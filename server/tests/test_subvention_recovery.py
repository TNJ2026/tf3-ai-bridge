"""Real adapter tests; no native events are sent by reconciliation."""
import json
import asyncio

import pytest
import test_ui_consolidated as ui
from test_subventions import FIXTURE
from tf3_mcp.no_gui_client import NoGuiClient, NoGuiOutcomeUnknown


def pending_previous(c):
    p=c.query('preview_subvention', {'uid':7001})
    token=p['result']['preview_token']
    adapter=c.state['v']['subventionAdapter']
    adapter['submitted']['6000']=c.lua.table_from({'uid':6000, 'gameTime':900000})
    return token


def legacy_rejection(tmp_path, monkeypatch):
    current=ui.SCRIPT
    source=current.read_text(encoding='utf-8')
    # The older adapter created an operation before rejecting, without a phase.
    source=source.replace('phase="prepared",gameTime=now()', 'gameTime=now()')
    # Reproduce the removed historical cross-UID gate only in this legacy fixture.
    source=source.replace('local state = readState()\n',
        'local state = readState()\n'
        'for _,op in pairs(submitted) do if not op.resolved then '
        'error("previous subvention accept requires reconciliation; query state and never resend",0) end end\n')
    legacy=tmp_path/'legacy.lua';legacy.write_text(source,encoding='utf-8')
    monkeypatch.setattr(ui,'SCRIPT',legacy)
    c=ui.Channel(tmp_path,FIXTURE)
    token=pending_previous(c)
    r=c.query('commit_subvention',{'preview_token':token})
    assert not r['ok'] and c.state['v']['uiConstruction']['pending']==r['id']
    assert c.lua.globals().dispatches==0
    monkeypatch.setattr(ui,'SCRIPT',current)
    codec=c.game.script['_internal']['json']
    c.state['v']=codec['decode'](codec['encode'](c.state['v']))
    return c,r['id'],token


def test_predispatch_error_closes_only_new_workflow(tmp_path):
    c=ui.Channel(tmp_path,FIXTURE)
    token=pending_previous(c)
    c.lua.execute('SUB.proposedSubventions[1].data.toDeliver=999')
    r=c.query('commit_subvention',{'preview_token':token})
    assert not r['ok']
    ledger=c.state['v']['uiConstruction']
    assert ledger['pending'] is None and ledger['pendingWorkflow'] is None
    assert ledger['requests'][r['id']]['mutationAttempted'] is False
    assert c.state['v']['subventionAdapter']['submitted']['6000']['resolved'] is None
    assert c.lua.globals().dispatches==0
    assert not c.query('commit_subvention',{'preview_token':token})['ok']


def test_no_gui_accept_not_blocked_by_unresolved_historical_contract(tmp_path):
    c=ui.Channel(tmp_path,FIXTURE)
    token=pending_previous(c)
    r=c.query('commit_subvention',{'preview_token':token})
    assert r['ok'],r
    assert r['result']['submitted'] is True
    assert c.lua.globals().dispatches==1
    assert c.state['v']['subventionAdapter']['submitted']['6000']['resolved'] is None
    assert not c.query('commit_subvention',{'preview_token':token})['ok']
    assert c.lua.globals().dispatches==1


def test_legacy_rejection_survives_reload_and_is_single_use(tmp_path,monkeypatch):
    c,rid,token=legacy_rejection(tmp_path,monkeypatch)
    r=c.query('reconcile_subvention_rejection',{'request_id':rid},epoch='new-session')
    assert r['ok'],r
    assert r['result']['mutationAttempted'] is False
    ledger=c.state['v']['uiConstruction']
    assert ledger['pending'] is None and ledger['pendingWorkflow'] is None
    assert ledger['requests'][rid]['status']=='reconciled_rejected'
    assert not c.query('reconcile_subvention_rejection',{'request_id':rid})['ok']
    assert not c.query('commit_subvention',{'preview_token':token})['ok']
    assert c.lua.globals().dispatches==0


@pytest.mark.parametrize('fault', ['error','command','id','read','token','operation','player','submission','phase','evidence','preview','unused','accepted','time'])
def test_legacy_recovery_refuses_incomplete_or_conflicting_proof(tmp_path,monkeypatch,fault):
    c,rid,token=legacy_rejection(tmp_path,monkeypatch)
    a=c.state['v']['subventionAdapter'];l=c.state['v']['uiConstruction'];op=a['operations'][token]
    if fault=='error':l['requests'][rid]['error']='unknown native failure'
    if fault=='command':l['requests'][rid]['cmd']='commit_loan'
    if fault=='id':rid='0'*32
    if fault=='read':l['pendingWorkflow']['read']='get_loan_operation'
    if fault=='token':a['epoch']='different'
    if fault=='operation':a['operations'][token]=None
    if fault=='player':op['player']=999
    if fault=='submission':a['submitted']['7001']=c.lua.table_from({'uid':7001})
    if fault=='phase':op['phase']='dispatch_started'
    if fault=='evidence':op['acceptanceEvidence']=c.lua.table_from({'acceptedTime':1000000})
    if fault=='preview':a['previews'][token]=c.lua.table_from({'uid':7001})
    if fault=='unused':l['workflowTokens'][token]=c.lua.table_from({'commit':'commit_subvention'})
    if fault=='accepted':c.lua.execute('local t=table.remove(SUB.proposedSubventions,1);t.acceptedTime=1000000;SUB.activeSubventions[1]=t')
    if fault=='time':op['spawnTime']=1e12
    r=c.query('reconcile_subvention_rejection',{'request_id':rid})
    assert not r['ok'],r
    assert c.state['v']['uiConstruction']['pending']
    assert c.lua.globals().dispatches==0


