import copy,json
from pathlib import Path
import pytest
from lupa import LuaRuntime
from hub_joint_prototype import compile_spec
from road_first_collection import stage_spec,source
from road_first_collection import WALK

def spec():
    t=json.loads((Path(__file__).resolve().parent/'fixtures/city_road_first_v3.json').read_text('utf8'))
    for r in t['roads']:r['buildPhase']='entrance' if r.get('bindRole')else 'frontage'
    return compile_spec(t)

def test_phase_split_and_fresh_positive_nodes():
    s=spec();original=copy.deepcopy(s);roads=stage_spec(s,'roads')
    assert not roads['facilities'] and not roads['portBindings']
    mapping={str(n['name']):100+i for i,n in enumerate(roads['nodes'])}
    facilities=stage_spec(s,'facilities',mapping,[201,202])
    assert len(facilities['facilities'])==6 and len(facilities['roads'])==3
    assert all(r['node0']>=100 and r['node1']<0 for r in facilities['roads'])
    assert all(n['entity']<0 for n in facilities['nodes'])
    assert len(facilities['existingBaseNodes'])==3 and s==original
    with pytest.raises(ValueError,match='readback'):stage_spec(s,'facilities')

def test_source_previews_never_submit_and_build_checks_walking_first():
    s=spec();road=stage_spec(s,'roads');mapping={str(n['name']):100+i for i,n in enumerate(road['nodes'])}
    facility=stage_spec(s,'facilities',mapping,[201]);o=dict(x=100,y=200,rotation=0)
    lua=LuaRuntime()
    for stage,sp in [('roads',road),('facilities',facility)]:
        for build in [False,True]:
            code=source(sp,o,stage,build)
            lua.execute('assert(load(...))',code)
            assert code.count('api.cmd.sendCommand(')==int(build)
            if stage=='facilities'and build:
                assert code.index('Walking preview failed')<code.index('api.cmd.sendCommand(')
                assert 'Existing road moved'in code


@pytest.mark.parametrize('reverse,expected',[(True,True),(False,False)])
def test_native_transfer_requires_both_directions_and_no_self_match(reverse,expected):
    helper=Path(__file__).resolve().parents[1].joinpath('station_walk_transfer.lua').read_text('utf8')
    lua=LuaRuntime()
    setup='local reach={[1]={[2]=65.6},[2]='+('{[1]=65.6}'if reverse else '{}')+'};'
    result=lua.execute(setup+helper+'return transfer({1},{2}).verified and transfer({2},{1}).verified')
    assert result==expected
    assert lua.execute('local reach={[1]={[1]=0}};'+helper+'return transfer({1},{1}).verified') is False
    assert lua.execute('local reach={};'+helper+'return transfer({},{2}).verified') is False


@pytest.mark.parametrize('linked,person',[(True,True),(False,True),(True,False)])
def test_preview_uses_native_from_to_links_and_person_lanes(linked,person):
    lua=LuaRuntime();setup='''
local function edge(id,modes)return {conns={{entity=id,index=0},{entity=id,index=1}},transportModes=modes,forwardOnly=false}end
api={type={ComponentType={}}};spec={existingRoadEntities={}}
pd={entity2tn={[-101]={edges={edge(-101,{[0]=true,[3]=true})}},[-102]={edges={edge(-102,{[0]=true,[13]=true})}}},tpNetLinkProposal={toAdd={}}}
'''
    if linked:setup+="pd.tpNetLinkProposal.toAdd={{link={from={edgeId={entity=-101,index=0},param=.3},to={edgeId={entity=-102,index=0},param=.6}}}};"
    if not person:setup+='pd.entity2tn[-102].edges[1].transportModes[0]=false;'
    result=lua.execute(setup+WALK+';return walkPreview')
    assert result['outbound']==(linked and person)
    assert result['inbound']==(linked and person)


@pytest.mark.parametrize('defer',[False,True])
def test_controller_auto_uses_two_stages_and_refuses_deferral(tmp_path,monkeypatch,defer):
    import construct_planned_map as mod
    from types import SimpleNamespace
    p=tmp_path/'plan.json';p.write_text(json.dumps(dict(templates={'city':{'placementMode':'road-first'}},
        hubs=[dict(owner='T1',kind='city',template='city',facilities={})],cities=[],roads=[])),encoding='utf8')
    args=['run','--plan',str(p),'--output',str(tmp_path/'out'),'--authorize-build','--current-map-test']
    if defer:args+=['--defer-walking']
    monkeypatch.setattr(mod.sys,'argv',args);calls=[]
    monkeypatch.setattr(mod.subprocess,'run',lambda c:(calls.append(c)or SimpleNamespace(returncode=0)))
    if defer:
        with pytest.raises(SystemExit):mod.main()
        assert calls==[]
    else:
        mod.main();assert len(calls)==2
        assert [c[c.index('--stage')+1]for c in calls]==['roads','facilities']
        assert all('--current-map-test'in c and '--authorize-build'in c for c in calls)


