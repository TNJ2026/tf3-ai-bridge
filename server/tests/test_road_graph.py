"""Graph topology/receipts and carriageway direction. Mock engine, not native acceptance."""
from copy import deepcopy
import math

import pytest
from tf3_mcp.road_graph import paired_highway, road_graph
from tf3_mcp.ui_log import validate_build_arguments
from test_ui_consolidated import Channel, NETWORK_FIXTURE

TEMPLATE = 'town/town_old_small'
HIGHWAY = '::/infrastructure/street/highway/highway_new_small.street_template'

FIXTURE = NETWORK_FIXTURE + r'''
local CT=api.type.ComponentType
CT.BASE_NODE_CONFIG=107
api.type.enum.TrafficLightPreference={AUTO=2}
api.type.enum.TransportMode.ELECTRIC_TRAM=6
api.type.BaseNodeLaneConnectionAndEntity={new=function()return {comp={
 trafficLightConfig={states={},trafficLightType=-1},crosswalks={},laneConnections={},
 doubleSlipSwitch=false,userModifiedTrafficLightStates=false,trafficLightPreference=2}}end}
api.type.LaneConnection={new=function()return {}end}
local function copy(t)
 if type(t)~='table' then return t end
 local c={};for k,v in pairs(t)do c[k]=copy(v)end;return c
end
LANES={{width=2,offset=-5,forward=false,transportModes={[0]=true}},
 {width=3,offset=-1.5,forward=false,transportModes={[2]=true,[3]=true,[4]=true}},
 {width=3,offset=1.5,forward=true,transportModes={[2]=true,[3]=true,[4]=true}},
 {width=2,offset=5,forward=true,transportModes={[0]=true}}}
HIGHWAY_LANES={{width=3.5,offset=-1.75,forward=true,transportModes={[2]=true,[3]=true,[4]=true}},
 {width=3.5,offset=1.75,forward=true,transportModes={[2]=true,[3]=true,[4]=true}}}
local rep=api.res.streetTemplateRep;local oldget,oldfind,oldname=rep.get,rep.find,rep.getName
rep.find=function(name)if name:find('/highway/') then return 33 end;return oldfind(name)end
rep.getName=function(id)if id==33 then return '::/infrastructure/street/highway/highway_new_small.street_template' end;return oldname(id)end
rep.get=function(id)
 local t=oldget(id);t.laneConfigs=id==33 and HIGHWAY_LANES or LANES;return t
end
for _,name in ipairs({'bridgeTypeRep','tunnelTypeRep'})do
 api.res[name]={find=function(r)return r=='native.structure' and 7 or -1 end,
 get=function(id)return id==7 and {} or nil end,getAll=function()return {[7]='native.structure'}end}
end
for _,cs in pairs(components)do
 local e=cs[CT.BASE_EDGE]
 if e then e.laneConfigs=LANES;e.typeIndex=-1;e.roadStyle='style';e.roadDevelopmentLocked=false;e.edgeDecorations={} end
 if e or cs[CT.BASE_NODE] then cs[998]={} end
end
local preview=api.engine.util.proposal.makeProposalData
previewCalls=0
api.engine.util.proposal.makeProposalData=function(p,...)
 previewCalls=previewCalls+1
 assert(#(p.streetProposal.edgesToRemove or {})==0,'Removal native preview would assert')
 return preview(p,...)
end
local send=api.cmd.sendCommand
api.cmd.sendCommand=function(cmd,cb)
 LAST_GRAPH=copy(cmd.proposal)
 if cmd.event then return send(cmd,cb)end
 send(cmd,function(res,ok,results)
  if ok then
   local sp=cmd.proposal.streetProposal;local map={}
   for i,r in ipairs(sp.nodesToAdd or {})do map[r.entity]=res.proposal.proposal.addedNodes[i].entity end
   for i,r in ipairs(sp.edgesToAdd or {})do
    local id=res.proposal.proposal.addedSegments[i].entity;map[r.entity]=id
    local comp=copy(r.comp);comp.node0=map[comp.node0] or comp.node0;comp.node1=map[comp.node1] or comp.node1
    components[id][CT.BASE_EDGE]=comp
    if WRONG_LANES then comp.laneConfigs[1].forward=not comp.laneConfigs[1].forward end
    if WRONG_TANGENT then comp.tangent0.y=1234 end
    if WRONG_STYLE then comp.roadStyle='wrong' end
   end
   for _,r in ipairs(sp.nodeConfigsToAdd or {})do
    local cfg=copy(r.comp)
    for _,l in ipairs(cfg.laneConnections)do
     l.segment0=map[l.segment0] or l.segment0;l.segment1=map[l.segment1] or l.segment1
     if WRONG_TURN then l.lane1=99 end
    end
    for i,e in ipairs(cfg.crosswalks)do cfg.crosswalks[i]=map[e] or e end
    components[map[r.entity] or r.entity][107]=cfg
    if BAD_SIGNAL then cfg.trafficLightConfig.states={{duration=0,minDuration=1,canSkip=false,lockedLanes={}}}end
    if CUSTOM_FLAG then cfg.userModifiedLaneConnections=true end
   end
   if MISSING_NETWORK then components[res.proposal.proposal.addedNodes[1].entity][998]=nil end
  end
  cb(res,ok,results)
 end)
end
'''


