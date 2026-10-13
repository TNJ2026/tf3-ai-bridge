"""Exercise the real frontage proposal builder with deterministic native geometry."""
from pathlib import Path
import json
import pytest
from lupa import LuaRuntime, LuaError
from tf3_mcp.ui_log import validate_build_arguments

SOURCE=Path(__file__).resolve().parents[2]/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua'

@pytest.fixture
def frontage():
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
      function V3(x,y,z)return {x=x,y=y,z=z}end
      function listOf(t)return t end
      function toPlain(t)return t end
      function isFrozenStreetNode(id)return frozen==id end
      function constructionOfEdge(id)return nil end
      function ownerOf(id)return 1 end
      function nodePosition(id)return nodes[id].position end
      nodes={[10]={position=V3(0,0,1)},[11]={position=V3(-40,0,1)},[12]={position=V3(40,0,1)}}
      edges={}
      for i,pair in ipairs({{11,10},{10,12}})do
       edges[20+i]={node0=pair[1],node1=pair[2],position0=nodes[pair[1]].position,position1=nodes[pair[2]].position,
        tangent0=V3(40,0,.1),tangent1=V3(40,0,.1),type=0,roadType=1,objects={},roadTemplate='road',roadStyle=0,laneConfigs={},roadDevelopmentLocked=false}
      end
      configs={}
      for _,id in ipairs({10,11,12})do configs[id]={laneConnections={{segment0=21,segment1=22,lane0=1,lane1=2,withRoad=true,withTram=false}},
       crosswalks={21,22},trafficLightConfig={states={},trafficLightType=0},trafficLightPreference=0,doubleSlipSwitch=false}end
      function getComponent(id,key)
       if key=='BASE_NODE'then return nodes[id]elseif key=='BASE_EDGE'then return edges[id]elseif key=='BASE_NODE_CONFIG'then return configs[id]end
      end
      api={engine={util={getPlayer=function()return 1 end},system={streetSystem={getNodeSegments=function(id)
       if id==10 then return {21,22}elseif id==11 then return extra and {21,99}or{21}else return {22}end
      end}}},type={enum={RoadType={STREET=1},BaseEdgeType={NORMAL=0}}}}
      for _,name in ipairs({'SegmentAndEntity','NodeAndEntity','BaseNodeLaneConnectionAndEntity'})do api.type[name]={new=function()return {comp={}}end}end
      api.type.LaneConnection={new=function()return {}end}
      previews=0
      function previewProposal(p)
       previews=previews+1
       local port=changed and previews==2 and -9 or -8
       local geometry={transportModes={[2]=true,[3]=true,[4]=true},conns={{entity=port},{entity=-7}},
        geometry={cubicSpline={pos={V3(0,0,1),V3(0,10,1)}},height={x=height or 1,y=1}}}
       local ci={collisionEntities={}}
       if removal and previews==2 then ci.removableModules={123}end
       return {ok=not blocked,critical=fatal and previews==2 or false}, {entity2tn={[port]={edges={geometry}}},collisionInfo=ci}
      end
    ''')
    source=SOURCE.read_text(encoding='utf-8')
    codec=source[source.index('local json = {}'):source.index('-- environment probe')]
    lua.globals().json=lua.execute(codec+'\nreturn json')
    helper=source[source.index('local frontageAdapter={}'):source.index('local function placeConstruction(')]
    adapter=lua.execute(helper+'\nreturn frontageAdapter')
    return lua,adapter

def test_frontage_preserves_and_remaps_outer_config(frontage):
    lua,a=frontage
    proposal=lua.eval('{streetProposal={}}')
    p,result,check=a['bind'](proposal,10)
    assert check['ok']
    street=p['streetProposal']
    assert len(street['nodesToAdd'])==0
    assert street['edgesToAdd'][1]['comp']['node1']==-8
    assert street['edgesToAdd'][2]['comp']['node0']==-8
    assert set(street['edgesToRemove'].values())=={21,22}
    assert set(street['nodeConfigsToRemove'].values())=={10,11,12}
    assert set(v['entity'] for v in street['nodeConfigsToAdd'].values())=={11,12}
    for v in street['nodeConfigsToAdd'].values():
        assert v['comp']['laneConnections'][1]['segment0']==-3
        assert v['comp']['laneConnections'][1]['segment1']==-4
        assert list(v['comp']['crosswalks'].values())==[-3,-4]
    assert lua.globals().configs[11]['laneConnections'][1]['segment0']==21
    assert result['connectionsVerified'] is False


def test_exact_native_entrance_does_not_duplicate_a_placeholder(frontage):
    """Model the native rejection seen at all three Hengshui road nodes."""
    lua,a=frontage
    lua.execute('''
      local original=previewProposal
      function previewProposal(p)
       -- The construction contributes a node exactly at (0,0,1).
       local removesOriginal=false
       for _,id in ipairs(p.streetProposal.nodesToRemove or {})do if id==10 then removesOriginal=true end end
       if not removesOriginal then return {critical=true,ok=false,messages={'coincident existing node'}},{entity2tn={}} end
       for _,n in ipairs(p.streetProposal.nodesToAdd or {}) do
        local v=n.comp.position
        if v.x==0 and v.y==0 and v.z==1 then
         return {critical=true,ok=false,messages={'duplicate base nodes'}},nil
        end
       end
       if previews==0 then
        assert(p.streetProposal.nodesToRemove[1]==10,'discovery must remove the coincident real node')
        assert(#p.streetProposal.nodesToAdd==1 and p.streetProposal.nodesToAdd[1].comp.position.x==-2)
        assert(p.streetProposal.edgesToAdd[1].comp.node1==-2)
        assert(p.streetProposal.edgesToAdd[2].comp.node0==-2)
       else
        assert(p.streetProposal.nodesToRemove[1]==10)
        assert(p.streetProposal.edgesToAdd[1].comp.node1==-8)
        assert(p.streetProposal.edgesToAdd[2].comp.node0==-8)
       end
       return original(p)
      end
    ''')
    p,result,check=a['bind'](lua.eval('{streetProposal={}}'),10)
    assert check['ok'] and result['nativeEntranceNode']==-8
    assert lua.globals().previews==2
    assert list(p['streetProposal']['nodesToRemove'].values())==[10]
    assert len(p['streetProposal']['nodesToAdd'])==0
    assert p['streetProposal']['edgesToAdd'][1]['comp']['position1']['x']==0
    assert p['streetProposal']['edgesToAdd'][2]['comp']['position0']['x']==0

@pytest.mark.parametrize('change',[
 'frozen=11','configs[11].userModifiedLaneConnections=true',
 'configs[11].trafficLightConfig.states={1}','height=2','changed=true','fatal=true',
 'edges[21].objects={1}'])
def test_frontage_rejects_unsafe_native_or_road_state(frontage,change):
    lua,a=frontage;lua.execute(change)
    with pytest.raises(LuaError):a['bind'](lua.eval('{streetProposal={}}'),10)

def test_frontage_signature_tracks_outer_adjacency_and_lane_changes(frontage):
    lua,a=frontage
    _,s=a['inspect'](10)
    lua.execute('extra=true');_,changed=a['inspect'](10)
    assert s!=changed
    lua.execute('extra=false;configs[11].laneConnections[1].lane0=4')
    assert a['inspect'](10)[1]!=s

def test_optional_frontage_argument():
    args=dict(x=1,y=2,rotation=180,carrier='ROAD')
    validate_build_arguments('preview_depot',args)
    validate_build_arguments('preview_depot',dict(args,frontage_node=10))
    with pytest.raises(ValueError):validate_build_arguments('preview_depot',dict(args,frontage_node=-1))

@pytest.mark.parametrize('change',['blocked=true','removal=true'])
def test_rejected_preview_keeps_diagnostics_without_authorizing_build(frontage,change):
    lua,a=frontage;lua.execute(change)
    _,_,check=a['bind'](lua.eval('{streetProposal={}}'),10)
    assert not check['ok']
    if change=='removal=true':
        assert check['blocked'] and check['unexpected_removals']
        assert check['removalReview']['removableModules']['entries'][1]['entity']==123

@pytest.mark.parametrize('names,allowed',[
 (['::/assets/vegetation/trees/oak/oak.mdl'],True),
 (['::/assets/vegetation/trees/oak/oak.mdl','::/assets/buildings/house.mdl'],False),
 (['::/assets/vegetation/trees_fake/oak.mdl'],False),([],False),
 (['::/assets/vegetation/trees/oak/oak.mdl']*8+['::/assets/rock.mdl'],False)])
def test_auto_removal_requires_every_model_to_be_a_known_tree(frontage,names,allowed):
    lua,a=frontage
    lua.globals().modelNames=lua.table_from(names)
    lua.execute("""
     local original=getComponent
     getComponent=function(id,key)
      if id==90 and key=='MODEL_INSTANCE_LIST'then
       local t={};for i in ipairs(modelNames)do t[i]={modelId=i}end
       return {thinInstances=t,fatInstances={}}
      end
      return original(id,key)
     end
     api.res={modelRep={getName=function(id)return modelNames[id]end}}
     local preview=previewProposal
     previewProposal=function(p)
      local c,d=preview(p);d.collisionInfo.autoRemovalEntity2models={[90]={{0,0}}};return c,d
     end
    """)
    _,_,check=a['bind'](lua.eval('{streetProposal={}}'),10)
    assert check['ok']==allowed
    if allowed:assert check['treeRemovals'][1]['entity']==90
    else:assert check['removalReview']['autoRemovalEntity2models']['count']==1

def test_lane_signature_uses_values_not_opaque_wrapper_addresses(frontage):
    lua,a=frontage
    lua.execute("""
     toPlain=function()return {_unavailable='opaque_userdata',description=tostring({})}end
     function replaceLanes()
      edges[21].laneConfigs={{offset=0,width=4,height=0,speed=22,forward=true,transportModes={[0]=false,[2]=true}}}
     end
     replaceLanes()
    """)
    _,before=a['inspect'](10)
    lua.execute('replaceLanes()')
    assert a['inspect'](10)[1]==before
    lua.execute('edges[21].laneConfigs[1].transportModes[2]=false')
    assert a['inspect'](10)[1]!=before


@pytest.mark.parametrize('failure', ['missing_data', 'missing_network', 'final_critical', 'height'])
def test_native_failure_keeps_details_without_another_preview(frontage, failure):
    lua,a=frontage
    lua.globals().failure=failure
    lua.execute('''
     local original=previewProposal
     function previewProposal(p)
      local c,d=original(p)
      c.messages={{key="native_rejection",detail="specific native reason"}}
      c.warnings={"warning"};c.infos={"info"}
      if failure=="missing_data" then return c,nil end
      if failure=="missing_network" then d.entity2tn=nil end
      if failure=="final_critical" and previews==2 then c.critical=true end
      return c,d
     end
     if failure=="height" then height=2 end
    ''')
    with pytest.raises(LuaError) as error:
        a['bind'](lua.eval('{streetProposal={}}'),10)
    raw=str(error.value).split('; diagnostic=',1)[1]
    diagnostic=json.JSONDecoder().raw_decode(raw)[0]
    assert diagnostic['native']['messages'][0]['detail']=='specific native reason'
    assert diagnostic['context']['node']==10
    assert diagnostic['stage']==({'height':'port_height','final_critical':'bound_preview'}.get(failure,'discover_port'))
    assert lua.globals().previews==(2 if failure=='final_critical' else 1)
    assert set(lua.globals().edges.keys())=={21,22}


@pytest.mark.parametrize('final_critical', [False, True])
def test_unbound_discovery_geometry_requires_independent_final_preview(frontage, final_critical):
    """An unbound discovery verdict cannot reject or approve a bound proposal."""
    lua,a=frontage
    lua.globals().finalCritical=final_critical
    lua.execute('''
      local original=previewProposal
      function previewProposal(p)
       local c,d=original(p)
       c.critical=previews==1 or finalCritical
       c.ok=not c.critical
       c.messages=c.critical and {'无法建造'} or {}
       return c,d
      end
    ''')
    proposal=lua.eval('{streetProposal={}}')
    if final_critical:
        with pytest.raises(LuaError,match='Final native frontage preview failed'):
            a['bind'](proposal,10)
    else:
        _,result,check=a['bind'](proposal,10)
        assert result['discoveryCritical'] is True
        assert list(result['discoveryMessages'].values())==['无法建造']
        assert check['ok'] and not check['critical']
    assert lua.globals().previews==2


def test_critical_discovery_without_a_matching_port_stops_before_final_preview(frontage):
    lua,a=frontage
    lua.execute('''
      local original=previewProposal
      function previewProposal(p)
       local c,d=original(p)
       c.critical=true;c.ok=false;d.entity2tn={}
       return c,d
      end
    ''')
    with pytest.raises(LuaError,match='Native entrance does not uniquely match'):
        a['bind'](lua.eval('{streetProposal={}}'),10)
    assert lua.globals().previews==1


def test_failure_diagnostics_are_bounded_and_cycle_safe(frontage):
    lua,a=frontage
    value=lua.execute('local t={};for i=1,300 do t[i]=string.rep("x",2000)end;t.loop=t;return t')
    with pytest.raises(LuaError) as error:
        a['fail']('rejected','test',value,lua.table())
    raw=str(error.value).split('; diagnostic=',1)[1]
    diagnostic=json.JSONDecoder().raw_decode(raw)[0]
    assert len(raw)<24000
    assert diagnostic['native']['_truncated'] is True
    assert lua.globals().previews==0


def test_failure_diagnostics_preserve_utf8_at_truncation(frontage):
    lua,a=frontage
    with pytest.raises(LuaError) as error:
        a['fail']('rejected','test',lua.table_from({'原生错误'*50:'高差不符'*200}),lua.table())
    raw=str(error.value).split('; diagnostic=',1)[1]
    diagnostic=json.JSONDecoder().raw_decode(raw)[0]
    key,value=next(iter(diagnostic['native'].items()))
    assert key.endswith('<truncated>') and value.endswith('<truncated>')
    assert '\ufffd' not in key+value


def test_native_read_only_configuration_flags_are_not_written(frontage):
    lua,a=frontage
    lua.execute('''
     api.type.BaseNodeLaneConnectionAndEntity.new=function()
      local values={}
      local comp=setmetatable({}, {__index=values,__newindex=function(_,key,value)
       if key=="userModifiedLaneConnections" or key=="userModifiedTrafficLightStates" then
        error("no writable member "..key)
       end
       values[key]=value
      end})
      return {comp=comp}
     end
    ''')
    p,_,check=a['bind'](lua.eval('{streetProposal={}}'),10)
    assert check['ok']
    for cfg in p['streetProposal']['nodeConfigsToAdd'].values():
        assert list(cfg['comp']['crosswalks'].values())==[-3,-4]
        assert cfg['comp']['laneConnections'][1]['segment0']==-3
        assert cfg['comp']['trafficLightPreference']==0
        assert cfg['comp']['doubleSlipSwitch'] is False


@pytest.mark.parametrize('flag', ['userModifiedLaneConnections','userModifiedTrafficLightStates'])
def test_read_only_custom_flags_still_block_frontage(frontage,flag):
    lua,a=frontage
    lua.globals().configs[11][flag]=True
    with pytest.raises(LuaError,match='Custom frontage node configuration'):
        a['bind'](lua.eval('{streetProposal={}}'),10)
    assert lua.globals().previews==0


def test_missing_joint_geometry_reports_construction_only_control(frontage):
    lua,a=frontage
    lua.execute("""
      api.type.SimpleProposal={new=function()return {streetProposal={}}end}
      local original=previewProposal
      function previewProposal(p)
       local c,d=original(p)
       if p.streetProposal.edgesToRemove then
        c.critical=true;c.ok=false;d.entity2tn={}
       else
        c.critical=false;c.ok=false;c.collisions={21}
       end
       return c,d
      end
    """)
    with pytest.raises(LuaError) as error:
        a['bind'](lua.eval('{streetProposal={},constructionsToAdd={{fileName="depot"}}}'),10)
    raw=str(error.value).split('; diagnostic=',1)[1]
    diagnostic=json.JSONDecoder().raw_decode(raw)[0]
    assert diagnostic['stage']=='unique_port'
    assert diagnostic['context']['joint']['networkCount']==0
    control=diagnostic['context']['control']
    assert control['critical'] is False and control['collisions']==[21]
    assert any('reason=match' in row for row in control['geometry']['rows'])
    assert diagnostic['native']['critical'] is True
    assert lua.globals().previews==2  # Only failed joint discovery and independent read-only control.
    assert set(lua.globals().edges.keys())=={21,22}


def test_geometry_summary_records_rejection_reasons_and_bounds(frontage):
    lua,a=frontage
    pd=lua.execute("""
      local edges={}
      for i=1,30 do edges[i]={transportModes={[2]=true,[3]=true,[4]=true},
       conns={{entity=-8},{entity=-7}},geometry={cubicSpline={pos={V3(i,0,1),V3(0,10,1)}},height={x=1,y=1}}} end
      return {entity2tn={[-8]={edges=edges}}}
    """)
    result=a['geometrySummary'](pd,lua.eval('V3(0,0,1)'),'ROAD')
    assert result['networkCount']==1 and result['edgeCount']==30
    assert result['endpointCount']==31 and result['truncated'] is True
    assert len(result['rows'])==12
    assert all('reason=xy' in row for row in result['rows'].values())


@pytest.mark.parametrize('native_height',[1.05,5,-4])
def test_measured_height_alignment_keeps_existing_road_height(frontage,native_height):
    lua,a=frontage
    lua.globals().height=native_height
    corrections=[]
    def align(delta):
        corrections.append(delta)
        lua.globals().height=native_height+delta
        return lua.eval('{streetProposal={}}')
    p,result,check=a['bind'](lua.eval('{streetProposal={}}'),10,'ROAD',align)
    assert corrections==pytest.approx([1-native_height])
    assert check['ok'] and lua.globals().previews==3
    assert result['heightAlignment']['roadHeightPreserved'] is True
    assert result['heightAlignment']['iterations']==1
    assert result['nativePosition']['z']==pytest.approx(1)
    for e in p['streetProposal']['edgesToAdd'].values():
        assert e['comp']['position0']['z']==1 and e['comp']['position1']['z']==1


def test_height_alignment_is_bounded_and_never_accepts_nonconvergence(frontage):
    lua,a=frontage;lua.globals().height=5
    calls=[]
    def bad_alignment(delta):
        calls.append(delta)
        return lua.eval('{streetProposal={}}')
    with pytest.raises(LuaError,match='did not converge'):
        a['bind'](lua.eval('{streetProposal={}}'),10,'ROAD',bad_alignment)
    assert calls==[-4] and lua.globals().previews==2
    assert set(lua.globals().edges.keys())=={21,22}


def test_height_correction_still_requires_clean_final_native_preview(frontage):
    lua,a=frontage;lua.globals().height=5
    lua.execute('''
      local original=previewProposal
      function previewProposal(p)
       local c,d=original(p)
       if previews==3 then c.critical=true end
       return c,d
      end
    ''')
    def align(delta):
        lua.globals().height=1
        return lua.eval('{streetProposal={}}')
    with pytest.raises(LuaError,match='Final native frontage preview failed'):
        a['bind'](lua.eval('{streetProposal={}}'),10,'ROAD',align)
    assert lua.globals().previews==3
