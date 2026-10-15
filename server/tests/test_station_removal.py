"""Station removal guards; mocked native API, not live acceptance."""
import asyncio
import hashlib
from unittest.mock import AsyncMock, Mock
import json
import pytest
from test_ui_consolidated import Channel
from test_depot_removal import FIXTURE as DEPOT, host, GEN, TAG

FIXTURE=DEPOT+r'''
local C=api.type.ComponentType
C.STOCK_LIST=C.STOCK_LIST or 92001
components[320][C.CONSTRUCTION].fileName='::/stations/street/modular_street_station/modular_terminal.con'
components[320][C.CONSTRUCTION].depots={}
components[320][C.CONSTRUCTION].stations={300}
components[300][C.VEHICLE_DEPOT]=nil
components[300][C.STATION]={terminals={{cargoUnload=true,passengersLoad=false,passengersUnload=false}}}
components[390]={[C.STATION_GROUP]={stations={300}}}
components[90010][C.TRANSPORT_VEHICLE].depot=301
api.engine.system.stationGroupSystem={getStationGroup=function(id)return 390 end}
api.engine.system.streetConnectorSystem.getConstructionEntityForStation=function(id)return 320 end
api.engine.system.transportVehicleSystem.getVehicles=function(ids,whole)return {} end
api.engine.system.simPersonSystem={getSimPersonsAtTerminalForTransportNetwork=function(id)return {} end}
api.engine.system.simEntityAtStockSystem={getStockCount=function(id,i)return 0 end}
local send=api.cmd.sendCommand
api.cmd.sendCommand=function(cmd,cb)
 send(cmd,cb)
 if LEFT_STATION and cmd.kind=='build' then components[300]={[C.STATION]={}} end
 if cmd.kind=='build' and not DELAY and not REJECT and not THROW and not LEFT_STATION then components[300]=nil end
end
'''

def preview(c):
 r=c.query('preview_station_removal',{'entity':320});assert r['ok'],r
 assert r['result']['nativePreview'] is False
 return r['result']['preview_token']
def commit(c,t):return c.query('commit_station_removal',{'preview_token':t,'backup_save':'verified_test_backup'})

def test_station_success_no_replay(tmp_path):
 c=Channel(tmp_path,FIXTURE);t=preview(c);r=commit(c,t);assert r['ok'] and r['result']['verified'],r
 assert c.lua.globals().components[90003] is not None
 assert c.query('get_station_removal_operation',{'operation_id':t})['result']['verified']
 assert not commit(c,t)['ok'];assert c.lua.globals().dispatches==1

@pytest.mark.parametrize('edit',[
 'components[300][C.PLAYER_OWNED].player=99',
 'components[320][C.CONSTRUCTION].fileName="other.con"',
 'components[320][C.CONSTRUCTION].depots={301}',
 'components[390][C.STATION_GROUP].stations={300,211}',
 'components[300][C.STATION].terminals[1].passengersLoad=true',
 'components[401][C.LINE].stops={{stationGroup=390}}',
 'api.engine.system.transportVehicleSystem.getVehicles=function()return {90010} end',
 'api.engine.system.transportVehicleSystem.getVehicles=function()return nil end',
 'api.engine.system.simPersonSystem.getSimPersonsAtTerminalForTransportNetwork=function()return {77} end',
 'components[300][C.STOCK_LIST]={stocks={{}}};api.engine.system.simEntityAtStockSystem.getStockCount=function()return 1 end',
 'components[320][C.CONSTRUCTION].subconstructions={300,320}',
 'components[1][C.GAME_SPEED].speedup=1',
 'local old=api.engine.util.proposal.createProposalRemove;api.engine.util.proposal.createProposalRemove=function(e)local p=old(e);p.proposal.removedSegments={{entity=90003}};return p end',
])
def test_refuses_dependencies_and_external_removal(tmp_path,edit):
 c=Channel(tmp_path,FIXTURE);c.lua.execute('local C=api.type.ComponentType;'+edit)
 r=c.query('preview_station_removal',{'entity':320});assert not r['ok'],r
 assert c.lua.globals().dispatches==0

@pytest.mark.parametrize('edit',[
 'components[401][C.LINE].stops={{stationGroup=390}}',
 'components[390][C.STATION_GROUP].stations={300,211}',
 'components[90003][C.BASE_EDGE].node1=123',
 'components[300][C.STATION].terminals[1].capacity=99',
])
def test_revalidates_before_submit(tmp_path,edit):
 c=Channel(tmp_path,FIXTURE);t=preview(c);c.lua.execute('local C=api.type.ComponentType;'+edit)
 assert not commit(c,t)['ok'];assert c.lua.globals().dispatches==0

@pytest.mark.parametrize('fault',['LEFT_STATION','PARTIAL','LOST_VEHICLE','REJECT','THROW'])
def test_unknown_or_partial_keeps_pending(tmp_path,fault):
 c=Channel(tmp_path,FIXTURE);t=preview(c);c.lua.globals()[fault]=True;r=commit(c,t)
 assert not r['ok'] or not r['result']['verified'],r
 assert c.state['v']['uiConstruction']['pending']
 assert not commit(c,t)['ok'];assert c.lua.globals().dispatches==1

