import ast
import copy
from pathlib import Path
import pytest
from lupa import LuaRuntime
from verify_joint_test import acceptance
from test_city_joint_collection import result
from fullmap_hub_template import compile_template

@pytest.mark.parametrize('missing',['roads','coverage','paths','facilities'])
def test_empty_evidence_fails(missing):
    r=result();r[missing]=[] if missing=='roads' else {}
    assert not acceptance(r,True)
    assert not r['placementAccepted']
    assert r['acceptanceFailures']

def test_return_path_and_airport_access_cannot_be_deferred():
    for field in ('return','airport'):
        r=result()
        if field=='return':del r['paths']['truck']['outbound']
        else:r['airportRoadLinkVerified']=False
        assert not acceptance(r,True) and not r['placementAccepted']

def test_production_without_bus_is_valid_but_missing_planned_role_is_not():
    r=result()
    for role in ('bus','road_depot'):
        del r['facilities'][role];del r['paths'][role]
    del r['paths']['walking']
    r['facilities']['road_maintenance']={}
    r['maintenance']={'serviceVerified':True,'roadsideVerified':True}
    spec={'facilities':[{'role':k} for k in r['facilities']],'roads':[{}]}
    assert acceptance(r,spec=spec)
    del r['facilities']['road_maintenance']
    assert not acceptance(r,spec=spec)

def test_new_capture_requires_internal_road_selection():
    with pytest.raises(ValueError,match='road selection'):
        compile_template({'captureRequiresRoadSelection':True})

def test_capture_lua_compiles_and_rejects_ambiguous_members():
    source=(Path(__file__).resolve().parents[1]/'capture_hub_template.py').read_text('utf8')
    tree=ast.parse(source)
    code=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str) and 'local targets=' in n.value)
    for token,value in [('CAMERA','"{}"'),('MEMBERS','"{}"'),('PRODUCTION','false'),('LEGACY','false'),('INCLUDE_DEPOT','false'),('INCLUDE_MAINTENANCE','false'),('CAPTURE_RADIUS','450')]:code=code.replace(token,value)
    LuaRuntime().execute('assert(load(...))',code)
    start=code.index('local selected=');end=code.index('if false then\n local pads=',start)
    selection=code[start:end]
    lua=LuaRuntime()
    setup="""api={};B={commands={get_facility_config=function(id)return {entity=id.entity}end}};targets={warehouse='warehouse'};out={facilities={}};nearby={{id=1,resource='warehouse',distance=1},{id=2,resource='warehouse',distance=2}};"""
    with pytest.raises(Exception,match='Ambiguous collection role'):
        lua.execute(setup+'members={};'+selection)
    lua.execute(setup+'members={warehouse=2};'+selection)
    assert lua.eval('out.facilities[1].entity')==2
