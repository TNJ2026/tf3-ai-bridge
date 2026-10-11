"""v37 proposal contracts and fault detection. No claims of native acceptance."""
from copy import deepcopy
import pytest
from test_road_graph import graph_channel, node, edge, preview, commit
from tf3_mcp.road_graph import road_graph


def special(c):
    c.lua.execute('''
    api.type.enum.TrafficLightPreference.YES=1
    api.type.enum.TrafficLightPreference.NO=0
    api.type.TrafficLightConfig={new=function()return {}end}
    api.type.TrafficLightState={new=function()return {}end}
    api.type.enum.EdgeObjectType={STOP_LEFT=1,STOP_RIGHT=0}
    api.type.ComponentType.EDGE_OBJECT=801
    api.type.ComponentType.STATION=802
    api.type.ComponentType.RAILROAD_CROSSING=803
    api.type.ComponentType.STATION_GROUP=804
    api.type.ComponentType.LINE=805
    components[80002]={[804]={stations={80001}}}
    components[80003]={[805]={stops={{stationGroup=80002}}}}
    api.engine.system.stationGroupSystem={getStationGroup=function(id)return GROUP_CHANGED and 80009 or 80002 end}
    api.engine.system.lineSystem.getLinesForStationGroup=function(group)return {80003}end
    local get,find,name=api.res.streetTemplateRep.get,api.res.streetTemplateRep.find,api.res.streetTemplateRep.getName
    api.res.streetTemplateRep.find=function(n)if n=='rail/test' then return 44 end;return find(n)end
    api.res.streetTemplateRep.getName=function(i)if i==44 then return 'rail/test' end;return name(i)end
    api.res.streetTemplateRep.get=function(i)
      if i==44 then return {roadType=api.type.enum.RoadType.TRACK,laneConfigs={{width=5,offset=0,forward=true,transportModes={[7]=true,[8]=true}}},streetStyle='rail'} end
      return get(i)
    end
    api.res.railroadCrossingTypeRep={find=function(n)return n=='crossing/test' and 3 or -1 end,get=function(i)return i==3 and {} or nil end,getAll=function()return {[3]='crossing/test'}end}
    api.engine.system.streetSystem.getEdgeForEdgeObject=function(object)
      for id,cs in pairs(components)do local e=cs[102]
        if e then for _,o in ipairs(e.objects or {})do if o[1]==object then return id end end end
      end
      return -1
    end
    api.engine.system.railRoadCrossingSystem={getRailroadCrossingForNode=function(node)return RCID or -1 end}
    function stopNetwork(id,x,z)
      local edges={}
      for _,v in ipairs({{1,api.type.enum.TransportMode.BUS},{0,api.type.enum.TransportMode.PERSON}})do
        edges[#edges+1]={transportModes={[v[2]]=true},conns={{entity=STREET_A,index=0},{entity=id,index=v[1]}},
          geometry={type=3,cubicOffsetSpline={pos={{x=0,y=0},{x=x,y=0}}},height={x=2,y=z}}}
      end
      return {edges=edges,nodes={}}
    end
    local send=api.cmd.sendCommand
    api.cmd.sendCommand=function(cmd,cb)
      send(cmd,function(res,ok,results)
        if ok then
          local sp=cmd.proposal.streetProposal
          for n,index in pairs(sp.node2rcType or {})do
            RCID=90001;components[RCID]={[803]={typeIndex=BAD_CROSSING and 99 or index}}
          end
          -- Observed v38 semantics: raw param is retained; native terminal position
          -- is re-linked and ground height may change. Faults must stay blocked.
          if not BAD_OBJECT then
            for _,r in ipairs(sp.edgesToAdd or {})do
              for _,o in ipairs(r.comp.objects or {})do
                local eo=components[o[1]][801]
                if eo then
                  local actual=api.engine.system.streetSystem.getEdgeForEdgeObject(o[1])
                  if BAD_PARAM then eo.param=.99 end
                  if not BAD_REFERENCE then
                    components[o[1]][802].terminals[1].vehicleNodeId.entity=actual
                    components[o[1]][802].terminals[1].personNodes[1].entity=actual
                  end
                  local z=2+(HEIGHT_SHIFT or 0);local x=25+(ANCHOR_SHIFT or 0)
                  components[actual][998]=stopNetwork(actual,x,z)
                  eo.transf.columns[4].z=z+(MODEL_HEIGHT_ERROR or 0)
                  if MISSING_STOP_NETWORK then components[actual][998].edges={}end
                end
              end
            end
          end
          if BAD_STATION and components[80001]then components[80001][802].cargo=true end
          if BAD_LINE then components[80003][805].stops={}end
          if BAD_GROUP then GROUP_CHANGED=true end
        end
        cb(res,ok,results)
      end)
    end
    ''')
    return c


