"""Line configuration event persistence and rejection guards; native API mocked."""
import json
import pytest
from test_e2e import FakeGame, SCRIPT
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments

ARGS=dict(line=700,stop_index=0,loads=[0],max_load=.5,force_unload=True,extra_wait=60)

@pytest.mark.parametrize('mode',['sync','deferred','lost','failure','expired','changed','complex','bad_cargo'])
def test_line_config_preview_and_single_commit(tmp_path,mode):
    g=FakeGame(tmp_path/'game');lua=g.lua
    lua.globals().mode=mode
    lua.execute('''
      now=1;os.clock=function()return now end;calls=0
      components[700]={[3]={customFilters=false,reservationPriority=1,stops={}},[10]={player=2}}
      for i=1,2 do components[700][3].stops[i]={stationGroup=199+i,station=0,terminal=0,
        waypoints={},alternativeTerminals={},maxAdditionalWaitingTime=3,
        stopConfig={load={true,true},maxLoad={1,1},forceUnload=false,destroyForConfigChange=false,destroyForRefresh=false}} end
      api.type.Line.StopConfig={new=function()return {}end}
      api.res.cargoTypeRep={getAll=function()return {[0]="PASSENGERS",[1]="COAL"}end}
      api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)return {event=true,id=id,name=name,param=param}end
      api.cmd.makeLineUpdateCmd=function(id,config)return {id=id,config=config}end
      api.cmd.sendCommand=function(cmd,cb)
       if cmd.event then forwarded=cmd;return end
       calls=calls+1
       finish=function()
        if mode~="failure" then components[cmd.id][3]=cmd.config end
        cb({},mode~="failure",{})
       end
       if mode=="sync" or mode=="failure" then finish() end
      end
    ''')
    state=lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
    log=tmp_path/'stdout.txt';log.touch();reader=UiLogRequests();output=[]
    lua.globals().print=lambda *v:output.append(' '.join(map(str,v)))
    def flush():
        with log.open('a',encoding='utf-8') as f:f.write('\n'.join(output)+'\n')
        output.clear()
    def query(cmd,args):
        ticket=reader.prepare_build(log,cmd,args)
        assert g.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',ticket['input'])=='Submitted; inspect log'
        e=lua.globals().forwarded
        fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
        fresh['handleEvent'](None,state,'',e['id'],e['name'],e['param']);flush()
        return ticket,e,reader.read(ticket['id'])
    args=dict(ARGS)
    if mode=='complex':lua.execute('components[700][3].stops[1].waypoints={17}')
    if mode=='bad_cargo':args['loads']=[250]
    _,_,preview=query('preview_line_stop',args)
    assert lua.globals().calls==0
    assert lua.globals().components[700][3]['stops'][1]['stopConfig']['maxLoad'][1]==1
    if mode in ('complex','bad_cargo'):
        assert not preview['response']['ok'];return
    assert preview['response']['ok'],preview
    token=preview['response']['result']['preview_token']
    if mode=='expired':lua.globals().now=100
    if mode=='changed':lua.execute('components[700][3].stops[2].terminal=1')
    ticket,event,result=query('commit_line_stop',{'preview_token':token})
    if mode in ('expired','changed'):
        assert not result['response']['ok'];assert lua.globals().calls==0
        _,_,again=query('commit_line_stop',{'preview_token':token})
        assert not again['response']['ok'];return
    fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    fresh['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
    assert lua.globals().calls==1
    if mode in ('deferred','lost'):
        assert result['status']=='pending'
        _,_,blocked=query('commit_line_stop',{'preview_token':token})
        assert not blocked['response']['ok']
        if mode=='lost':return
        state['v']['independent']='keep';lua.globals().finish();flush()
        assert state['v']['independent']=='keep'
        result=reader.read(ticket['id'])
    assert result['response']['ok']==(mode!='failure'),result
    assert (state['v']['uiConstruction']['pending'] is None)==(mode!='failure')
    if mode!='failure':
        stop=lua.globals().components[700][3]['stops'][1]
        assert stop['stopConfig']['load'][1] and not stop['stopConfig']['load'][2]
        assert stop['stopConfig']['maxLoad'][1]==.5 and stop['maxAdditionalWaitingTime']==60
        assert lua.globals().components[700][3]['stops'][2]['stopConfig']['maxLoad'][1]==1

@pytest.mark.parametrize('key,value',[('loads',[True]),('loads',[1,1]),('loads',list(range(9))),('max_load',1.1),('max_load',float('nan')),('extra_wait',601)])
def test_line_config_bounds(key,value):
    with pytest.raises(ValueError):validate_build_arguments('preview_line_stop',dict(ARGS,**{key:value}))
