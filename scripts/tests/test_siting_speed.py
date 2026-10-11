"""Cheap exclusions and shared road geometry must preserve siting semantics."""
import copy
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_template_map as planner
from tf3_mcp.flat_areas import FlatTerrain


def template():
    return dict(facilities=[dict(role='truck', localPosition=dict(x=0, y=0),
                                relativeRotation=0)],
                roads=[dict(position0=dict(x=-20, y=0), position1=dict(x=20, y=0))])


def test_unreachable_anchors_skip_terrain_without_changing_ranked_results():
    grid = dict(x=-2000, y=-2000, nx=81, ny=81, spacing=50,
                heights=[0]*6561, water=[False]*6561)
    class CountingTerrain(FlatTerrain):
        calls = 0
        def profile(self, *args, **kwargs):
            self.calls += 1
            return super().profile(*args, **kwargs)
    nodes = {1: dict(x=600, y=0), 2: dict(x=800, y=0)}
    terrain = CountingTerrain(grid)
    args = (nodes, 'city', terrain, {'truck': (10, 10)}, dict(x=0, y=0))
    distances = {2: 900}
    actual = planner.collection_candidates(template(), [1, 2], *args,
                                          city_network_distances=distances)
    calls = terrain.calls
    terrain.calls = 0
    expected = planner.collection_candidates(template(), [2], *args,
                                            city_network_distances=distances)
    assert actual == expected and actual
    assert calls == terrain.calls
    terrain.calls = 0
    assert not planner.collection_candidates(template(), [1], *args,
                                            city_network_distances=distances)
    assert terrain.calls == 0


def test_rejected_footprints_do_not_trigger_access_terrain_queries():
    class WetTerrain:
        calls = 0
        def profile(self, bounds):
            self.calls += 1
            return dict(outsideSurvey=False, dry=False)
    terrain = WetTerrain()
    assert not planner.collection_candidates(template(), [1], {1: dict(x=0, y=0)},
        'production', terrain, {'truck': (10, 10)}, dict(x=0, y=0))
    assert terrain.calls == 8*8  # Every rotation/extension still gets its footprint check.


def test_shared_graph_preserves_curves_parallel_edges_and_disconnected_nodes(monkeypatch):
    def edge(a, b, x0, y0, x1, y1):
        return dict(node0=a, node1=b, position0=dict(x=x0, y=y0),
                    position1=dict(x=x1, y=y1), tangent0=dict(x=0, y=200),
                    tangent1=dict(x=0, y=-200))
    edges = [edge(1, 2, 0, 0, 100, 0), edge(2, 3, 100, 0, 200, 0),
             edge(1, 3, 0, 0, 200, 0), edge(1, 2, 0, 0, 100, 0),
             edge(9, 10, 1000, 0, 1100, 0)]
    calls = []
    original = planner.curve
    def counted(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(planner, 'curve', counted)
    graph = planner.road_distance_graph(edges)
    before = copy.deepcopy(graph)
    d1 = planner.road_service_distances(graph, 1, 7)
    d3 = planner.road_service_distances(graph, 3, 11)
    assert len(calls) == 9*len(edges) and graph == before
    # Independent relaxation oracle, including parallel edges and curved lengths.
    expected = {1: 7}
    for _ in range(len(graph)):
        for node, links in graph.items():
            for other, cost in links:
                if expected.get(node, math.inf)+cost < expected.get(other, math.inf):
                    expected[other] = expected[node]+cost
    assert d1 == expected and d1[2] > 107 and 9 not in d1
    assert math.isclose(d1[3]-7, d3[1]-11)
    assert planner.road_service_distances(graph, 99, 5) == {99: 5}
    assert graph == before
    changed = copy.deepcopy(edges)
    changed[0]['tangent0']['y'] = 400
    assert planner.road_distance_graph(changed) != graph