def object_graph(c, **kwargs):
    c.lua.execute('''components[80001]={[801]={param=.25,transf={columns={{x=1,y=0,z=0,w=0},{x=0,y=1,z=0,w=0},{x=0,y=0,z=1,w=0},{x=25,y=5,z=2,w=1}}},edgeObjectConstruction='stop/test',params={year=2000}},[802]={cargo=false,terminals={{vehicleNodeId={entity=EDGE_AB,index=1},personNodes={{entity=EDGE_AB,index=0}}}}}}
      components[EDGE_AB][998]=stopNetwork(EDGE_AB,25,2)
      components[EDGE_AB][102].objects={{80001,1}}''')
    return {'nodes':[{'split':{'edge':c.lua.globals().EDGE_AB,'param':.5,'preserve_objects':True,**kwargs}},node(50,100)],'edges':[edge(0,1)]}


def test_object_split_retains_entity_and_uses_no_native_removal_preview(tmp_path):
    c=special(graph_channel(tmp_path));g=object_graph(c)
    p=preview(c,g);assert p['specialCases']['objects'][0]['id']==80001
    assert p['structural_only'] and c.lua.globals().previewCalls==0
    r=commit(c,p);assert r['ok'] and r['result']['verified'],r
    assert r['result']['preservedObjects'][0]['verified']
    sp=c.lua.globals().LAST_GRAPH.streetProposal
    assert sp.edgeObjectsToAdd is None and sp.edgeObjectsToRemove is None
    assert c.lua.globals().components[80001][801].param==.25


@pytest.mark.parametrize('flag',['BAD_OBJECT','BAD_STATION','BAD_REFERENCE','BAD_LINE','BAD_GROUP','BAD_PARAM','MISSING_STOP_NETWORK'])
def test_object_readback_failure_keeps_pending(tmp_path,flag):
    c=special(graph_channel(tmp_path));p=preview(c,object_graph(c));c.lua.globals()[flag]=True
    r=commit(c,p);assert r['ok'] and r['result']['built'] and not r['result']['verified'],r
    assert c.state['v']['uiConstruction']['pending']


@pytest.mark.parametrize('mutation',["components[80001][801].param=0", "components[80001][801]=nil", "components[EDGE_AB][102].objects={{80001,2}}"])
def test_unsafe_object_split_rejected_before_dispatch(tmp_path,mutation):
    c=special(graph_channel(tmp_path));g=object_graph(c);c.lua.execute(mutation)
    r=c.query('preview_road_graph',{'graph':g,'isolated_test':True})
    assert not r['ok'] and c.lua.globals().dispatches==0 and c.lua.globals().previewCalls==0


@pytest.mark.parametrize('kind',[1,2])
def test_structure_split_keeps_both_children_resource(tmp_path,kind):
    c=special(graph_channel(tmp_path));c.lua.globals().STRUCTURE=kind
    c.lua.execute('components[EDGE_AB][102].type=STRUCTURE;components[EDGE_AB][102].typeIndex=7')
    g={'nodes':[{'split':{'edge':c.lua.globals().EDGE_AB,'param':.5,'allow_structure':True}},node(50,100)],'edges':[edge(0,1,structure='bridge' if kind==1 else 'tunnel',structure_resource='native.structure')]}
    p=preview(c,g);r=commit(c,p);assert r['ok'] and r['result']['verified'],r
    for eid in r['result']['edges']:assert c.lua.globals().components[eid][102].type==kind
    assert c.lua.globals().previewCalls==0


