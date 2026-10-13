import asyncio
from pathlib import Path
from types import SimpleNamespace
import pytest
from lupa.lua52 import LuaRuntime,LuaError
from carrier_acceptance import departure_result,nearest_order,policy
from fleet_departure import observe

ROOT=Path(__file__).resolve().parents[2]


def vehicle(ident=1,line=50,speed=1,**kw):
    return dict(id=ident,line=line,noPath=False,userStopped=False,
                motion=dict(groundAvailable=True,ground={'dyn':{'speed':speed}}),**kw)


def test_only_actual_motion_and_native_faults_gate_departure():
    snap={'vehicles':[vehicle()],'problems':[]}
    assert departure_result(snap,{1:50})['accepted']
    assert not departure_result(snap,{1:51})['accepted']
    assert not departure_result(snap,{})['accepted']
    assert not departure_result({'vehicles':[]},{1:50})['accepted']
    snap['vehicles'][0]['motion']={}
    assert not departure_result(snap,{1:50})['accepted']
    snap['vehicles'][0]=vehicle();snap['problems']=[50]
    assert not departure_result(snap,{1:50})['accepted']
    snap['problems']=[51]
    assert departure_result(snap,{1:50})['accepted']
    snap['vehicles'][0]['noPath']=True
    assert not departure_result(snap,{1:50})['accepted']


def test_air_motion_is_supported_without_return_or_cargo_checks():
    v=vehicle();v['motion']={'aircraftAvailable':True,'aircraft':{'speed':20}}
    assert departure_result({'vehicles':[v]},{1:50})['accepted']
    assert not policy()['returnTripRequired']
    assert not policy()['cargoDeliveryCountsRequired']


def test_stable_nearest_order_without_exhaustive_search():
    stops=[dict(id=str(i),position=dict(x=x,y=0)) for i,x in enumerate([0,100,20,30])]
    assert [s['id'] for s in nearest_order(stops)]==['0','2','3','1']
    assert len(stops)==4 and nearest_order([])==[]


def test_observation_exits_on_departure_and_restores_pause(tmp_path):
    class Fake:
        def __init__(self):
            self.a=SimpleNamespace(output=tmp_path);self.b=SimpleNamespace(heartbeat=lambda:{'connected':True})
            self.speed=0;self.samples=0;self.commands=[]
        async def session(self):return {'speedup':0}
        async def eval(self,code):
            assert 'resolve_native_path=false' in code
            assert 'get_vehicle_cargo' not in code
            self.samples+=1
            v=vehicle(speed=0 if self.samples==1 else 1)
            return {'state':{'speedup':self.speed},'vehicles':[v],'problems':[]}
        async def call(self,cmd,args=None):
            self.commands.append((cmd,args))
            if cmd=='set_game_speed':
                assert args['expected_speed']==self.speed
                self.speed=args['speed']
            return {'speedup':self.speed}
        async def save(self,phase):self.commands.append(('save',phase))
    fake=Fake()
    result=asyncio.run(observe(fake,[50],seconds=45,interval=.001))
    assert result['operationalAccepted'] and fake.samples==2
    assert fake.speed==0
    assert [a['speed'] for c,a in fake.commands if c=='set_game_speed']==[1,0]


@pytest.mark.parametrize('name',['fullmap_lines.lua','fullmap_fleet.lua','fullmap_vehicles.lua','fish_port_audit.lua','route_support_preview.lua'])
def test_modified_lua_parses(name):
    LuaRuntime().execute('assert(load(...))',(ROOT/'scripts'/name).read_text('utf8'))


def line_lua(existing=False,incompatible=False):
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
local CT={STATION_GROUP=1,CONSTRUCTION=2,STATION=3,NAME=4,LINE=5}
components={
 [100]={[1]={stations={10,11}}},[200]={[1]={stations={20,21}}},
 [101]={[2]={transf={cols=function()return{x=0,y=0}end},stations={10,11}}},
 [201]={[2]={transf={cols=function()return{x=100,y=0}end},stations={20,21}}}}
