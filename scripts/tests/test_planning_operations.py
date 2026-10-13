import copy
import pytest
from planning_operations import assign_air_maintenance, chain_forecasts, platform_forecasts, enrich


def line(id, source='A', destination='B', **kwargs):
    return dict(id=id, mode='HELICOPTER', source=source, destination=destination,
                cargos={'6':10}, flows=['R'], fleet_forecast=1, oneway_seconds_forecast=100,
                headway_seconds_forecast=200, deadline_seconds=250,
                source_terminal_index=0, destination_terminal_index=0, **kwargs)


def plan():
    return dict(facilities=[dict(id=k,kind='heliport',position={'x':x,'y':0}) for k,x in [('A',0),('B',100),('REMOTE',10000)]],
        line_specs=[line('L1'),line('L2')],hubs=[],routes=[dict(id='R',cargo=6,transfer_chain=[dict(mode='HELICOPTER',**{'from':'A','to':'B'})])])


def test_endpoint_maintenance_balances_and_rejects_explicit_incapability():
    p=plan();r=assign_air_maintenance(p)
    assert r['fleetLoadByBase']=={'A':1,'B':1}
    assert all(not a['nativeVerified'] for a in r['assignments'])
    p['facilities'][0]['maintenance_capability_verified']=False
    assign_air_maintenance(p)
    assert all(l['maintenance_base']=='B' for l in p['line_specs'])


def test_missing_maintenance_candidates_never_fabricates_acceptance():
    p=plan();p['facilities']=[]
    result=assign_air_maintenance(p)
    assert all(x['status']=='unresolved' for x in result['assignments'])
    assert all(x['maintenance_base'] is None for x in p['line_specs'])


def test_parallel_legs_weighted_not_summed_and_wait_exposes_chain_risk():
    p=plan();p['line_specs'][1]['cargos']['6']=30
    p['line_specs'][1]['oneway_seconds_forecast']=200
    result=chain_forecasts(p)[0]
    assert result['travelSeconds']==175
    assert result['estimatedTotalSeconds']==275
    assert result['riskForecast'] and not result['nativeTimingVerified']
    p['cargo_deadlines_seconds']={'6':300}
    assert chain_forecasts(p)[0]['riskForecast'] is False


def test_series_and_missing_data():
    p=plan();p['routes'][0]['transfer_chain'].append(dict(mode='TRUCK',**{'from':'truck','to':{'town':2}}))
    assert chain_forecasts(p)[0]['complete'] is False
    truck=line('L3','truck',{'town':2});truck['mode']='TRUCK';p['line_specs'].append(truck)
    assert chain_forecasts(p)[0]['estimatedTotalSeconds']==400
    truck['headway_seconds_forecast']=float('nan')
    assert chain_forecasts(p)[0]['estimatedTotalSeconds'] is None


def test_overflow_pad_uses_declared_warehouse_group_only():
    p=plan();p['hubs']=[dict(facilities={'heliport':'A','warehouse':'W'})]
    p['facilities'].append(dict(id='overflow',kind='helipad',shared_warehouse='W'))
    p['line_specs'][0]['source']='overflow'
    assert len(chain_forecasts(p)[0]['legs'][0]['lines'])==2
    p['facilities'][-1]['shared_warehouse']='OTHER'
    assert len(chain_forecasts(p)[0]['legs'][0]['lines'])==1
    assert chain_forecasts(p)[0]['complete'] is False
    assert chain_forecasts(p)[0]['unmappedLines']==['L1']


def test_platform_frequency_not_only_line_count():
    p=plan()
    for l in p['line_specs']:l['headway_seconds_forecast']=100
    r=platform_forecasts(p)
    assert all(x['lineLimitPassed'] and x['capacityReviewRequired'] for x in r)
    assert r[0]['occupancyEstimate']==pytest.approx(1.2)
    p['line_specs'][0]['destination_terminal_index']=1
    assert len(platform_forecasts(p))==3


def test_non_cargo_roles_and_maintenance_not_counted_as_handling():
    p=plan();p['hubs']=[dict(owner='H',facilities={'warehouse':'W','heliport':'REMOTE','truck':'TR','bus':'BUS','road_depot':'D'})]
    p['collection_quantity_decisions']={'decisions':[{'owner':'H','traffic':['old']}]}
    enrich(p)
    assert p['hubs'][0]['sharedStockCheck']==['REMOTE','TR']
    assert p['collection_quantity_decisions']['decisions'][0]['traffic']==[]


def test_basic_mode_skips_detailed_forecasts_and_accepts_unbound_draft_terminal(monkeypatch):
    p=plan()
    p['operations_review']={'mode':'detailed','chains':[{'old':True}]}
    for l in p['line_specs']:
        l.pop('headway_seconds_forecast')
        l.pop('source_terminal_index')
    def unexpected(_):
        pytest.fail('Basic planning must not compute chain forecasts')
    monkeypatch.setattr('planning_operations.chain_forecasts',unexpected)
    result=enrich(p)
    assert result['mode']=='basic' and result['chains']==[]
    assert not result['operationalAccepted']
    assert result['maintenance']['assignments']
    assert all('roundtrip_seconds_forecast' not in l and 'headway_seconds_forecast' not in l for l in p['line_specs'])
    assert all(r['occupancyEstimate'] is None and not r['capacityReviewRequired'] for r in result['platforms'])
    assert any(r['terminal'] is None and r['lineLimitPassed'] is None for r in result['platforms'])


def test_detailed_mode_is_explicit_and_retains_estimates_when_switching_to_basic():
    p=plan();p['operationsAnalysis']='detailed'
    for l in p['line_specs']:l.pop('headway_seconds_forecast')
    result=enrich(p)
    assert result['mode']=='detailed' and result['chains'][0]['complete']
    assert p['line_specs'][0]['headway_seconds_forecast']==200
    p['operationsAnalysis']='basic';result=enrich(p)
    assert result['chains']==[] and all(r['occupancyEstimate'] is None for r in result['platforms'])
    assert p['line_specs'][0]['headway_seconds_forecast']==200


def test_unknown_occupancy_does_not_request_capacity_review_but_known_line_limit_does():
    p=plan()
    for l in p['line_specs']:l.pop('headway_seconds_forecast')
    assert all(r['forecastStatus']=='unknown' and not r['capacityReviewRequired'] for r in platform_forecasts(p))
    p['line_specs'] += [line('L3'),line('L4')]
    assert all(r['capacityReviewRequired'] for r in platform_forecasts(p,detailed=False))
