"""Inventory identities, deduplication and failures through the actual event transport."""
import pytest

from test_ui_extended_reads import query
from tf3_mcp.ui_log import validate_build_arguments


@pytest.fixture
def inventory_query(query):
    query.lua.execute('''
      local CT=api.type.ComponentType
      CT.WAREHOUSE=880;CT.STOCK_LIST=881
      components[900]={[CT.CONSTRUCTION]={fileName="::/warehouses/warehouse.con",stations={910,911}}}
      components[901]={[CT.WAREHOUSE]={construction=900,stockList=800}}
      components[902]={[CT.WAREHOUSE]={construction=900,stockList=800}}
      components[903]={[CT.WAREHOUSE]={construction=999,stockList=802}}
      components[800]={[CT.STOCK_LIST]={stocks={{capacity=500},{capacity=500}}}}
      components[801]={[CT.STOCK_LIST]={stocks={{capacity=100}}}}
      components[910]={[CT.STATION]={}}
      components[911]={[CT.STATION]={}}
      components[912]={[CT.STATION_GROUP]={stations={910,911,910}}}
      catches={[910]={800,800,801},[911]={800}}
      api.engine.forEachEntityWithComponent=function(fn,kind)
        assert(kind==CT.WAREHOUSE)
        for _,id in ipairs({901,902,903})do fn(id)end
      end
      api.engine.system.catchmentAreaSystem={getStationCatchables=function(id,cargo)
        assert(cargo==true);return catches[id] end}
    ''')
    return query


def test_inventory_capacity_deduplicated_across_modules_stations_and_catches(inventory_query):
    r=inventory_query('get_facility_inventory',{'entity':900})
    assert r['ok'],r
    v=r['result']
    assert v['complete'] and v['totalCapacity']==1100
    assert [x['stockList'] for x in v['inventories']]==[800,801]
    assert v['inventories'][0]['stocks']==[
        {'stockIndex':0,'capacity':500},{'stockIndex':1,'capacity':500}]
    assert [x['stockList'] for x in v['warehouses']]==[800,800]
    assert v['stations']==[{'station':910,'stockLists':[800,801]},
                           {'station':911,'stockLists':[800]}]


@pytest.mark.parametrize('entity',[910,912])
def test_station_and_group_inventory_without_warehouse_scan(inventory_query,entity):
    inventory_query.lua.execute('api.engine.forEachEntityWithComponent=function()error("must not scan")end')
    r=inventory_query('get_facility_inventory',{'entity':entity})
    assert r['ok'],r
    assert r['result']['totalCapacity']==1100
    assert r['result']['warehouses']==[]
    assert len(r['result']['stations'])==(1 if entity==910 else 2)


def test_unknown_catchable_never_becomes_zero_inventory(inventory_query):
    inventory_query.lua.execute('catches[910]={800,99999,99999};catches[911]={99999}')
    r=inventory_query('get_facility_inventory',{'entity':900})
    assert r['ok'],r
    assert not r['result']['complete']
    assert r['result']['unknownCatchables']==[99999]
    assert r['result']['totalCapacity']==1000


@pytest.mark.parametrize('setup,error',[
    ('components[800]=nil','stock list missing'),
    ('components[910]=nil','Station changed'),
    ('components[800][881].stocks[1].capacity=-1','Invalid native stock capacity'),
    ('components[800][881].stocks[1].capacity=0/0','Invalid native stock capacity'),
    ('for i=1,65 do components[800][881].stocks[i]={capacity=1}end','slot limit'),
    ('for i=1,513 do catches[910][i]=800 end','Catchment result limit'),
    ('api.engine.system.catchmentAreaSystem.getStationCatchables=function()error("native failed")end','native failed'),
])
def test_invalid_native_inventory_is_explicit_failure(inventory_query,setup,error):
    inventory_query.lua.execute(setup)
    r=inventory_query('get_facility_inventory',{'entity':900})
    assert not r['ok'] and error in r['error']


@pytest.mark.parametrize('entity',[99999,800])
def test_wrong_target_refused(inventory_query,entity):
    assert not inventory_query('get_facility_inventory',{'entity':entity})['ok']


@pytest.mark.parametrize('args',[{}, {'entity':True}, {'entity':900,'ignoreErrors':True}])
def test_strict_arguments(args):
    with pytest.raises(ValueError):validate_build_arguments('get_facility_inventory',args)
