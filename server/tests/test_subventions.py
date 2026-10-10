"""Exercise real subvention bridge code and the auto-accept policy; no live game."""
import asyncio
import json

import pytest

from test_e2e import MOCK_API, SCRIPT, lupa_mod
from tf3_mcp.subventions import SubventionAutoAccept, evaluate, expectation, make_policy


FIXTURE = r'''
local CT=api.type.ComponentType
CT.STOCK_LIST=109;CT.GAME_SCRIPT=110;CT.STATION=111;CT.INDUSTRY=112;CT.TOWN_BUILDING=113;CT.TRANSPORT_NETWORK=114
components[1][CT.GAME_TIME].gameTime=1000000
api.util={getDefaultDayDuration=function()return 4000 end,getDefaultYearDuration=function()return 1461000 end}
api.res.cargoTypeRep={find=function(n)return n=="::/cargos/fish/fish.cargo" and 6 or -1 end,
 getName=function(id)return "cargo"..id end}
local function money(a)return {type="Money",params={amount=a}} end
SUB={pause=false,
 proposedSubventions={
  {id="::/game_mechanics/subventions/deliver_cargo/deliver_cargo.res",uid=7001,spawnTime=900000,
   data={name="供应产业",toDeliver=20,delivered=0,cargosToDeliver={12},expireDurationProposed=644000,
    expireDuration=2922000,effectDuration=7305000,stockListEntity={entity=600},
    upfront={money(4000000)},failure={money(4000000),money(9000000)}}},
  {id="::/game_mechanics/subventions/deliver_workers/deliver_workers.res",uid=7002,spawnTime=950000,
   data={name="运输工人",expireDurationProposed=600000,expireDuration=3000000,effectDuration=365250,
    to={entity=600},upfront={money(8000000)},complete={money(24000000)},failure={money(8000000),money(13000000)}}}},
 activeSubventions={},completedSubventions={},
 failedSubventions={
  {id="::/game_mechanics/subventions/deliver_cargo_town/deliver_cargo_town.res",uid=6001,spawnTime=1000,acceptedTime=2000,
   data={name="供给城镇",toDeliver=32,delivered=0,cargoType="::/cargos/fish/fish.cargo",expireDuration=50000,
    townEntity={entity=100},upfront={money(7980000)},
    failure={money(7980000),{type="Reputation",params={amount=0.7,townEntity={entity=100}}}}}}}}
components[9100]={[CT.GAME_SCRIPT]={state=SUB}}
api.engine.system.gameScriptSystem={getEntityForGameScript=function(n)
 assert(n=="::/game_mechanics/subventions/subventions.gs");return 9100 end}
-- forest 500 produces cargo 12; sawmill 600 is the target
components[500]={[CT.INDUSTRY]={stockList=501,construction=502},[CT.NAME]={name="Forest"}}
components[600]={[CT.INDUSTRY]={stockList=601,construction=602},[CT.NAME]={name="Sawmill"}}
components[501]={[CT.STOCK_LIST]={}}
components[601]={[CT.STOCK_LIST]={}}
api.engine.util.stock={
 getCargoMaxProductionPerYear=function(s,c)return (s==501 and c==12) and 50 or 0 end,
 getCargoProducedPerYear=function(s,c)return (s==501 and c==12) and 20 or 0 end,
 getCargoMaxConsumptionPerYear=function()return 0 end}
components[700]={[CT.STATION_GROUP]={stations={710}}}
components[701]={[CT.STATION_GROUP]={stations={711}}}
components[710]={[CT.STATION]={terminals={{cargoLoad=true,cargoUnload=true,vehicleNodeId={entity=800,index=0}}}}}
components[711]={[CT.STATION]={terminals={{cargoLoad=true,cargoUnload=true,vehicleNodeId={entity=801,index=0}}}}}
CATCH={[710]={500},[711]={600}}
api.engine.system.catchmentAreaSystem={getStationCatchables=function(s)return CATCH[s] or {} end}
components[800]={[CT.TRANSPORT_NETWORK]={edges={{geometry={length=500}}}}}
components[801]={[CT.TRANSPORT_NETWORK]={edges={{geometry={length=500}}}}}
api.engine.util.pathfinding={findPathNodeToNode=function()return {{{entity=800,index=0}},{{entity=801,index=0}}} end}
local load={};for i=1,30 do load[i]=false end;load[13]=true
components[900]={[CT.LINE]={customFilters=true,stops={
  {stationGroup=700,station=0,terminal=0,stopConfig={load=load,maxLoad={[13]=1}}},
  {stationGroup=701,station=0,terminal=0,stopConfig={load={}}}}},
 [CT.PLAYER_OWNED]={player=2},[CT.NAME]={name="Logs"}}
components[910]={[CT.TRANSPORT_VEHICLE]={line=900,transportVehicleConfig={vehicles={{part={modelId=50}}}}}}
api.cmd.makeScriptingSendEventCmd=function(src,id,name,payload)
 assert(src=="");return {kind="event",id=id,name=name,payload=payload}
end
'''


