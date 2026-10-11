import hashlib
import json
import asyncio

import pytest

from test_headless import host, GEN
from test_e2e import SCRIPT
from test_warehouses import warehouse_game
from tf3_mcp.headless import HeadlessRequests, TAG
from tf3_mcp import headless_recovery
from tf3_mcp.headless_client import HeadlessClient, HeadlessRequestRejected
from test_channel_migration import Requests


def test_client_reports_known_rejection_without_polling_or_retry():
    requests = Requests()
    requests.outcome = 'rejected'
    with pytest.raises(HeadlessRequestRejected, match='rejected before dispatch'):
        asyncio.run(HeadlessClient(requests, 0).call('get_game_state'))
    assert len(requests.calls) == 1


def long_line_args():
    return {'line': 700, 'stops': [dict(source_index=i, station=0, terminal=0,
                                     loads=[0], max_load=1, force_unload=False, extra_wait=0)
                                 for i in range(7)]}


@pytest.mark.parametrize('advertised', [False, True])
def test_host_checks_loaded_receiver_before_publication(host, advertised):
    if advertised:
        row = json.loads(host.log.read_text().split(TAG)[1])
        row['inputLimits'] = {'default': 512, 'preview_line_edit': 8192}
        host.log.write_text(TAG + json.dumps(row) + '\n')
        ticket = host.send('preview_line_edit', long_line_args(), kind='build', expected_session='session')
        assert len(host._load()['requests'][ticket['id']]['input'].encode()) == 808
    else:
        with pytest.raises(ValueError, match='512 bytes'):
            host.send('preview_line_edit', long_line_args(), kind='build', expected_session='session')
        assert not host.ledger.exists()
        assert (host.mod / 'headless' / GEN / '1.lua').read_bytes() == b'return ""\n'


@pytest.mark.parametrize('command,size,rejected', [
    ('get_validation_state', 512, False), ('get_validation_state', 513, True),
    ('preview_line_edit', 810, False), ('preview_line_edit', 8192, False),
    ('preview_line_edit', 8193, True),
])
def test_native_input_boundaries_and_next_request(warehouse_game, command, size, rejected):
    lua, _ = warehouse_game
    lua.execute('''
      headlessNow=1; os.clock=function()return headlessNow end
      payload=""; forwarded=nil
      resolveutil={loadfile=function(path)return function()return payload end end}
      api.cmd.makeScriptingSendEventCmd=function(script,id,name,param)return {param=param} end
      api.cmd.sendCommand=function(cmd)forwarded=cmd end
    ''')
    text = SCRIPT.read_text(encoding='utf-8').replace('local HEADLESS_GENERATION = "disabled"',
                  f'local HEADLESS_GENERATION = "{GEN}"').replace('local HEADLESS_ON_DEMAND = false',
                                                                             'local HEADLESS_ON_DEMAND = true')
    script = lua.execute(text)
    rows = []
    lua.globals().debugPrint = lambda s: rows.append(json.loads(s.split(TAG, 1)[1])) if TAG in s else None
    tick = lambda: script['guiUpdate'](None, None, None)
    tick()
    assert rows[-1]['inputLimits']['preview_line_edit'] == 8192
    args = long_line_args() if command == 'preview_line_edit' else {}
    text = 'b' * 32 + ' ' + command + ' ' + json.dumps(args, separators=(',', ':'))
    text += ' ' * (size - len(text.encode()))
    assert len(text.encode()) == size
    def submit(text):
        row = rows[-1]
        lua.globals().payload = json.dumps(dict(generation=GEN, session=row['session'], slot=row['slot'],
                                                expires=row['due'] + 20, kind='build', input=text))
        lua.globals().headlessNow = row['due']
        lua.globals().forwarded = None
        tick()
    submit(text)
    assert (lua.globals().forwarded is None) == rejected
    assert any(r['status'] == 'rejected' for r in rows) == rejected
    assert rows[-1]['status'] == 'ready' and rows[-1]['slot'] == 2
    if rejected:
        receipt = next(r for r in rows if r['status'] == 'rejected')
        assert receipt['dispatchAttempted'] is False and receipt['inputBytes'] == size
    submit('c' * 32 + ' get_validation_state {}')
    assert lua.globals().forwarded is not None
    assert rows[-1]['status'] == 'ready' and rows[-1]['slot'] == 3


