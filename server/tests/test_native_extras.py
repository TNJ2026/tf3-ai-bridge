"""Actual Lua GUI/event dispatch with native mocks; no live-game acceptance claim."""
import asyncio
import inspect
import json

import pytest

from test_ui_consolidated import Channel
from test_no_gui import host, GEN
from tf3_mcp.native_extras import SCHEMAS, ENGINE_READS, GUI_READS, register
from tf3_mcp.ui_log import validate_build_arguments
from tf3_mcp.no_gui import TAG

FIXTURE = r'''
extrasCalls={};function record(name,...)extrasCalls[#extrasCalls+1]={name=name,args={...}} end
local function effect(name)return function(...)record(name,...)end end
components[701]={[api.type.ComponentType.TRANSPORT_VEHICLE]={}}
components[700]={[api.type.ComponentType.LINE]={stops={{},{}}}}
api.type.Vec2f={new=function(x,y)return {x=x,y=y}end}
api.type.Vec3f={new=function(x,y,z)return {x=x,y=y,z=z}end}
api.type.Vec4f={new=function(x,y,z,w)return {x=x,y=y,z=z,w=w}end}
api.type.EmissionGrid={Type={Noise=0,Pollution=1}}
api.gui={
 camera={focusEntity=effect('focus'),focusPosition=effect('position'),followEntity=effect('follow'),
  enterFollowCameraCockpit=effect('cockpit'),leaveFollowCameraCockpit=effect('leave'),takeScreenshot=effect('screenshot'),
  getEye=function()return {x=1,y=2,z=3}end,getCenter=function()return {x=4,y=5,z=6}end,getFollowEntity=function()return {701,3}end},
 mission={setMarkerAtPosition=effect('marker'),removeMarker=effect('remove_marker'),setZoneCircle=effect('circle'),removeZone=effect('remove_circle'),
  setMovePathVisualizationAtEntity=effect('path'),removeMovePathVisualization=effect('remove_path'),playCutscene=effect('cutscene'),
  isCutscenePlaying=function()return false end,getCutsceneElapsedTime=function()return 0 end},
 HighlightStyle={Circle=1,Square=2,Mask=3},byId={setHighlighted=effect('highlight')},
 guide={GuideTarget={new=function(t)return {idOrTag=t}end},trySpawnGuideById=function(...)record('guide',...);return false end,resetGuide=effect('reset')},
 spawnEphemeralHudImage=effect('icon'),sound={letVehicleHorn=effect('horn'),playRandomSoundEffect=effect('sound')},
 voiceOverManager={play=effect('voice'),stop=effect('stop_voice'),isPlayingAny=function()return false end,getPlaying=function()return '' end},
 benchMark={}
}
for _,m in ipairs({'getBeginFrameTimes','getEventTimes','getCoreStepTimes','getRenderTimes','getSwapTimes'})do api.gui.benchMark[m]=function()return {10,20,30}end end
for _,m in ipairs({'getReplicateTimes','getCommandTimes','getGameStepTimes'})do api.gui.benchMark[m]=function()return {{frameTime=10,gameTime=20}}end end
api.engine.system.landVehicleMoveSystem={getBlockedTrains=function()return {{701,702},{703,704}}end}
api.engine.system.lineSystem.getBestLineAssignment=function(id,line,allow)
 assert(id==700 and #line.stops==2 and allow==true);return {{station=0,terminal=1},{station=1,terminal=0}} end
api.engine.system.simPersonSystem={getSimPersonsForDestination=function(id)assert(id==100);return {33,22,11}end}
api.engine.system.emissionGridSystem={getInterpolatedEmission=function(pos,avg,kind)
 assert(pos.x==10 and pos.y==20 and avg==true);return kind==0 and 0 or 12.5 end}
'''


