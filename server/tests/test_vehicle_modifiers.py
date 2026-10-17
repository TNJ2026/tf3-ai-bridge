"""Native source/event lifecycle mocks; not a live-game acceptance claim."""
import pytest
from test_ui_consolidated import Channel
from test_no_gui import host
from tf3_mcp.ui_log import validate_build_arguments

FIXTURE = '''
local CT=api.type.ComponentType
CT.GAME_SCRIPT='GAME_SCRIPT'
components[1][CT.GAME_SPEED].speedup=0
components[9000]={[CT.PLAYER_OWNED]={player=2},[CT.TRANSPORT_VEHICLE]={
 transportVehicleConfig={vehicles={}},modifiers={topSpeedScale=1.2,noiseScale=1,pollutionScale=1,comfortScale=1}}}
components[9100]={[CT.GAME_SCRIPT]={state={modificationMap={[9000]={landmark={TopSpeed=1.2}}}}}}
api.engine.system.gameScriptSystem={getEntityForGameScript=function(name)
 assert(name=='::/vehicle/vehicle_modifier.gs');return 9100 end}
api.cmd.makeScriptingSendEventCmd=function(src,id,name,param)
 assert(id=='VehicleModifier' and name=='ChangeModifier');return {modifier=param} end
function APPLY(cmd)
 local p=cmd.modifier;local map=components[9100][CT.GAME_SCRIPT].state.modificationMap
 map[p.entity]=map[p.entity] or {};map[p.entity][p.id]=next(p.modifications) and p.modifications or nil
 if SOURCE_ONLY then return end
 local out={TopSpeed=1,Noise=1,Pollution=1,Comfort=1}
 for _,mods in pairs(map[p.entity])do for k,v in pairs(mods)do out[k]=out[k]+v-1 end end
 components[p.entity][CT.TRANSPORT_VEHICLE].modifiers={topSpeedScale=out.TopSpeed,noiseScale=out.Noise,pollutionScale=out.Pollution,comfortScale=out.Comfort}
end
api.cmd.sendCommand=function(cmd,cb)
 if THROW then error('dispatch unknown') end
 if DELAY then PENDING=cmd;return end
 APPLY(cmd);if cb then cb({},true) end
end
'''

def preview(c, **args):
    r = c.query('preview_vehicle_modifiers', dict(vehicle=9000, **args))
    assert r['ok'], r
    return r['result']['preview_token']

def commit(c, token):
    return c.query('commit_vehicle_modifiers', dict(preview_token=token, backup_save='modifier_test'))

def read_op(c, token):
    return c.query('get_vehicle_modifier_operation', {'operation_id': token})

def test_apply_preserve_reset_and_single_use(tmp_path):
    c=Channel(tmp_path,FIXTURE)
    token=preview(c,top_speed=1.5,noise=.8)
    r=commit(c,token);assert r['ok'],r
    assert not r['result']['verified']  # submission never claims nested completion
    r=read_op(c,token);assert r['ok'],r
    assert r['result']['verified']
    assert r['result']['observed']['effective']['TopSpeed']==pytest.approx(1.7)
    assert r['result']['observed']['sources']['landmark']['TopSpeed']==1.2
    assert not commit(c,token)['ok']
    assert c.lua.globals().dispatches==1
    token=preview(c,comfort=1.4)
    assert commit(c,token)['ok']
    r=read_op(c,token)['result'];assert r['verified']
    assert r['desired']['TopSpeed']==1.5
    token=preview(c,reset=True);assert commit(c,token)['ok']
    r=read_op(c,token)['result'];assert r['verified']
    assert r['observed']['effective']['TopSpeed']==pytest.approx(1.2)

@pytest.mark.parametrize('mode',['DELAY','THROW','SOURCE_ONLY'])
def test_unknown_blocks_writes_and_readback_resolves_only_effective(tmp_path,mode):
    c=Channel(tmp_path,FIXTURE)
    token=preview(c,top_speed=1.5)
    c.lua.globals()[mode]=True
    r=commit(c,token);assert r['ok'],r
    assert not read_op(c,token)['result']['verified']
    assert c.state['v']['uiConstruction']['pending']
    assert not c.query('preview_vehicle_modifiers',dict(vehicle=9000,top_speed=2))['ok']
    assert not commit(c,token)['ok']
    assert c.lua.globals().dispatches==1
    if mode=='DELAY':
        c.lua.execute('APPLY(PENDING)')
        assert read_op(c,token)['result']['verified']
        assert c.state['v']['uiConstruction']['pending'] is None

@pytest.mark.parametrize('setup',[
 'components[9000][api.type.ComponentType.PLAYER_OWNED].player=3',
 'components[9000][api.type.ComponentType.TRANSPORT_VEHICLE].modifiers.topSpeedScale=2',
 'components[9100][api.type.ComponentType.GAME_SCRIPT].state=nil',
 'components[1][api.type.ComponentType.GAME_SPEED].speedup=1'])
