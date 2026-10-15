from pathlib import Path
from lupa.lua52 import LuaRuntime


def harness():
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''now=0;files={};events={};app={}
    app.getAllUserdata=function(d)local a={};for k in pairs(files) do a[#a+1]=k end;return a end
    app.loadUserdata=function(d,n)return files[n] end
    app.saveUserdata=function(d,n,v)files[n]=v end
    app.removeUserdata=function(d,n)files[n]=nil end''')
    config=lua.table_from(dict(id='test',session='session',request='req',response='resp',rounds=2))
    factory=lua.execute((Path(__file__).parents[1]/'userdata_duplex_probe.lua').read_text())
    tick=factory(config,lua.eval('function(r)events[#events+1]=r end'),lua.eval('function()return now end'),
                 lua.eval('function(x)return x end'),lua.eval('function(x)return x end'))
    tick()
    def send(seq,payload='中文',session='session',op='echo',attempt=None):
        lua.globals().now+=1
        lua.globals().files['req']=lua.table_from(dict(probeId='test',session=session,seq=seq,
            payload=payload,op=op,attempt=attempt or str(lua.globals().now)))
        tick();return lua.globals().files['resp']
    return lua,tick,send


def test_external_first_repeated_roundtrip_and_dedup():
    lua,tick,send=harness()
    assert lua.globals().files['req'] is None and lua.globals().files['resp'] is None
    assert send(1)['processed']==1
    assert send(1)['status']=='duplicate'
    assert send(1,'different')['status']=='rejected'
    assert send(2,session='old')['reason']=='wrong_session'
    assert send(2)['processed']==2
    send(3,op='finish')
    assert lua.globals().files['req'] is None and lua.globals().files['resp'] is None
    assert lua.globals().events[len(lua.globals().events)]['cleaned'] is True


def test_idle_request_not_reprocessed_and_skipped_sequence_rejected():
    lua,tick,send=harness();send(1,attempt='fixed')
    count=len(lua.globals().events);lua.globals().now+=1;tick()
    assert len(lua.globals().events)==count
    assert send(3)['status']=='rejected'


def test_foreign_response_not_removed_on_timeout():
    lua,tick,send=harness();send(1)
    lua.globals().files['resp']=lua.table_from(dict(probeId='other'))
    lua.globals().now=181;tick()
    assert lua.globals().files['resp']['probeId']=='other'
    assert lua.globals().events[len(lua.globals().events)]['cleaned'] is False
