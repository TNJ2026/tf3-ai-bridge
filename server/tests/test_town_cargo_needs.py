"""City demand edits exercise the real Lua bridge without mutating a live save."""
import asyncio
import json
import pytest
from test_e2e import MOCK_API, SCRIPT, lupa_mod

FIXTURE = r"""
NOW=100;REV=1;SENDS=0;os.clock=function()return NOW end
components[100][2].cargoNeeds={{},{{1,1}},{{2,1}}}
api.res.cargoTypeRep={getAll=function()return {[0]='passengers',[1]='fish',[2]='fuel',[3]='clothes'}end}
ug_require=function()return {makeEntityAndRevision=function(id)return {entity=id,revision=REV}end}end
api.cmd.makeTownUpdateCargoNeedsCmd=function(id,needs,update)return {id=id,needs=needs,update=update}end
api.cmd.sendCommand=function(cmd,cb)
 SENDS=SENDS+1
 if THROW then error('unknown dispatch outcome')end
 if FAIL then cb({},false);return end
 local weighted={};for i,ids in ipairs(cmd.needs)do weighted[i]={};for k,id in ipairs(ids)do assert(type(id)=='number');weighted[i][k]={id,1/k}end end
 cmd.weighted=weighted
 if DELAY then PENDING=cmd else components[cmd.id][2].cargoNeeds=weighted;REV=REV+1 end
 UPDATE=cmd.update;cb({},true)
end
"""
@pytest.fixture
def game():
    lua=lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API);lua.execute(FIXTURE)
    bridge=lua.execute(SCRIPT.read_text(encoding='utf8'))['_internal']
    def call(cmd,**args):
        return json.loads(bridge['json']['encode'](bridge['commands'][cmd](lua.table_from(args,recursive=True))))
    return lua,call

def preview(call,**kw):
    return call('preview_town_cargo_needs',town=100,commercial=[3],**kw)['preview_token']

def test_equal_count_edit_noop_and_readback(game):
    lua,c=game
    p=c('preview_town_cargo_needs',town=100,commercial=[2],industrial=[3],update_buildings=True)
    assert lua.globals().SENDS==0
    r=c('commit_town_cargo_needs',preview_token=p['preview_token'])
    assert r['verified'] and r['observed']==dict(residential=[],commercial=[2],industrial=[3])
    assert lua.globals().UPDATE is True
    with pytest.raises(Exception,match='consumed'):c('commit_town_cargo_needs',preview_token=p['preview_token'])
    p=c('preview_town_cargo_needs',town=100,commercial=[2])
    assert c('commit_town_cargo_needs',preview_token=p['preview_token'])['no_change']
    assert lua.globals().SENDS==1

@pytest.mark.parametrize('args',[dict(commercial=[]),dict(commercial=[1,2]),dict(commercial=[0]),dict(commercial=[99]),dict(commercial=[1,1]),dict(commercial=[1.5]),dict(commercial=[True]),dict(commercial='bad'),dict(commercial={2:1}),dict(update_buildings='yes'),{}])
def test_invalid_never_dispatches(game,args):
    lua,c=game
    with pytest.raises(Exception):c('preview_town_cargo_needs',town=100,**args)
    assert lua.globals().SENDS==0

@pytest.mark.parametrize('change',['NOW=161','REV=2','components[100][2].cargoNeeds[2][1][2]=0.5','components[100][2].cargoNeeds[2]={{2,1}}','components[1][4].gameTime=0','components[100]=nil'])
def test_stale_preview_never_dispatches(game,change):
    lua,c=game;t=preview(c);lua.execute(change)
    with pytest.raises(Exception):c('commit_town_cargo_needs',preview_token=t)
    assert lua.globals().SENDS==0

@pytest.mark.parametrize('flag',['DELAY','FAIL','THROW'])
def test_unknown_outcome_locks_and_delayed_readback(game,flag):
    lua,c=game;t=preview(c);lua.globals()[flag]=True
    assert c('commit_town_cargo_needs',preview_token=t)['status']=='needs_reconciliation'
    t2=preview(c)
    with pytest.raises(Exception,match='reconciliation'):c('commit_town_cargo_needs',preview_token=t2)
    assert lua.globals().SENDS==1
    if flag=='DELAY':
        lua.execute('components[PENDING.id][2].cargoNeeds=PENDING.weighted')
        assert c('get_town_cargo_operation',operation_id=t)['verified']
        assert lua.globals().SENDS==1

def test_mcp_forwarding_and_validation(monkeypatch):
    from tf3_mcp import server
    calls=[]
    async def fake(cmd,**kw):calls.append((cmd,kw));return {}
    monkeypatch.setattr(server,'_call',fake)
    async def run():
        await server.get_town_cargo_needs(100)
        await server.preview_town_cargo_needs(100,commercial=[])
        await server.commit_town_cargo_needs('token')
        await server.get_town_cargo_operation('token')
        with pytest.raises(ValueError):await server.preview_town_cargo_needs(100)
        with pytest.raises(ValueError):await server.preview_town_cargo_needs(100,commercial=[True])
    asyncio.run(run())
    assert calls[1]==('preview_town_cargo_needs',dict(town=100,commercial=[],update_buildings=False))
    assert len(calls)==4
