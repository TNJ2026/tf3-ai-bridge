"""Real Lua adapter with mocked native constructor/readback; no live mutations."""
import json
from pathlib import Path
import pytest
from test_e2e import MOCK_API, MOCK_CONSTRUCTION, SCRIPT, lupa_mod


@pytest.fixture
def terrain_game():
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute(MOCK_CONSTRUCTION.read_text('utf8'))
    lua.execute('''
NOW=100;os.clock=function()return NOW end
REV=1;SENDS=0;HEIGHTS={};BLOCKERS={}
local CT=api.type.ComponentType;CT.TERRAIN=201;CT.MODEL_INSTANCE_LIST=202
components[1][CT.TERRAIN]={waterLevel=0}
api.engine.terrain.getBaseResolution=function()return {x=4,y=4,z=.05}end
api.engine.terrain.getBoundingBox=function()return {min={x=-1000,y=-1000},max={x=1000,y=1000}}end
api.engine.terrain.getBaseHeightAt=function(p)return HEIGHTS[p.x..':'..p.y] or 10 end
api.engine.terrain.getHeightAt=function(p)return api.engine.terrain.getBaseHeightAt(p)+(ALIGN or 0)end
api.engine.terrain.isOnWater=function()return WET==true end
api.engine.terrain.getTerrainEntityRevisions=function()return {[1]={num={REV,0,0}}}end
api.engine.util.octree.findEntitiesInCircle=function(_,_,ct)return ct==CT.BASE_EDGE and BLOCKERS or {}end
api.type.GridVec2f={new=function(x,y,w,h,value)
 assert(value.x==value.y);return {x0=x,y0=y,width=w,height=h,value=value.x}
end}
api.type.Proposal={new=function()return {terrain={}}end}
api.cmd.makeWorldBuildProposalCmd=function(p,ctx,ignore,player)
 assert(ignore==false and player==true);return p
end
api.cmd.sendCommand=function(p,cb)
 SENDS=SENDS+1
 if THROW or FAIL_AT==SENDS then error('unknown outcome')end
 if DELAY then return end
 local g=p.terrain.baseHeightMod
 for x=g.x0,g.x0+g.width-1 do for y=g.y0,g.y0+g.height-1 do
  HEIGHTS[(x*4)..':'..(y*4)]=g.value+(BAD_READBACK or 0)
 end end
 REV=REV+1;cb({},true)
end
''')
    script = lua.execute(SCRIPT.read_text('utf8'))

    def call(name, **args):
        result = script['_internal']['commands'][name](lua.table_from(args, recursive=True))
        return json.loads(script['_internal']['json']['encode'](result))
    return lua, call


def preview(call, **overrides):
    args = dict(bounds=dict(min=dict(x=101,y=101),max=dict(x=107,y=107)),target_height=10.2)
    return call('preview_flatten_terrain', **dict(args, **overrides))


def test_uniform_rectangle_one_submit_and_guard_readback(terrain_game):
    lua, call = terrain_game
    p = preview(call)
    assert p['validation'] == 'structural_only' and not p['native_preview']
    assert p['flattened_bounds'] == dict(min=dict(x=100,y=100),max=dict(x=108,y=108))
    assert lua.globals().SENDS == 0
    r = call('commit_flatten_terrain', preview_token=p['preview_token'], backup_save='test_before')
    assert r['verified'] and r['mismatched_vertices'] == 0
    assert lua.globals().SENDS == 1
    assert call('get_terrain_operation',operation_id=r['operation_id'])['verified']
    with pytest.raises(Exception,match='consumed'):
        call('commit_flatten_terrain',preview_token=p['preview_token'],backup_save='test_before')


@pytest.mark.parametrize('change,reason', [('WET=true','water_or_unknown'),('ALIGN=1','surface_base_difference_requires_review'),('BLOCKERS={99}','existing_entities')])
def test_obstacles_and_water_fail_closed(terrain_game,change,reason):
    lua,call=terrain_game;lua.execute(change);p=preview(call)
    assert p['blocked'] and any(reason in b for b in p['blockers'])
    assert 'preview_token' not in p and lua.globals().SENDS==0


