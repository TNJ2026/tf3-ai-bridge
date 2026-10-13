"""Guarded road-depot demolition. Native API is mocked; not live acceptance."""
import asyncio
import hashlib
import json
from unittest.mock import AsyncMock, Mock

import pytest
from test_ui_consolidated import Channel
from tf3_mcp.headless_client import HeadlessClient
from tf3_mcp.ui_log import validate_build_arguments
from tf3_mcp.headless import TAG
from test_headless import host, GEN

FIXTURE = r'''
local C=api.type.ComponentType
components[1][C.GAME_SPEED].speedup=0
components[320][C.CONSTRUCTION].fileName='::/depots/road/road_depot/road_depot.con'
components[320][C.CONSTRUCTION].params={seed=1,year=2000}
components[320][C.CONSTRUCTION].depots={300}
components[320][C.CONSTRUCTION].subconstructions={300}
components[320][C.CONSTRUCTION].frozenNodes={90000}
components[320][C.CONSTRUCTION].frozenEdges={90002}
components[90000]={[C.BASE_NODE]={position={x=1,y=1,z=0}}}
components[90001]={[C.BASE_NODE]={position={x=2,y=1,z=0}}}
components[90002]={[C.BASE_EDGE]={node0=90000,node1=90001,objects={}}}
components[90003]={[C.BASE_EDGE]={node0=90001,node1=STREET_A,objects={}}}
components[401]={[C.LINE]={stops={}},[C.PLAYER_OWNED]={player=2}}
components[90010]={[C.TRANSPORT_VEHICLE]={depot=300,line=401,state=1,userStopped=false,noPath=false,
 transportVehicleConfig={vehicles={{part={modelId=50},purchaseTime=100}}}}}
api.engine.util.proposal.createProposalRemove=function(entity)
 local c=components[entity][C.CONSTRUCTION]
 local p={toRemove={entity},toAdd={},old2new={},proposal={addedNodes={},addedSegments={},
  removedSegments={},removedNodes={},edgeObjectsToAdd={},new2oldEdgeObjects={},old2newEdgeObjects={},
  nodeConfigsToAdd={},nodeConfigsToRemove={}}}
 for _,id in ipairs(c.frozenEdges) do p.proposal.removedSegments[#p.proposal.removedSegments+1]={entity=id} end
 for _,id in ipairs(c.frozenNodes) do p.proposal.removedNodes[#p.proposal.removedNodes+1]={entity=id} end
 return p
end
-- The production adapter passes a full native Proposal unchanged. Translate
-- only at the mocked engine backend, whose historical implementation uses SimpleProposal.
local make=api.cmd.makeWorldBuildProposalCmd
api.cmd.makeWorldBuildProposalCmd=function(p,ctx,ignoreErrors,playerInitiated)
 assert(p.toRemove and p.proposal and p.constructionsToRemove==nil,'expected full native Proposal')
 return make({constructionsToRemove=p.toRemove,constructionsToAdd={},streetProposal={}},ctx,ignoreErrors,playerInitiated)
end
local old=api.cmd.sendCommand
api.cmd.sendCommand=function(cmd,cb)
 if cmd.kind=='build' then
  assert(cmd.ignoreErrors==false,'must not bypass native collision checks')
  if THROW then error('dispatch failed; outcome unknown') end
  if DELAY then DELIVER=function()old(cmd,cb)end;return end
  if REJECT then cb(nil,false,{});return end
  old(cmd,cb)
  if PARTIAL then components[90003]=nil end
  if LOST_VEHICLE then components[90010]=nil end
  if LEFT_NODE then components[90000]={[C.BASE_NODE]={}} end
  return
 end
 return old(cmd,cb)
end
'''

def preview(c, entity=300):
    r=c.query('preview_depot_removal', {'entity':entity})
    assert r['ok'],r
    assert r['result']['nativePreview'] is False
    return r['result']['preview_token']

def commit(c, token, **kw):
    return c.query('commit_depot_removal', {'preview_token':token,'backup_save':'verified_test_backup'}, **kw)

def read(c, token, **kw):
    return c.query('get_depot_removal_operation', {'operation_id':token}, **kw)

