"""Identity readbacks must distinguish alighting evidence from disappearing IDs."""
import pytest
from test_ui_extended_reads import query
from test_ui_cargo_reads import cargo_query
from tf3_mcp.ui_log import validate_build_arguments


@pytest.fixture
def identity_query(cargo_query):
    cargo_query.lua.execute('''
      mapCalls=0
      onboard={[701]={[0]={[0]=905,[1]=903,[2]=904,[3]=902,[4]=901},[20]={999}}}
      api.engine.system.simEntityAtVehicleSystem.getVehicle2Cargo2SimEntitesMap=function()
       mapCalls=mapCalls+1;return onboard
      end
      for i,name in ipairs({'SIM_PERSON','SIM_CARGO','SIM_ENTITY_AT_VEHICLE',
       'SIM_PERSON_AT_VEHICLE','SIM_ENTITY_AT_TERMINAL','SIM_ENTITY_MOVING',
       'SIM_ENTITY_AT_BUILDING'}) do api.type.ComponentType[name]=1900+i end
      components[901]={[1901]={cargoType=0,targetOrAtEntity=400,destinations={400,401,402},pickupTime=120000},
       [1903]={vehicle=701,line=700,lineStop0=0,lineStop1=1,roundTripCounter=0},
       [1904]={vehicle=701,part=0,place=3,expectedArrivalTime=125000}}
      for id=902,905 do components[id]={[1901]={cargoType=0},[1903]={vehicle=701},[1904]={vehicle=701}} end
    ''')
    return cargo_query


def test_default_count_read_does_not_enumerate_identity_map(identity_query):
    r=identity_query('get_vehicle_cargo',{'vehicle':701,'cargo':0})
    assert r['ok'] and 'entities' not in r['result']
    assert identity_query.lua.globals().mapCalls==0


@pytest.fixture
def cargo_identity_query(identity_query):
    identity_query.lua.execute('''
      onboard={}
      for id=1001,1005 do components[id]={[1902]={cargoType=20,pickupTime=100},[1903]={vehicle=701,line=700}} end
      components[1006]={[1902]={cargoType=20},[1903]={vehicle=999}}
      components[1007]={[1902]={cargoType=19},[1903]={vehicle=701}}
      components[1008]={[1902]={cargoType=20,pickupPoints={{vehicle=701}}}}
    ''')
    return identity_query


def test_empty_aggregate_map_resolves_cargo_by_type_and_current_vehicle(cargo_identity_query):
    identity_query=cargo_identity_query
    r=identity_query('get_vehicle_cargo',{'vehicle':701,'cargo':20,'include_entities':True,'limit':2})
    assert r['ok'],r
    e=r['result']['entities']
    assert e['ids']==[1001,1002] and e['total']==5 and e['hasMore'] and e['countAgreement']
    assert e['source']=='sim_cargo_vehicle_components' and e['scannedCargo']==8 and e['scannedPersons']==0
    r=identity_query('get_vehicle_cargo',{'vehicle':701,'cargo':20,'include_entities':True,'offset':4,'limit':2})
    assert r['result']['entities']['ids']==[1005] and not r['result']['entities']['hasMore']
    assert identity_query.lua.globals().mapCalls==0


def test_empty_component_scan_is_explicit_count_mismatch(identity_query):
    e=identity_query('get_vehicle_cargo',{'vehicle':701,'cargo':20,'include_entities':True})['result']['entities']
    assert e['ids']==[] and e['total']==0 and not e['countAgreement']


@pytest.mark.parametrize('setup,expected',[
    ('api.engine.forEachEntity=function(f)f(1001);f(1001)end','Duplicate onboard'),
    ('components[-1]=components[1001];api.engine.forEachEntity=function(f)f(-1)end','Invalid onboard'),
    ('for i=2000,12000 do components[i]={[1902]={cargoType=20},[1903]={vehicle=701}}end','exceeds read bound'),
    ('local old=api.engine.getComponent;api.engine.getComponent=function(id,ct)if ct==1903 then error("native vehicle failure")end;return old(id,ct)end','native vehicle failure'),
    ('components[1001][1902].cargoType=nil','Invalid scanned cargo type'),
    ('api.type.ComponentType.SIM_CARGO=nil','Cargo component types unavailable'),
    ('api.engine.forEachEntity=function(f)for i=1,100001 do f(1008)end end','scan exceeds'),
    ('api.engine.forEachEntity=function(f)for i=1,1000001 do f(999999)end end','entity scan exceeds'),
])
def test_bad_native_identity_data_is_never_a_successful_empty_list(cargo_identity_query,setup,expected):
    identity_query=cargo_identity_query
    identity_query.lua.execute(setup)
    r=identity_query('get_vehicle_cargo',{'vehicle':701,'cargo':20,'include_entities':True})
    assert not r['ok'] and expected in r['error']


def test_cargo_current_membership_and_empty_vehicle(cargo_identity_query):
    cargo_identity_query.lua.execute('for id=1001,1005 do components[id][1903]=nil end;quality.countTotal=0;quality.countBad=0;api.engine.system.simEntityAtVehicleSystem.getVehicleSimEntitiesCountForCargoType=function()return 0 end')
    r=cargo_identity_query('get_vehicle_cargo',{'vehicle':701,'cargo':20,'include_entities':True})['result']
    assert r['entities']['ids']==[] and r['entities']['countAgreement'] and r['countAgreement']