@pytest.mark.parametrize('kind',[0,1,2])
def test_split_only_requires_no_unrelated_branch(tmp_path,kind):
    c=special(graph_channel(tmp_path));c.lua.globals().STRUCTURE=kind
    c.lua.execute('components[EDGE_AB][102].type=STRUCTURE;components[EDGE_AB][102].typeIndex=STRUCTURE==0 and -1 or 7')
    g={'nodes':[{'split':{'edge':c.lua.globals().EDGE_AB,'param':.5,'allow_structure':True}}],'edges':[]}
    assert road_graph(g)
    r=commit(c,preview(c,g));assert r['ok'] and r['result']['verified'],r
    assert len(r['result']['edges'])==2
    assert not road_graph({'nodes':[node(700,700)],'edges':[]})


def custom(c, crosswalk=True):
    c.lua.execute('''local cfg=api.type.BaseNodeLaneConnectionAndEntity.new().comp
      cfg.laneConnections={{segment0=EDGE_AB,segment1=EDGE_BC,lane0=1,lane1=2,withRoad=true,withTram=false}}
      cfg.userModifiedLaneConnections=true;cfg.userModifiedTrafficLightStates=true;cfg.trafficLightPreference=1
      cfg.crosswalks={EDGE_AB};cfg.trafficLightConfig={trafficLightType=-1,states={
        {duration=20,minDuration=2,canSkip=false,lockedLanes={1}},
        {duration=8,minDuration=1,canSkip=true,lockedLanes={0}}}}
      components[STREET_B][107]=cfg''')
    return {'nodes':[{'node':c.lua.globals().STREET_B,'junction':{'extend':'preserve','phase_duration':7}},node(100,100)],'edges':[edge(0,1)]}


def test_custom_signal_extension_preserves_restrictions_timing_and_crosswalk_indices(tmp_path):
    c=special(graph_channel(tmp_path));g=custom(c);p=preview(c,g);r=commit(c,p)
    assert r['ok'] and r['result']['verified'],r
    cfg=c.lua.globals().components[c.lua.globals().STREET_B][107]
    # Reverse old->old turn remains prohibited; only four new-arm turns added.
    assert len(cfg.laneConnections)==5 and cfg.userModifiedLaneConnections
    assert len(cfg.trafficLightConfig.states)==6
    assert cfg.trafficLightConfig.states[1].duration==20
    assert list(cfg.trafficLightConfig.states[1].lockedLanes.values())==[5,1,2,3,4]
    assert list(cfg.trafficLightConfig.states[2].lockedLanes.values())==[0,1,2,3,4]
    assert cfg.trafficLightConfig.states[3].duration==7
    assert cfg.trafficLightConfig.states[3].lockedLanes[5]==5


def test_explicit_initial_signal_plan_and_invalid_index(tmp_path):
    c=special(graph_channel(tmp_path))
    phases=[dict(locked_lanes=[1],duration=12,min_duration=1,can_skip=True),dict(locked_lanes=[0],duration=12,min_duration=1,can_skip=True)]
    g={'nodes':[node(700,700),dict(node(800,700),junction={'signals':dict(preference='YES',traffic_light_type=-1,states=phases)}),node(900,700)],'edges':[edge(0,1),edge(1,2)]}
    bad=deepcopy(g);bad['nodes'][1]['junction']['signals']['states'][0]['locked_lanes']=[2]
    assert not c.query('preview_road_graph',{'graph':bad,'isolated_test':True})['ok']
    r=commit(c,preview(c,g));assert r['ok'] and r['result']['verified'],r


def crossing_graph():
    return {'nodes':[dict(node(700,700),crossing_resource='crossing/test'),node(600,700),node(800,700),node(700,600),node(700,800)],
            'edges':[edge(0,1),edge(0,2),edge(0,3,template='rail/test'),edge(0,4,template='rail/test')]}


