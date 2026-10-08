import sys,copy
from pathlib import Path
import pytest
from lupa.lua52 import LuaRuntime,LuaError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from primary_warehouse import prelude,inventory_totals,selection
from fullmap_hub_audit import requests

SETUP='''
local CT={CONSTRUCTION=1,WAREHOUSE=2,STOCK_LIST=3}
constructs={[10]={},[20]={stations={201}},[30]={stations={301}},[40]={stations={401}}}
warehouses={[11]={construction=10,stockList=100},[12]={construction=10,stockList=100}}
lists={[100]={stocks={{capacity=500},{capacity=500}}}}
catch={[201]={11},[301]={100},[401]={12}}
calls=0;scans=0;stockReads=0
api={type={ComponentType=CT},engine={
 entityExists=function(id)return lists[id]~=nil end,
 getComponent=function(id,ct)if ct==1 then return constructs[id]elseif ct==2 then return warehouses[id]else stockReads=stockReads+1;return lists[id]end end,
 forEachEntityWithComponent=function(fn,ct)assert(ct==2);scans=scans+1;for id in pairs(warehouses)do fn(id)end end,
 system={simEntityAtStockSystem={getStockCount=function(sid,slot)assert(sid==100 and slot>=0 and slot<2);return 25 end},catchmentAreaSystem={getStationCatchables=function(st,cargo)assert(cargo);calls=calls+1;return catch[st]end}}
}}
'''

def run(extra='',tail='return primaryWarehouse(10,{harbor=20,pad1=30,pad2=40})'):
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.execute(SETUP+extra)
    return lua,lua.execute(prelude()+tail)

def test_aliases_canonicalized_and_capacity_not_counted_per_alias_or_station():
    lua,r=run()
    assert r['verified'] and r['primaryStockList']==100 and r['capacity']==1000
    assert r['quantity']==50
    assert list(r['commonWarehouseStockIds'].values())==[100]
    assert lua.globals().calls==3 and lua.globals().scans==1
    assert not r['operationalAccepted']

@pytest.mark.parametrize('bad',['{}','{10}','{999}'])
def test_empty_or_construction_only_or_unrelated_coverage_rejected(bad):
    _,r=run('catch[401]='+bad)
    assert not r['verified'] and len(r['commonWarehouseStockIds'])==0

def test_multiple_inventories_require_selection_not_independent_any_stock():
    setup='warehouses[13]={construction=10,stockList=101};lists[101]={stocks={{capacity=200}}};catch[401]={13}'
    with pytest.raises(LuaError,match='Multiple inventories'):run(setup)
    _,r=run(setup,'return primaryWarehouse(10,{harbor=20,pad1=30,pad2=40},100)')
    assert not r['verified'] and r['capacity']==1000

def test_invalid_or_missing_stock_stops_before_catchment_query():
    lua=LuaRuntime();lua.execute(SETUP+'lists[100]=nil')
    with pytest.raises(LuaError,match='Invalid warehouse stock'):
        lua.execute(prelude()+'return primaryWarehouse(10,{pad=30})')
    assert lua.globals().calls==0

def test_no_roles_or_no_station_cannot_pass():
    with pytest.raises(LuaError,match='No cargo station'):run(tail='return primaryWarehouse(10,{})')
    _,r=run('constructs[40].stations={}')
    assert not r['verified']

def test_shared_station_is_read_once_and_multiple_hubs_share_warehouse_scan():
    lua,r=run(tail='local a=primaryWarehouse(10,{one=20,two=20});local b=primaryWarehouse(10,{pad=30});return a')
    assert r['verified'] and lua.globals().calls==2 and lua.globals().scans==1

def test_capacity_deduplicated_across_reused_hubs_and_inconsistent_reads_stop():
    a={'inventoryById':{'100':{'stockList':100,'capacity':1000,'quantity':50}}}
    assert inventory_totals([a,copy.deepcopy(a)])=={'inventoryIds':[100],'capacity':1000,'quantity':50}
    b=copy.deepcopy(a);b['inventoryById']['100']['capacity']=2000
    with pytest.raises(ValueError,match='changed between reads'):inventory_totals([a,b])

def test_current_land_and_fishing_roles_without_passenger_or_maintenance():
    p={'hubs':[{'owner':'town','facilities':dict(warehouse='W',truck='T',heliport='H',bus='B',road_maintenance='M')}],
       'ports':[dict(id='P',warehouse='FW',helipad='F1',helipad2='F2')]}
    r=requests(p)
    assert r[0]['targets']=={'truck':'T','heliport':'H'}
    assert r[1]['targets']=={'harbor':'P','helipad':'F1','helipad2':'F2'}

@pytest.mark.parametrize('value',[True,-1,1.5,'1; dangerous()'])
def test_primary_selection_is_not_lua_source(value):
    with pytest.raises(ValueError):selection(value)