def test_steep_boundary_is_not_claimed_as_smoothing(terrain_game):
    _,call=terrain_game;p=preview(call,target_height=12)
    assert 'edge_grade_requires_separate_transition_design' in p['blockers']
    assert p['transition_supported'] and p['transition_width']==0 and 'preview_token' not in p


@pytest.mark.parametrize('change,error', [('REV=2','terrain changed'),('NOW=161','expired'),('components[1][4].gameTime=0','session changed'),('BLOCKERS={99}','blocked')])
def test_stale_token_never_sends(terrain_game,change,error):
    lua,call=terrain_game;p=preview(call);lua.execute(change)
    with pytest.raises(Exception,match=error):
        call('commit_flatten_terrain',preview_token=p['preview_token'],backup_save='test_before')
    assert lua.globals().SENDS==0


@pytest.mark.parametrize('flag',['THROW','DELAY','BAD_READBACK'])
def test_unknown_outcome_blocks_followup(terrain_game,flag):
    lua,call=terrain_game;p=preview(call);lua.globals()[flag]=.1 if flag=='BAD_READBACK' else True
    r=call('commit_flatten_terrain',preview_token=p['preview_token'],backup_save='test_before')
    assert r['status']=='needs_reconciliation' and not r['verified']
    second=preview(call,target_height=10.1)
    with pytest.raises(Exception,match='reconciliation'):
        call('commit_flatten_terrain',preview_token=second['preview_token'],backup_save='test_before')
    assert lua.globals().SENDS==1


def test_fragment_matches_embedded_bridge():
    fragment=Path(__file__).resolve().parents[2]/'scripts/terrain_flatten_fragment.lua'
    assert fragment.read_text('utf8').strip() in SCRIPT.read_text('utf8')


def test_commit_wrapper_saves_stable_backup_before_dispatch(tmp_path,monkeypatch):
    import asyncio
    import re
    from types import SimpleNamespace
    from tf3_mcp import server
    bridge_dir=tmp_path/'tf3_mcp';bridge_dir.mkdir();(tmp_path/'save').mkdir()
    monkeypatch.setattr(server,'bridge',lambda:SimpleNamespace(dir=bridge_dir))
    calls=[]
    async def call(command,**kwargs):
        calls.append((command,kwargs))
        if command=='eval':
            slot=re.search(r'app.saveGame\("([^"]+)"',kwargs['code'])[1]
            (tmp_path/'save'/(slot+'.sav')).write_bytes(b'new save')
            return {'requested':True}
        assert len(calls)==2 and calls[0][0]=='eval'
        return {'verified':True}
    monkeypatch.setattr(server,'_call',call)
    async def sleep(_):pass
    monkeypatch.setattr(asyncio,'sleep',sleep)
    import time
    clock=iter(range(100,200));monkeypatch.setattr(time,'monotonic',lambda:next(clock))
    r=asyncio.run(server.commit_flatten_terrain('test-token'))
    assert r['verified'] and Path(r['backup_path']).exists()
    assert calls[1][1]['backup_save']==r['backup_save']
    assert calls[1][1]['preview_token']=='test-token'


