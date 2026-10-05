import copy,json,asyncio,contextlib
from pathlib import Path
from types import SimpleNamespace
import pytest
from lupa import LuaRuntime,LuaError
from hub_joint_prototype import compile_spec,probe
from build_joint_collection import prepare,code_for,execute
from verify_joint_test import acceptance
from test_hub_joint_prototype import fixture
from test_hub_joint_bind import SETUP

SCRIPTS=Path(__file__).resolve().parents[1]
def city():
    t=fixture()
    t['facilities'].append(dict(role='road_depot',resource='::/depots/road/road_depot/road_depot.con',localPosition=dict(x=0,y=0,z=0),relativeRotation=90,params={'modules':{}}))
    t['rolePortNodes']['road_depot']=['3']
    return t

def test_five_roles_and_reserved_ids():
    t=city();old=copy.deepcopy(t);s=compile_spec(t)
    assert t==old and len(s['facilities'])==5
    assert set(s['portBindings'])=={'bus','truck','road_depot'}
    assert s['bindGeneratedPorts'] and s['alignGeneratedPortGeometry']
    ids=[n['entity']for n in s['nodes']]+[r['entity']for r in s['roads']]
    assert len(ids)==len(set(ids)) and max(ids)<-5
    assert s['portBindings']['road_depot']['expectedLocalPort']['x']==pytest.approx(35)

def test_missing_depot_port_or_wrong_resource_rejected():
    t=city();del t['rolePortNodes']['road_depot']
    with pytest.raises(ValueError,match='road_depot'):compile_spec(t)
    t=city();t['facilities'][-1]['resource']='other'
    with pytest.raises(ValueError,match='resource'):compile_spec(t)

def test_shared_template_port_preserved_for_native_resolution():
    t=city();t['rolePortNodes']['road_depot']=t['rolePortNodes']['truck'][:]
    s=compile_spec(t)
    assert s['portBindings']['road_depot']['roadNode']==s['portBindings']['truck']['roadNode']

DEPOT='''
spec.portBindings.road_depot={roadNode=-8,expectedLocalPort={x=35,y=0,z=0}}
function point(p)return p end
pd.entity2tn[-60]={edges={{conns={{entity=-61,index=0},{entity=-62,index=0}},transportModes={[2]=true,[3]=true,[4]=true},geometry={cubicSpline={pos={{x=35,y=0},{x=20.26,y=0}}},height={x=0,y=0}}}}}
api.engine.util.proposal.makeProposalData=function()called=called+1;return{entity2tn={[-21]={},[-23]={},[-61]={}}}end
'''
def bind(extra=''):
    lua=LuaRuntime();lua.execute(SETUP+DEPOT+extra)
    lua.execute((SCRIPTS/'hub_joint_bind_probe.lua').read_text('utf8'))
    return lua.globals()

def test_external_depot_port_not_frozen_inner_endpoint():
    g=bind();assert g.spec.portBindings.road_depot.nativeEntranceNode==-61
    assert g.called==1

def test_depot_missing_or_ambiguous_geometry_stops():
    with pytest.raises(LuaError,match='ambiguous'):bind('pd.entity2tn[-60]=nil')
    with pytest.raises(LuaError,match='ambiguous'):bind('pd.entity2tn[-60].edges[1].geometry.cubicSpline.pos[2].x=35')

def test_shared_port_never_silently_overwrites_truck_binding():
    with pytest.raises(LuaError,match='Shared template port'):bind('spec.portBindings.road_depot.roadNode=-5')
    g=bind('spec.portBindings.road_depot.roadNode=-5;pd.entity2tn[-60].edges[1].conns[1].entity=-23')
    assert g.spec.portBindings.truck.nativeEntranceNode==g.spec.portBindings.road_depot.nativeEntranceNode

def test_native_depot_world_ids_and_changed_id_rejected():
    with pytest.raises(LuaError,match='ambiguous'):bind('pd.entity2tn[-60].edges[1].conns[1].entity=999')
    with pytest.raises(LuaError,match='identity changed'):bind('api.engine.util.proposal.makeProposalData=function()return{entity2tn={[-21]={},[-23]={}}}end')

def test_native_code_has_exactly_one_commit_and_valid_lua():
    s=compile_spec(city());o={'x':100,'y':200,'rotation':37}
    preview=code_for(s,o);commit=code_for(s,o,True)
    assert 'sendCommand'not in preview and commit.count('api.cmd.sendCommand(')==1
    assert 'Depot preview path failed'in preview and 'Depot preview path failed'in commit
    lua=LuaRuntime()
    for source in (probe(s),preview,commit):lua.execute('assert(load(...))',source)

