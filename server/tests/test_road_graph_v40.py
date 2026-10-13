"""Preservation and rejection tests for v40; these are not native acceptance."""
from copy import deepcopy
import pytest
from test_road_graph import graph_channel,node,edge,preview,commit
from test_road_graph_special import special,crossing_graph
from tf3_mcp.road_graph import road_graph


@pytest.mark.parametrize('count,pending',[(255,False),(256,False),(1024,False),(255,True)])
def test_saved_budget_retains_receipts_pending_and_finite_limit(tmp_path,count,pending):
    c=graph_channel(tmp_path)
    c.lua.globals().TEST_STATE=c.state
    c.lua.execute(f'''local requests={{}}
      for i=1,{count} do requests[string.format('%032x',i)]={{status='returned',cmd='commit_road_graph',ok=true}} end
      TEST_STATE.v.uiConstruction={{requests=requests,tokens={{}},count={count},pending={"'unresolved'" if pending else 'nil'}}}''')
    old=c.state['v']['uiConstruction']['requests']['00000000000000000000000000000001']
    r=c.query('preview_road_graph',{'graph':{'nodes':[node(700,700),node(800,700)],'edges':[edge(0,1)]},'isolated_test':True})
    assert r['ok']==(count<256),r
    ledger=c.state['v']['uiConstruction']
    assert ledger['requests']['00000000000000000000000000000001']['cmd']==old['cmd']
    assert ledger['count']==count+(count<256)
    assert ledger['pending']==('unresolved' if pending else None)
    assert c.lua.globals().dispatches==0
    # Re-delivery of this exact engine event must neither emit nor consume again.
    before=ledger['count'];e=c.lua.globals().forwarded
    c.game.script['handleEvent'](None,c.state,'',e['id'],e['name'],e['param'])
    assert c.state['v']['uiConstruction']['count']==before
    if pending:
        result=commit(c,r['result'])
        assert not result['ok'] and c.lua.globals().dispatches==0
        assert c.state['v']['uiConstruction']['pending']=='unresolved'

def signal_fixture():
    # Six turns minus west->south, plus west crosswalk: six signal indices.
    phases=[dict(locked_lanes=[j for j in range(6) if j!=i],duration=10+i,min_duration=1,can_skip=True) for i in range(6)]
    policy=dict(blocked_turns=[dict(from_edge=0,to_edge=2)],crosswalk_edges=[0],signals=dict(preference='YES',traffic_light_type=-1,states=phases))
    return {'nodes':[dict(node(700,700),junction=policy),node(600,700),node(800,700),node(700,600)],'edges':[edge(0,1),edge(0,2),edge(0,3)]}

def test_initial_custom_walk_and_banned_turn_then_extension(tmp_path):
    c=special(graph_channel(tmp_path));g=signal_fixture();assert road_graph(g)
    r=commit(c,preview(c,g));assert r['result']['verified'],r
    center=r['result']['entityMap']['-1'];west=r['result']['entityMap']['-5'];south=r['result']['entityMap']['-7']
    cfg=c.lua.globals().components[center][107]
    assert len(cfg.laneConnections)==5 and list(cfg.crosswalks.values())==[west]
    assert not any(t.segment0==west and t.segment1==south for t in cfg.laneConnections.values())
    g={'nodes':[{'node':center,'junction':{'extend':'preserve','phase_duration':7}},node(700,800)],'edges':[edge(0,1)]}
    r=commit(c,preview(c,g));assert r['result']['verified'],r
    cfg=c.lua.globals().components[center][107]
    assert len(cfg.laneConnections)==11 and len(cfg.trafficLightConfig.states)==12
    assert not any(t.segment0==west and t.segment1==south for t in cfg.laneConnections.values())
    assert 11 in list(cfg.trafficLightConfig.states[1].lockedLanes.values())

