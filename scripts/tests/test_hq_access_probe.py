"""Offline behavior tests, including the original nil-parameter regression."""
import asyncio,copy,json,sys
from pathlib import Path
import pytest
from lupa.lua52 import LuaRuntime,LuaError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hq_access_probe as probe

SOURCE=Path(probe.__file__).with_name('hq_access_preview.lua').read_text('utf8')
SETUP='''
calls=0;stages={}
function debugPrint(s)stages[#stages+1]=s end
local function n(e,i)return{entity=e,index=i}end
local function edge(e)return{conns={n(e,0),n(e,1)},transportModes={[0]=true},forwardOnly=false}end
input={runId='test',args={},road={position0={x=0,y=0,z=1},position1={x=10,y=0,z=1},roadTemplate='road'}}
pd={errorState={critical=false,messages={},infos={},warnings={}},collisionInfo={collisionEntities={}},
entity2tn={[-1]={edges={edge(-1)}}},tpNetLinkProposal={toAdd={{link={
from={edgeId={entity=-1,index=0},param=1},to={edgeId={entity=22,index=0},param=.5}}}}}}
setmetatable(pd,{__index=function(_,key)error('Unexpected native field '..key)end})
B={json={decode=function()return input end,encode=function(v)return v end},
prepareHeadquarters=function()return {},{player=1},{year=2000,seed=1,modules={[1]={}}}end}
api={type={ComponentType={BASE_EDGE=1,TRANSPORT_NETWORK=2},Context={new=function()return{}end}},engine={
system={streetSystem={getNode2SegmentMap=function()return{[1]={22},[2]={22}}end}},
forEachEntityWithComponent=function()error('BASE_EDGE enumeration is unsupported')end,
getComponent=function(e,c)if c==1 then return input.road else return {edges={edge(22)}}end end,
util={proposal={makeProposalData=function()calls=calls+1;return pd end}}}}
'''
def run(extra=''):
    lua=LuaRuntime(unpack_returned_tuples=True);lua.execute(SETUP+extra)
    result=lua.execute(SOURCE.replace('INPUT_JSON',"'fixture'"))
    return lua,result

def test_single_proposal_and_only_typed_bounded_fields():
    lua,r=run()
    assert lua.globals().calls==1 and r['nativeProposalCalls']==1
    assert r['road']==22 and len(r['networks'])==2 and len(r['links'])==1
    assert r['phases'][len(r['phases'])]=='typed_link_read_complete'
    assert 'toPlain'not in SOURCE and 'sendCommand'not in SOURCE

def test_nil_parameters_stops_before_native_preview():
    lua=LuaRuntime();lua.execute(SETUP+"B.prepareHeadquarters=function()return {},{player=1},nil end")
    with pytest.raises(LuaError,match='parameter table missing'):
        lua.execute(SOURCE.replace('INPUT_JSON',"'fixture'"))
    assert lua.globals().calls==0

def test_collisions_do_not_read_native_graph():
    lua,r=run("pd.collisionInfo.collisionEntities={{entity=9}};pd.entity2tn=nil;pd.tpNetLinkProposal=nil")
    assert not r['check']['clear'] and len(r['networks'])==0

def test_changed_road_stops_before_proposal():
    lua=LuaRuntime();lua.execute(SETUP+"api.engine.system.streetSystem.getNode2SegmentMap=function()return{}end")
    with pytest.raises(LuaError,match='Frontage road missing'):
        lua.execute(SOURCE.replace('INPUT_JSON',"'fixture'"))
    assert lua.globals().calls==0

def test_native_edge_budget_stops_oversized_read():
    with pytest.raises(LuaError,match='Edge budget exceeded'):
        run("local e=pd.entity2tn[-1].edges[1];for i=2,4097 do pd.entity2tn[-1].edges[i]=e end")

def test_unreadable_link_fails_instead_of_claiming_no_link():
    with pytest.raises(LuaError,match='Invalid automatic link endpoint'):
        run('pd.tpNetLinkProposal.toAdd[1].link.from=nil')

def sample(oneway=False,links=True):
    def net(entity):return {'entity':entity,'edges':[{'index':0,'from':{'entity':entity,'index':0},'to':{'entity':entity,'index':1},'forwardOnly':oneway if entity<0 else False}]}
    return {'check':{'clear':True},'nativeProposalCalls':1,'road':22,'networks':[net(-1),net(22)],
            'links':[{'from':{'entity':-1,'index':0,'param':1},'to':{'entity':22,'index':0,'param':.5}}]if links else []}

def test_bidirectional_link_at_road_midpoint():
    r=probe.analyze(sample());assert r['entranceConnected'] and r['inbound']and r['outbound']
    assert r['constructionReady']is False

def test_missing_link_cannot_pass_from_geometry_only():
    assert not probe.analyze(sample(links=False))['entranceConnected']

def test_oneway_entrance_does_not_mask_failed_return_path():
    r=probe.analyze(sample(oneway=True));assert r['outbound']and not r['inbound']and not r['entranceConnected']

def test_invalid_link_parameter_fails_closed():
    r=sample();r['links'][0]['to']['param']=float('nan')
    with pytest.raises(ValueError,match='link parameter'):probe.analyze(r)

def test_existing_positive_entities_use_real_links_without_proposal():
    r=sample();r['nativeProposalCalls']=0
    r=json.loads(json.dumps(r).replace('"entity": -1','"entity": 71'))
    a=probe.analyze(r,existing_entities=[71])
    assert a['entranceConnected'] and not a['constructionReady']
    r['links']=[]
    assert not probe.analyze(r,existing_entities=[71])['entranceConnected']

def test_existing_audit_rejects_proposals_or_unknown_owners():
    with pytest.raises(ValueError,match='must not generate'):
        probe.analyze(sample(),existing_entities=[71])
    r=sample();r['nativeProposalCalls']=0
    with pytest.raises(ValueError,match='Positive current'):
        probe.analyze(r,existing_entities=[])

def test_missing_reuse_only_facility_cannot_fall_through_to_preview():
    source=Path(probe.__file__).with_name('fullmap_facility.lua').read_text('utf8')
    # Execute the actual gate before the native preview branch, with no API available.
    start=source.index("assert(not task.reuseOnly")
    end=source.index('local args=task.args',start)
    lua=LuaRuntime();lua.execute("task={reuseOnly=true};action='preview'")
    with pytest.raises(LuaError,match='Reuse-only facility missing'):
        lua.execute(source[start:end])

def test_prepare_only_never_constructs_bridge(monkeypatch,tmp_path):
    p={'focus_town':1,'facilities':[{'id':'HQ','args':dict(town=1,x=0,y=0,z=1,rotation=0),'road_frontage':{'edge_hint':22}}]}
    s={'obstacles':[dict(kind='BASE_EDGE',entity=22,position0=dict(x=0,y=0,z=1),position1=dict(x=10,y=0,z=1),roadTemplate='road')]}
    (tmp_path/'plan.json').write_text(json.dumps(p));(tmp_path/'snapshot.json').write_text(json.dumps(s))
    monkeypatch.setattr(probe,'Batch',lambda *a:pytest.fail('Offline preparation contacted bridge'))
    monkeypatch.setattr(sys,'argv',['probe','--plan',str(tmp_path/'plan.json'),'--output',str(tmp_path/'out.json'),'--prepare-only'])
    asyncio.run(probe.main());assert json.loads((tmp_path/'out.json').read_text())['gameCalls']==0
    with pytest.raises(RuntimeError,match='Existing result'):asyncio.run(probe.main())
