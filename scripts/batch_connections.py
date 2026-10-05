"""Warehouse frontage roads: preview, one construction request, readback.

Coordinates are engineering anchors, never historical entity ids. Unknown outcomes
remain locked until a person reviews the actual map; verify never repairs roads.
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

# Current surveyed public-road anchors; resolved again on EVERY request.
ANCHORS = {
    "W1": ((369.91397094727, 1085.4735107422), [(369, 978), (469, 978)]),
    "W2": ((-2653.484375, 5137.5424804688), [(-2970, 5204)]),
    "W3": ((3914.1665039062, 6734.5126953125), [(3912, 6802), (3972, 6802)]),
    "W4": ((6435.3203125, 1802.3934326172), [(6759, 1802), (6759, 1930)]),
}

def road_preview_ok(result):
    return (result.get("buildable") is True and not result.get("critical")
            and not result.get("blocked") and not result.get("blocking")
            and not result.get("messages"))

def point(xy):
    return dict(x=xy[0], y=xy[1])

def within_current(a, b, task, margin=5):
    """Conservative swept road envelope against native four-module footprint."""
    theta = math.radians(task.get("rotation", 0))
    origin = task["position"]
    def local(p):
        x, y = p[0]-origin["x"], p[1]-origin["y"]
        return x*math.cos(theta)+y*math.sin(theta), -x*math.sin(theta)+y*math.cos(theta)
    a, b = local(a), local(b)
    # Liang-Barsky slab intersection, expanded for carriageway width.
    lo, hi = 0., 1.
    for axis, mn, mx in ((0, -20-margin, 52+margin), (1, -12-margin, 76+margin)):
        delta = b[axis]-a[axis]
        if abs(delta) < 1e-9:
            if not mn <= a[axis] <= mx:
                return False
        else:
            t1, t2 = sorted(((mn-a[axis])/delta, (mx-a[axis])/delta))
            lo, hi = max(lo,t1), min(hi,t2)
            if lo > hi:
                return False
    return True

class ConnectionRunner(Runner):
    async def road_args(self, task):
        config = await self.existing(task)
        if config is None:
            raise StopBatch("先建造并验收目标仓库")
        anchor, points = ANCHORS[task["warehouseId"]]
        chain = [anchor] + points
        if any(within_current(a,b,task) for a,b in zip(chain,chain[1:])):
            raise StopBatch("接驳走廊侵入仓库占地；重新规划")
        nearby = await self.call("find_nearby", {**point(anchor), "radius": 2, "limit": 20})
        nodes = [n for n in nearby["nodes"] if n.get("position")
                 and math.hypot(n["position"]["x"]-anchor[0], n["position"]["y"]-anchor[1]) < .15
                 and n.get("connections") and not n.get("construction")]
        if len(nodes) != 1:
            raise StopBatch("公路锚点改变或被设施占用；重新调查，不套用旧节点")
        n = nodes[0]
        args = {"start": {"node": n["id"]}, "end": point(points[-1]),
                "via": [point(p) for p in points[:-1]], "street_type": "country/country_new_small",
                "snap_radius": 0, "max_segment_length": 50, "allow_collisions": False}
        return args, {"warehouse": config["entity"], "node": n}

    async def readback(self, commit):
        # IDs here are readback hints, not reusable construction parameters.
        ids = commit.get("edges", [])
        if not ids:
            return {"geometryVerified": False, "junctionVerified": False}
        code = '''local out={edges={}};local CT=api.type.ComponentType
for _,id in ipairs(IDS) do
 local e=api.engine.getComponent(id,CT.BASE_EDGE)
 if e then out.edges[#out.edges+1]={id=id,node0=e.node0,node1=e.node1,
  x0=e.position0.x,y0=e.position0.y,x1=e.position1.x,y1=e.position1.y} end
end;return out'''.replace("IDS", "{"+",".join(str(int(i)) for i in ids)+"}")
        current = await self.call("eval", {"code": code})
        old = commit.get("readback", {}).get("edges")
        geometry = len(current["edges"]) == len(ids) and (old is None or old == current["edges"])
        return {**current, "geometryVerified": geometry,
                "junctionVerifiedAtCommit": commit.get("verified") is True,
                "warehouseCargoCoverageVerified": False, "simulationVerified": False,
                "operationalAccepted": False}

    async def run(self):
        await self.session()
        if self.action == "build" and any(i.get("commitAttempts",0) and i.get("status") != "road_verified"
                                           for i in self.ledger["items"].values()):
            raise StopBatch("存在未核实的道路提交；先verify并核对地图，禁止重发")
        if self.action == "build":
            await self.checkpoint("road_before")
        for task in self.plan["warehouses"]:
            key=task["warehouseId"]
            item=self.ledger["items"].setdefault(key,{"commitAttempts":0,"name":task["name"]})
            await self.session()
            if item.get("commitAttempts"):
                if not item.get("commit") or not item["commit"].get("readback"):
                    raise StopBatch(f"{key} 请求结果未知；请依据坐标检查实际道路，脚本不重试")
                audit=await self.readback(item["commit"])
                item["audit"]=audit
                if not audit["geometryVerified"]:
                    item["status"]="needs_reconciliation";self.flush()
                    raise StopBatch(f"{key} 道路被替换或改变；重新调查")
                self.flush()
                print(f"{key}: 道路几何读回；货运覆盖及当前寻路另行验收",flush=True)
                continue
            args, resolved=await self.road_args(task)
            item["resolved"]=resolved
            if self.action == "verify":
                item["status"]="not_submitted";self.flush();continue
            preview=await self.call("build_road",{**args,"preview":True})
            item.update(input=args,preview=preview,status="preview_ready" if road_preview_ok(preview) else "preview_blocked")
            self.flush()
            if not road_preview_ok(preview):
                raise StopBatch(f"{key} 道路原生预览未通过；停止，见ledger.json")
            if self.action == "preview":
                print(f"{key}: 道路预览通过",flush=True);continue
            # Re-resolve before committing; no reused preview or entity IDs.
            await self.session()
            fresh, current=await self.road_args(task)
            if current != resolved:
                raise StopBatch("仓库或路口发生变化；重新规划")
            item.update(status="commit_started",commitAttempts=1);self.flush()
            try:
                result=await self.call("build_road",{**fresh,"preview":False})
                item["commit"]=result;self.flush()
                if not all(result.get(k) is True for k in ("built","complete","verified")):
                    raise StopBatch("道路提交未完整确认；禁止重建")
                audit=await self.readback(result)
                result["readback"]=audit
                item["audit"]=audit
                if not audit["geometryVerified"]:
                    raise StopBatch("施工后道路读回失败")
                item["status"]="road_verified";self.flush()
                await self.checkpoint(key+"_road_after")
            except Exception:
                item["status"]="needs_reconciliation";self.flush();raise

async def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("preview","build","verify"))
    p.add_argument("--plan",type=Path,default=PLAN)
    p.add_argument("--output",type=Path,default=ROOT/"exports/supply_warehouse_20261002/road_batch")
    p.add_argument("--bridge-dir",type=Path)
    a=p.parse_args(argv)
    plan=json.loads(a.plan.read_text(encoding="utf-8-sig"))
    bridge=Bridge(directory=a.bridge_dir)
    runner=ConnectionRunner(bridge,plan,a.output,a.action)
    try:
        with batch_lock(bridge.dir):
            await runner.run()
        return 0
    except Exception as error:
        runner.ledger["events"].append({"stopped":str(error),"time":time.time()});runner.flush()
        print(f"停止：{error}；记录：{runner.path}",file=sys.stderr);return 2

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
