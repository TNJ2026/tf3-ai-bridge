"""Save dispatch must not mistake an acknowledgement or an old file for completion."""
import json

import pytest

from test_headless import GEN, host
from test_e2e import SCRIPT
from test_warehouses import warehouse_game
from tf3_mcp.headless import HeadlessRequests, TAG
from tf3_mcp.ui_log import validate_save_arguments


@pytest.mark.parametrize('args', [None, {}, {'slot':'../2222'}, {'slot':'C:/x'},
    {'slot':'a.sav'}, {'slot':'CON'}, {'slot':'lpt1'}, {'slot':''}, {'slot':'x'*81},
    {'slot':3}, {'slot':'x','overwrite':1}, {'slot':'x','code':'anything'}])
def test_reject_unsafe_save_names_and_arguments(args):
    with pytest.raises(ValueError):
        validate_save_arguments('save_game', args)


def enable(host):
    row=json.loads(host.log.read_text().split(TAG)[1])
    row['saveGameAvailable']=True
    host.log.write_text(TAG+json.dumps(row)+'\n')


def publish(host, overwrite=False):
    return host.send('save_game', {'slot':'2222','overwrite':overwrite}, kind='save', expected_session='session')


def acknowledge(host, ticket, **changes):
    response=dict(id=ticket['id'],cmd='save_game',ok=True,
                  result=dict(requested=True,verified=False,slot='2222',session='session'))
    response.update(changes)
    with host.log.open('a') as f:
        f.write(f'[TNJ_UI_READ_V1] id={ticket["id"]} part=1 total=1 hex={json.dumps(response).encode().hex()}\n')


def test_save_requires_capability_and_verified_session(host):
    with pytest.raises(ValueError,match='does not support'):publish(host)
    enable(host)
    with pytest.raises(ValueError,match='verified current session'):
        host.send('save_game', {'slot':'2222'},kind='save')
    assert not host.ledger.exists()


def test_existing_save_requires_explicit_overwrite(host):
    enable(host)
    folder=host.directory.parent/'save';folder.mkdir();(folder/'2222.sav').write_bytes(b'old')
    with pytest.raises(ValueError,match='overwrite'):publish(host)
    assert not host.ledger.exists()
    assert publish(host,True)['status']=='published'


def test_native_ack_old_file_timeout_and_late_verified_result_after_restart(host,monkeypatch):
    enable(host)
    folder=host.directory.parent/'save';folder.mkdir();path=folder/'2222.sav';path.write_bytes(b'old')
    ticket=publish(host,True);acknowledge(host,ticket)
    assert host.read(ticket['id'])['status']=='pending'
    with pytest.raises(ValueError,match='unresolved'):host.send('get_game_state')
    monkeypatch.setattr('tf3_mcp.headless.time.time',lambda:221)
    assert host.read(ticket['id'])['status']=='timeout_unknown'
    assert host._load()['pending']==ticket['id']
    path.write_bytes(b'new save data')
    restarted=HeadlessRequests(host.directory,host.mod)
    assert restarted.read(ticket['id'])['status']=='timeout_unknown'
    monkeypatch.setattr('tf3_mcp.headless.time.time',lambda:223)
    # Receiver freshness is independent from the result frame.
    with host.log.open('a') as f:
        f.write(TAG+json.dumps(dict(generation=GEN,session='session',slot=2,status='ready',utc=223,clock=133,due=135,saveGameAvailable=True))+'\n')
    result=restarted.read(ticket['id'])
    assert result['status']=='received' and result['response']['result']['verified']
    assert result['response']['result']['file']['signature']['size']==13
    assert result['response']['result']['file']['reloadVerified'] is False
    assert restarted.status()['pending'] is None
    path.unlink()
    assert HeadlessRequests(host.directory,host.mod).read(ticket['id'])==result


def test_growing_and_empty_files_do_not_complete(host,monkeypatch):
    enable(host);ticket=publish(host);acknowledge(host,ticket)
    folder=host.directory.parent/'save';folder.mkdir();path=folder/'2222.sav';path.touch()
    assert host.read(ticket['id'])['status']=='pending'
    path.write_bytes(b'part')
    assert host.read(ticket['id'])['status']=='pending'
    monkeypatch.setattr('tf3_mcp.headless.time.time',lambda:102)
    path.write_bytes(b'part plus more')
    assert host.read(ticket['id'])['status']=='pending'
    assert host._load()['requests'][ticket['id']]['saveStableSince']==102
    assert host._load()['pending']==ticket['id']


