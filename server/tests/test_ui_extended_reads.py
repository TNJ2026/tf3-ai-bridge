"""Extended read transport, including snapshots across engine module recreation."""
import pytest
from test_e2e import FakeGame, SCRIPT
from tf3_mcp.ui_log import UiLogRequests
from test_facilities import FIXTURE as FACILITIES
from test_industries import FIXTURE as INDUSTRIES
from test_prospections import FIXTURE as PROSPECTIONS
from test_loans import FIXTURE as LOANS
from test_subventions import FIXTURE as SUBVENTIONS
from test_town_cargo_needs import FIXTURE as TOWN_CARGO
from test_map_layers import runtime as map_runtime
from test_terrain_flatten import terrain_game

@pytest.fixture
def query(tmp_path,request):
    g=FakeGame(tmp_path/'game');lua=g.lua
    command=getattr(request.node,'callspec',None)
    command=command.params.get('command') if command else None
    if command in ('get_map_data','get_terrain_tile'):
        lua,_=request.getfixturevalue('map_runtime')
    elif command in ('get_terrain','get_terrain_grid','get_terrain_operation_capabilities'):
        lua,_=request.getfixturevalue('terrain_game')
    elif command=='list_facility_resources':lua.execute(FACILITIES)
    elif command=='list_industry_resources':lua.execute(FACILITIES);lua.execute(INDUSTRIES)
    elif command in ('list_prospections','get_prospections'):lua.execute(PROSPECTIONS)
    elif command=='get_loans':lua.execute(LOANS)
    elif command=='get_subventions':lua.execute(SUBVENTIONS)
    elif command=='get_town_cargo_needs':lua.execute(TOWN_CARGO)
    elif command=='get_vehicle_motion':
        lua.execute("""
          api.type.ComponentType.MOVE_PATH=901
          api.type.ComponentType.MOVE_PATH_AIRCRAFT=902
          components[701]={[9]={state=1},[901]={path={edges={{{entity=88,index=0},true}},endOffset=0},dyn={pathPos={edgeIndex=0,pos=3,pos01=0.2},speed=2}}}
          api.engine.util.vehicle=api.engine.util.vehicle or {}
          api.engine.util.vehicle.getPosition=function(id)assert(id==701);return {x=1,y=2,z=3}end
        """)
    elif command=='list_cargo_types':lua.execute('api.res.cargoTypeRep={getAll=function()return {[0]="PASSENGERS",[1]="COAL"}end}')
    gui=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    lua.execute('''
     api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)return {id=id,name=name,param=param}end
     api.cmd.sendCommand=function(cmd,cb)forwarded=cmd end
    ''')
    state=lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
    log=tmp_path/'stdout.txt';log.touch();reader=UiLogRequests();output=[]
    lua.globals().print=lambda *v:output.append(' '.join(map(str,v)))
    def call(cmd,args):
        ticket=reader.prepare_build(log,cmd,args)
        assert gui['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',ticket['input'])=='Submitted; inspect log'
        e=lua.globals().forwarded;fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
        fresh['handleEvent'](None,state,'',e['id'],e['name'],e['param'])
        with log.open('a',encoding='utf-8') as f:f.write('\n'.join(output)+'\n')
        output.clear()
        return reader.read(ticket['id'])['response']
    call.lua=lua
    return call

@pytest.mark.parametrize('command,args',[
 ('get_vehicle_motion',{'vehicle':701}),('list_cargo_types',{}),('get_terrain',{'x':0,'y':0}),
 ('find_nearby',{'x':0,'y':0,'radius':100,'limit':2}),
 ('list_facility_resources',{'limit':2}),('list_industry_resources',{}),
 ('list_prospections',{}),('get_prospections',{}),('get_loans',{}),
 ('get_subventions',{'assess':True}),('get_terrain_operation_capabilities',{}),
 ('get_terrain_grid',{'x':0,'y':0,'spacing':10,'columns':2,'rows':2,'limit':4}),
 ('get_map_data',{}),('get_terrain_tile',{'tile_x':-1,'tile_y':-1}),
 ('get_town_cargo_needs',{'town':100}),
])
def test_extended_read_event(query,command,args):
    response=query(command,args)
    assert response['ok'],response

def test_fixed_map_snapshot_survives_event_module_recreation(query):
    first=query('list_map_entities',{'kind':'TOWN','limit':1,'snapshot':'new'})
    assert first['ok'],first
    token=first['result']['snapshot']
    second=query('list_map_entities',{'kind':'TOWN','limit':1,'offset':1,'snapshot':token})
    assert second['ok'] and second['result']['snapshot']==token,second
    released=query('release_map_snapshot',{'snapshot':token})
    assert released['ok'],released
    old=query('list_map_entities',{'kind':'TOWN','limit':1,'snapshot':token})
    assert not old['ok']

@pytest.mark.parametrize('command,args,setup',[
 ('delete_line',{'line':700},'components[701][9].line=700'),
 ('delete_line',{'line':700},'components[700][10].player=99'),
 ('sell_vehicles',{'vehicles':[701]},'components[701][9].state=1'),
 ('sell_vehicles',{'vehicles':[701]},'components[701][10].player=99'),
 ('sell_vehicles',{'vehicles':[701]},'api.engine.system.transportVehicleSystem.getDepotVehicles=function()return {}end'),
])
def test_cleanup_preflight_rejects_without_dispatch(query,command,args,setup):
    query.lua.execute('''
      components[700]={[3]={stops={}},[10]={player=2}}
      components[701]={[9]={state=0,line=-1,depot=300},[10]={player=2}}
    ''')
    query.lua.execute(setup)
    response=query(command,args)
    assert not response['ok'],response
    assert query.lua.globals().forwarded['name']=='tnj_bridge_build.request'