@pytest.mark.parametrize('confirmed', [True,False])
def test_confirmation_read_is_durable_after_native_history_pruned(tmp_path,confirmed):
    c=ui.Channel(tmp_path,FIXTURE)
    p=c.query('preview_subvention',{'uid':7001});token=p['result']['preview_token']
    r=c.query('commit_subvention',{'preview_token':token});assert r['ok'],r
    c.lua.execute('local t=table.remove(SUB.proposedSubventions,1);t.acceptedTime=1000000;SUB.activeSubventions[1]=t')
    if confirmed:
        assert c.query('get_subventions',{'assess':False})['ok']
    c.lua.execute('SUB.activeSubventions={}')
    codec=c.game.script['_internal']['json'];c.state['v']=codec['decode'](codec['encode'](c.state['v']))
    r=c.query('get_subvention_operation',{'operation_id':token},epoch='new-session')
    assert r['ok'] and r['result']['verified']==confirmed
    assert (c.state['v']['uiConstruction']['pending'] is None)==confirmed
    assert c.lua.globals().dispatches==1
    if confirmed:
        p=c.query('preview_subvention',{'uid':7002});assert p['ok'],p
        assert c.query('commit_subvention',{'preview_token':p['result']['preview_token']})['ok']


def test_wrong_identity_never_confirms(tmp_path):
    c=ui.Channel(tmp_path,FIXTURE)
    p=c.query('preview_subvention',{'uid':7001});token=p['result']['preview_token']
    assert c.query('commit_subvention',{'preview_token':token})['ok']
    c.lua.execute('local t=table.remove(SUB.proposedSubventions,1);t.spawnTime=999;t.acceptedTime=1000000;SUB.activeSubventions[1]=t')
    r=c.query('get_subvention_operation',{'operation_id':token})
    assert not r['result']['verified'] and c.state['v']['uiConstruction']['pending']
    assert c.state['v']['subventionAdapter']['submitted']['7001']['resolved'] is None


def test_dispatch_exception_cannot_be_reconciled_as_rejection(tmp_path):
    c=ui.Channel(tmp_path,FIXTURE)
    p=c.query('preview_subvention',{'uid':7001});token=p['result']['preview_token']
    c.lua.execute('local send=api.cmd.sendCommand;api.cmd.sendCommand=function(cmd,cb) if cmd.kind=="event" then dispatches=dispatches+1;error("uncertain dispatch") end;return send(cmd,cb) end')
    r=c.query('commit_subvention',{'preview_token':token})
    assert r['ok'] and not r['result']['verified']
    assert r['result']['phase']=='dispatch_started'
    assert c.state['v']['uiConstruction']['pending']==r['id']
    assert not c.query('reconcile_subvention_rejection',{'request_id':r['id']})['ok']
    assert c.state['v']['uiConstruction']['pending']==r['id']
    assert c.lua.globals().dispatches==1


@pytest.mark.parametrize('fault',[None,'session','pending','version','readback'])
def test_client_reconciliation_checks_version_session_and_independent_readback(fault):
    class Client(NoGuiClient):
        def __init__(self):
            super().__init__(None);self.calls=[]
        async def status(self):
            return {'receiver':{'session':'wrong' if fault=='session' else 's'}}
        async def request(self,name,args):
            self.calls.append(name)
            if name=='get_validation_state':
                after=len(self.calls)>1
                return dict(session='s',pending='wrong' if fault=='pending' else ('r' if not after or fault=='readback' else None),
                            subventionReconciliationVersion=0 if fault=='version' else 1)
            return dict(request_id='r',status='reconciled_rejected',mutationAttempted=False,retryAllowed=False)
    async def run():
        c=Client()
        if fault:
            with pytest.raises((ValueError,NoGuiOutcomeUnknown)):
                await c.reconcile_subvention_rejection('r','s')
        else:assert (await c.reconcile_subvention_rejection('r','s'))['verification']['pending'] is None
        assert c.calls.count('reconcile_subvention_rejection')==(1 if fault in (None,'readback') else 0)
    asyncio.run(run())
