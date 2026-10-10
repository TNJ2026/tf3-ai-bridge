"""Targeted native cargo reads through the actual GUI/event/log transport."""
import json
import pytest
from test_ui_extended_reads import query
from tf3_mcp.ui_log import validate_build_arguments


@pytest.fixture
def cargo_query(query):
    query.lua.execute('''
      calls=0;api.type.ComponentType.STOCK_LIST=83
      components[701]={[9]={line=700,state=1}}
      components[700]={[3]={stops={{stationGroup=200},{stationGroup=201}}}}
      components[800]={[83]={stocks={{capacity=500},{capacity=20}}}}
      api.engine.forEachEntity=function(f)for id in pairs(components)do f(id)end end
      api.res.cargoTypeRep={getAll=function()return {[0]='PASSENGERS',[20]='FUEL'}end}
      quality={countTotal=5,countBad=1,averageQuality=0.75,isVeryBad=false}
      local function q(id,cargo)calls=calls+1;assert(cargo==0 or cargo==20);return quality end
      api.engine.util.cargo={getCargoQualityDataForVehicle=q,getCargoQualityDataForStockList=q,
       getCargoQualityDataAtStop=function(line,stop,cargo)assert(line==700 and stop==1);return q(line,cargo)end}
      api.engine.system.simEntityAtVehicleSystem={getVehicleSimEntitiesCountForCargoType=function(id,cargo)
       calls=calls+1;assert(id==701 and (cargo==20 or cargo==0));return 5 end}
      api.engine.system.simEntityAtStockSystem={getStockCountForCargoType=function(id,slot,cargo)
       calls=calls+1;assert(id==800 and cargo==20 and (slot==0 or slot==1));return slot==0 and 3 or 2 end}
      api.engine.util.stock={getCargoTypeDeliveredPerYear=function(id,cargo)calls=calls+1;assert(id==800 and cargo==20);return 140 end,
       getCargoTypeShippedPerYear=function(id,cargo)calls=calls+1;assert(id==800 and cargo==20);return 120 end}
    ''')
    return query


@pytest.mark.parametrize('command,args',[
    ('get_vehicle_cargo',{'vehicle':701,'cargo':20}),
    ('get_vehicle_cargo',{'vehicle':701,'cargo':0}),
    ('get_stop_cargo',{'line':700,'stop_index':1,'cargo':20}),
    ('get_stock_cargo',{'stock_list':800,'cargo':20}),
])
def test_targeted_cargo_values_and_resource_ids(cargo_query,command,args):
    r=cargo_query(command,args)
    assert r['ok'],r
    v=r['result'];assert v['cargo']==args['cargo'] and v['gameTime']==123000
    assert v['quality']['countTotal']==5 and v['quality']['countBad']==1
    assert v['quality']['hasBadCargo'] and v['quality']['averageQuality']==0.75
    if command!='get_stop_cargo':assert v['count']==5 and v['countAgreement']
    if command=='get_stock_cargo':
        assert v['annualDelivered']==140 and v['annualShipped']==120
        assert v['stocks']==[{'stockIndex':0,'capacity':500,'count':3},{'stockIndex':1,'capacity':20,'count':2}]


def test_empty_quality_does_not_claim_expired_cargo(cargo_query):
    cargo_query.lua.execute('quality={countTotal=0,countBad=0,isVeryBad=true};api.engine.system.simEntityAtVehicleSystem.getVehicleSimEntitiesCountForCargoType=function()return 0 end')
    r=cargo_query('get_vehicle_cargo',{'vehicle':701,'cargo':20})['result']
    assert not r['quality']['hasCargo'] and not r['quality']['hasBadCargo']
    assert r['quality']['nativeIsVeryBad'] and r['quality'].get('averageQuality') is None
    assert r['countAgreement']