def test_reloaded_log_never_certifies_new_file(host):
    enable(host);ticket=publish(host);acknowledge(host,ticket)
    with host.log.open('a') as f:f.write('Game is ready\n')
    folder=host.directory.parent/'save';folder.mkdir();(folder/'2222.sav').write_bytes(b'new')
    with pytest.raises(ValueError,match='reloaded'):host.read(ticket['id'])
    assert host._load()['pending']==ticket['id']


def test_native_error_does_not_release_pending(host):
    enable(host);ticket=publish(host);acknowledge(host,ticket,ok=False,error='unknown save failure')
    assert host.read(ticket['id'])['status']=='timeout_unknown'
    assert host._load()['pending']==ticket['id']


def native_channel(warehouse_game, callable_table=False):
    lua,_=warehouse_game
    lua.execute('''
      headlessNow=1;os.clock=function()return headlessNow end
      saveCalls=0;contents={};app={}
      api.engine.getComponent(api.engine.util.getWorld(),api.type.ComponentType.GAME_SPEED).speedup=0
      app.saveGame=function(slot,callback,mapEditor,skipName)
        assert(slot=='2222' and mapEditor==false and skipName==true)
        saveCalls=saveCalls+1;callback()
        if failSave then error('native save outcome unknown') end
      end
      resolveutil={loadfile=function(path)
        if not contents[path] then return nil,'Could not find file '..path end
        return function()return contents[path] end
      end}
    ''')
    if callable_table:
        lua.execute('local save=app.saveGame;app.saveGame=setmetatable({},{__metatable="native",__call=function(_,...)return save(...)end})')
    source=SCRIPT.read_text(encoding='utf-8').replace('local HEADLESS_GENERATION = "disabled"',f'local HEADLESS_GENERATION = "{GEN}"').replace('local HEADLESS_ON_DEMAND = false','local HEADLESS_ON_DEMAND = true')
    script=lua.execute(source);rows=[];output=[]
    lua.globals().debugPrint=lambda line:rows.append(json.loads(line.split(TAG)[1])) if TAG in line else None
    lua.globals().print=lambda *args:output.append(' '.join(map(str,args)))
    tick=lambda:script['guiUpdate'](None,None,None)
    tick()
    def send(i,args=None,kind='save',cmd='save_game',session=None):
        row=rows[-1]
        data=dict(generation=GEN,session=session or row['session'],slot=row['slot'],expires=row['due']+20,kind=kind,input=f'{i:032x} '+cmd+' '+json.dumps(args or {'slot':'2222'}))
        path='tnj_tf3_ai_bridge::/tf3_mcp_bridge/headless/'+GEN+'/'+row['filename']
        lua.globals().contents[path]=json.dumps(data)
        lua.globals().headlessNow=row['due'];tick()
    return lua,rows,output,send


@pytest.mark.parametrize('callable_table',[False,True])
def test_native_save_without_panel_callback_globals_or_speed_change(warehouse_game,callable_table):
    lua,rows,output,send=native_channel(warehouse_game,callable_table)
    assert rows[-1]['saveGameAvailable']
    send(1)
    assert lua.globals().saveCalls==1 and rows[-1]['status']=='ready'
    data=json.loads(bytes.fromhex(output[-1].split('hex=')[1]))
    assert data['ok'] and data['result']['requested'] and not data['result']['verified']
    assert lua.eval('api.engine.getComponent(api.engine.util.getWorld(),api.type.ComponentType.GAME_SPEED).speedup')==0
    # Save IDs are not evicted with the rolling read ledger.
    for i in range(2,260):send(i,{'limit':1},'read','list_towns')
    send(1)
    assert lua.globals().saveCalls==1 and rows[-1]['status']=='stopped'


@pytest.mark.parametrize('case',['running','bad_session','bad_slot','native_error','missing_api'])
def test_native_save_fails_closed_without_retry(warehouse_game,case):
    lua,rows,output,send=native_channel(warehouse_game)
    if case=='running':lua.execute('api.engine.getComponent(api.engine.util.getWorld(),api.type.ComponentType.GAME_SPEED).speedup=1')
    if case=='native_error':lua.execute('failSave=true')
    if case=='missing_api':lua.execute('app.saveGame=nil')
    send(1,{'slot':'../2222'} if case=='bad_slot' else None,session='wrong' if case=='bad_session' else None)
    assert rows[-1]['status']=='stopped'
    assert lua.globals().saveCalls==(1 if case=='native_error' else 0)
    assert not any('[TNJ_UI_READ_V1]' in line for line in output)