@pytest.fixture
def game():
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute(FIXTURE)
    script = lua.execute(SCRIPT.read_text(encoding="utf8"))

    def call(name, **args):
        result = script["_internal"]["commands"][name](lua.table_from(args, recursive=True))
        return json.loads(script["_internal"]["json"]["encode"](result))
    return lua, call


def events(lua):
    sent = lua.eval("sentCommands")
    return [sent[i] for i in range(1, len(sent) + 1) if sent[i]["kind"] == "event"]


def by_uid(state):
    return {t["uid"]: t for t in state["tasks"]}


def test_get_subventions_describes_and_assesses(game):
    lua, call = game
    state = call("get_subventions")
    tasks = by_uid(state)
    assert state["activeCount"] == 0 and state["maxActive"] == 5
    logs = tasks[7001]
    assert logs["status"] == "Proposed" and logs["kind"] == "deliver_cargo"
    assert logs["upfrontMoney"] == 4000000 and logs["failureMoney"] == 13000000
    assert logs["offerDeadline"] == 1544000 and logs["remainingDays"] == 136
    assert logs["requiredPerYear"] == pytest.approx(10)
    assert logs["target"] == {"entity": 600, "name": "Sawmill", "kind": "industry", "exists": True}
    a = logs["assessment"]
    assert a["served"] and a["lines"][0]["line"] == 900 and a["lines"][0]["vehicles"] == 1
    assert a["lines"][0]["roundTripMeters"] == 2000 and a["lines"][0]["roundTripSeconds"] == 276
    assert a["supplyActualPerYear"] == 20 and a["estimatedPerYear"] == 20
    assert a["margin"] == pytest.approx(2.0)
    workers = tasks[7002]
    assert workers["completeMoney"] == 24000000
    assert workers["assessment"] == {"supported": False, "served": False, "lines": [], "reason": "unsupported_kind"}
    fish = tasks[6001]
    assert fish["status"] == "Failed" and fish["cargo"] == [6] and fish["target"]["kind"] == "town"
    assert fish["otherEffects"]["failure"] == [{"type": "Reputation", "amount": 0.7, "town": 100}]
    assert "assessment" not in fish
    assert events(lua) == []  # reading never sends commands


def test_assessment_requires_cargo_loading_at_a_producer(game):
    lua, call = game
    lua.execute("components[900][api.type.ComponentType.LINE].stops[1].stopConfig.load[13]=false")
    assert not by_uid(call("get_subventions"))[7001]["assessment"]["served"]
    lua.execute("components[900][api.type.ComponentType.LINE].stops[1].stopConfig.load[13]=true;CATCH[710]={}")
    assert not by_uid(call("get_subventions"))[7001]["assessment"]["served"]


def test_accept_sends_one_native_event_and_refuses_resend(game):
    lua, call = game
    result = call("accept_subvention", uid=7001, expect={"kind": "deliver_cargo", "toDeliver": 20, "target": 600,
                                                          "upfrontMoney": 4000000, "failureMoney": 13000000})
    assert result["submitted"] and result["callbackAccepted"]
    sent = events(lua)
    assert len(sent) == 1 and sent[0]["id"] == "Subvention" and sent[0]["name"] == "onAccept"
    assert sent[0]["payload"]["uid"] == 7001
    # native script has not processed the event yet: still proposed, marked as submitted
    assert by_uid(call("get_subventions"))[7001]["submission"]["callbackAccepted"]
    with pytest.raises(Exception, match="already submitted"):
        call("accept_subvention", uid=7001)
    assert len(events(lua)) == 1


@pytest.mark.parametrize("setup,args,message", [
    ("", {"uid": 1234}, "not proposed"),
    ("", {"uid": 7001.5}, "integer"),
    ("", {"uid": 7001, "expect": {"toDeliver": 21}}, "terms changed: toDeliver"),
    ("", {"uid": 7001, "expect": {"bogus": 1}}, "unknown expectation"),
    ("components[1][api.type.ComponentType.GAME_TIME].gameTime=1600000", {"uid": 7001}, "offer expired"),
    ("for i=1,5 do SUB.activeSubventions[i]={uid=i,data={}} end", {"uid": 7001}, "maximum active"),
])
def test_accept_rejections_send_nothing(game, setup, args, message):
    lua, call = game
    if setup:
        lua.execute(setup)
    with pytest.raises(Exception, match=message):
        call("accept_subvention", **args)
    assert events(lua) == []


