"""Native selector contract, retained history, safe text, and transport gates."""
import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest
from test_e2e import MOCK_API, SCRIPT, lupa_mod
from tf3_mcp.ui_log import validate_build_arguments

FIXTURE = r'''
api.type.ComponentType.GAME_SCRIPT=110
STATE={history={8,3,5,9,11,404},notifications={
 [8]={timestamp=200,notification={type='custom',params={value=1}}},
 [3]={timestamp=100,dismissed=true,tracked=true,notification={type='old'}},
 [5]={timestamp=100,expired=true,notification={type='custom'}},
 [9]={timestamp=200,tracked=false,notification={type='custom'}},
 [11]={timestamp=300,notification={type='::/game_mechanics/notifications/types/town_rating_warning.script',
  params={entities={{entity=100}},param={key='transport'}},simParams={mapping={[100]='Test Town'}}}},
 [12]={timestamp=50,notification={type='orphan'}},
},ignored={fully=false,types={custom=true}}}
components[9001]={[110]={state=STATE}}
api.engine.system.gameScriptSystem={getEntityForGameScript=function(p)
 assert(p=='::/game_mechanics/notifications/notifications.gs');return 9001 end}
_=function(s)return s end
ug_require=function(p)
 if p:find('lang_util',1,true) then return {format=function(s,args)
  return (s:gsub('{(%w+)}',function(k)return args[k] end)) end} end
 if p:find('town_util',1,true) then return {GetRatings=function()return {{key='transport',name='Transport'}}end} end
 if p:find('notification_util',1,true) then return {getGuiTypeFromNotificationType=function()return 'Problem'end} end
 error('Unreviewed import '..p)
end
api.cmd.sendCommand=function()error('READ MUST NOT MUTATE')end
math.random=function()error('READ MUST NOT CONSUME RNG')end
'''

@pytest.fixture
def game():
    lua=lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API);lua.execute(FIXTURE)
    script=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    def call(**args):
        result=script['_internal']['commands']['get_notifications'](lua.table_from(args,recursive=True))
        return json.loads(script['_internal']['json']['encode'](result))
    return lua,call

def test_popup_selector_matches_native_not_guessed_expiry(game):
    _,call=game;r=call()
    assert [x['id'] for x in r['items']]==[5,8,9,11]
    assert r['currentCount']==4 and r['total']==4
    assert not r['screenVisibleKnown'] and not r['historyComplete']
    assert r['missingHistoryIds']==[404]
    # Native UI selector does not inspect tracked, ignored or expired flags.
    assert r['items'][0]['expired'] and r['items'][0]['popupEligible']

def test_retained_entries_and_pagination(game):
    _,call=game
    r=call(include_history=True,offset=0,limit=2)
    assert [x['id'] for x in r['items']]==[12,3]
    assert not r['items'][0]['inHistory'] and not r['items'][1]['popupEligible']
    assert r['total']==6 and r['hasMore'] and r['nextOffset']==2
    assert not call(offset=99)['hasMore']

def test_known_native_template_unknown_renderer_and_read_only(game):
    lua,call=game;before=lua.eval('STATE.notifications[11].notification.simParams.mapping[100]')
    r=call();unknown=r['items'][1];known=r['items'][3]
    assert not unknown['textKnown'] and unknown['params']=={'value':1}
    assert known['textKnown'] and known['title']=='Town Rating Very Poor'
    assert 'Transport' in known['description'] and 'Test Town' in known['description']
    assert lua.eval('STATE.notifications[11].notification.simParams.mapping[100]')==before
    assert r['readOnly']

def test_unavailable_state_is_error_not_empty_success(game):
    lua,call=game;lua.execute('STATE.history=nil')
    with pytest.raises(Exception,match='state/history unavailable'):call()

def test_unknown_payload_and_renderer_errors_preserve_entries(game):
    lua,call=game;lua.execute('STATE.notifications[8].notification=nil;ug_require=function()error("renderer unavailable")end')
    r=call();assert r['total']==4
    assert not r['items'][1]['textKnown']
    assert 'renderer unavailable' in r['items'][3]['textUnavailableReason']

@pytest.mark.parametrize('args',[{'include_history':1},{'offset':-1},{'limit':0},{'limit':101},{'extra':True}])
def test_host_rejects_invalid_args(args):
    with pytest.raises(ValueError):validate_build_arguments('get_notifications',args)

def test_defaults_and_old_receiver_gate():
    validate_build_arguments('get_notifications',{})
    from tf3_mcp.no_gui_client import NoGuiClient
    c=NoGuiClient(Mock());c.status=AsyncMock(return_value={'receiver':{'session':'s'},'pending':None})
    with pytest.raises(ValueError,match='lacks notifications'):asyncio.run(c.call('get_notifications',{}))
    c.requests.send.assert_not_called()

def test_public_tool_routes_to_engine(monkeypatch):
    from tf3_mcp import server
    f=AsyncMock(return_value={'readOnly':True});monkeypatch.setattr(server,'_call',f)
    asyncio.run(server.get_notifications())
    f.assert_awaited_once_with('get_notifications',_engine=True,include_history=False,offset=0,limit=100)

def test_subvention_native_entrypoint_and_unreviewed_indirection(game):
    lua,call=game
    lua.execute(r'''
local original=ug_require
local resource='::/game_mechanics/subventions/deliver_passengers/deliver_passengers.res'
local script='::/game_mechanics/subventions/deliver_passengers/deliver_passengers.script@deliver_passengers'
SCRIPT_PATH=script
api.res.genericRep={find=function(id)assert(id==resource);return 1 end,
 get=function()return {data={scriptFile=SCRIPT_PATH}}end}
ug_require=function(path)
 if path=='::/scripts/util.tl' then return {useFn=function(file)
  assert(file==script)
  return {getNotificationData=function(id,params,status,reason,names)
   assert(status=='Proposed' and reason=='None');return {description=names[100]..' route'}end}
 end} end
 return original(path)
end
STATE.notifications[11].notification={type='::/game_mechanics/notifications/types/subvention_notification.script',
 params={uid=42,id=resource,params={},status=1},simParams={mapping={[100]='Test Town'}}}
''')
    r=call()['items'][3]
    assert r['textKnown'] and r['description']=='Test Town route' and r['subventionUid']==42
    lua.execute("SCRIPT_PATH='unreviewed.script@run'")
    r=call()['items'][3]
    assert not r['textKnown'] and 'differs' in r['textUnavailableReason']

def test_native_userdata_state_fallback(game):
    lua,call=game
    lua.execute('components[9001][110]={state_native={asTable=function()return STATE end}}')
    assert call()['currentCount']==4

def test_low_level_host_old_receiver_cannot_publish(host):
    with pytest.raises(ValueError,match='lacks notifications'):
        host.send('get_notifications',{},kind='build',expected_session='session')
    assert not host.ledger.exists()

from test_no_gui import host
