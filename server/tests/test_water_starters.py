"""Exercise actual water starter handlers without changing a running game."""
import asyncio
import json
import pytest
from test_facilities import game as facility_game
from tf3_mcp.ui_log import validate_build_arguments


@pytest.fixture
def water_game(facility_game):
    lua, call = facility_game
    lua.execute('''
local resources={
 [60]="::/stations/water/harbor_modular",[61]="::/depots/water/water_depot",[62]="::/depots/water/water_maint_station"}
local cf=api.res.constructionRep.find;local cg=api.res.constructionRep.get
api.res.constructionRep.find=function(n)for id,path in pairs(resources)do if n==path..".con"then return id end end;return cf(n)end
api.res.constructionRep.get=function(id)if resources[id]then return {metadata={revision=REVISION or 1},params={},
 availability={yearFrom=FUTURE and 9999 or 1850,yearTo=0},
 updateScript={fileName=BAD_SCRIPT and "bad" or resources[id]..".script@updateFn",params={}},
 createTemplateScript={fileName=resources[id]..".script@createTemplateFn",params={}}}end;return cg(id)end
local names={[70]={"pedestrian_entrance","pedestrian_entrance"},[71]={"passenger_dock_100_50","water_module_100_50"},
 [72]={"passenger_dock_100_25","water_module_100_25"},[73]={"medium_pier","water_pier_100_12"},
 [74]={"passenger_dock_25_25","water_module_25_25"},[75]={"passenger_dock_50_12","water_module_50_12"},
 [76]={"small_pier","water_pier_50_12"}}
local mf=api.res.moduleRep.find;local mg=api.res.moduleRep.get
api.res.moduleRep.find=function(n)for id,row in pairs(names)do if n=="::/stations/water/"..row[1]..".module"then return id end end;return mf(n)end
api.res.moduleRep.get=function(id)if names[id]then return {type=BAD_MODULE and "wrong" or names[id][2],
 availability={yearFrom=1850,yearTo=0},metadata={revision=REVISION or 1},updateScript={fileName="native@update",params={}}}end;return mg(id)end
ug_require=function(n)
 assert(n=="::/game_mechanics/company/company_util.tl")
 return {getConstructionDisableCacheData=function()return {}end,
 getConstructionDisableReason=function()return LOCKED and {reason="permit"} or {numRemaining=1}end}
end
api.engine.terrain.isValidCoordinate=function()return not OUTSIDE end
''')
    return lua, call


def preview(call, kind='harbor', **extra):
    return call('build_water_facility',kind=kind,x=700,y=740,z=0,rotation=90,**extra)


@pytest.mark.parametrize('kind', ['harbor','shipyard','maintenance'])
def test_preview_single_commit_config_only_and_duplicate_guard(water_game, kind):
    lua,call=water_game
    p=preview(call,kind)
    modules=p['parameters']['modules']
    if kind=='harbor':
        assert set(map(int,modules))=={100010150,99010150,99010053,100009804,100009736}
        assert modules['100009736']['name'].endswith('/small_pier.module')
        assert p['harborSize']=='small' and p['waterHarborLayoutVersion']==1
    else:
        assert modules in ({},[])
    assert not p['serviceVerified'] and not p['navigationVerified']
    assert lua.globals().SUBMISSIONS is None
    r=call('commit_facility',preview_token=p['preview_token'])
    assert r['built'] and r['configurationVerified']
    assert not r['serviceVerified'] and not r['navigationVerified']
    with pytest.raises(Exception,match='consumed'):call('commit_facility',preview_token=p['preview_token'])
    with pytest.raises(Exception,match='already exists'):preview(call,kind)
    assert lua.globals().SUBMISSIONS==1


def test_explicit_large_preserves_native_layout(water_game):
    lua,call=water_game
    p=preview(call,harbor_size='large')
    assert set(map(int,p['parameters']['modules']))=={101010150,98010150,100010150,99010150,100009722,100009612,100009444}
    assert p['harborSize']=='large'
    assert call('commit_facility',preview_token=p['preview_token'])['built']


@pytest.mark.parametrize('kind,size',[('harbor','medium'),('harbor',True),('shipyard','small'),('maintenance','large')])
def test_invalid_size_cannot_preview_or_submit(water_game,kind,size):
    lua,call=water_game
    with pytest.raises(Exception):preview(call,kind,harbor_size=size)
    assert lua.globals().PREVIEWS is None and lua.globals().SUBMISSIONS is None
    with pytest.raises(ValueError):validate_build_arguments('build_water_facility',dict(kind=kind,x=1,y=2,z=2,harbor_size=size))


def test_old_water_receiver_never_silently_builds_large():
    from tf3_mcp.headless_client import HeadlessClient
    from unittest.mock import AsyncMock,Mock
    requests=Mock();client=HeadlessClient(requests)
    client.status=AsyncMock(return_value={'receiver':{'session':'s','waterFacilityVersion':1},'pending':None})
    with pytest.raises(ValueError,match='small/large'):
        asyncio.run(client.call('build_water_facility',dict(kind='harbor',x=1,y=2,z=2)))
    requests.send.assert_not_called()


