"""New-channel air construction using actual handlers, with mocked native API."""
import json

import pytest

from test_e2e import SCRIPT
from test_helipads import heli_game as pad_game
from test_heliports import heli_game as port_game
from test_airfield_starter import airfield_game
from test_facilities import game as facility_game
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments


@pytest.mark.parametrize('command,fixture', [('build_helipad', 'pad_game'), ('build_heliport', 'port_game'), ('build_airfield', 'airfield_game')])
def test_air_preview_commit_fresh_events_readback_and_unknown(request, command, fixture, tmp_path):
    lua, _ = request.getfixturevalue(fixture)
    lua.execute('''
      local send=api.cmd.sendCommand
      api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)
        return {event=true,id=id,name=name,param=param}
      end
      api.cmd.sendCommand=function(cmd,callback)
        if cmd.event then forwarded=cmd else send(cmd,callback) end
      end
    ''')
    gui=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    state=lua.execute('local s={v={},snapshot={}};function s:get()return self.snapshot end;function s:set(v)self.v=v end;return s')
    log=tmp_path/'stdout.txt';log.touch()
    reader=UiLogRequests();output=[]
    lua.globals().print=lambda *args: output.append(' '.join(map(str,args)))

    def query(cmd,args,unknown=False):
        ticket=reader.prepare_build(log,cmd,args)
        assert gui['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',ticket['input'])=='Submitted; inspect log'
        event=lua.globals().forwarded
        fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
        if unknown:
            fresh['_internal']['commands']['commit_facility']=lua.eval('function() error("native outcome unknown") end')
        state['snapshot']=state['v']
        fresh['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
        with log.open('a',encoding='utf-8') as f:f.write('\n'.join(output)+'\n')
        output.clear()
        return event,reader.read(ticket['id'])['response']

    args=dict(x=700,y=740,z=2,rotation=90)
    _,preview=query(command,args)
    assert preview['ok'] and preview['result']['preview'],preview
    assert lua.globals().SUBMISSIONS is None
    token=preview['result']['preview_token']
    event,built=query('commit_facility',dict(preview_token=token))
    assert built['ok'] and built['result']['built'] and built['result']['verified'],built
    assert not state['v']['uiConstruction']['pending']
    _,read=query('get_facility_config',dict(entity=built['result']['entity']))
    assert read['ok'] and read['result']['resource']==built['result']['config']['resource']
    assert lua.globals().SUBMISSIONS==1
    state['snapshot']=state['v']
    fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    fresh['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
    assert not output and lua.globals().SUBMISSIONS==1
    _,repeat=query('commit_facility',dict(preview_token=token))
    assert not repeat['ok'] and lua.globals().SUBMISSIONS==1
    _,preview=query(command,dict(x=1700,y=1740,z=2))
    _,failed=query('commit_facility',dict(preview_token=preview['result']['preview_token']),unknown=True)
    assert not failed['ok'] and state['v']['uiConstruction']['pending']
    _,preview=query(command,dict(x=2700,y=2740,z=2))
    _,blocked=query('commit_facility',dict(preview_token=preview['result']['preview_token']))
    assert not blocked['ok'] and 'unresolved' in blocked['error']
    assert lua.globals().SUBMISSIONS==1
    for bad in ({'x':1,'y':2},dict(args,ignoreErrors=True),dict(args,z=float('inf'))):
        with pytest.raises(ValueError):validate_build_arguments(command,bad)
        raw='a'*32+' '+command+' '+json.dumps(bad)
        assert gui['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',raw)!='Submitted; inspect log'