def node(x, y, z=2):
    return {'position': dict(x=x, y=y, z=z)}


def edge(a, b, **kw):
    return {'from': a, 'to': b, 'template': TEMPLATE, **kw}


def graph_channel(tmp_path):
    return Channel(tmp_path, FIXTURE)


def preview(c, g):
    r = c.query('preview_road_graph', {'graph': g, 'isolated_test': True})
    assert r['ok'] and r['result'].get('preview_token'), r
    return r['result']


def commit(c, p):
    return c.query('commit_road_graph', {'preview_token': p['preview_token'], 'backup_save': 'isolated_before'})


@pytest.mark.parametrize('arms', [2, 3, 4, 5, 8])
def test_new_intersection_turns_and_single_commit(tmp_path, arms):
    c = graph_channel(tmp_path)
    g = {'nodes': [node(700,700)] + [node(700+100*math.cos(i*2*math.pi/arms),700+100*math.sin(i*2*math.pi/arms)) for i in range(arms)],
         'edges': [edge(0,i+1) for i in range(arms)]}
    p = preview(c,g)
    assert p['nativePreviewPassed'] and c.lua.globals().dispatches == 0
    r=commit(c,p)
    assert r['ok'] and r['result']['verified'],r
    assert not r['result']['directedPathsVerified']
    cfg=c.lua.globals().LAST_GRAPH.streetProposal.nodeConfigsToAdd[1].comp
    assert len(cfg.laneConnections)==arms*(arms-1)
    assert c.lua.globals().dispatches==1
    assert not commit(c,p)['ok'] and c.lua.globals().dispatches==1


def test_existing_implicit_junction_and_fourth_arm(tmp_path):
    c=graph_channel(tmp_path)
    p=preview(c,{'nodes':[node(700,700),node(800,700),node(900,700)],'edges':[edge(0,1),edge(1,2)]})
    r=commit(c,p);assert r['result']['verified'],r
    center=next(j['node'] for j in r['result']['junctions'])
    # Add both arms in one atomic proposal: two -> four, preserving old turns.
    p=preview(c,{'nodes':[{'node':center},node(800,800),node(800,600)],'edges':[edge(0,1),edge(0,2)]})
    r=commit(c,p);assert r['result']['verified'],r
    assert len(c.lua.globals().components[center][107].laneConnections)==12


def test_split_exact_curve_and_remap_old_crosswalks(tmp_path):
    c=graph_channel(tmp_path)
    p=preview(c,{'nodes':[node(700,700),node(800,700),node(900,700)],'edges':[edge(0,1),edge(1,2)]})
    r=commit(c,p);assert r['result']['verified'],r
    split=r['result']['edges'][0]
    c.lua.globals().SPLIT=split
    c.lua.execute('''local e=components[SPLIT][102];local id=components[e.node0][107] and e.node0 or e.node1
      components[id][107].crosswalks={SPLIT};OLD_NODE=id
      components[SPLIT][102].tangent0.y=20;components[SPLIT][102].tangent1.y=-20''')
    comp=c.lua.globals().components[split][102]
    x=(comp.position0.x+comp.position1.x)/2
    calls=c.lua.globals().previewCalls
    p=preview(c,{'nodes':[{'split':{'edge':split,'param':.5}},node(x,800)],'edges':[edge(0,1)]})
    assert p['structural_only'] and not p['nativePreviewPassed']
    assert c.lua.globals().previewCalls==calls
    r=commit(c,p);assert r['ok'] and r['result']['verified'],r
    assert c.lua.globals().components[split] is None
    assert c.lua.globals().components[c.lua.globals().OLD_NODE][107].crosswalks[1]!=split
    assert c.lua.globals().previewCalls==calls
    new_nodes=c.lua.globals().LAST_GRAPH.streetProposal.nodesToAdd
    assert any(abs(new_nodes[i].comp.position.y-705)<1e-6 for i in range(1,len(new_nodes)+1))