def test_success_existing_depot_preserves_road_and_vehicle_no_replay(tmp_path):
    c=Channel(tmp_path,FIXTURE)
    token=preview(c)
    assert c.lua.globals().dispatches==0
    r=commit(c,token);assert r['ok'] and r['result']['verified'],r
    assert r['result']['phase']=='confirmed'
    assert c.lua.globals().components[320] is None and c.lua.globals().components[300] is None
    assert c.lua.globals().components[90003] is not None
    assert c.lua.globals().components[90010] is not None
    assert read(c,token)['result']['verified']
    assert not commit(c,token)['ok']
    assert c.lua.globals().dispatches==1
    assert c.state['v']['uiConstruction']['pending'] is None


class NativeRecord:
    """Python proxy appears as opaque userdata to Lua, like native components."""
    def __init__(self, data):
        self.data={k:NativeRecord(v) if hasattr(v,'items') else v for k,v in data.items()}
    def __getitem__(self, key):
        return self.data[key]


def test_native_userdata_node_round_trip_and_changes(tmp_path):
    c=Channel(tmp_path,FIXTURE)
    ct=c.lua.globals().api.type.ComponentType
    for entity in (90001,c.lua.globals().STREET_A):
        container=c.lua.globals().components[entity]
        container[ct.BASE_NODE]=NativeRecord(container[ct.BASE_NODE])
    plain=c.game.script['_internal']['toPlain']
    old=plain(container[ct.BASE_NODE],0,None,'Network.BaseNode')
    assert old['_unavailable']=='opaque_userdata'
    # Earlier Network.BaseNode hint was undefined: tables passed, userdata failed.
    token=preview(c)
    r=commit(c,token)
    assert r['ok'] and r['result']['verified'],r
    assert read(c,token)['result']['verified']


def test_native_userdata_node_change_rejected(tmp_path):
    c=Channel(tmp_path,FIXTURE)
    ct=c.lua.globals().api.type.ComponentType
    container=c.lua.globals().components[90001]
    node=container[ct.BASE_NODE]
    native=NativeRecord(node)
    container[ct.BASE_NODE]=native
    token=preview(c)
    native.data['position'].data['x']=123
    assert not commit(c,token)['ok']
    assert c.lua.globals().dispatches==0


def test_native_vehicle_part_preserved(tmp_path):
    c=Channel(tmp_path,FIXTURE)
    part=NativeRecord({'modelId':50,'reversed':False,'color':{'x':1,'y':1,'z':1}})
    part.data['compartment2loadConfig']=c.lua.table()
    c.lua.globals().components[90010][9]['transportVehicleConfig']['vehicles'][1]['part']=part
    token=preview(c)
    r=commit(c,token)
    assert r['ok'] and r['result']['verified'],r


def test_full_native_proposal_userdata(tmp_path):
    c=Channel(tmp_path,FIXTURE)
    p=c.lua.globals().api.engine.util.proposal.createProposalRemove(320)
    street=NativeRecord({});street.data=dict(p['proposal'].items())
    native=NativeRecord({});native.data=dict(p.items());native.data['proposal']=street
    c.lua.globals().NATIVE_PROPOSAL=native
    c.lua.execute('api.engine.util.proposal.createProposalRemove=function()return NATIVE_PROPOSAL end')
    # Missing fields in native bindings can throw; backend must not inspect SimpleProposal fields.
    c.lua.execute('local old=api.cmd.makeWorldBuildProposalCmd;api.cmd.makeWorldBuildProposalCmd=function(p,ctx,ignore,user) local t={toRemove=p.toRemove,proposal=p.proposal};return old(t,ctx,ignore,user) end')
    token=preview(c)
    result=commit(c,token)
    assert result['ok'] and result['result']['verified'],result