@pytest.mark.parametrize('command,args',[
 ('preview_station_removal',{'entity':320}),('commit_station_removal',{'preview_token':'x','backup_save':'backup'}),('get_station_removal_operation',{'operation_id':'x'})])
def test_old_receiver_refused(host,command,args):
 with pytest.raises(ValueError,match='lacks station removal'):host.send(command,args,kind='build',expected_session='session')
 assert not host.ledger.exists()

@pytest.mark.parametrize('fault',[None,'missing','unverified','session','generation','changed','stale','future','proof_missing','wrong_kind'])
def test_backup_proof_required_before_publication(host, fault):
    host.log.write_text(TAG+json.dumps(dict(generation=GEN,session='session',slot=1,
        status='ready',utc=100,clock=10,due=12,stationRemovalVersion=1))+'\n')
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
        with pytest.raises(ValueError):host.send('commit_station_removal',args,kind='build',expected_session='session')
        assert host._load().get('pending') is None
        assert (host.mod/'headless'/GEN/'1.lua').read_bytes()==b'return ""\n'
    else:
        assert host.send('commit_station_removal',args,kind='build',expected_session='session')['status']=='published'


@pytest.mark.parametrize('fault',[None,'old_receiver','pending','backup','backup_error','commit_error'])
def test_public_tool_backup_then_single_commit(monkeypatch,fault):
    from tf3_mcp import server
    client=Mock();client.status=AsyncMock(return_value={'receiver':{'stationRemovalVersion':0 if fault=='old_receiver' else 1},'pending':'x' if fault=='pending' else None})
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
        with pytest.raises(Exception):asyncio.run(server.commit_station_removal('token'))
    else:assert asyncio.run(server.commit_station_removal('token'))['verified']
    if fault in ('old_receiver','pending'):assert calls==[]
    else:
        assert calls[0][0]=='save_game' and calls[0][1]['overwrite'] is False
        if fault in (None,'commit_error'):
            assert len(calls)==2 and calls[1]==('commit_station_removal',{'preview_token':'token','backup_save':calls[0][1]['slot']})
        else:assert len(calls)==1

def test_native_station_userdata_fingerprint(tmp_path):
 from test_depot_removal import NativeRecord
 c=Channel(tmp_path,FIXTURE);ct=c.lua.globals().api.type.ComponentType
 st=c.lua.globals().components[300][ct.STATION]
 native=NativeRecord({});native.data=dict(st.items());native.data.update(tag=0,catchmentAreas=c.lua.table(),pool=c.lua.table())
 c.lua.globals().components[300][ct.STATION]=native
 t=preview(c);native.data['tag']=99
 assert not commit(c,t)['ok'];assert c.lua.globals().dispatches==0

def test_delayed_commit_reconciles_once(tmp_path):
 c=Channel(tmp_path,FIXTURE);t=preview(c);c.lua.globals().DELAY=True
 r=commit(c,t);assert r['ok'] and not r['result']['verified']
 c.lua.execute('DELIVER()')
 r=c.query('get_station_removal_operation',{'operation_id':t});assert r['ok'] and r['result']['verified'],r
 assert c.lua.globals().dispatches==1

def test_line_readback_change_keeps_pending(tmp_path):
 c=Channel(tmp_path,FIXTURE+r'''
 local old=api.cmd.sendCommand
 api.cmd.sendCommand=function(cmd,cb)old(cmd,cb);if cmd.kind=='build' then components[401][api.type.ComponentType.LINE].reservationPriority=99 end end
 ''');t=preview(c);r=commit(c,t)
 assert r['ok'] and not r['result']['verified'],r
 assert c.state['v']['uiConstruction']['pending']

def test_native_terminal_edge_id_variant_preserves_identity(tmp_path):
 from test_depot_removal import NativeRecord
 c=Channel(tmp_path,FIXTURE);ct=c.lua.globals().api.type.ComponentType
 edge=NativeRecord({'entity':320,'index':1})
 c.lua.globals().components[300][ct.STATION].terminals[1]['vehicleEdges']=c.lua.table_from([edge])
 t=preview(c);edge.data['index']=2
 assert not commit(c,t)['ok'];assert c.lua.globals().dispatches==0

@pytest.mark.parametrize('fields',[{'entity':320},{'entity':320,'index':-1},{'param':0.5,'entity':320,'index':1}])
def test_unreadable_or_partial_edge_position_stays_blocked(tmp_path,fields):
 from test_depot_removal import NativeRecord
 c=Channel(tmp_path,FIXTURE);ct=c.lua.globals().api.type.ComponentType
 c.lua.globals().components[300][ct.STATION].terminals[1]['vehicleEdges']=c.lua.table_from([NativeRecord(fields)])
 assert not c.query('preview_station_removal',{'entity':320})['ok']
 assert c.lua.globals().dispatches==0
