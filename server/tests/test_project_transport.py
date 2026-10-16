"""Receiver transport projects against native API mocks; no live game claims."""
import json

import pytest

from test_ui_consolidated import Channel
from test_e2e import SCRIPT
from test_construction_project import PID, project
from tf3_mcp.ui_log import validate_build_arguments

FIXTURE = '''
now=10;os.clock=function()return now end
components[1][5].speedup=0;components[2][6].balance=100000000
api.type.Line.StopConfig={new=function()return {}end}
api.res.cargoTypeRep={getAll=function()return {[0]="PASSENGERS",[1]="LOGS"}end}
api.type.ComponentType.STATION=30
api.type.ComponentType.MOVE_PATH=31
api.type.ComponentType.MOVE_PATH_AIRCRAFT=32
components[300][8].outNodes={123}
for _,id in ipairs({210,211})do
 components[id][30]={terminals={{passengersLoad=true,cargoLoad=false,vehicleNodeId={entity=300,index=0},personNodes={}}}}
end
api.engine.util.vehicle={getPartPrice=function()return expensiveSecond and (counts.buy or 0)>0 and 200000 or 100000 end,getPosition=function()return {x=motionX or 0,y=0,z=0}end}
api.engine.system.lineSystem.getProblemLines=function()return problems or {}end
api.cmd.makeLineUpdateCmd=function(id,config)return {kind='lineUpdate',id=id,config=config}end
local send=api.cmd.sendCommand
counts={}
api.cmd.sendCommand=function(cmd,cb)
 assert(not inUpdate or cb==nil,'Callbacks are currently disallowed')
 if cmd.kind then counts[cmd.kind]=(counts[cmd.kind] or 0)+1 end
 if cmd.kind=='lineUpdate' then components[cmd.id][3]=cmd.config;cb({},true,{});return end
 send(cmd,function(res,ok,results)
  if cmd.kind=='buy' and ok then
   local v=components[res.resultVehicleEntity][9];v.transportVehicleConfig=cmd.config;v.noPath=false
  end
  if cmd.kind=='buy' and counts.buy==2 and loseSecond then return end
  if cmd.kind=='setLine' and badAssignment then components[cmd.vehicle][9].line=-1 end
  cb(res,ok,results)
 end)
end
'''


def ref(path):return {'$ref':path}


def steps():
    line=ref('route.commit.line')
    vehicles=[ref('fleet.commit.bought.1'),ref('fleet.commit.bought.2')]
    return [
        dict(id='route',preview='create_line',arguments=dict(station_groups=[200,201],name='Project route'),max_cost=0,
             checks=[dict(command='get_entity',arguments={'id':line},expect={'id':line})]),
        dict(id='fleet',preview='buy_vehicles',arguments=dict(depot=300,model='vehicle/bus/old_bus.mdl',count=2,mode='BUS'),max_cost=200000,
             checks=[dict(command='get_entity',arguments={'id':v},expect={'id':v}) for v in vehicles]),
        dict(id='assign',preview='assign_vehicles',arguments=dict(line=line,vehicles=vehicles,stop_index=0),max_cost=0,
             checks=[dict(command='get_vehicle_motion',arguments={'vehicle':v},expect={'vehicle':v}) for v in vehicles]),
        dict(id='depart',preview='accept_departure',arguments=dict(line=line,vehicles=vehicles,seconds=45),max_cost=0,checks=[])]


def channel(tmp_path):
    c=Channel(tmp_path,FIXTURE)
    # Keep the receiving engine module alive while ticking; GUI and engine have
    # different module instances, just as in game.
    c.engine=c.lua.execute(SCRIPT.read_text(encoding='utf-8'))
    c.lua.execute('')
    c.state['hasEventSubscriptions']=c.lua.eval('function()return true end')
    c.state['subscribeToEvent']=c.lua.eval('function()end')
    return c


def execute(c,plan=None,command='execute_project'):
    args=project(plan or steps()) if command=='execute_project' else {'project_id':PID,'backup_save':'fresh_backup'}
    ticket=c.reader.prepare_build(c.log,command,args)
    assert c.game.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',ticket['input'])=='Submitted; inspect log'
    e=c.lua.globals().forwarded
    c.engine['handleEvent'](None,c.state,'',e['id'],e['name'],e['param'])
    with c.log.open('a',encoding='utf-8') as f:f.write('\n'.join(c.output)+'\n')
    c.output.clear()
    return c.reader.read(ticket['id'])['response']


def tick(c):
    c.lua.execute('inUpdate=true')
    try:c.engine['update'](None,c.state,.2)
    finally:c.lua.execute('inUpdate=false')
    e=c.lua.globals().forwarded
    if e and type(e['param']) is not str:
        c.engine['handleEvent'](None,c.state,'',e['id'],e['name'],e['param'])


def move(c,speed=10):
    c.lua.execute('''
    for _,cs in pairs(components)do if cs[9] and cs[9].line>=0 then
      cs[31]={dyn={speed=SPEED}};cs[9].state=1
    end end
    now=now+2
    '''.replace('SPEED',str(speed)))