@pytest.mark.parametrize('bad',[False,True])
def test_native_crossing_proposal_and_resource_readback(tmp_path,bad):
    c=special(graph_channel(tmp_path));c.lua.globals().BAD_CROSSING=bad
    g=crossing_graph();assert road_graph(g)
    r=commit(c,preview(c,g));assert r['ok'] and r['result']['built'],r
    assert r['result']['verified'] is (not bad)
    sp=c.lua.globals().LAST_GRAPH.streetProposal
    assert list(sp.node2rcType.values())==[3]
    assert len(sp.nodeConfigsToAdd)==0  # native crossing routing, no train-to-road turns
    assert sorted(x.type for x in sp.edgesToAdd.values())==[0,0,1,1]


@pytest.mark.parametrize('bad',['not_straight','shallow','three_arms','elevated','missing_resource','mixed_without_opt_in'])
def test_invalid_crossing_fails_before_native_preview(tmp_path,bad):
    c=special(graph_channel(tmp_path));g=crossing_graph()
    if bad=='not_straight':g['nodes'][4]['position']['x']=750
    elif bad=='shallow':
        g['nodes'][3]['position'].update(x=600,y=680);g['nodes'][4]['position'].update(x=800,y=720)
    elif bad=='three_arms':g['nodes'].pop();g['edges'].pop()
    elif bad=='elevated':g['edges'][0].update(structure='bridge',structure_resource='native.structure')
    elif bad=='missing_resource':g['nodes'][0]['crossing_resource']='wrong'
    else:del g['nodes'][0]['crossing_resource']
    r=c.query('preview_road_graph',{'graph':g,'isolated_test':True})
    assert not r['ok'] and c.lua.globals().previewCalls==0 and c.lua.globals().dispatches==0,r


@pytest.mark.parametrize('bad',[{'extend':'reset'},{'phase_duration':10},{'extend':'preserve','phase_duration':0},{'signals':{}},{'unexpected':True}])
def test_host_rejects_invalid_junction_options(bad):
    g={'nodes':[dict(node(0,0),junction=bad),node(100,0)],'edges':[edge(0,1)]}
    assert not road_graph(g)

@pytest.mark.parametrize('fault', ['none','missing_callback','edge','config','new_edge','exception'])
def test_native_rejection_requires_unchanged_graph_before_unlock(tmp_path,fault):
    c=special(graph_channel(tmp_path))
    g={'nodes':[{'split':{'edge':c.lua.globals().EDGE_AB,'param':.5}}],'edges':[]}
    p=preview(c,g)
    c.lua.globals().FAULT=fault
    c.lua.execute('''local send=api.cmd.sendCommand
      api.cmd.sendCommand=function(cmd,cb)
        if cmd.event then return send(cmd,cb)end
        dispatches=dispatches+1
        if FAULT=='missing_callback' then return end
        if FAULT=='edge' then components[EDGE_AB][102].tangent0.y=3 end
        if FAULT=='config' then
          local cfg=api.type.BaseNodeLaneConnectionAndEntity.new().comp
          cfg.trafficLightPreference=1;components[STREET_B][107]=cfg
        end
        if FAULT=='new_edge' then components[99001]={[102]={node0=STREET_A,node1=STREET_B}} end
        if FAULT=='exception' then error('native test exception')end
        cb({errorState={critical=false,messages={'Collision'}},collisionInfo={collisionEntities={{entity=999}}}},false,{})
      end''')
    r=commit(c,p)
    pending=c.state['v'].uiConstruction.pending
    if fault=='exception':
        assert not r['ok'] and pending
        return
    assert r['ok'] and not r['result']['built'] and not r['result']['verified'],r
    if fault=='none':
        assert r['result']['phase']=='rejected_unchanged' and r['result']['rejectionVerified']
        assert r['result']['nativeResult']['messages']==['Collision']
        assert r['result']['nativeResult']['collisions']==[999]
        assert pending is None
        # Original consumed token is never replayable. Operation ID and token resolve alike.
        before=c.lua.globals().dispatches
        for key in [r['result']['id'],p['preview_token']]:
            read=c.query('get_road_graph_operation',{'operation_id':key})
            assert read['ok'] and read['result']['phase']=='rejected_unchanged'
        assert not commit(c,p)['ok'] and c.lua.globals().dispatches==before
    else:
        assert r['result']['phase']=='unconfirmed' and pending
        assert not r['result'].get('rejectionVerified')

