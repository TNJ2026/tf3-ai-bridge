import math
import pytest
from tf3_mcp.frontage_planning import (curve, project, candidates, road_half_width,
    external_port, footprint_contains, safe_preview)


def edge():
    return dict(position0=dict(x=0,y=0,z=2),position1=dict(x=100,y=0,z=2),
        tangent0=dict(x=100,y=0,z=0),tangent1=dict(x=100,y=0,z=0),
        laneConfigs=[dict(width=5,offset=.5),dict(width=5,offset=-.5)])


def test_projection_and_true_curve_tangent():
    e=edge();e['tangent0']['y']=80;e['tangent1']['y']=-60
    point,tangent=curve(e,.37)
    assert project(e,point['x'],point['y'])==pytest.approx(.37,abs=1e-6)
    p1,_=curve(e,.37001);p0,_=curve(e,.36999)
    for k in 'xyz':assert tangent[k]==pytest.approx((p1[k]-p0[k])/.00002,abs=1e-5)


@pytest.mark.parametrize('side',['left','right'])
@pytest.mark.parametrize('param',[.2,.43,.79])
def test_road_native_port_matches_exact_point_on_both_sides(side,param):
    e=edge();e['tangent0']['y']=30
    profile=dict(kind='tram_depot',port=dict(x=-1.64813,y=-37.4153,z=.4))
    result=candidates(e,profile,param=param,side=side,search=False)[0]
    a=math.radians(result['rotation']);port=profile['port'];target,_=curve(e,param)
    assert result['x']+math.cos(a)*port['x']-math.sin(a)*port['y']==pytest.approx(target['x'])
    assert result['y']+math.sin(a)*port['x']+math.cos(a)*port['y']==pytest.approx(target['y'])
    assert result['z']+port['z']==pytest.approx(target['z'])


def test_air_boundary_uses_width_including_offsets_not_snap_point():
    e=edge();profile=dict(kind='helipad',bounds=[-18,18,-20,18])
    narrow=candidates(e,profile,param=.5,search=False)[0]
    e['laneConfigs']=[dict(width=4,offset=0),dict(width=5,offset=0),dict(width=5,offset=0),dict(width=4,offset=0)]
    wide=candidates(e,profile,param=.5,search=False)[0]
    assert narrow['y']==25.5 and wide['y']==29
    assert road_half_width(e['laneConfigs'])==9


def test_port_local_coordinates_undo_rotation_and_translation():
    con=dict(transf=dict(columns=[dict(x=0,y=1),dict(x=-1,y=0),{},dict(x=100,y=200,z=10)]),frozenNodes=[2])
    edges=[dict(node0=1,node1=2,position0=dict(x=135,y=198,z=10.5),position1=dict(x=100,y=200,z=10))]
    assert external_port(con,edges)==dict(x=-2,y=-35,z=.5)
    with pytest.raises(ValueError,match='Unique'):external_port(con,[])


def test_bad_inputs_and_no_implicit_endpoint_snapping():
    profile=dict(kind='road_depot',port=dict(x=0,y=-35,z=0))
    assert candidates(edge(),profile,param=0,search=False)==[]
    for value in (float('nan'),True,-1,1.1):
        with pytest.raises(ValueError):candidates(edge(),profile,param=value)
    with pytest.raises(ValueError):road_half_width([])


def test_bounded_alternatives_do_not_duplicate_candidates():
    profile=dict(kind='road_depot',port=dict(x=0,y=-35,z=0))
    result=candidates(edge(),profile,param=.5)
    assert len(result)==10
    assert len({(c['param'],c['side']) for c in result})==10


def test_oriented_footprint_and_cash_preview_guards():
    assert footprint_contains(dict(x=10,y=10,rotation=90),[-2,2,-5,5],dict(x=14,y=10))
    assert not footprint_contains(dict(x=10,y=10,rotation=90),[-2,2,-5,5],dict(x=10,y=14))
    good=dict(ok=True,preview_token='abc',cost=42)
    assert safe_preview(good)
    for name in ('critical','warnings','collisions','blocked','unexpected_removals'):
        assert not safe_preview(dict(good,**{name:True}))
    assert not safe_preview(dict(good,cost=float('nan')))
