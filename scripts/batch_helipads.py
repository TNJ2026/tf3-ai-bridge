"""Native helicopter facilities: preview -> backup -> one commit -> station audit.

Reuses warehouse batch session, journal, locking and backup guards. Default is 29
land candidates; marine sites are excluded. Roads, routes and aircraft are separate.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path
from batch_warehouses import ROOT, PLAN, Runner, Bridge, StopBatch, batch_lock, pose_matches

RESOURCE = "::/stations/air/helipad.con"

AUDIT = '''local target=TARGET;local CT=api.type.ComponentType
local map=api.engine.system.streetConnectorSystem.getStation2ConstructionMap()
local out={stations={}}
api.engine.forEachEntityWithComponent(function(id)
 if map[id]==target then
  local station=api.engine.getComponent(id,CT.STATION)
  local row={entity=id,terminals={},catchables={}}
  for index,t in ipairs(station.terminals) do
   row.terminals[#row.terminals+1]={index=index-1,cargoLoad=t.cargoLoad,cargoUnload=t.cargoUnload}
  end
  for _,entity in pairs(api.engine.system.catchmentAreaSystem.getStationCatchables(id,true)) do
   row.catchables[#row.catchables+1]=entity
  end
  out.stations[#out.stations+1]=row
 end
end,CT.STATION)
return out'''

def land_tasks(plan, ids=None):
    tasks=[]
    for site in plan["sites"]:
        if site.get("role") != "facility" or not site.get("position"):
            continue
        # Native helipad geometry marker; never reinterpret a port as a helipad.
        basis=site.get("basis", "").lower()
        if "helipad" not in basis and "停机坪36×38" not in basis:
            continue
        task=dict(site,warehouseId=f"H{len(tasks)+1:02d}",initialCapacity=0,cargoIds=[])
        tasks.append(task)
    if ids:
        unknown=set(ids)-{t["warehouseId"] for t in tasks}
        if unknown:
            raise StopBatch("未知停机坪编号："+",".join(sorted(unknown)))
        tasks=[t for t in tasks if t["warehouseId"] in ids]
    if not tasks:
        raise StopBatch("没有原生helipad陆地候选位置")
    # Retain full plan digest, including reservations and the selected tasks.
    return dict(plan,warehouses=tasks)

class HelipadRunner(Runner):
    async def call(self, command, args=None, engine=True):
        if command not in ("build_warehouse", "commit_facility"):
            return await super().call(command,args,engine)
        if not self.bridge.heartbeat().get("connected"):
            raise StopBatch("游戏心跳过期")
        source=(ROOT/"mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua").read_text(encoding="utf-8")
        if command == "build_warehouse":
            self.disk_preview_args={k:v for k,v in args.items() if k != "module_count"}
            self.disk_source=source
        elif self.disk_preview_args is None or source != self.disk_source:
            raise StopBatch("源码或预览输入变化；禁止提交")
        payload=json.dumps(self.disk_preview_args,ensure_ascii=False,allow_nan=False)
        delimiter="====="
        while "]"+delimiter+"]" in payload or "]"+delimiter+"]" in source:
            delimiter+="="
        def literal(s):
            return "["+delimiter+"["+s+"]"+delimiter+"]"
        code=('local env=setmetatable({},{__index=_G});local B=assert(load('+literal(source)
              +',"=helipad_batch_bridge","t",env))()._internal;local a=B.json.decode('+literal(payload)
              +');local p=B.commands.build_helipad(a);')
        if command == "build_warehouse":
            code+='return B.json.encode(p)'
        else:
            code+=('if not p.preview_token then return B.json.encode({built=false,blocked=true,freshPreview=p}) end;'
                   'local r=B.commands.commit_facility({preview_token=p.preview_token});r.freshPreview=p;return B.json.encode(r)')
        result=await self.bridge.call("eval",{"code":code},engine=True,timeout=30)
        return json.loads(result) if isinstance(result,str) else result

    async def existing(self, task):
        rows=(await self.call("list_facilities",{"mine_only":False}))["items"]
        p=task["position"]
        candidates=[r for r in rows if r["resource"]==RESOURCE
                    and math.hypot(r["position"]["x"]-p["x"],r["position"]["y"]-p["y"])<5]
        if len(candidates)>1:
            raise StopBatch("停机坪位置存在多个设施")
        if not candidates:
            return None
        c=await self.call("get_facility_config",{"entity":candidates[0]["entity"]})
        if not pose_matches(c,task) or c["owner"]!=self.previous_state["player"]:
            raise StopBatch("既有停机坪位置、朝向或所有者不一致")
        return c

    async def audit(self, task, config):
        native=await self.call("eval",{"code":AUDIT.replace("TARGET",str(config["entity"]))})
        cargo=any(t.get("cargoLoad") is True and t.get("cargoUnload") is True
                  for s in native["stations"] for t in s["terminals"])
        return {"entity":config["entity"],"staticVerified":pose_matches(config,task)
                and config["owner"]==self.previous_state["player"] and cargo,
                "cargoTerminalsVerified":cargo,"native":native,"roadPathVerified":False,
                "operationalAccepted":False,"simulationVerified":False,"reloadVerified":False,
                "pending":["入口道路及货物覆盖","直升机航线及装卸配置","实际运输","长期模拟及重载"]}

async def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("preview","build","verify"))
    p.add_argument("--plan",type=Path,default=PLAN)
    p.add_argument("--output",type=Path,default=ROOT/"exports/supply_warehouse_20261002/helipad_batch_all")
    p.add_argument("--ids",nargs="+",help="H01..H29；省略时处理所有陆地停机坪")
    p.add_argument("--bridge-dir",type=Path)
    a=p.parse_args(argv)
    plan=land_tasks(json.loads(a.plan.read_text(encoding="utf-8-sig")),a.ids)
    bridge=Bridge(directory=a.bridge_dir)
    runner=HelipadRunner(bridge,plan,a.output,a.action)
    try:
        with batch_lock(bridge.dir):
            await runner.run()
        return 0
    except Exception as error:
        runner.ledger["events"].append({"stopped":str(error),"time":time.time()});runner.flush()
        print(f"停止：{error}；记录：{runner.path}",file=sys.stderr);return 2

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
