"""Native starter airfield: real Lua handler with guarded native proposal mocks."""
import asyncio
import pytest
from test_facilities import game as facility_game
from tf3_mcp.ui_log import validate_build_arguments

@pytest.fixture
def airfield_game(facility_game):
    lua, call = facility_game
    lua.execute('''
local oldFind=api.res.constructionRep.find;local oldGet=api.res.constructionRep.get
api.res.constructionRep.find=function(n)if n=="::/stations/air/airfield.con"then return 60 end;return oldFind(n)end
api.res.constructionRep.get=function(id)if id==60 then return {metadata={},availability={},params={},updateScript={fileName=BAD_UPDATE and "other@update" or "::/stations/air/airfield.script@updateFn"}}end;return oldGet(id)end
api.res.metaConstructionRep={find=function(n)
 assert(n=="::/stations/air/airfield_era_b.metacon");return 0 end,get=function()
 return {availability={yearFrom=FUTURE and 9999 or 1950,yearTo=1980},createTemplateScript={fileName=BAD_TEMPLATE and "other@template" or "::/stations/air/airfield.script@createTemplateFn",params={}}}
end}
local names={[70]="af_hangar",[71]="af_main",[72]="af_terminal"}
local mf=api.res.moduleRep.find;local mg=api.res.moduleRep.get
api.res.moduleRep.find=function(n)for id,name in pairs(names)do if n=="::/stations/air/airfield/"..name..".module"then return id end end;return mf(n)end
api.res.moduleRep.get=function(id)if names[id]then return {availability={yearFrom=1850,yearTo=0},type=BAD_MODULE and "other" or "airfield_building",metadata={nativeName=names[id],revision=MODULE_REVISION or 1},updateScript={fileName="native@"..names[id],params={}}}end;return mg(id)end
ug_require=function(name)
 assert(name=="::/game_mechanics/company/company_util.tl")
 return {getConstructionDisableCacheData=function(rows)assert(rows[1][3]=="Airfields");return {}end,getConstructionDisableReason=function()return LOCKED and {reason="no permit"}or{numRemaining=1}end}
end
api.engine.terrain.isValidCoordinate=function()return not OUTSIDE end
api.engine.terrain.isOnWater=function()return WATER==true end
''')
    return lua, call


def preview(call):return call('build_airfield',x=700,y=740,z=2,rotation=90)


def test_starter_commit_readback_single_use(airfield_game):
    lua,call=airfield_game
    p=preview(call)
    modules=p['parameters']['modules']
    assert {int(k) for k in modules}=={10001000,10001002,10001004}
    assert [modules[str(k)]['name'].rsplit('/',1)[-1] for k in [10001000,10001002,10001004]]==['af_hangar.module','af_main.module','af_terminal.module']
    assert all(m['metadata']['revision']==1 for m in modules.values())
    assert not p['externalConnectionsBuilt'] and not p['serviceVerified']
    assert lua.globals().SUBMISSIONS is None
    r=call('commit_facility',preview_token=p['preview_token'])
    assert r['built'] and r['verified'] and r['config']['resource']=='::/stations/air/airfield.con'
    with pytest.raises(Exception,match='consumed'):call('commit_facility',preview_token=p['preview_token'])
    with pytest.raises(Exception,match='already exists'):preview(call)
    assert lua.globals().SUBMISSIONS==1


@pytest.mark.parametrize('flag,error',[('FUTURE','unavailable'),('BAD_TEMPLATE','unrecognized'),('BAD_UPDATE','unrecognized'),('BAD_MODULE','unrecognized'),('LOCKED','locked'),('WATER','dry land'),('OUTSIDE','outside')])
def test_preflight_guards(airfield_game,flag,error):
    lua,call=airfield_game;lua.execute(flag+'=true')
    with pytest.raises(Exception,match=error):preview(call)
    assert lua.globals().SUBMISSIONS is None and lua.globals().PREVIEWS is None


def test_collision_rechecked_and_resource_change_consumes(airfield_game):
    lua,call=airfield_game
    p=preview(call);lua.execute('COLLISIONS={{entity=99999}}')
    assert call('commit_facility',preview_token=p['preview_token'])['blocked']
    lua.execute('COLLISIONS={}')
    p=preview(call);lua.execute('MODULE_REVISION=2')
    with pytest.raises(Exception,match='changed'):call('commit_facility',preview_token=p['preview_token'])
    assert lua.globals().SUBMISSIONS is None


def test_mcp_and_strict_schema(monkeypatch):
    from tf3_mcp import server
    calls=[]
    async def fake(cmd,**args):calls.append((cmd,args));return {'preview':True}
    monkeypatch.setattr(server,'_call',fake)
    asyncio.run(server.build_airfield(1,2,3))
    assert calls[0][0]=='build_airfield' and calls[0][1]['_engine'] and calls[0][1]['preview']
    for args in [dict(x=1,y=2),dict(x=1,y=2,z=3,source_entity=4),dict(x=1,y=2,z=float('inf')),dict(x=1,y=2,z=3,ignoreErrors=True)]:
        with pytest.raises(ValueError):validate_build_arguments('build_airfield',args)
    validate_build_arguments('build_airfield',dict(x=1,y=2,z=3))
