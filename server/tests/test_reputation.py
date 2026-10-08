"""Read-only reputation contract, native UI units, and compatibility failures."""
import json
import pytest
from test_e2e import MOCK_API, SCRIPT, lupa_mod
from test_heliports import heli_game

@pytest.fixture
def reputation():
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute(r"""
STATS={ [20]={trees=.01,rocks=.002,terrainModification=.003,demolishedTownBuilding=.004},
        [10]={trees=0,rocks=0,terrainModification=.005,demolishedTownBuilding=0} }
ug_require=function(path)
 assert(path=="::/game_mechanics/towns/town_util.tl")
 return {
 getProposalStats=function(p,pd,initiated) assert(initiated);assert(pd.valid);return {townStats=STATS} end,
 calculateProposalImpact=function(s)return s end,
 addTownAuthorityPenalties=function(f,values)assert(f.score==1);f.reasonToPenalty=values end}
end
""")
    script=lua.execute(SCRIPT.read_text(encoding="utf-8"))
    def call(proposal=None):
        r=script["_internal"]["previewReputation"](proposal or lua.table(),lua.table_from({"valid":True}))
        return json.loads(script["_internal"]["json"]["encode"](r))
    return lua,call

def test_multiple_towns_sorted_units_and_breakdown(reputation):
    _,call=reputation
    r=call()
    assert r["available"] and r["unit"]=="percentage_points"
    assert [t["town"] for t in r["towns"]]==[10,20]
    assert r["total_penalty"]==pytest.approx(2.4)
    assert r["total_delta"]==pytest.approx(-2.4)
    assert r["towns"][1]["reasons"]["DemolishedTownBuilding"]==pytest.approx(.4)
    assert not r["actual_score_change"]

def test_empty_result_is_known_zero(reputation):
    lua,call=reputation
    lua.execute("STATS={}")
    r=call();assert r["available"] and r["total_penalty"]==0

@pytest.mark.parametrize("code",[
    "ug_require=nil", "ug_require=function()error('module unavailable')end",
    "STATS[10].trees=0/0", "STATS[10].trees=math.huge",
])
def test_unknown_is_not_zero(reputation,code):
    lua,call=reputation;lua.execute(code)
    r=call();assert not r["available"] and r["reason"]
    assert "total_penalty" not in r

def test_simple_building_adapter_uses_native_result(reputation):
    lua,call=reputation
    lua.execute(r"""
api.type.Proposal={new=function()return {toAdd_native={size=function()return 1 end}}end,
 ConstructionEntity={new=function()return {construction={}}end}}
api.engine.util.construction={getConstructionResult=function(name,index,params)
 assert(name=='warehouse' and index==0 and params.seed==7)
 return {subconstructions={}}
end}
SIMPLE={constructionsToAdd={{fileName='warehouse',params={seed=7},transf={},playerEntity=2}},
 constructionsToRemove={},streetProposal={}}
local original=ug_require
ug_require=function(path)
 local u=original(path)
 u.getProposalStats=function(p,pd,initiated)
  assert(#p.toAdd==1 and p.toAdd[1].playerEntity==2 and initiated)
  return {townStats=STATS}
 end
 return u
end
""")
    # Test with a matching native preview count, without issuing any command.
    script=lua.execute(SCRIPT.read_text(encoding="utf-8"))
    pd=lua.eval("{toAddData_native={size=function()return 1 end}}")
    r=script["_internal"]["previewReputation"](lua.globals().SIMPLE,pd)
    assert r["available"]
    lua.execute("SIMPLE.streetProposal.edgesToAdd={1}")
    r=script["_internal"]["previewReputation"](lua.globals().SIMPLE,pd)
    assert not r["available"]

def test_old_preview_still_works_if_native_module_missing(heli_game):
    lua,call=heli_game
    r=call("build_heliport",x=700,y=740,z=2)
    assert r["check"]["ok"] and r["preview_token"]
    assert r["check"]["reputation"]["available"] is False
    assert lua.globals().SUBMISSIONS is None


@pytest.mark.parametrize("field", ["infos", "messages"])
def test_native_placement_constraints_block_even_without_critical(heli_game, field):
    lua, call = heli_game
    lua.execute("""
local original = api.engine.util.proposal.makeProposalData
api.engine.util.proposal.makeProposalData = function(...)
 local pd = original(...)
 pd.errorState[PLACEMENT_FIELD] = {"Place on coastline"}
 return pd
end
""")
    lua.globals().PLACEMENT_FIELD = field
    result = call("build_heliport", x=700, y=740, z=2)
    assert not result["check"]["critical"]
    assert result["check"][field] == ["Place on coastline"]
    assert result["check"]["placementBlocked"]
    assert not result["check"]["ok"]
    assert not result.get("preview_token")
    assert lua.globals().SUBMISSIONS is None
