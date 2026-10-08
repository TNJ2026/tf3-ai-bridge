"""Native prospecting adapter: mock mutations only; real read-only checks recorded separately."""
import json
import pytest
from test_e2e import MOCK_API, SCRIPT, lupa_mod

FIXTURE = r"""
api.type.ComponentType.GAME_SCRIPT=110
NOW=100;os.clock=function()return NOW end
STATE={pendingProspections={}};HISTORY={};SEND_COUNT=0;REV=1
components[9001]={[110]={state={notifications=HISTORY}}}
api.engine.system.gameScriptSystem={getEntityForGameScript=function(p)return p:find('notifications') and 9001 or 9000 end}
api.res.genericRep={getAllOfType=function()return {1,2}end,getName=function(i)return 'explore'..i end,
 get=function(i)return {data={cargoType='cargo'..i,permitKey='shared',requiredTags={i==1 and 'FARM' or 'NONE'}}}end}
api.res.getBaseConfig=function()return {economyId='base'}end
api.res.economyRep={find=function()return 0 end,get=function()return {placementParams={farm={tags={'FARM'}}}}end}
api.res.cargoTypeRep={find=function()return 1 end,get=function()return {name='Vegetables'}end}
local util={prospectionTimeMs=6000,externalGetCompanyState=function()return STATE end,
 getConstructionDisableCacheData=function()return {}end,getConstructionDisableReason=function()
 return LOCKED and {reason='Cooldown'} or {numRemaining=1}end}
ug_require=function(p)
 if p:find('company_util')then return util end
 if p:find('entity_util')then return {makeEntityAndRevision=function(id)return {entity=id,revision=REV}end,
 entityEquals=function(a,b)return a.entity==b.entity and a.revision==b.revision end}end
 return {constructionDesc={make=function(x)return x end}}
end
api.cmd.makeScriptingSendEventCmd=function(src,id,name,p)
 assert(src=='' and id=='Companies' and name=='spawnIndustry');assert(p.permitKey=='shared');assert(p.types[1]=='farm')
 return p
end
function DELIVER(p)
 STATE.pendingProspections={{townEntity={entity=p.townEntity,revision=REV},cargoType=p.cargoType,initiatedTimestamp=components[1][4].gameTime,attempts=0}}
end
api.cmd.sendCommand=function(p,cb)
 SEND_COUNT=SEND_COUNT+1
 if THROW then error('unknown outcome')end
 if DELAY then DEFERRED=p else DELIVER(p)end
 cb({},true)
end
"""
@pytest.fixture
def game():
    lua=lupa_mod.LuaRuntime(unpack_returned_tuples=True);lua.execute(MOCK_API);lua.execute(FIXTURE)
    script=lua.execute(SCRIPT.read_text(encoding='utf8'))
    def call(name,**args):
        r=script['_internal']['commands'][name](lua.table_from(args,recursive=True))
        return json.loads(script['_internal']['json']['encode'](r))
    return lua,call

def preview(call):return call('preview_prospection',town=100,resource='explore1')['preview_token']

def test_readonly_catalog_and_preview(game):
    lua,c=game;r=c('list_prospections')['resources'];assert r[0]['available'] and not r[1]['available']
    preview(c);assert c('get_prospections')['pending']==[];assert lua.globals().SEND_COUNT==0

def test_once_and_duplicate(game):
    lua,c=game;t=preview(c);r=c('commit_prospection',preview_token=t);assert r['verified'] and r['status']=='pending'
    with pytest.raises(Exception,match='consumed'):c('commit_prospection',preview_token=t)
    with pytest.raises(Exception,match='already pending'):preview(c)
    assert lua.globals().SEND_COUNT==1

@pytest.mark.parametrize('change,error', [('LOCKED=true','unavailable'),('REV=2','reference changed'),('NOW=161','expired'),('components[1][4].gameTime=1','session changed')])
def test_stale_preview_no_dispatch(game,change,error):
    lua,c=game;t=preview(c);lua.execute(change)
    with pytest.raises(Exception,match=error):c('commit_prospection',preview_token=t)
    assert lua.globals().SEND_COUNT==0

