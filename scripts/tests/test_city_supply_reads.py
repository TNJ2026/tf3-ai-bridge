"""Supply-only reads must not visit buildings; spatial reads keep targeted details."""
import ast
from pathlib import Path
import pytest
from lupa import LuaRuntime
ROOT=Path(__file__).resolve().parents[2]

def runtime():
 l=LuaRuntime(unpack_returned_tuples=True)
 l.execute("""
 B={json={encode=function(v)return v end},commands={}}
 B.toPlain=function(v)return v end
 B.commands.get_game_state=function()return {}end
 B.commands.get_map_info=function()return {towns={{id=100}},industries={}}end
 B.commands.get_town_cargo_supply=function(a)assert(a.town==100);return {items={{cargo=6,supply=4,demand=10}},scope='panel',gameTime=123}end
 api={type={ComponentType={TOWN='TOWN',TRANSPORT_VEHICLE='VEHICLE'}},res={cargoTypeRep={getAll=function()return {[6]='fish'}end,get=function()return {name='fish'}end}},engine={util={getPlayer=function()return 1 end},system={lineSystem={getProblemLines=function()return {}end}}}}
 api.engine.getComponent=function(id,k)assert(id==100 and k=='TOWN');return {cargoNeeds={}}end
 api.engine.forEachEntityWithComponent=function()error('unexpected full building scan')end
 api.engine.getEntitiesWithComponent=function(k)return k=='TOWN' and {100} or {}end
 """)
 return l

def test_supply_survey_never_reads_buildings():
 r=runtime().execute((ROOT/'scripts/current_two_supply_survey.lua').read_text('utf-8'))
 assert r['towns'][1]['demand']['6']==10
 assert r['towns'][1]['supply']['items'][1]['supply']==4

def test_observation_uses_panel_not_annual_building_scan():
 l=runtime();l.globals().FULL=True
 r=l.execute((ROOT/'scripts/fullmap_observe.lua').read_text('utf-8'))
 assert r['townSupply'][1]['supply']==4 and r['townSupply'][1]['demand']==10
 assert r['cities']['100']['annualDeliveredKnown'] is False
 assert r['cities']['100']['deliveredPerYear'] is None

@pytest.mark.parametrize('file',['bus_population_survey.lua','current_two_supply_survey.lua','fullmap_observe.lua'])
def test_lua_compile(file):
 l=LuaRuntime();l.eval('function(s) assert(load(s)) end')((ROOT/'scripts'/file).read_text('utf-8'))

@pytest.mark.parametrize('file',['read_plan_inputs.py','fullmap_city_coverage.py'])
def test_embedded_lua_compile(file):
 tree=ast.parse((ROOT/'scripts'/file).read_text('utf-8'))
 l=LuaRuntime();check=l.eval('function(s) assert(load(s)) end');count=0
 for node in ast.walk(tree):
  if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.startswith('local ') and 'return B.json.encode' in node.value:check(node.value);count+=1
 assert count>0


def test_coverage_only_reads_target_city_and_deduplicates_stock():
 tree=ast.parse((ROOT/'scripts/fullmap_city_coverage.py').read_text('utf-8'))
 code=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('local cities='))
 l=LuaRuntime();l.execute("""
 CITIES={{id=100,name='Target'}};STOPS={{town=100,stations={9}}}
 B={json={decode=function(v)return v end,encode=function(v)return v end}}
 api={type={ComponentType={STATION='STATION',TOWN_BUILDING='TOWN_BUILDING'}},res={cargoTypeRep={getAll=function()return {[6]='fish'}end}},engine={}}
 api.engine.system={townBuildingSystem={getTown2BuildingMap=function()return {[100]={1,2},[200]={999}}end},catchmentAreaSystem={getStationCatchables=function()return {55}end}}
 api.engine.getComponent=function(id,kind)
  assert(id~=999,'unrelated city read')
  if id==9 then return {}end
  return {town=100,stockList=55}
 end
 api.engine.entityExists=function()return true end
 api.engine.util={stock={getCargoMaxConsumptionPerYear=function()return 10 end}}
 """)
 r=l.execute(code)
 assert r[1]['stocks']==1 and r[1]['coveredDemand']==10 and r[1]['demand']==10
