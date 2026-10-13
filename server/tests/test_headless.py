import json
import re

import pytest

from tf3_mcp.headless import HeadlessRequests, TAG
from test_e2e import SCRIPT
from test_warehouses import warehouse_game

GEN = 'a' * 32


@pytest.fixture
def host(tmp_path, monkeypatch):
    directory = tmp_path / 'tf3_mcp'; directory.mkdir()
    logs = tmp_path / 'crash_dump'; logs.mkdir()
    mod = tmp_path / 'mod'; slots = mod / 'headless' / GEN; slots.mkdir(parents=True)
    for n in range(1, 5):
        (slots / f'{n}.lua').write_bytes(b'return ""\n')
    log = logs / 'stdout.txt'
    log.write_text(TAG + json.dumps(dict(generation=GEN, session='session', slot=1,
                                        status='ready', utc=100, clock=10, due=12)) + '\n')
    monkeypatch.setattr('tf3_mcp.headless.time.time', lambda: 100.25)
    return HeadlessRequests(directory, mod)


def test_durable_publication_response_and_restart(host):
    ticket = host.send('get_game_state')
    content = (host.mod / 'headless' / GEN / '1.lua').read_text()
    decoded = bytes(int(n) for n in re.findall(r'\\(\d{3})', content)).decode()
    envelope = json.loads(decoded)
    assert envelope['session'] == 'session' and envelope['slot'] == 1
    assert ticket['id'] in envelope['input']
    restarted = HeadlessRequests(host.directory, host.mod)
    with pytest.raises(ValueError, match='unresolved'):
        restarted.send('get_finances')
    response = dict(id=ticket['id'], cmd='get_game_state', ok=True, result={'date': 'today'})
    with host.log.open('a') as f:
        f.write(f'[TNJ_UI_READ_V1] id={ticket["id"]} part=1 total=1 hex={json.dumps(response).encode().hex()}\n')
    assert restarted.read(ticket['id'])['response'] == response
    assert restarted.status()['pending'] is None
    assert restarted.read(ticket['id'])['response'] == response
    with pytest.raises(ValueError, match='not empty'):
        restarted.send('get_finances')


def test_no_publish_on_invalid_or_changed_session(host):
    for cmd, args, kind, session in [('run_lua', {}, 'read', None),
                                    ('commit_road', {'preview_token': 'p'}, 'build', None),
                                    ('commit_road', {'preview_token': 'p'}, 'build', 'old')]:
        with pytest.raises(ValueError):
            host.send(cmd, args, kind=kind, expected_session=session)
    assert not host.ledger.exists()


@pytest.mark.parametrize('command,args', [
    ('get_network_template', {'template':'highway/highway_new_small'}),
    ('list_road_structures', {}),
    ('commit_road_graph', {'preview_token':'x','backup_save':'isolated'}),
    ('get_road_graph_operation', {'operation_id':'x'}),
])
def test_old_receiver_refuses_v35_before_publication(host,command,args):
    with pytest.raises(ValueError,match='lacks v35'):
        host.send(command,args,kind='build',expected_session='session')
    assert not host.ledger.exists()
    assert (host.mod / 'headless' / GEN / '1.lua').read_bytes()==b'return ""\n'


@pytest.mark.parametrize('version',[None,36,37,38,39,40,41])
def test_special_road_graph_requires_loaded_v37(host,version):
    row=dict(generation=GEN,session='session',slot=1,status='ready',utc=100,clock=10,due=12,
             inputLimits={'default':512,'preview_road_graph':8192})
    if version is not None:row['roadGraphVersion']=version
    host.log.write_text(TAG+json.dumps(row)+'\n')
    args={'graph':{'nodes':[{'split':{'edge':123,'param':.5,'allow_structure':True}}],'edges':[]},'isolated_test':True}
    if version in (37,38,39,40):
        assert host.send('preview_road_graph',args,kind='build',expected_session='session')['status']=='published'
    else:
        with pytest.raises(ValueError,match='lacks v37'):
            host.send('preview_road_graph',args,kind='build',expected_session='session')
        assert not host.ledger.exists()
        assert (host.mod/'headless'/GEN/'1.lua').read_bytes()==b'return ""\n'


@pytest.mark.parametrize('version',[37,38,39,40,41])
def test_v40_preservation_rejected_before_publication_on_old_receiver(host,version):
    row=dict(generation=GEN,session='session',slot=1,status='ready',utc=100,clock=10,due=12,
             roadGraphVersion=version,inputLimits={'default':512,'preview_road_graph':8192})
    host.log.write_text(TAG+json.dumps(row)+'\n')
    args={'graph':{'nodes':[{'split':{'edge':123,'param':.5,'preserve_crossings':True}}],'edges':[]},'isolated_test':True}
    if version==40:
        assert host.send('preview_road_graph',args,kind='build',expected_session='session')['status']=='published'
    else:
        with pytest.raises(ValueError,match='lacks v'):
            host.send('preview_road_graph',args,kind='build',expected_session='session')
        assert not host.ledger.exists()


