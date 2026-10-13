import asyncio
import copy
import json
from pathlib import Path

import pytest

from tf3_mcp.recovery_adapter import HeadlessRecoveryAdapter
from tf3_mcp.recovery_runtime import RecoveryBlocked, digest, file_digest


class Requests:
    def __init__(self, root):
        self.directory = root
        self.data = dict(receiver=dict(session='session', generation='gen', status='ready'),
                         ageSeconds=0, pending=None)
    def status(self): return copy.deepcopy(self.data)
    def _save_path(self, slot): return self.directory / (slot + '.sav')


class Client:
    def __init__(self):
        self.calls = []
        self.speed = 0
        self.pending = None
    async def bind(self, session): self.calls.append(('bind', session))
    async def call(self, command, arguments=None):
        self.calls.append((command, arguments))
        if command == 'get_game_state': return dict(player=1, gameTime=100, speedup=self.speed)
        if command == 'get_validation_state': return dict(session='session', capabilityRevision='v40', pending=self.pending)
        if command == 'get_map_info': return dict(width=100, height=100, industries=[], towns=[dict(id=1, position=dict(x=0,y=0))])
        if command == 'get_entity': return dict(components={'LINE': dict(stops=[2,3], noPath=False)})
        if command == 'save_game': return dict(verified=True, slot=arguments['slot'])
        raise AssertionError(command)


@pytest.fixture
def adapter(tmp_path):
    config = dict(gameExecutable=str(tmp_path / 'tf3.exe'), audit=[dict(name='line', command='get_entity',
                    arguments={'id': 1, 'components': ['LINE']}, fields=['components.LINE.stops'])])
    rows = [dict(pid=123, created='creation-1', executable=config['gameExecutable'])]
    obj = HeadlessRecoveryAdapter(Requests(tmp_path), tmp_path / 'recovery', config,
                                  process_query=lambda _: rows.copy())
    obj.client = Client()
    return obj, rows


def run(coro): return asyncio.run(coro)


def test_native_snapshot_binds_process_and_selects_fields(adapter):
    obj, rows = adapter
    out = run(obj.snapshot())
    assert out['audit'] == {'line': {'components.LINE.stops': [2,3]}}
    binding = json.loads(obj.binding_path.read_text())
    assert binding['process'] == rows[0] and binding['session'] == 'session'
    assert run(obj.save('unique')) == dict(verified=True, slot='unique')


@pytest.mark.parametrize('failure', ['pending', 'running', 'missing_field', 'no_process', 'engine_pending'])
def test_snapshot_refuses_incomplete_or_unstable_state(adapter, failure):
    obj, rows = adapter
    if failure == 'pending': obj.requests.data['pending'] = 'old'
    if failure == 'running': obj.client.speed = 4
    if failure == 'missing_field': obj.config['audit'][0]['fields'] = ['missing']
    if failure == 'no_process': rows.clear()
    if failure == 'engine_pending': obj.client.pending = 'native-old'
    with pytest.raises((RecoveryBlocked, KeyError)): run(obj.snapshot())
    assert not obj.binding_path.exists()


def test_exit_evidence_cannot_be_inferred_from_old_pause(adapter):
    obj, rows = adapter
    run(obj.snapshot())
    rows.clear()
    result = run(obj.observe())
    assert result['process'] == 'exited' and 'lastGameTime' not in result
    binding = json.loads(obj.binding_path.read_text())
    evidence = dict(process=binding['process'], session='session', source='native_final_game_time',
                    capturedAt=binding['capturedAt'], gameTime=100)
    (obj.directory / 'exit_evidence.json').write_text(json.dumps(evidence), encoding='utf-8')
    assert run(obj.observe())['lastGameTime'] == 100
    evidence['process']['pid'] = 999
    (obj.directory / 'exit_evidence.json').write_text(json.dumps(evidence), encoding='utf-8')
    assert 'lastGameTime' not in run(obj.observe())


def test_bootstrap_is_pinned_no_shell_and_receipt_does_not_claim_loaded(adapter, tmp_path, monkeypatch):
    obj, rows = adapter
    rows.clear()
    executable = tmp_path / 'validated-loader.exe'
    executable.write_bytes(b'test fixture, never executed')
    save = tmp_path / 'checkpoint.sav'
    save.write_bytes(b'save bytes')
    checkpoint = dict(path=str(save), file=file_digest(save))
    obj.config['bootstrap'] = dict(validated=True, argv=[str(executable), '{checkpoint}'],
                                    executableSha256=file_digest(executable)['sha256'])
    calls = []
    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return type('Process', (), {'pid': 555})()
    monkeypatch.setattr('tf3_mcp.recovery_adapter.subprocess.Popen', popen)
    result = run(obj.launch(checkpoint))
    assert result == dict(pid=555, argvDigest=digest([str(executable), str(save)]),
                          requested=True, loaded=False, verified=False)
    assert calls[0][1]['shell'] is False
    executable.write_bytes(b'changed')
    with pytest.raises(RecoveryBlocked, match='changed'): run(obj.launch(checkpoint))
    assert len(calls) == 1


def test_missing_bootstrap_never_guesses_game_switches(adapter, tmp_path):
    obj, rows = adapter
    rows.clear()
    with pytest.raises(RecoveryBlocked, match='No validated'): run(obj.preflight_launch({}))


def test_audit_cannot_execute_game_mutations(adapter):
    obj, _ = adapter
    obj.config['audit'][0]['command'] = 'eval'
    with pytest.raises(ValueError, match='audit'):
        HeadlessRecoveryAdapter(obj.requests, obj.directory, obj.config)


def test_diagnostics_preserve_raw_bytes_and_never_overwrite_originals(adapter):
    obj, _ = adapter
    run(obj.snapshot())
    original = obj.requests.directory / 'headless_requests.json'
    original.write_bytes(b'unknown request, non-UTF8 log: \xff')
    result = run(obj.capture_evidence('../not-a-path'))
    item = next(f for f in result['files'] if f['source'] == str(original))
    assert Path(item['captured']).read_bytes() == original.read_bytes()
    assert Path(item['captured']).resolve().is_relative_to(obj.directory.resolve())
    original.write_bytes(b'changed later')
    assert run(obj.capture_evidence('../not-a-path')) == result
    assert Path(item['captured']).read_bytes() != original.read_bytes()
