import asyncio
import pytest
from test_facilities import game as facility_game
from tf3_mcp.ui_log import validate_build_arguments

@pytest.fixture
def bonus_game(facility_game):
 lua,call=facility_game
 lua.execute('''
local ct=api.type.ComponentType
for _,name in ipairs({'GAME_SCRIPT','INDUSTRY','PERSON_CAPACITY','STOCK_LIST','STATION'})do ct[name]=ct[name] or name end
components[5000]={[ct.INDUSTRY]={stockList=5000,construction=8000},
 [ct.PERSON_CAPACITY]={capacity=20},[ct.STOCK_LIST]={modifiers={productivity=1},
 stocks={{cargoType=3,capacity=100},{cargoType=9,capacity=200}},
 rules={{booster=false,input={{0}},output={[9]=5}},
 {booster=true,input={{17,0}},boostFactor=.52,capacity=4,consumptionFactor=1}},ruleDatas={}}}
components[8000][ct.CONSTRUCTION].stations={5001}
components[8000][ct.CONSTRUCTION].persistentMetadata={workersBoostFactor=1.9}
components[5001]={[ct.STATION]={terminals={{tag=7,passengersLoad=true,passengersUnload=true,cargoLoad=true,cargoUnload=true,transportModes={[12]=true}}}}}
WORKER_STATE={lastVisitors={},pendingVisitors={}}
components[5002]={[ct.GAME_SCRIPT]={state_native={findPath=function(_,path)
 assert(path[1]=='industriesState' and path[2]==5000)
 if NO_ENTRY then return nil end
 return {asTable=function()return WORKER_STATE end}
end}}}
api.engine.system.gameScriptSystem={getEntityForGameScript=function(name)
 assert(name=='::/industries/industry_workers.gs');return NO_SCRIPT and -1 or 5002 end}
api.res.cargoTypeRep={getName=function(id)return id==3 and '::/cargos/fertilizer/fertilizer.cargo' or 'vegetables'end,
 get=function(id)return {name=id==3 and '肥料' or '蔬菜'}end}
ug_require=function(name)
 assert(name=='::/industries/industry_productivity_util.tl')
 return {RequiredWorkersFractionForBoost=.5,workersTimeIntervalMax=200,
 getPersonCapacityPotentialBoost=function()error('must not mutate RNG')end}
end
math.randomseed=function()error('query must not seed RNG')end
math.random=function()error('query must not consume RNG')end
''')
 return lua,call

def test_maps_input_stock_not_cargo_id_and_native_transfer(bonus_game):
 lua,call=bonus_game;r=call('get_industry_bonuses',industry=5000)
 w=r['workers'];assert w['capacity']==20 and w['requiredVisitors']==10
 assert w['recordedVisitors']==0 and not w['active'] and not w['thresholdMet']
 assert w['potentialMultiplier']==1.9
 c=r['cargoBonuses'][0];i=c['inputAlternatives'][0]['items'][0]
 assert (i['cargo'],i['name'],i['quantity'],i['stockCapacity'])==(3,'肥料',17,100)
 assert not c['activeKnown'] and c['deliveryTarget']==5000
 assert r['transfer']['stations'][0]['station']==5001 and r['readOnly']
 assert lua.globals().SUBMISSIONS is None

def test_unknown_state_is_not_zero_and_rng_fallback_not_called(bonus_game):
 lua,call=bonus_game;lua.execute('NO_SCRIPT=true;components[8000][api.type.ComponentType.CONSTRUCTION].persistentMetadata={}')
 w=call('get_industry_bonuses',industry=5000)['workers']
 assert not w['observationAvailable'] and 'recordedVisitors' not in w
 assert not w['potentialMultiplierAvailable'] and 'potentialMultiplier' not in w

def test_known_empty_and_pending_not_counted(bonus_game):
 lua,call=bonus_game;lua.execute('NO_ENTRY=true')
 assert call('get_industry_bonuses',industry=5000)['workers']['recordedVisitors']==0
 lua.execute('NO_ENTRY=false;WORKER_STATE.pendingVisitors={{time=0}}')
 w=call('get_industry_bonuses',industry=5000)['workers'];assert w['pendingVisitors']==1 and not w['thresholdMet']

def test_recorded_threshold_separate_from_applied_multiplier_and_expiry(bonus_game):
 lua,call=bonus_game;lua.execute('for i=1,10 do WORKER_STATE.lastVisitors[i]={time=-1000000000} end')
 w=call('get_industry_bonuses',industry=5000)['workers']
 assert w['thresholdMet'] and not w['active'] and w['inWindowVisitors']==0

def test_actual_multiplier_fallback_and_unresolved_station(bonus_game):
 lua,call=bonus_game;lua.execute('''components[8000][api.type.ComponentType.CONSTRUCTION].persistentMetadata={}
components[8000][api.type.ComponentType.CONSTRUCTION].stations={}
components[5000][api.type.ComponentType.STOCK_LIST].modifiers.productivity=2.1''')
 r=call('get_industry_bonuses',industry=5000);assert r['workers']['active'] and r['workers']['potentialMultiplier']==2.1
 assert not r['transfer']['stationResolved']

def test_wrong_entity_and_invalid_mapping_fail_explicitly(bonus_game):
 lua,call=bonus_game
 with pytest.raises(Exception,match='not an industry'):call('get_industry_bonuses',industry=8000)
 lua.execute('components[5000][api.type.ComponentType.STOCK_LIST].rules[2].input={{0,0,8}}')
 with pytest.raises(Exception,match='stock index unavailable'):call('get_industry_bonuses',industry=5000)
 assert lua.globals().SUBMISSIONS is None

@pytest.mark.parametrize('args',[{}, {'industry':True},{'industry':-1},{'industry':5,'extra':1}])
def test_argument_validation(args):
 with pytest.raises(ValueError):validate_build_arguments('get_industry_bonuses',args)

def test_old_receiver_never_publishes():
 from unittest.mock import AsyncMock,Mock
 from tf3_mcp.no_gui_client import NoGuiClient
 c=NoGuiClient(Mock());c.status=AsyncMock(return_value={'receiver':{'session':'s'},'pending':None})
 with pytest.raises(ValueError,match='lacks industry bonuses'):asyncio.run(c.call('get_industry_bonuses',{'industry':5}))
 c.requests.send.assert_not_called()

def test_public_tool_routes_to_engine(monkeypatch):
 from tf3_mcp import server
 from unittest.mock import AsyncMock
 f=AsyncMock(return_value={'readOnly':True});monkeypatch.setattr(server,'_call',f)
 assert asyncio.run(server.get_industry_bonuses(5000))['readOnly']
 f.assert_awaited_once_with('get_industry_bonuses',_engine=True,industry=5000)


def test_native_userdata_node_id_is_structured(bonus_game):
 lua,call=bonus_game
 class Node:
  entity=410
  index=7
 lua.globals().NODE=Node()
 lua.execute('components[5001][api.type.ComponentType.STATION].terminals[1].vehicleNodeId=NODE')
 node=call('get_industry_bonuses',industry=5000)['transfer']['stations'][0]['terminals'][0]['vehicleNodeId']
 assert node=={'entity':410,'index':7}
