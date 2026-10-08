"""Facility proposals exercise real Lua validators without touching a live save."""
import json

import pytest

from test_e2e import MOCK_API, MOCK_CONSTRUCTION, SCRIPT, lupa_mod


FIXTURE = r'''
local CT=api.type.ComponentType
local conName="::/warehouses/warehouse.con"
local records={
 construction={{name=conName,params={{key="size",values={"small","large"},numbers={},postConstructionModifiable=true}},availability={yearFrom=1900,yearTo=0}}},
 metaConstruction={},
 module={{name="::/warehouses/a.module",type="storage",availability={yearFrom=1900,yearTo=0}},
 {name="::/warehouses/b.module",type="storage",availability={yearFrom=1900,yearTo=0}},
 {name="::/warehouses/wrong.module",type="platform",availability={yearFrom=1900,yearTo=0}},
 {name="::/warehouses/future.module",type="storage",availability={yearFrom=9999,yearTo=0}}}
}
for kind,rows in pairs(records) do
 for _,d in ipairs(rows) do d.metadata={};d.updateScript={fileName="native@update",params={}} end
 api.res[kind.."Rep"]={getAll=function()local r={};for i,d in ipairs(rows)do r[i-1]=d.name end;return r end,
 find=function(name)for i,d in ipairs(rows)do if name==d.name then return i-1 end end;return -1 end,
 get=function(id)return rows[id+1]end}
end
local function nativeParams(p) return {asTable=function()return p end} end
PARAMS={seed=91,year=1968,size=1,custom={important={"preserve",4}},modules={[10]={name="::/warehouses/a.module",variant=0}}}
local V=api.type.Vec4f.new
components[8000]={[CT.PLAYER_OWNED]={player=2},[CT.CONSTRUCTION]={fileName=conName,params_native=nativeParams(PARAMS),timeBuilt=123,
 transf=api.type.Mat4f.new(V(1,0,0,0),V(0,1,0,0),V(0,0,1,0),V(300,300,2,1)),
 slots={{id=10,type="storage",replaceable=true},{id=11,type="storage",replaceable=false}},slotConfig={storage={maxModules=2}},frozenNodes={},frozenEdges={},dependentSlots={}}}
api.engine.util.getCalendarDate=function()return {year=1968}end
api.engine.util.proposal.createProposalReplaceConstruction=function(id,params)
 REPLACEMENTS=(REPLACEMENTS or 0)+1
 return {replacement=id,params=params}
end
api.engine.util.proposal.makeProposalData=function(p)
 assert(not p.replacement,"unsafe removal preview")
 PREVIEWS=(PREVIEWS or 0)+1
 return {errorState={critical=false,messages={},warnings={}},costs=100,collisionInfo={collisionEntities=COLLISIONS or {}}}
end
api.cmd.makeWorldBuildProposalCmd=function(p,ctx,ignore,initiated)
 assert(ignore==false,"must never ignore errors")
 return p
end
api.cmd.sendCommand=function(p,cb)
 SUBMISSIONS=(SUBMISSIONS or 0)+1
 if p.replacement then
  components[8000][CT.CONSTRUCTION].params_native=nativeParams(p.params)
 else
  local e=p.constructionsToAdd[1]
  components[8001]={[CT.PLAYER_OWNED]={player=2},[CT.CONSTRUCTION]={fileName=e.fileName,params_native=nativeParams(e.params),transf=e.transf,
  slots={},slotConfig={},frozenNodes={},frozenEdges={},dependentSlots={},timeBuilt=124}}
 end
 cb({},true,{})
end
'''


@pytest.fixture
def game():
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute(MOCK_CONSTRUCTION.read_text(encoding="utf8"))
    lua.execute(FIXTURE)
    script = lua.execute(SCRIPT.read_text(encoding="utf8"))
    def call(name, **kwargs):
        value = script["_internal"]["commands"][name](lua.table_from(kwargs, recursive=True))
        return json.loads(script["_internal"]["json"]["encode"](value))
    return lua, call


def test_catalog_and_lossless_config(game):
    _, call = game
    page = call("list_facility_resources", kind="module", limit=2)
    assert page["total"] == 4 and page["next_offset"] == 2
    assert len(call("list_facility_resources", kind="module", offset=2)["items"]) == 2
    c = call("get_facility_config", entity=8000)
    assert c["params"]["custom"]["important"] == ["preserve", 4]
    assert len(c["transform"]) == 4
    assert len(c["compatible_modules"]) == 3


def test_replace_preserves_params_strict_and_single_use(game):
    lua, call = game
    p = call("configure_facility", entity=8000, modules=[{"slot":10,"resource":"::/warehouses/b.module"}])
    assert p["check"]["structural_only"] and not p["check"]["collision_checked"]
    assert lua.globals().REPLACEMENTS is None and lua.globals().SUBMISSIONS is None
    r = call("commit_facility", preview_token=p["preview_token"])
    assert r["built"] and r["verified"]
    assert r["config"]["params"]["custom"]["important"] == ["preserve", 4]
    assert lua.globals().PREVIEWS is None
    with pytest.raises(Exception, match="consumed"):
        call("commit_facility", preview_token=p["preview_token"])
    assert lua.globals().SUBMISSIONS == 1


@pytest.mark.parametrize("change,error", [
    ({"slot":99,"resource":"::/warehouses/b.module"}, "unknown"),
    ({"slot":11,"resource":"::/warehouses/wrong.module"}, "type"),
    ({"slot":11,"resource":"::/warehouses/missing.module"}, "unknown"),
    ({"slot":11,"resource":"::/warehouses/future.module"}, "unavailable"),
    ({"slot":10,"remove":True}, "removal"),
    ({"slot":10,"resource":"::/warehouses/b.module","variant":2}, "variant"),
])
def test_invalid_module_never_submits(game, change, error):
    lua, call = game
    with pytest.raises(Exception, match=error):
        call("configure_facility", entity=8000, modules=[change])
    assert lua.globals().SUBMISSIONS is None


