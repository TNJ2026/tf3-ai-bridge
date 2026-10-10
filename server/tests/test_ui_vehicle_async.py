"""Bounded one-vehicle operations reuse real handlers, with mocked native effects."""
import json
import pytest
from test_e2e import FakeGame, SCRIPT
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments

CASES=[
    *[("set_game_speed",{"speed":s,"expected_speed":1},"speed") for s in (0,1,2,4)],
    ('buy_vehicles',{'depot':300,'model':'vehicle/bus/old_bus.mdl','count':1},'buy'),
    ('assign_vehicles',{'vehicles':[701],'line':700,'stop_index':0},'setLine'),
    ('set_vehicle_stopped',{'vehicle':701,'stopped':True},'stop'),
    ('set_vehicle_stopped',{'vehicle':701,'stopped':False},'stop'),
    ('send_to_depot',{'vehicle':701},'toDepot'),
    ('sell_vehicles',{'vehicles':[701]},'sell'),
    ('delete_line',{'line':700},'lineDestroy'),
]

@pytest.mark.parametrize('vehicle,index',[(701,1),(9999,0)])
def test_assignment_preflight_rejects_stale_vehicle_or_stop(tmp_path,vehicle,index):
    g=FakeGame(tmp_path/'game');lua=g.lua
    lua.execute('''
      components[700]={[3]={stops={{stationGroup=200}}},[10]={player=2}}
      components[701]={[9]={carrier=0,state=0,depot=300,line=-1},[10]={player=2}}
      api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)return {id=id,name=name,param=param}end
      api.cmd.sendCommand=function(cmd,cb)forwarded=cmd end
    ''')
    state=lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
    output=[];lua.globals().print=lambda *v:output.append(' '.join(map(str,v)))
    log=tmp_path/'stdout.txt';log.touch();reader=UiLogRequests()
    t=reader.prepare_build(log,'assign_vehicles',{'vehicles':[vehicle],'line':700,'stop_index':index})
    g.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',t['input'])
    e=lua.globals().forwarded
    g.script['handleEvent'](None,state,'',e['id'],e['name'],e['param'])
    log.write_text('\n'.join(output)+'\n',encoding='utf-8')
    assert not reader.read(t['id'])['response']['ok']
    assert lua.globals().forwarded==e or lua.globals().forwarded['name']==e['name']
    assert state['v']['uiConstruction']['requests'][t['id']]['status']=='rejected'
    assert state['v']['uiConstruction']['pending'] is None

@pytest.mark.parametrize('command,args',[
    ('buy_vehicles',{'depot':300,'model':'bus','count':2}),
    ('buy_vehicles',{'depot':300,'model':'bus','count':1,'line':700}),
    ('buy_vehicles',{'depot':300,'model':'bus','count':True}),
    ('assign_vehicles',{'vehicles':[701,702],'line':700,'stop_index':0}),
    ('assign_vehicles',{'vehicles':[701],'line':700,'stop_index':-1}),
    ('assign_vehicles',{'vehicles':{'1':701,'x':702},'line':700,'stop_index':0}),
    ('set_vehicle_stopped',{'vehicle':701,'stopped':1}),
    ('send_to_depot',{'vehicle':701,'sell_on_arrival':True}),
])
def test_host_and_lua_vehicle_argument_bounds(tmp_path,command,args):
    with pytest.raises(ValueError):validate_build_arguments(command,args)
    g=FakeGame(tmp_path/'game')
    status=g.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request','a'*32+' '+command+' '+json.dumps(args))
    assert status!='Submitted; inspect log' and len(g.lua.globals().sentCommands)==0

