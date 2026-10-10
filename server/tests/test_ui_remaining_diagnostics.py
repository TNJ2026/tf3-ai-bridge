"""Opt-in native port, facility geometry and stock diagnostics fail closed."""
import json

import pytest

from test_e2e import FakeGame
from test_ui_hq_readback import existing
from test_ui_hq_access import access
from test_headquarters import hq_game
from test_ui_cargo_reads import cargo_query
from test_ui_extended_reads import query
from tf3_mcp.ui_log import validate_build_arguments


@pytest.fixture
def opaque_path(tmp_path):
    game = FakeGame(tmp_path / 'game')
    lua = game.lua
    lua.execute('''
api.type.ComponentType.MOVE_PATH=901
api.type.ComponentType.MOVE_PATH_AIRCRAFT=902
api.type.ComponentType.TRANSPORT_NETWORK=903
local a={nodeId={entity=810,index=0},port=0}
local b={nodeId={entity=811,index=1},port=0}
path_ports={a,b};reverse_path=false;port_calls=0
local opaque={opaque_marker=true}
components[701]={[9]={state=1},[901]={path={edges={opaque,opaque,opaque,opaque}},dyn={pathPos={edgeIndex=0,pos=2,pos01=.1},speed=2}}}
components[810]={};components[811]={};components[812]={}
components[800]={[903]={edges={{conns={{entity=810,index=0},{entity=811,index=1}}}}}}
api.engine.util.vehicle=api.engine.util.vehicle or {}
api.engine.util.vehicle.getPosition=function()return {x=1,y=2,z=3}end
api.engine.util.transport={
 getStartPort=function(item)assert(item.opaque_marker);port_calls=port_calls+1;return path_ports[reverse_path and 2 or 1]end,
 getEndPort=function(item)assert(item.opaque_marker);port_calls=port_calls+1;return path_ports[reverse_path and 1 or 2]end}
node_data={ports={{edgeId={entity=800,index=0}}}}
edge_data={ports={a,b}}
api.engine.system.transportNetworkSystem={getTpNetData=function()
 return {getNodeData=function(self,id)return node_data end,getEdgeData=function(self,e)assert(e.entity==800);return edge_data end}
end}
''')
    return game, lua


@pytest.mark.parametrize('reverse', [False, True])
def test_opaque_native_ports_crosscheck_direction_without_path_search(opaque_path, reverse):
    game, lua = opaque_path
    lua.globals().reverse_path = reverse
    call = game.script['_internal']['commands']['get_vehicle_motion']
    default = call(lua.table_from({'vehicle': 701}))
    assert not default['ground']['path']['currentEdgeAvailable']
    assert lua.globals().port_calls == 0
    result = call(lua.table_from({'vehicle': 701, 'resolve_native_path': True}))
    rows = list(result['ground']['path']['samples'].values())
    assert [r['pathIndex'] for r in rows] == [0, 1, 3]
    assert all(r['tupleBase'] == 'native_ports' and r['forward'] == (not reverse) for r in rows)
    assert all(r['edge']['entity'] == 800 and r['portEvidence']['nativePathQueries'] == 0 for r in rows)
    assert lua.globals().port_calls == 6
    assert len(lua.globals().sentCommands) == 0


@pytest.mark.parametrize('mutation,reason', [
    ('path_ports[1].port=-1', 'Invalid native path port'),
    ('path_ports[1].nodeId.entity=99999', 'removed'),
    ('node_data.ports={}', 'index outside node'),
    ('node_data.ports[1].edgeId.index=100', 'index outside network'),
    ('edge_data.ports={path_ports[1],path_ports[1]}', 'Ambiguous'),
    ('edge_data.ports[2]={nodeId={entity=812,index=0},port=0}', 'disagrees'),
    ('api.engine.util.transport.getStartPort=function()error("native port failure")end', 'native port failure'),
])
def test_opaque_native_port_failure_is_not_swallowed(opaque_path, mutation, reason):
    game, lua = opaque_path
    lua.execute(mutation)
    with pytest.raises(Exception, match=reason):
        game.script['_internal']['commands']['get_vehicle_motion'](lua.table_from({'vehicle': 701, 'resolve_native_path': True}))
    assert len(lua.globals().sentCommands) == 0


@pytest.mark.parametrize('returns', ['12345', 'nil', 'false', '"opaque"', '0/0', 'math.huge'])
def test_nonrecord_native_ports_remain_unknown_without_native_graph_calls(opaque_path, returns):
    game, lua = opaque_path
    lua.execute('''
api.engine.util.transport.getStartPort=function()return %s end
api.engine.util.transport.getEndPort=function()return 54321 end
api.engine.system.transportNetworkSystem.getTpNetData=function()error("must not decode scalar ports")end
''' % returns)
    result = game.script['_internal']['commands']['get_vehicle_motion'](
        lua.table_from({'vehicle': 701, 'resolve_native_path': True}))
    path = result['ground']['path']
    assert not path['currentEdgeAvailable']
    assert len(path['samples']) == 3
    for row in path['samples'].values():
        assert not row['available']
        assert row['reason'] == 'unsupported_native_port_representation'
        assert row['portEvidence']['finish']['value'] == 54321
        assert row['portEvidence']['nativePathQueries'] == 0
        assert row['edge'] is None
    assert len(lua.globals().sentCommands) == 0


