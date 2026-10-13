"""UI to engine construction transport; actual handlers, mocked native engine."""
import json

import pytest

from test_warehouses import warehouse_game
from test_e2e import SCRIPT
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments


@pytest.mark.parametrize('cmd,args', [
    ('build_road', {}), ('build_warehouse', {'x': 1, 'y': 2}),
    ('build_warehouse', {'x': True, 'y': 2, 'z': 0}),
    ('build_warehouse', {'x': 1, 'y': 2, 'z': float('nan')}),
    ('build_warehouse', {'x': 1, 'y': 2, 'z': 0, 'ignoreErrors': True}),
    ('commit_facility', {'preview_token': ''}),
])
def test_build_arguments_rejected(cmd, args):
    with pytest.raises(ValueError):
        validate_build_arguments(cmd, args)


def test_ui_engine_preview_commit_readback_and_replay(warehouse_game, tmp_path):
    lua, _ = warehouse_game
    lua.execute('''
      local oldFind,oldGet=api.res.constructionRep.find,api.res.constructionRep.get
      api.res.constructionRep.find=function(name)
        if name=="::/towns/house.con" then return 100 end
        return oldFind(name)
      end
      api.res.constructionRep.get=function(id)
        if id==100 then return {metadata={}} end
        return oldGet(id)
      end
      local nativeSend=api.cmd.sendCommand
      api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)
        return {event=true,id=id,name=name,param=param}
      end
      api.cmd.sendCommand=function(cmd,callback)
        if cmd.event then forwarded=cmd else nativeSend(cmd,callback) end
      end
    ''')
    script=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    state=lua.execute('''
      local s={value={},snapshot={}}
      function s:get()return self.snapshot end
      function s:set(v)self.value=v end
      return s
    ''')
    log=tmp_path/'stdout.txt'; log.touch()
    reader=UiLogRequests(); output=[]
    lua.globals().print=lambda *args: output.append(' '.join(map(str,args)))

    def query(cmd,args):
        ticket=reader.prepare_build(log,cmd,args)
        status=script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly',
                                        'tnj_bridge_readonly.request',ticket['input'])
        assert status=='Submitted; inspect log'
        event=lua.globals().forwarded
        state['snapshot']=state['value']
        script['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
        with log.open('a',encoding='utf-8') as f:
            f.write('\n'.join(output)+'\n')
        output.clear()
        return ticket, event, reader.read(ticket['id'])['response']

    _,_,survey=query('survey_build_site',dict(x=700,y=740))
    assert survey['ok'] and len(survey['result']['points'])==9
    assert survey['result']['center']['x']==700
    assert survey['result']['center']['y']==740
    _,_,facilities=query('list_facilities',{})
    assert facilities['ok'] and 'items' in facilities['result'], facilities
    ticket,event,preview=query('build_warehouse',dict(x=700,y=740,z=2,module_count=1))
    assert preview['ok'] and preview['result']['preview']
    assert not lua.globals().components[8001]
    token=preview['result']['preview_token']
    ticket,event,built=query('commit_facility',dict(preview_token=token))
    assert built['ok'] and built['result']['built'] and built['result']['verified']
    entity=built['result']['entity']
    before=(lua.globals().SUBMISSIONS or 0)
    # Engine delivery repeats are ignored, including after recreating the script.
    fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    state['snapshot']=state['value']
    fresh['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
    assert (lua.globals().SUBMISSIONS or 0)==before and not output
    _,_,again=query('commit_facility',dict(preview_token=token))
    assert not again['ok'] and (lua.globals().SUBMISSIONS or 0)==before
    _,_,read=query('get_facility_config',dict(entity=entity))
    assert read['ok'] and read['result']['entity']==entity

    # A fresh GUI epoch cannot commit an old preview even with a new request ID.
    _,_,old_preview=query('build_warehouse',dict(x=1700,y=1740,z=2))
    old_token=old_preview['result']['preview_token']
    script=fresh
    _,_,stale=query('commit_facility',dict(preview_token=old_token))
    assert not stale['ok'] and 'session' in stale['error']
    assert (lua.globals().SUBMISSIONS or 0)==before

    # Unknown native outcomes latch subsequent commits. Query readback remains usable.
    _,_,new_preview=query('build_warehouse',dict(x=1700,y=1740,z=2))
    script['_internal']['commands']['commit_facility']=lua.eval('function() error("native outcome unknown") end')
    _,_,unknown=query('commit_facility',dict(preview_token=new_preview['result']['preview_token']))
    assert not unknown['ok']
    assert state['value']['uiConstruction']['pending']
    _,_,next_preview=query('build_warehouse',dict(x=2700,y=2740,z=2))
    _,_,blocked=query('commit_facility',dict(preview_token=next_preview['result']['preview_token']))
    assert not blocked['ok'] and 'unresolved' in blocked['error']
    assert (lua.globals().SUBMISSIONS or 0)==before
