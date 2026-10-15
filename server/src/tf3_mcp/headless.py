"""Opt-in resource or native userdata ingress; existing UI/log validators and replies.

Bounded mode preindexes files; demand mode creates them after startup. Explicit userdata mode
reuses a generation-specific mailbox. No GUI automation, automatic fallback, automatic reload
or unknown-outcome retry.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from .ui_log import UiLogRequests

TAG = "[TNJ_HEADLESS_V1]"
_workflow_locks = ContextVar('tf3_workflow_locks', default=())


@contextmanager
def public_lock(directory):
    """Same nonblocking process lock used by scripts.batch_warehouses.batch_lock."""
    path = Path(directory) / "warehouse_batch.lock"
    key = (os.getpid(), str(path.resolve()))
    # A recovery workflow holds the OS lock across awaits. Its own to_thread
    # requests inherit this context; unrelated tasks/processes still take the
    # nonblocking OS lock. Do not spawn concurrent writers inside this context.
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None  # asyncio.to_thread inherits the lease context
    for lease in _workflow_locks.get():
        if lease['key'] == key and lease['active']:
            if task is not None and task is not lease['task']:
                raise RuntimeError('Concurrent child writer cannot inherit a workflow lock')
            yield
            return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0"); handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def workflow_lock(directory):
    """Explicit async workflow lease; ordinary public_lock stays non-reentrant."""
    key = (os.getpid(), str((Path(directory) / 'warehouse_batch.lock').resolve()))
    if any(lease['key'] == key and lease['active'] for lease in _workflow_locks.get()):
        raise RuntimeError('Workflow already active in this context')
    with public_lock(directory):
        try:
            task = asyncio.current_task()
        except RuntimeError:
            task = None
        lease = dict(key=key, task=task, active=True)
        token = _workflow_locks.set((*_workflow_locks.get(), lease))
        try:
            yield
        finally:
            lease['active'] = False
            _workflow_locks.reset(token)


def atomic(path, data):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temp.open("wb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)


class HeadlessRequests:
    def __init__(self, directory: Path, mod: Path):
        self.directory, self.mod = Path(directory), Path(mod)
        self.log = self.directory.parent / "crash_dump/stdout.txt"
        self.ledger = self.directory / "headless_requests.json"

    def _load(self):
        if not self.ledger.exists():
            return {"version": 1, "requests": {}, "pending": None}
        value = json.loads(self.ledger.read_text(encoding="utf-8"))
        if value.get("version") != 1:
            raise ValueError("Unknown headless ledger version")
        return value

    def _save(self, value):
        atomic(self.ledger, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))

    def _save_path(self, slot):
        from .ui_log import validate_save_arguments
        validate_save_arguments('save_game', {'slot': slot})
        folder = self.directory.parent / 'save'
        path = folder / (slot + '.sav')
        if folder.is_symlink() or path.is_symlink():
            raise ValueError('Save symlinks are not supported')
        return path

    @staticmethod
    def _signature(path):
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        if not path.is_file():
            raise ValueError('Save target is not a regular file')
        return dict(size=stat.st_size, mtimeNs=stat.st_mtime_ns, inode=stat.st_ino)

    def _verify_save(self, row):
        response = row['nativeResponse']
        elapsed = max(0, time.time() - row['created'])
        pending = dict(id=row['id'], status='timeout_unknown' if elapsed >= 120 else 'pending',
                       phase='verifying_save_file', retryAllowed=False, elapsedSeconds=round(elapsed, 2))
        result = response.get('result', {})
        if (not response['ok'] or result.get('requested') is not True
                or result.get('slot') != row['saveSlot'] or result.get('session') != row['session']):
            return dict(pending, status='timeout_unknown', phase='native_save_outcome_unknown', nativeResponse=response)
        path = self._save_path(row['saveSlot'])
        current = self._signature(path)
        if not current or current['size'] <= 0 or current == row['saveBefore']:
            row.pop('saveCandidate', None); row.pop('saveStableSince', None)
            return pending
        if row.get('saveCandidate') != current:
            row['saveCandidate'] = current
            row['saveStableSince'] = time.time()
            return pending
        if time.time() - row['saveStableSince'] < 1:
            return pending
        # Require the same live session after the write; an old/new map's file is not proof.
        live = self.status()['receiver']
        if live['session'] != row['session'] or live['generation'] != row['generation']:
            raise ValueError('Session changed during save verification; do not replay')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if self._signature(path) != current:
            row.pop('saveCandidate', None); row.pop('saveStableSince', None)
            return pending
        row['saveVerification'] = dict(path=str(path), signature=current, sha256=digest.hexdigest(),
                                       stableSeconds=time.time() - row['saveStableSince'], reloadVerified=False)
        row['response'] = dict(response, result=dict(result, verified=True,
                                verification='new_nonempty_stable_file', file=row['saveVerification']))
        return dict(status='received', response=row['response'])

    def _archive(self, ledger):
        # Keep the hot ledger bounded, retaining immutable per-request evidence
        # on disk. Never evict an unresolved request or its dispatch intent.
        excess = len(ledger["requests"]) - 256
        if excess <= 0:
            return
        history = self.directory / "headless_history"
        history.mkdir(exist_ok=True)
        for request_id, record in list(ledger["requests"].items()):
            if excess <= 0:
                break
            if "response" not in record or ledger.get("pending") == request_id or ledger.get('loadVerification') == request_id:
                continue
            destination = history / (request_id + ".json")
            data = json.dumps(record, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if destination.exists() and destination.read_bytes() != data:
                raise ValueError("Conflicting archived request; stop without overwriting evidence")
            if not destination.exists():
                atomic(destination, data)
            del ledger["requests"][request_id]
            excess -= 1

    def status(self):
        # Keep only a bounded, complete-line log tail. Native stdout timestamps
        # do not provide the request identity; the session/generation do.
        with self.log.open("rb") as f:
            f.seek(max(0, self.log.stat().st_size - 2 * 1024 * 1024))
            lines = f.read().decode("utf-8", errors="replace").splitlines(keepends=True)
        latest = None
        for line in lines:
            if not line.endswith("\n"):
                continue
            if "Game is ready" in line or "[tf3_mcp_bridge] started in gui state" in line:
                latest = None
            if TAG in line:
                latest = json.loads(line.split(TAG, 1)[1])
        if latest is None:
            raise ValueError("No live headless receiver; install and load the diagnostic mod")
        generation = latest.get("generation", "")
        if not re.fullmatch(r"[0-9a-f]{32}", generation):
            raise ValueError("Invalid receiver generation")
        userdata = latest.get('mode') == 'userdata'
        demand = latest.get("mode") in ("demand", "userdata")
        if latest.get("mode", "bounded") not in ("bounded", "demand", "userdata"):
            raise ValueError("Unknown receiver mode")
        if type(latest.get("slot")) is not int or not 1 <= latest["slot"] <= (2**53-1 if demand else 1024):
            raise ValueError("Invalid receiver slot")
        if userdata and (latest.get('userdataVersion') != 1 or latest.get('userdataDirectory') != 'mod_presets'
                or latest.get('filename') != 'tnj_mcp_' + generation + '_request.preset.lua'):
            raise ValueError('Invalid userdata mailbox identity')
        if demand and not userdata and not re.fullmatch(r"s[a-zA-Z0-9_]+_[0-9]+\.lua", latest.get("filename", "")):
            raise ValueError("Invalid demand resource filename")
        age = time.time() - latest["utc"]
        if not 0 <= age <= 5:
            raise ValueError("Headless heartbeat stale; no dispatch")
        ledger = self._load()
        return {"receiver": latest, "ageSeconds": age,
                "pending": ledger.get("pending"), "sessionTransition": ledger.get('sessionTransition'), "loadVerification": ledger.get('loadVerification'), "bounded": not demand,
                "nativeCacheReclamationVerified": False}

    def isolate_previous_save(self, request_id, expected_session):
        """Explicit new-session recovery for a save only; never infer its outcome.

        Retains the original intent and permanently quarantines its save slot.
        Only identity reads are enabled until verify_session_transition succeeds.
        Not a generic pending reset: world mutations and loads are excluded.
        """
        with public_lock(self.directory):
            ledger = self._load()
            live = self.status()['receiver']
            row = ledger['requests'].get(request_id, {})
            if (ledger.get('sessionTransition') or ledger.get('loadVerification')
                    or ledger.get('pending') != request_id or row.get('kind') != 'save'
                    or row.get('command') != 'save_game' or not row.get('saveSlot')
                    or not row.get('session') or row['session'] == expected_session
                    or live['session'] != expected_session or live['status'] != 'ready'
                    or live.get('mode') != 'demand' or 'response' in row):
                raise ValueError('Only an unresolved save from a different session can be isolated')
            transition = dict(requestId=request_id, previousSession=row['session'],
                              session=expected_session, generation=live['generation'],
                              started=time.time(), outcome='unknown', retryAllowed=False)
            row['sessionIsolation'] = transition.copy()
            row['status'] = 'previous_session_save_unknown'
            ledger.setdefault('quarantinedSaveSlots', {})[row['saveSlot']] = request_id
            ledger['sessionTransition'] = transition
            ledger['pending'] = None
            self._save(ledger)
            return transition

    def isolate_previous_state_read(self, request_id, expected_session):
        """Explicit isolation of an old, argument-free state read, never a retry.

        Keep its unknown outcome and exact publication. World writes remain gated
        by the existing three-read session transition verification.
        """
        with public_lock(self.directory):
            ledger = self._load()
            live = self.status()['receiver']
            row = ledger['requests'].get(request_id, {})
            if (not re.fullmatch(r'[0-9a-f]{32}', request_id)
                    or ledger.get('sessionTransition') or ledger.get('loadVerification')
                    or ledger.get('pending') != request_id
                    or row.get('id') != request_id or row.get('kind') != 'read'
                    or row.get('command') != 'get_game_state'
                    or row.get('input') != request_id + ' get_game_state'
                    or row.get('status') != 'published' or not row.get('session')
                    or row['session'] == expected_session or live['session'] != expected_session
                    or live['status'] != 'ready' or live.get('mode') != 'demand'
                    or any(k in row for k in ('response', 'reconciliation', 'sessionIsolation'))):
                raise ValueError('Only an unresolved argument-free state read from a previous session can be isolated')
            filename = 's' + re.sub('[^a-zA-Z0-9]', '_', row['session']) + '_' + str(row['slot']) + '.lua'
            payload = (self.mod / 'headless' / row['generation'] / filename).read_bytes()
            if not re.fullmatch(rb'return "(?:\\[0-9]{3})+"\n', payload):
                raise ValueError('Unrecognized original publication')
            envelope = json.loads(bytes(int(n) for n in re.findall(rb'\\([0-9]{3})', payload)))
            if envelope != {k: row[k] for k in ('session', 'generation', 'slot', 'expires', 'kind', 'input')}:
                raise ValueError('Original publication differs from durable state read')
            transition = dict(requestId=request_id, previousSession=row['session'],
                              session=expected_session, generation=live['generation'],
                              started=time.time(), outcome='unknown', retryAllowed=False,
                              kind='previous_session_state_read',
                              publishedPayloadSha256=hashlib.sha256(payload).hexdigest())
            row['sessionIsolation'] = transition.copy()
            row['status'] = 'previous_session_state_read_unknown'
            ledger['sessionTransition'] = transition
            ledger['pending'] = None
            self._save(ledger)
            return transition

    def rebind_state_read_transition(self, expected_previous_session, expected_session):
        """Move an unfinished read-isolation gate to a freshly loaded receiver.

        No writes are unlocked; every intervening request must be terminal.
        """
        with public_lock(self.directory):
            ledger = self._load()
            transition = ledger.get('sessionTransition')
            live = self.status()['receiver']
            if (not transition or transition.get('kind') != 'previous_session_state_read'
                    or ledger.get('pending') or ledger.get('loadVerification')
                    or transition['session'] != expected_previous_session
                    or expected_previous_session == expected_session
                    or live['session'] != expected_session or live['status'] != 'ready'):
                raise ValueError('Fresh receiver and resolved state-read transition required')
            origin = ledger['requests'].get(transition['requestId'], {})
            if origin.get('status') != 'previous_session_state_read_unknown':
                raise ValueError('Original unknown state read must remain isolated')
            for row in ledger['requests'].values():
                if (row.get('session') == expected_previous_session
                        and row.get('created', 0) >= transition['started']
                        and 'response' not in row and 'reconciliation' not in row):
                    raise ValueError('Intervening request outcome remains unresolved')
            ledger.setdefault('sessionTransitionHistory', []).append(transition.copy())
            transition = dict(transition, session=expected_session,
                              generation=live['generation'], started=time.time())
            ledger['sessionTransition'] = transition
            origin['sessionIsolation'] = transition.copy()
            self._save(ledger)
            return transition

    def verify_session_transition(self, expected_session):
        """Unlock only after durable, fresh native identity/pending reads."""
        with public_lock(self.directory):
            ledger = self._load()
            transition = ledger.get('sessionTransition')
            live = self.status()['receiver']
            if (not transition or ledger.get('pending') or ledger.get('loadVerification')
                    or transition['session'] != expected_session or live['session'] != expected_session
                    or live['generation'] != transition['generation'] or live['status'] != 'ready'):
                raise ValueError('Session transition identity or pending mismatch')
            evidence = {}
            for command in ('get_game_state', 'get_map_info', 'get_validation_state'):
                rows = [r for r in ledger['requests'].values()
                        if r.get('command') == command and r.get('session') == expected_session
                        and r.get('generation') == live['generation']
                        and r.get('created', 0) >= transition['started']
                        and 0 <= time.time() - r.get('created', 0) <= 60
                        and r.get('response', {}).get('ok') is True
                        and r['response'].get('id') == r.get('id')
                        and r['response'].get('cmd') == command]
                if not rows:
                    raise ValueError('Fresh independent read required: ' + command)
                evidence[command] = max(rows, key=lambda r: r['created'])
            state = evidence['get_game_state']['response']['result']
            world = evidence['get_map_info']['response']['result']
            validation = evidence['get_validation_state']['response']['result']
            # This audited native response omits nil-valued Lua fields, including pending.
            pending_known = ('pending' in validation or
                             validation.get('capabilityRevision') == 'consolidated-20261011-v40')
            if (validation.get('session') != expected_session or not pending_known
                    or validation.get('pending') or state.get('player') is None
                    or state.get('world') is None or not isinstance(world, dict) or not world):
                raise ValueError('Native identity or pending remains unknown')
            proof = dict(transition, verifiedAt=time.time(), player=state['player'], world=state['world'],
                         mapDigest=hashlib.sha256(json.dumps(world, sort_keys=True).encode()).hexdigest(),
                         evidenceRequests={k: v['id'] for k, v in evidence.items()})
            ledger['requests'][transition['requestId']]['sessionIsolation'] = proof
            ledger['sessionTransition'] = None
            self._save(ledger)
            return proof

    def send(self, command, arguments=None, *, kind="read", expected_session=None):
        with public_lock(self.directory):
            ledger = self._load()
            if ledger.get("pending"):
                raise ValueError("Previous request unresolved; read its result, never resubmit")
            transition = ledger.get('sessionTransition')
            identity_kinds = {'get_game_state': 'read', 'get_map_info': 'read', 'get_validation_state': 'build'}
            # Native validation is read-only but uses the extended build dispatcher.
            if transition and (identity_kinds.get(command) != kind
                               or expected_session != transition['session']):
                raise ValueError('Session transition permits only independent identity reads')
            if kind in ('save', 'load') and (arguments or {}).get('slot') in ledger.get('quarantinedSaveSlots', {}):
                raise ValueError('Previous-session unknown save slot is quarantined; never replay or load it')
            if ledger.get('loadVerification') and not (kind == 'read' or command == 'get_validation_state'):
                raise ValueError('Loaded session requires independent readback; writes blocked')
            self._archive(ledger)
            if len(ledger["requests"]) >= 4096:
                raise ValueError("Unresolved ledger bound reached; reconcile before new work")
            reader = UiLogRequests()
            if kind == "read":
                ticket = reader.prepare(self.log, command, arguments)
            elif kind == "build":
                ticket = reader.prepare_build(self.log, command, arguments or {})
            elif kind == 'save':
                ticket = reader.prepare_save(self.log, command, arguments)
            elif kind == 'load':
                ticket = reader.prepare_load(self.log, command, arguments)
            else:
                raise ValueError("Unsupported request kind")
            if kind in ('build', 'save', 'load') and not expected_session:
                raise ValueError("Operations require an independently verified current session")
            # Wait for a fresh ready window rather than racing a nearly expired slot.
            deadline = time.monotonic() + 6
            while True:
                status = self.status(); row = status["receiver"]
                if row["status"] == "ready" and status["ageSeconds"] < 1.25:
                    break
                if row["status"] in ("stopped", "exhausted") or time.monotonic() >= deadline:
                    raise ValueError("No fresh unconsumed slot; nothing submitted")
                time.sleep(.05)
            if expected_session is not None and row["session"] != expected_session:
                raise ValueError("Session changed; invalidate previous IDs and previews")
            # Old loaded receivers do not advertise limits and only accept 512.
            # Check before intent/slot publication, even if the host allows more.
            if command == 'get_town_cargo_supply' and row.get('townCargoSupplyVersion') != 2:
                raise ValueError('Loaded receiver lacks town cargo supply v2; nothing dispatched')
            if (command == 'get_town_cargo_supply' and arguments.get('include_passengers')
                    and row.get('townPassengerSupplyVersion') != 1):
                raise ValueError('Loaded receiver lacks town passenger supply v1; nothing dispatched')
            if command == 'get_industry_bonuses' and row.get('industryBonusesVersion') != 1:
                raise ValueError('Loaded receiver lacks industry bonuses v1; nothing submitted')
            if command == 'reconcile_assignment_rejection' and row.get('assignmentReconciliationVersion') != 1:
                raise ValueError('Loaded receiver lacks assignment reconciliation v1; nothing dispatched')
            if command == 'get_notifications' and row.get('notificationsVersion') != 1:
                raise ValueError('Loaded receiver lacks notifications v1; nothing submitted')
            if (command == 'build_water_facility' and arguments.get('kind') == 'harbor'
                    and row.get('waterHarborLayoutVersion') != 1):
                raise ValueError('Loaded receiver lacks small/large harbor layouts; nothing submitted')
            if command in {'preview_depot_removal', 'commit_depot_removal', 'get_depot_removal_operation'}:
                if row.get('depotRemovalVersion') != 1:
                    raise ValueError('Loaded receiver lacks depot removal v1; nothing submitted')
                if command == 'commit_depot_removal':
                    # Require fresh, unchanged save evidence from this host/session;
                    # a user-supplied filename is not proof of a completed backup.
                    saved = [r for r in ledger['requests'].values()
                             if r.get('saveSlot') == arguments['backup_save']
                             and r.get('kind') == 'save'
                             and r.get('session') == row['session']
                             and r.get('generation') == row['generation']
                             and isinstance(r.get('saveVerification'), dict)
                             and r.get('response', {}).get('result', {}).get('verified') is True]
                    if not saved:
                        raise ValueError('Verified current-session backup required; nothing submitted')
                    backup = max(saved, key=lambda r: r['created'])
                    if not 0 <= time.time() - backup['created'] <= 120:
                        raise ValueError('Backup is not recent; nothing submitted')
                    evidence = backup['saveVerification']
                    path = self._save_path(arguments['backup_save'])
                    if (self._signature(path) != evidence['signature']
                            or hashlib.sha256(path.read_bytes()).hexdigest() != evidence['sha256']
                            or self._signature(path) != evidence['signature']):
                        raise ValueError('Backup changed since verification; nothing submitted')
            limits = row.get('inputLimits', {'default': 512})
            if command in {'get_network_template', 'list_road_structures', 'preview_road_graph',
                           'commit_road_graph', 'get_road_graph_operation'} and limits.get('preview_road_graph') != 8192:
                raise ValueError('Loaded receiver lacks v35 road graph capability; reload the installed receiver first; nothing submitted')
            if command == 'preview_road_graph':
                graph = arguments['graph']
                special = (not graph['edges'] or any('junction' in n or 'crossing_resource' in n
                           or any(k in n.get('split', {}) for k in ('preserve_objects', 'allow_structure'))
                           for n in graph['nodes']))
                if special and row.get('roadGraphVersion') not in (37, 38, 39, 40):
                    raise ValueError('Loaded receiver lacks v37 special road graph capability; nothing submitted')
                advanced = any(any(k in n.get('split', {}) for k in ('preserve_crossings', 'preserve_tunnel_chain'))
                               or any(k in n.get('junction', {}) for k in ('blocked_turns', 'crosswalk_edges'))
                               for n in graph['nodes'])
                if advanced and row.get('roadGraphVersion') != 40:
                    raise ValueError('Loaded receiver lacks v40 preservation capability; nothing submitted')
            if command == 'reset_operation_quota' and row.get('operationQuotaVersion') != 1:
                raise ValueError('Loaded receiver lacks quota reset support; nothing submitted')
            limit = limits.get(command, limits.get('default', 512))
            if type(limit) is not int or not 1 <= limit <= 8192:
                raise ValueError('Invalid receiver input limit; nothing submitted')
            if len(ticket['input'].encode('utf-8')) > limit:
                raise ValueError(f'Loaded receiver accepts {limit} bytes for {command}; nothing submitted')
            save_before = None
            load_evidence = None
            if kind == 'load':
                from .headless_load import prepare
                load_evidence = prepare(self, ledger, row, arguments)
            if kind == 'save':
                if row.get('saveGameAvailable') is not True:
                    raise ValueError('Loaded receiver does not support headless saves; load the updated mod')
                save_before = self._signature(self._save_path(arguments['slot']))
                if save_before is not None and not arguments.get('overwrite', False):
                    raise ValueError('Save already exists; explicit overwrite=true required')
            userdata = row.get('mode') == 'userdata'
            demand = row.get("mode") in ("demand", "userdata")
            if not demand and any(x["generation"] == row["generation"] and x["session"] != row["session"]
                   for x in ledger["requests"].values()):
                raise ValueError("Generation already used by another session; install fresh slots, never recycle")
            reader.read(ticket["id"])  # rejects reload/log replacement during window selection
            path = (self.directory.parent / 'mod_presets' / row['filename'] if userdata else
                    self.mod / "headless" / row["generation"] / (row['filename'] if demand else f'{row["slot"]}.lua'))
            if userdata:
                from .bridge import decode_message
                if path.parent.is_symlink() or path.is_symlink():
                    raise ValueError('Userdata mailbox symlinks are not supported')
                if path.exists():
                    previous = decode_message(path.read_text(encoding='utf-8'))
                    previous_id = previous.get('input', '').split(' ', 1)[0] if isinstance(previous, dict) else ''
                    terminal = ledger['requests'].get(previous_id, {})
                    if (not isinstance(previous, dict) or previous.get('generation') != row['generation']
                            or not ('response' in terminal or 'reconciliation' in terminal)
                            or any(previous.get(k) != terminal.get(k) for k in
                                   ('generation','session','slot','input','expires','kind'))):
                        raise ValueError('Existing userdata mailbox has no matching terminal receipt')
            elif (demand and path.exists()) or (not demand and path.read_bytes() != b'return ""\n'):
                raise ValueError("Slot is not empty; never overwrite a request")
            if any(x["generation"] == row["generation"] and x["session"] == row["session"] and x["slot"] == row["slot"]
                   for x in ledger["requests"].values()):
                raise ValueError("Slot already reserved in durable ledger")
            key = row['generation'] + '|' + row['session']
            high_water = ledger.setdefault('highWater', {})
            if row['slot'] <= high_water.get(key, 0):
                raise ValueError("Slot already consumed/reserved; no replay after archival")
            envelope = dict(session=row["session"], generation=row["generation"],
                            slot=row["slot"], expires=row["due"] + (20 if demand else 2),
                            kind=kind, input=ticket["input"])
            encoded = json.dumps(envelope, separators=(",", ":"), ensure_ascii=True)
            if len(encoded.encode('utf-8')) > 16384:
                raise ValueError('Headless envelope exceeds receiver limit; nothing submitted')
            # Lua decimal byte escapes avoid executing interpolation/long-bracket data.
            payload = ('return "' + ''.join('\\%03d' % c for c in encoded.encode('utf-8')) + '"\n').encode('ascii')
            if userdata:
                from .bridge import encode_message
                payload = encode_message(envelope).encode('utf-8')
            _, inode, offset, cmd, anchor, _ = reader.pending[ticket["id"]]
            record = dict(envelope, id=ticket["id"], command=cmd, inode=inode,
                          offset=offset, anchor=anchor.hex(), created=time.time(), status="intent")
            if userdata:
                record['transport'] = 'userdata'
                record['publicationSha256'] = hashlib.sha256(payload).hexdigest()
            if kind == 'save':
                record.update(saveSlot=arguments['slot'], saveBefore=save_before)
            if kind == 'load':
                record.update(load_evidence)
            ledger["requests"][ticket["id"]] = record
            ledger["pending"] = ticket["id"]
            high_water[key] = row['slot']
            self._save(ledger)  # fsync intent BEFORE publishing, even on later failure
            atomic(path, payload)
            record["status"] = "published"
            self._save(ledger)
            return {"id": ticket["id"], "status": "published", "session": row["session"],
                    "slot": row["slot"], "retryAllowed": False}

    def read(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r'[0-9a-f]{32}', request_id):
            raise ValueError("Invalid request ID")
        with public_lock(self.directory):
            ledger = self._load()
            row = ledger["requests"].get(request_id)
            if row is None:
                archived = self.directory / 'headless_history' / (request_id + '.json')
                if not archived.is_file():
                    raise ValueError("Unknown durable request ID")
                row = json.loads(archived.read_text(encoding='utf-8'))
                if row.get('id') != request_id or row.get('response', {}).get('id') != request_id:
                    raise ValueError("Archived response identity mismatch")
            if "response" in row:
                return {"status": "received", "response": row["response"]}
            if 'sessionIsolation' in row:
                return dict(status='timeout_unknown', id=request_id, retryAllowed=False,
                            phase=('previous_session_state_read_isolated' if row.get('kind') == 'read'
                                   else 'previous_session_save_isolated'), isolation=row['sessionIsolation'])
            if 'reconciliation' in row:
                return dict(status='rejected', id=request_id, retryAllowed=False,
                            reconciliation=row['reconciliation'])
            from .headless_recovery import native_input_rejection
            rejection = native_input_rejection(self, row)
            if rejection:
                row['reconciliation'] = rejection
                row['status'] = 'rejected_before_dispatch'
                if ledger['pending'] == request_id:
                    ledger['pending'] = None
                self._save(ledger)
                return dict(status='rejected', id=request_id, retryAllowed=False,
                            reconciliation=rejection)
            reader = UiLogRequests()
            reader.pending[request_id] = (self.log, row["inode"], row["offset"], row["command"],
                bytes.fromhex(row["anchor"]), time.monotonic() - max(0, time.time() - row["created"]))
            result = reader.read(request_id, allow_load_transition=row['kind'] == 'load')
            if result["status"] == "received":
                if row['kind'] == 'load':
                    from .headless_load import observe
                    result = observe(self, row, result['response'])
                    if result['status'] != 'received':
                        self._save(ledger)
                        return result
                    ledger['loadVerification'] = request_id
                if row['kind'] == 'save':
                    row['nativeResponse'] = result['response']
                    result = self._verify_save(row)
                    if result['status'] != 'received':
                        self._save(ledger)
                        return result
                row["response"] = result["response"]
                row["status"] = "received"
                # Engine maintains its own unresolved-commit latch independently.
                if ledger["pending"] == request_id:
                    ledger["pending"] = None
                self._archive(ledger)
                self._save(ledger)
            return result

    def verify_load(self, request_id):
        from .headless_load import verify
        with public_lock(self.directory):
            return verify(self, self._load(), request_id)

    def reconcile_legacy_input_rejection(self, request_id, receiver_source, *, apply=False):
        """Explicit evidence audit; never fabricate a native response or replay."""
        from .headless_recovery import legacy_input_rejection
        with public_lock(self.directory):
            ledger = self._load()
            row = ledger['requests'].get(request_id)
            if not row:
                raise ValueError('Unknown request')
            if 'reconciliation' in row:
                return row['reconciliation']
            if ledger.get('pending') != request_id or 'response' in row:
                raise ValueError('Only the current unresolved request can be reconciled')
            evidence = legacy_input_rejection(self, row, Path(receiver_source))
            if apply:
                row['reconciliation'] = evidence
                row['status'] = 'rejected_before_dispatch'
                ledger['pending'] = None
                self._save(ledger)
            return dict(evidence, applied=apply)

    def reconcile_legacy_quota_rejection(self, request_id, receiver_source, *, apply=False):
        """Audit a pinned old pre-dispatch rejection; retain intent and evidence."""
        from .headless_recovery import legacy_quota_rejection
        with public_lock(self.directory):
            ledger = self._load()
            row = ledger['requests'].get(request_id)
            if not row:
                raise ValueError('Unknown request')
            if 'reconciliation' in row:
                return row['reconciliation']
            if ledger.get('pending') != request_id or 'response' in row:
                raise ValueError('Only the current unresolved request can be reconciled')
            evidence = legacy_quota_rejection(self, row, Path(receiver_source))
            if apply:
                row['reconciliation'] = evidence
                row['status'] = 'rejected_before_dispatch'
                ledger['pending'] = None
                self._save(ledger)
            return dict(evidence, applied=apply)