def test_native_rejection_persists_across_restart_without_fake_success(host):
    ticket = host.send('get_game_state')
    ledger = host._load()
    row = ledger['requests'][ticket['id']]
    # Simulate an older/mismatched publisher sending an oversized request.
    row['input'] += ' ' * (513 - len(row['input']))
    host._save(ledger)
    rejection = dict(generation=GEN, session='session', slot=1, status='rejected', id=ticket['id'],
                     command='get_game_state', reason='input_too_large', dispatchAttempted=False,
                     inputBytes=len(row['input'].encode()), inputLimit=512)
    with host.log.open('a') as stream:
        stream.write(TAG + json.dumps(rejection) + '\n')
    result = host.read(ticket['id'])
    assert result['status'] == 'rejected' and not result['retryAllowed']
    assert 'response' not in result
    assert host._load()['pending'] is None
    restarted = HeadlessRequests(host.directory, host.mod)
    assert restarted.read(ticket['id']) == result
    assert restarted._load()['requests'][ticket['id']]['input'] == row['input']


def legacy_fixture(host, monkeypatch):
    heartbeat = json.loads(host.log.read_text().split(TAG)[1])
    heartbeat.update(mode='demand', filename='ssession_1.lua', inputLimits={'default': 512, 'preview_line_edit': 8192})
    host.log.write_text(TAG + json.dumps(heartbeat) + '\n')
    ticket = host.send('preview_line_edit', long_line_args(), kind='build', expected_session='session')
    source = host.mod / 'legacy.lua'
    source.write_text('exact audited fixture')
    monkeypatch.setattr(headless_recovery, 'LEGACY_SOURCE_SHA256', hashlib.sha256(source.read_bytes()).hexdigest())
    stopped = dict(generation=GEN, session='session', slot=1, status='stopped',
                   error='[string "/tnj_tf3_ai_bridge/content/tf3_mcp_bridge/bridge.script.lua"]:7215: Invalid request input')
    new = dict(heartbeat, session='new', filename='snew_1.lua')
    with host.log.open('a') as stream:
        stream.write(TAG + json.dumps(stopped) + '\n[tf3_mcp_bridge] started in gui state\n' + TAG + json.dumps(new) + '\n')
    return ticket['id'], source


def test_explicit_legacy_audit_retains_evidence_and_never_replays(host, monkeypatch):
    request, source = legacy_fixture(host, monkeypatch)
    before = host.ledger.read_bytes()
    audit = host.reconcile_legacy_input_rejection(request, source)
    assert not audit['applied'] and audit['dispatchAttempted'] is False
    assert host.ledger.read_bytes() == before
    audit = host.reconcile_legacy_input_rejection(request, source, apply=True)
    assert audit['applied']
    record = host._load()['requests'][request]
    assert host._load()['pending'] is None and 'response' not in record
    assert record['status'] == 'rejected_before_dispatch' and record['input']
    assert HeadlessRequests(host.directory, host.mod).read(request)['status'] == 'rejected'


@pytest.mark.parametrize('damage', ['source', 'publication', 'anchor', 'dispatch', 'response', 'wrong_stop'])
def test_legacy_recovery_refuses_ambiguous_evidence(host, monkeypatch, damage):
    request, source = legacy_fixture(host, monkeypatch)
    before = host.ledger.read_bytes()
    if damage == 'source':
        source.write_text('different')
    elif damage == 'publication':
        (host.mod / 'headless' / GEN / 'ssession_1.lua').write_bytes(b'return ""\n')
    elif damage == 'anchor':
        host.log.write_text('rewritten\n' + host.log.read_text())
    elif damage == 'wrong_stop':
        host.log.write_text(host.log.read_text().replace(':7215:', ':7216:'))
    else:
        with host.log.open('a') as stream:
            stream.write((TAG + json.dumps(dict(generation=GEN, session='session', slot=1, status='consumed'))
                          if damage == 'dispatch' else '[TNJ_UI_READ_V1] id=' + request + ' part=1') + '\n')
    with pytest.raises(ValueError):
        host.reconcile_legacy_input_rejection(request, source, apply=True)
    assert host.ledger.read_bytes() == before
