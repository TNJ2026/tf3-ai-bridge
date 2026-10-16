"""Fault injection: crashes at intent boundaries, rollback and stale evidence."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from tf3_mcp.no_gui import public_lock, workflow_lock
from tf3_mcp.recovery_runtime import (RecoveryBlocked, RecoveryRuntime, classify,
                                     equivalent, file_digest, map_key)


def baseline():
    return dict(session='first', generation='installed-v1', capabilityRevision='v40', pending=None,
                state=dict(player=3, gameTime=100, speedup=0),
                world=dict(width=1000, height=1000,
                           towns=[dict(id=7, position=dict(x=1, y=2))], industries=[]),
                audit={'line': {'noPath': False, 'stops': [5, 6]}, 'stock': {'capacity': 500}})


class Adapter:
    def __init__(self, path):
        self.path = path
        self.current = baseline()
        self.saved = {}
        self.saves = self.launches = 0
        self.fail_save = self.fail_launch = False
        self.obs = dict(identityVerified=True, process='exited', connected=False,
                        lastSession='first', lastGameTime=100)

    async def snapshot(self):
        return copy.deepcopy(self.current)

    def save_path(self, slot):
        return self.path / (slot + '.sav')

    async def save(self, slot):
        self.saves += 1
        if self.fail_save:
            raise TimeoutError('native save unknown')
        self.save_path(slot).write_bytes(b'valid native save')
        self.saved[slot] = copy.deepcopy(self.current)
        return {'verified': True}

    async def observe(self):
        return copy.deepcopy(self.obs)

    async def capture_evidence(self, incident_id):
        return {'incident': incident_id, 'retained': True}

    async def preflight_launch(self, cp):
        if self.fail_launch:
            raise RecoveryBlocked('bootstrap unavailable')

    async def launch(self, cp):
        self.launches += 1
        self.current = copy.deepcopy(self.saved[cp['slot']])
        self.current['session'] = 'loaded'
        self.obs.update(process='running', connected=True)
        return {'requested': True}


@pytest.fixture
def system(tmp_path):
    adapter = Adapter(tmp_path)
    clock = [1000]
    runtime = RecoveryRuntime(adapter, tmp_path / 'journal', tmp_path / 'bridge', clock=lambda: clock[0])
    return runtime, adapter, clock


def run(coro):
    return asyncio.run(coro)


def finish(runtime, clock):
    assert run(runtime.recover_once('crash'))['status'] == 'awaiting_receiver'
    clock[0] += 2
    return run(runtime.recover_once('crash'))


def test_checkpoint_launch_revalidate_across_controller_restart(system):
    runtime, adapter, clock = system
    checkpoint = run(runtime.checkpoint())
    assert checkpoint['status'] == 'verified'
    assert Path(checkpoint['path']).exists()
    assert run(runtime.recover_once('crash', allow_launch=True))['status'] == 'awaiting_receiver'
    restarted = RecoveryRuntime(adapter, runtime.directory, runtime.lock_directory, clock=lambda: clock[0])
    result = finish(restarted, clock)
    assert result['status'] == 'recovered_paused'
    assert result['readyToReplan'] and not result['operationalVerified']
    assert not result['monitorEnabled'] and not result['replayAllowed']
    assert run(restarted.recover_once('crash', allow_launch=True)) == result
    assert adapter.launches == 1


@pytest.mark.parametrize('change,reason', [
    ({'process': 'running', 'connected': False}, 'Only confirmed'),
    ({'process': 'unknown'}, 'Only confirmed'),
    ({'identityVerified': False}, 'Only confirmed'),
    ({'lastSession': 'other'}, 'bound'),
    ({'lastGameTime': None}, 'unknown'),
    ({'lastGameTime': 101}, 'exceeds'),
    ({'lastGameTime': 99}, 'exceeds'),
])
def test_faults_do_not_authorize_restart(system, change, reason):
    runtime, adapter, _ = system
    run(runtime.checkpoint())
    adapter.obs.update(change)
    result = run(runtime.recover_once('crash', allow_launch=True))
    assert result['status'] == 'blocked' and reason in result['error']
    assert adapter.launches == 0
    with pytest.raises(RecoveryBlocked, match='Another unresolved'):
        run(runtime.recover_once('new-id', allow_launch=True))


def test_no_authorization_no_launch(system):
    runtime, adapter, _ = system
    run(runtime.checkpoint())
    assert run(runtime.recover_once('crash'))['status'] == 'blocked'
    assert adapter.launches == 0


def test_tampered_checkpoint_never_loaded(system):
    runtime, adapter, _ = system
    cp = run(runtime.checkpoint())
    Path(cp['path']).write_bytes(b'corrupted/replaced save')
    assert run(runtime.recover_once('crash', allow_launch=True))['status'] == 'blocked'
    assert adapter.launches == 0


def test_unknown_save_not_repeated(system):
    runtime, adapter, _ = system
    adapter.fail_save = True
    with pytest.raises(TimeoutError):
        run(runtime.checkpoint())
    with pytest.raises(RecoveryBlocked, match='save outcome'):
        run(runtime.checkpoint())
    assert adapter.saves == 1


@pytest.mark.parametrize('fault', ['same_session', 'map', 'version', 'time', 'pending', 'unpaused', 'audit', 'industry'])
def test_reload_requires_native_identity_and_object_audit(system, fault):
    runtime, adapter, _ = system
    run(runtime.checkpoint())
    run(runtime.recover_once('crash', allow_launch=True))
    if fault == 'same_session': adapter.current['session'] = 'first'
    if fault == 'map': adapter.current['world']['towns'][0]['position']['x'] = 99
    if fault == 'version': adapter.current['generation'] = 'different'
    if fault == 'time': adapter.current['state']['gameTime'] = 101
    if fault == 'pending': adapter.current['pending'] = 'old-request'
    if fault == 'unpaused': adapter.current['state']['speedup'] = 4
    if fault == 'audit': adapter.current['audit']['line']['stops'] = [9, 10]
    if fault == 'industry': adapter.current['world']['industries'] = [{'id': 88, 'fileName': 'different'}]
    result = run(runtime.recover_once('crash'))
    assert result['status'] == 'blocked'
    assert adapter.launches == 1


def test_crash_between_launch_intent_and_dispatch_never_replayed(system):
    runtime, adapter, clock = system
    run(runtime.checkpoint())
    async def fail(cp):
        raise asyncio.CancelledError()
    adapter.launch = fail
    with pytest.raises(asyncio.CancelledError):
        run(runtime.recover_once('crash', allow_launch=True))
    assert runtime.read()['incidents']['crash']['status'] == 'launch_intent'
    assert run(runtime.recover_once('crash', allow_launch=True))['status'] == 'launch_intent'
    clock[0] += 181
    assert run(runtime.recover_once('crash'))['status'] == 'blocked'
    assert runtime.read()['launches'] == 1


def test_unknown_mutation_reconcile_without_replay(system):
    runtime, adapter, clock = system
    run(runtime.checkpoint())
    calls = []
    async def prepare(): return {'preview_token': 'fresh'}
    async def submit(preview):
        calls.append(preview)
        raise TimeoutError('commit outcome unknown')
    async def verify(result): raise AssertionError('must not verify absent result')
    plan = {'type': 'build_warehouse', 'site': [1, 2]}
    with pytest.raises(TimeoutError):
        run(runtime.execute('build-1', plan, prepare, submit, verify))
    old = run(runtime.execute('build-1', plan, prepare, submit, verify))
    assert old['status'] == 'unknown' and len(calls) == 1
    with pytest.raises(RecoveryBlocked):
        run(runtime.execute('build-2', plan, prepare, submit, verify))
    run(runtime.recover_once('crash', allow_launch=True))
    finish(runtime, clock)
    async def inspect(op, snapshot):
        assert snapshot['session'] == 'loaded'
        return {'outcome': 'absent', 'evidence': {'nativeSiteSurvey': 'no warehouse'}}
    result = run(runtime.reconcile('build-1', inspect))
    assert result['status'] == 'rolled_back'
    assert result['error'] == 'commit outcome unknown'
    run(runtime.checkpoint())
    with pytest.raises(RecoveryBlocked, match='quarantined'):
        run(runtime.execute('build-3', plan, prepare, submit, verify))
    assert len(calls) == 1


def test_completed_operation_is_reaudited_after_rollback(system):
    runtime, adapter, clock = system
    run(runtime.checkpoint())
    async def prepare(): return {'token': 'current'}
    async def submit(preview):
        adapter.current['audit']['stock']['capacity'] = 1000
        return {'success': True}
    async def verify(result): return {'verified': True, 'capacity': 1000}
    assert run(runtime.execute('expand', {'capacity': 1000}, prepare, submit, verify))['status'] == 'verified'
    run(runtime.recover_once('crash', allow_launch=True))
    finish(runtime, clock)
    assert runtime.read()['operations']['expand']['status'] == 'requires_reconciliation'
    with pytest.raises(RecoveryBlocked): run(runtime.checkpoint())


def test_restart_budget_survives_new_incident_ids(system):
    runtime, adapter, clock = system
    run(runtime.checkpoint())
    run(runtime.recover_once('crash', allow_launch=True))
    finish(runtime, clock)
    adapter.obs.update(process='exited', connected=False, lastSession='loaded')
    assert run(runtime.recover_once('crash-2', allow_launch=True))['status'] == 'blocked'
    assert adapter.launches == 1


def test_no_callback_when_identity_changed(system):
    runtime, adapter, _ = system
    run(runtime.checkpoint())
    adapter.current['session'] = 'manual-reload'
    async def unexpected(*args): raise AssertionError('callback not allowed')
    with pytest.raises(RecoveryBlocked):
        run(runtime.execute('build', {}, unexpected, unexpected, unexpected))


def test_classification_and_incomplete_identity():
    assert classify({'connected': False}) == 'unknown_process'
    assert classify(dict(identityVerified=True, process='running', connected=False)) == 'bridge_unavailable'
    assert classify(dict(identityVerified=True, process='running', connected=True, pending='x')) == 'unresolved_request'
    a = baseline()
    b = copy.deepcopy(a)
    b['world']['towns'][0]['name'] = 'renamed'
    assert map_key(a['world']) == map_key(b['world'])
    b['world']['towns'].append(b['world']['towns'][0])
    with pytest.raises(RecoveryBlocked): map_key(b['world'])


def test_workflow_lock_reentrant_through_to_thread(tmp_path):
    async def work():
        with workflow_lock(tmp_path):
            def nested():
                with public_lock(tmp_path): return 'ok'
            assert await asyncio.to_thread(nested) == 'ok'
    run(work())


def test_independent_process_cannot_enter_workflow_lock(tmp_path):
    import os
    import subprocess
    import sys
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    code = 'from tf3_mcp.no_gui import public_lock\nimport sys\nwith public_lock(sys.argv[1]): pass\n'
    with workflow_lock(tmp_path):
        result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], env=env,
                                capture_output=True, timeout=10)
        assert result.returncode != 0
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], env=env,
                            capture_output=True, timeout=10)
    assert result.returncode == 0


def test_child_task_cannot_inherit_writer_permission(tmp_path):
    async def child():
        with public_lock(tmp_path):
            raise AssertionError('must not enter')
    async def work():
        with workflow_lock(tmp_path):
            with pytest.raises(RuntimeError, match='Concurrent child'):
                await asyncio.create_task(child())
    run(work())


def test_unknown_loss_requires_separate_explicit_policy(system):
    runtime, adapter, _ = system
    run(runtime.checkpoint())
    adapter.obs.pop('lastGameTime')
    result = run(runtime.recover_once('crash', allow_launch=True, allow_unknown_loss=True))
    assert result['status'] == 'awaiting_receiver'
    assert result['lostGameTime'] is None and result['unknownLossAuthorized'] is True