@pytest.mark.parametrize('flag,error',[('FUTURE','unavailable'),('BAD_SCRIPT','unrecognized'),('BAD_MODULE','module'),('LOCKED','locked'),('OUTSIDE','outside')])
def test_rejection_before_preview_or_submission(water_game,flag,error):
    lua,call=water_game;lua.globals()[flag]=True
    with pytest.raises(Exception,match=error):preview(call)
    assert lua.globals().PREVIEWS is None and lua.globals().SUBMISSIONS is None


def test_stale_resource_and_collision_consume_token(water_game):
    lua,call=water_game;p=preview(call);lua.execute('REVISION=2')
    with pytest.raises(Exception,match='changed'):call('commit_facility',preview_token=p['preview_token'])
    p=preview(call);lua.execute('COLLISIONS={{entity=999999}}')
    assert call('commit_facility',preview_token=p['preview_token'])['blocked']
    with pytest.raises(Exception,match='consumed'):call('commit_facility',preview_token=p['preview_token'])
    assert lua.globals().SUBMISSIONS is None


def test_mcp_and_schema(monkeypatch):
    from tf3_mcp import server
    calls=[]
    async def fake(cmd,**args):calls.append((cmd,args));return {'preview':True}
    monkeypatch.setattr(server,'_call',fake)
    asyncio.run(server.build_water_facility('harbor',1,2,0))
    assert calls[0][0]=='build_water_facility' and calls[0][1]['preview']
    valid=dict(kind='harbor',x=1,y=2,z=0)
    validate_build_arguments('build_water_facility',valid)
    for invalid in [dict(valid,kind='fish'),dict(valid,ignoreErrors=True),dict(valid,z=float('inf')),{k:v for k,v in valid.items() if k!='kind'}]:
        with pytest.raises(ValueError):validate_build_arguments('build_water_facility',invalid)


def test_old_receiver_rejected_before_dispatch():
    from tf3_mcp.headless_client import HeadlessClient
    from unittest.mock import AsyncMock,Mock
    requests=Mock();client=HeadlessClient(requests)
    client.status=AsyncMock(return_value={'receiver':{'session':'s'},'pending':None})
    with pytest.raises(ValueError,match='lacks water'):
        asyncio.run(client.call('build_water_facility',dict(kind='harbor',x=1,y=2,z=0)))
    requests.send.assert_not_called()


def test_native_descriptor_wrapper_identity_is_not_recipe_change(water_game):
    from test_ui_network_native_snapshots import NativeRecord
    lua, call = water_game
    lua.globals().water_native_script = lambda filename: NativeRecord(
        fileName=filename, params=lua.table_from({'version': lua.globals().SCRIPT_VERSION or 1}))
    lua.execute('''
local get=api.res.constructionRep.get
api.res.constructionRep.get=function(id)
 local d=get(id);if id>=60 and id<=62 then d.updateScript=water_native_script(d.updateScript.fileName) end;return d
end
''')
    p=preview(call)
    assert call('commit_facility',preview_token=p['preview_token'])['built']
    # Use a different site after the first build. Recipe content is still checked.
    p=call('build_water_facility',kind='shipyard',x=900,y=740,z=2)
    lua.globals().SCRIPT_VERSION=2
    with pytest.raises(Exception,match='changed'):
        call('commit_facility',preview_token=p['preview_token'])
    assert lua.globals().SUBMISSIONS==1


@pytest.mark.parametrize('change', ['none','unknown_error','wrong_command','wrong_pending','missing_error','conflict'])
def test_facility_reconciliation_requires_exact_pre_submit_receipt(water_game, change):
    from test_operation_quota import QuotaChannel
    lua,_=water_game;c=QuotaChannel(lua)
    p=c.query('build_water_facility',dict(kind='harbor',x=700,y=740,z=2))
    assert p['ok'],p
    lua.globals().REVISION=2
    r=c.query('commit_facility',dict(preview_token=p['result']['preview_token']))
    assert not r['ok'] and r['error']=='facility changed since preview; inspect and preview again'
    ledger=c.state['v']['uiConstruction'];old=ledger['requests'][r['id']]
    if change=='unknown_error': old['error']='native outcome unknown'
    elif change=='wrong_command': old['cmd']='buy_vehicles'
    elif change=='wrong_pending': ledger['pending']='a'*32
    elif change=='missing_error': old['error']=None
    elif change=='conflict':
        row=next(v for v in c.state['v']['responses'].values() if v['id']==r['id'])
        proof=json.loads(row['text']);proof['error']='native command failed';row['text']=json.dumps(proof)
    pending=ledger['pending']
    result=c.query('reconcile_facility_rejection',dict(request_id=r['id']))
    assert result['ok']==(change=='none'),result
    assert lua.globals().SUBMISSIONS is None
    if change=='none':
        assert ledger['pending'] is None and old['status']=='reconciled_rejected'
        assert old['retryAllowed'] is False
        assert not c.query('reconcile_facility_rejection',dict(request_id=r['id']))['ok']
        assert not c.query('commit_facility',dict(preview_token=p['result']['preview_token']))['ok']
    else: assert ledger['pending']==pending