@pytest.mark.parametrize('flag',['DELAY','THROW'])
def test_unknown_blocks_further_submission(game,flag):
    lua,c=game;t=preview(c);lua.globals()[flag]=True
    assert c('commit_prospection',preview_token=t)['status']=='needs_reconciliation'
    t2=preview(c)
    with pytest.raises(Exception,match='reconciliation'):c('commit_prospection',preview_token=t2)
    assert lua.globals().SEND_COUNT==1
    if flag=='DELAY':
        lua.execute('DELIVER(DEFERRED)');assert c('get_prospection_operation',operation_id=t)['status']=='pending'

@pytest.mark.parametrize('success',[True,False])
def test_result_requires_native_notification(game,success):
    lua,c=game;t=preview(c);c('commit_prospection',preview_token=t);lua.execute('STATE.pendingProspections={}')
    assert c('get_prospection_operation',operation_id=t)['status']=='finished_result_unconfirmed'
    lua.execute("HISTORY[1]={timestamp=123001,notification={type='::/game_mechanics/company/company_notification_prospection.script',params={companyEntity=2,townEntity={entity=100},cargoType='cargo1'"+(',resultEntity={entity=888}'if success else '')+"}}}")
    assert c('get_prospection_operation',operation_id=t)['status']==('succeeded'if success else 'failed')

def test_invalid_inputs_and_shared_permit_recheck(game):
    lua,c=game
    for args in [dict(town=999,resource='explore1'),dict(town=100,resource='unknown'),dict(town=100,resource='explore2')]:
        with pytest.raises(Exception):c('preview_prospection',**args)
    assert lua.globals().SEND_COUNT==0


def test_mcp_routes_to_engine(monkeypatch):
    import asyncio
    from tf3_mcp import server
    seen=[]
    async def fake(cmd,**args):seen.append((cmd,args));return {}
    monkeypatch.setattr(server,"_call",fake)
    async def run():
        await server.list_prospections()
        await server.get_prospections()
        await server.preview_prospection(100,"explore1")
        await server.commit_prospection("token")
        await server.get_prospection_operation("token")
    asyncio.run(run())
    assert [v[0] for v in seen]==["list_prospections","get_prospections","preview_prospection","commit_prospection","get_prospection_operation"]
    assert all(v[1]["_engine"] for v in seen)


def test_missing_result_history_fails_closed(game):
    lua,c=game;t=preview(c);lua.execute('components[9001]=nil')
    assert not c('get_prospections')['history_available']
    with pytest.raises(Exception,match='history unavailable'):c('commit_prospection',preview_token=t)
    assert lua.globals().SEND_COUNT==0


def test_reloaded_bridge_rejects_old_token(game):
    lua,c=game;t=preview(c)
    new=lua.execute(SCRIPT.read_text(encoding='utf8'))
    with pytest.raises(Exception,match='reloaded'):
        new['_internal']['commands']['commit_prospection'](lua.table_from({'preview_token':t}))
    assert lua.globals().SEND_COUNT==0


def test_portable_receipt_survives_lua_instance_change(game):
    lua,c=game;t=preview(c);result=c('commit_prospection',preview_token=t)
    receipt=result['tracking_receipt'];assert receipt['registered']
    new=lua.execute(SCRIPT.read_text(encoding='utf8'))
    r=new['_internal']['commands']['get_prospection_operation'](lua.table_from({'operation_id':t,'tracking_receipt':receipt},recursive=True))
    assert r['verified'] and r['status']=='pending'
    assert lua.globals().SEND_COUNT==1
    receipt['town']['revision']=99
    r=new['_internal']['commands']['get_prospection_operation'](lua.table_from({'operation_id':t,'tracking_receipt':receipt},recursive=True))
    assert not r['verified']
