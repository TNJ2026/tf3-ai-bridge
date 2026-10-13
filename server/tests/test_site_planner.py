import copy

import pytest

from test_development_planner import snapshot, bounds
from tf3_mcp.site_planner import BoxIndex, search_sites, touches
from tf3_mcp.planning_geometry import dry_access
from tf3_mcp.route_planner import Terrain


def test_access_crossing_water_rejected_before_ranking():
    s=snapshot()
    # A dry candidate at x=500, but its connection from x=200 crosses a wet column.
    for j in range(21):s['grid']['water'][j*21+7]=True
    r=request(radius=1,rotations=[0],access=dict(anchor=dict(x=200,y=500),
                                               local_entry=dict(x=-30,y=0)))
    p=search_sites(s,[r])
    assert not p['sites'] and p['searches'][0]['rejected']['access_crosses_water']==1


def test_access_rotates_entry_and_remains_unverified():
    r=request(radius=1,rotations=[90],access=dict(anchor=dict(x=200,y=500),
                                                local_entry=dict(x=0,y=-30)))
    c=search_sites(snapshot(),[r])['sites'][0]
    assert c['access']['entry']==dict(x=530,y=500)
    assert c['access']['native_verified'] is False and c['requiresNativePreview']


def test_access_grade_and_unknown_bounds_fail_closed():
    s=snapshot();s['grid']['heights']=[i%21*50 for i in range(441)]
    assert dry_access(Terrain(s['grid']),dict(x=100,y=100),dict(x=500,y=100))=='access_grade_requires_design'
    assert dry_access(Terrain(s['grid']),dict(x=-100,y=100),dict(x=500,y=100))=='access_outside_survey'


def request(**changes):
    row = dict(name='仓库', target=dict(x=500,y=500),radius=100,step=25,
               current=bounds(-10,-10,20),reserved=bounds(-25,-25,50),basis='test dimensions')
    row.update(changes)
    return row


def test_rank_reserve_avoidance_and_immutability():
    s=snapshot(); original=copy.deepcopy(s)
    plan=search_sites(s,[request()],reserved_areas=[bounds(520,470,40)])
    assert s==original and plan['metrics']['gameCalls']==0
    assert plan['buildable'] is None and len(plan['sites'])==3
    assert all(not touches(c['reserved'],bounds(520,470,40)) for c in plan['sites'])
    assert plan['searches'][0]['rejected']['obstacle_or_reservation']>0
    assert all(c['requiresNativePreview'] and c['buildable'] is None for c in plan['sites'])


def test_explicit_strict_policy_excludes_water_and_terrain_ridge():
    for field,value,reason in [('water',True,'water'),('heights',100,'height_range')]:
        s=snapshot(); s['grid'][field][10*21+10]=value
        plan=search_sites(s,[request(radius=1,terrain_policy='strict')])
        assert plan['sites']==[]
        assert plan['searches'][0]['rejected'][reason]==2


def test_building_ridge_remains_a_candidate_without_claiming_native_adaptation():
    s=snapshot();s['grid']['heights'][10*21+10]=100
    original=copy.deepcopy(s)
    p=search_sites(s,[request(radius=1,rotations=[0])])
    assert s==original and p['metrics']['gameCalls']==0
    assert p['searches'][0]['rejected']=={}
    c=p['sites'][0]
    assert c['position']==dict(x=500,y=500)
    assert c['heightRange']==[2,100]
    assert c['terrainAssessment']['exceedsHeightReference']
    assert c['terrainAssessment']['adaptationRequired'] is None
    assert not c['terrainAssessment']['placementVerified']
    assert c['requiresNativePreview'] and c['buildable'] is None


@pytest.mark.parametrize('failure',['water','obstacle','access_grade'])
def test_advisory_terrain_does_not_bypass_independent_siting_gates(failure):
    s=snapshot();r=request(radius=1,rotations=[0])
    if failure=='water':
        s['grid']['water'][10*21+10]=True;reason='water'
    elif failure=='obstacle':
        s['obstacles'].append(dict(kind='CONSTRUCTION',entity=800,**bounds(490,490,20)))
        reason='obstacle_or_reservation'
    else:
        s['grid']['heights']=[i%21*50 for i in range(441)]
        r['access']=dict(anchor=dict(x=200,y=500),local_entry=dict(x=-30,y=0))
        reason='access_grade_requires_design'
    p=search_sites(s,[r])
    assert not p['sites'] and p['searches'][0]['rejected'][reason]==1


