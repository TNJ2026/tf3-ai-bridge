"""One-envelope receiver execution, using native proposal mocks (not live tests)."""
import json

import pytest

from test_road_graph import graph_channel, node, edge
from test_no_gui import host, TAG, GEN
from tf3_mcp.ui_log import validate_build_arguments

PID = '1234567890abcdef1234567890abcdef'


def step(name='road1', y=700):
    ref = {'$ref':name+'.commit.edges.1'}
    return dict(id=name, preview='preview_road_graph', max_cost=100000,
                arguments={'graph':{'nodes':[node(700,y),node(800,y)],'edges':[edge(0,1)]}},
                checks=[{'command':'get_entity','arguments':{'id':ref},'expect':{'id':ref}}])


def project(steps=None):
    return dict(project_id=PID, steps=steps or [step()], cash_floor=5000000,
                reserved_cash=0, backup_save='project_backup')


def channel(tmp_path):
    c=graph_channel(tmp_path)
    c.lua.execute('components[1][5].speedup=0;components[2][6].balance=100000000')
    return c


def test_two_roads_one_envelope_with_independent_checks(tmp_path):
    c=channel(tmp_path)
    r=c.query('execute_project', project([step(),step('road2',900)]))
    assert r['ok'],r
    assert r['result']['complete'],r
    assert c.lua.globals().dispatches==2
    assert all(s['status']=='complete' and len(s['requests'])==3 for s in r['result']['steps'])
    assert c.state['v']['uiProjectActive'] is None
    assert c.query('get_project',{'project_id':PID})['result']['complete']
    assert not c.query('execute_project',project())['ok']
    assert c.lua.globals().dispatches==2


def test_second_quote_failure_resume_never_rebuilds_first(tmp_path):
    c=channel(tmp_path);a=project([step(),step('road2',900)])
    a['steps'][1]['max_cost']=0
    r=c.query('execute_project',a)
    assert r['ok'] and r['result']['status']=='blocked',r
    assert r['result']['steps'][0]['status']=='complete'
    assert c.lua.globals().dispatches==1
    r=c.query('resume_project',{'project_id':PID,'backup_save':'fresh_backup'})
    assert r['ok'] and r['result']['status']=='blocked',r
    assert c.lua.globals().dispatches==1
    assert c.query('cancel_project',{'project_id':PID})['result']['status']=='cancelled'


def test_acceptance_failure_resumes_reads_only(tmp_path):
    c=channel(tmp_path);a=project();a['steps'][0]['checks'][0]['expect']={'id':999}
    r=c.query('execute_project',a)
    assert r['ok'] and r['result']['status']=='acceptance_failed',r
    assert c.lua.globals().dispatches==1
    r=c.query('resume_project',{'project_id':PID,'backup_save':'fresh_backup'})
    assert r['result']['status']=='acceptance_failed'
    assert c.lua.globals().dispatches==1


def test_unknown_readback_freezes_other_writes_and_resume(tmp_path):
    c=channel(tmp_path);c.lua.globals().WRONG_LANES=True
    r=c.query('execute_project',project([step(),step('road2',900)]))
    assert r['ok'] and r['result']['status']=='unknown',r
    assert c.lua.globals().dispatches==1
    assert c.state['v']['uiProjectActive']==PID
    assert c.query('get_project',{'project_id':PID})['result']['status']=='unknown'
    assert not c.query('resume_project',{'project_id':PID,'backup_save':'fresh_backup'})['ok']
    assert not c.query('cancel_project',{'project_id':PID})['ok']
    assert not c.query('set_game_speed',{'speed':1,'expected_speed':0})['ok']
    assert c.lua.globals().dispatches==1


@pytest.mark.parametrize('mode',['cash','running','reserve','quota'])
def test_admission_rejects_without_mutation(tmp_path,mode):
    c=channel(tmp_path);a=project()
    if mode=='cash':c.lua.execute('components[2][6].balance=5100000')
    if mode=='running':c.lua.execute('components[1][5].speedup=1')
    if mode=='reserve':a['reserved_cash']=95000000
    if mode=='quota':
        c.query('get_validation_state',{})
        # Inspect actual field through native quota helper rather than assuming its layout.
        c.state['v']['uiConstruction']['quota']=c.lua.table_from({'round':0,'used':256})
    r=c.query('execute_project',a)
    assert not r['ok'],r
    assert c.lua.globals().dispatches==0


@pytest.mark.parametrize('mutation', [
    lambda a:a['steps'][0].update(preview='commit_road'),
    lambda a:a.update(cash_floor=0),
    lambda a:a['steps'][0].update(checks=[]),
    lambda a:a['steps'][0]['checks'][0].update(command='set_game_speed'),
    lambda a:a['steps'][0]['arguments'].update(bogus=True),
    lambda a:a['steps'][0]['checks'][0]['arguments'].update(id={'$ref':'future.commit.entity'}),
    lambda a:a.update(steps=[step()]*9),
    lambda a:a.update(steps=[step(),step()]),
])
def test_host_validates_entire_plan(mutation):
    a=project();mutation(a)
    with pytest.raises(ValueError):validate_build_arguments('execute_project',a)


