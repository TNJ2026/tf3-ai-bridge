from legacy_file_transport_fixture import legacy_engine_source
"""Preview/operation state must survive engine module recreation and JSON storage."""
import json
import pytest
from test_e2e import MOCK_API, MOCK_CONSTRUCTION, SCRIPT, lupa_mod
from test_facilities import FIXTURE as FACILITIES
from test_industries import FIXTURE as INDUSTRY
from test_town_cargo_needs import FIXTURE as TOWN
from test_loans import FIXTURE as LOAN

@pytest.mark.parametrize("kind,fixture,preview,args,commit,get", [
 ("industry", INDUSTRY, "preview_industry", dict(resource="::/warehouses/warehouse.con",x=700,y=700), "commit_industry", "get_industry_operation"),
 ("town", TOWN, "preview_town_cargo_needs", dict(town=100,commercial=[3]), "commit_town_cargo_needs", "get_town_cargo_operation"),
 ("loan", LOAN, "preview_loan", dict(action="borrow",offer_type="Small"), "commit_loan", "get_loan_operation"),
], ids=["industry","town","loan"])
@pytest.mark.parametrize("deferred_state", [False, True])
def test_preview_and_operation_survive_recreation(kind,fixture,preview,args,commit,get,deferred_state):
    lua=lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    if kind=="industry":
        lua.execute(MOCK_CONSTRUCTION.read_text("utf8"));lua.execute(FACILITIES)
    lua.execute(fixture)
    state=lua.execute("local v={};return {get=function()return v end,set=function(_,x)v=x end}")
    if deferred_state:
        state=lua.execute("""
        local function copy(v) if type(v)~='table' then return v end local out={} for k,x in pairs(v)do out[k]=copy(x)end return out end
        local v,pending={},nil
        return {get=function()return copy(v)end,set=function(_,x)pending=copy(x)end,flush=function()if pending then v=pending;pending=nil end end}
        """)
    counter=0
    def event(cmd, epoch="one", **kw):
        nonlocal counter
        counter+=1
        script=lua.execute(legacy_engine_source(SCRIPT.read_text("utf8")))
        script["handleEvent"](None,state,None,"tf3_mcp","tf3_mcp_request",json.dumps(dict(id=str(counter),cmd=cmd,args=kw,facilityEpoch=epoch)))
        if deferred_state: state["flush"]()
        responses=state["get"](state)["responses"];r=json.loads(responses[len(responses)]["text"])
        codec=script["_internal"]["json"];state["set"](state,codec["decode"](codec["encode"](state["get"](state))))
        if deferred_state: state["flush"]()
        return r
    stale=event(preview,epoch="old",**args)["result"]["preview_token"]
    assert not event(commit,epoch="new",preview_token=stale)["ok"]
    token=event(preview,**args)["result"]["preview_token"]
    r=event(commit,preview_token=token)
    assert r["ok"] and r["result"]["verified"],r
    assert event(get,operation_id=token)["result"]["verified"]
    assert not event(commit,preview_token=token)["ok"]
