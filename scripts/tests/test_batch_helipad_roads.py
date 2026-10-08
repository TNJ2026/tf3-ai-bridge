import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from batch_helipad_roads import routes,transform

@pytest.mark.parametrize('node',[
    {'id':3,'x':100,'y':-100}, {'id':4,'x':-100,'y':20},
    {'id':5,'x':100,'y':80}])
def test_frontage_outside_facility_and_no_forced_collisions(node):
    site={'x':0,'y':0,'ax':1,'ay':0,'bx':0,'by':1}
    for length,args in routes(site,node):
        assert length>0 and args['end']['y']==-35
        assert args['snap_radius']==0 and args['allow_collisions'] is False
        assert args['start']=={'node':node['id']}
        assert all(abs(p['x'])>=30 for p in args['via'])

def test_frontage_rotates_with_facility_transform():
    site={'x':10,'y':20,'ax':0,'ay':1,'bx':-1,'by':0}
    assert transform(site,0,-35)=={'x':45,'y':20}

def test_dead_end_can_extend_existing_direction_before_turning():
    site={'x':0,'y':0,'ax':1,'ay':0,'bx':0,'by':1}
    node={'id':9,'x':100,'y':60,'edges':[8],'ux':1,'uy':0}
    variants=list(routes(site,node))
    assert any(args['via'][0]=={'x':140,'y':60} for _,args in variants)