def test_preflight_rejects(tmp_path,setup):
    c=Channel(tmp_path,FIXTURE+setup)
    assert not c.query('preview_vehicle_modifiers',dict(vehicle=9000,top_speed=1.5))['ok']
    assert c.lua.globals().dispatches==0

def test_changed_sources_refuse_and_consume_token(tmp_path):
    c=Channel(tmp_path,FIXTURE);token=preview(c,top_speed=1.5)
    c.lua.execute('components[9100][api.type.ComponentType.GAME_SCRIPT].state.modificationMap[9000].landmark.TopSpeed=1.3')
    assert not commit(c,token)['ok']
    assert not commit(c,token)['ok']
    assert c.lua.globals().dispatches==0

@pytest.mark.parametrize('args',[{}, {'top_speed':0},{'noise':-1},{'comfort':11}, {'pollution':True}, {'noise':float('nan')}, {'top_speed':float('inf')},{'reset':True,'noise':1}])
def test_validation(args):
    with pytest.raises(ValueError):
        validate_build_arguments('preview_vehicle_modifiers',dict(vehicle=1,**args))

def test_old_receiver_blocked(host):
    with pytest.raises(ValueError,match='vehicleModifiersVersion'):
        host.send('preview_vehicle_modifiers',dict(vehicle=1,top_speed=1.5),kind='build',expected_session='session')
    assert not host.ledger.exists()


def test_fresh_native_state_and_noop(tmp_path):
    c=Channel(tmp_path,FIXTURE+'''
components[9100][api.type.ComponentType.GAME_SCRIPT].state={}
components[9000][api.type.ComponentType.TRANSPORT_VEHICLE].modifiers.topSpeedScale=1
''')
    token=preview(c,reset=True)
    assert commit(c,token)['result']['verified']
    assert c.lua.globals().dispatches==0


def test_session_change_rejected(tmp_path):
    c=Channel(tmp_path,FIXTURE);token=preview(c,top_speed=1.5)
    r=c.query('commit_vehicle_modifiers',dict(preview_token=token,backup_save='modifier_test'),epoch='other-session')
    assert not r['ok'] and c.lua.globals().dispatches==0


def test_source_only_update_cannot_be_reconciled_by_aggregate_alone(tmp_path):
    c=Channel(tmp_path,FIXTURE);token=preview(c,top_speed=1.5)
    c.lua.globals().DELAY=True
    assert commit(c,token)['ok']
    c.lua.execute('components[9000][api.type.ComponentType.TRANSPORT_VEHICLE].modifiers.topSpeedScale=1.7')
    assert not read_op(c,token)['result']['verified']


def test_backup_evidence_required(host):
    import json
    from tf3_mcp.no_gui import TAG
    from test_no_gui import GEN
    # Advertise only the capability; no verified save exists in the host ledger.
    row=dict(generation=GEN,session='session',slot=1,status='ready',utc=100,clock=10,due=12,vehicleModifiersVersion=1)
    host.log.write_text(TAG+json.dumps(row)+'\n')
    with pytest.raises(ValueError,match='Verified current-session backup'):
        host.send('commit_vehicle_modifiers',dict(preview_token='abc',backup_save='test'),kind='build',expected_session='session')
    assert not host.ledger.exists()


def test_expired_token_refuses_dispatch(tmp_path):
    c=Channel(tmp_path,FIXTURE);token=preview(c,top_speed=1.5)
    row=c.state['v']['uiConstruction']['modifierPreviews'][token]
    row['created']=row['created']-61
    assert not commit(c,token)['ok']
    assert c.lua.globals().dispatches==0


@pytest.mark.parametrize('failure',[None,'backup','old_receiver'])
def test_mcp_backup_commit_read_order(tmp_path,monkeypatch,failure):
    import asyncio
    from types import SimpleNamespace
    from tf3_mcp import server
    calls=[]
    class Client:
        requests=SimpleNamespace(directory=tmp_path)
        async def status(self):
            return {'receiver':{'vehicleModifiersVersion':0 if failure=='old_receiver' else 1}}
        async def call(self,cmd,args):
            calls.append(cmd)
            if cmd=='save_game': return {'verified':failure!='backup'}
            if cmd=='commit_vehicle_modifiers': return {'operation_id':'token','verified':False}
            assert cmd=='get_vehicle_modifier_operation'
            return {'operation_id':'token','verified':True}
    monkeypatch.setattr(server,'transport_mode',lambda:'no_gui')
    monkeypatch.setattr(server,'no_gui_client',lambda:Client())
    if failure:
        with pytest.raises(Exception): asyncio.run(server.commit_vehicle_modifiers('token'))
        assert calls==([] if failure=='old_receiver' else ['save_game'])
    else:
        assert asyncio.run(server.commit_vehicle_modifiers('token'))['verified']
        assert calls==['save_game','commit_vehicle_modifiers','get_vehicle_modifier_operation']