def test_missing_backup_never_dispatches(tmp_path,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from tf3_mcp import server
    monkeypatch.setattr(server,'bridge',lambda:SimpleNamespace(dir=tmp_path/'tf3_mcp'))
    calls=[]
    async def call(command,**kwargs):calls.append(command);return {'requested':True}
    async def sleep(_):pass
    monkeypatch.setattr(server,'_call',call);monkeypatch.setattr(asyncio,'sleep',sleep)
    with pytest.raises(Exception,match='Backup write not confirmed'):
        asyncio.run(server.commit_flatten_terrain('test-token'))
    assert calls==['eval']


def test_terrain_timeout_invalidates_map_cache(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from tf3_mcp import server
    from tf3_mcp.bridge import BridgeError
    async def call(*args,**kwargs):raise BridgeError('timeout')
    monkeypatch.setattr(server,'bridge',lambda:SimpleNamespace(call=call))
    invalidations=[]
    monkeypatch.setattr(server._map_cache,'invalidate',lambda:invalidations.append(True))
    with pytest.raises(Exception,match='timeout'):
        asyncio.run(server._call('commit_flatten_terrain',preview_token='test'))
    assert invalidations==[True]


def test_engine_events_preserve_tokens_and_operations_across_module_recreation(terrain_game):
    lua, _ = terrain_game
    state = lua.execute("local value={};return {get=function()return value end,set=function(_,v)value=v end}")
    serial = 0
    def event(name, epoch="session-a", **args):
        nonlocal serial
        serial += 1
        script = lua.execute(SCRIPT.read_text("utf8"))
        payload = json.dumps(dict(id=str(serial),cmd=name,args=args,terrainEpoch=epoch))
        script["handleEvent"](None,state,None,"tf3_mcp","tf3_mcp_request",payload)
        responses = state["get"](state)["responses"]
        result = json.loads(responses[len(responses)]["text"])
        # Game state is serialized plain data, not a module's table references.
        encoded = script["_internal"]["json"]["encode"](state["get"](state))
        state["set"](state,script["_internal"]["json"]["decode"](encoded))
        return result
    p = event("preview_flatten_terrain",bounds=dict(min=dict(x=101,y=101),max=dict(x=107,y=107)),target_height=10.2)["result"]
    r = event("commit_flatten_terrain",preview_token=p["preview_token"],backup_save="test_before")
    assert r["ok"] and r["result"]["verified"]
    assert event("get_terrain_operation",operation_id=p["preview_token"])["result"]["verified"]
    assert not event("commit_flatten_terrain",preview_token=p["preview_token"],backup_save="test_before")["ok"]
    p2 = event("preview_flatten_terrain",bounds=dict(min=dict(x=101,y=101),max=dict(x=107,y=107)),target_height=10.1)["result"]
    assert not event("commit_flatten_terrain",epoch="reloaded",preview_token=p2["preview_token"],backup_save="test_before")["ok"]
    assert lua.globals().SENDS == 1


def test_smooth_transition_blends_and_preserves_guard(terrain_game):
    lua,call=terrain_game
    p=preview(call,target_height=10.8,transition_width=16)
    assert not p['blocked'] and p['summary']['native_steps']>1
    r=call('commit_flatten_terrain',preview_token=p['preview_token'],backup_save='test_before')
    assert r['verified'] and r['completed_steps']==r['total_steps']
    points=r['receipt']['expected_points']
    assert any(10<x['expected']<10.8 for x in points if x['transition'])
    assert all(x['expected']==x['before'] for x in points if not x['transition'] and not x['inside'])
    assert all(x['expected']==10.8 for x in points if x['inside'])


def test_smooth_partial_failure_stops_and_blocks_new_operation(terrain_game):
    lua,call=terrain_game
    p=preview(call,target_height=10.8,transition_width=16)
    lua.globals().FAIL_AT=2
    r=call('commit_flatten_terrain',preview_token=p['preview_token'],backup_save='test_before')
    assert not r['verified'] and r['completed_steps']==1 and lua.globals().SENDS==2
    p2=preview(call,target_height=10.7,transition_width=16)
    with pytest.raises(Exception,match='reconciliation'):
        call('commit_flatten_terrain',preview_token=p2['preview_token'],backup_save='test_before')
    assert lua.globals().SENDS==2


def test_smooth_step_budget_and_grade_fail_before_submission(terrain_game):
    lua,call=terrain_game
    p=preview(call,target_height=11,transition_width=64)
    assert p['blocked'] and 'native_step_budget_exceeded_reduce_area_or_transition' in p['blockers']
    p=preview(call,target_height=14,transition_width=8)
    assert p['blocked'] and 'edge_grade_requires_separate_transition_design' in p['blockers']
    assert lua.globals().SENDS==0


def test_preview_wrapper_forwards_transition_width(monkeypatch):
    import asyncio
    from tf3_mcp import server
    async def call(command,**args):
        assert command=='preview_flatten_terrain' and args['transition_width']==24
        return {'preview':True}
    monkeypatch.setattr(server,'_call',call)
    assert asyncio.run(server.preview_flatten_terrain({},10,transition_width=24))['preview']