@pytest.mark.parametrize('direction', [True, False])
def test_documented_edge_id_dir_record_is_read_without_port_fallback(opaque_path, direction):
    game, lua = opaque_path
    lua.globals().record_direction = direction
    lua.execute('''
local item={edgeId={entity=800,index=0},dir=record_direction}
components[701][901].path.edges={item,item,item,item}
api.engine.util.transport.getStartPort=function()error("record already decoded")end
''')
    result = game.script['_internal']['commands']['get_vehicle_motion'](
        lua.table_from({'vehicle': 701, 'resolve_native_path': True}))
    path = result['ground']['path']
    assert path['currentEdgeAvailable']
    for row in path['samples'].values():
        assert row['edge']['entity'] == 800
        assert row['forward'] == direction
        assert row['tupleBase'] == 'edgeId_dir'
    assert len(lua.globals().sentCommands) == 0


def test_disconnected_station_geometry_is_returned_without_claiming_access(existing):
    lua, call = existing
    lua.execute('''
components[700][api.type.ComponentType.CONSTRUCTION].fileName="::/stations/rail/modular_station/modular_station.con"
api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities=function()return {}end
components[701][api.type.ComponentType.TRANSPORT_NETWORK].edges[1].geometry={marker=true}
components[701][api.type.ComponentType.TRANSPORT_NETWORK].edges[1].linkable=1
api.engine.util.transport={calcPosition=function(g,t)assert(g.marker);return {x=10*t,y=25,z=2}end}
''')
    result = call('get_facility_access', entity=700, person_graph=True, person_geometry=True)
    assert not result['automaticRoadLinkObserved']
    graph = result['personGraph']
    assert graph['roads'] == [] and graph['links'] == []
    row = next(x for x in graph['networks'] if x['entity'] == 701)['edges'][0]
    assert row['position0'] == {'x': 0, 'y': 25, 'z': 2}
    assert row['position1'] == {'x': 10, 'y': 25, 'z': 2}
    assert row['linkable'] == 1
    assert graph['facilityEntities'] == graph['hqEntities']
    assert lua.globals().PREVIEW_CALLS == 0 and lua.globals().SUBMISSIONS is None
    assert len(json.dumps(result)) < 6000


def test_geometry_requires_explicit_graph(existing):
    _, call = existing
    with pytest.raises(Exception, match='requires person_graph'):
        call('get_facility_access', entity=700, person_geometry=True)


def test_stock_diagnostic_keeps_mixed_cargo_scope_and_invalid_sentinel(cargo_query):
    cargo_query.lua.execute('''
api.type.ComponentType.SIM_CARGO=904
components[901]={[904]={cargoType=18,sourceEntity=50,targetOrPickupEntity=800,startTime=1,pickupTime=2,deliveryExtensionDuration=0}}
api.engine.system.simEntityAtStockSystem.getStockCount=function(id,slot)return slot==0 and 8 or 2 end
api.engine.system.simEntityAtStockSystem.getStockSimEntity=function(id,slot)return slot==0 and 901 or -1 end
api.engine.util.cargo.getCargoQualityDataForStock=function(id,slot,cargo)
 assert(cargo==nil);return {countTotal=0,countBad=0,isVeryBad=true}
end
''')
    r = cargo_query('get_stock_cargo', {'stock_list': 800, 'cargo': 20, 'diagnostic': True})
    assert r['ok'], r
    stocks = r['result']['stocks']
    d = stocks[0]['diagnostic']
    assert d['allCargoCount'] == 8 and stocks[0]['count'] == 3
    assert d['cargo']['cargoType'] == 18 and not d['requestedCargoMatches']
    assert not d['allCargoQuality']['hasBadCargo']
    assert stocks[1]['diagnostic']['oldestEntity'] == -1
    assert not stocks[1]['diagnostic']['oldestEntityExists']


@pytest.mark.parametrize('command,args', [
    ('get_vehicle_motion', {'vehicle': 701, 'resolve_native_path': 1}),
    ('get_stock_cargo', {'stock_list': 800, 'cargo': 18, 'diagnostic': 'yes'}),
    ('get_facility_access', {'entity': 700, 'person_graph': True, 'person_geometry': 1}),
])
def test_diagnostic_schema_rejects_non_booleans(command, args):
    with pytest.raises(ValueError):
        validate_build_arguments(command, args)
