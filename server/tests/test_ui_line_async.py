"""Existing line business handler through bounded UI/no_gui engine dispatch."""
import json

import pytest

from test_e2e import FakeGame, SCRIPT
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments


@pytest.mark.parametrize('args', [
    {'station_groups':[200], 'name':'x'},
    {'station_groups':[True,201], 'name':'x'},
    {'station_groups':[200,201]},
    {'station_groups':[200,201], 'name':'界'*27},
    {'station_groups':[200,201], 'name':'x','ignoreErrors':True},
])
def test_invalid_line_args(args, tmp_path):
    with pytest.raises(ValueError):
        validate_build_arguments('create_line',args)
    game=FakeGame(tmp_path/'bridge')
    text='a'*32+' create_line '+json.dumps(args,ensure_ascii=False)
    status=game.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',text)
    assert status!='Submitted; inspect log'
    assert len(game.lua.globals().sentCommands)==0


@pytest.mark.parametrize('deferred', [False, True])
@pytest.mark.parametrize('outcome', ['success', 'failure', 'missing_identity'])
@pytest.mark.parametrize('no_gui', [False, True])
def test_line_callback_completion_and_durable_replay(tmp_path, deferred, outcome, no_gui):
    game=FakeGame(tmp_path/'bridge');lua=game.lua
    lua.globals().defer_line=deferred
    lua.globals().line_outcome=outcome
    lua.execute('''
      api.type.Line.StopConfig={new=function()return {} end}
      api.res.cargoTypeRep={getAll=function()return {[0]="PASSENGERS",[1]="LOGS"}end}
      components[210][api.type.ComponentType.STATION]={terminals={{passengersLoad=true,cargoLoad=false}}}
      components[211][api.type.ComponentType.STATION]={terminals={{passengersLoad=true,cargoLoad=false}}}
      native_send=api.cmd.sendCommand
      line_submissions=0
      api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)
        return {event=true,id=id,name=name,param=param}
      end
      api.cmd.sendCommand=function(cmd,callback)
        if cmd.event then forwarded=cmd;return end
        if cmd.kind~="lineCreate" then return native_send(cmd,callback) end
        line_submissions=line_submissions+1
        native_send(cmd,function(data,ok,result)
          if line_outcome=="failure" then ok=false end
          if line_outcome=="missing_identity" then result={} end
          saved_callback=function()callback(data,ok,result)end
          if not defer_line then saved_callback() end
        end)
      end
    ''')
    state=lua.execute('''
      local s={value={},snapshot={},inEvent=false}
      function s:get()if self.inEvent then return self.snapshot else return self.value end end
      function s:set(v)self.value=v end
      return s
    ''')
    log=tmp_path/'stdout.txt';log.touch()
    reader=UiLogRequests();output=[]
    lua.globals().print=lambda *a:output.append(' '.join(map(str,a)))
    def flush():
        with log.open('a',encoding='utf-8') as f:f.write('\n'.join(output)+'\n')
        output.clear()
    def event(script,e):
        # Copy snapshot so the mock models native serialized state, not aliases.
        state['snapshot']=lua.eval('function(v) local function copy(t) if type(t)~="table" then return t end local o={} for k,x in pairs(t) do o[k]=copy(x) end return o end return copy(v) end')(state['value'])
        state['inEvent']=True
        script['handleEvent'](None,state,'',e['id'],e['name'],e['param'])
        state['inEvent']=False
    script=game.script
    ticket=reader.prepare_build(log,'create_line',{'station_groups':[200,201],'name':'New line'})
    if no_gui:
        generation='a'*32
        rows=[]
        lua.globals().debugPrint=lambda line:rows.append(json.loads(line.split('[TNJ_NO_GUI_V1]',1)[1])) if '[TNJ_NO_GUI_V1]' in line else None
        lua.execute('no_gui_now=1;os.clock=function()return no_gui_now end;resolveutil={loadfile=function()return function()return no_gui_payload end end}')
        text=SCRIPT.read_text(encoding='utf-8').replace('local NO_GUI_GENERATION = "disabled"',f'local NO_GUI_GENERATION = "{generation}"').replace('local NO_GUI_ON_DEMAND = false','local NO_GUI_ON_DEMAND = true')
        script=lua.execute(text);script['guiUpdate'](None,None,None)
        row=rows[-1]
        lua.globals().no_gui_payload=json.dumps(dict(generation=generation,session=row['session'],slot=row['slot'],expires=row['due']+20,kind='build',input=ticket['input']))
        lua.globals().no_gui_now=row['due'];script['guiUpdate'](None,None,None)
    else:
        assert script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',ticket['input'])=='Submitted; inspect log'
    original=lua.globals().forwarded;event(script,original);flush()
    if deferred:
        assert reader.read(ticket['id'])['status']=='pending'
        assert state['value']['uiConstruction']['pending']==ticket['id']
        fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
        event(fresh,original);flush()
        assert lua.globals().line_submissions==1
        # A distinct mutation is refused while the first result is unknown.
        other=reader.prepare_build(log,'create_line',{'station_groups':[200,201],'name':'Other'})
        fresh['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',other['input'])
        event(fresh,lua.globals().forwarded);flush()
        assert not reader.read(other['id'])['response']['ok']
        state['value']['independentMarker']='must survive'
        lua.globals().saved_callback();flush()
        assert state['value']['independentMarker']=='must survive'
    result=reader.read(ticket['id'])
    assert result['status']=='received'
    assert result['response']['ok']==(outcome=='success')
    assert (state['value']['uiConstruction']['pending'] is None)==(outcome=='success')
    fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    event(fresh,original);flush()
    lua.globals().saved_callback();flush()
    assert lua.globals().line_submissions==1
    assert reader.read(ticket['id'])==result  # no duplicate log frames
