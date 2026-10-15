import json
import pytest
from test_headless import host, GEN
from tf3_mcp.headless import TAG


def seed_read(host):
    host.log.write_text(TAG + json.dumps(dict(generation=GEN, session='old', slot=1,
        status='ready', utc=100, clock=10, due=11, mode='demand', filename='sold_1.lua'))+'\n')
    ticket = host.send('get_game_state')
    host.log.write_text(TAG + json.dumps(dict(generation=GEN, session='new', slot=1,
        status='ready', utc=100, clock=10, due=11, mode='demand', filename='snew_1.lua'))+'\n')
    return ticket['id']


def test_unknown_read_is_preserved_and_writes_stay_blocked(host):
    key = seed_read(host)
    original = host._load()['requests'][key].copy()
    host.isolate_previous_state_read(key, 'new')
    result = host.read(key)
    assert result['status'] == 'timeout_unknown' and result['retryAllowed'] is False
    assert result['phase'] == 'previous_session_state_read_isolated'
    row = host._load()['requests'][key]
    for k, value in original.items():
        if k != 'status':
            assert row[k] == value
    with pytest.raises(ValueError, match='identity reads'):
        host.send('set_game_speed', {'speed': 0}, kind='build', expected_session='new')
    with pytest.raises(ValueError, match='Fresh independent'):
        host.verify_session_transition('new')
    assert host.send('get_game_state', expected_session='new')['id'] != key


@pytest.mark.parametrize('change', [
    {'kind': 'build'}, {'command': 'save_game'}, {'session': 'new'},
    {'input': 'unexpected'}, {'response': {}}, {'reconciliation': {}},
    {'expires': 999},
])
def test_nonmatching_requests_rejected_without_ledger_change(host, change):
    key = seed_read(host)
    ledger = host._load(); ledger['requests'][key].update(change); host._save(ledger)
    before = host.ledger.read_bytes()
    with pytest.raises(ValueError):
        host.isolate_previous_state_read(key, 'new')
    assert host.ledger.read_bytes() == before


def test_changed_payload_is_not_isolated(host):
    key = seed_read(host)
    (host.mod / 'headless' / GEN / 'sold_1.lua').write_text('return "changed"\n')
    before = host.ledger.read_bytes()
    with pytest.raises(ValueError):
        host.isolate_previous_state_read(key, 'new')
    assert host.ledger.read_bytes() == before


def test_rebind_preserves_gate_and_requires_terminal_intervening_requests(host):
    key = seed_read(host)
    host.isolate_previous_state_read(key, 'new')
    host.log.write_text(TAG + json.dumps(dict(generation='b'*32, session='third', slot=1,
        status='ready', utc=100, clock=10, due=11))+'\n')
    ledger = host._load()
    ledger['requests']['2'*32] = dict(session='new', created=100.25, status='published')
    host._save(ledger)
    before = host.ledger.read_bytes()
    with pytest.raises(ValueError, match='Intervening'):
        host.rebind_state_read_transition('new', 'third')
    assert host.ledger.read_bytes() == before
    ledger['requests']['2'*32]['reconciliation'] = {'retryAllowed': False}
    host._save(ledger)
    host.rebind_state_read_transition('new', 'third')
    assert host.read(key)['status'] == 'timeout_unknown'
    assert host._load()['sessionTransitionHistory'][0]['session'] == 'new'
    with pytest.raises(ValueError, match='identity reads'):
        host.send('set_game_speed', {'speed': 0}, kind='build', expected_session='third')
    with pytest.raises(ValueError):
        host.rebind_state_read_transition('new', 'third')
