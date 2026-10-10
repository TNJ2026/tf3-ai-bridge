"""Exercise opaque native records across separate engine Lua module instances."""
import json
import pytest
from test_ui_consolidated import Channel, NETWORK_FIXTURE


class NativeRecord:
    # Lupa exposes Python objects as userdata: fields work, pairs() is unavailable,
    # and a newly returned wrapper has a different identity/address.
    def __init__(self, **fields):
        self.fields = fields

    def __getitem__(self, key):
        return self.fields[key]


def setup_native_lanes(c):
    c.lua.globals().native_lane = lambda: NativeRecord(
        speed=20, width=3, height=0, forward=True, offset=1.5,
        transportModes=c.lua.table_from({2: True, 3: True, 4: True}))
    c.lua.execute('''
      local get=api.res.streetTemplateRep.get
      api.res.streetTemplateRep.get=function(id)
       local t=get(id);t.laneConfigs={native_lane()};return t
      end
    ''')


ARGS = {'start': {'x':700,'y':700}, 'via':[{'x':750,'y':710}],
        'end':{'x':800,'y':700}, 'template':'town/town_old_small'}


def test_native_lane_wrappers_compare_values_across_engine_instances(tmp_path):
    c=Channel(tmp_path, NETWORK_FIXTURE);setup_native_lanes(c)
    assert c.lua.eval('type(native_lane())')=='userdata'
    p=c.query('preview_network',ARGS);assert p['ok'],p
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert r['ok'] and r['result']['verified'],r
    assert c.lua.globals().dispatches==1
    assert not c.state['v']['uiConstruction']['pending']


@pytest.mark.parametrize('field,value', [('speed',21),('width',4),('height',.1),
                                        ('forward',False),('offset',2),('transportModes',{})])
def test_native_lane_changes_still_refuse_before_dispatch(tmp_path,field,value):
    c=Channel(tmp_path, NETWORK_FIXTURE);setup_native_lanes(c)
    old=c.lua.globals().native_lane
    p=c.query('preview_network',ARGS);assert p['ok'],p
    def changed():
        lane=old();lane.fields[field]=c.lua.table_from(value) if isinstance(value,dict) else value
        return lane
    c.lua.globals().native_lane=changed
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert not r['ok'] and r['error'].endswith('Network endpoints or template changed'),r
    assert c.lua.globals().dispatches==0
    assert c.state['v']['uiConstruction']['pending']==r['id']
    reconciled=c.query('reconcile_network_rejection',{'request_id':r['id']})
    assert reconciled['ok'] and not reconciled['result']['mutationAttempted'],reconciled
    assert not c.state['v']['uiConstruction']['pending']
    assert not c.query('reconcile_network_rejection',{'request_id':r['id']})['ok']
    assert not c.query('commit_network',{'preview_token':p['result']['preview_token']})['ok']
    assert c.lua.globals().dispatches==0


@pytest.mark.parametrize('change',['native_error','wrong_id','wrong_cmd','missing','duplicate','different_pending'])
def test_network_reconciliation_requires_exact_persisted_proof(tmp_path,change):
    c=Channel(tmp_path, NETWORK_FIXTURE);setup_native_lanes(c)
    p=c.query('preview_network',ARGS)
    c.lua.execute('api.engine.terrain.getHeightAt=function()return 1 end')
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert not r['ok'] and r['error'].endswith('Network endpoints or template changed'),r
    ledger=c.state['v']['uiConstruction'];responses=c.state['v']['responses']
    row=next(x for x in responses.values() if x['id']==r['id'])
    proof=json.loads(row['text'])
    if change=='native_error':proof['error']='native outcome unknown'
    elif change=='wrong_id':proof['id']='0'*32
    elif change=='wrong_cmd':proof['cmd']='commit_facility'
    elif change=='missing':
        row['id']='0'*32;ledger['requests'][r['id']]['error']=None
    elif change=='duplicate':responses[len(responses)+1]=c.lua.table_from({'id':r['id'],'text':row['text']})
    elif change=='different_pending':ledger['pending']='0'*32
    row['text']=json.dumps(proof)
    pending=ledger['pending']
    result=c.query('reconcile_network_rejection',{'request_id':r['id']})
    assert not result['ok'] and ledger['pending']==pending,result
    assert c.lua.globals().dispatches==0


@pytest.mark.parametrize('field', ['speed','width','height','forward','offset','transportModes'])
def test_incomplete_native_lane_cannot_issue_a_preview_token(tmp_path,field):
    c=Channel(tmp_path, NETWORK_FIXTURE);setup_native_lanes(c)
    old=c.lua.globals().native_lane
    def incomplete():
        lane=old();del lane.fields[field];return lane
    c.lua.globals().native_lane=incomplete
    r=c.query('preview_network',ARGS)
    assert not r['ok'] and 'unreadable native data' in r['error'],r
    assert ' at $.' in r['error'] and field in r['error'],r
    assert c.lua.globals().dispatches==0
    assert not c.state['v']['uiConstruction']['pending']