@pytest.mark.parametrize('edit',[
 'p.toRemove={320,999}', 'p.toAdd={{}}', 'p.old2new={[320]=999}',
 'p.proposal.removedSegments={{entity=90003}}', 'p.proposal.removedNodes={{entity=90001}}',
 'p.proposal.addedSegments={{}}', 'p.proposal.addedNodes={{}}',
 'p.proposal.edgeObjectsToAdd={{}}', 'p.proposal.new2oldEdgeObjects={[1]={2}}',
 'p.proposal.old2newEdgeObjects={[1]={2}}', 'p.proposal.nodeConfigsToAdd={{entity=90001}}',
 'p.proposal.nodeConfigsToRemove={90001}',
])
def test_native_proposal_scope_rejection_includes_evidence(tmp_path,edit):
    c=Channel(tmp_path,FIXTURE)
    c.lua.execute('local old=api.engine.util.proposal.createProposalRemove;api.engine.util.proposal.createProposalRemove=function(e) local p=old(e);'+edit+';return p end')
    result=c.query('preview_depot_removal',{'entity':300})
    assert not result['ok'] and 'nativeScope=' in result['error'],result
    assert c.lua.globals().dispatches==0

@pytest.mark.parametrize('change',[
 'components[300][8].vehicles={1};components[90010][9].state=0',
 'components[90010][9].state=3',
 'components[90010][9].state=99',
 'components[90010][9].line=-1',
 'components[300][10].player=3',
 "components[320][11].fileName='::/depots/rail/depot.con'",
 'components[320][11].stations={999}',
 'components[320][11].subconstructions={300,999}',
 'components[1][5].speedup=4',
 'components[90003][api.type.ComponentType.BASE_EDGE].node0=90000',
 'components[90002][api.type.ComponentType.BASE_EDGE].objects={999}',
 'api.engine.system.transportVehicleSystem.getDepotVehicles=function()error("unavailable")end',
 'api.engine.system.transportVehicleSystem.getDepotVehicles=function()return nil end',
 'api.engine.system.streetSystem.getNodeSegments=function()return nil end',
 'api.engine.util.proposal.createProposalRemove=function()return {constructionsToRemove={320,99},streetProposal={}}end',
 'api.engine.util.proposal.createProposalRemove=function()return {constructionsToRemove={320},streetProposal={edgesToRemove={90003}}}end',
])
def test_invalid_or_unknown_dependencies_never_dispatch(tmp_path,change):
    c=Channel(tmp_path,FIXTURE);c.lua.execute(change)
    r=c.query('preview_depot_removal',{'entity':320})
    assert not r['ok'],r
    assert c.lua.globals().dispatches==0
    assert c.state['v']['uiConstruction']['pending'] is None

@pytest.mark.parametrize('change',[
 'components[320][11].params.seed=2',
 'components[90010][9].state=3',
 'components[90010][9].line=400',
 'components[90003][api.type.ComponentType.BASE_EDGE].roadType=999',
 'components[1][5].speedup=1',
])
def test_changed_state_consumes_token_without_dispatch(tmp_path,change):
    c=Channel(tmp_path,FIXTURE);token=preview(c);c.lua.execute(change)
    assert not commit(c,token)['ok']
    assert not commit(c,token)['ok']
    assert c.lua.globals().dispatches==0
    assert c.state['v']['uiConstruction']['pending'] is None

def test_expiry_session_and_quota_reset_invalidate(tmp_path):
    c=Channel(tmp_path,FIXTURE);token=preview(c)
    assert not commit(c,token,epoch='other-session')['ok']
    token=preview(c)
    l=c.state['v']['uiConstruction'];l['depotRemovalPreviews'][token]['clock']=-1000
    assert not commit(c,token)['ok']
    token=preview(c)
    q=c.query('get_validation_state',{})['result']['operationQuota']
    r=c.query('reset_operation_quota',{'expected_round':q['round'],'expected_used':q['used'],'expected_count':q['activeRequestCount']})
    assert r['ok'],r
    assert not commit(c,token)['ok'] and c.lua.globals().dispatches==0

