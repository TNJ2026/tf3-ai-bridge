"""Actual GUI/engine road handlers against the native API fixture; not live evidence."""
import json

import pytest

from test_e2e import FakeGame, bridge_dir, SCRIPT
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments


@pytest.mark.parametrize('endpoint', [True, {}, {'node': True}, {'node': 1, 'x': 0},
                                      {'x': 0, 'y': float('inf')}, {'x': 1, 'y': 2, 'snap': 5}])
def test_reject_unsafe_endpoint(endpoint):
    with pytest.raises(ValueError):
        validate_build_arguments('preview_road', {'start': endpoint, 'end': {'x': 200, 'y': 300}, 'street_type': 'town/town_old_small'})


def test_road_panel_preview_commit_readback_duplicate_and_stale(bridge_dir, tmp_path):
    with FakeGame(bridge_dir) as game:
        lua, script = game.lua, game.script
        lua.execute('''
          local send=api.cmd.sendCommand
          api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)
            return {event=true,id=id,name=name,param=param}
          end
          api.cmd.sendCommand=function(cmd,callback)
            if cmd.event then forwarded=cmd else send(cmd,callback) end
          end
        ''')
        state = lua.execute('local s={v={},snapshot={}};function s:get()return self.snapshot end;function s:set(v)self.v=v end;return s')
        log=tmp_path/'stdout.txt'; log.touch()
        reader=UiLogRequests(); output=[]
        lua.globals().print=lambda *args: output.append(' '.join(map(str,args)))

        def query(cmd,args):
            ticket=reader.prepare_build(log,cmd,args)
            assert script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly', 'tnj_bridge_readonly.request',ticket['input'])=='Submitted; inspect log'
            event=lua.globals().forwarded
            # Native events can run in separate module instances and get() can
            # retain the event-start snapshot. Keep only the GUI instance fixed.
            state['snapshot']=state['v']
            fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
            fresh['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
            with log.open('a',encoding='utf-8') as f: f.write('\n'.join(output)+'\n')
            output.clear()
            return event,reader.read(ticket['id'])['response']

        args={'start': {'x': 700, 'y': 700}, 'end': {'x': 800, 'y': 700}, 'street_type': 'town/town_old_small'}
        _,preview=query('preview_road',args)
        assert preview['ok'], preview
        assert preview['result']['preview'] and preview['result']['buildable']
        token=preview['result']['preview_token']
        event,built=query('commit_road',{'preview_token':token})
        assert built['ok'] and built['result']['built'] and built['result']['verified'],built
        assert not state['v']['uiConstruction']['pending']
        _,read=query('get_entity',{'id':built['result']['edges'][0]})
        assert read['ok'] and 'BASE_EDGE' in read['result']['components']
        # A repeated delivered event never emits a second response or builds again.
        state['snapshot']=state['v']
        script['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
        assert not output
        _,repeat=query('commit_road',{'preview_token':token})
        assert not repeat['ok']

        # Reproduce the old missing module-local ticket; no native dispatch.
        _,preview=query('preview_road',args)
        state['v']['uiRoadAdapter']=None
        event,rejected=query('commit_road',{'preview_token':preview['result']['preview_token']})
        assert not rejected['ok'] and 'Unknown or consumed road preview' in rejected['error']
        rejected_id=rejected['id']
        assert state['v']['uiConstruction']['pending']==rejected_id
        _,reconciled=query('reconcile_road_rejection',{'request_id':rejected_id})
        assert reconciled['ok'] and not reconciled['result']['mutationAttempted']
        assert not state['v']['uiConstruction']['pending']
        assert state['v']['uiConstruction']['requests'][rejected_id]['status']=='reconciled_rejected'
        _,again=query('reconcile_road_rejection',{'request_id':rejected_id})
        assert not again['ok']

        # Unknown/native failures cannot be cleared by the narrow recovery path.
        state['v']['uiConstruction']['pending']=rejected_id
        state['v']['uiConstruction']['requests'][rejected_id]['status']='error'
        for _,row in state['v']['responses'].items():
            if row['id']==rejected_id:
                row['text']=json.dumps({'id':rejected_id,'ok':False,'error':'native outcome unknown'})
        _,blocked=query('reconcile_road_rejection',{'request_id':rejected_id})
        assert not blocked['ok'] and state['v']['uiConstruction']['pending']==rejected_id

        # Both validation layers refuse collision overrides.
        bad=dict(args,allow_collisions=True)
        with pytest.raises(ValueError): reader.prepare_build(log,'preview_road',bad)
        raw='a'*32+' preview_road '+json.dumps(bad)
        assert 'Invalid construction argument' in script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',raw)


def test_road_expiry_and_changed_endpoints_consume_tokens(bridge_dir):
    with FakeGame(bridge_dir) as game:
        lua=game.lua
        commands=game.script['_internal']['commands']
        args=lua.table_from({'start': {'node': lua.globals().STREET_C},
                             'end': {'x': 300, 'y': 0}, 'street_type': 'town/town_old_small'}, recursive=True)
        preview=commands['preview_road'](args)
        token=preview['preview_token'];assert token
        lua.execute('components[STREET_C][api.type.ComponentType.BASE_NODE].position.x=101')
        with pytest.raises(Exception, match='endpoints changed'):
            commands['commit_road'](lua.table_from({'preview_token':token}))
        with pytest.raises(Exception, match='consumed'):
            commands['commit_road'](lua.table_from({'preview_token':token}))
        args=lua.table_from({'start': {'x': 700, 'y': 700}, 'end': {'x': 800, 'y': 700}, 'street_type': 'town/town_old_small'},recursive=True)
        preview=commands['preview_road'](args)
        lua.execute('local old=os.clock;os.clock=function()return old()+61 end')
        with pytest.raises(Exception, match='expired'):
            commands['commit_road'](lua.table_from({'preview_token':preview['preview_token']}))


@pytest.mark.parametrize('bad', [
    {'ok': False}, {'placementBlocked': True}, {'collisions': [68459]},
    {'commitSupported': False}, {'critical': True}, {'blocked': True},
])
def test_native_placement_failure_never_issues_or_uses_ticket(bridge_dir, bad):
    """Native geometry can be buildable while placement is rejected (live airport case)."""
    with FakeGame(bridge_dir) as game:
        lua = game.lua
        commands = game.script['_internal']['commands']
        good = {'ok': True, 'buildable': True, 'commitSupported': True, 'collisions': []}
        lua.globals().road_result = lua.table_from(dict(good, **bad), recursive=True)
        lua.globals().road_commands = commands
        lua.execute('''
          native_mutations=0
          road_commands.build_road=function(args)
            if not args.preview then native_mutations=native_mutations+1 end
            return road_result
          end
        ''')
        args = lua.table_from({'start': {'x': 700, 'y': 700},
                              'end': {'x': 800, 'y': 700},
                              'street_type': 'town/town_old_small'}, recursive=True)
        assert commands['preview_road'](args)['preview_token'] is None
        lua.globals().road_result = lua.table_from(good, recursive=True)
        token = commands['preview_road'](args)['preview_token']
        assert token
        lua.globals().road_result = lua.table_from(dict(good, **bad), recursive=True)
        with pytest.raises(Exception, match='no longer buildable'):
            commands['commit_road'](lua.table_from({'preview_token': token}))
        assert lua.globals().native_mutations == 0
        with pytest.raises(Exception, match='consumed'):
            commands['commit_road'](lua.table_from({'preview_token': token}))