def test_default_cargo_count_never_scans_entities(cargo_identity_query):
    cargo_identity_query.lua.execute('api.engine.forEachEntity=function()error("unexpected scan")end;api.engine.forEachEntityWithComponent=function()error("unexpected scan")end')
    r=cargo_identity_query('get_vehicle_cargo',{'vehicle':701,'cargo':20})
    assert r['ok'] and 'entities' not in r['result']


def test_same_person_onboard_then_walking_then_at_building(identity_query):
    a=identity_query('get_sim_entity',{'id':901})
    assert a['ok'],a
    c=a['result']['components']
    assert c['SIM_ENTITY_AT_VEHICLE']['vehicle']==701 and c['SIM_PERSON_AT_VEHICLE']['place']==3
    identity_query.lua.execute('components[901][1903]=nil;components[901][1904]=nil;components[901][1906]={line=700,lineStop0=0,lineStop1=1,partialPath=false,expectedArrivalTime=126000}')
    b=identity_query('get_sim_entity',{'id':901})['result']
    assert b['exists'] and 'SIM_ENTITY_AT_VEHICLE' not in b['components']
    assert b['components']['SIM_ENTITY_MOVING']['lineStop1']==1
    identity_query.lua.execute('components[901][1906]=nil;components[901][1907]={waitingTime=10}')
    c=identity_query('get_sim_entity',{'id':901})['result']['components']
    assert c['SIM_ENTITY_AT_BUILDING']['waitingTime']==10 and c['SIM_PERSON']['targetOrAtEntity']==400


def test_deleted_person_is_missing_not_delivered(identity_query):
    identity_query.lua.execute('components[901]=nil')
    r=identity_query('get_sim_entity',{'id':901})
    assert r['ok'] and r['result']['exists'] is False and 'components' not in r['result']
    assert 'not proof' in r['result']['scope']


@pytest.mark.parametrize('setup,message',[
    ('components[901]={[1]={name="not a sim entity"}}','neither SIM_PERSON nor SIM_CARGO'),
    ('api.type.ComponentType.SIM_ENTITY_MOVING=nil','Native component type unavailable'),
    ('local old=api.engine.getComponent;api.engine.getComponent=function(id,ct)if ct==1903 then error("native component failure")end;return old(id,ct)end','native component failure'),
])
def test_missing_types_and_native_failures_do_not_claim_alighting(identity_query,setup,message):
    identity_query.lua.execute(setup)
    r=identity_query('get_sim_entity',{'id':901})
    assert not r['ok'] and message in r['error']


@pytest.mark.parametrize('cmd,args',[
    ('get_vehicle_cargo',{'vehicle':701,'cargo':0,'limit':1}),
    ('get_vehicle_cargo',{'vehicle':701,'cargo':0,'include_entities':False,'offset':0}),
    ('get_vehicle_cargo',{'vehicle':701,'cargo':0,'include_entities':True,'limit':101}),
    ('get_vehicle_cargo',{'vehicle':701,'cargo':0,'include_entities':True,'offset':-1}),
    ('get_sim_entity',{'id':True}),('get_sim_entity',{'id':-1}),
])
def test_identity_read_argument_bounds(cmd,args):
    with pytest.raises(ValueError):validate_build_arguments(cmd,args)


def test_live_regression_empty_aggregate_map_does_not_hide_onboard_people(identity_query):
    identity_query.lua.execute('onboard={};components[902][1904].place=35;components[906]={[1901]={cargoType=0},[1903]={vehicle=999},[1904]={vehicle=999}}')
    a=identity_query('get_vehicle_cargo',{'vehicle':701,'cargo':0,'include_entities':True,'limit':2})
    e=a['result']['entities']
    assert e['ids']==[901,902] and e['total']==5 and e['countAgreement']
    assert e['source']=='sim_person_vehicle_components' and e['scannedPersons']==6
    b=identity_query('get_vehicle_cargo',{'vehicle':701,'cargo':0,'include_entities':True,'offset':2,'limit':3})
    assert b['result']['entities']['ids']==[903,904,905] and not b['result']['entities']['hasMore']
    assert identity_query.lua.globals().mapCalls==0


@pytest.mark.parametrize('setup,message',[
    ('components[902][1904].vehicle=999','components disagree'),
    ('components[902][1903]=nil','components disagree'),
    ('local old=api.engine.getComponent;api.engine.getComponent=function(id,ct)if ct==1904 then error("native seat failure")end;return old(id,ct)end','native seat failure'),
    ('api.engine.forEachEntityWithComponent=function(f)for i=1,100001 do f(999999)end end','scan exceeds'),
])
def test_passenger_scan_never_hides_disagreement_or_native_failure(identity_query,setup,message):
    identity_query.lua.execute(setup)
    r=identity_query('get_vehicle_cargo',{'vehicle':701,'cargo':0,'include_entities':True})
    assert not r['ok'] and message in r['error']