def test_rejection_survives_response_eviction_and_new_engine_epoch(tmp_path):
    c=Channel(tmp_path, NETWORK_FIXTURE);setup_native_lanes(c)
    p=c.query('preview_network',ARGS)
    c.lua.execute('api.engine.terrain.getHeightAt=function()return 1 end')
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert not r['ok']
    for _ in range(12):assert c.query('get_terrain',{'x':0,'y':0})['ok']
    assert all(v['id']!=r['id'] for v in c.state['v']['responses'].values())
    receipt=c.query('reconcile_network_rejection',{'request_id':r['id']},epoch='after-reload')
    assert receipt['ok'] and receipt['result']['evidenceSource']=='durable_engine_pre_dispatch_phase'
    assert c.lua.globals().dispatches==0 and not c.state['v']['uiConstruction']['pending']


@pytest.mark.parametrize('mode',['ok','enum_ok','wrong_id','wrong_epoch','wrong_map','wrong_player','unconsumed','unknown_error',
    'addition_exact','addition_opt_in','addition_and_move','addition_and_remove',
    'addition_and_replace','addition_and_town_move','duplicate_industry','duplicate_town','unknown_policy'])
def test_installer_pinned_legacy_receipt_is_bound_and_single_use(tmp_path,monkeypatch,mode):
    import test_ui_consolidated as module
    from network_rejection_recovery import lua_literal
    c=Channel(tmp_path, NETWORK_FIXTURE);setup_native_lanes(c)
    p=c.query('preview_network',ARGS)
    c.lua.execute('api.engine.terrain.getHeightAt=function()return 1 end')
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert not r['ok']
    ledger=c.state['v']['uiConstruction'];ledger['requests'][r['id']]['error']=None
    c.state['v']['responses']=c.lua.table()
    c.state['v']['uiNetworkAdapter']['operations']=None # emulate the legacy saved format
    # The base mock intentionally lacks a map; give this read only a finite map.
    source=module.SCRIPT.read_text(encoding='utf-8')
    source=source.replace('local function stableDataSignature(value)', '''
      commands.get_map_info=function()return {width=1000,height=1000,
       towns={{id=100,name="Town",position={x=0,y=0}}},
       industries={{id=500,fileName="farm",position={x=100,y=100}}}}end
      local function stableDataSignature(value)
    ''',1)
    payload={'id':r['id'],'cmd':'commit_network','ok':False,'error':r['error'],
             'session':c.state['v']['uiNetworkAdapter']['epoch'],'token':p['result']['preview_token'],
             'player':2,'map':{'width':1000,'height':1000,
               'towns':{'100':{'name':'Town','position':{'x':0,'y':0}}},
               'industries':{'500':{'fileName':'farm','position':{'x':100,'y':100}}}}}
    if mode=='enum_ok':
        payload['error']='[string "C:/bridge.script.lua"]:5254: Cannot loop over this component type'
        payload['rejectionKind']='network_edge_enumeration_before_dispatch'
        ledger['requests'][r['id']]['error']=payload['error']
    elif mode=='wrong_id':payload['id']='0'*32
    elif mode=='wrong_epoch':payload['session']='other'
    elif mode=='wrong_map':payload['map']['industries']['500']['position']['x']=101
    elif mode=='wrong_player':payload['player']=99
    elif mode=='unconsumed':ledger['tokens'][payload['token']]='old'
    elif mode=='unknown_error':payload['error']='native failure'
    if mode.startswith('addition_') or mode.startswith('duplicate_'):
        original='industries={{id=500,fileName="farm",position={x=100,y=100}}}'
        replacement='industries={{id=500,fileName="farm",position={x=100,y=100}},{id=501,fileName="mine",position={x=200,y=200}}}'
        if mode != 'addition_exact':payload['identityPolicy']='original_objects_plus_industry_additions'
        if mode=='addition_and_move':replacement=replacement.replace('x=100','x=101')
        elif mode=='addition_and_remove':replacement='industries={{id=501,fileName="mine",position={x=200,y=200}}}'
        elif mode=='addition_and_replace':replacement=replacement.replace('fileName="farm"','fileName="mine"')
        elif mode=='addition_and_town_move':source=source.replace('name="Town",position={x=0,y=0}','name="Town",position={x=1,y=0}')
        elif mode=='duplicate_industry':replacement=replacement.replace('id=501','id=500')
        elif mode=='duplicate_town':source=source.replace('towns={{id=100,name="Town",position={x=0,y=0}}}', 'towns={{id=100,name="Town",position={x=0,y=0}},{id=100,name="Town",position={x=0,y=0}}}')
        assert original in source
        source=source.replace(original,replacement)
    elif mode=='unknown_policy':payload['identityPolicy']='ignore_changes'
    source=source.replace('local NETWORK_REJECTION_MIGRATION = nil','local NETWORK_REJECTION_MIGRATION = '+lua_literal(payload),1)
    path=tmp_path/'migration.lua';path.write_text(source,encoding='utf-8');monkeypatch.setattr(module,'SCRIPT',path)
    result=c.query('reconcile_network_rejection',{'request_id':r['id']},epoch='new-session')
    assert c.lua.globals().dispatches==0
    if mode in ('ok','enum_ok','addition_opt_in'):
        assert result['ok'] and result['result']['evidenceSource']=='installer_pinned_host_receipt',result
        assert not ledger['pending']
        if mode=='addition_opt_in':
            delta=result['result']['identityDelta']
            assert delta['addedIndustries']==[{'id':501,'fileName':'mine','position':{'x':200,'y':200}}]
            assert delta['oldPreviewsReusable'] is False
            assert ledger['requests'][r['id']]['recoveryIdentityDelta']['addedIndustries'][1]['id']==501
        assert not c.query('reconcile_network_rejection',{'request_id':r['id']})['ok']
    else:assert not result['ok'] and ledger['pending']==r['id'],result


