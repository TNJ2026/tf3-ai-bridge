"""HQ permission, duplicate, collision and one-use commit guards in the real Lua bridge."""
import json

import pytest

from test_e2e import MOCK_API, MOCK_CONSTRUCTION, SCRIPT, lupa_mod
from test_facilities import FIXTURE


@pytest.fixture
def hq_game():
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute(MOCK_CONSTRUCTION.read_text(encoding="utf8"))
    lua.execute(FIXTURE)
    lua.execute('''
local oldGet=api.res.constructionRep.get
local oldFind=api.res.constructionRep.find
api.res.constructionRep.find=function(n)
 if n=="::/landmarks/hq/headquarter.con" then return 559 end
 local id=oldFind(n);return id>=0 and id or 998
end
api.res.constructionRep.get=function(id)
 if id==559 then return {metadata={},availability={yearFrom=1825,yearTo=0},
 createTemplateScript={fileName="::/landmarks/hq/headquarter.script@createTemplateFn",params={}}} end
 if id==998 then return {} end
 return oldGet(id)
end
local oldModuleFind=api.res.moduleRep.find
local oldModuleGet=api.res.moduleRep.get
api.res.moduleRep.find=function(n)
 if n=="::/landmarks/hq/modules/hq_main.module" then return 999 end
 return oldModuleFind(n)
end
api.res.moduleRep.get=function(id)
 if id==999 then return {metadata={main=true},updateScript={fileName="native@update",params={}},
 availability={yearFrom=1,yearTo=1}} end
 return oldModuleGet(id)
end
ug_require=function(n)
 if n=="::/game_mechanics/company/company_util.tl" then return {
 getConstructionDisableCacheData=function()return {}end,
 getConstructionDisableReason=function()return LOCKED and {reason="no permit"} or {numRemaining=1} end} end
 if n=="::/landmarks/hq/headquarter.script.tl" then return {
 createTemplateFn=function()return {[6432000]="::/landmarks/hq/modules/hq_main.module"}end} end
 error("unexpected native import")
end
api.engine.terrain.isValidCoordinate=function()return true end
api.engine.system.streetConnectorSystem={getConstructionClosestTown=function()return CLOSEST or 100 end}
for _,componentsForEntity in pairs(components) do
 local c=componentsForEntity[api.type.ComponentType.CONSTRUCTION]
 if c and not c.fileName then componentsForEntity[api.type.ComponentType.CONSTRUCTION]=nil end
end
''')
    script = lua.execute(SCRIPT.read_text(encoding="utf8"))
    lua.globals().HQ_INTERNAL = script["_internal"]
    commands = script["_internal"]["commands"]
    commands["get_map_info"] = lua.eval('''function()return {towns={
 {id=100,name="Zürich",position={x=700,y=700}},
 {id=101,name="Bern",position={x=3000,y=3000}}}}end''')

    def call(name, **kwargs):
        result = commands[name](lua.table_from(kwargs, recursive=True))
        return json.loads(script["_internal"]["json"]["encode"](result))

    return lua, call


def preview(call):
    return call("build_headquarters", town=100, x=700, y=740, z=2, rotation=0)


def test_native_main_template_single_submission_and_readback(hq_game):
    lua, call = hq_game
    p = preview(call)
    assert lua.globals().SUBMISSIONS is None
    assert p["resource"] == "::/landmarks/hq/headquarter.con"
    assert p["parameters"]["modules"]["6432000"]["metadata"]["main"]
    r = call("commit_facility", preview_token=p["preview_token"])
    assert r["built"] and r["verified"] and r["town"] == 100
    assert r["config"]["category"] == "headquarters"
    assert not r["config"]["cloneable"] and not r["config"]["configurable"]
    assert call("list_facilities")["total"] == 2
    with pytest.raises(Exception, match="consumed"):
        call("commit_facility", preview_token=p["preview_token"])
    with pytest.raises(Exception, match="already owns"):
        preview(call)
    assert lua.globals().SUBMISSIONS == 1


def test_permission_changes_block_commit(hq_game):
    lua, call = hq_game
    p = preview(call)
    lua.execute("LOCKED=true")
    with pytest.raises(Exception, match="locked"):
        call("commit_facility", preview_token=p["preview_token"])
    assert lua.globals().SUBMISSIONS is None


