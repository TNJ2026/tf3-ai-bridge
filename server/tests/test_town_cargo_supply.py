import asyncio
import pytest
from test_facilities import game as game
from tf3_mcp.ui_log import validate_build_arguments

SETUP = """
api.type.enum=api.type.enum or {}
api.type.enum.LandUseType={RESIDENTIAL=0,COMMERCIAL=1,INDUSTRIAL=2}
api.engine.system.townBuildingSystem={getCargoSupplyAndLimit=function(town,land)
 assert(town==100)
 if land==0 then return {} end
 if land==1 then return {[6]={3.2,10.9,0},[27]={0,0,0}} end
 return {[6]={20,5.8,0},[20]={1,8,0}}
end}
components[100]={[api.type.ComponentType.TOWN]={}}
"""

def test_native_panel_rounding_and_cargo_dedup(game):
 lua,call=game;lua.execute(SETUP)
 r=call('get_town_cargo_supply',town=100)
 assert r['readOnly'] and not r['periodKnown']
 assert r['districts']['commercial'][0]['supply']==4
 assert r['districts']['commercial'][0]['demand']==10
 assert r['items'][0]=={'cargo':6,'supply':9,'demand':15,'rateKnown':True,'supplyRate':.6}
 assert r['items'][2]['rateKnown'] is False and 'supplyRate' not in r['items'][2]
 assert lua.globals().SUBMISSIONS is None

@pytest.mark.parametrize('value',['nil','{[6]={0/0,10}}','{[6]={1,-1}}'])
def test_missing_and_invalid_are_not_zero(game,value):
 lua,call=game;lua.execute(SETUP)
 lua.execute('api.engine.system.townBuildingSystem.getCargoSupplyAndLimit=function()return '+value+' end')
 with pytest.raises(Exception):call('get_town_cargo_supply',town=100)

@pytest.mark.parametrize('args',[{}, {'town':True},{'town':-1},{'town':100,'extra':1}])
def test_validation(args):
 with pytest.raises(ValueError):validate_build_arguments('get_town_cargo_supply',args)

@pytest.mark.parametrize('args',[{'town':100},{'town':100,'include_passengers':False},{'town':100,'include_passengers':True}])
def test_optional_passenger_flag_host_validation(args):
 assert validate_build_arguments('get_town_cargo_supply',args)==args

def test_old_receiver_rejected_before_send():
 from unittest.mock import AsyncMock,Mock
 from tf3_mcp.no_gui_client import NoGuiClient
 c=NoGuiClient(Mock());c.status=AsyncMock(return_value={'receiver':{'session':'s'},'pending':None})
 with pytest.raises(ValueError,match='lacks town cargo supply'):asyncio.run(c.call('get_town_cargo_supply',{'town':100}))
 c.requests.send.assert_not_called()

def test_public_tool(monkeypatch):
 from tf3_mcp import server
 from unittest.mock import AsyncMock
 f=AsyncMock(return_value={'readOnly':True});monkeypatch.setattr(server,'_call',f)
 assert asyncio.run(server.get_town_cargo_supply(100))['readOnly']
 f.assert_awaited_once_with('get_town_cargo_supply',_engine=True,town=100)


def test_native_callable_table_binding(game):
 lua,call=game;lua.execute(SETUP)
 lua.execute("local f=api.engine.system.townBuildingSystem.getCargoSupplyAndLimit; api.engine.system.townBuildingSystem.getCargoSupplyAndLimit=setmetatable({}, {__call=function(_,...)return f(...)end,__metatable='protected'})")
 r=call('get_town_cargo_supply',town=100)
 assert r['townCargoSupplyVersion']==2 and r['items'][0]['supplyRate']==.6
 assert lua.globals().SUBMISSIONS is None


PASSENGERS = """
api.engine.system.townBuildingSystem.getLandUsePersonCapacities=function()return {101,800,900}end
api.engine.util.town={getTownLineUsage=function()return .123 end}
"""

@pytest.mark.parametrize('usage,supply',[(0,0),(.123,25),(.25,51),(.9,101)])
def test_passenger_panel_rounding_clamping_and_scope(game,usage,supply):
 lua,call=game;lua.execute(SETUP+PASSENGERS)
 lua.execute('api.engine.util.town.getTownLineUsage=function()return '+str(usage)+' end')
 r=call('get_town_cargo_supply',town=100,include_passengers=True)
 p=r['passengers']
 assert p['demand']==101 and p['supply']==supply
 assert p['rawLineUsage']==usage and p['supplyRate']==pytest.approx(supply/101)
 assert p['panelRowPresent'] and not p['periodKnown']
 assert 'not bus-only' in p['scope']
 assert r['items'][0]['supply']==9  # Cargo totals stay separate.
 assert lua.globals().SUBMISSIONS is None

def test_zero_passenger_demand_has_no_panel_row_or_ratio(game):
 lua,call=game;lua.execute(SETUP+PASSENGERS)
 lua.execute('api.engine.system.townBuildingSystem.getLandUsePersonCapacities=function()return {0}end; api.engine.util.town=nil')
 p=call('get_town_cargo_supply',town=100,include_passengers=True)['passengers']
 assert not p['panelRowPresent'] and not p['rateKnown']
 assert 'supply' not in p and 'supplyRate' not in p

@pytest.mark.parametrize('code',[
 'api.engine.system.townBuildingSystem.getLandUsePersonCapacities=nil',
 'api.engine.system.townBuildingSystem.getLandUsePersonCapacities=function()return {}end',
 'api.engine.util.town.getTownLineUsage=function()return 0/0 end',
 'api.engine.util.town.getTownLineUsage=function()return -1 end',
])
def test_passenger_unknown_rejected(game,code):
 lua,call=game;lua.execute(SETUP+PASSENGERS+code)
 with pytest.raises(Exception):call('get_town_cargo_supply',town=100,include_passengers=True)

def test_passenger_capability_rejected_before_dispatch():
 from unittest.mock import AsyncMock,Mock
 from tf3_mcp.no_gui_client import NoGuiClient
 c=NoGuiClient(Mock())
 c.status=AsyncMock(return_value={'receiver':{'session':'s','townCargoSupplyVersion':2},'pending':None})
 with pytest.raises(ValueError,match='lacks town passenger supply'):
  asyncio.run(c.call('get_town_cargo_supply',{'town':100,'include_passengers':True}))
 c.requests.send.assert_not_called()

def test_public_passenger_tool(monkeypatch):
 from tf3_mcp import server
 from unittest.mock import AsyncMock
 f=AsyncMock(return_value={'readOnly':True});monkeypatch.setattr(server,'_call',f)
 asyncio.run(server.get_town_cargo_supply(100,include_passengers=True))
 f.assert_awaited_once_with('get_town_cargo_supply',_engine=True,town=100,include_passengers=True)