@pytest.mark.parametrize('kind', ['bridge','tunnel'])
def test_explicit_structure_resource(tmp_path,kind):
    c=graph_channel(tmp_path)
    p=preview(c,{'nodes':[node(700,700,20),node(800,700,20)],'edges':[edge(0,1,structure=kind,structure_resource='native.structure')]})
    r=commit(c,p);assert r['ok'] and r['result']['verified'],r
    e=c.lua.globals().components[r['result']['edges'][0]][102]
    assert e.type==(1 if kind=='bridge' else 2) and e.typeIndex==7


@pytest.mark.parametrize('flag',['WRONG_LANES','WRONG_TANGENT','WRONG_STYLE','WRONG_TURN','BAD_SIGNAL','MISSING_NETWORK','CUSTOM_FLAG'])
def test_wrong_readback_keeps_pending(tmp_path,flag):
    c=graph_channel(tmp_path)
    p=preview(c,{'nodes':[node(700,700),node(800,700),node(900,700)],'edges':[edge(0,1),edge(1,2)]})
    c.lua.globals()[flag]=True
    r=commit(c,p)
    assert r['ok'] and r['result']['built'] and not r['result']['verified'],r
    assert c.state['v']['uiConstruction']['pending']


@pytest.mark.parametrize('mutation', ['NOW=161','api.res.streetTemplateRep.get=function()return {roadType=99}end'])
def test_stale_consumed_without_dispatch(tmp_path,mutation):
    c=graph_channel(tmp_path);p=preview(c,{'nodes':[node(700,700),node(800,700)],'edges':[edge(0,1)]})
    c.lua.execute(mutation)
    assert not commit(c,p)['ok'] and c.lua.globals().dispatches==0
    assert not commit(c,p)['ok'] and c.lua.globals().dispatches==0


def highway_lanes(forward=True):
    return [{'width':3.5,'offset':0,'forward':forward,'transportModes':{'2':True,'3':True,'4':True}} for _ in range(2)]


def test_native_highway_repeated_offsets_include_shoulders():
    lanes=[{'width':width,'offset':0,'forward':i!=0,
            'transportModes':{'2':i in (1,2),'3':i in (1,2),'4':i in (1,2)}}
           for i,width in enumerate((4,5,5,4))]
    p=paired_highway([dict(x=0,y=0,z=0),dict(x=100,y=0,z=0)],HIGHWAY,lanes)
    assert p['native_lane_width']==18 and p['center_offset']==11
    assert abs(p['graph']['nodes'][0]['position']['y']-p['graph']['nodes'][2]['position']['y'])==22


@pytest.mark.parametrize('forward', [False,True])
@pytest.mark.parametrize('side', ['left','right'])
def test_dual_highway_actual_direction_and_separation(forward,side):
    p=paired_highway([dict(x=700,y=700,z=2),dict(x=800,y=700,z=2)],HIGHWAY,highway_lanes(forward),4,side)
    assert road_graph(p['graph'])
    dirs=p['directions'];nodes=p['graph']['nodes']
    for d in dirs:
        a,b=nodes[d['entry']]['position'],nodes[d['exit']]['position']
        assert (b['x']>a['x']) == (d['travel']=='A_to_B')
    ya=nodes[dirs[0]['entry']]['position']['y'];yb=nodes[dirs[1]['entry']]['position']['y']
    assert (ya<yb)==(side=='right') and abs(ya-yb)==11


def test_highway_whole_graph_one_native_proposal(tmp_path):
    c=graph_channel(tmp_path)
    native=c.query('get_network_template',{'template':HIGHWAY});assert native['ok'],native
    plan=paired_highway([dict(x=x,y=700,z=2) for x in (700,800,900)],HIGHWAY,native['result']['laneConfigs'])
    p=preview(c,plan['graph']);r=commit(c,p)
    assert r['ok'] and r['result']['verified'] and len(r['result']['edges'])==4,r
    assert c.lua.globals().dispatches==1