def test_one_project_line_two_purchases_assignments_and_actual_departure(tmp_path):
    c=channel(tmp_path);r=execute(c)
    assert r['ok'] and r['result']['status']=='observing',r
    assert not r['result']['complete']
    assert c.lua.globals().counts['lineCreate']==1
    assert c.lua.globals().counts['buy']==2
    assert c.lua.globals().counts['setLine']==2
    assert c.lua.globals().components[1][5]['speedup']==1
    move(c);tick(c)
    r=c.query('get_project',{'project_id':PID})['result']
    assert r['complete'],r
    assert c.lua.globals().components[1][5]['speedup']==0
    assert c.state['v']['uiProjectActive'] is None
    assert not c.query('execute_project',project(steps()))['ok']
    assert c.lua.globals().counts['buy']==2


@pytest.mark.parametrize('mode',['timeout','fault','user_speed','reload','unknown_problem'])
def test_departure_failure_boundaries(tmp_path,mode):
    c=channel(tmp_path);r=execute(c);assert r['result']['status']=='observing',r
    if mode=='timeout':c.lua.globals().now=60
    elif mode=='fault':
        line=c.state['v']['uiProjects'][PID]['outputs']['route']['commit']['line']
        c.lua.globals().problems=c.lua.table_from([line])
    elif mode=='user_speed':c.lua.execute('components[1][5].speedup=4')
    elif mode=='reload':c.engine=c.lua.execute(SCRIPT.read_text(encoding='utf-8').replace('local NO_GUI_GENERATION = "disabled"','local NO_GUI_GENERATION = "changed"'))
    else:
        move(c);c.lua.execute('problems={{unparsed=true}};now=60')
    tick(c)
    job=c.state['v']['uiProjects'][PID]
    assert job['status']==('unknown' if mode=='reload' else 'acceptance_failed')
    assert c.lua.globals().components[1][5]['speedup']==(4 if mode=='user_speed' else 1 if mode=='reload' else 0)
    assert c.lua.globals().counts['buy']==2


def test_second_purchase_lost_callback_never_repeats(tmp_path):
    c=channel(tmp_path);c.lua.globals().loseSecond=True;r=execute(c)
    assert r['result']['status']=='unknown',r
    assert c.lua.globals().counts['buy']==2
    assert c.lua.globals().counts['setLine'] is None
    assert not c.query('resume_project',{'project_id':PID,'backup_save':'fresh_backup'})['ok']
    assert c.lua.globals().counts['buy']==2


@pytest.mark.parametrize('mutate',[
    lambda s:s[1]['arguments'].update(count=17),
    lambda s:s[1]['arguments'].update(mode='unknown'),
    lambda s:s[3]['arguments'].update(seconds=0),
    lambda s:s.append(s[0]),
    lambda s:s[0].update(max_cost=1),
])
def test_transport_plan_validation(mutate):
    s=steps();mutate(s)
    with pytest.raises(ValueError):validate_build_arguments('execute_project',project(s))


def test_timeout_resume_does_not_rebuy_or_reassign(tmp_path):
    c=channel(tmp_path);assert execute(c)['result']['status']=='observing'
    c.lua.globals().now=60;tick(c)
    assert c.state['v']['uiProjects'][PID]['status']=='acceptance_failed'
    assert execute(c,command='resume_project')['result']['status']=='observing'
    move(c);tick(c)
    assert c.state['v']['uiProjects'][PID]['status']=='complete'
    assert c.lua.globals().counts['buy']==2 and c.lua.globals().counts['setLine']==2


def test_assignment_readback_failure_does_not_resend_successful_command(tmp_path):
    c=channel(tmp_path);c.lua.globals().badAssignment=True
    r=execute(c);assert r['result']['status']=='blocked',r
    assert c.lua.globals().counts['setLine']==1
    line=c.state['v']['uiProjects'][PID]['outputs']['route']['commit']['line']
    first=c.state['v']['uiProjects'][PID]['outputs']['fleet']['commit']['bought'][1]
    c.lua.globals().components[first][9]['line']=line;c.lua.globals().badAssignment=False
    assert execute(c,command='resume_project')['result']['status']=='observing'
    assert c.lua.globals().counts['setLine']==2 and c.lua.globals().counts['buy']==2


def test_line_edit_in_same_project(tmp_path):
    c=channel(tmp_path);s=steps();line=ref('route.commit.line')
    s.insert(1,dict(id='configure',preview='preview_line_edit',arguments=dict(line=line,stops=[
        dict(station_group=g,station=0,terminal=0,loads=[0],max_load=1,force_unload=False,extra_wait=0) for g in (200,201)]),
        max_cost=0,checks=[dict(command='get_entity',arguments={'id':line},expect={'id':line})]))
    r=execute(c,s);assert r['result']['status']=='observing',r['result'].get('error',r)
    assert c.lua.globals().counts['lineUpdate']==1
    move(c);tick(c);assert c.state['v']['uiProjects'][PID]['status']=='complete'