def test_atomic_write_failure_preserves_intent(host, monkeypatch):
    from tf3_mcp import headless
    original = headless.atomic
    def fail(path, data):
        if path.suffix == '.lua':
            raise OSError('unknown publication failure')
        return original(path, data)
    monkeypatch.setattr(headless, 'atomic', fail)
    with pytest.raises(OSError):
        host.send('get_game_state')
    restarted = HeadlessRequests(host.directory, host.mod)
    assert restarted.status()['pending']
    with pytest.raises(ValueError, match='unresolved'):
        restarted.send('get_game_state')


def test_reload_does_not_clear_pending(host):
    ticket = host.send('get_game_state')
    with host.log.open('a') as f:
        f.write('[tf3_mcp_bridge] started in gui state\n')
    with pytest.raises(ValueError, match='reloaded'):
        host.read(ticket['id'])
    assert host._load()['pending'] == ticket['id']


def test_stale_receiver_refuses_dispatch(host, monkeypatch):
    monkeypatch.setattr('tf3_mcp.headless.time.time', lambda: 110)
    with pytest.raises(ValueError, match='stale'):
        host.send('get_game_state')
    assert not host.ledger.exists()


def test_public_batch_lock_is_shared(host):
    from tf3_mcp.headless import public_lock
    with public_lock(host.directory):
        with pytest.raises(OSError):
            host.send('get_game_state')
    assert not host.ledger.exists()


def test_demand_creates_missing_resource_and_session_scopes_filename(host):
    row=dict(generation=GEN,session='new_session',slot=1,status='ready',
             utc=100,clock=10,due=11,mode='demand',filename='snew_session_1.lua')
    host.log.write_text(TAG+json.dumps(row)+'\n')
    ticket=host.send('get_game_state')
    assert (host.mod/'headless'/GEN/'snew_session_1.lua').is_file()
    assert ticket['slot']==1


def test_archival_retains_old_result_and_high_water(host):
    ledger=host._load()
    for n in range(1,258):
        request_id=f'{n:032x}'
        ledger['requests'][request_id]=dict(id=request_id,generation=GEN,session='session',slot=n,
            response=dict(id=request_id,cmd='get_game_state',ok=True,result={}))
    ledger['highWater']={GEN+'|session':257}
    host._save(ledger)
    host._archive(ledger);host._save(ledger)
    assert len(ledger['requests'])==256
    restarted=HeadlessRequests(host.directory,host.mod)
    assert restarted.read(f'{1:032x}')['response']['ok']
    # Slot 1 is no longer in the hot ledger but remains blocked by high water.
    with pytest.raises(ValueError,match='consumed/reserved'):
        restarted.send('get_game_state')


@pytest.mark.parametrize('kind,command',[
    ('read','get_game_state'),('build','get_validation_state'),
    ('build','get_sim_entity {"id":999999}'),
])
def test_demand_idle_and_more_than_256_reads(warehouse_game,kind,command):
    lua,_=warehouse_game
    lua.execute('''
        headlessNow=1; os.clock=function()return headlessNow end
        contents={}; calls=0
        resolveutil={loadfile=function(path)
            calls=calls+1
            local value=contents[path]
            if value==nil then return nil,"Could not find file "..path end
            return function()return value end
        end}
        api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)
          return {event=true,id=id,name=name,param=param}
        end
        local send=api.cmd.sendCommand
        api.cmd.sendCommand=function(cmd,cb)
          if cmd.event then forwarded=cmd else send(cmd,cb) end
        end
    ''')
    source=SCRIPT.read_text(encoding='utf-8').replace('local HEADLESS_GENERATION = "disabled"',f'local HEADLESS_GENERATION = "{GEN}"').replace('local HEADLESS_ON_DEMAND = false','local HEADLESS_ON_DEMAND = true')
    script=lua.execute(source); rows=[]; output=[]
    lua.globals().debugPrint=lambda s: rows.append(json.loads(s.split(TAG,1)[1])) if TAG in s else None
    lua.globals().print=lambda *args:output.append(' '.join(map(str,args)))
    tick=lambda:script['guiUpdate'](None,None,None)
    state=lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
    tick()
    for t in (100,2200,7200):
        lua.globals().headlessNow=t;tick()
        assert rows[-1]['status']=='ready' and rows[-1]['slot']==1
    for n in range(1,302):
        r=rows[-1]
        req=dict(generation=GEN,session=r['session'],slot=r['slot'],expires=r['due']+20,
                 kind=kind,input=f'{n:032x} '+command)
        path='tnj_tf3_ai_bridge::/tf3_mcp_bridge/headless/'+GEN+'/'+r['filename']
        lua.globals().contents[path]=json.dumps(req)
        lua.globals().headlessNow=r['due'];tick()
        assert rows[-1]['status']=='ready' and rows[-1]['slot']==n+1
        if kind=='build':
            e=lua.globals().forwarded
            script['handleEvent'](None,state,'',e['id'],e['name'],e['param'])
    if kind=='read':assert len(output)==301
    else:
        assert sum(' part=1 ' in line for line in output)==301
        assert state['v']['uiConstruction']['count']==1
        assert state['v']['uiConstruction']['reclaimedReadRequests']==300
    assert not any(r['status']=='stopped' for r in rows)
    if kind=='build':
        # GUI forwarding no longer kills the receiver at 256. The durable
        # engine quota is tested separately, including its rejection/read/reset.
        gui=script['guiHandleEvent']
        for n in range(1000,1256):
            status=gui(None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',
                       f'{n:032x} build_warehouse '+json.dumps(dict(x=700,y=740,z=2)))
            assert status=='Submitted; inspect log'
        before=lua.globals().forwarded
        status=gui(None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',
                   f'{1256:032x} build_warehouse '+json.dumps(dict(x=700,y=740,z=2)))
        assert status=='Submitted; inspect log'
        assert lua.globals().forwarded['param']!=before['param']
        status=gui(None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',
                   f'{1000:032x} build_warehouse '+json.dumps(dict(x=700,y=740,z=2)))
        assert status=='Duplicate request; inspect existing log'


