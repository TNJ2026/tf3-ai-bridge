"""Bounded, opt-in recovery outside the game process.

No daemon, synthetic receipts, pending reset, mutation replay or speed restore.
Adapters must provide fresh native observations; callbacks are trusted local
integration code, not instructions read from game data.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from .no_gui import atomic, workflow_lock


class RecoveryBlocked(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def file_digest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RecoveryBlocked('Checkpoint must be an existing regular file')
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    after = path.stat()
    if before.st_size <= 0 or (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size, after.st_mtime_ns, after.st_ino):
        raise RecoveryBlocked('Checkpoint empty or changed while hashing')
    return {'sha256': h.hexdigest(), 'size': after.st_size}


def map_key(world):
    """Complete native map response, stable across renaming and industry growth."""
    towns = world.get('towns')
    if any(type(world.get(k)) not in (int, float) or not math.isfinite(world[k]) or world[k] <= 0
           for k in ('width', 'height')):
        raise RecoveryBlocked('Unknown map dimensions')
    if not isinstance(towns, list) or not towns or world.get('truncated'):
        raise RecoveryBlocked('Complete city inventory required')
    points = []
    ids = set()
    for town in towns:
        if type(town.get('id')) is not int or town['id'] in ids:
            raise RecoveryBlocked('Invalid/duplicate city identity')
        ids.add(town['id'])
        point = [town['position'][axis] for axis in ('x', 'y')]
        if not all(type(n) in (int, float) and math.isfinite(n) for n in point):
            raise RecoveryBlocked('Invalid city coordinates')
        points.append(point)
    if len({tuple(p) for p in points}) != len(points):
        raise RecoveryBlocked('Duplicate city positions')
    return digest({'width': world['width'], 'height': world['height'], 'towns': sorted(points)})


def world_signature(world):
    data = dict(world)
    for key in ('towns', 'industries'):
        rows = world.get(key)
        if not isinstance(rows, list) or any(type(r.get('id')) is not int for r in rows):
            raise RecoveryBlocked('Incomplete native map inventory')
        if len({r['id'] for r in rows}) != len(rows):
            raise RecoveryBlocked('Duplicate native map entity')
        data[key] = sorted(rows, key=lambda r: r['id'])
    return digest(data)


def validate_snapshot(value):
    for field in ('session', 'generation', 'capabilityRevision'):
        if not isinstance(value.get(field), str) or not value[field]:
            raise RecoveryBlocked('Missing native identity: ' + field)
    if 'pending' not in value or value['pending']:
        raise RecoveryBlocked('Unresolved host/engine request; preserve original evidence')
    state = value['state']
    if state.get('speedup') != 0:
        raise RecoveryBlocked('Recovery requires a paused simulation')
    if type(state.get('player')) is not int or type(state.get('gameTime')) not in (int, float):
        raise RecoveryBlocked('Missing player/game time')
    if not math.isfinite(state['gameTime']):
        raise RecoveryBlocked('Invalid game time')
    if not value.get('audit'):
        raise RecoveryBlocked('Explicit native object/line/stock audit required')
    map_key(value['world'])
    world_signature(value['world'])


def equivalent(before, after, *, reloaded=False):
    validate_snapshot(before)
    validate_snapshot(after)
    if map_key(before['world']) != map_key(after['world']):
        raise RecoveryBlocked('Different map')
    if world_signature(before['world']) != world_signature(after['world']):
        raise RecoveryBlocked('Native map objects differ from checkpoint')
    for key in ('generation', 'capabilityRevision'):
        if before[key] != after[key]:
            raise RecoveryBlocked('Loaded implementation changed; separate migration required')
    for key in ('player', 'gameTime'):
        if before['state'][key] != after['state'][key]:
            raise RecoveryBlocked('Checkpoint player/time mismatch')
    if before['audit'] != after['audit']:
        raise RecoveryBlocked('Native checkpoint audit mismatch')
    if reloaded:
        if before['session'] == after['session']:
            raise RecoveryBlocked('New loaded session not observed')
    elif before['session'] != after['session']:
        raise RecoveryBlocked('Session changed during operation')


def classify(observation):
    """A stale heartbeat alone never proves a crash or authorizes a restart."""
    if observation.get('identityVerified') is not True:
        return 'unknown_process'
    if observation.get('process') == 'exited':
        return 'process_exited'
    if observation.get('process') != 'running':
        return 'unknown_process'
    if observation.get('connected') is not True:
        return 'bridge_unavailable'
    if observation.get('pending'):
        return 'unresolved_request'
    return 'connected'


class RecoveryRuntime:
    """All public async methods serialize against the existing batch lock.

    adapter: snapshot(), save(slot), observe(), launch(checkpoint), save_path(slot).
    launch starts an absent process with a separately configured, pinned bootstrap
    command. It never kills a live process or clears the transport's pending lock.
    """
    def __init__(self, adapter, directory, lock_directory, *, clock=time.time):
        self.adapter = adapter
        self.directory, self.lock_directory = Path(directory), Path(lock_directory)
        self.path = self.directory / 'recovery.json'
        self.clock = clock

    def read(self):
        if not self.path.exists():
            return {'schema': 1, 'checkpoints': {}, 'operations': {}, 'incidents': {},
                    'quarantinedPlans': [], 'launches': 0, 'monitorEnabled': False}
        state = json.loads(self.path.read_text(encoding='utf-8'))
        if state.get('schema') != 1:
            raise RecoveryBlocked('Unsupported recovery journal')
        return state

    def write(self, state):
        self.directory.mkdir(parents=True, exist_ok=True)
        atomic(self.path, json.dumps(state, ensure_ascii=True, allow_nan=False,
                                    indent=2).encode('utf-8'))

    def _idle(self, state):
        if any(c['status'] != 'verified' for c in state['checkpoints'].values()):
            raise RecoveryBlocked('Previous save outcome unknown; no duplicate save or mutation')
        if any(i['status'] not in ('recovered_paused',) for i in state['incidents'].values()):
            raise RecoveryBlocked('Recovery incident requires completion or investigation')
        if any(o['status'] not in ('verified', 'verified_after_recovery', 'rolled_back')
               for o in state['operations'].values()):
            raise RecoveryBlocked('Unknown/quarantined operation requires investigation')

    async def checkpoint(self):
        """Create an independent, non-overwritten pre-operation native save."""
        with workflow_lock(self.lock_directory):
            state = self.read()
            self._idle(state)
            before = await self.adapter.snapshot()
            validate_snapshot(before)
            previous = state.get('lastSnapshot')
            if previous and (map_key(previous['world']) != map_key(before['world'])
                    or previous['state']['player'] != before['state']['player']
                    or previous['session'] != before['session']):
                raise RecoveryBlocked('Journal belongs to another map/session; reconcile first')
            ident = uuid.uuid4().hex
            slot = 'tf3_recovery_before_' + ident
            record = {'id': ident, 'slot': slot, 'status': 'save_intent',
                      'createdAt': self.clock(), 'baseline': before,
                      'path': str(self.adapter.save_path(slot))}
            if Path(record['path']).exists():
                raise RecoveryBlocked('Independent backup already exists')
            state['checkpoints'][ident] = record
            self.write(state)  # durable intent before any game mutation
            try:
                record['receipt'] = await self.adapter.save(slot)
                if record['receipt'].get('verified') is not True:
                    raise RecoveryBlocked('Native save file not verified stable')
                record['file'] = file_digest(record['path'])
                after = await self.adapter.snapshot()
                equivalent(before, after)
                record['status'] = 'verified'
                state['activeCheckpoint'] = ident
                state['lastSnapshot'] = after
            except BaseException as exc:
                record.update(status='save_unknown', error=str(exc))
                self.write(state)
                raise
            self.write(state)
            return record

    async def execute(self, operation_id, plan, prepare, submit, verify):
        """Integrate an authorized operation; never replays any existing ID.

        prepare obtains a fresh native preview. submit receives it exactly once.
        verify performs independent native readback and returns {verified: True,
        ...evidence}. Native callbacks alone are not accepted as readback.
        """
        if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 160:
            raise ValueError('Explicit operation ID required')
        plan_hash = digest(plan)
        with workflow_lock(self.lock_directory):
            state = self.read()
            if operation_id in state['operations']:
                old = state['operations'][operation_id]
                if old['planDigest'] != plan_hash:
                    raise RecoveryBlocked('Operation ID reused for a different plan')
                return old
            self._idle(state)
            if plan_hash in state['quarantinedPlans']:
                raise RecoveryBlocked('Plan quarantined; no retry under another ID')
            cp = state['checkpoints'][state['activeCheckpoint']]
            if cp['status'] != 'verified' or file_digest(cp['path']) != cp['file']:
                raise RecoveryBlocked('Invalid checkpoint')
            now = await self.adapter.snapshot()
            equivalent(state['lastSnapshot'], now)
            prepared = await prepare()
            # Read again after preview; preparation must not mutate the world.
            equivalent(now, await self.adapter.snapshot())
            operation = {'id': operation_id, 'planDigest': plan_hash, 'plan': plan,
                         'checkpoint': cp['id'], 'session': now['session'],
                         'status': 'intent', 'startedAt': self.clock(), 'prepared': prepared}
            state['operations'][operation_id] = operation
            self.write(state)
            try:
                operation['result'] = await submit(prepared)
                operation['status'] = 'returned'
                self.write(state)
                evidence = await verify(operation['result'])
                operation['readback'] = evidence
                if evidence.get('verified') is not True:
                    raise RecoveryBlocked('Independent operation readback failed')
                after = await self.adapter.snapshot()
                validate_snapshot(after)
                for key in ('session', 'generation', 'capabilityRevision'):
                    if now[key] != after[key]:
                        raise RecoveryBlocked('Identity changed during mutation')
                if (map_key(now['world']) != map_key(after['world']) or
                        now['state']['player'] != after['state']['player'] or
                        now['state']['gameTime'] != after['state']['gameTime']):
                    raise RecoveryBlocked('Map/player/time changed during mutation')
                operation['status'] = 'verified'
                state['lastSnapshot'] = after
            except BaseException as exc:
                operation.update(status='unknown', error=str(exc))
                if plan_hash not in state['quarantinedPlans']:
                    state['quarantinedPlans'].append(plan_hash)
                self.write(state)
                raise
            self.write(state)
            return operation

    async def reconcile(self, operation_id, inspect):
        """Read-only, explicit integration audit after recovery; never retries.

        inspect(operation, fresh_snapshot) must resolve objects anew and return
        outcome=applied|absent plus nonempty evidence. Absence permits a NEW plan,
        not replay of the old ID/token. The suspect plan stays quarantined.
        """
        with workflow_lock(self.lock_directory):
            state = self.read()
            if not any(i['status'] == 'recovered_paused' for i in state['incidents'].values()):
                raise RecoveryBlocked('No verified recovery to reconcile')
            operation = state['operations'][operation_id]
            if operation['status'] != 'requires_reconciliation':
                raise RecoveryBlocked('Operation is not awaiting recovery reconciliation')
            before = await self.adapter.snapshot()
            equivalent(state['lastSnapshot'], before)
            evidence = await inspect(operation, before)
            if evidence.get('outcome') not in ('applied', 'absent') or not evidence.get('evidence'):
                raise RecoveryBlocked('Unknown operation outcome; retain original journal')
            equivalent(before, await self.adapter.snapshot())
            operation['recoveryAudit'] = evidence
            operation['status'] = 'verified_after_recovery' if evidence['outcome'] == 'applied' else 'rolled_back'
            self.write(state)
            return operation

    async def recover_once(self, incident_id, *, allow_launch=False, max_lost_game_time=0,
                           max_launches=1, startup_timeout=180, allow_unknown_loss=False):
        """One bounded step, intended for the existing scheduler; no sleeps/daemon.

        Authorization is checked again for any new launch. Unknown submissions
        remain unknown even after rollback; recovery only returns readyToReplan.
        """
        if not isinstance(incident_id, str) or not 1 <= len(incident_id) <= 160:
            raise ValueError('Explicit incident ID required')
        if (type(max_launches) is not int or not 1 <= max_launches <= 3 or
                type(max_lost_game_time) not in (int, float) or not math.isfinite(max_lost_game_time)
                or max_lost_game_time < 0 or not 1 <= startup_timeout <= 600):
            raise ValueError('Invalid bounded recovery policy')
        with workflow_lock(self.lock_directory):
            state = self.read()
            incident = state['incidents'].get(incident_id)
            if incident and incident['status'] in ('blocked', 'recovered_paused'):
                return incident
            if incident is None:
                if any(i['status'] != 'recovered_paused' for i in state['incidents'].values()):
                    raise RecoveryBlocked('Another unresolved incident; do not bypass by changing ID')
                incident = {'id': incident_id, 'status': 'observing', 'createdAt': self.clock()}
                state['incidents'][incident_id] = incident
                self.write(state)
            try:
                if self.clock() < incident['createdAt']:
                    raise RecoveryBlocked('Wall clock regressed during recovery')
                observation = await self.adapter.observe()
                incident['observation'] = observation
                incident['classification'] = classify(observation)
                if 'evidence' not in incident:
                    incident['evidence'] = await self.adapter.capture_evidence(incident_id)
                    self.write(state)
                if incident['status'] in ('launch_intent', 'awaiting_receiver'):
                    # Includes a controller crash between intent and dispatch:
                    # absence of a receipt never authorizes another launch.
                    if self.clock() > incident['deadline']:
                        raise RecoveryBlocked('Recovery startup expired; launch outcome not replayed')
                    if incident['classification'] != 'connected':
                        self.write(state)
                        return incident
                    cp = state['checkpoints'][incident['checkpoint']]
                    if file_digest(cp['path']) != cp['file']:
                        raise RecoveryBlocked('Checkpoint changed during recovery')
                    after = await self.adapter.snapshot()
                    equivalent(cp['baseline'], after, reloaded=True)
                    # The native audit is repeated on a later round to avoid
                    # accepting a transient startup response as a stable load.
                    if 'firstReadback' not in incident:
                        incident.update(firstReadback=after, firstReadbackAt=self.clock())
                        self.write(state)
                        return incident
                    if self.clock() - incident['firstReadbackAt'] < 1:
                        self.write(state)
                        return incident
                    equivalent(incident['firstReadback'], after)
                    incident.update(status='recovered_paused', readback=after,
                                    readyToReplan=True, operationalVerified=False,
                                    replayAllowed=False, monitorEnabled=False)
                    state['lastSnapshot'] = after
                    for op in state['operations'].values():
                        op['beforeRecoveryStatus'] = op['status']
                        op['status'] = 'requires_reconciliation'
                    # Original results/sessions remain intact; no operation is
                    # assumed retained just because loading the save succeeded.
                else:
                    if incident['classification'] != 'process_exited':
                        raise RecoveryBlocked('Only confirmed process exit permits automatic launch')
                    if allow_launch is not True:
                        raise RecoveryBlocked('Launch/rollback not authorized')
                    if state['launches'] >= max_launches:
                        raise RecoveryBlocked('Persistent restart limit reached')
                    cp = state['checkpoints'][state['activeCheckpoint']]
                    if cp['status'] != 'verified' or file_digest(cp['path']) != cp['file']:
                        raise RecoveryBlocked('No intact verified checkpoint')
                    last = state['lastSnapshot']
                    # Only paused, recorded baselines have a bounded rollback
                    # window. A game that ran unobserved must not be rolled back.
                    validate_snapshot(last)
                    if observation.get('lastSession') != last['session']:
                        raise RecoveryBlocked('Exited process not bound to the last game session')
                    observed_time = observation.get('lastGameTime')
                    known_time = type(observed_time) in (int, float) and math.isfinite(observed_time)
                    if not known_time and allow_unknown_loss is not True:
                        raise RecoveryBlocked('Last game time unknown; rollback loss cannot be bounded')
                    loss = observed_time - cp['baseline']['state']['gameTime'] if known_time else None
                    if loss is not None and (loss < 0 or loss > max_lost_game_time):
                        raise RecoveryBlocked('Rollback exceeds permitted game time')
                    await self.adapter.preflight_launch(cp)
                    incident.update(status='launch_intent', checkpoint=cp['id'],
                                    deadline=self.clock() + startup_timeout, lostGameTime=loss,
                                    unknownLossAuthorized=allow_unknown_loss is True)
                    state['launches'] += 1
                    for op in state['operations'].values():
                        if op['status'] != 'verified' and op['planDigest'] not in state['quarantinedPlans']:
                            state['quarantinedPlans'].append(op['planDigest'])
                    self.write(state)
                    incident['launchReceipt'] = await self.adapter.launch(cp)
                    incident['status'] = 'awaiting_receiver'
            except Exception as exc:
                incident.update(status='blocked', error=str(exc), readyToReplan=False, replayAllowed=False)
            self.write(state)
            return incident