@pytest.mark.parametrize('height,anchor,model_error,passed',[(.067,0,0,True),(.3,0,0,False),(0,1,0,False),(.067,0,.01,False)])
def test_stop_ground_height_requires_matching_native_anchor(tmp_path,height,anchor,model_error,passed):
    c=special(graph_channel(tmp_path));p=preview(c,object_graph(c))
    c.lua.globals().HEIGHT_SHIFT=height;c.lua.globals().ANCHOR_SHIFT=anchor;c.lua.globals().MODEL_HEIGHT_ERROR=model_error
    r=commit(c,p);assert r['ok'] and r['result']['built']
    assert r['result']['verified'] is passed


def test_second_split_uses_real_anchor_instead_of_retained_native_param(tmp_path):
    c=special(graph_channel(tmp_path));g=object_graph(c);g['nodes'][0]['split']['param']=.75
    r=commit(c,preview(c,g));assert r['result']['verified']
    owned=r['result']['preservedObjects'][0]['edge']
    g={'nodes':[{'split':{'edge':owned,'param':.7,'preserve_objects':True}}],'edges':[]}
    p=preview(c,g);o=p['specialCases']['objects'][0]
    assert o['nativeParam']==.25 and abs(o['projectedSourceParam']-1/3)<1e-6
    r=commit(c,p);assert r['result']['verified'] and c.lua.globals().components[80001][801].param==.25


def test_actual_anchor_proximity_is_guarded_despite_stale_metadata(tmp_path):
    c=special(graph_channel(tmp_path));g=object_graph(c)
    c.lua.execute('components[EDGE_AB][998]=stopNetwork(EDGE_AB,49,2)')
    r=c.query('preview_road_graph',{'graph':g,'isolated_test':True})
    assert not r['ok'] and 'too close' in r['error'] and c.lua.globals().dispatches==0


def test_captured_native_stop_geometry_resolves_retained_parameter(tmp_path):
    import json
    from pathlib import Path
    c=special(graph_channel(tmp_path))
    f=json.loads((Path(__file__).parent/'fixtures/road_stop_native_v38.json').read_text(encoding='utf-8'))
    def clean(v):
        if isinstance(v,list):return [clean(x) for x in v]
        if isinstance(v,dict):return {(int(k) if isinstance(k,str) and k.isdigit() else k):clean(x) for k,x in v.items() if k!='_unavailableFields'}
        return v
    def put(entity,ct,value):
        existing=c.lua.globals().components[entity]
        if existing is None:existing=c.lua.table();c.lua.globals().components[entity]=existing
        existing[ct]=c.lua.table_from(clean(value),recursive=True)
    eid=f['edge']['id'];e=f['edge']['components']['BASE_EDGE']
    put(eid,102,e);put(eid,998,f['network']['components']['TRANSPORT_NETWORK'])
    ct=c.lua.globals().api.type.ComponentType.BASE_NODE
    for side in [0,1]:
        put(e[f'node{side}'],ct,{'position':e[f'position{side}']});put(e[f'node{side}'],998,{'nodes':[],'edges':[]})
    for stop in f['stops']:
        put(stop['id'],801,stop['components']['EDGE_OBJECT']);put(stop['id'],802,stop['components']['STATION'])
    g={'nodes':[{'split':{'edge':eid,'param':.8,'preserve_objects':True}}],'edges':[]}
    r=preview(c,g)
    for obj in r['specialCases']['objects']:
        assert obj['nativeParam']==.5
        assert abs(obj['projectedSourceParam']-.374932861328)<1e-6
    assert c.lua.globals().dispatches==0 and c.lua.globals().previewCalls==0