@pytest.mark.parametrize('phase',['before','during','after'])
def test_network_phase_journal_never_reconciles_after_dispatch(tmp_path,phase):
    c=Channel(tmp_path, NETWORK_FIXTURE);setup_native_lanes(c)
    p=c.query('preview_network',ARGS);assert p['ok']
    if phase=='before':
        c.lua.execute('api.engine.system.streetSystem.getNode2SegmentMap=function()error("read index unavailable")end')
    else:
        # Reproduce an exception at/after native command entry, including an error
        # that misleadingly ends in a pre-dispatch error's known text.
        c.lua.execute('''
          local send=api.cmd.sendCommand
          api.cmd.sendCommand=function(cmd,cb)
           if cmd.event then forwarded=cmd;return end
           if FAIL_AFTER then send(cmd,cb) end
           error("Network endpoints or template changed")
          end
        ''')
        c.lua.globals().FAIL_AFTER=phase=='after'
    r=c.query('commit_network',{'preview_token':p['result']['preview_token']})
    assert not r['ok']
    ledger=c.state['v']['uiConstruction'];assert ledger['pending']==r['id']
    result=c.query('reconcile_network_rejection',{'request_id':r['id']})
    if phase=='before':
        assert result['ok'] and result['result']['evidenceSource']=='durable_engine_pre_dispatch_phase'
        assert not ledger['pending'] and c.lua.globals().dispatches==0
    else:
        assert not result['ok'] and ledger['pending']==r['id'],result


@pytest.mark.parametrize('mode',['missing_flag','flag_false','flag_true','changed_flag','flag_appears','changed_lanes','changed_crosswalks','changed_signal','missing_lanes','missing_crosswalks','missing_signal'])
def test_node_config_native_missing_documented_flag_only(tmp_path,mode):
    c=Channel(tmp_path)
    ct=c.lua.globals().api.type.ComponentType
    ct['BASE_NODE_CONFIG']=997
    edge=next(entity for entity,cs in c.lua.globals().components.items() if cs[ct.BASE_EDGE] is not None)
    node=c.lua.globals().components[edge][ct.BASE_EDGE]['node0']
    lane=NativeRecord(segment0=edge,segment1=edge,lane0=0,lane1=1,withRoad=True,withTram=False)
    signal=NativeRecord(states=c.lua.table(),trafficLightType=-1)
    cfg=NativeRecord(laneConnections=c.lua.table_from([lane]),crosswalks=c.lua.table_from([edge]),
        trafficLightPreference=2,trafficLightConfig=signal,doubleSlipSwitch=False,userModifiedTrafficLightStates=False)
    if mode in ('flag_false','changed_flag'):cfg.fields['userModifiedLaneConnections']=False
    if mode=='flag_true':cfg.fields['userModifiedLaneConnections']=True
    if mode=='missing_lanes':del cfg.fields['laneConnections']
    if mode=='missing_crosswalks':del cfg.fields['crosswalks']
    if mode=='missing_signal':del signal.fields['trafficLightType']
    c.lua.globals().components[node][ct.BASE_NODE_CONFIG]=cfg
    p=c.query('preview_road_upgrade',{'edge':edge,'street_type':'town/town_old_medium'})
    if mode in ('missing_lanes','missing_crosswalks','missing_signal'):
        assert not p['ok'] and 'unreadable native data at $.a' in p['error'],p
        assert c.lua.globals().dispatches==0
        return
    assert p['ok'],p
    if mode in ('changed_flag','flag_appears'):cfg.fields['userModifiedLaneConnections']=True
    if mode=='changed_lanes':lane.fields['lane1']=2
    if mode=='changed_crosswalks':cfg.fields['crosswalks']=c.lua.table()
    if mode=='changed_signal':signal.fields['trafficLightType']=1
    r=c.query('commit_edge_edit',{'preview_token':p['result']['preview_token']})
    if mode.startswith('changed_') or mode=='flag_appears':
        assert not r['ok'] and c.lua.globals().dispatches==0,r
    else:
        assert r['ok'] and r['result']['verified'],r
        assert c.lua.globals().dispatches==1