def test_headless_query_preview_commit_readback_without_gui_event(warehouse_game, tmp_path):
    lua, _ = warehouse_game
    lua.execute('''
        headlessNow=1; os.clock=function() return headlessNow end
        slotPayload=""; slotReads={}
        resolveutil={loadfile=function(path)
            assert(not slotReads[path], "resource read twice")
            slotReads[path]=true
            return function() return slotPayload end
        end}
        local nativeSend=api.cmd.sendCommand
        api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)
            return {event=true,id=id,name=name,param=param}
        end
        api.cmd.sendCommand=function(cmd,callback)
            if cmd.event then forwarded=cmd else nativeSend(cmd,callback) end
        end
    ''')
    text = SCRIPT.read_text(encoding='utf-8').replace('local HEADLESS_GENERATION = "disabled"', f'local HEADLESS_GENERATION = "{GEN}"')
    script = lua.execute(text)
    state = lua.execute('local s={value={}};function s:get()return self.value end;function s:set(v)self.value=v end;return s')
    records, output = [], []
    lua.globals().debugPrint = lambda line: records.append(json.loads(line.split(TAG, 1)[1])) if TAG in line else None
    lua.globals().print = lambda *args: output.append(' '.join(map(str, args)))
    script['guiUpdate'](None, None, None)
    from tf3_mcp.ui_log import UiLogRequests
    reader = UiLogRequests(); log = tmp_path / 'stdout.txt'; log.touch()

    def query(command, args, kind='build', bad_session=False):
        row = records[-1]; assert row['status'] == 'ready'
        ticket = (reader.prepare_build(log, command, args) if kind == 'build' else reader.prepare(log, command, args))
        envelope = dict(generation=GEN, session='wrong' if bad_session else row['session'], slot=row['slot'],
                        expires=row['due']+2, kind=kind, input=ticket['input'])
        lua.globals().slotPayload = json.dumps(envelope)
        lua.globals().forwarded = None
        lua.globals().headlessNow = row['due']
        script['guiUpdate'](None, None, None)
        event = lua.globals().forwarded
        if event:
            script['handleEvent'](None, state, '', event['id'], event['name'], event['param'])
        with log.open('a') as f:
            f.write('\n'.join(output)+'\n')
        output.clear()
        return reader.read(ticket['id']), event

    result, event = query('get_game_state', {}, 'read')
    assert result['response']['ok'] and event is None
    result, _ = query('build_warehouse', {'x':700,'y':740,'z':2})
    assert result['response']['ok'], result
    preview = result['response']['result']; assert preview['preview']
    result, commit = query('commit_facility', {'preview_token':preview['preview_token']})
    assert result['response']['ok'], result
    built = result['response']['result']; assert built['built'] and built['verified']
    submissions = lua.globals().SUBMISSIONS
    script['handleEvent'](None, state, '', commit['id'], commit['name'], commit['param'])
    assert lua.globals().SUBMISSIONS == submissions and not output
    result, _ = query('get_facility_config', {'entity':built['entity']})
    assert result['response']['result']['entity'] == built['entity']
    result, event = query('get_game_state', {}, 'read', bad_session=True)
    assert event is None and result['status'] == 'pending'
    assert records[-1]['status'] == 'stopped'
    assert lua.globals().SUBMISSIONS == submissions
