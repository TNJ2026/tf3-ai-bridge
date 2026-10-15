from pathlib import Path
from lupa.lua52 import LuaRuntime


def harness(existing=False):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
      now=0; files={}; events={}; saves=0; removes=0
      app={}
      app.getAllUserdata=function(dir) assert(dir=='mod_presets');local a={};for k in pairs(files) do a[#a+1]=k end;return a end
      app.saveUserdata=function(dir,name,value) saves=saves+1;files[name]=value end
      app.loadUserdata=function(dir,name) return files[name] end
      app.removeUserdata=function(dir,name) removes=removes+1;files[name]=nil end
    ''')
    config = lua.table_from(dict(id='unique', filename='unique.preset', a='token_a', b='token_b'))
    if existing:
        lua.globals().files['unique.preset'] = lua.table_from(dict(owner='user'))
    factory = lua.execute((Path(__file__).parents[1] / 'userdata_roundtrip_probe.lua').read_text())
    tick = factory(config, lua.eval('function(row) events[#events+1]=row end'), lua.eval('function() return now end'))
    return lua, tick


def test_a_external_b_twice_cleanup_and_no_replay():
    lua, tick = harness();tick()
    assert lua.globals().events[2]['event']=='read_a'
    assert lua.globals().events[2]['listedInNativePresets'] is True
    lua.globals().files['unique.preset']['marker']='token_b'
    lua.globals().now=1;tick()
    assert lua.globals().removes==0
    lua.globals().now=2;tick()
    assert lua.globals().events[5]['event']=='complete'
    assert lua.globals().events[5]['cleaned'] is True
    tick();assert lua.globals().saves==1 and lua.globals().removes==1


def test_existing_file_never_overwritten_or_removed():
    lua,tick=harness(True);tick()
    assert lua.globals().saves==0 and lua.globals().removes==0
    assert lua.globals().files['unique.preset']['owner']=='user'


def test_timeout_cleans_only_owned_file():
    lua,tick=harness();tick();lua.globals().now=121;tick()
    assert lua.globals().events[3]['event']=='failed'
    assert lua.globals().events[3]['cleaned'] is True


def test_replaced_file_preserved():
    lua,tick=harness();tick()
    lua.globals().files['unique.preset']['probeId']='someone_else'
    lua.globals().now=1;tick()
    assert lua.globals().removes==0