def test_stale_configuration_consumes_token(game):
    lua, call = game
    p=call("configure_facility",entity=8000,parameters={"size":2})
    lua.execute("PARAMS.seed=92")
    with pytest.raises(Exception, match="changed"):
        call("commit_facility",preview_token=p["preview_token"])
    assert lua.globals().SUBMISSIONS is None


def test_limits_and_ownership(game):
    lua, call=game
    lua.execute("components[8000][11].slotConfig.storage.maxModules=1")
    with pytest.raises(Exception,match="limit"):
        call("configure_facility",entity=8000,modules=[{"slot":11,"resource":"::/warehouses/b.module"}])
    lua.execute("components[8000][10].player=3")
    with pytest.raises(Exception,match="owned"):
        call("configure_facility",entity=8000,parameters={"size":2})


def test_unknown_parameter_and_invalid_choice(game):
    _,call=game
    for params in [{"seed":7},{"size":0},{"size":3},{"size":"2"}]:
        with pytest.raises(Exception):call("configure_facility",entity=8000,parameters=params)


def test_clone_build_and_unknown_collision(game):
    lua,call=game
    lua.execute("COLLISIONS={{entity=987654}}")
    assert call("build_facility",source_entity=8000,x=700,y=700,z=2)["blocked"]
    lua.execute("COLLISIONS={}")
    p=call("build_facility",source_entity=8000,x=700,y=700,z=2)
    r=call("commit_facility",preview_token=p["preview_token"])
    assert r["built"] and r["verified"] and r["entity"]==8001


def test_rechecks_collisions_on_commit(game):
    lua,call=game
    p=call("build_facility",source_entity=8000,x=700,y=700,z=2)
    lua.execute("COLLISIONS={{entity=987654}}")
    assert call("commit_facility",preview_token=p["preview_token"])["blocked"]
    assert lua.globals().SUBMISSIONS is None


def test_time_rollback_invalidates_preview(game):
    lua,call=game
    p=call("configure_facility",entity=8000,parameters={"size":2})
    lua.execute("components[1][4].gameTime=1")
    with pytest.raises(Exception,match="session changed"):
        call("commit_facility",preview_token=p["preview_token"])
    assert lua.globals().SUBMISSIONS is None


def test_failure_is_not_retried_or_verified(game):
    lua,call=game
    p=call("configure_facility",entity=8000,parameters={"size":2})
    lua.execute("api.cmd.sendCommand=function(p,cb) SUBMISSIONS=(SUBMISSIONS or 0)+1;cb({},false,{})end")
    r=call("commit_facility",preview_token=p["preview_token"])
    assert r["submitted"] and not r["built"] and not r["verified"]
    assert lua.globals().SUBMISSIONS==1


def test_unexpected_demolition_blocks_clone(game):
    lua,call=game
    lua.execute('''api.engine.util.proposal.makeProposalData=function()
    return {errorState={critical=false,messages={},warnings={}},collisionInfo={collisionEntities={},buildingEntities={99}}}
    end''')
    p=call("build_facility",source_entity=8000,x=700,y=700,z=2)
    assert p["blocked"] and p["check"]["unexpected_removals"]
    assert lua.globals().SUBMISSIONS is None


@pytest.mark.parametrize('asset,allowed', [
    ('::/assets/vegetation/trees/brleaf_02/brleaf_02.mdl', True),
    ('::/depots/road/depot.mdl', False),
    ('::/assets/vegetation/trees_fake/tree.mdl', False),
])
def test_auto_removal_only_allows_identified_tree_lists(game, asset, allowed):
    lua, call = game
    lua.globals().ASSET_NAME = asset
    lua.execute('''
    api.type.ComponentType.MODEL_INSTANCE_LIST='MODEL_INSTANCE_LIST'
    api.res.modelRep=api.res.modelRep or {}
    components[9000]={[api.type.ComponentType.MODEL_INSTANCE_LIST]={thinInstances={{modelId=7}},fatInstances={}}}
    api.res.modelRep.getName=function()return ASSET_NAME end
    api.engine.util.proposal.makeProposalData=function()
      return {errorState={critical=false,messages={},warnings={}},collisionInfo={collisionEntities={},autoRemovalEntity2models={[9000]={{0,0}}}}}
    end
    ''')
    p = call('build_facility', source_entity=8000, x=700, y=700, z=2)
    assert bool(p.get('preview_token')) == allowed
    assert lua.globals().SUBMISSIONS is None


def test_server_tools_route_and_cache_invalidation(monkeypatch):
    import asyncio
    from tf3_mcp import server
    from tf3_mcp.bridge import BridgeError
    calls=[]
    class FakeBridge:
        async def call(self, cmd, args, timeout, engine):
            calls.append((cmd,args,engine))
            if cmd=="commit_facility":raise BridgeError("timeout: reconcile")
            return {"preview":True}
    monkeypatch.setattr(server,"bridge",lambda:FakeBridge())
    invalidations=[]
    monkeypatch.setattr(server._map_cache,"invalidate",lambda:invalidations.append(True))
    async def run():
        await server.configure_facility(8000, modules=[{"slot":11,"resource":"x"}])
        await server.build_facility(8000,700,700,2)
        assert not invalidations
        with pytest.raises(Exception,match="reconcile"):await server.commit_facility("token")
    asyncio.run(run())
    assert all(c[2] for c in calls)
    assert len(invalidations)==1