def test_building_adaptation_policy_does_not_apply_to_street_stops():
    s=street_snapshot();s['grid']['heights']=[i%21*50 for i in range(441)]
    r=request(kind='street_stop',edges=[7],radius=400)
    p=search_sites(s,[r])
    assert not p['sites'] and p['searches'][0]['terrainPolicy']=='strict'
    assert p['searches'][0]['rejected']['height_range']==3
    with pytest.raises(ValueError,match='street_stop terrain_policy'):
        search_sites(s,[dict(r,terrain_policy='advisory')])
    with pytest.raises(ValueError,match='terrain_policy'):
        search_sites(snapshot(),[request(terrain_policy='ignore_everything')])


def test_unknown_bounds_and_budget_do_not_become_clear():
    p=search_sites(snapshot(),[request(target=dict(x=0,y=0),radius=1)])
    assert p['sites']==[] and p['searches'][0]['rejected']['outside_survey']==2
    with pytest.raises(ValueError,match='budget'):
        search_sites(snapshot(),[request(radius=5000,step=10)])
    with pytest.raises(ValueError,match='contain current'):
        search_sites(snapshot(),[request(reserved=bounds(0,0,5))])


def street_snapshot():
    s=snapshot()
    edge=dict(entity=7,kind='BASE_EDGE',**dict(min=dict(x=200,y=495),max=dict(x=800,y=505)),
              position0=dict(x=200,y=500),position1=dict(x=800,y=500),
              tangent0=dict(x=600,y=0),tangent1=dict(x=600,y=0))
    s['obstacles']=[edge]
    return s


def test_stop_only_excludes_host_edge_and_requires_revalidation():
    s=street_snapshot()
    r=request(kind='street_stop',edges=[7],radius=400)
    p=search_sites(s,[r])
    assert len(p['sites'])==3
    assert p['sites'][0]['param']==.5 and p['sites'][0]['edge']==7
    assert p['sites'][0]['requiresStreetValidation']
    s['obstacles'].append(dict(entity=8,kind='BASE_EDGE',**bounds(475,475,50)))
    p=search_sites(s,[r])
    assert len(p['sites'])==2
    assert all(c['param']!=.5 for c in p['sites'])
    with pytest.raises(ValueError,match='not found'):
        search_sites(s,[request(kind='street_stop',edges=[99])])


def test_index_matches_full_scan_including_degenerate_and_large_boxes():
    rows=[dict(entity=i,**bounds(i*100,100,10)) for i in range(500)]
    rows += [dict(entity=501,min=dict(x=150,y=0),max=dict(x=150,y=500)),
             dict(entity=502,**bounds(-10000,-10000,9000))]
    idx=BoxIndex(rows)
    for x in range(-50,600,7):
        b=bounds(x,90,20)
        assert idx.blocked(b)==any(touches(b,r) for r in rows)
    assert idx.checks < len(rows)*93//10


def test_rotation_preserves_asymmetric_upgrade_offsets():
    r=request(radius=1,rotations=[90],reserved=dict(min=dict(x=-10,y=-10),max=dict(x=80,y=20)))
    p=search_sites(snapshot(),[r])
    reserve=p['sites'][0]['reserved']
    assert reserve['min']['x']==pytest.approx(480)
    assert reserve['max']['y']==pytest.approx(580)


def test_mcp_tool_offline_card_and_saved_plan(tmp_path,monkeypatch):
    import asyncio
    import json
    from tf3_mcp import server
    from tf3_mcp.development_planner import save_json
    async def forbidden(*args,**kwargs):
        raise AssertionError('offline search must not query game')
    monkeypatch.setattr(server,'_call',forbidden)
    path=save_json(snapshot(),tmp_path,'survey')
    result=asyncio.run(server.find_facility_sites(path,str(tmp_path),[request()]))
    assert not (result.meta or {}).get('planningCard')
    assert not list(tmp_path.glob('report-*'))
    data=result.structured_content
    assert data['metrics']['gameCalls']==0
    saved=json.loads(__import__('pathlib').Path(data['plan_path']).read_text(encoding='utf-8'))
    assert saved['searches'][0]['candidates'][0]['position']==dict(x=500,y=500)