def test_two_lines_unified_departure_waits_for_both(tmp_path):
    from copy import deepcopy
    c=channel(tmp_path);s=steps();second=deepcopy(s[:3])
    # Replace step names and references consistently, retaining identical endpoints.
    second=json.loads(json.dumps(second).replace('route','route2').replace('fleet','fleet2').replace('assign','assign2'))
    second[2]['preview']='assign_vehicles'
    departure=s[-1]
    departure['arguments']={'seconds':45,'fleets':[
        {'line':ref(name+'.commit.line'),'vehicles':[ref(fleet+'.commit.bought.1'),ref(fleet+'.commit.bought.2')]}
        for name,fleet in [('route','fleet'),('route2','fleet2')]]}
    r=execute(c,s[:3]+second+[departure]);assert r['result']['status']=='observing',r
    move(c)
    second_vehicle=c.state['v']['uiProjects'][PID]['outputs']['fleet2']['commit']['bought'][2]
    c.lua.globals().components[second_vehicle][31]['dyn']['speed']=0
    tick(c);assert c.state['v']['uiProjects'][PID]['status']=='observing'
    c.lua.globals().components[second_vehicle][31]['dyn']['speed']=10
    tick(c);assert c.state['v']['uiProjects'][PID]['status']=='complete'
    assert c.lua.globals().counts['lineCreate']==2 and c.lua.globals().counts['buy']==4


def test_requote_blocks_second_purchase_and_resume_only_buys_remaining(tmp_path):
    c=channel(tmp_path);c.lua.globals().expensiveSecond=True
    r=execute(c);assert r['result']['status']=='blocked',r
    assert c.lua.globals().counts['buy']==1
    c.lua.globals().expensiveSecond=False
    r=execute(c,command='resume_project');assert r['result']['status']=='observing',r
    assert c.lua.globals().counts['buy']==2


@pytest.mark.parametrize('state',[0,3,999])
def test_non_operating_vehicle_with_motion_is_not_departure(tmp_path,state):
    c=channel(tmp_path);assert execute(c)['result']['status']=='observing'
    move(c);c.lua.execute('for _,cs in pairs(components)do if cs[9] then cs[9].state=STATE end end;now=60'.replace('STATE',str(state)))
    tick(c);assert c.state['v']['uiProjects'][PID]['status']=='acceptance_failed'


def test_observation_survives_separate_callback_lua_instances(tmp_path):
    c=channel(tmp_path);assert execute(c)['result']['status']=='observing'
    c.engine=c.lua.execute(SCRIPT.read_text(encoding='utf-8'))
    move(c);tick(c)
    assert c.state['v']['uiProjects'][PID]['status']=='complete'


@pytest.mark.parametrize('valid',[True,False])
def test_narrow_legacy_false_epoch_recovery_requires_verified_speed_receipt(tmp_path,valid):
    c=channel(tmp_path);assert execute(c)['result']['status']=='observing'
    job=c.state['v']['uiProjects'][PID];job['status']='unknown'
    job['error']='Receiver reloaded during observation; inspect speed and results'
    if not valid:
        request=job['steps'][4]['requests'][1]['id']
        c.state['v']['uiConstruction']['requests'][request]['ok']=False
    r=c.query('cancel_project',{'project_id':PID})
    assert r['ok']==valid,r
    assert c.lua.globals().components[1][5]['speedup']==(0 if valid else 1)
    assert c.lua.globals().counts['buy']==2


@pytest.mark.parametrize('reason,paused,allowed',[
    ('Callbacks are currently disallowed',True,True),
    ('Callbacks are currently disallowed',False,False),
    ('Timeout waiting for callback',True,False),
])
def test_callback_dispatch_rejection_cancel_requires_exact_receipt_and_pause(tmp_path,reason,paused,allowed):
    c=channel(tmp_path);assert execute(c)['result']['status']=='observing'
    job=c.state['v']['uiProjects'][PID];row=job['steps'][4]
    job['status']='unknown';job['error']=reason;row['phase']='commit'
    rid='f'*32
    row['requests'][2]=c.lua.table_from(dict(id=rid,command='set_game_speed',phase='commit'))
    ledger=c.state['v']['uiConstruction'];ledger['pending']=rid
    ledger['requests'][rid]=c.lua.table_from(dict(cmd='set_game_speed',status='error',ok=False,result=reason))
    c.lua.globals().components[1][5]['speedup']=0 if paused else 1
    r=c.query('cancel_project',{'project_id':PID})
    assert r['ok']==allowed,r
    assert (c.state['v']['uiConstruction']['pending'] is None)==allowed
    assert c.lua.globals().counts['buy']==2


def test_lost_observation_event_freezes_without_resending(tmp_path):
    c=channel(tmp_path);assert execute(c)['result']['status']=='observing'
    c.engine['update'](None,c.state,.2)
    sequence=c.state['v']['uiProjects'][PID]['observationSequence']
    c.lua.globals().now=30;c.engine['update'](None,c.state,.2)
    job=c.state['v']['uiProjects'][PID]
    assert job['status']=='unknown' and job['observationSequence']==sequence
