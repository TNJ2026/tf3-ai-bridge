import json
import pytest
from test_headless import host, GEN
from tf3_mcp.headless import TAG

OLD = '1' * 32

def seed(host):
    host._save({'version': 1, 'pending': OLD, 'requests': {OLD: {
        'id': OLD, 'kind': 'save', 'command': 'save_game', 'session': 'old',
        'generation': GEN, 'saveSlot': 'old_backup', 'status': 'published'}}})
    host.log.write_text(TAG + json.dumps(dict(generation=GEN, session='new', slot=1,
        status='ready', utc=100, clock=10, due=11, mode='demand', filename='snew_1.lua'))+'\n')


def test_save_isolation_gates_and_preserves_unknown(host):
    seed(host)
    host.isolate_previous_save(OLD, 'new')
    assert host.read(OLD)['status'] == 'timeout_unknown'
    assert host._load()['requests'][OLD]['saveSlot'] == 'old_backup'
    with pytest.raises(ValueError, match='identity reads'):
        host.send('set_game_speed', {'speed': 0, 'expected_speed': 4}, kind='build', expected_session='new')
    with pytest.raises(ValueError, match='Fresh independent'):
        host.verify_session_transition('new')
    ticket = host.send('get_game_state', expected_session='new')
    assert ticket['status'] == 'published'
    assert host._load()['requests'][OLD]['status'] == 'previous_session_save_unknown'


@pytest.mark.parametrize('kind,command,session', [('build','commit_road','old'), ('load','load_game','old'), ('save','save_game','new')])
def test_other_operations_or_same_session_cannot_be_isolated(host, kind, command, session):
    seed(host)
    ledger=host._load(); ledger['requests'][OLD].update(kind=kind,command=command,session=session);host._save(ledger)
    before=host.ledger.read_bytes()
    with pytest.raises(ValueError): host.isolate_previous_save(OLD,'new')
    assert host.ledger.read_bytes()==before


def test_transition_requires_native_pending_clear_and_quarantines_slot(host):
    seed(host);host.isolate_previous_save(OLD,'new')
    ledger=host._load()
    results={'get_game_state': {'player': 1,'world': 2}, 'get_map_info': {'towns': []},
             'get_validation_state': {'session': 'new','pending': 'unresolved'}}
    for i,(command,result) in enumerate(results.items(),2):
        key=str(i)*32
        ledger['requests'][key]=dict(id=key,command=command,session='new',generation=GEN,created=100.25,
            response=dict(id=key,cmd=command,ok=True,result=result))
    host._save(ledger)
    with pytest.raises(ValueError,match='Native identity'):host.verify_session_transition('new')
    ledger['requests']['4'*32]['response']['result']['pending']=None;host._save(ledger)
    proof=host.verify_session_transition('new')
    assert proof['outcome']=='unknown' and not proof['retryAllowed']
    assert host._load()['sessionTransition'] is None
    for kind,command in [('save','save_game'),('load','load_game')]:
        with pytest.raises(ValueError,match='quarantined'):
            host.send(command,{'slot':'old_backup'},kind=kind,expected_session='new')
