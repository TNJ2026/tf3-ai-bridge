"""Warehouse plan runner: preview -> checkpoint -> fresh preview -> one commit -> audit.

Uses the running bridge, so preview tokens stay in its engine instance. Never
loads historical build scripts, invents warehouse slots, or retries a mutation.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server/src"))
from tf3_mcp.bridge import Bridge

PLAN = ROOT / "exports/supply_warehouse_20261002/optimized_network.json"
RESOURCE = "::/warehouses/warehouse.con"
MODULE = "::/warehouses/wh_universal.module"


class StopBatch(RuntimeError):
    pass


@contextmanager
def batch_lock(directory):
    """One warehouse runner per live bridge, including read-only reconciliation."""
    path = Path(directory) / "warehouse_batch.lock"
    with path.open("a+b") as handle:
        handle.seek(0)
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise StopBatch("另一个仓库批次正在执行，禁止并发施工或核对") from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def fingerprint(world):
    # Resolve by names/resources and coordinates, never by historical entity ids.
    return sorted(("town", t["name"], round(t["position"]["x"], 2), round(t["position"]["y"], 2))
                  for t in world["towns"]) + sorted(
        ("industry", i["fileName"], round(i["position"]["x"], 2), round(i["position"]["y"], 2))
        for i in world["industries"])


def module_layout(config):
    modules = config["params"].get("modules", {})
    if not isinstance(modules, dict) or len(modules) != 4:
        return False
    coordinates = set()
    for key, module in modules.items():
        if module.get("name") != MODULE or module.get("variant") != 0:
            return False
        slot = int(key)
        if slot % 10 != 0:
            return False
        value = slot // 10
        coordinates.add((value % 250000 - 250, value // 250000 - 250))
    return coordinates == {(0, 3), (4, 3), (0, 7), (4, 7)}


def pose_matches(config, task):
    p, q = config["position"], task["position"]
    if math.hypot(p["x"] - q["x"], p["y"] - q["y"]) > .1:
        return False
    angle = math.radians(task.get("rotation", 0))
    col = config["transform"][0]
    return abs(col["x"] - math.cos(angle)) < .001 and abs(col["y"] - math.sin(angle)) < .001


def preview_ok(preview):
    check = preview.get("check", {})
    return (preview.get("preview") is True and bool(preview.get("preview_token"))
            and not preview.get("blocked") and check.get("ok") is True
            and not check.get("critical") and not check.get("blocked")
            and not check.get("structural_only") and check.get("collisions") == []
            and not check.get("unexpected_removals") and not check.get("collision_data_unavailable"))


AUDIT = r'''
local target = TARGET
local result = {warehouses={}, coveringStations={}, totalCapacity=0}
local CT = api.type.ComponentType
local stockEntities = {}
api.engine.forEachEntityWithComponent(function(id)
  local w = api.engine.getComponent(id, CT.WAREHOUSE)
  if w.construction == target then
    local list = api.engine.getComponent(w.stockList, CT.STOCK_LIST)
    assert(list, "warehouse stock list unreadable")
    local row = {entity=id, stockList=w.stockList, stocks={}}
    stockEntities[id]=true;stockEntities[w.stockList]=true
    for index, stock in ipairs(list.stocks) do
      local cargos={}
      api.res.cargoTypeRep.forEachCargoType(stock.cargoTypes,function(cargo) cargos[#cargos+1]=cargo end)
      row.stocks[#row.stocks+1]={index=index-1,capacity=stock.capacity,cargoIds=cargos,mixedTypes=stock.mixedTypes}
      result.totalCapacity=result.totalCapacity+stock.capacity
    end
    result.warehouses[#result.warehouses+1]=row
  end
end, CT.WAREHOUSE)
api.engine.forEachEntityWithComponent(function(id)
  local catches=api.engine.system.catchmentAreaSystem.getStationCatchables(id,true)
  local covered=false
  for _,entity in pairs(catches) do if stockEntities[entity] or entity==target then covered=true end end
  if covered then
    local station=api.engine.getComponent(id,CT.STATION)
    local terminals={}
    for index,terminal in ipairs(station.terminals) do
      terminals[#terminals+1]={index=index-1,cargoLoad=terminal.cargoLoad,cargoUnload=terminal.cargoUnload}
    end
    result.coveringStations[#result.coveringStations+1]={entity=id,terminals=terminals}
  end
end, CT.STATION)
return result
'''


class Runner:
    def __init__(self, bridge, plan, output, action, disk_bridge=False):
        self.bridge, self.plan, self.output, self.action = bridge, plan, Path(output), action
        self.disk_bridge = disk_bridge
        self.disk_preview_args = None
        self.disk_source = None
        self.path = self.output / "ledger.json"
        digest = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if self.path.exists():
            self.ledger = json.loads(self.path.read_text(encoding="utf-8"))
            if self.ledger["planDigest"] != digest:
                raise StopBatch("任务清单改变；旧施工记录不能套用到新方案，请使用新的输出目录")
        else:
            self.ledger = {"schema": 1, "planDigest": digest, "items": {}, "events": []}
        self.previous_state = None

    def flush(self):
        write_json(self.path, self.ledger)

    async def call(self, command, args=None, engine=True):
        if not self.bridge.heartbeat().get("connected"):
            raise StopBatch("心跳过期；停止请求")
        if self.disk_bridge and command in ("build_warehouse", "commit_facility"):
            source = (ROOT / "mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua").read_text(encoding="utf-8")
            assert "]====]" not in source
            if command == "build_warehouse":
                self.disk_preview_args = dict(args or {})
                self.disk_source = source
            elif self.disk_preview_args is None or source != self.disk_source:
                raise StopBatch("磁盘桥接源码或预览输入改变；禁止提交")
            # Engine eval does not retain Python-call scratch reliably. Re-preview
            # and consume the NEW token in the same isolated engine invocation.
            payload = json.dumps(self.disk_preview_args, ensure_ascii=False)
            delimiter = "==="
            while "]" + delimiter + "]" in payload:
                delimiter += "="
            code = ('local env=setmetatable({},{__index=_G});local B=assert(load([====[' + source
                    + ']====],"=warehouse_batch_bridge","t",env))()._internal;local a=B.json.decode(['
                    + delimiter + '[' + payload + ']' + delimiter + ']);local p=B.commands.build_warehouse(a);')
            if command == "build_warehouse":
                code += 'return B.json.encode(p)'
            else:
                code += ('if not p.preview_token then return B.json.encode({built=false,blocked=true,freshPreview=p}) end;'
                         'local r=B.commands.commit_facility({preview_token=p.preview_token});r.freshPreview=p;return B.json.encode(r)')
            result = await self.bridge.call("eval", {"code": code}, engine=True, timeout=30)
        else:
            result = await self.bridge.call(command, args or {}, engine=engine, timeout=30)
        if isinstance(result, str):
            result = json.loads(result)
        if not isinstance(result, dict):
            raise StopBatch(f"{command} 返回无法识别的结果")
        return result

    async def session(self):
        state = await self.call("get_game_state")
        world = await self.call("get_map_info")
        if fingerprint(world) != fingerprint(self.plan["snapshot"]["map"]):
            raise StopBatch("当前城镇/产业位置与规划地图不同；重新调查并规划")
        expected = self.plan["snapshot"]["state"]
        if (state["world"], state["player"]) != (expected["world"], expected["player"]):
            raise StopBatch("当前玩家或世界与规划不一致")
        if self.previous_state and (state["gameTime"] < self.previous_state["gameTime"]
                                    or state["tickCount"] < self.previous_state["tickCount"]):
            raise StopBatch("检测到重载/会话回退；停止并重新解析")
        if self.action == "build" and state["speedup"] != 0:
            raise StopBatch("批量施工要求当前游戏已暂停，以保持预览和提交一致；脚本不自动改变速度")
        self.previous_state = state
        self.ledger["lastSession"] = state
        self.flush()
        return state

    async def facilities(self):
        rows = (await self.call("list_facilities", {"mine_only": True}))["items"]
        return [row for row in rows if row["resource"] == RESOURCE]

    async def existing(self, task):
        q = task["position"]
        rows = [r for r in await self.facilities()
                if math.hypot(r["position"]["x"] - q["x"], r["position"]["y"] - q["y"]) < 5]
        if len(rows) > 1:
            raise StopBatch(f'{task["name"]} 附近有多个仓库，需核对')
        if not rows:
            return None
        config = await self.call("get_facility_config", {"entity": rows[0]["entity"]})
        if not module_layout(config) or not pose_matches(config, task):
            raise StopBatch(f'{task["name"]} 已有仓库布局/朝向不匹配，禁止重复建造')
        return config

    async def audit(self, task, config):
        stock = await self.call("eval", {"code": AUDIT.replace("TARGET", str(config["entity"]))})
        cargos = {cargo for warehouse in stock["warehouses"] for item in warehouse["stocks"] for cargo in item["cargoIds"]}
        static = (module_layout(config) and pose_matches(config, task)
                  and config["owner"] == self.previous_state["player"]
                  and stock["totalCapacity"] >= task["initialCapacity"]
                  and set(task["cargoIds"]).issubset(cargos))
        coverage = any(t.get("cargoLoad") is True and t.get("cargoUnload") is True
                       for station in stock["coveringStations"] for t in station["terminals"])
        result = {"entity": config["entity"], "staticVerified": static, "stock": stock,
                  "stationCoverageVerified": coverage, "roadPathVerified": False,
                  "operationalAccepted": False, "simulationVerified": False, "reloadVerified": False,
                  "pending": ["真实道路TRUCK双向接入", "来源/目的地货物路由与线路", "实际收货和发货", "长期模拟及重载"]}
        if not coverage:
            result["pending"].insert(0, "货运站真实覆盖与装卸")
        return result

    async def checkpoint(self, phase):
        name = "tf3_wh_" + phase + "_" + time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        path = self.bridge.dir.parent / "save" / (name + ".sav")
        await self.call("eval", {"code": f'app.saveGame("{name}",function() end,false,true);return {{requested=true}}'}, engine=False)
        deadline = time.monotonic() + 30
        previous = None
        while time.monotonic() < deadline:
            if path.exists():
                stat = path.stat()
                current = (stat.st_size, stat.st_mtime_ns)
                if stat.st_size > 0 and current == previous:
                    self.ledger["events"].append({"save": str(path), "bytes": stat.st_size, "reloadVerified": False})
                    self.flush()
                    return
                previous = current
            await asyncio.sleep(.5)
        raise StopBatch("存档文件未确认完成；停止施工")

    async def run(self):
        await self.session()
        if self.action == "build" and any(x.get("status") in ("commit_started", "needs_reconciliation")
                                          for x in self.ledger["items"].values()):
            raise StopBatch("存在未核实的施工请求；只能先运行verify，不自动重试")
        if self.action == "build":
            await self.checkpoint("before")
        for task in self.plan["warehouses"]:
            key = task["warehouseId"]
            item = self.ledger["items"].setdefault(key, {"name": task["name"], "commitAttempts": 0})
            await self.session()
            config = await self.existing(task)
            if config:
                result = await self.audit(task, config)
                item.update(status="static_verified" if result["staticVerified"] else "needs_reconciliation", audit=result)
                self.flush()
                if not result["staticVerified"]:
                    raise StopBatch(f'{task["name"]} 配置或库容验收失败')
                print(f'{key}: 已存在，静态验收通过；运营验收待完成', flush=True)
                continue
            if item["commitAttempts"] > 0:
                raise StopBatch(f"{key} 之前提交过但现在找不到；需人工核对，不重复建造")
            if self.action == "verify":
                item["status"] = "not_built"
                self.flush()
                print(f"{key}: 尚未建造", flush=True)
                continue
            p = task["position"]
            ground = await self.call("get_terrain", {"x": p["x"], "y": p["y"]})
            if ground.get("valid") is not True or ground.get("water") is not False:
                raise StopBatch(f"{key} 地形无效或水域信息不明确")
            args = {"x": p["x"], "y": p["y"], "z": ground["height"], "module_count": 4,
                    "rotation": task.get("rotation", 0), "name": task["name"]}
            preview = await self.call("build_warehouse", args)
            item.update(status="preview_ready" if preview_ok(preview) else "preview_blocked", input=args, preview=preview)
            self.flush()
            if not preview_ok(preview):
                raise StopBatch(f"{key} 原生预览未通过；见ledger.json")
            if self.action == "preview":
                print(f"{key}: 原生预览通过（令牌不会用于后续build）", flush=True)
                continue
            # Persistent write-ahead marker prevents a second submission after any unknown result.
            item.update(status="commit_started", commitAttempts=1)
            self.flush()
            try:
                committed = await self.call("commit_facility", {"preview_token": preview["preview_token"]})
                item["commit"] = committed
                if committed.get("built") is not True or committed.get("verified") is not True:
                    raise StopBatch(f"{key} 提交未完整确认")
                await self.session()
                config = await self.existing(task)
                if not config or config["entity"] != committed.get("entity"):
                    raise StopBatch(f"{key} 提交后实体读回不匹配")
                result = await self.audit(task, config)
                item["audit"] = result
                if not result["staticVerified"]:
                    raise StopBatch(f"{key} 静态验收失败")
                item["status"] = "static_verified"
                self.flush()
                await self.checkpoint(key + "_after")
            except Exception:
                item["status"] = "needs_reconciliation"
                self.flush()
                raise
            print(f"{key}: 单次施工并静态验收通过；接驳/运营待验收", flush=True)
        self.ledger["lastAction"] = self.action
        self.ledger["operationalAccepted"] = False
        self.flush()


def validate(plan):
    tasks = plan["warehouses"]
    if not tasks or len({t["warehouseId"] for t in tasks}) != len(tasks):
        raise StopBatch("仓库任务为空或编号重复")
    for task in tasks:
        if task["initialModules"] != 4 or task["initialCapacity"] != 2000 or task["moduleResource"] != MODULE:
            raise StopBatch("此脚本仅支持已核对的4模块通用仓库布局")
        for value in (task["position"]["x"], task["position"]["y"], task.get("rotation", 0)):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise StopBatch("坐标/角度必须有限")
        if any(not isinstance(cargo, int) or cargo < 0 for cargo in task["cargoIds"]):
            raise StopBatch("货物编号必须是非负整数")
    for index, task in enumerate(tasks):
        for other in tasks[index + 1:]:
            if all(task["reserved"]["min"][k] < other["reserved"]["max"][k]
                   and task["reserved"]["max"][k] > other["reserved"]["min"][k] for k in ("x", "y")):
                raise StopBatch("仓库升级预留区互相重叠")


async def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "build", "verify"))
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output", type=Path, default=ROOT / "exports/supply_warehouse_20261002/batch")
    parser.add_argument("--bridge-dir", type=Path)
    parser.add_argument("--disk-bridge", action="store_true",
                        help="在隔离引擎eval加载新版磁盘接口；重新预览与提交在同次调用，不重载游戏或写全局")
    args = parser.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    validate(plan)
    bridge = Bridge(directory=args.bridge_dir)
    try:
        with batch_lock(bridge.dir):
            runner = Runner(bridge, plan, args.output, args.action, args.disk_bridge)
            try:
                await runner.run()
            except Exception as error:
                runner.ledger["events"].append({"action": args.action, "stopped": str(error), "time": time.time()})
                runner.flush()
                raise
    except Exception as error:
        print(f"停止：{error}\n记录：{args.output / 'ledger.json'}", file=sys.stderr)
        return 2
    print(f"记录：{runner.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
