"""Native warehouse starter layouts, collision/session guards and stock readback."""
import asyncio
import json

import pytest

from test_e2e import MOCK_API, MOCK_CONSTRUCTION, SCRIPT, lupa_mod
from test_facilities import FIXTURE


@pytest.fixture
def warehouse_game():
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute(MOCK_CONSTRUCTION.read_text(encoding="utf8"))
    lua.execute(FIXTURE)
    lua.execute('''
local CT=api.type.ComponentType
CT.WAREHOUSE=9000;CT.STOCK_LIST=9001
for _,row in pairs(components) do
 local c=row[CT.CONSTRUCTION]
 if c and not c.fileName then row[CT.CONSTRUCTION]=nil end
end
api.res.metaConstructionRep={find=function()return 0 end,get=function()
 return {availability={yearFrom=1940,yearTo=1980},createTemplateScript={
 fileName=BAD_TEMPLATE and "unknown@factory" or "::/warehouses/warehouse.script@createTemplateFn",
 params={initialModule="wh_universal.module"}}}
end}
local oldFind=api.res.moduleRep.find;local oldGet=api.res.moduleRep.get
api.res.moduleRep.find=function(name)
 if name=="::/warehouses/wh_universal.module" then return 50 end
 return oldFind(name)
end
api.res.moduleRep.get=function(id)
 if id==50 then return {availability={yearFrom=1850,yearTo=0},type="warehouse_large",
 metadata={type="universal"},updateScript={fileName="native@universal",params={}}} end
 return oldGet(id)
end
ug_require=function(name)
 assert(name=="::/game_mechanics/company/company_util.tl","no global native script imports")
 return {getConstructionDisableCacheData=function()return {} end,
 getConstructionDisableReason=function()return LOCKED and {reason="no permit"} or {numRemaining=1} end}
end
api.engine.terrain.isValidCoordinate=function()return true end
api.engine.terrain.isOnWater=function()return WATER==true end
local oldSend=api.cmd.sendCommand
api.cmd.sendCommand=function(p,callback)
 oldSend(p,callback)
 local n=0;for _ in pairs(p.constructionsToAdd[1].params.modules)do n=n+1 end
 components[8010]={[CT.WAREHOUSE]={construction=8001,stockList=8011}}
 components[8011]={[CT.STOCK_LIST]={stocks={{capacity=WRONG_CAPACITY and 1 or n*500}}}}
end
''')
    script = lua.execute(SCRIPT.read_text(encoding="utf8"))

    def call(name, **kwargs):
        result = script["_internal"]["commands"][name](lua.table_from(kwargs, recursive=True))
        return json.loads(script["_internal"]["json"]["encode"](result))

    return lua, call


def preview(call, **args):
    return call("build_warehouse", x=700, y=740, z=2, **args)


@pytest.mark.parametrize("count,coordinates", [(1, {(0, 3)}), (4, {(0, 3), (4, 3), (0, 7), (4, 7)})])
def test_starter_encoding_and_exact_capacity_readback(warehouse_game, count, coordinates):
    lua, call = warehouse_game
    p = preview(call, module_count=count)
    assert lua.globals().SUBMISSIONS is None
    slots = {int(key) for key in p["parameters"]["modules"]}
    assert slots == {10 * (250000 * (y + 250) + x + 250) for x, y in coordinates}
    assert all(m["metadata"]["type"] == "universal" for m in p["parameters"]["modules"].values())
    result = call("commit_facility", preview_token=p["preview_token"])
    assert result["built"] and result["verified"]
    assert result["stock_capacity"] == count * 500
    assert result["externalConnectionsBuilt"] is False
    with pytest.raises(Exception, match="consumed"):
        call("commit_facility", preview_token=p["preview_token"])
    with pytest.raises(Exception, match="already exists"):
        preview(call)
    assert lua.globals().SUBMISSIONS == 1


@pytest.mark.parametrize("count", [0, 2, 16, 1.5, "4"])
def test_invalid_size_does_not_preview(warehouse_game, count):
    lua, call = warehouse_game
    with pytest.raises(Exception, match="module_count"):
        preview(call, module_count=count)
    assert lua.globals().PREVIEWS is None


