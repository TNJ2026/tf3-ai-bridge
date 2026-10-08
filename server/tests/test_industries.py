"""Sandbox industry placement against the real Lua bridge; never a live save."""
import json
import pytest
from test_e2e import MOCK_API, MOCK_CONSTRUCTION, SCRIPT, lupa_mod
from test_facilities import FIXTURE as FACILITIES

FIXTURE = r'''
SANDBOX=true
api.res.getBaseConfig=function()return {sandboxMode=SANDBOX}end
local rep=api.res.constructionRep
local original=rep.get
rep.get=function(id)local d=original(id);if d then d.isIndustry=true end;return d end
api.type.ComponentType.INDUSTRY=99
api.type.Map={Industry={new=function()return {}end}}
api.type.Context={new=function()return {}end}
local nativePreview=api.engine.util.proposal.makeProposalData
api.engine.util.proposal.makeProposalData=function(p)
 assert(p.constructionsToAdd,"SimpleProposal expected, got Proposal")
 assert(p.constructionsToAdd[1].params.seed==123,"preserve native industry parameters")
 return nativePreview(p)
end
api.type.Mat4f.new=function(a,b,c,d)
 local values={a,b,c,d}
 return {cols=function(self,i)return values[i+1]end}
end
api.engine.terrain.isValidCoordinate=function(p)return math.abs(p.x)<10000 and math.abs(p.y)<10000 end
MAP={industries={{existing=9000,fileName="old",pos={x=1,y=2}}},towns={{existing=100,pos={x=10,y=20}}}}
api.engine.terrain.makeMapFromGame=function()return MAP end
api.engine.mapgen={createIndustries=function(seed,items)
 assert(items[1].existing==9000,"existing industries must be preserved")
 local v=items[#items];local V=api.type.Vec4f.new
 local tr=api.type.Mat4f.new(V(1,0,0,0),V(0,1,0,0),V(0,0,1,0),V(v.pos.x+(SHIFT or 0),v.pos.y,5,1))
 return {toRemove=REMOVALS or {},toAdd={{fileName=v.fileName,transf=tr,bbox={},streetPoint={},onWater=v.onWater}}}
end}
api.engine.util.proposal.createIndustryProposal=function(seed,info,context)
 return {toRemove={},old2new={},proposal={removedSegments=ROAD_REMOVALS or {}},toAdd={{fileName=info.fileName,transf=info.transf,construction={params={seed=123}},playerEntity=2}}}
end
api.cmd.sendCommand=function(p,cb)
 SUBMISSIONS=(SUBMISSIONS or 0)+1
 COMPLETE=function()
  local e=p.constructionsToAdd[1]
  components[8100]={[11]={fileName=e.fileName,transf=e.transf,industries={8101}}}
  if not NO_INDUSTRY then components[8101]={[99]={construction=8100}} end
  cb({},true)
 end
 if not DELAY then COMPLETE() end
end
'''

@pytest.fixture
def game():
    lua=lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute(MOCK_CONSTRUCTION.read_text(encoding="utf-8"))
    lua.execute(FACILITIES)
    lua.execute(FIXTURE)
    script=lua.execute(SCRIPT.read_text(encoding="utf-8"))
    def call(name, **args):
        value=script["_internal"]["commands"][name](lua.table_from(args,recursive=True))
        return json.loads(script["_internal"]["json"]["encode"](value))
    return lua,call

def preview(call, **extra):
    return call("preview_industry",resource="::/warehouses/warehouse.con",x=700,y=700,**extra)

def test_catalog_preview_commit_single_use(game):
    lua,call=game
    assert call("list_industry_resources")["sandbox"]
    p=preview(call)
    assert lua.globals().SUBMISSIONS is None
    r=call("commit_industry",preview_token=p["preview_token"])
    assert r["verified"] and r["entities"][0]["industries"]==[8101]
    with pytest.raises(Exception,match="consumed"):
        call("commit_industry",preview_token=p["preview_token"])
    assert lua.globals().SUBMISSIONS==1

@pytest.mark.parametrize("change,error",[
    ("SANDBOX=false","sandbox"),
    ("REMOVALS={9000}","removals"),
    ("ROAD_REMOVALS={12}","roads"),
])
def test_fail_closed(game,change,error):
    lua,call=game
    lua.execute(change)
    with pytest.raises(Exception,match=error):preview(call)
    assert lua.globals().SUBMISSIONS is None

@pytest.mark.parametrize("change,error",[
    ("SANDBOX=false","sandbox"),
    ("components[1][4].gameTime=1","session"),
    ("MAP.towns[1].pos.x=999","session"),
    ("SHIFT=10","layout"),
])
def test_recheck_commit(game,change,error):
    lua,call=game
    p=preview(call)
    lua.execute(change)
    with pytest.raises(Exception,match=error):call("commit_industry",preview_token=p["preview_token"])
    assert lua.globals().SUBMISSIONS is None

def test_collision_recheck(game):
    lua,call=game
    p=preview(call)
    lua.execute("COLLISIONS={{entity=987654}}")
    assert call("commit_industry",preview_token=p["preview_token"])["blocked"]
    assert lua.globals().SUBMISSIONS is None

def test_pending_and_independent_readback(game):
    lua,call=game
    lua.execute("DELAY=true")
    p=preview(call)
    r=call("commit_industry",preview_token=p["preview_token"])
    assert not r["verified"] and r["do_not_resubmit"]
    lua.execute("COMPLETE()")
    assert call("get_industry_operation",operation_id=r["operation_id"])["verified"]
    lua.execute("MAP.industries={}")
    assert call("get_industry_operation",operation_id=r["operation_id"])["status"]=="session_changed"
    assert lua.globals().SUBMISSIONS==1

def test_construction_only_not_verified(game):
    lua,call=game
    lua.execute("NO_INDUSTRY=true")
    p=preview(call)
    assert not call("commit_industry",preview_token=p["preview_token"])["verified"]
    assert call("get_industry_operation",operation_id="missing")["do_not_resubmit"]

@pytest.mark.parametrize("extra",[{"rotation":float("nan")},{"on_water":"yes"},{"seed":""}])
def test_bad_arguments(game,extra):
    lua,call=game
    with pytest.raises(Exception):preview(call,**extra)
    assert lua.globals().SUBMISSIONS is None

def test_mcp_routes(monkeypatch):
    import asyncio
    from tf3_mcp import server
    seen=[]
    async def fake(cmd,**args):
        seen.append((cmd,args))
        return {}
    monkeypatch.setattr(server,"_call",fake)
    async def run():
        await server.list_industry_resources()
        await server.preview_industry("industry.con",100,200)
        await server.commit_industry("token")
        await server.get_industry_operation("token")
    asyncio.run(run())
    assert [r[0] for r in seen]==["list_industry_resources","preview_industry","commit_industry","get_industry_operation"]
    assert all(r[1]["_engine"] for r in seen)

def test_expired_and_reloaded_token(game):
    lua,call=game
    p=preview(call)
    lua.execute("local original=os.clock;os.clock=function()return original()+61 end")
    with pytest.raises(Exception,match="expired"):
        call("commit_industry",preview_token=p["preview_token"])
    fresh=lua.execute(SCRIPT.read_text(encoding="utf-8"))
    with pytest.raises(Exception,match="reloaded"):
        fresh["_internal"]["commands"]["commit_industry"](lua.table_from({"preview_token":p["preview_token"]}))
    assert lua.globals().SUBMISSIONS is None
