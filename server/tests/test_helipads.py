"""Exercise native helicopter proposals and one-use/session/collision guards."""
import json
import asyncio
import pytest
from test_e2e import MOCK_API, MOCK_CONSTRUCTION, SCRIPT, lupa_mod
from test_facilities import FIXTURE

@pytest.fixture
def heli_game():
    lua=lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute(MOCK_CONSTRUCTION.read_text(encoding="utf-8"))
    lua.execute(FIXTURE)
    lua.execute('''
local oldFind=api.res.constructionRep.find;local oldGet=api.res.constructionRep.get
api.res.constructionRep.find=function(n)
 if n=="::/stations/air/helipad.con" then return 50 end;return oldFind(n) end
api.res.constructionRep.get=function(id)
 if id==50 then return {metadata={},params={},availability={yearFrom=1950,yearTo=0},
 updateScript={fileName=BAD_SCRIPT and "unknown" or "::/stations/air/helipad/helipad.script@updateFn",params={}}} end
 return oldGet(id) end
ug_require=function(n)
 assert(n=="::/game_mechanics/company/company_util.tl")
 return {getConstructionDisableCacheData=function()return {} end,
 getConstructionDisableReason=function()return LOCKED and {reason="locked"} or {} end}
end
api.engine.terrain.isValidCoordinate=function()return true end
api.engine.terrain.isOnWater=function()return WATER==true end
''')
    script=lua.execute(SCRIPT.read_text(encoding="utf-8"))
    def call(name,**args):
        value=script["_internal"]["commands"][name](lua.table_from(args,recursive=True))
        return json.loads(script["_internal"]["json"]["encode"](value))
    return lua,call

def test_native_module_free_and_one_commit(heli_game):
    lua,call=heli_game
    p=call("build_helipad",x=700,y=740,z=2,rotation=90)
    assert p["preview"] and p["check"]["ok"]
    assert "modules" not in p["parameters"]
    assert lua.globals().SUBMISSIONS is None
    r=call("commit_facility",preview_token=p["preview_token"])
    assert r["built"] and r["verified"] and r["config"]["resource"]=="::/stations/air/helipad.con"
    with pytest.raises(Exception,match="consumed"):
        call("commit_facility",preview_token=p["preview_token"])
    with pytest.raises(Exception,match="already exists"):
        call("build_helipad",x=700,y=740,z=2)
    assert lua.globals().SUBMISSIONS==1

@pytest.mark.parametrize("flag,reason",[("WATER","dry land"),("LOCKED","locked"),("BAD_SCRIPT","unrecognized")])
def test_guard_never_submits(heli_game,flag,reason):
    lua,call=heli_game
    lua.globals()[flag]=True
    with pytest.raises(Exception,match=reason):
        call("build_helipad",x=700,y=740,z=2)
    assert lua.globals().SUBMISSIONS is None

def test_recheck_collision_consumes_token(heli_game):
    lua,call=heli_game
    p=call("build_helipad",x=700,y=740,z=2)
    lua.execute("COLLISIONS={8000}")
    assert call("commit_facility",preview_token=p["preview_token"])["blocked"]
    assert lua.globals().SUBMISSIONS is None

def test_year_lock(heli_game):
    lua,call=heli_game
    lua.execute("api.engine.util.getCalendarDate=function()return {year=1949}end")
    with pytest.raises(Exception,match="unavailable"):
        call("build_helipad",x=700,y=740,z=2)

def test_player_change(heli_game):
    lua,call=heli_game
    p=call("build_helipad",x=700,y=740,z=2)
    lua.execute("api.engine.util.getPlayer=function()return 99 end")
    with pytest.raises(Exception,match="changed"):
        call("commit_facility",preview_token=p["preview_token"])
    assert lua.globals().SUBMISSIONS is None

def test_mcp_helipad_only_previews(monkeypatch):
    from tf3_mcp import server
    calls=[]
    async def fake_call(command,**args):
        calls.append((command,args));return {"preview":True}
    monkeypatch.setattr(server,"_call",fake_call)
    asyncio.run(server.build_helipad(700,740,2,90))
    command,args=calls[0]
    assert command=="build_helipad" and args["_engine"] and args["preview"]
    assert args["rotation"]==90 and "module_count" not in args
