"""Recover only a durable, proven pre-dispatch legacy town identity rejection."""
import json
import pytest
import test_ui_consolidated as ui
from test_town_cargo_needs import FIXTURE


def rejected_legacy_tick(tmp_path,monkeypatch):
    current=ui.SCRIPT
    source=current.read_text(encoding='utf-8')
    marker='and an[1]==bn[1] and an[2]==bn[2]'
    assert source.count(marker)==1
    legacy=tmp_path/'bridge.script.lua'
    legacy.write_text(source.replace(marker,marker+' and an[3]==bn[3]'),encoding='utf-8')
    monkeypatch.setattr(ui,'SCRIPT',legacy)
    c=ui.Channel(tmp_path,FIXTURE)
    p=c.query('preview_town_cargo_needs',{'town':100,'commercial':[3]})
    assert p['ok'],p
    token=p['result']['preview_token']
    c.lua.execute('REV=253')
    r=c.query('commit_town_cargo_needs',{'preview_token':token})
    assert not r['ok'] and r['error'].endswith('town/session changed'),r
    assert c.lua.globals().dispatches==0
    monkeypatch.setattr(ui,'SCRIPT',current)
    # Simulate a state save/load (no shared references survive).
    codec=c.game.script['_internal']['json']
    c.state['v']=codec['decode'](codec['encode'](c.state['v']))
    return c,r['id'],token


def test_proven_legacy_tick_rejection_single_use_and_persistent(tmp_path,monkeypatch):
    c,request,token=rejected_legacy_tick(tmp_path,monkeypatch)
    r=c.query('reconcile_town_cargo_rejection',{'request_id':request},epoch='reloaded-session')
    assert r['ok'] and r['result']['status']=='reconciled_rejected',r
    state=c.state['v'];ledger=state['uiConstruction']
    assert ledger['pending'] is None and ledger['pendingWorkflow'] is None
    assert state['town_cargoAdapter']['previews'][token] is None
    assert ledger['requests'][request]['mutationAttempted'] is False
    assert not c.query('reconcile_town_cargo_rejection',{'request_id':request})['ok']
    assert not c.query('commit_town_cargo_needs',{'preview_token':token})['ok']
    assert c.lua.globals().dispatches==0


@pytest.mark.parametrize('change',[
 'unknown_error','wrong_id','operation_exists','missing_preview','token_still_unused',
 'wrong_read','wrong_epoch','generation','modification','demand','weight','player','clock'])
def test_recovery_refuses_incomplete_or_changed_proof(tmp_path,monkeypatch,change):
    c,request,token=rejected_legacy_tick(tmp_path,monkeypatch)
    state=c.state['v'];ledger=state['uiConstruction'];adapter=state['town_cargoAdapter']
    if change=='unknown_error':ledger['requests'][request]['error']='native unknown result'
    if change=='wrong_id':request='0'*32
    if change=='operation_exists':adapter['operations'][token]=c.lua.table_from({'status':'dispatched'})
    if change=='missing_preview':adapter['previews'][token]=None
    if change=='token_still_unused':ledger['workflowTokens'][token]=c.lua.table_from({'commit':'commit_town_cargo_needs'})
    if change=='wrong_read':ledger['pendingWorkflow']['read']='get_loan_operation'
    if change=='wrong_epoch':adapter['epoch']='different'
    if change=='generation':c.lua.execute('GEN=2')
    if change=='modification':c.lua.execute('MODREV=2')
    if change=='demand':c.lua.execute('components[100][2].cargoNeeds[2][1][1]=2')
    if change=='weight':c.lua.execute('components[100][2].cargoNeeds[2][1][2]=.5')
    if change=='player':adapter['previews'][token]['before']['player']=123
    if change=='clock':adapter['previews'][token]['before']['gameTime']=1e12
    r=c.query('reconcile_town_cargo_rejection',{'request_id':request})
    assert not r['ok'],r
    assert c.state['v']['uiConstruction']['pending']
    assert c.lua.globals().dispatches==0
