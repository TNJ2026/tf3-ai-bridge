import asyncio
import copy
import json
from pathlib import Path

import pytest

from tf3_mcp.flat_areas import FlatTerrain,grid_digest,preference_key,svg_layer
from test_development_planner import snapshot,bounds
from test_site_planner import request
from tf3_mcp.site_planner import search_sites


def grid(nx=7,ny=7,spacing=10):
    return dict(x=0,y=0,nx=nx,ny=ny,spacing=spacing,heights=[0]*(nx*ny),water=[False]*(nx*ny))


def test_regions_preserve_water_holes_instead_of_treating_bounds_as_flat():
    g=grid();g['water'][3*7+3]=True;before=copy.deepcopy(g)
    terrain=FlatTerrain(g);report=terrain.report()
    assert g==before and report['summary']['flatCells']==32
    cells={(x,y)for r in report['regions']for y,a,b in r['cellRuns']for x in range(a,b)}
    assert (2,2)not in cells and (3,3)not in cells
    assert report['regions'][0]['bounds']==bounds(0,0,60)
    assert not terrain.profile(bounds(0,0,60))['dry']
    assert report['buildable']is None and report['requiresNativePreview'] and report['gameCalls']==0


def test_diagonal_patches_are_separate_and_steep_interior_is_seen():
    g=grid(3,3);g['water'][2]=True;g['water'][6]=True
    assert len(FlatTerrain(g).report()['regions'])==2
    g=grid();g['heights'][3*7+3]=6
    p=FlatTerrain(g).profile(bounds(0,0,60))
    assert p['maxGroundGrade']>.05 and p['heightRangeM']==6 and not p['flatPreferred']


def test_a_gently_sloping_large_region_is_not_a_level_collection_pad():
    g=grid(21,3);g['heights']=[(i%21)*.4 for i in range(63)]
    p=FlatTerrain(g).profile(dict(min=dict(x=0,y=0),max=dict(x=200,y=20)))
    assert p['maxGroundGrade']==pytest.approx(.04) and p['heightRangeM']==8
    assert not p['flatPreferred']


def test_outside_unknown_and_malformed_inputs_fail_closed():
    t=FlatTerrain(grid())
    assert t.profile(bounds(-1,0,10))['outsideSurvey']
    with pytest.raises(ValueError,match='inverted'):t.profile(dict(min=dict(x=2,y=0),max=dict(x=1,y=1)))
    g=grid();g['heights'][0]=float('nan')
    with pytest.raises(ValueError):FlatTerrain(g)
    g=grid();g['water'][0]=None
    with pytest.raises(ValueError,match='booleans'):FlatTerrain(g)


def test_flat_ground_beats_shorter_distance_and_steep_access_is_demoted():
    g=grid(11,3);g['heights']=[max(0,5-i%11)*.6 for i in range(33)]
    t=FlatTerrain(g);near=t.profile(bounds(10,0,10));far=t.profile(bounds(70,0,10))
    assert preference_key(far,far,100)<preference_key(near,near,1)
    assert preference_key(far,near,1)>preference_key(far,far,100)


def test_batch_siting_defaults_to_flat_first_with_explicit_legacy_ranking():
    s=snapshot();s['grid']['heights']=[max(0,12-i%21)*1.5 for i in range(441)]
    r=request(radius=150,rotations=[0]);flat=search_sites(s,[r],max_candidates=1)['sites'][0]
    legacy=search_sites(s,[dict(r,ranking='distance_height')],max_candidates=1)['sites'][0]
    assert flat['position']['x']>=625 and legacy['distance']<=50
    assert legacy['terrain']['heightRangeM']>flat['terrain']['heightRangeM']
    assert flat['terrain']['heightRangeM']==0 and flat['requiresNativePreview']
    with pytest.raises(ValueError,match='ranking'):search_sites(s,[dict(r,ranking='anything')])


def test_capture_derives_flat_regions_from_one_read_without_a_card(tmp_path,monkeypatch):
    from tf3_mcp import server
    s=snapshot();s.update(scope='global',coverage={},consistency='one command');calls=[]
    async def read(command,**kwargs):
        calls.append(command);return copy.deepcopy(s)
    monkeypatch.setattr(server,'_call',read)
    r=asyncio.run(server.capture_planning_snapshot(str(tmp_path)))
    layer=json.loads(Path(r['flat_areas_path']).read_text('utf8'))
    assert calls==['get_planning_snapshot'] and layer['gridDigest']==grid_digest(s['grid'])
    assert layer['refinement']['requiredBeforeNativePreview'] and not list(tmp_path.glob('report-*'))
    calls.clear();r=asyncio.run(server.capture_planning_snapshot(str(tmp_path/'off'),include_flat_areas=False))
    assert calls==['get_planning_snapshot'] and 'flat_areas_path'not in r


def test_svg_uses_exact_region_runs_and_has_no_opaque_background():
    import xml.etree.ElementTree as ET
    r=FlatTerrain(grid()).report();root=ET.fromstring(svg_layer(r))
    assert len(root.findall('.//{http://www.w3.org/2000/svg}rect'))==6
    assert root.attrib['viewBox']=='0 0 60 60'