for _,id in ipairs({10,11,20,21})do components[id]={[3]={terminals={{transportModes={[4]=true},cargoLoad=true,cargoUnload=true,vehicleNodeId={entity=id,index=0}}}}}end
task={id='L',name='test',mode='TRUCK',endpoints={{id='A',position={x=0,y=0},loads={7}},{id='B',position={x=100,y=0},loads={}}}}
local function new()return{}end
lines={};pathCalls=0
api={type={ComponentType=CT,enum={TransportMode={TRUCK=4}},Vec3f={new=new},Line={new=new,Stop={new=new},StopConfig={new=new}}},
res={cargoTypeRep={getAll=function()return{[0]='passenger',[7]='meat'}end}},
engine={util={getPlayer=function()return 1 end,pathfinding={findPathNodeToNode=function()pathCalls=pathCalls+1;error('Unexpected path search')end}},
forEachEntityWithComponent=function(fn,ct)for id,c in pairs(components)do if c[ct]then fn(id)end end end,
getComponent=function(id,ct)return components[id] and components[id][ct]end,
system={lineSystem={getLines=function()return lines end}}},
cmd={makeLineCreateCmd=function(name,color,owner,line)return line end,sendCommand=function(line,cb)components[300]={[4]={name='test'},[5]=line};lines={300};cb(nil,true)end}}
B={json={decode=function()return task end,encode=function(x)return x end}}
''')
    if existing:
        lua.execute('''components[300]={[4]={name='test'},[5]={customFilters=true,stops={
{stationGroup=100,station=1,terminal=0,stopConfig={load={[1]=false,[8]=true},maxLoad={[1]=1,[8]=1},forceUnload=false}},
{stationGroup=200,station=1,terminal=0,stopConfig={load={[1]=false,[8]=false},maxLoad={[1]=1,[8]=1},forceUnload=false}}}}};lines={300}''')
    if incompatible:
        lua.execute('components[10][3].terminals[1].cargoLoad=false;components[11][3].terminals[1].cargoLoad=false')
    source=(ROOT/'scripts/fullmap_lines.lua').read_text('utf8').replace('TASKJSON','"task"').replace('ACTION','"build"')
    return lua,source


def test_line_build_has_no_path_search_and_preserves_existing_compatible_direction():
    for existing in (False,True):
        lua,source=line_lua(existing)
        r=lua.execute(source)
        assert r['verified'] and r['configurationVerified'] and not r['pathVerified']
        assert r['stops'][1]['station']==(1 if existing else 0)
        assert lua.globals().pathCalls==0


def test_line_build_still_rejects_incompatible_cargo_terminal():
    lua,source=line_lua(incompatible=True)
    with pytest.raises(LuaError,match='compatible cargo terminal'):lua.execute(source)
    assert len(lua.globals().lines)==0


def test_purchase_preview_needs_no_return_nodes_or_path_search():
    lua,source=line_lua(existing=True)
    lua.execute('''
api.type.ComponentType.VEHICLE_DEPOT=6;api.type.ComponentType.GAME_TIME=7
components[401]={[2]={transf={cols=function()return{x=200,y=0}end},depots={451}}}
components[451]={[6]={transportModes={[4]=true},outNodes={{entity=451,index=0}},inNodes={}}}
components[999]={[7]={gameTime=1}}
api.engine.util.getWorld=function()return 999 end
api.engine.util.getCalendarDate=function()return{year=2000}end
api.engine.system.transportVehicleSystem={getLineVehicles=function()return{}end,getDepotVehicles=function()return{}end}
api.res.modelRep={find=function()return 1 end,get=function()return{metadata={availability={yearFrom=1900,yearTo=0},transportVehicle={transportModes={4},compartments={{loadConfigs={{cargoEntry={cargoTypeSet=1}}}}}}}}end}
api.res.cargoTypeRep.hasCargoType=function(set,cargo)return cargo==7 end
task.model='truck';task.cargos={7};task.origin={x=0,y=0};task.depots={{id='D',position={x=200,y=0}}}
''')
    code=(ROOT/'scripts/fullmap_fleet.lua').read_text('utf8').replace('TASKJSON','"task"').replace('ACTION','"preview"')
    result=lua.execute(code)
    assert result['selected']['depot']==451 and not result['selected']['pathVerified']
    assert lua.globals().pathCalls==0


def test_support_preview_uses_compatible_bases_and_endpoint_maintenance_only():
    lua,_=line_lua(existing=True)
    lua.execute('''
api.type.ComponentType.VEHICLE_DEPOT=6
components[101][2].depots={};components[201][2].depots={}
components[401]={[2]={transf={cols=function()return{x=200,y=0}end},depots={451}}}
components[451]={[6]={transportModes={[4]=true},outNodes={{entity=451,index=0}},inNodes={},maintenancePool=8,catchmentArea={position={x=0,y=0},radius=50}}}
task={{id='L',mode='TRUCK',stops={{group=100,station=1,terminal=0}},positions={{x=0,y=0},{x=100,y=0}}}}
''')
    source=(ROOT/'scripts/route_support_preview.lua').read_text('utf8').replace('TASKJSON','"task"')
    result=lua.execute(source)['lines'][1]
    assert result['purchaseCandidates'][1]['depot']==451
    assert len(result['maintenanceCandidates'][1]['coveredEndpoints'])==1
    assert not result['pathVerified'] and lua.globals().pathCalls==0


def test_position_change_proves_departure_but_missing_motion_does_not():
    before=vehicle(speed=0);after=vehicle(speed=0)
    before['motion']['position']={'x':1,'y':2,'z':3}
    after['motion']['position']={'x':2,'y':2,'z':3}
    assert departure_result({'vehicles':[after]}, {1:50}, {'vehicles':[before]})['accepted']
    after['motion']['groundAvailable']=False
    assert not departure_result({'vehicles':[after]}, {1:50}, {'vehicles':[before]})['accepted']