def test_2d_current_template_compiles_with_derived_tangents():
    path=SCRIPTS.parent/'config/planning_templates/city_air.json'
    paths=[p for p in (SCRIPTS.parent/'config/planning_templates').glob('*.json') if {f['role']for f in json.loads(p.read_text('utf8')).get('facilities',[])}in ({'bus','truck','warehouse','heliport','road_depot'},{'bus','truck','warehouse','heliport','road_depot','road_maintenance'})]
    assert paths
    for path in paths:
        s=compile_spec(json.loads(path.read_text('utf8')))
        LuaRuntime().execute('assert(load(...))',probe(s))
        assert all('z'in r['tangent0']and'z'in r['tangent1']for r in s['roads'])

def result():
    return dict(modulesVerified=True,roads=[dict(baseEdge=True,network=True,node0Network=True,node1Network=True)],coverage={'truck':True,'heliport':True},paths={'truck':{'inbound':{'verified':True}},'road_depot':{'out_4':{'verified':True}},'walking':{'inbound':{'verified':False}}},airportRoadLinkRequired=True,airportRoadLinkVerified=False)

def test_walking_deferral_does_not_claim_full_acceptance():
    r=result();assert acceptance(r,True)is False
    assert r['placementAccepted']and r['walkingDeferred'] and not r['paths']['walking']['inbound']['verified']
    r=result();assert acceptance(r,False)is False and not r['placementAccepted']

@pytest.mark.parametrize('failure',['depot','coverage','modules','road'])
def test_deferral_keeps_other_gates(failure):
    r=result()
    if failure=='depot':r['paths']['road_depot']['out_4']['verified']=False
    elif failure=='coverage':r['coverage']['truck']=False
    elif failure=='modules':r['modulesVerified']=False
    else:r['roads'][0]['network']=False
    acceptance(r,True);assert not r['placementAccepted']

def make_plan():
    t=city();owner='T1';fs=[]
    for f in t['facilities']:
        fs.append(dict(id=owner+'_'+f['role'],kind=f['role'],position=f['localPosition'],rotation=f['relativeRotation'],params=f['params'],resource=f['resource']))
    roads=[dict(id=f'T1_internal_{i}',path=[r['position0'],r['position1']],templateRoad=r,street_type=r['roadTemplate'])for i,r in enumerate(t['roads'])]
    return dict(hubs=[dict(owner=owner,template='city',position=dict(x=0,y=0),rotation=0,facilities={f['role']:owner+'_'+f['role']for f in t['facilities']})],templates={'city':t},facilities=fs,roads=roads)

@pytest.mark.parametrize('unknown',[False,True])
def test_executor_single_submission_and_no_retry(tmp_path,monkeypatch,unknown):
    import build_joint_collection as mod
    plan=make_plan()
    class Fake:
        def __init__(self):
            self.p=plan;self.out=tmp_path;self.b=SimpleNamespace(dir=tmp_path);self.ledger={'items':{}};self.commits=0;self.saves=[]
        async def session(self):return {'speedup':0}
        def flush(self):pass
        def tasks(self):return plan['facilities']
        async def save(self,phase):self.saves.append(phase)
        async def read_facilities(self,tasks,action,with_session):
            return [dict(result=dict(existing=self.commits>0,audit=dict(staticVerified=True,entity=100+i,params=t['params'])))for i,t in enumerate(tasks)]
        async def eval(self,code):
            if 'api.cmd.sendCommand('in code:
                self.commits+=1
                return dict(callback={'success':not unknown},added=dict(constructions=list(range(100,105)),edges=[],nodes=[]))
            if 'local ids=B.json.decode'in code:
                r=result();r['airportRoadLinkVerified']=True;r['paths']['walking']['inbound']['verified']=True
                return r
            return {'previewPassed':True}
    b=Fake();monkeypatch.setattr(mod,'Batch',lambda a:b);monkeypatch.setattr(mod,'batch_lock',lambda d:contextlib.nullcontext())
    a=SimpleNamespace(owner='T1',action='build',isolated_test_save=True,authorize_build=True,defer_walking=True)
    if unknown:
        with pytest.raises(mod.StopBatch,match='incomplete'):asyncio.run(execute(a))
        assert b.ledger['items']['JOINT_T1']['status']=='needs_reconciliation'
    else:
        asyncio.run(execute(a))
        assert b.ledger['items']['JOINT_T1']['status']=='static_verified'
        assert len([v for k,v in b.ledger['items'].items()if k.startswith('T1_')])==5
    with pytest.raises(mod.StopBatch):asyncio.run(execute(a))
    assert b.commits==1 and b.saves[0]=='joint_preview_before'
    assert 'joint_before'in b.saves

def test_missing_test_save_confirmation_never_calls_bridge(tmp_path,monkeypatch):
    import build_joint_collection as mod
    b=SimpleNamespace(p=make_plan(),out=tmp_path)
    monkeypatch.setattr(mod,'Batch',lambda a:b)
    with pytest.raises(mod.StopBatch,match='isolated'):
        asyncio.run(execute(SimpleNamespace(owner='T1',action='build',isolated_test_save=False)))