def test_old_receiver_rejects_before_publication(host):
    with pytest.raises(ValueError,match='projectBatchVersion'):
        host.send('execute_project',project(),kind='build',expected_session='session')
    assert not host.ledger.exists()


def test_verified_backup_required_for_raw_project(host):
    host.log.write_text(TAG+json.dumps(dict(generation=GEN,session='session',slot=1,
        status='ready',utc=100,clock=10,due=12,projectBatchVersion=2,
        inputLimits={'default':512,'execute_project':8192}))+'\n')
    with pytest.raises(ValueError,match='Verified current-session backup'):
        host.send('execute_project',project(),kind='build',expected_session='session')
    assert not host.ledger.exists()


def test_blocked_cash_can_resume_successfully(tmp_path):
    c=channel(tmp_path)
    c.lua.execute('components[2][6].balance=5100000')
    assert not c.query('execute_project',project())['ok']
    c.lua.execute('components[2][6].balance=100000000')
    r=c.query('resume_project',{'project_id':PID,'backup_save':'fresh_backup'})
    assert r['result']['complete'],r
    assert c.lua.globals().dispatches==1


def test_native_account_balance_fallback(tmp_path):
    c=channel(tmp_path)
    c.lua.execute('api.engine.util.finance.getPlayersBalance=function()return nil end')
    r=c.query('execute_project',project())
    assert r['result']['complete'],r


@pytest.mark.parametrize('enabled,authorized',[(True,True),(True,False),(False,True)])
def test_no_costs_requires_explicit_opt_in_and_native_flag(tmp_path,enabled,authorized):
    c=channel(tmp_path)
    c.lua.execute('api.engine.util.finance.getPlayersBalance=function()return nil end;components[2][6].balance=0')
    c.lua.execute('api.res.getBaseConfig=function()return {noCosts='+str(enabled).lower()+'}end')
    a=project();a['allow_no_costs']=authorized
    r=c.query('execute_project',a)
    assert (r['ok'] and r['result']['complete'])==(enabled and authorized),r
    assert c.lua.globals().dispatches==(1 if enabled and authorized else 0)


def test_later_step_can_check_prior_committed_entity(tmp_path):
    c=channel(tmp_path);a=project([step(),step('road2',900)])
    a['steps'][1]['checks'].append(a['steps'][0]['checks'][0])
    r=c.query('execute_project',a)
    assert r['result']['complete'],r
    assert c.lua.globals().dispatches==2


def test_receiver_validates_later_step_before_any_construction(tmp_path):
    from test_e2e import SCRIPT
    c=channel(tmp_path);a=project([step(),step('road2',900)])
    a['steps'][1]['preview']='set_game_speed'
    fresh=c.lua.execute(SCRIPT.read_text(encoding='utf-8'),name='test/bridge.script.lua')
    fresh['handleEvent'](None,c.state,'','tnj_bridge_build','tnj_bridge_build.request',
        json.dumps(dict(id='f'*32,cmd='execute_project',args=a,facilityEpoch='test')))
    assert c.lua.globals().dispatches==0
    assert c.state['v']['uiProjects'] is None
    response=json.loads(bytes.fromhex(c.output[-1].split('hex=')[1]))
    assert not response['ok'] and 'Unsupported project preview' in response['error']


def test_changed_session_cannot_resume(tmp_path):
    c=channel(tmp_path);a=project();a['steps'][0]['max_cost']=0
    assert c.query('execute_project',a)['result']['status']=='blocked'
    r=c.query('resume_project',{'project_id':PID,'backup_save':'fresh_backup'},epoch='other')
    assert not r['ok']
    assert c.lua.globals().dispatches==0


def test_mcp_wrapper_saves_once_and_dispatches_one_project(tmp_path,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from tf3_mcp import server
    calls=[]
    class Client:
        requests=SimpleNamespace(directory=tmp_path)
        async def status(self):return {'receiver':{'projectBatchVersion':2}}
        async def call(self,command,args):
            calls.append((command,args))
            return {'get_game_state':{'speedup':0},'get_validation_state':{},
                    'save_game':{'verified':True},'execute_project':{'complete':True}}[command]
    monkeypatch.setattr(server,'transport_mode',lambda:'no_gui')
    monkeypatch.setattr(server,'no_gui_client',lambda:Client())
    a=project();del a['backup_save']
    assert asyncio.run(server._construction_project('execute_project',a))['complete']
    assert [x[0] for x in calls]==['get_game_state','get_validation_state','save_game','execute_project']
    assert calls[-1][1]['backup_save']==calls[-2][1]['slot']
    names={t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {'execute_project','resume_project','get_project','cancel_project'}<=names