@pytest.mark.parametrize('change', ['duplicate','bool_index','unknown','missing_z','unused','structure','nan'])
def test_strict_graph_schema(change):
    g={'nodes':[node(700,700),node(800,700)],'edges':[edge(0,1)]}
    if change=='duplicate':g['edges'].append(edge(1,0))
    elif change=='bool_index':g['edges'][0]['from']=True
    elif change=='unknown':g['edges'][0]['ignoreErrors']=True
    elif change=='missing_z':del g['nodes'][0]['position']['z']
    elif change=='unused':g['nodes'].append(node(900,700))
    elif change=='structure':g['edges'][0]['structure']='bridge'
    elif change=='nan':g['nodes'][0]['position']['z']=float('nan')
    assert not road_graph(g)
    with pytest.raises(ValueError):validate_build_arguments('preview_road_graph',{'graph':g,'isolated_test':True})


def test_no_explicit_isolation_never_dispatches(tmp_path):
    c=graph_channel(tmp_path)
    r=c.query('preview_road_graph',{'graph':{'nodes':[node(700,700),node(800,700)],'edges':[edge(0,1)]},'isolated_test':False})
    assert not r['ok'] and c.lua.globals().dispatches==0 and c.lua.globals().previewCalls==0


def test_implicit_existing_node_materializes_all_old_turns(tmp_path):
    c=graph_channel(tmp_path)
    center=c.lua.globals().STREET_B
    p=preview(c,{'nodes':[{'node':center},node(100,100)],'edges':[edge(0,1)]})
    r=commit(c,p);assert r['ok'] and r['result']['verified'],r
    assert len(c.lua.globals().components[center][107].laneConnections)==6


def test_construction_external_port_preserves_owned_stub(tmp_path):
    c=graph_channel(tmp_path)
    c.lua.execute('''frozen[EDGE_AB]=999
      components[999]={[api.type.ComponentType.CONSTRUCTION]={frozenNodes={9998},frozenEdges={EDGE_AB}}}''')
    old=c.lua.globals().EDGE_AB
    p=preview(c,{'nodes':[{'node':c.lua.globals().STREET_A},node(-100,0)],'edges':[edge(0,1)]})
    r=commit(c,p);assert r['ok'] and r['result']['verified'],r
    assert c.lua.globals().components[old][102] is not None


def test_duplicate_existing_edge_rejected(tmp_path):
    c=graph_channel(tmp_path)
    r=c.query('preview_road_graph',{'graph':{'nodes':[{'node':c.lua.globals().STREET_A},{'node':c.lua.globals().STREET_B}],
                                           'edges':[edge(0,1)]},'isolated_test':True})
    assert not r['ok'] and c.lua.globals().dispatches==0 and c.lua.globals().previewCalls==0


def test_split_preserves_explicit_deadend_crosswalk(tmp_path):
    c=graph_channel(tmp_path)
    c.lua.execute('''local cfg=api.type.BaseNodeLaneConnectionAndEntity.new().comp
      cfg.crosswalks={EDGE_AB};components[STREET_A][107]=cfg''')
    old=c.lua.globals().EDGE_AB
    p=preview(c,{'nodes':[{'split':{'edge':old,'param':.5}},node(50,100)],'edges':[edge(0,1)]})
    r=commit(c,p);assert r['ok'] and r['result']['verified'],r
    cfg=c.lua.globals().components[c.lua.globals().STREET_A][107]
    assert len(cfg.laneConnections)==0 and cfg.crosswalks[1]!=old
    assert c.lua.globals().components[cfg.crosswalks[1]][102] is not None


def test_roundabout_and_ramp_one_proposal(tmp_path):
    c=graph_channel(tmp_path)
    points=[node(700+100*math.cos(i*math.pi/4),700+100*math.sin(i*math.pi/4)) for i in range(8)]
    g={'nodes':points+[node(900,700)],'edges':[edge(i,(i+1)%8,template=HIGHWAY) for i in range(8)]+[edge(0,8,template=HIGHWAY)]}
    p=preview(c,g);r=commit(c,p)
    assert r['ok'] and r['result']['verified'],r
    assert len(r['result']['edges'])==9 and len(r['result']['junctions'])==8
    cfgs=c.lua.globals().LAST_GRAPH.streetProposal.nodeConfigsToAdd
    # Two incoming lanes of ring feed two outgoing lanes each on ring and exit.
    assert sorted(len(cfgs[i].comp.laneConnections) for i in range(1,len(cfgs)+1))==[4]*7+[8]