def test_unknown_submission_locks_road_phase(tmp_path,monkeypatch):
    import asyncio,contextlib
    import road_first_collection as mod
    from types import SimpleNamespace
    base=spec()
    class Fake:
        def __init__(self):self.p={};self.out=tmp_path;self.b=SimpleNamespace(dir=tmp_path);self.ledger={'items':{}};self.commits=0
        async def session(self):return {'speedup':0}
        def flush(self):pass
        async def save(self,phase):pass
        async def eval(self,code):
            if 'api.cmd.sendCommand('in code:
                self.commits+=1;return {'callback':{'success':False}}
            return {'previewPassed':True}
    b=Fake();monkeypatch.setattr(mod,'Batch',lambda a:b)
    monkeypatch.setattr(mod,'prepare',lambda p,o,include_external=False:({},base,{'x':0,'y':0,'rotation':0}))
    monkeypatch.setattr(mod,'batch_lock',lambda d:contextlib.nullcontext())
    a=SimpleNamespace(owner='T1',action='build',stage='roads',current_map_test=True,authorize_build=True)
    with pytest.raises(mod.StopBatch,match='unknown'):asyncio.run(mod.run(a))
    assert b.ledger['items']['ROAD_FIRST_T1_roads']['status']=='needs_reconciliation'
    with pytest.raises(mod.StopBatch,match='Unreconciled'):asyncio.run(mod.run(a))
    assert b.commits==1


def test_production_road_first_keeps_complete_city_and_vehicle_walking_gates():
    from planning_pipeline_core import prepare_template
    p=Path(__file__).resolve().parent/'fixtures/city_road_first_v3.json'
    t=prepare_template(json.loads(p.read_text('utf8')),'production')
    assert t['placementMode']=='road-first'
    s=compile_spec(t);r=stage_spec(s,'roads')
    assert len(r['roads'])==7 and not r['facilities']
    mapping={str(n['name']):100+i for i,n in enumerate(r['nodes'])}
    f=stage_spec(s,'facilities',mapping,[201,202,203,204])
    assert {v['role'] for v in f['facilities']}=={'heliport','bus','road_depot','road_maintenance','truck','warehouse'}
    assert len(f['roads'])==3 and f['roads'][0]['node0']>0
    lua=LuaRuntime()
    for build in (False,True):
        code=source(f,dict(x=0,y=0,rotation=90),'facilities',build)
        lua.execute('assert(load(...))',code)
        assert 'Walking preview failed' in code
        assert 'Vehicle preview path failed' in code
        assert code.count('api.cmd.sendCommand(')==int(build)
    bad=copy.deepcopy(s);bad['facilities']=[v for v in bad['facilities'] if v['role']!='bus']
    with pytest.raises(ValueError,match='dual-pad'):stage_spec(bad,'roads')


def test_receipts_are_isolated_by_collection_and_legacy_is_unambiguous(tmp_path):
    from types import SimpleNamespace
    from road_first_collection import stage_key,evidence_dir,StopBatch
    b=SimpleNamespace(p={'hubs':[{'owner':'T1'},{'owner':'P2'}]},out=tmp_path,ledger={'items':{}})
    assert stage_key(b,'T1','roads')!=stage_key(b,'P2','roads')
    assert evidence_dir(b,'T1')!=evidence_dir(b,'P2')
    b.ledger['items']['ROAD_FIRST_roads']={'status':'static_verified'}
    with pytest.raises(StopBatch,match='legacy'):stage_key(b,'P2','roads')
    b.p['hubs']=[{'owner':'T1'}]
    assert stage_key(b,'T1','roads')=='ROAD_FIRST_roads'
    assert stage_key(b,'P2','roads')=='ROAD_FIRST_P2_roads'


def test_roadside_template_rejects_broken_alignment():
    from road_snap_layout import validate_road_snaps
    p=Path(__file__).resolve().parent/'fixtures/city_road_first_v3.json'
    t=json.loads(p.read_text('utf8'));validate_road_snaps(t)
    pads=[f for f in t['facilities'] if f.get('roadSnap')]
    assert {f['role'] for f in pads}=={'road_maintenance'}
    pads[0]['localPosition']['y']+=1
    with pytest.raises(ValueError,match='aligns'):compile_spec(t)


@pytest.mark.parametrize('found',[True,False])
def test_snap_height_reads_existing_frontage_and_rejects_missing_road(found):
    from road_first_collection import SNAP_HEIGHT
    lua=LuaRuntime()
    setup='''
local data={ [10]={node0=11,node1=12},[11]={position={x=0,y=0,z=5}},[12]={position={x=100,y=0,z=9}} }
api={type={ComponentType={BASE_EDGE=1,BASE_NODE=2}},engine={getComponent=function(id,kind)return data[id]end}}
local spec={existingRoadEntities={10}}
local function point(p)return p end
local f={roadSnap={roadPoint={x=50,y=0}}}
'''
    if not found:setup+='spec.existingRoadEntities={};'
    code=setup+SNAP_HEIGHT+'return roadsideHeight(f,{x=50,y=32,z=100}).z'
    if found:assert lua.execute(code)==7
    else:
        with pytest.raises(Exception,match='Fresh frontage missing'):lua.execute(code)