@pytest.mark.parametrize('fault',['unknown_edge','not_incident','duplicate_walk','no_person','self_turn','all_turns'])
def test_bad_initial_junction_policy_has_no_dispatch(tmp_path,fault):
    c=special(graph_channel(tmp_path));g=signal_fixture();policy=g['nodes'][0]['junction']
    if fault=='unknown_edge':policy['crosswalk_edges']=[47]
    elif fault=='not_incident':g['nodes']+=[node(1000,700),node(1100,700)];g['edges'].append(edge(4,5));policy['crosswalk_edges']=[3]
    elif fault=='duplicate_walk':policy['crosswalk_edges']=[0,0]
    elif fault=='no_person':c.lua.execute('LANES[1].transportModes={};LANES[4].transportModes={}')
    elif fault=='self_turn':policy['blocked_turns']=[dict(from_edge=0,to_edge=0)]
    else:policy['blocked_turns']=[dict(from_edge=a,to_edge=b) for a in range(3) for b in range(3) if a!=b]
    if not road_graph(g):
        with pytest.raises(ValueError):c.query('preview_road_graph',{'graph':g,'isolated_test':True})
        assert c.lua.globals().dispatches==0
    else:
        r=c.query('preview_road_graph',{'graph':g,'isolated_test':True});assert not r['ok'] and c.lua.globals().dispatches==0,r

def tunnel(c):
    c.lua.execute('''for _,id in ipairs({EDGE_AB,EDGE_BC})do components[id][102].type=2;components[id][102].typeIndex=7 end''')
    return {'nodes':[{'split':{'edge':c.lua.globals().EDGE_AB,'param':.5,'allow_structure':True,'preserve_tunnel_chain':True}}],'edges':[]}

def test_partial_tunnel_split_replaces_neighbor_without_splitting_it(tmp_path):
    c=special(graph_channel(tmp_path));g=tunnel(c);assert road_graph(g);p=preview(c,g)
    assert p['replacedEdges']==2 and p['segments']==3 and p['specialCases']['preservedTunnelNeighbors']==[c.lua.globals().EDGE_BC]
    r=commit(c,p);assert r['result']['verified'],r
    sp=c.lua.globals().LAST_GRAPH.streetProposal
    assert len(sp.nodesToAdd)==1 and len(sp.edgesToAdd)==3 and c.lua.globals().previewCalls==0

@pytest.mark.parametrize('fault',['resource','objects','not_tunnel'])
def test_tunnel_chain_rejects_unsafe_neighbor(tmp_path,fault):
    c=special(graph_channel(tmp_path));g=tunnel(c)
    if fault=='resource':c.lua.execute('components[EDGE_BC][102].typeIndex=99')
    elif fault=='objects':c.lua.execute('components[EDGE_BC][102].objects={{999,0}}')
    else:c.lua.execute('components[EDGE_AB][102].type=0')
    r=c.query('preview_road_graph',{'graph':g,'isolated_test':True});assert not r['ok'] and c.lua.globals().dispatches==0,r

def existing_crossing(c):
    r=commit(c,preview(c,crossing_graph()));assert r['result']['verified']
    center=r['result']['entityMap']['-1'];c.lua.globals().CROSS_CENTER=center
    c.lua.execute('''components[RCID][803].nodes={CROSS_CENTER}
      api.engine.system.railRoadCrossingSystem.getRailroadCrossingForNode=function(id)return id==CROSS_CENTER and RCID or -1 end''')
    return r

@pytest.mark.parametrize('track',[False,True])
def test_split_existing_crossing_arm_preserves_four_way_topology(tmp_path,track):
    c=special(graph_channel(tmp_path));r=existing_crossing(c)
    candidates=[i for i in r['result']['edges'] if (c.lua.globals().components[i][102].roadType==0)==track]
    g={'nodes':[{'split':{'edge':candidates[0],'param':.5,'preserve_crossings':True}}],'edges':[]}
    p=preview(c,g);assert p['replacedEdges']==1
    r=commit(c,p);assert r['result']['verified'] and r['result']['railroadCrossings'][0]['verified'],r

def test_existing_crossing_requires_opt_in(tmp_path):
    c=special(graph_channel(tmp_path));r=existing_crossing(c)
    eid=next(i for i in r['result']['edges'] if c.lua.globals().components[i][102].roadType==1)
    r=c.query('preview_road_graph',{'isolated_test':True,'graph':{'nodes':[{'split':{'edge':eid,'param':.5}}],'edges':[]}})
    assert not r['ok']
