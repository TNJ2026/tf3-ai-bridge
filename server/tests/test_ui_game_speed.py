"""On-demand speed mutations: strict multipliers and independent native readback."""
import json
import pytest
from test_ui_consolidated import Channel
from tf3_mcp.ui_log import validate_build_arguments


@pytest.mark.parametrize('args',[{}, {'speed':0}, {'speed':0,'expected_speed':True},
 {'speed':True,'expected_speed':1}, {'speed':1.5,'expected_speed':1},
 {'speed':3,'expected_speed':1}, {'speed':-1,'expected_speed':1},
 {'speed':99,'expected_speed':1}, {'speed':'2','expected_speed':1}])
def test_invalid_speed_rejected_by_both_schemas(tmp_path,args):
    with pytest.raises(ValueError):validate_build_arguments('set_game_speed',args)
    c=Channel(tmp_path)
    text='a'*32+' set_game_speed '+json.dumps(args)
    status=c.game.script['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',text)
    assert status!='Submitted; inspect log' and c.lua.globals().dispatches==0


def test_stale_expected_speed_never_dispatches(tmp_path):
    c=Channel(tmp_path)
    r=c.query('set_game_speed',{'speed':4,'expected_speed':0})
    assert not r['ok'] and 'speed changed' in r['error']
    assert c.lua.globals().dispatches==0
    assert c.state['v']['uiConstruction']['pending'] is None


def test_false_success_keeps_pending_and_blocks_next_mutation(tmp_path):
    c=Channel(tmp_path)
    c.lua.execute("""
local old=api.cmd.sendCommand
api.cmd.sendCommand=function(cmd,cb)
 if cmd.kind=='speed' then dispatches=dispatches+1;cb({},true,{}) else old(cmd,cb) end
end
""")
    r=c.query('set_game_speed',{'speed':0,'expected_speed':1})
    assert not r['ok'] and 'readback mismatch' in r['error']
    assert c.state['v']['uiConstruction']['pending']
    assert not c.query('set_game_speed',{'speed':2,'expected_speed':1})['ok']
    assert c.lua.globals().dispatches==1
