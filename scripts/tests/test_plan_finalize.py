import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from plan_finalize import finalize, validate_pack
from fullmap_fleet import fleet_rows, Fleet
from fullmap_batch import StopBatch


def make_pack(root):
    def write(name,value): (root/name).write_text(json.dumps(value),'utf8')
    box={'min':{'x':-2,'y':-1},'max':{'x':2,'y':1}}
    facilities=[dict(id=k,kind=kind,position={'x':0,'y':0},rotation=90,footprint=box,reserved=box,reuseOnly=k=='HQ')
                for k,kind in [('HQ','headquarters'),('D','road_depot'),('A','truck'),('B','truck')]]
    line=dict(id='L',mode='TRUCK',source='A',destination='B',cargos={'6':10},flows=[],path=[{'x':0,'y':0}],
        vehicle_model='model',fleet_forecast=2,oneway_seconds_forecast=100,load_at_source=[6],load_at_destination=[])
    p=dict(facilities=facilities,ports=[],line_specs=[line],routes=[],hubs=[],roads=[],city_stops=[],supply=[],industries=[],
        cities=[dict(id=1,name='Test',position={'x':0,'y':0})],focus_town=1,snapshot=str(root/'snapshot.json'))
    write('snapshot.json',{});write('network_plan.json',p)
    jobs=[dict(id=f['id'],stage='facility',depends_on=[]) for f in facilities]+[dict(id='L',stage='line',spec=line,depends_on=[])]
    write('execution_manifest.json',dict(jobs=jobs,commit_enabled=False))
    write('fleet_manifest.json',dict(commit_enabled=False,vehicles=[dict(line='L',model='model',quantity=2,depot='D',cargos=[6])]))
    return p


def test_finalize_synchronizes_and_detects_stale_artifacts_without_game(tmp_path):
    p=make_pack(tmp_path);result=finalize(tmp_path)
    assert result['passed'] and result['gameCalls']==0
    now=json.loads((tmp_path/'network_plan.json').read_text('utf8'))
    assert now['facilities']==p['facilities'] and now['line_specs'][0]['purchase_base']=='D'
    assert (tmp_path/'before_operations_update/network_plan.json').exists()
    assert '已建复用' in (tmp_path/'report_plan.json').read_text('utf8')
    hq=next(s for s in json.loads((tmp_path/'report_plan.json').read_text('utf8'))['sites'] if s['name']=='HQ')
    assert hq['current']['max']['x']==pytest.approx(1)
    assert hq['current']['max']['y']==pytest.approx(2)
    with (tmp_path/'FACILITIES.csv').open('a',encoding='utf8') as f:f.write('stale')
    with pytest.raises(ValueError,match='Stale derived'):validate_pack(tmp_path)


def test_finalize_refuses_execution_ledger(tmp_path):
    make_pack(tmp_path);(tmp_path/'ledger.json').write_text('{}','utf8')
    with pytest.raises(ValueError,match='reconcile'):finalize(tmp_path)

def test_staged_network_acceptance_remains_a_line_prerequisite(tmp_path):
    p=make_pack(tmp_path);p['line_specs'][0]['prerequisite_jobs']=['VERIFY_NETWORK']
    (tmp_path/'network_plan.json').write_text(json.dumps(p),'utf8')
    path=tmp_path/'execution_manifest.json';m=json.loads(path.read_text('utf8'))
    m['jobs'].append(dict(id='VERIFY_NETWORK',kind='native_path_acceptance',depends_on=['A','B']))
    path.write_text(json.dumps(m),'utf8');finalize(tmp_path)
    result=json.loads(path.read_text('utf8'))
    assert 'VERIFY_NETWORK' in next(j for j in result['jobs'] if j['id']=='L')['depends_on']


def test_fleet_exact_manifest_count_model_and_depot_validation(tmp_path):
    p=make_pack(tmp_path)
    policy=json.loads((tmp_path/'fleet_manifest.json').read_text('utf8'));policy['planDigest']='x'
    rows=fleet_rows(policy,p,'x')
    assert rows[0]['count']==2 and rows[0]['model']=='model' and rows[0]['depot']=='D'
    policy['vehicles'][0]['quantity']=2.5
    with pytest.raises(StopBatch,match='integer'):fleet_rows(policy,p,'x')
    policy['vehicles'][0]['quantity']=2;policy['vehicles'][0]['depot']='HQ'
    with pytest.raises(StopBatch,match='depot'):fleet_rows(policy,p,'x')


def test_fleet_preview_restricts_to_manifest_depot(tmp_path):
    import asyncio
    p=make_pack(tmp_path);policy=json.loads((tmp_path/'fleet_manifest.json').read_text('utf8'));policy['planDigest']='x'
    (tmp_path/'fleet_manifest.json').write_text(json.dumps(policy),'utf8')
    b=Fleet.__new__(Fleet);b.p=p;b.a=SimpleNamespace(fleet=tmp_path/'fleet_manifest.json',action='preview',limit=0)
    b.ledger={'planDigest':'x','items':{'L':{'status':'static_verified'}}};b.session=AsyncMock();b.save=AsyncMock();b.flush=lambda:None
    b.specs=lambda:[dict(id='L',mode='TRUCK',endpoints=[{'position':{'x':0,'y':0}}])]
    b.tasks=lambda:p['facilities']+[dict(id='WRONG',kind='road_depot',position={'x':0,'y':0})]
    b.line=AsyncMock(return_value={'existing':True,'verified':True});b.vehicle=AsyncMock(side_effect=[{'vehicles':[]},{'selected':1},{'vehicles':[]},{'selected':1}])
    asyncio.run(b.run())
    assert len(b.vehicle.call_args_list)==4
    assert all([d['id'] for d in c.args[0]['depots']]==['D'] for c in b.vehicle.call_args_list)
    assert all(c.args[1]!='build' for c in b.vehicle.call_args_list)