def test_template_permission_and_water_guards(warehouse_game):
    lua, call = warehouse_game
    for variable, message in (("BAD_TEMPLATE", "unrecognized"), ("LOCKED", "locked"), ("WATER", "dry land")):
        lua.execute(f"{variable}=true")
        with pytest.raises(Exception, match=message):
            preview(call)
        lua.execute(f"{variable}=false")
    assert lua.globals().SUBMISSIONS is None


def test_collision_rechecked_at_commit(warehouse_game):
    lua, call = warehouse_game
    lua.execute("COLLISIONS={{entity=99999}}")
    assert preview(call)["blocked"]
    lua.execute("COLLISIONS={}")
    p = preview(call)
    lua.execute("COLLISIONS={{entity=99999}}")
    assert call("commit_facility", preview_token=p["preview_token"])["blocked"]
    assert lua.globals().SUBMISSIONS is None


def test_world_change_consumes_preview(warehouse_game):
    lua, call = warehouse_game
    p = preview(call)
    lua.execute("api.engine.util.getWorld=function()return 99 end")
    with pytest.raises(Exception, match="changed"):
        call("commit_facility", preview_token=p["preview_token"])
    assert lua.globals().SUBMISSIONS is None


def test_wrong_capacity_is_not_verified(warehouse_game):
    lua, call = warehouse_game
    p = preview(call)
    lua.execute("WRONG_CAPACITY=true")
    result = call("commit_facility", preview_token=p["preview_token"])
    assert result["built"] and not result["verified"]


def test_mcp_warehouse_is_preview_in_engine(monkeypatch):
    from tf3_mcp import server
    calls = []

    async def fake_call(cmd, **args):
        calls.append((cmd, args))
        return {"preview": True}

    monkeypatch.setattr(server, "_call", fake_call)
    asyncio.run(server.build_warehouse(700, 740, 2))
    cmd, args = calls[0]
    assert cmd == "build_warehouse" and args["preview"] and args["_engine"]
    assert args["module_count"] == 4


def test_facility_ticket_survives_engine_recreation_and_is_single_use(warehouse_game):
    lua, _ = warehouse_game
    state = lua.execute("local v={};return {get=function()return v end,set=function(_,x)v=x end}")
    counter = 0
    def event(cmd, epoch="one", **args):
        nonlocal counter
        counter += 1
        script = lua.execute(SCRIPT.read_text("utf8"))
        script["handleEvent"](None, state, None, "tf3_mcp", "tf3_mcp_request",
            json.dumps(dict(id=str(counter), cmd=cmd, args=args, facilityEpoch=epoch)))
        responses = state["get"](state)["responses"]
        result = json.loads(responses[len(responses)]["text"])
        codec = script["_internal"]["json"]
        state["set"](state, codec["decode"](codec["encode"](state["get"](state))))
        return result
    stale = event("build_warehouse", x=700,y=740,z=2,module_count=1)["result"]["preview_token"]
    assert not event("commit_facility", epoch="two", preview_token=stale)["ok"]
    p = event("build_warehouse", epoch="two", x=700,y=740,z=2,module_count=1)["result"]
    r = event("commit_facility", epoch="two", preview_token=p["preview_token"])
    assert r["ok"] and r["result"]["built"] and r["result"]["verified"]
    assert not event("commit_facility", epoch="two", preview_token=p["preview_token"])["ok"]
    assert lua.globals().SUBMISSIONS == 1


def test_commit_reconciles_id_reused_from_different_construction(warehouse_game):
    lua, call = warehouse_game
    lua.execute("components[8001]={[api.type.ComponentType.CONSTRUCTION]={fileName='::/industries/farm/farm.con'}}")
    p = preview(call, module_count=1)
    r = call("commit_facility", preview_token=p["preview_token"])
    assert r["built"] and r["verified"] and r["entity"] == 8001
    assert r["stock_capacity"] == 500
    assert lua.globals().SUBMISSIONS == 1
