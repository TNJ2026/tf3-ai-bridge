import asyncio,copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from lupa import LuaRuntime,LuaError
from fish_port_collection import DEFAULT as AIR_DEFAULT,prepare,attempt,clear,execute
from hub_joint_prototype import compile_spec,probe
ROOT=Path(__file__).resolve().parents[2]
DEFAULT=ROOT/'config/planning_templates/fish_port.json'

def test_air_port_has_two_pads_and_no_truck_or_roads():
    s=prepare(AIR_DEFAULT)
    assert {f['role'] for f in s['facilities']}=={'harbor','water_maintenance','water_depot','warehouse','helipad','helipad2'}
    assert s['transferMode']=='helicopter' and not s['bindGeneratedPorts']
    assert s['nodes']==s['roads']==[] and s['portBindings']=={}
    code=attempt(s,{'x':0,'y':0,'rotation':0})
    LuaRuntime().execute('assert(load(...))',code)
    assert 'sendCommand' not in code

def test_air_port_rejects_truck_roads():
    t=json.loads(AIR_DEFAULT.read_text('utf8'))
    t['roads']=json.loads(DEFAULT.read_text('utf8'))['roads']
    with pytest.raises(ValueError,match='truck roads'):compile_spec(t)

def test_template_is_four_roles_and_not_an_extra_shipyard():
    s=prepare(DEFAULT)
    assert {f['role']for f in s['facilities']}=={'harbor','water_maintenance','warehouse','truck'}
    assert all('water_depot.con'not in f['resource']for f in s['facilities'])
    assert s['cargoPolicy']=={'allowed':['fish'],'oil':'helicopter'}
    assert set(s['portBindings'])=={'truck'} and s['bindGeneratedPorts']
    ids=[n['entity']for n in s['nodes']]+[r['entity']for r in s['roads']]
    assert len(ids)==len(set(ids)) and all(x< -len(s['facilities'])for x in ids)

def test_wrong_maintenance_resource_and_oil_policy_rejected():
    t=json.loads(DEFAULT.read_text('utf8'));t['cargoPolicy']['allowed'].append('crude')
    with pytest.raises(ValueError,match='Fish-only'):compile_spec(t)
    t=json.loads(DEFAULT.read_text('utf8'));next(f for f in t['facilities']if f['role']=='water_maintenance')['resource']='::/depots/water/water_depot.con'
    with pytest.raises(ValueError,match='resource'):compile_spec(t)

def test_water_roles_cannot_use_terrain_height():
    t=json.loads(DEFAULT.read_text('utf8'));next(f for f in t['facilities']if f['role']=='harbor')['heightPolicy']='terrain'
    with pytest.raises(ValueError,match='height'):compile_spec(t)

def test_generated_lua_parses_and_cannot_submit():
    s=prepare(DEFAULT);code=probe(s)
    lua=LuaRuntime();lua.execute('assert(load(...))',code)
    assert 'sendCommand('not in code
    assert 'waterLevel+2'in code
    assert 'local isolatedTestConfirmed=false'in code
    assert 'f.heightPolicy'in code and 'api.res.moduleRep.get(rid)'in code
    assert "templateName='::/infrastructure/street/'" in code
    assert 'tpl.streetStyle' in code
    assert 'waterSurfaceContacts' in code
    lua.execute('assert(load(...))',attempt(s,{'x':1,'y':2,'rotation':45}))
    generated=attempt(s,{'x':1,'y':2,'rotation':45})
    assert 'sendCommand' not in generated
    assert 'Vehicle preview path failed' in generated and 'previewPaths=paths' in generated
    audit=(ROOT/'scripts/fish_port_audit.lua').read_text('utf8')
    lua.execute('assert(load(...))',audit.replace('SPEC_JSON','"s"').replace('ORIGIN_JSON','"o"').replace('ADDED_JSON','"a"'))

@pytest.mark.parametrize('kind',['critical','infos','warnings','messages','collisions'])
def test_preview_rejection_is_not_build_permission(kind):
    r={'errorState':{'critical':False,'infos':[],'messages':[],'warnings':[]},'collisions':[]}
    assert clear(r)
    if kind=='critical':r['errorState'][kind]=True
    elif kind=='collisions':r[kind]=[-1]
    else:r['errorState'][kind]=['placement rejected']
    assert not clear(r)
    assert not clear({})

def test_shore_check_accepts_straddling_coast_but_rejects_inland_or_open_water():
    lua=LuaRuntime()
    lua.execute("""
    angle=0;spec={facilities={{role='water_maintenance',localPosition={x=0,y=0},relativeRotation=0,heightPolicy='water_surface'}}}
    function point(p)return p end
    api={type={Vec2f={new=function(x,y)return{x=x,y=y}end}},engine={terrain={isOnWater=function(p)return p.y<5 end}}}
    """)
    lua.execute((ROOT/'scripts/fish_port_shore_check.lua').read_text('utf8'))
    for water in ('true','false'):
        lua.execute('api.engine.terrain.isOnWater=function(p)return '+water+' end')
        with pytest.raises(LuaError,match='shoreline mismatch'):
            lua.execute((ROOT/'scripts/fish_port_shore_check.lua').read_text('utf8'))

def test_prepare_never_connects_to_bridge(tmp_path,monkeypatch):
    import fish_port_collection
    monkeypatch.setattr(fish_port_collection,'Batch',lambda *a:pytest.fail('No game calls permitted'))
    a=SimpleNamespace(action='prepare',output=tmp_path,template=DEFAULT)
    asyncio.run(execute(a))
    assert (tmp_path/'joint_spec.json').exists()
    assert not json.loads((tmp_path/'joint_spec.json').read_text('utf8'))['commitEnabled']

def test_unauthorized_build_is_blocked_before_bridge(tmp_path,monkeypatch):
    import fish_port_collection
    monkeypatch.setattr(fish_port_collection,'Batch',lambda *a:pytest.fail('No game calls permitted'))
    a=SimpleNamespace(action='build',output=tmp_path,plan=Path('unused'),isolated_test_save=False,authorize_build=False)
    with pytest.raises(ValueError,match='build authorization'):asyncio.run(execute(a))

def test_preview_needs_no_map_pause_or_isolated_save(tmp_path,monkeypatch):
    import fish_port_collection
    from contextlib import nullcontext
    class FakeBatch:
        b=SimpleNamespace(dir=tmp_path)
        async def session(self):pytest.fail('Preview must not enforce plan map identity')
        async def call(self,command,args):
            assert command=='get_game_state'
            return {'speedup':4,'player':9,'world':77,'gameTime':10,'tickCount':20}
        async def save(self,phase):pass
        async def eval(self,code):
            assert 'sendCommand' not in code and 'isolatedTestConfirmed' not in code
            return {'errorState':{'critical':False,'infos':[],'messages':[],'warnings':[]},'collisions':[],'connectionsVerified':True}
    monkeypatch.setattr(fish_port_collection,'Batch',lambda *a:FakeBatch())
    monkeypatch.setattr(fish_port_collection,'batch_lock',lambda *a:nullcontext())
    a=SimpleNamespace(action='preview',output=tmp_path,plan=Path('unused'),isolated_test_save=False,x=0,y=0,rotation=0,template=AIR_DEFAULT)
    asyncio.run(execute(a))
    assert json.loads((tmp_path/'fish_port_receipt.json').read_text('utf8'))['previewPassed']
