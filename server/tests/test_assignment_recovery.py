"""Reject-only reconciliation never resends a vehicle command or clears unknowns."""
import json
import pytest
from test_e2e import FakeGame, SCRIPT
from tf3_mcp.ui_log import UiLogRequests, validate_build_arguments

@pytest.mark.parametrize("case", ["valid", "lost", "partial", "thrown", "other_command", "wrong_pending", "wrong_vehicle", "wrong_line", "already_assigned", "outside_depot", "wrong_owner", "running", "missing_depot", "line_conflict", "extra_failure", "workflow"])
def test_assignment_reconciliation(tmp_path, case):
    g=FakeGame(tmp_path/'game');lua=g.lua
    lua.execute('''
      components[700]={[3]={stops={{stationGroup=200},{stationGroup=201}}},[10]={player=2}}
      components[701]={[9]={carrier=0,state=0,depot=300,line=-1},[10]={player=2}}
      api.engine.system.transportVehicleSystem.getDepotVehicles=function()return {701}end
      api.engine.system.transportVehicleSystem.getLineVehicles=function()return {}end
      local game=api.engine.getComponent(api.engine.util.getWorld(),api.type.ComponentType.GAME_SPEED);game.speedup=0
      native_calls=0
      api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)return {event=true,id=id,name=name,param=param}end
      api.cmd.sendCommand=function(cmd,cb)
        if cmd.event then forwarded=cmd;return end
        native_calls=native_calls+1
        assert(cmd.kind=="setLine")
        cb(cmd,false,{})
      end
    ''')
    state=lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
    output=[];lua.globals().print=lambda *v:output.append(' '.join(map(str,v)))
    log=tmp_path/'stdout.txt';log.touch();reader=UiLogRequests()
    def send(command,args,module=None):
        module=module or g.script
        t=reader.prepare_build(log,command,args)
        module['guiHandleEvent'](None,None,None,'','tnj_bridge_readonly','tnj_bridge_readonly.request',t['input'])
        e=lua.globals().forwarded
        module['handleEvent'](None,state,'',e['id'],e['name'],e['param'])
        with log.open('a',encoding='utf-8') as f:f.write('\n'.join(output)+'\n')
        output.clear()
        return t,reader.read(t['id'])['response'],e
    original,response,event=send('assign_vehicles',{'vehicles':[701],'line':700,'stop_index':0})
    assert response['ok'] is False
    ledger=state['v']['uiConstruction'];old=ledger['requests'][original['id']]
    assert ledger['pending']==original['id']
    args={'request_id':original['id'],'vehicle':701,'line':700}
    if case=='lost':old['status']='started';old['result']=None
    if case=='partial':old['result']['assigned'][1]=701
    if case=='thrown':old['result']='unknown exception'
    if case=='other_command':old['cmd']='send_to_depot'
    if case=='wrong_pending':ledger['pending']='f'*32
    if case=='wrong_vehicle':args['vehicle']=702
    if case=='wrong_line':args['line']=999
    if case=='already_assigned':lua.execute('components[701][9].line=700')
    if case=='outside_depot':lua.execute('components[701][9].state=1')
    if case=='wrong_owner':lua.execute('components[701][10].player=99')
    if case=='running':lua.execute('api.engine.getComponent(api.engine.util.getWorld(),api.type.ComponentType.GAME_SPEED).speedup=4')
    if case=='missing_depot':lua.execute('api.engine.system.transportVehicleSystem.getDepotVehicles=function()return {}end')
    if case=='line_conflict':lua.execute('api.engine.system.transportVehicleSystem.getLineVehicles=function()return {701}end')
    if case=='extra_failure':old['result']['failures']['hidden']='unknown'
    if case=='workflow':ledger['pendingWorkflow']=lua.table_from({'id':original['id']})
    before=ledger['pending']
    fresh=lua.execute(SCRIPT.read_text(encoding='utf-8'))
    _,result,_=send('reconcile_assignment_rejection',args,fresh)
    assert result['ok']==(case=='valid'),result
    assert lua.globals().native_calls==1
    if case=='valid':
        assert ledger['pending'] is None
        assert old['status']=='reconciled_rejected' and old['retryAllowed'] is False
        assert old['result']['failures'][1]=='vehicle 701 rejected'
        assert result['result']['gameMutation'] is False
        fresh['handleEvent'](None,state,'',event['id'],event['name'],event['param'])
        assert lua.globals().native_calls==1
        _,again,_=send('reconcile_assignment_rejection',args,fresh)
        assert again['ok'] is False
    else:assert ledger['pending']==before

@pytest.mark.parametrize('args',[{}, {'request_id':'a'*32}, {'request_id':'a'*32,'vehicle':True,'line':700}, {'request_id':'bad','vehicle':701,'line':700}, {'request_id':'a'*32,'vehicle':701,'line':700,'force':True}])
def test_reconciliation_arguments_fail_closed(args):
    with pytest.raises(ValueError):validate_build_arguments('reconcile_assignment_rejection',args)