def proposed(**over):
    task = {"uid": 1, "status": "Proposed", "kind": "deliver_cargo", "failureMoney": 10_000_000, "remainingDays": 100,
            "toDeliver": 20, "upfrontMoney": 4_000_000, "requiredPerYear": 10, "target": {"entity": 600},
            "assessment": {"supported": True, "served": True, "lines": [{"vehicles": 1}],
                           "estimatedPerYear": 20, "margin": 2.0}}
    task.update(over)
    return task


def test_policy_accepts_only_when_every_rule_passes():
    policy = make_policy()
    assert evaluate(proposed(), policy, 0)[0]
    assert not evaluate(proposed(failureMoney=20_000_000), policy, 0)[0]
    assert not evaluate(proposed(kind="deliver_workers"), policy, 0)[0]
    assert not evaluate(proposed(), policy, 5)[0]
    low = proposed(assessment={"supported": True, "served": True, "lines": [{"vehicles": 1}],
                               "estimatedPerYear": 12, "margin": 1.2})
    ok, reasons = evaluate(low, policy, 0)
    assert not ok and "1.20x" in reasons[0]
    idle = proposed(assessment={"supported": True, "served": True, "lines": [{"vehicles": 0}],
                                "estimatedPerYear": 0, "margin": 0})
    assert not evaluate(idle, policy, 0)[0]
    assert not evaluate(proposed(assessment={"supported": True, "served": False}), policy, 0)[0]
    assert not evaluate(proposed(remainingDays=3), make_policy(min_remaining_days=10), 0)[0]
    assert expectation(proposed()) == {"kind": "deliver_cargo", "toDeliver": 20, "upfrontMoney": 4_000_000,
                                       "failureMoney": 10_000_000, "target": 600}
    with pytest.raises(ValueError):
        make_policy(max_active=6)


class FakeGame:
    def __init__(self, tasks, fail_accept=False):
        self.tasks, self.fail_accept, self.accepts = tasks, fail_accept, []

    async def __call__(self, cmd, **args):
        if cmd == "get_subventions":
            return {"gameTime": 1, "activeCount": 0, "tasks": self.tasks}
        assert cmd == "accept_subvention"
        self.accepts.append(args)
        if self.fail_accept:
            raise RuntimeError("timed out")
        return {"submitted": True, "callbackAccepted": True}


def test_auto_accept_dry_run_logs_without_accepting(tmp_path):
    game = FakeGame([proposed(uid=1)])
    auto = SubventionAutoAccept(game, tmp_path / "log.json")
    out = asyncio.run(auto.run_once())
    assert out["decisions"][0]["decision"] == "accept" and game.accepts == []
    assert json.loads((tmp_path / "log.json").read_text(encoding="utf8"))["log"][0]["result"] == "dry_run"


def test_auto_accept_attempts_each_uid_once_and_one_per_pass(tmp_path):
    game = FakeGame([proposed(uid=1), proposed(uid=2), proposed(uid=3, kind="deliver_workers")])
    auto = SubventionAutoAccept(game, tmp_path / "log.json")
    auto.dry_run = False
    first = asyncio.run(auto.run_once())
    assert first["submitted"] == [1] and first["accepted"] == [] and game.accepts[0]["expect"]["target"] == 600
    asyncio.run(auto.run_once())  # uid 1 still shows as proposed: never resent
    assert [a["uid"] for a in game.accepts] == [1]
    game.tasks[0]['status']='Active'
    confirmed=asyncio.run(auto.run_once())
    assert confirmed['accepted']==[1]
    assert [a["uid"] for a in game.accepts] == [1, 2]
    asyncio.run(auto.run_once())
    assert [a["uid"] for a in game.accepts] == [1, 2]


def test_auto_accept_never_retries_after_an_error(tmp_path):
    game = FakeGame([proposed(uid=1)], fail_accept=True)
    auto = SubventionAutoAccept(game, None)
    auto.dry_run = False
    asyncio.run(auto.run_once())
    asyncio.run(auto.run_once())
    assert len(game.accepts) == 1
    assert auto.attempted[1]["result"] == {"error": "timed out"}


@pytest.mark.parametrize('fraction',[0, .1, .5, 1, None, -1, 2])
def test_load_fraction_limits_capacity(game,fraction):
    lua,call=game
    lua.execute('components[900][api.type.ComponentType.LINE].stops[1].stopConfig.maxLoad[13]='+('nil' if fraction is None else str(fraction)))
    task=by_uid(call('get_subventions'))[7001]
    a=task['assessment']
    if fraction is None or fraction<=0 or fraction>1:
        assert not a['served'] and not evaluate(task,make_policy(),0)[0]
    else:
        assert a['lines'][0]['capacityPerTrip']==pytest.approx(20*fraction)
        assert a['lines'][0]['capacityPerYear']==pytest.approx(20*fraction*1461/276)


