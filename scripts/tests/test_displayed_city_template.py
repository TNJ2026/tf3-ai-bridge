"""Current captured layout stays portable and uses the requested road profile."""
import copy,json,math
from pathlib import Path
import pytest
from lupa import LuaRuntime
from planning_pipeline_core import prepare_template
from hub_joint_prototype import compile_spec
from build_joint_collection import code_for
from verify_joint_test import expected_roadside_offsets
from road_snap_layout import validate_road_snaps


def template():
    return json.loads((Path(__file__).resolve().parents[2]/'config/planning_templates/city.json').read_text('utf8'))


def test_displayed_configuration_and_portable_native_proposals():
    t=template();s=compile_spec(prepare_template(t,'city'))
    assert t['placementMode']=='joint' and s['hydrateModules']
    roles={f['role']:f for f in s['facilities']}
    modules=lambda role:[v['name'] for v in roles[role]['params']['modules'].values()]
    assert sum('passenger_platform' in v for v in modules('bus'))==6
    assert sum('cargo_platform' in v for v in modules('truck'))==12
    assert len(modules('warehouse'))==6
    assert len(s['roads'])==6 and len(s['nodes'])==7
    assert all(r['roadTemplate']=='country/country_new_medium' for r in s['roads'])
    assert all(n['entity']<0 for n in s['nodes'])
    assert all(r['entity']<0 and r['node0']<0 and r['node1']<0 for r in s['roads'])
    assert not t['nativeJointPreviewPassed'] and not t['constructionAuthorized']
    assert '<max depth>' not in json.dumps(t)
    for build in (False,True):
        code=code_for(s,dict(x=100,y=200,rotation=73),build)
        LuaRuntime().execute('assert(load(...))',code)
        assert code.count('api.cmd.sendCommand(')==int(build)


def test_medium_road_keeps_observed_maintenance_offset_in_readback():
    t=template();f=next(f for f in t['facilities'] if f['role']=='road_maintenance')
    assert f['roadSnap']['roadsideOffsetM']==pytest.approx(12,abs=.001)
    validate_road_snaps(t)
    positions={'road_maintenance':dict(x=123,y=456)};before=copy.deepcopy(positions)
    expected=expected_roadside_offsets(positions,compile_spec(t))
    assert positions==before
    assert expected['road_maintenance']['roadsideOffsetM']==f['roadSnap']['roadsideOffsetM']
    del f['roadSnap']['requiredNativeVerification']
    with pytest.raises(ValueError,match='native verification'):validate_road_snaps(t)


def test_medium_profile_does_not_accept_old_seven_metre_snap():
    old=json.loads((Path(__file__).with_name('fixtures')/'city_road_first_v3.json').read_text('utf8'))
    for r in old['roads']:r['roadTemplate']='country/country_new_medium'
    with pytest.raises(ValueError,match='clearance'):validate_road_snaps(old)


def test_native_module_metadata_is_rehydrated_from_resource():
    s=compile_spec(template());code=code_for(s,dict(x=0,y=0,rotation=0))
    block=code[code.index('local modules={}'):code.index(" if spec.collectionKind=='fish_port' then f.params.year")]
    setup='''
local spec={collectionKind='aviation',hydrateModules=true}
local f={params={modules={['42']={name='actual.module',variant=3}}}}
api={res={moduleRep={find=function(name)assert(name=='actual.module');return 7 end,
get=function(id)assert(id==7);return {metadata={real=true},updateScript={fileName='real.lua',params={}}}end}}}
'''
    result=LuaRuntime().execute(setup+block+'return f.params.modules[42]')
    assert result['variant']==3 and result['metadata']['real']
    assert result['updateScript']['fileName']=='real.lua'