@pytest.mark.parametrize('fault',['DELAY','THROW','PARTIAL','LOST_VEHICLE','REJECT','LEFT_NODE'])
def test_unknown_or_partial_retains_block_read_only_recovery(tmp_path,fault):
    c=Channel(tmp_path,FIXTURE);token=preview(c);c.lua.execute(f'{fault}=true')
    r=commit(c,token)
    assert not r['ok'] if fault=='THROW' else not r['result']['verified']
    assert c.state['v']['uiConstruction']['pending']
    assert not commit(c,token)['ok']
    assert not c.query('preview_depot_removal',{'entity':320})['ok']
    # Serialize persistent state, then read through a new Lua script instance.
    codec=c.game.script['_internal']['json']
    c.state['v']=codec['decode'](codec['encode'](c.state['v']))
    assert not read(c,token,epoch='new-session')['ok']
    assert not read(c,token)['result']['verified']
    if fault=='DELAY':
        c.lua.execute('DELIVER()')
        assert read(c,token)['result']['verified']
        assert c.state['v']['uiConstruction']['pending'] is None
    else:assert c.state['v']['uiConstruction']['pending']
    assert c.lua.globals().dispatches==1

def test_protocol_validation_and_legacy_stays_disabled():
    for command,args in [('preview_depot_removal',{'entity':300}),
                         ('commit_depot_removal',{'preview_token':'x','backup_save':'test'}),
                         ('get_depot_removal_operation',{'operation_id':'x'})]:
        assert validate_build_arguments(command,args)==args
    with pytest.raises(ValueError):validate_build_arguments('commit_depot_removal',{'preview_token':'x'})
    client=HeadlessClient(Mock());client.status=AsyncMock(return_value={'receiver':{'session':'test'}})
    with pytest.raises(ValueError,match='not implemented'):asyncio.run(client.call('bulldoze',{'entity':300}))
    client.requests.send.assert_not_called()


@pytest.mark.parametrize('command,args',[
    ('preview_depot_removal', {'entity':300}),
    ('commit_depot_removal', {'preview_token':'x','backup_save':'backup'}),
    ('get_depot_removal_operation', {'operation_id':'x'}),
])
def test_old_receiver_rejected_without_publication(host, command, args):
    with pytest.raises(ValueError, match='lacks depot removal'):
        host.send(command, args, kind='build', expected_session='session')
    assert not host.ledger.exists()
    assert (host.mod/'headless'/GEN/'1.lua').read_bytes()==b'return ""\n'