def test_native_blocks_other_accept_until_confirmation(game):
    lua,call=game
    call('accept_subvention',uid=7001)
    with pytest.raises(Exception,match='requires reconciliation'):
        call('accept_subvention',uid=7002)
    assert len(events(lua))==1
    lua.execute('SUB.activeSubventions[1]=table.remove(SUB.proposedSubventions,1)')
    call('accept_subvention',uid=7002)
    assert len(events(lua))==2


@pytest.mark.parametrize('result',[{'submitted':False,'dispatchError':'failed'}, {'submitted':True,'callbackAccepted':False}])
def test_rejected_dispatch_is_not_accepted(result):
    async def run():
        sent=[]
        async def call(cmd,**args):
            if cmd=='get_subventions':return dict(activeCount=4,tasks=[proposed(uid=1),proposed(uid=2)])
            sent.append(args['uid']);return result
        auto=SubventionAutoAccept(call);auto.dry_run=False
        first=await auto.run_once()
        assert first['accepted']==[] and first['submitted']==[] and first['failed']==[1]
        assert (await auto.run_once())['pending']==[1]
        assert sent==[1]
    asyncio.run(run())


def test_pending_at_limit_and_concurrent_passes():
    async def run():
        sent=[];tasks=[proposed(uid=1),proposed(uid=2)]
        async def call(cmd,**args):
            await asyncio.sleep(0)
            if cmd=='get_subventions':return dict(activeCount=4+sum(t['status']=='Active' for t in tasks),tasks=tasks)
            sent.append(args['uid']);return dict(submitted=True,callbackAccepted=True)
        auto=SubventionAutoAccept(call);auto.dry_run=False
        await asyncio.gather(auto.run_once(),auto.run_once())
        assert sent==[1]
        tasks[0]['status']='Active'
        r=await auto.run_once()
        assert r['accepted']==[1] and sent==[1]
    asyncio.run(run())

@pytest.mark.parametrize("collection,status", [
    ("activeSubventions", "Active"),
    ("completedSubventions", "Complete"),
    ("failedSubventions", "Failed"),
])
def test_native_accept_state_survives_bridge_recreation(game, collection, status):
    """A lost local submission ledger cannot make a native accepted task proposed again."""
    lua, call = game
    call("accept_subvention", uid=7001)
    assert len(events(lua)) == 1
    lua.execute(f"local task=table.remove(SUB.proposedSubventions,1); "
                f"task.acceptedTime=1000000; table.insert(SUB.{collection},task)")
    # New bridge instance has no Lua-local submitted table from the first instance.
    restarted = lua.execute(SCRIPT.read_text(encoding="utf8"))
    commands = restarted["_internal"]["commands"]
    result = commands["get_subventions"](lua.table_from({"assess": False}))
    tasks = by_uid(json.loads(restarted["_internal"]["json"]["encode"](result)))
    assert tasks[7001]["status"] == status
    assert tasks[7001]["acceptedTime"] == 1000000
    with pytest.raises(Exception, match="not proposed"):
        commands["accept_subvention"](lua.table_from({"uid": 7001}))
    assert len(events(lua)) == 1


@pytest.mark.parametrize("invalid", ["nil", "-1", "99999", "600"])
def test_assessment_never_queries_invalid_producer_stock(game, invalid):
    lua, call = game
    lua.execute("components[500][api.type.ComponentType.INDUSTRY].stockList="+invalid)
    lua.execute("stockCalls=0;api.engine.util.stock.getCargoMaxProductionPerYear=function()stockCalls=stockCalls+1;error('invalid stock native call')end")
    assert not by_uid(call("get_subventions"))[7001]["assessment"]["served"]
    assert lua.globals().stockCalls == 0


@pytest.mark.parametrize("invalid", ["nil", "-1", "99999", "600"])
def test_assessment_never_queries_invalid_city_building_stock(game, invalid):
    lua, call = game
    lua.execute("""
      local CT=api.type.ComponentType
      SUB.proposedSubventions[1].id="::/game_mechanics/subventions/deliver_cargo_town/deliver_cargo_town.res"
      SUB.proposedSubventions[1].data.stockListEntity=nil
      SUB.proposedSubventions[1].data.townEntity={entity=100}
      components[601]={[CT.TOWN_BUILDING]={town=100}};CATCH[711]={601}
      stockCalls=0;api.engine.util.stock.getCargoMaxConsumptionPerYear=function()stockCalls=stockCalls+1;error('invalid stock native call')end
    """)
    lua.execute("components[601][api.type.ComponentType.TOWN_BUILDING].stockList="+invalid)
    assert not by_uid(call("get_subventions"))[7001]["assessment"]["served"]
    assert lua.globals().stockCalls == 0