@pytest.mark.parametrize('command,args,setup',[
    ('get_vehicle_cargo',{'vehicle':9999,'cargo':20},''),
    ('get_vehicle_cargo',{'vehicle':100,'cargo':20},''),
    ('get_vehicle_cargo',{'vehicle':701,'cargo':1},''),
    ('get_stop_cargo',{'line':700,'stop_index':2,'cargo':20},''),
    ('get_stop_cargo',{'line':701,'stop_index':1,'cargo':20},''),
    ('get_stop_cargo',{'line':700,'stop_index':1,'cargo':21},''),
    ('get_stock_cargo',{'stock_list':100,'cargo':20},''),
    ('get_stock_cargo',{'stock_list':800,'cargo':21},''),
    ('get_stock_cargo',{'stock_list':800,'cargo':20},'for i=1,65 do components[800][83].stocks[i]={capacity=1}end'),
])
def test_invalid_entities_cargo_and_slots_never_reach_inventory_api(cargo_query,command,args,setup):
    cargo_query.lua.execute(setup)
    r=cargo_query(command,args)
    assert not r['ok'] and cargo_query.lua.globals().calls==0


def test_native_failure_is_not_zero_cargo(cargo_query):
    cargo_query.lua.execute('api.engine.util.cargo.getCargoQualityDataForVehicle=function()error("native read failed")end')
    r=cargo_query('get_vehicle_cargo',{'vehicle':701,'cargo':20})
    assert not r['ok'] and 'native read failed' in r['error']


def test_inconsistent_counts_are_explicit(cargo_query):
    cargo_query.lua.execute('quality.countTotal=7')
    r=cargo_query('get_vehicle_cargo',{'vehicle':701,'cargo':20})['result']
    assert not r['countAgreement'] and r['count']==5 and r['quality']['countTotal']==7


def test_optional_per_stock_quality_keeps_distinct_native_count_scopes(cargo_query):
    cargo_query.lua.execute('''
      api.engine.util.cargo.getCargoQualityDataForStock=function(id,slot,cargo)
       assert(id==800 and cargo==20 and (slot==0 or slot==1))
       return {countTotal=slot==0 and 3 or 0,countBad=0,isVeryBad=slot==1}
      end
      quality.countTotal=0
    ''')
    r=cargo_query('get_stock_cargo',{'stock_list':800,'cargo':20,'stock_quality':True})
    assert r['ok'],r
    v=r['result']
    assert v['count']==5 and not v['countAgreement']
    assert v['stocks'][0]['quality']['countTotal']==3 and v['stocks'][0]['countAgreement']
    assert v['stocks'][1]['count']==2 and not v['stocks'][1]['countAgreement']
    assert not v['stocks'][1]['quality']['hasBadCargo']


def test_per_stock_quality_native_error_is_not_ignored(cargo_query):
    cargo_query.lua.execute('api.engine.util.cargo.getCargoQualityDataForStock=function()error("stock quality read failed")end')
    r=cargo_query('get_stock_cargo',{'stock_list':800,'cargo':20,'stock_quality':True})
    assert not r['ok'] and 'stock quality read failed' in r['error']


def test_id_only_stock_snapshot_never_serializes_large_stock_records(cargo_query):
    cargo_query.lua.execute("components[800][83].stocks[1].tag=string.rep('x',100000)")
    full=cargo_query('list_map_entities',{'kind':'STOCK_LIST','limit':1})
    assert not full['ok']
    assert full['resultFailureReason']=='encoded_size_limit' and full['encodedBytes']>full['maxEncodedBytes']
    first=cargo_query('list_map_entities',{'kind':'STOCK_LIST','limit':1,'snapshot':'new','ids_only':True})
    assert first['ok'],first
    assert first['result']['items']==[{'id':800}]
    assert len(json.dumps(first))<1000
    assert cargo_query.lua.globals().calls==0


@pytest.mark.parametrize('command,args',[
    ('get_vehicle_cargo',{'vehicle':701,'cargo':True}),
    ('get_stock_cargo',{'stock_list':-1,'cargo':20}),
    ('get_stock_cargo',{'stock_list':800,'cargo':20,'stock_quality':1}),
    ('get_stop_cargo',{'line':700,'stop_index':-1,'cargo':20}),
    ('list_map_entities',{'ids_only':'true'}),
])
def test_host_rejects_invalid_cargo_read_arguments(command,args):
    with pytest.raises(ValueError):validate_build_arguments(command,args)