def test_remaining_permit_is_allowed_and_native_lock_blocks_preview(hq_game):
    lua, call = hq_game
    assert preview(call)["preview_token"]
    lua.execute("LOCKED=true")
    with pytest.raises(Exception, match="no permit"):
        preview(call)
    assert lua.globals().SUBMISSIONS is None


def test_collisions_block_preview_and_commit(hq_game):
    lua, call = hq_game
    lua.execute("COLLISIONS={{entity=987654}}")
    assert preview(call)["blocked"]
    lua.execute("COLLISIONS={}")
    p = preview(call)
    lua.execute("COLLISIONS={{entity=987654}}")
    assert call("commit_facility", preview_token=p["preview_token"])["blocked"]
    assert lua.globals().SUBMISSIONS is None


def test_wrong_town_and_nonfinite_site_rejected(hq_game):
    lua, call = hq_game
    for args in [dict(town=101, x=700, y=740, z=2), dict(town=100, x=float("nan"), y=740, z=2)]:
        with pytest.raises(Exception):
            call("build_headquarters", **args)
    assert lua.globals().SUBMISSIONS is None


def test_wrong_native_town_readback_is_unverified(hq_game):
    lua, call = hq_game
    p = preview(call)
    lua.execute("CLOSEST=101")
    r = call("commit_facility", preview_token=p["preview_token"])
    assert r["built"] and not r["verified"]
    assert lua.globals().SUBMISSIONS == 1


def test_world_change_invalidates_ticket(hq_game):
    lua, call = hq_game
    p = preview(call)
    lua.execute("api.engine.util.getWorld=function()return 99 end")
    with pytest.raises(Exception, match="changed"):
        call("commit_facility", preview_token=p["preview_token"])
    assert lua.globals().SUBMISSIONS is None


def test_mcp_preview_routes_to_engine_without_cache_mutation(monkeypatch):
    import asyncio
    from tf3_mcp import server
    calls = []

    async def fake_call(cmd, **args):
        calls.append((cmd, args))
        return {"preview": True}

    monkeypatch.setattr(server, "_call", fake_call)
    asyncio.run(server.build_headquarters(100, 700, 740, 2))
    cmd, args = calls[0]
    assert cmd == "build_headquarters" and args["_engine"] and args["preview"]


def test_preparation_keeps_native_parameters_without_preview_or_submission(hq_game):
    lua, call = hq_game
    lua.execute('''
PREVIEW_CALLS=0
local original=api.engine.util.proposal.makeProposalData
api.engine.util.proposal.makeProposalData=function(...)PREVIEW_CALLS=PREVIEW_CALLS+1;return original(...)end
local p,b,params=HQ_INTERNAL.prepareHeadquarters({town=100,x=700,y=740,z=2,rotation=0})
assert(type(params)=='table' and type(params.modules)=='table')
assert(p.constructionsToAdd[1].params==params)
assert(params.modules[6432000].metadata.main)
''')
    assert lua.globals().PREVIEW_CALLS == 0
    p=preview(call)
    assert 'parameters' in p and 'params' not in p
    assert lua.globals().PREVIEW_CALLS == 1
    assert lua.globals().SUBMISSIONS is None


@pytest.mark.parametrize('template', ['nil','{}','{[1]="wrong.module"}',
                                      '{[1.5]="::/landmarks/hq/modules/hq_main.module"}'])
def test_malformed_template_rejected_before_native_parameter_assignment(hq_game,template):
    lua,_=hq_game
    lua.execute('''
local original=ug_require
ug_require=function(name)
 if name=='::/landmarks/hq/headquarter.script.tl'then return {createTemplateFn=function()return '''+template+''' end}end
 return original(name)
end
api.type.SimpleProposal.ConstructionEntity.new=function()error('UNSAFE_NATIVE_SETTER_REACHED')end
''')
    with pytest.raises(Exception)as error:
        lua.execute('HQ_INTERNAL.prepareHeadquarters({town=100,x=700,y=740,z=2,rotation=0})')
    assert 'UNSAFE_NATIVE_SETTER_REACHED' not in str(error.value)
    assert lua.globals().SUBMISSIONS is None
