"""Free road ends may omit a config; junctions must never lose theirs."""
from pathlib import Path
import pytest
from lupa import LuaRuntime, LuaError
from test_ui_consolidated import Channel

SOURCE = Path(__file__).resolve().parents[2] / 'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua'


@pytest.fixture
def stop_builder():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
      edge={node0=10,node1=11,objects={}}
      configs={[11]={laneConnections={{segment0=20,segment1=21,lane0=1,lane1=2,withRoad=true,withTram=true}},
        crosswalks={20,21},trafficLightPreference=2}}
      adjacency={[10]={20},[11]={20,21}}
      function getComponent(id,kind)
        if kind=='BASE_NODE_CONFIG' then return configs[id] end
        if kind=='BASE_NODE' and id~=missing then return {position={x=0,y=0,z=0}} end
      end
      function isFrozenStreetNode(id)return id==frozen end
      function listOf(v)return v end
      function currentYear()return 1961 end
      api={type={ComponentType={BASE_EDGE=1,BASE_EDGE_STREET=2},enum={EdgeObjectType={STOP_LEFT=0,STOP_RIGHT=1}},
        SegmentAndEntity={new=function()return {} end},LaneConnection={new=function()return {} end},
        BaseNodeLaneConnectionAndEntity={new=function()return {} end},
        SimpleProposal={new=function()return {streetProposal={}} end},
        SimpleStreetProposal={EdgeObject={new=function()return {} end}}},
        engine={getComponent=function()return edge end,util={getPlayer=function()return 1 end},
        system={streetSystem={getNodeSegments=function(id)return adjacency[id] end}}}}
    ''')
    source = SOURCE.read_text(encoding='utf-8')
    builder = lua.execute(source[source.index('local function makeStopProposal('):source.index('commands.build_street_stop =')] + '\nreturn makeStopProposal')
    return lua, lambda: builder(20, lua.globals().edge, 'road', lua.table(), .3, False, 'small_mid_twosided.con', None)


def test_free_end_keeps_junction_config_and_tram_references(stop_builder):
    lua, build = stop_builder
    proposal = build()['streetProposal']
    assert list(proposal['nodeConfigsToRemove'].values()) == [11]
    cfg = proposal['nodeConfigsToAdd'][1]['comp']
    assert list(cfg['crosswalks'].values()) == [-1, 21]
    assert cfg['laneConnections'][1]['segment0'] == -1
    assert cfg['laneConnections'][1]['segment1'] == 21
    assert cfg['laneConnections'][1]['withTram'] is True
    assert cfg['trafficLightPreference'] == 2
    assert len(proposal['edgeObjectsToAdd']) == 2
    assert list(proposal['edgesToRemove'].values()) == [20]


@pytest.mark.parametrize('change', ['adjacency[10]={}', 'adjacency[10]={21}',
    'adjacency[10]={20,21}', 'frozen=10', 'missing=10'])
def test_missing_config_refuses_unproven_endpoint(stop_builder, change):
    lua, build = stop_builder
    lua.execute(change)
    with pytest.raises(LuaError, match='outside a free road end'):
        build()


def test_explicit_empty_config_is_preserved_not_treated_as_absent(stop_builder):
    lua, build = stop_builder
    lua.execute('configs[10]={laneConnections={},crosswalks={20}}')
    proposal = build()['streetProposal']
    assert len(proposal['nodeConfigsToAdd']) == 2
    assert len(proposal['nodeConfigsToAdd'][1]['comp']['laneConnections']) == 0
    assert proposal['nodeConfigsToAdd'][1]['comp']['crosswalks'][1] == -1


def test_edge_preview_invalidated_by_new_neighbor_before_dispatch(tmp_path):
    channel = Channel(tmp_path)
    edge = channel.lua.globals().EDGE_AB
    p = channel.query('preview_road_upgrade', {'edge':edge,'street_type':'town/town_old_medium'})
    assert p['ok'], p
    channel.lua.execute('''
      local original=api.engine.system.streetSystem.getNodeSegments
      api.engine.system.streetSystem.getNodeSegments=function(node)
        local result=original(node);result[#result+1]=99999;return result
      end
    ''')
    r = channel.query('commit_edge_edit', {'preview_token':p['result']['preview_token']})
    assert not r['ok'] and 'Edge/player changed' in r['error']
    assert channel.lua.globals().dispatches == 0
    assert not channel.state['v']['uiConstruction']['pending']