def arguments(command):
    values = dict(entity=701, vehicle=701, line=700, destination=100, x=10, y=20, z=0,
                  distance=300, key='test', marker_type='native-test', scaling=1,
                  radius=6000, r=0, g=1, b=0, alpha=.3, target='test-id',
                  highlighted=True, style='Circle', tooltip='提示', caption='测试',
                  icon='::/ui/test.tga', resource='::/test/resource', duration=5,
                  delay=0, resolve_language=False, scale=1, limit=2, offset=0,
                  jump=True, allow_terminal_changes=True, use_average=True)
    return {key: values[key] for key in SCHEMAS[command]}


class ExtrasChannel(Channel):
    def gui_query(self, command, args):
        ticket = self.reader.prepare_build(self.log, command, args)
        status = self.game.script['guiHandleEvent'](None, None, None, '', 'tnj_bridge_readonly', 'tnj_bridge_readonly.request', ticket['input'])
        assert status == 'Result logged', status
        with self.log.open('a', encoding='utf-8') as f:
            f.write('\n'.join(self.output) + '\n')
        self.output.clear()
        return ticket, self.reader.read(ticket['id'])['response']


@pytest.mark.parametrize('command', SCHEMAS)
def test_all_tools_route_and_execute(tmp_path, command):
    c = ExtrasChannel(tmp_path, FIXTURE)
    result = c.query(command, arguments(command)) if command in ENGINE_READS else c.gui_query(command, arguments(command))[1]
    assert result['ok'], result
    assert c.lua.globals().dispatches == 0  # no native world mutation commands
    if command == 'set_map_circle':
        args = c.lua.globals().extrasCalls[1]['args']
        assert args[1] == 'tnj_mcp_extras_test' and args[6] is False
        assert result['result']['prohibitBuilding'] is False
    if command == 'show_game_guide':
        assert result['result']['shown'] is False
    if command == 'sample_environment':
        assert result['result']['fields']['noise']['value'] == 0
        assert result['result']['fields']['pollution']['value'] == 12.5
    if command == 'get_destination_persons':
        assert result['result']['items'] == [11, 22]
        assert result['result']['nextOffset'] == 2
    if command == 'get_game_performance':
        assert result['result']['fields']['guiUpdate']['value']['samples'] == [10, 20]
        assert result['result']['fields']['simulation']['value']['samples'][0]['gameTime'] == 20


@pytest.mark.parametrize('command', SCHEMAS)
def test_host_and_receiver_reject_unknown_fields(tmp_path, command):
    bad = dict(arguments(command), arbitrary_function='destroy')
    with pytest.raises(ValueError):
        validate_build_arguments(command, bad)
    c = ExtrasChannel(tmp_path, FIXTURE)
    text = 'a' * 32 + ' ' + command + ' ' + json.dumps(bad)
    status = c.game.script['guiHandleEvent'](None, None, None, '', 'tnj_bridge_readonly', 'tnj_bridge_readonly.request', text)
    assert 'Invalid extras argument' in status
    assert len(c.lua.globals().extrasCalls) == 0


@pytest.mark.parametrize('command,key,bad', [
    ('focus_game_entity','entity', True), ('focus_game_entity','entity',-1),
    ('focus_game_position','x',float('inf')), ('focus_game_position','distance',0),
    ('take_game_screenshot','scale',5), ('get_game_performance','limit',201),
    ('set_map_circle','alpha',1.1), ('show_entity_hud_icon','duration',61),
    ('set_map_marker','key','../another'), ('play_game_sound','resource','C:/sound.wav'),
    ('play_game_sound','resource','::/../sound'), ('play_game_sound','resource','::/a//b'),
    ('highlight_game_ui','style','Unknown'), ('get_blocked_trains','offset',0.5),
])
def test_argument_boundaries(command,key,bad):
    args=arguments(command);args[key]=bad
    with pytest.raises(ValueError):validate_build_arguments(command,args)


