import asyncio
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from batch_connections import ConnectionRunner, road_preview_ok, within_current
from batch_helipads import land_tasks, HelipadRunner
from batch_warehouses import StopBatch

@pytest.mark.parametrize("rotation", [0, 90, 37])
def test_corridors_respect_rotated_warehouse_envelope(rotation):
    import math
    task={"position":{"x":100,"y":200},"rotation":rotation}
    def world(x,y):
        a=math.radians(rotation)
        return (100+x*math.cos(a)-y*math.sin(a),200+x*math.sin(a)+y*math.cos(a))
    assert within_current(world(-100,0),world(100,0),task)
    assert not within_current(world(-100,-30),world(100,-30),task)

@pytest.mark.parametrize("bad",[{"blocked":True},{"critical":True},{"blocking":[1]},
                               {"messages":["too sharp"]},{"buildable":False}])
def test_unsafe_road_preview_rejected(bad):
    assert not road_preview_ok({"buildable":True,**bad})

def test_manifest_excludes_ports_and_resolves_selection():
    plan={"sites":[
        {"id":"land1","role":"facility","position":{"x":1,"y":2},"basis":"native HELIPAD"},
        {"id":"port","role":"port","position":{"x":3,"y":4},"basis":"helipad"},
        {"id":"unplaced","role":"facility","basis":"helipad"},
        {"id":"warehouse","role":"facility","position":{"x":5,"y":6},"basis":"warehouse"},
        {"id":"land2","role":"facility","position":{"x":7,"y":8},"basis":"停机坪36×38"}]}
    original=json.dumps(plan,ensure_ascii=False)
    tasks=land_tasks(plan)["warehouses"]
    assert [t["id"] for t in tasks]==["land1","land2"]
    assert json.dumps(plan,ensure_ascii=False)==original
    assert len(land_tasks(plan,["H02"])["warehouses"])==1
    with pytest.raises(StopBatch,match="未知"):
        land_tasks(plan,["H99"])

def test_road_timeout_is_journalled_and_never_replayed(tmp_path):
    class Fake(ConnectionRunner):
        async def session(self): pass
        async def checkpoint(self,phase): pass
        async def road_args(self,t): return {"start":{"node":10}}, {"warehouse":20}
        async def call(self,c,a=None,engine=True):
            if a.get("preview"):
                return {"buildable":True}
            self.submissions+=1
            raise TimeoutError("unknown")
    r=Fake(None,{"warehouses":[{"warehouseId":"W1","name":"one"}]},tmp_path,"build")
    r.submissions=0
    with pytest.raises(TimeoutError): asyncio.run(r.run())
    with pytest.raises(StopBatch,match="禁止重发"): asyncio.run(r.run())
    assert r.submissions==1
    assert json.loads(r.path.read_text(encoding="utf-8"))["items"]["W1"]["commitAttempts"]==1

def test_heli_same_eval_fresh_preview_and_source_guard(tmp_path):
    class Bridge:
        def heartbeat(self): return {"connected":True}
        async def call(self,c,a,**kwargs):
            self.code=a["code"]
            return {"preview":True,"preview_token":"one"}
    b=Bridge()
    r=HelipadRunner(b,{"snapshot":{}},tmp_path,"preview")
    asyncio.run(r.call("build_warehouse",{"x":1,"y":2,"z":3,"module_count":4}))
    assert "module_count" not in r.disk_preview_args
    asyncio.run(r.call("commit_facility",{}))
    assert 'local p=B.commands.build_helipad(a)' in b.code
    assert 'preview_token=p.preview_token' in b.code
    assert 'local env=setmetatable' in b.code
    r.disk_source="changed"
    with pytest.raises(StopBatch,match="源码"): asyncio.run(r.call("commit_facility",{}))

def test_cargo_station_missing_fails_facility_audit(tmp_path):
    class Fake(HelipadRunner):
        async def call(self,*args,**kwargs): return {"stations":[]}
    r=Fake(None,{"snapshot":{}},tmp_path,"verify")
    r.previous_state={"player":2}
    t={"position":{"x":1,"y":2},"rotation":0}
    c={"entity":3,"owner":2,"position":t["position"],"transform":[{"x":1,"y":0}]}
    audit=asyncio.run(r.audit(t,c))
    assert not audit["staticVerified"] and not audit["cargoTerminalsVerified"]
    assert not audit["operationalAccepted"]
