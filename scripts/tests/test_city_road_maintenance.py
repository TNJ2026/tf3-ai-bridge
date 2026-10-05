import json
from pathlib import Path
import pytest
from hub_joint_prototype import compile_spec
from planning_pipeline_core import prepare_template
from road_first_collection import stage_spec,source
from verify_joint_test import AUDIT
from lupa import LuaRuntime

def template():
    return json.loads((Path(__file__).resolve().parents[2]/'config/planning_templates/city.json').read_text('utf8'))

def test_maintenance_survives_planning_and_road_first_compilation():
    t=prepare_template(template(),'city');s=compile_spec(t)
    assert len(s['facilities'])==6
    assert 'road_maintenance' not in s['portBindings'] # Native resource has no vehicle entrance.
    roads=stage_spec(s,'roads');assert len(roads['roads'])==7
    mapping={str(n['name']):100+i for i,n in enumerate(roads['nodes'])}
    facilities=stage_spec(s,'facilities',mapping,[201])
    code=source(facilities,dict(x=0,y=0,rotation=90),'facilities')
    assert 'roadsideHeight' in code and 'Fresh frontage missing' in code
    LuaRuntime().execute('assert(load(...))',code)
    LuaRuntime().execute('assert(load(...))',AUDIT.replace('IDS','"{}"').replace('EXPECTED','"{}"'))

def test_maintenance_cannot_be_moved_to_frontage_end_or_wrong_snap():
    t=template();t['roads']=[r for r in t['roads']if r['node0']!=10]
    with pytest.raises(ValueError,match='continuing frontage'):compile_spec(t)
    t=template();f=next(f for f in t['facilities']if f['role']=='road_maintenance');f['roadSnap']['localPoint']['y']=-35
    with pytest.raises(ValueError,match='snap offset'):compile_spec(t)

def test_legacy_five_facility_template_remains_readable():
    t=template();t['facilities']=[f for f in t['facilities']if f['role']!='road_maintenance']
    assert len(compile_spec(prepare_template(t,'city'))['facilities'])==5


@pytest.mark.parametrize('defer',[False,True])
@pytest.mark.parametrize('failed',['serviceVerified','roadsideVerified',None])
def test_maintenance_gate_cannot_be_deferred(defer,failed):
    from verify_joint_test import acceptance
    from test_city_joint_collection import result
    r=result();r['airportRoadLinkVerified']=True;r['paths']['walking']['inbound']['verified']=True
    r['facilities']={'road_maintenance':123}
    r['maintenance']={'serviceVerified':True,'roadsideVerified':True}
    if failed:r['maintenance'][failed]=False
    assert acceptance(r,defer) is (failed is None)
    assert r['placementAccepted'] is (failed is None)
