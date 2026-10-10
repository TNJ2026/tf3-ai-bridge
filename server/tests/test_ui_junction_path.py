"""Single-query junction checks: no native path batching or error suppression."""
from pathlib import Path
import pytest
from lupa import LuaRuntime, LuaError
from tf3_mcp.ui_log import validate_build_arguments
SOURCE=Path(__file__).resolve().parents[2]/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua'
@pytest.mark.parametrize('case',['ok','reverse','empty','detour','stale','no_lanes','native_error','bad_mode'])
def test_directed_path_is_fresh_bounded_and_strict(case):
    lua=LuaRuntime(unpack_returned_tuples=True);lua.globals().case=case
    lua.execute('''
     commands={};calls=0
     api={type={enum={TransportMode={BUS=2,TRUCK=3,CAR=4}}},engine={system={streetSystem={getNodeSegments=function()return case=='stale' and {20} or {20,21}end}},util={pathfinding={findPathNodeToNode=function(a,b,m)
      calls=calls+1
      if case=='native_error'then error('native failure')end
      if case=='empty'then return {}end
      return {{{entity=a[1].entity==11 and 20 or 21,index=0}},{{entity=case=='detour' and 99 or 10,index=0}},{{entity=b[1].entity==12 and 21 or 20,index=0}}}
     end}}}}
     function getComponent(id,key)
      if key=='BASE_NODE'then return {position={x=0,y=0,z=0}}end
      if key=='BASE_EDGE'then return {node0=10,node1=id==20 and 11 or 12}end
      if key=='TRANSPORT_NETWORK'then
       local other=id==20 and 11 or 12
       return {edges={{transportModes={[2]=case~='no_lanes'},conns={{entity=other,index=0},{entity=10,index=0}}},
        {transportModes={[2]=case~='no_lanes'},conns={{entity=10,index=1},{entity=other,index=1}}}}}
      end
      if key=='BASE_NODE_CONFIG'then return {laneConnections={{segment0=20,segment1=21,lane0=0,lane1=0,withRoad=true,withTram=false}},crosswalks={20}}end
     end
    ''')
    s=SOURCE.read_text(encoding='utf-8');start=s.index(' commands.check_road_junction_path=');end=s.index(' ENGINE_COMMANDS.check_road_junction_path=true',start)
    lua.execute(s[start:end]);args=lua.table_from(dict(node=10,from_edge=21 if case=='reverse' else 20,to_edge=20 if case=='reverse' else 21,mode='AIR' if case=='bad_mode' else 'BUS'))
    if case in ['stale','no_lanes','native_error','bad_mode']:
        with pytest.raises(LuaError):lua.globals().commands.check_road_junction_path(args)
        assert lua.globals().calls==(1 if case=='native_error' else 0)
    else:
        r=lua.globals().commands.check_road_junction_path(args)
        assert lua.globals().calls==1
        assert r['directPathVerified']==(case in ['ok','reverse'])
        assert r['configurationAvailable'] and r['laneConnections'][1]['segment0']==20

def test_path_protocol_bounds():
    validate_build_arguments('check_road_junction_path',dict(node=1,from_edge=2,to_edge=3,mode='BUS'))
    with pytest.raises(ValueError):validate_build_arguments('check_road_junction_path',dict(node=-1,from_edge=2,to_edge=3,mode='BUS'))


@pytest.mark.parametrize('mode',['TRAIN','ELECTRIC_TRAIN','TRAM','ELECTRIC_TRAM'])
@pytest.mark.parametrize('direction',['forward','reverse','oneway_reverse','missing_flag_reverse','wrong_mode','stale'])
def test_rail_tram_query_respects_native_direction_and_modes(tmp_path,mode,direction):
    # Exercise the complete GUI/event protocol as well as one-query native dispatch.
    from test_ui_consolidated import Channel
    c=Channel(tmp_path, '''
      local CT=api.type.ComponentType;CT.TRANSPORT_NETWORK=998
      api.type.enum.TransportMode.TRAIN=7;api.type.enum.TransportMode.ELECTRIC_TRAIN=8
      api.type.enum.TransportMode.TRAM=5;api.type.enum.TransportMode.ELECTRIC_TRAM=6
      api.engine.system.streetSystem.getNodeSegments=function()return STALE and {90001} or {90001,90002}end
      components[90000]={[CT.BASE_NODE]={position={x=0,y=0,z=0}}}
      local a={entity=90001,index=0};local n={entity=90000,index=0};local b={entity=90002,index=0}
      for _,id in ipairs({90001,90002}) do
       components[id]={[CT.BASE_EDGE]={roadType=0,node0=90000,node1=id+10},
        [998]={edges={{transportModes={[5]=true,[6]=true,[7]=true,[8]=true},
         conns=id==90001 and {a,n} or {n,b},forwardOnly=false}}}}
      end
      pathCalls=0
      api.engine.util.pathfinding={findPathNodeToNode=function(a,b,m)
       pathCalls=pathCalls+1;lastMode=m[1]
       assert(a[1].entity~=b[1].entity)
       return {{{entity=a[1].entity,index=0}},{{entity=90000,index=0}},{{entity=b[1].entity,index=0}}}
      end}
    ''')
    if 'TRAM' in mode:
        c.lua.execute('for _,id in ipairs({90001,90002})do components[id][api.type.ComponentType.BASE_EDGE].roadType=1 end')
    if direction=='oneway_reverse':c.lua.execute('components[90001][998].edges[1].forwardOnly=true')
    if direction=='missing_flag_reverse':c.lua.execute('components[90001][998].edges[1].forwardOnly=nil')
    if direction=='wrong_mode':c.lua.execute('components[90001][998].edges[1].transportModes={}')
    if direction=='stale':c.lua.globals().STALE=True
    reverse='reverse' in direction
    r=c.query('check_network_junction_path',dict(node=90000,from_edge=90002 if reverse else 90001,to_edge=90001 if reverse else 90002,mode=mode))
    if direction in ['oneway_reverse','missing_flag_reverse','wrong_mode','stale']:
        assert not r['ok'] and c.lua.globals().pathCalls==0,r
    else:
        assert r['ok'] and r['result']['directPathVerified'],r
        assert c.lua.globals().pathCalls==1 and c.lua.globals().lastMode==c.lua.globals().api.type.enum.TransportMode[mode]
    assert c.lua.globals().dispatches==0
    assert not c.state['v']['uiConstruction']['pending']
