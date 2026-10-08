import pytest
from test_e2e import FakeGame, bridge_dir, run
from tf3_mcp.bridge import Bridge

NETWORK = r'''
local CT=api.type.ComponentType
CT.BASE_NODE_CONFIG=107;CT.TRANSPORT_NETWORK=108
api.type.enum.TransportMode.CAR=2;api.type.enum.TransportMode.TRUCK=4
components[STREET_C][107]={laneConnections={}}
refreshed={};phases={};rejectRefresh=false;useDetour=false
local get=api.engine.getComponent
api.engine.getComponent=function(id,ct)
 local e=components[id] and components[id][CT.BASE_EDGE]
 if ct==108 and e then
  local function n(node,index)return {entity=node,index=index,edge=id}end
  return {edges={{transportModes={[2]=true,[4]=true},conns={n(e.node0,0),n(e.node1,0)}},
                {transportModes={[2]=true,[4]=true},conns={n(e.node1,1),n(e.node0,1)}}}}
 end
 if ct==108 and components[id] and components[id][CT.BASE_NODE] then return {nodes={},edges={}}end
 return get(id,ct)
end
api.engine.util.pathfinding={findPathNodeToNode=function(from,to,modes)
 local a,b=from[1].edge,to[1].edge
 local x,y=components[a][CT.BASE_EDGE],components[b][CT.BASE_EDGE]
 local node=(x.node0==y.node0 or x.node0==y.node1) and x.node0 or x.node1
 if not refreshed[node] then return {}end
 if useDetour then return {{{entity=999999},true},{{entity=b},true}}end
 return {{{entity=a},true},{{entity=node},true},{{entity=b},true}}
end}
local send=api.cmd.sendCommand
api.cmd.sendCommand=function(cmd,callback)
 if cmd.kind=='build' then
  local p=cmd.proposal.streetProposal
  if #(p.nodesToAdd or {})>0 then phases[#phases+1]='build';assert(not p.nodeConfigsToRemove)end
  if p.nodeConfigsToRemove then
   assert(#(p.edgesToAdd or {})==0);phases[#phases+1]='clear'
  end
  if p.edgesToRemove then
   phases[#phases+1]='refresh';assert(cmd.ignoreErrors==false)
   if rejectRefresh then callback({},false,{});return end
   local e=components[p.edgesToRemove[1]][CT.BASE_EDGE]
   if not components[STREET_C][107] then refreshed[STREET_C]=true end
  end
 end
 return send(cmd,callback)
end
'''


def build(b,game,preview=False):
    return run(b.call('build_road',{'start':{'node':game.lua.globals().STREET_C},
                                   'end':{'x':300,'y':0},'preview':preview}))


def test_dead_end_requires_clear_then_refresh_and_new_ids(bridge_dir):
    with FakeGame(bridge_dir) as g:
        g.lua.execute(NETWORK);r=build(Bridge(bridge_dir,timeout=5),g)
        assert r['built'] and r['verified'] and r['complete']
        assert list(g.lua.globals().phases.values())==['build','clear','refresh']
        assert r['connections']['junctions'][0]['repaired']
        for e in r['edges']:assert g.lua.globals().components[e] is not None


@pytest.mark.parametrize('mode',['reject','detour','custom'])
def test_incomplete_connection_is_not_reported_complete(bridge_dir,mode):
    with FakeGame(bridge_dir) as g:
        g.lua.execute(NETWORK)
        if mode=='reject':g.lua.execute('rejectRefresh=true')
        elif mode=='detour':g.lua.execute('useDetour=true')
        else:g.lua.execute('components[STREET_C][107].laneConnections={{segment0=EDGE_BC}}')
        r=build(Bridge(bridge_dir,timeout=5),g)
        assert r['built'] and not r['verified'] and not r['complete']
        assert 'do not rebuild' in r['reason']['messages'][0]
        if mode=='custom':assert 'clear' not in list(g.lua.globals().phases.values())


def test_preview_never_refreshes(bridge_dir):
    with FakeGame(bridge_dir) as g:
        g.lua.execute(NETWORK);r=build(Bridge(bridge_dir,timeout=5),g,preview=True)
        assert r['buildable'] and not list(g.lua.globals().phases.values())


def test_healthy_junction_does_not_rebuild(bridge_dir):
    with FakeGame(bridge_dir) as g:
        g.lua.execute(NETWORK+'\nrefreshed[STREET_C]=true')
        r=build(Bridge(bridge_dir,timeout=5),g)
        assert r['complete'] and list(g.lua.globals().phases.values())==['build']


@pytest.mark.parametrize('preview', [True, False])
def test_frozen_internal_node_rejected_before_native_proposal(bridge_dir, preview):
    from tf3_mcp.bridge import BridgeError
    with FakeGame(bridge_dir) as g:
        g.lua.execute(NETWORK + '''
frozen[EDGE_BC]=9000
components[9000]={[api.type.ComponentType.CONSTRUCTION]={frozenNodes={STREET_C}}}
api.engine.util.proposal.makeProposalData=function() error('native preview must not run') end
''')
        with pytest.raises(BridgeError, match='frozen construction node'):
            build(Bridge(bridge_dir,timeout=5), g, preview=preview)
        assert not list(g.lua.globals().phases.values())


@pytest.mark.parametrize('target', ['node', 'edge'])
def test_missing_transport_network_rejected_before_native_preview(bridge_dir, target):
    from tf3_mcp.bridge import BridgeError
    with FakeGame(bridge_dir) as g:
        g.lua.execute(NETWORK)
        g.lua.execute('''
local prior=api.engine.getComponent
local broken=''' + ('STREET_C' if target=='node' else 'EDGE_BC') + '''
api.engine.getComponent=function(id,ct)if id==broken and ct==108 then return nil end;return prior(id,ct)end
api.engine.util.proposal.makeProposalData=function()error('native preview must not run')end
''')
        with pytest.raises(BridgeError,match='missing TRANSPORT_NETWORK'):
            build(Bridge(bridge_dir,timeout=5),g,preview=True)
        assert not list(g.lua.globals().phases.values())
