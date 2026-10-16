import hashlib
import json

import pytest

from test_no_gui import GEN, host
from test_no_gui_save import native_channel
from test_warehouses import warehouse_game
from tf3_mcp.no_gui import TAG, NoGuiRequests
from tf3_mcp.ui_log import validate_load_arguments


@pytest.mark.parametrize('args', [None, {}, {'slot':'a'}, {'slot':'a','backup_save':'a'},
    {'slot':'../a','backup_save':'b'}, {'slot':'a','backup_save':'CON'},
    {'slot':'a','backup_save':'b','code':'x'}])
def test_load_arguments(args):
    with pytest.raises(ValueError):validate_load_arguments('load_game', args)


def setup_host(host):
    row=json.loads(host.log.read_text().split(TAG)[1])
    row.update(loadGameVersion=1,loadGameAvailable=True,mode='demand',filename='ssession_1.lua')
    host.log.write_text(TAG+json.dumps(row)+'\n')
    ledger=host._load()
    for slot in ('target','backup'):
        path=host._save_path(slot);path.parent.mkdir(exist_ok=True);path.write_bytes(slot.encode())
        ledger['requests'][slot]=dict(kind='save',saveSlot=slot,session='session',generation=GEN,created=99,slot=0,
            saveVerification=dict(signature=host._signature(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
            response={'ok':True,'result':dict(verified=True,gameTime=10,player=1,world=2)})
    add_read(ledger,'get_game_state',dict(speedup=0,gameTime=10,player=1,world=2))
    add_read(ledger,'get_validation_state',dict(session='session',pending=None))
    host._save(ledger)


def add_read(ledger, command, value, session='session', created=100.1):
    ledger['requests'][command]=dict(kind='read',command=command,session=session,created=created,generation=GEN,slot=0,
                                    response=dict(ok=True,result=value))


def publish(host):
    return host.send('load_game',dict(slot='target',backup_save='backup'),kind='load',expected_session='session')


def ack(host,ticket):
    response=dict(id=ticket['id'],cmd='load_game',ok=True,result=dict(requested=True,slot='target',session='session',verified=False))
    with host.log.open('a') as f:
        f.write(f'[TNJ_UI_READ_V1] id={ticket["id"]} part=1 total=1 hex={json.dumps(response).encode().hex()}\n')


def transition(host):
    with host.log.open('a') as f:
        f.write('Game is ready\n'+TAG+json.dumps(dict(generation=GEN,session='new',slot=1,mode='demand',
            filename='snew_1.lua',status='ready',utc=100,clock=10,due=12,loadGameVersion=1,loadGameAvailable=True))+'\n')


@pytest.mark.parametrize('case',['capability','changed_file','missing_save','native_pending','running','stale_backup','missing_session'])
def test_load_preflight_fails_without_publication(host,case):
    setup_host(host);ledger=host._load()
    if case=='capability':host.log.write_text(host.log.read_text().replace('"loadGameVersion": 1','"loadGameVersion": 0'))
    if case=='changed_file':host._save_path('target').write_bytes(b'changed')
    if case=='missing_save':del ledger['requests']['target']
    if case=='native_pending':ledger['requests']['get_validation_state']['response']['result']['pending']='operation'
    if case=='running':ledger['requests']['get_game_state']['response']['result']['speedup']=1
    if case=='stale_backup':ledger['requests']['backup']['created']=-1000
    host._save(ledger)
    with pytest.raises(ValueError):
        if case=='missing_session':host.send('load_game',dict(slot='target',backup_save='backup'),kind='load')
        else:publish(host)
    assert not (host.mod/'no_gui'/GEN/'ssession_1.lua').exists()
    assert not host._load().get('pending')


def test_ack_is_not_load_and_new_session_is_not_full_verification(host):
    setup_host(host);ticket=publish(host);ack(host,ticket)
    assert host.read(ticket['id'])['status']=='pending'
    with pytest.raises(ValueError,match='unresolved'):publish(host)
    transition(host)
    restored=NoGuiRequests(host.directory,host.mod)
    result=restored.read(ticket['id'])['response']['result']
    assert result['reloadObserved'] and not result['verified']
    assert restored._load()['loadVerification']==ticket['id']
    with pytest.raises(ValueError,match='readback'):restored.send('save_game',{'slot':'new'},kind='save',expected_session='new')
    with pytest.raises(ValueError,match='native read'):restored.verify_load(ticket['id'])
    ledger=restored._load()
    add_read(ledger,'get_game_state',dict(speedup=0,gameTime=10,player=1,world=2),'new',100.3)
    add_read(ledger,'get_map_info',dict(towns=[],industries=[],width=10,height=10),'new',100.3)
    add_read(ledger,'get_validation_state',dict(session='new',pending=None),'new',100.3)
    restored._save(ledger)
    verified=restored.verify_load(ticket['id'])
    assert verified['verified'] and verified['identity']['session']=='new'
    assert restored._load()['loadVerification'] is None
    assert restored.verify_load(ticket['id'])==verified


def test_current_save_does_not_scan_unrelated_history(host):
    setup_host(host)
    history=host.directory/'no_gui_history';history.mkdir()
    (history/'unrelated.json').write_text('not a save record')
    assert publish(host)['status']=='published'


@pytest.mark.parametrize('fault', [None, 'hash', 'late', 'wrong_generation', 'changed_save'])
def test_explicit_preload_deployment_resumes_only_original_verification(host, fault):
    import os
    from tf3_mcp.no_gui_load import authorize_installed_upgrade
    setup_host(host)
    gen = 'b'*32
    script = host.mod/'bridge.script.lua'
    script.write_text('local NO_GUI_GENERATION = "'+gen+'"')
    evidence = host.directory/'deployment.json'
    evidence.write_text(json.dumps(dict(status='installed_requires_fresh_load',generation=gen,
        modContent=str(host.mod),installedSha256=hashlib.sha256(script.read_bytes()).hexdigest())))
    os.utime(script,(90,90));os.utime(evidence,(90,90))
    ticket=publish(host);ack(host,ticket);transition(host)
    host.log.write_text(host.log.read_text().rsplit(TAG,1)[0]+TAG+json.dumps(dict(
        generation=gen,session='new',slot=1,mode='demand',filename='snew_1.lua',status='ready',
        utc=100,clock=10,due=12,loadGameVersion=1))+'\n')
    with pytest.raises(ValueError,match='Unexpected receiver'):host.read(ticket['id'])
    if fault=='hash':script.write_text('changed');os.utime(script,(90,90))
    if fault=='late':os.utime(evidence,(101,101))
    if fault=='wrong_generation':
        d=json.loads(evidence.read_text());d['generation']='c'*32;evidence.write_text(json.dumps(d));os.utime(evidence,(90,90))
    if fault=='changed_save':host._save_path('target').write_bytes(b'changed')
    if fault:
        with pytest.raises(ValueError):authorize_installed_upgrade(host,ticket['id'],evidence)
        assert 'loadReceiverUpgrade' not in host._load()['requests'][ticket['id']]
    else:
        authorize_installed_upgrade(host,ticket['id'],evidence)
        assert host._load()['pending']==ticket['id']
        result=host.read(ticket['id'])['response']['result']
        assert result['reloadObserved'] and not result['verified']
        assert host._load()['loadVerification']==ticket['id']
        assert host._load()['requests'][ticket['id']]['generation']==GEN
    assert len([r for r in host._load()['requests'].values() if r.get('kind')=='load'])==1


@pytest.mark.parametrize('case',['no_ack','wrong_time','modified_file','log_rotated'])
def test_load_unknown_or_wrong_target_never_unblocks_writes(host,case):
    setup_host(host);ticket=publish(host)
    if case!='no_ack':ack(host,ticket)
    transition(host)
    if case=='modified_file':host._save_path('target').write_bytes(b'changed')
    if case=='log_rotated':host.log.write_text('rotated\n')
    if case in ('modified_file','log_rotated'):
        with pytest.raises(ValueError):host.read(ticket['id'])
        assert host._load()['pending']==ticket['id'];return
    if case=='no_ack':
        assert host.read(ticket['id'])['status']=='pending'
        assert host._load()['pending']==ticket['id'];return
    host.read(ticket['id']);ledger=host._load()
    add_read(ledger,'get_game_state',dict(speedup=0,gameTime=999,player=1,world=2),'new',100.3)
    add_read(ledger,'get_map_info',dict(towns=[],industries=[]),'new',100.3)
    add_read(ledger,'get_validation_state',dict(session='new'),'new',100.3);host._save(ledger)
    with pytest.raises(ValueError,match='does not match'):host.verify_load(ticket['id'])
    assert host._load()['loadVerification']==ticket['id']


def enable_native(lua):
    lua.execute('''
      loadCalls=0;waitCalls=0
      api.type.SavegameId={new=function()return {}end}
      app.SaveGameNamespace={getSavegame=function()return 'save'end}
      app.findAllSavegames=function(namespace)
       assert(namespace=='save');return {{saveName='target',path='native/path',size=100}}
      end
      app.setWaitForStartReadyGame=function()waitCalls=waitCalls+1 end
      app.loadGame=function(id,editor,info)
       assert(id.path=='native/path' and id.saveGameName=='target' and id.saveGameNamespace=='save')
       assert(editor==false and info==nil);loadCalls=loadCalls+1
       if failLoad then error('native load failed')end
      end
    ''')


def test_native_load_uses_menu_api_once_and_stops_departing_receiver(warehouse_game):
    lua,rows,output,send=native_channel(warehouse_game);enable_native(lua)
    send(1,{'slot':'target','backup_save':'backup'},'load','load_game')
    assert lua.globals().loadCalls==1 and lua.globals().waitCalls==1
    assert rows[-1]['status']=='dispatched'
    data=json.loads(bytes.fromhex(output[-1].split('hex=')[1]))
    assert data['result']['requested'] and not data['result']['verified']
    rows[-1]['due']=100  # A later GUI tick still cannot dispatch another load.
    send(2,{'slot':'target','backup_save':'backup'},'load','load_game')
    assert lua.globals().loadCalls==1


@pytest.mark.parametrize('case',['missing','ambiguous','running','native_error','unsafe','missing_api'])
def test_native_load_failures_never_retry(warehouse_game,case):
    lua,rows,output,send=native_channel(warehouse_game);enable_native(lua)
    if case=='missing':lua.execute('app.findAllSavegames=function()return {}end')
    if case=='ambiguous':lua.execute("app.findAllSavegames=function()return {{saveName='target',size=1},{saveName='target',size=1}}end")
    if case=='running':lua.execute('api.engine.getComponent(api.engine.util.getWorld(),api.type.ComponentType.GAME_SPEED).speedup=1')
    if case=='native_error':lua.execute('failLoad=true')
    if case=='missing_api':lua.execute('app.loadGame=nil')
    send(1,{'slot':'../target' if case=='unsafe' else 'target','backup_save':'backup'},'load','load_game')
    assert rows[-1]['status']=='stopped'
    assert lua.globals().loadCalls==(1 if case=='native_error' else 0)


def test_native_error_ack_cannot_be_certified_by_later_manual_reload(host):
    setup_host(host);ticket=publish(host);ack(host,ticket)
    with host.log.open('a') as f:
        f.write(TAG+json.dumps(dict(session='session',generation=GEN,slot=1,status='stopped',error='load failed'))+'\n')
    transition(host)
    with pytest.raises(ValueError,match='stopped with an error'):host.read(ticket['id'])
    assert host._load()['pending']==ticket['id']


def test_callable_native_load_binding(warehouse_game):
    lua,rows,output,send=native_channel(warehouse_game);enable_native(lua)
    lua.execute('local fn=app.loadGame;app.loadGame=setmetatable({},{__metatable="native",__call=function(_,...)return fn(...)end})')
    send(1,{'slot':'target','backup_save':'backup'},'load','load_game')
    assert lua.globals().loadCalls==1


@pytest.mark.parametrize('failed_at',[None,'save_game','load_game'])
def test_named_load_backs_up_before_single_load_and_reads_back(tmp_path,monkeypatch,failed_at):
    import asyncio
    from tf3_mcp.no_gui_client import NoGuiClient,NoGuiOutcomeUnknown
    from test_channel_migration import Requests
    class LoadRequests(Requests):
        def __init__(self):
            super().__init__();self.directory=tmp_path;self.verified=False
        def status(self):
            result=super().status();result['receiver'].update(loadGameVersion=1,loadGameAvailable=True)
            return result
        def _load(self):return {}
        def read(self,ident):
            command,_=self.calls[int(ident)]
            if command==failed_at:return {'status':'timeout_unknown'}
            return super().read(ident)
        def verify_load(self,ident):
            assert [name for name,_ in self.calls[-3:]]==['get_game_state','get_map_info','get_validation_state']
            self.verified=True
            return {'verified':True,'identity':{'session':self.session}}
    async def run():
        r=LoadRequests();r.responses.update(get_game_state={'speedup':0},get_validation_state={'pending':None})
        def load(args):
            assert args['slot']=='target' and args['backup_save'].startswith('tf3_before_load_')
            r.session='new'
            return {'reloadObserved':True,'newSession':'new'}
        r.responses['load_game']=load
        monkeypatch.setattr('tf3_mcp.no_gui_load.verified_save',lambda *a: {})
        client=NoGuiClient(r,0)
        if failed_at:
            with pytest.raises(NoGuiOutcomeUnknown):await client.load_game('target','current')
            assert not r.verified
        else:
            result=await client.load_game('target','current')
            assert result['verified'] and client.identity['session']=='new'
        names=[name for name,_ in r.calls]
        assert names.count('save_game')==1
        assert names.count('load_game')==(0 if failed_at=='save_game' else 1)
        if 'load_game' in names:assert names.index('save_game')<names.index('load_game')
    asyncio.run(run())
