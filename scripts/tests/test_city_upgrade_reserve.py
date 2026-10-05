"""Regression checks for upgrade space through template, siting and plan geometry."""
import copy
import json
import math
from pathlib import Path

import pytest
from planning_pipeline_core import (FACILITY_HALF_SIZES, facility_bounds, positioned_bounds,
                                    prepare_template, layout_key)
from plan_template_map import collection_candidates
from tf3_mcp.flat_areas import FlatTerrain
from tf3_mcp.planning_geometry import facility_aabb, facility_polygon, intersects, polygon

ROOT = Path(__file__).resolve().parents[2]


def city():
    return json.loads((ROOT/'config/planning_templates/city.json').read_text('utf8'))


def test_default_preserves_positions_modules_and_joint_geometry():
    from hub_joint_prototype import compile_spec
    t = city()
    old = copy.deepcopy(t)
    for f in old['facilities']:
        f.pop('upgradeReserveM')
    actual = compile_spec(t)
    for f in actual['facilities']:
        f.pop('upgradeReserveM', None)
    assert actual == compile_spec(old)
    assert prepare_template(t, 'city') == t
    assert all(f['upgradeReserveM'] for f in t['facilities'])


@pytest.mark.parametrize('padding', [{'maxX': -1}, {'maxY': math.nan},
                                     {'minX': True}, {'left': 10}, [], {'maxX': '20'}])
def test_bad_padding_fails_before_siting(padding):
    t = city(); t['facilities'][0]['upgradeReserveM'] = padding
    with pytest.raises(ValueError, match='reserve'):
        prepare_template(t, 'city')


def test_expansion_into_neighbour_rejected():
    t = city(); t['facilities'][0]['upgradeReserveM'] = {'maxX': 100}
    with pytest.raises(ValueError, match='reservations overlap'):
        prepare_template(t, 'city')


def test_observed_asymmetric_footprint_overrides_generic_size():
    f = dict(role='warehouse', footprintBounds=dict(min=dict(x=-53,y=-19),
             max=dict(x=69,y=141)), upgradeReserveM={'maxY':30})
    assert facility_bounds(f) == f['footprintBounds']
    assert facility_bounds(f, reserved=True)['max']['y'] == 171
    assert positioned_bounds(f, dict(x=100,y=200))['min'] == dict(x=47,y=181)


@pytest.mark.parametrize('bounds', [{}, {'min':{}, 'max':{}},
    dict(min=dict(x=0,y=0),max=dict(x=0,y=1)),
    dict(min=dict(x=0,y=0),max=dict(x=float('nan'),y=1))])
def test_invalid_observed_footprint_rejected(bounds):
    with pytest.raises(ValueError, match='footprint'):
        facility_bounds(dict(role='warehouse',footprintBounds=bounds))


def test_candidate_footprint_uses_observed_bounds():
    g=dict(x=-500,y=-500,nx=41,ny=41,spacing=25,heights=[0]*1681,water=[False]*1681)
    f=dict(role='truck',localPosition=dict(x=0,y=0),relativeRotation=0,
           footprintBounds=dict(min=dict(x=-20,y=-15),max=dict(x=60,y=35)))
    t=dict(facilities=[f],roads=[dict(position0=dict(x=-20,y=0),position1=dict(x=20,y=0))])
    candidates=collection_candidates(t,[1],{1:dict(x=0,y=0)},'production',
                                    FlatTerrain(g),{'truck':(10,10)},dict(x=0,y=0))
    c=next(c for c in candidates if c['rotation']==0 and c['entry']['x']==90)
    assert c['boxes'][0]['max']['x']-c['origin']['x']==60
    assert c['boxes'][0]['min']['y']-c['origin']['y']==-15


@pytest.mark.parametrize('rotation', [0, 45, 90, 180, 270])
def test_rotation_shared_by_siting_export_and_network(rotation):
    f = dict(role='truck', upgradeReserveM={'maxY': 40})
    p = dict(x=100, y=200)
    row = dict(position=p, rotation=rotation,
               footprint=positioned_bounds(f, p), reserved=positioned_bounds(f, p, reserved=True))
    expected = polygon(facility_bounds(f, reserved=True), p, rotation)
    assert facility_polygon(row, 'reserved') == expected
    box = facility_aabb(row)
    assert box['min']['x'] == min(v['x'] for v in expected)
    assert box['max']['y'] == max(v['y'] for v in expected)
    if rotation == 90:
        # Local +Y is world -X. The added land must be protected on that side.
        obstacle = polygon(dict(min=dict(x=31,y=195),max=dict(x=35,y=205)))
        assert intersects(expected, obstacle)
        assert not intersects(facility_polygon(row, 'footprint'), obstacle)


def test_terrain_candidate_includes_directional_reserve_and_rejects_water():
    g = dict(x=-500,y=-500,nx=41,ny=41,spacing=25,
             heights=[0]*1681,water=[False]*1681)
    t = dict(facilities=[dict(role='truck',localPosition=dict(x=0,y=0),
                              relativeRotation=0,upgradeReserveM={'maxY':100})],
             roads=[dict(position0=dict(x=-20,y=0),position1=dict(x=20,y=0))])
    def candidates(grid):
        return collection_candidates(t,[1],{1:dict(x=0,y=0)},'production',
                                     FlatTerrain(grid),{'truck':(10,10)},dict(x=0,y=0))
    candidate = next(c for c in candidates(g) if c['rotation']==0 and c['entry']['x']==90)
    assert candidate['reserveBoxes'][0]['max']['y']==110
    assert candidate['boxes'][0]['max']['y']==10
    # Water lies outside the footprint + old 20 m survey margin, inside expansion.
    wet=copy.deepcopy(g);wet['water'][24*41+24]=True  # (100,100)
    assert not any(c['rotation']==0 and c['entry']['x']==90 for c in candidates(wet))


def test_reserve_changes_invalidate_layout_cache():
    t=city();details=dict(buildings=[],industries=[])
    before=layout_key({},details,{'city':t})
    t['facilities'][0]['upgradeReserveM']['maxY']+=10
    assert before!=layout_key({},details,{'city':t})