@pytest.mark.parametrize('case',['objects','frozen','foreign','rail','custom_signals','custom_turns'])
def test_unsupported_edits_fail_before_preview(tmp_path,case):
    c=graph_channel(tmp_path)
    args={'nodes':[{'split':{'edge':c.lua.globals().EDGE_AB,'param':.5}},node(50,100)],'edges':[edge(0,1)]}
    if case=='objects':c.lua.execute('components[EDGE_AB][102].objects={{123,0}}')
    elif case=='frozen':c.lua.execute('frozen[STREET_A]=999;components[999]={[api.type.ComponentType.CONSTRUCTION]={frozenNodes={STREET_A},frozenEdges={EDGE_AB}}}')
    elif case=='foreign':c.lua.execute('components[EDGE_AB][api.type.ComponentType.PLAYER_OWNED]={player=777}')
    elif case=='rail':c.lua.execute('components[EDGE_AB][102].roadType=0')
    else:
        c.lua.execute('''local cfg=api.type.BaseNodeLaneConnectionAndEntity.new().comp
          cfg.laneConnections={{segment0=EDGE_AB,segment1=EDGE_BC,lane0=1,lane1=2,withRoad=true,withTram=false}}
          components[STREET_B][107]=cfg''')
        if case=='custom_signals':c.lua.execute('components[STREET_B][107].userModifiedTrafficLightStates=true')
        else:c.lua.execute('components[STREET_B][107].userModifiedLaneConnections=true')
        args={'nodes':[{'node':c.lua.globals().STREET_B},node(100,100)],'edges':[edge(0,1)]}
    r=c.query('preview_road_graph',{'graph':args,'isolated_test':True})
    assert not r['ok'] and c.lua.globals().dispatches==0 and c.lua.globals().previewCalls==0,r


def test_native_lane_userdata_not_pairs(tmp_path):
    from test_ui_network_native_snapshots import NativeRecord
    c=graph_channel(tmp_path)
    def native(i):
        return NativeRecord(speed=20,width=3,height=0,offset=-1.5 if i==1 else 1.5,
                            forward=i==2,transportModes=c.lua.table_from({2:True,4:True}))
    c.lua.globals().native_lane=native
    c.lua.execute('''local get=api.res.streetTemplateRep.get
      api.res.streetTemplateRep.get=function(id)local t=get(id);t.laneConfigs={native_lane(1),native_lane(2)};return t end''')
    p=preview(c,{'nodes':[node(700,700),node(800,700),node(900,700)],'edges':[edge(0,1),edge(1,2)]})
    r=commit(c,p);assert r['ok'] and r['result']['verified'],r


def test_no_automatic_replay_lost_callback_and_readable_operation(tmp_path):
    c=graph_channel(tmp_path);p=preview(c,{'nodes':[node(700,700),node(800,700)],'edges':[edge(0,1)]})
    c.lua.globals().LOST=True;r=commit(c,p)
    assert r['ok'] and not r['result']['verified'] and c.lua.globals().dispatches==1
    result=c.query('get_road_graph_operation',{'operation_id':p['preview_token']})
    assert result['ok'] and result['result']['phase']=='unconfirmed'
    assert c.state['v']['uiConstruction']['pending'] and c.lua.globals().dispatches==1


@pytest.mark.parametrize('change',['directions','width','reversing','overlong','sharp','overlap'])
def test_invalid_highway_profiles_and_corridors(change):
    lanes=highway_lanes();points=[dict(x=0,y=0,z=0),dict(x=100,y=0,z=0)]
    if change=='directions':lanes[0]['forward']=False
    elif change=='width':lanes[0]['width']=float('nan')
    elif change=='reversing':points.append(dict(x=0,y=0,z=0))
    elif change=='overlong':points[1]['x']=500
    elif change=='sharp':points.append(dict(x=100,y=100,z=0))
    elif change=='overlap':
        # Smooth full circle returns to start: non-adjacent carriageways intersect.
        points=[dict(x=100*math.cos(i*math.pi/4),y=100*math.sin(i*math.pi/4),z=0) for i in range(9)]
    with pytest.raises(ValueError):paired_highway(points,HIGHWAY,lanes)