@pytest.mark.parametrize('fault',[None,'missing','unverified','session','generation','changed','stale','future','proof_missing','wrong_kind'])
def test_backup_proof_required_before_publication(host, fault):
    host.log.write_text(TAG+json.dumps(dict(generation=GEN,session='session',slot=1,
        status='ready',utc=100,clock=10,due=12,depotRemovalVersion=1))+'\n')
    path=host._save_path('backup');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(b'known stable save')
    record=dict(kind='save',slot=0,created=99,saveSlot='backup',session='session',generation=GEN,
        response={'result':{'verified':True}},
        saveVerification={'signature':host._signature(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    if fault=='unverified':record['response']['result']['verified']=False
    if fault in ('session','generation'):record[fault]='wrong'
    if fault=='changed':path.write_bytes(b'changed')
    if fault=='stale':record['created']=-1000
    if fault=='future':record['created']=101
    if fault=='proof_missing':record.pop('saveVerification')
    if fault=='wrong_kind':record['kind']='build'
    ledger=host._load()
    if fault!='missing':ledger['requests']['backup']=record
    host._save(ledger)
    args={'preview_token':'x','backup_save':'backup'}
    if fault:
        with pytest.raises(ValueError):host.send('commit_depot_removal',args,kind='build',expected_session='session')
        assert host._load().get('pending') is None
        assert (host.mod/'headless'/GEN/'1.lua').read_bytes()==b'return ""\n'
    else:
        assert host.send('commit_depot_removal',args,kind='build',expected_session='session')['status']=='published'


@pytest.mark.parametrize('fault',[None,'old_receiver','pending','backup','backup_error','commit_error'])
def test_public_tool_backup_then_single_commit(monkeypatch,fault):
    from tf3_mcp import server
    client=Mock();client.status=AsyncMock(return_value={'receiver':{'depotRemovalVersion':0 if fault=='old_receiver' else 1},'pending':'x' if fault=='pending' else None})
    monkeypatch.setattr(server,'transport_mode',lambda:'headless')
    monkeypatch.setattr(server,'headless_client',lambda:client)
    calls=[]
    async def call(cmd,**kwargs):
        calls.append((cmd,kwargs))
        if cmd=='save_game':
            if fault=='backup_error':raise ValueError('save unknown')
            return {'verified':fault!='backup'}
        if fault=='commit_error':raise ValueError('unknown outcome')
        return {'verified':True}
    monkeypatch.setattr(server,'_call',call)
    if fault:
        with pytest.raises(Exception):asyncio.run(server.commit_depot_removal('token'))
    else:assert asyncio.run(server.commit_depot_removal('token'))['verified']
    if fault in ('old_receiver','pending'):assert calls==[]
    else:
        assert calls[0][0]=='save_game' and calls[0][1]['overwrite'] is False
        if fault in (None,'commit_error'):
            assert len(calls)==2 and calls[1]==('commit_depot_removal',{'preview_token':'token','backup_save':calls[0][1]['slot']})
        else:assert len(calls)==1

BOUNDARY = r'''
local C=api.type.ComponentType
C.BASE_NODE_CONFIG=C.BASE_NODE_CONFIG or 91001
local cfg={laneConnections={
 {segment0=90002,segment1=90003,lane0=1,lane1=2,withRoad=true,withTram=false},
 {segment0=90003,segment1=90002,lane0=1,lane1=2,withRoad=true,withTram=false},
 {segment0=90003,segment1=90004,lane0=1,lane1=2,withRoad=true,withTram=false}},
 crosswalks={90002,90003},trafficLightPreference=2,doubleSlipSwitch=false,
 userModifiedTrafficLightStates=false,trafficLightConfig={trafficLightType=-1,states={}}}
components[90001][C.BASE_NODE_CONFIG]=cfg
local native=api.engine.util.proposal.createProposalRemove
api.engine.util.proposal.createProposalRemove=function(e)
 local p=native(e)
 local c=components[90001][C.BASE_NODE_CONFIG]
 local after={laneConnections={},crosswalks={},trafficLightPreference=c.trafficLightPreference,
 doubleSlipSwitch=c.doubleSlipSwitch,userModifiedTrafficLightStates=c.userModifiedTrafficLightStates,
 trafficLightConfig=c.trafficLightConfig}
 for _,v in ipairs(c.laneConnections) do if v.segment0~=90002 and v.segment1~=90002 then after.laneConnections[#after.laneConnections+1]=v end end
 for _,v in ipairs(c.crosswalks) do if v~=90002 then after.crosswalks[#after.crosswalks+1]=v end end
 p.proposal.nodeConfigsToRemove={90001};p.proposal.nodeConfigsToAdd={{entity=90001,comp=after}}
 return p
end
local make=api.cmd.makeWorldBuildProposalCmd
api.cmd.makeWorldBuildProposalCmd=function(p,...)
 local cmd=make(p,...);cmd.boundary=p.proposal.nodeConfigsToAdd;return cmd
end
local send=api.cmd.sendCommand
api.cmd.sendCommand=function(cmd,cb)
 send(cmd,cb)
 if cmd.kind=='build' and not SKIP_CONFIG then
  for _,r in ipairs(cmd.boundary) do components[r.entity][C.BASE_NODE_CONFIG]=r.comp end
 end
 if BAD_CONFIG_READBACK then components[90001][C.BASE_NODE_CONFIG].doubleSlipSwitch=true end
end
'''


def test_boundary_cleanup_preserves_main_road_turns_and_config(tmp_path):
    c=Channel(tmp_path,FIXTURE+BOUNDARY)
    token=preview(c)
    result=commit(c,token)
    assert result['ok'] and result['result']['verified'],result
    config=c.lua.globals().components[90001][c.lua.globals().api.type.ComponentType.BASE_NODE_CONFIG]
    assert len(config.laneConnections)==1 and config.laneConnections[1].segment0==90003
    assert len(config.crosswalks)==1 and config.crosswalks[1]==90003


@pytest.mark.parametrize('edit',[
 'p.proposal.nodeConfigsToAdd[1].comp.laneConnections={}',
 'p.proposal.nodeConfigsToAdd[1].comp.crosswalks={}',
 'p.proposal.nodeConfigsToAdd[1].comp.trafficLightPreference=1',
 'p.proposal.nodeConfigsToAdd[1].comp.doubleSlipSwitch=true',
 'p.proposal.nodeConfigsToAdd[1].comp.userModifiedTrafficLightStates=true',
 'p.proposal.nodeConfigsToAdd[1].comp.trafficLightConfig={trafficLightType=7,states={}}',
 'p.proposal.nodeConfigsToAdd[1].comp.userModifiedLaneConnections=true',
 'p.proposal.nodeConfigsToAdd[1].comp.laneConnections[2]={segment0=90002,segment1=90003}',
 'p.proposal.nodeConfigsToAdd[1].entity=999',
 'p.proposal.nodeConfigsToRemove={90001,90001}',
 'p.proposal.nodeConfigsToAdd[2]=p.proposal.nodeConfigsToAdd[1]',
 'p.proposal.nodeConfigsToRemove={}',
 'p.proposal.nodeConfigsToAdd={}',
 'p.proposal.nodeConfigsToAdd={};p.proposal.nodeConfigsToRemove={}',
])
def test_boundary_cleanup_rejects_unrelated_or_incomplete_change(tmp_path,edit):
    c=Channel(tmp_path,FIXTURE+BOUNDARY)
    c.lua.execute('local old=api.engine.util.proposal.createProposalRemove;api.engine.util.proposal.createProposalRemove=function(e)local p=old(e);'+edit+';return p end')
    result=c.query('preview_depot_removal',{'entity':300})
    assert not result['ok'],result
    assert c.lua.globals().dispatches==0


def test_boundary_signal_phases_refused_without_index_remapping(tmp_path):
    c=Channel(tmp_path,FIXTURE+BOUNDARY)
    c.lua.execute('components[90001][api.type.ComponentType.BASE_NODE_CONFIG].trafficLightConfig.states={{lockedLanes={0},duration=10,minDuration=1,canSkip=false}}')
    result=c.query('preview_depot_removal',{'entity':300})
    assert not result['ok'] and 'signal phases' in result['error'],result
    assert c.lua.globals().dispatches==0


@pytest.mark.parametrize('fault',['SKIP_CONFIG','BAD_CONFIG_READBACK'])
def test_boundary_cleanup_readback_failure_retains_pending(tmp_path,fault):
    c=Channel(tmp_path,FIXTURE+BOUNDARY)
    token=preview(c)
    c.lua.globals()[fault]=True
    result=commit(c,token)
    assert result['ok'] and not result['result']['verified'],result
    assert 'external_node_config_changed:90001' in list(result['result']['issues'])
    assert c.state['v']['uiConstruction']['pending']
    assert not read(c,token)['result']['verified']
    assert c.lua.globals().dispatches==1


def test_boundary_config_change_between_preview_and_commit(tmp_path):
    c=Channel(tmp_path,FIXTURE+BOUNDARY)
    token=preview(c)
    c.lua.execute('components[90001][api.type.ComponentType.BASE_NODE_CONFIG].trafficLightPreference=0')
    result=commit(c,token)
    assert not result['ok'] and 'state changed' in result['error'],result
    assert c.lua.globals().dispatches==0


def test_boundary_native_userdata_config(tmp_path):
    c=Channel(tmp_path,FIXTURE+BOUNDARY)
    ct=c.lua.globals().api.type.ComponentType
    cfg=c.lua.globals().components[90001][ct.BASE_NODE_CONFIG]
    native=NativeRecord({})
    native.data=dict(cfg.items())
    native.data['trafficLightConfig']=NativeRecord({})
    native.data['trafficLightConfig'].data=dict(cfg.trafficLightConfig.items())
    c.lua.globals().components[90001][ct.BASE_NODE_CONFIG]=native
    token=preview(c)
    result=commit(c,token)
    assert result['ok'] and result['result']['verified'],result
