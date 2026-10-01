import copy
import pytest
from tf3_mcp.route_planner import plan_routes, Terrain, Obstacles


def snapshot():
    return dict(grid=dict(x=-2000,y=-2000,nx=81,ny=61,spacing=100,
                         heights=[2.]*(81*61),water=[False]*(81*61)),
                stations=[dict(ports=[dict(node=1,position=dict(x=0,y=0,z=2),direction=dict(x=1,y=0))]),
                          dict(ports=[dict(node=2,position=dict(x=4000,y=0,z=2),direction=dict(x=-1,y=0))])],
                obstacles=[],state={'tickCount':42})


def test_clear_route_and_grade():
    s=snapshot();before=copy.deepcopy(s);r=plan_routes(s)
    assert r['candidates'] and r['buildable'] is None
    p=r['candidates'][0]
    assert p['length']==pytest.approx(4000)
    assert p['path'][0]['x']==0 and p['path'][-1]['x']==4000
    assert p['maxGrade']<=.025+1e-9
    assert s==before and p['requiresNativePreview']


def test_model_only_depot_causes_detour():
    s=snapshot();s['obstacles']=[dict(entity=83407,kind='MODEL_INSTANCE_LIST',
        min=dict(x=1850,y=-150,z=0),max=dict(x=2150,y=150,z=30))]
    r=plan_routes(s)
    assert r['candidates'] and r['stats']['rejected']['obstacle']>0
    for c in r['candidates']:
        assert c['length']>4000
        assert not any(list(Obstacles(s['obstacles']).conflicts(p['x'],p['y'],p['z'])) for p in c['path'])


def test_blocked_exit_reports_no_candidate():
    s=snapshot();s['obstacles']=[dict(entity=3,kind='CONSTRUCTION',
        min=dict(x=-100,y=-100,z=0),max=dict(x=100,y=100,z=30))]
    assert plan_routes(s)['candidates']==[]


def test_road_clearance_and_bucket_boundary():
    o=Obstacles([dict(entity=4,kind='BASE_EDGE',min=dict(x=100,y=100,z=0),max=dict(x=105,y=105,z=2))])
    assert list(o.conflicts(99,99,3))==[4]
    assert list(o.conflicts(99,99,15))==[]
    assert list(o.conflicts(99,99,-15))==[]


def test_water_and_interpolation():
    g=dict(x=0,y=0,nx=2,ny=2,spacing=100,heights=[0,10,20,30],water=[False,True,False,False])
    assert Terrain(g).sample(50,50)==(15,True)
    assert Terrain(g).sample(100,100)[0]==30
    with pytest.raises(ValueError):Terrain(g).sample(-1,0)


def test_invalid_limits():
    with pytest.raises(ValueError):plan_routes(snapshot(),max_candidates=0)


def test_free_ports_empty():
    s=snapshot();s['stations'][0]['ports']=[]
    assert plan_routes(s)['candidates']==[]