def test_missing_native_functions_and_partial_values(tmp_path):
    c=ExtrasChannel(tmp_path,FIXTURE)
    c.lua.execute('api.gui.camera.focusEntity=nil;api.gui.benchMark.getRenderTimes=nil;api.gui.camera.getCenter=function()error("unavailable")end')
    _,r=c.gui_query('get_native_extras_capabilities',{})
    assert not r['result']['tools']['focus_game_entity']['available']
    _,r=c.gui_query('focus_game_entity',{'entity':701})
    assert not r['ok'] and 'unavailable' in r['error']
    _,r=c.gui_query('get_game_performance',{'limit':2})
    assert not r['result']['complete'] and not r['result']['fields']['render']['available']
    assert r['result']['fields']['simulation']['available']
    _,r=c.gui_query('get_game_camera',{})
    assert not r['result']['complete'] and r['result']['fields']['eye']['available']


def test_missing_entity_and_replay_never_repeat_effect(tmp_path):
    c=ExtrasChannel(tmp_path,FIXTURE)
    _,r=c.gui_query('focus_game_entity',{'entity':999999})
    assert not r['ok'] and len(c.lua.globals().extrasCalls)==0
    ticket,r=c.gui_query('sound_vehicle_horn',{'vehicle':701})
    assert r['ok']
    status=c.game.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',ticket['input'])
    assert status.startswith('Duplicate') and len(c.lua.globals().extrasCalls)==1


@pytest.mark.parametrize('command', SCHEMAS)
def test_old_receiver_rejected_before_publish(host,command):
    with pytest.raises(ValueError,match='nativeExtrasVersion'):
        host.send(command,arguments(command),kind='build',expected_session='session')
    assert not host.ledger.exists()
    assert (host.mod/'no_gui'/GEN/'1.lua').read_bytes()==b'return ""\n'


def test_typed_mcp_registration_matches_wire_contract():
    class MCP:
        def __init__(self):self.tools={}
        def tool(self):
            def add(fn):self.tools[fn.__name__]=fn;return fn
            return add
    async def call(command,**args):
        validate_build_arguments(command,args)
        return command,args
    m=MCP();register(m,call)
    assert m.tools.keys()==SCHEMAS.keys()
    for command,fn in m.tools.items():
        supplied=arguments(command)
        required={k:v for k,v in supplied.items() if inspect.signature(fn).parameters[k].default is inspect.Parameter.empty}
        result=asyncio.run(fn(**required))
        assert result[0]==command


def test_native_accessors_are_lazy_and_report_missing_paths(tmp_path):
    c=ExtrasChannel(tmp_path,FIXTURE)
    c.lua.execute('api.gui.camera.getEye=nil')
    _,response=c.gui_query('get_native_extras_capabilities',{})
    row=response['result']['tools']['get_game_camera']
    assert not row['available']
    assert row['diagnostics']['gui.camera.getEye']['valueType']=='nil'
    c.lua.execute('api.gui.camera.getEye=function()return {x=10,y=20,z=30}end')
    _,response=c.gui_query('get_game_camera',{})
    assert response['result']['fields']['eye']['value']==dict(x=10,y=20,z=30)


@pytest.mark.parametrize('command', SCHEMAS)
def test_native_callable_tables_with_hidden_metatables(tmp_path, command):
    c=ExtrasChannel(tmp_path,FIXTURE)
    c.lua.execute("""
      local seen={}
      local function wrap(t)
       if type(t)~='table' or seen[t] then return end
       seen[t]=true
       for k,v in pairs(t)do
        if type(v)=='function' then
         local f=v;t[k]=setmetatable({}, {__metatable='native',__call=function(_,...)return f(...)end})
        elseif type(v)=='table' then wrap(v)end
       end
      end
      wrap(api.gui);wrap(api.engine.system)
      wrap(api.type.Vec2f);wrap(api.type.Vec3f);wrap(api.type.Vec4f)
    """)
    result=c.query(command,arguments(command)) if command in ENGINE_READS else c.gui_query(command,arguments(command))[1]
    assert result['ok'],result
    if command=='get_native_extras_capabilities':
        assert all(row['available'] for row in result['result']['tools'].values())
    if command in {'get_game_camera','get_game_performance','get_game_voiceover','get_game_cutscene','sample_environment'}:
        assert result['result']['complete']
    assert c.lua.globals().dispatches==0
