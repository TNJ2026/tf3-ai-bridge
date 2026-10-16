import json
import pytest
from test_no_gui import host, GEN, SCRIPT
from test_warehouses import warehouse_game
from tf3_mcp.no_gui import TAG, NoGuiRequests
from tf3_mcp.bridge import encode_message, decode_message


def setup_host(host):
    (host.directory.parent/'mod_presets').mkdir()
    row=dict(generation=GEN,session='session',slot=1,status='ready',utc=100,clock=10,due=11,
        mode='userdata',userdataVersion=1,userdataDirectory='mod_presets',filename='tnj_mcp_'+GEN+'_request.preset.lua')
    host.log.write_text(TAG+json.dumps(row)+'\n')
    return row,host.directory.parent/'mod_presets'/row['filename']


def test_publication_and_restart_recovery(host):
    row,path=setup_host(host)
    ticket=host.send('get_game_state')
    payload=decode_message(path.read_text())
    assert payload['input']==ticket['id']+' get_game_state'
    restarted=NoGuiRequests(host.directory,host.mod)
    with pytest.raises(ValueError,match='unresolved'):restarted.send('get_game_state')
    response=dict(id=ticket['id'],cmd='get_game_state',ok=True,result={'world':2})
    with host.log.open('a') as f:f.write('[TNJ_UI_READ_V1] id='+ticket['id']+' part=1 total=1 hex='+json.dumps(response).encode().hex()+'\n')
    assert restarted.read(ticket['id'])['response']==response
    row['slot']=2;host.log.write_text(TAG+json.dumps(row)+'\n')
    second=restarted.send('get_game_state')
    assert second['id']!=ticket['id'] and second['slot']==2


def test_foreign_mailbox_never_overwritten(host):
    row,path=setup_host(host);path.write_text(encode_message({'input':'foreign'}))
    before=path.read_bytes()
    with pytest.raises(ValueError,match='terminal receipt'):host.send('get_game_state')
    assert path.read_bytes()==before and not host.ledger.exists()


@pytest.mark.parametrize('change',[{'filename':'../other.lua'},{'userdataDirectory':'save'},{'userdataVersion':2}])
def test_status_rejects_untrusted_mailbox_paths(host,change):
    row,_=setup_host(host);row.update(change);host.log.write_text(TAG+json.dumps(row)+'\n')
    with pytest.raises(ValueError,match='mailbox identity'):host.status()


def test_atomic_publication_failure_preserves_intent(host,monkeypatch):
    row,path=setup_host(host)
    from tf3_mcp import no_gui
    original=no_gui.atomic
    def fail(p,data):
        if p==path:raise OSError('publication unknown')
        return original(p,data)
    monkeypatch.setattr(no_gui,'atomic',fail)
    with pytest.raises(OSError):host.send('get_game_state')
    assert host._load()['pending']
    with pytest.raises(ValueError,match='unresolved'):host.send('get_game_state')


@pytest.mark.parametrize('packaged', [False, True])
def test_native_userdata_idle_replay_and_301_reads(warehouse_game, tmp_path, packaged):
    lua,_=warehouse_game
    lua.execute('''no_guiNow=1;os.clock=function()return no_guiNow end
      files={}; app={}
      app.getAllUserdata=function(d) assert(d=='mod_presets');local r={};for k in pairs(files)do r[#r+1]=k end;return r end
      app.loadUserdata=function(d,n)return files[n] end
      app.removeUserdata=function(d,n)files[n]=nil end
      resolveutil=nil
    ''')
    text=SCRIPT.read_text(encoding='utf-8').replace('local NO_GUI_GENERATION = "disabled"',f'local NO_GUI_GENERATION = "{GEN}"').replace('local NO_GUI_ON_DEMAND = false','local NO_GUI_ON_DEMAND = true').replace('local NO_GUI_USERDATA = false','local NO_GUI_USERDATA = true')
    generation = GEN
    if packaged:
        from build_mod_package import build_package
        from pathlib import Path
        release = build_package(SCRIPT.parents[2], tmp_path / 'release')
        generation = release['generation']
        text = (Path(release['modRoot']) / 'content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
    script=lua.execute(text);rows=[];output=[]
    lua.globals().debugPrint=lambda s:rows.append(json.loads(s.split(TAG,1)[1])) if TAG in s else None
    lua.globals().print=lambda *args:output.append(' '.join(map(str,args)))
    tick=lambda:script['guiUpdate'](None,None,None)
    tick()
    for t in (100,7200):
        lua.globals().no_guiNow=t;tick();assert rows[-1]['slot']==1
    mailbox='tnj_mcp_'+generation+'_request.preset'
    old=None
    for n in range(1,302):
        r=rows[-1]
        packet=dict(generation=generation,session=r['session'],slot=r['slot'],expires=r['due']+20,kind='read',input=f'{n:032x} get_game_state')
        if n==2:
            # Reappearing old bytes cannot execute or consume another sequence.
            lua.globals().files[mailbox]=lua.table_from(dict(hex=json.dumps(old).encode().hex()))
            lua.globals().no_guiNow=r['due'];tick()
            assert rows[-1]['slot']==2 and len(output)==1
            r=rows[-1];packet['expires']=r['due']+20
        lua.globals().files[mailbox]=lua.table_from(dict(hex=json.dumps(packet).encode().hex()))
        lua.globals().no_guiNow=r['due'];tick()
        assert rows[-1]['status']=='ready' and rows[-1]['slot']==n+1
        assert lua.globals().files[mailbox] is None
        old=packet
    assert len(output)==301