@pytest.mark.parametrize('command,args,native_kind',CASES)
@pytest.mark.parametrize('mode',['sync','deferred','rejected','lost'])
def test_demand_vehicle_callbacks_and_replay(tmp_path,command,args,native_kind,mode):
    game=FakeGame(tmp_path/'game');lua=game.lua
    lua.globals().test_kind=native_kind;lua.globals().callback_mode=mode
    lua.execute('''
      components[700]={[3]={stops={{stationGroup=200},{stationGroup=201}}},[1]={name="test"},[10]={player=2}}
      components[701]={[9]={carrier=0,state=0,depot=300,line=-1,userStopped=false},[10]={player=2}}
      mutation_calls=0;headless_now=1;os.clock=function()return headless_now end
      resolveutil={loadfile=function()return function()return headless_payload end end}
      local old=api.cmd.sendCommand
      api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)return {event=true,id=id,name=name,param=param}end
      api.cmd.sendCommand=function(cmd,cb)
        if cmd.event then forwarded=cmd;return end
        if cmd.kind~=test_kind then return old(cmd,cb) end
        mutation_calls=mutation_calls+1
        old(cmd,function(data,ok,result)
          if callback_mode=="rejected" then ok=false end
          finish_callback=function()cb(data,ok,result)end
          if callback_mode=="sync" or callback_mode=="rejected" then finish_callback() end
        end)
      end
    ''')
    generation='b'*32
    text=SCRIPT.read_text(encoding='utf-8').replace('local HEADLESS_GENERATION = "disabled"',f'local HEADLESS_GENERATION = "{generation}"').replace('local HEADLESS_ON_DEMAND = false','local HEADLESS_ON_DEMAND = true')
    script=lua.execute(text);state=lua.execute('local s={value={}};function s:get()return self.value end;function s:set(v)self.value=v end;return s')
    rows=[];output=[]
    lua.globals().debugPrint=lambda line:rows.append(json.loads(line.split('[TNJ_HEADLESS_V1]',1)[1])) if '[TNJ_HEADLESS_V1]' in line else None
    lua.globals().print=lambda *v:output.append(' '.join(map(str,v)))
    log=tmp_path/'stdout.txt';log.touch();reader=UiLogRequests()
    ticket=reader.prepare_build(log,command,args)
    script['guiUpdate'](None,None,None);row=rows[-1]
    lua.globals().headless_payload=json.dumps(dict(generation=generation,session=row['session'],slot=row['slot'],expires=row['due']+20,kind='build',input=ticket['input']))
    lua.globals().headless_now=row['due'];script['guiUpdate'](None,None,None)
    e=lua.globals().forwarded
    def event(module,event):module['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
    def flush():
        with log.open('a',encoding='utf-8') as f:f.write('\n'.join(output)+'\n')
        output.clear()
    event(script,e);flush()
    fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'));event(fresh,e);flush()
    assert lua.globals().mutation_calls==1
    if mode in ('deferred','lost'):
        assert reader.read(ticket['id'])['status']=='pending'
        assert state['value']['uiConstruction']['pending']==ticket['id']
        blocked=reader.prepare_build(log,command,args)
        fresh['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',blocked['input'])
        event(fresh,lua.globals().forwarded);flush()
        assert not reader.read(blocked['id'])['response']['ok']
        assert lua.globals().mutation_calls==1
        if mode=='lost':
            recovery=reader.prepare_build(log,'reconcile_depot_rejection',{'request_id':ticket['id']})
            fresh['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',recovery['input'])
            event(fresh,lua.globals().forwarded);flush()
            assert not reader.read(recovery['id'])['response']['ok']
            assert state['value']['uiConstruction']['pending']==ticket['id']
            assert lua.globals().mutation_calls==1
            return
        state['value']['unrelated']='retained';lua.globals().finish_callback();flush()
        assert state['value']['unrelated']=='retained'
    response=reader.read(ticket['id'])['response']
    assert response['ok']==(mode!='rejected'),response
    assert (state['value']['uiConstruction']['pending'] is None)==(mode!='rejected')
    if command=='set_game_speed' and response['ok']:
        assert response['result']=={'speedup':args['speed'],'previousSpeed':1,'verified':True}
    if command=='buy_vehicles' and response['ok']:
        vehicle=response['result']['bought'][0]
        assert lua.globals().components[vehicle][9]['line']==-1  # buy never assigns implicitly
    if command=='assign_vehicles' and response['ok']:assert lua.globals().components[701][9]['line']==700
    if command=='set_vehicle_stopped' and response['ok']:assert lua.globals().components[701][9]['userStopped']==args['stopped']
    assert lua.globals().mutation_calls==1

    if mode=='rejected':
        recovery=reader.prepare_build(log,'reconcile_depot_rejection',{'request_id':ticket['id']})
        fresh['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',recovery['input'])
        event(fresh,lua.globals().forwarded);flush()
        reply=reader.read(recovery['id'])['response']
        assert reply['ok']==(command=='send_to_depot'),reply
        assert (state['value']['uiConstruction']['pending'] is None)==(command=='send_to_depot')
        if reply['ok']:
            assert reply['result']['retryAllowed'] is False
            assert state['value']['uiConstruction']['requests'][ticket['id']]['status']=='reconciled_rejected'
            event(fresh,e);flush()  # original rejected command remains suppressed
            again=reader.prepare_build(log,'reconcile_depot_rejection',{'request_id':ticket['id']})
            fresh['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',again['input'])
            event(fresh,lua.globals().forwarded);flush()
            assert not reader.read(again['id'])['response']['ok']
        assert lua.globals().mutation_calls==1


@pytest.mark.parametrize('motion',['none','ground','aircraft'])
def test_vehicle_motion_is_bounded_readonly(tmp_path,motion):
    game=FakeGame(tmp_path/'game');lua=game.lua
    lua.execute("""
      components[701]={[9]={carrier=0,state=1,depot=300,line=700},[10]={player=2}}
      api.type.ComponentType.MOVE_PATH=901
      api.type.ComponentType.MOVE_PATH_AIRCRAFT=902
      position_calls=0
      api.engine.util.vehicle=api.engine.util.vehicle or {}
      api.engine.util.vehicle.getPosition=function(id)
        assert(id==701);position_calls=position_calls+1;return {x=1,y=2,z=3}
      end
    """)
    if motion=='ground':
        lua.execute('components[701][901]={state=1,blocked=42,dyn={speed=0,timeStanding=50},path={secret=999}}')
    if motion=='aircraft':
        lua.execute('components[701][902]={speed=4,aircraftState={flightState=2,waitingDistance=30},path0={secret=999}}')
    validate_build_arguments('get_vehicle_motion',{'vehicle':701})
    result=game.script['_internal']['commands']['get_vehicle_motion'](lua.table_from({'vehicle':701}))
    assert result['groundAvailable']==(motion=='ground')
    assert result['aircraftAvailable']==(motion=='aircraft')
    if motion=='ground':
        assert result['ground']['dyn']['timeStanding']==50
        assert result['ground']['path']['edgeCount'] is None
    if motion=='aircraft':
        assert result['aircraft']['flight']['waitingDistance']==30
        assert result['aircraft']['path0'] is None
    assert len(lua.globals().sentCommands)==0
    assert lua.globals().position_calls==(0 if motion=='none' else 1)


@pytest.mark.parametrize('tuple_base',[0,1,'named'])
@pytest.mark.parametrize('index,count',[(0,5),(4,5),(5,5),(-1,5),(0,0)])
def test_motion_path_is_bounded_and_indexes_zero_based(tmp_path,index,count,tuple_base):
    game=FakeGame(tmp_path/'game');lua=game.lua
    lua.globals().path_index=index;lua.globals().path_count=count;lua.globals().tuple_base=tuple_base
    lua.execute("""
      api.type.ComponentType.MOVE_PATH=901
      api.type.ComponentType.MOVE_PATH_AIRCRAFT=902
      local edges={}
      for i=1,path_count do
        if tuple_base=="named" then edges[i]={first={entity=100+i,index=i-1},second=i%2==0}
        else edges[i]={[tuple_base]={entity=100+i,index=i-1},[tuple_base+1]=i%2==0} end
      end
      components[701]={[9]={state=1},[901]={path={edges=edges,endOffset=1},dyn={pathPos={edgeIndex=path_index,pos=12,pos01=0.5},speed=0}}}
      api.engine.util.vehicle=api.engine.util.vehicle or {}
      api.engine.util.vehicle.getPosition=function()return {x=1,y=2,z=3}end
    """)
    result=game.script['_internal']['commands']['get_vehicle_motion'](lua.table_from({'vehicle':701}))
    path=result['ground']['path']
    assert path['edgeCount']==count
    valid=0<=index<count
    assert path['currentEdgeAvailable']==valid
    if valid:
        rows=list(path['samples'].values())
        expected=list(dict.fromkeys([index,min(index+1,count-1),count-1]))
        assert [r['pathIndex'] for r in rows]==expected
        assert [r['edge']['entity'] for r in rows]==[101+i for i in expected]
        assert len(rows)<=3
        assert all(r['available'] and r['tupleBase']==tuple_base for r in rows)
    else:assert path['samples'] is None
    assert len(lua.globals().sentCommands)==0
