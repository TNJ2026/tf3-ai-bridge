"""Explicit native load: verified local saves, durable intent, no retries or UI input."""
import hashlib
import json
import time


def authorize_installed_upgrade(host, request_id, evidence_path):
    """Bind an interrupted load to a proven pre-load deployment, never clear it."""
    from pathlib import Path
    import re
    from .headless import public_lock
    with public_lock(host.directory):
        ledger = host._load()
        row = ledger['requests'].get(request_id)
        if not row or row.get('kind') != 'load' or ledger.get('pending') != request_id:
            raise ValueError('An unresolved original load is required')
        path = Path(evidence_path)
        raw = path.read_bytes(); deployment = json.loads(raw)
        script = host.mod / 'bridge.script.lua'
        data = script.read_bytes()
        match = re.search(rb'local HEADLESS_GENERATION = "([a-f0-9]{32})"', data)
        live = host.status()
        generation = deployment.get('generation')
        if (deployment.get('status') != 'installed_requires_fresh_load'
                or Path(deployment.get('modContent', '')).resolve() != host.mod.resolve()
                or path.stat().st_mtime > row['created'] or script.stat().st_mtime > row['created']
                or hashlib.sha256(data).hexdigest() != deployment.get('installedSha256')
                or not match or match[1].decode() != generation
                or generation == row['generation']
                or live['receiver']['generation'] != generation
                or live['receiver']['session'] == row['session']
                or live['receiver']['status'] != 'ready' or live['ageSeconds'] > 5
                or live['receiver'].get('loadGameVersion') != 1):
            raise ValueError('Receiver upgrade is not proven by an unchanged pre-load deployment')
        verify_file(host, row['loadSlot'], row['loadFile'])
        verify_file(host, row['loadBackupSlot'], row['loadBackup'])
        evidence = dict(generation=generation, installedSha256=deployment['installedSha256'],
                        deploymentPath=str(path.resolve()), deploymentSha256=hashlib.sha256(raw).hexdigest())
        if row.get('loadReceiverUpgrade') not in (None, evidence):
            raise ValueError('Original upgrade evidence cannot be replaced')
        row['loadReceiverUpgrade'] = evidence
        host._save(ledger)
        return evidence


def verified_save(host, ledger, slot):
    rows = list(ledger['requests'].values())
    history = host.directory / 'headless_history'
    # The hot ledger retains the newest completed records. A matching verified
    # save there is authoritative; never scan unrelated history on this path.
    hot_match = any(r.get('kind') == 'save' and r.get('saveSlot') == slot
                    and r.get('response', {}).get('result', {}).get('verified') is True
                    and isinstance(r.get('saveVerification'), dict) for r in rows)
    if not hot_match and history.exists():
        for path in history.glob('*.json'):
            row = json.loads(path.read_text(encoding='utf-8'))
            if row.get('saveSlot') == slot:
                rows.append(row)
    candidates = [r for r in rows if r.get('kind') == 'save' and r.get('saveSlot') == slot
                  and r.get('response', {}).get('result', {}).get('verified') is True
                  and isinstance(r.get('saveVerification'), dict)]
    if not candidates:
        raise ValueError('Load requires a save previously verified by this channel')
    saved = max(candidates, key=lambda r: r['created'])
    verify_file(host, slot, saved['saveVerification'])
    return saved


def verify_file(host, slot, evidence):
    path = host._save_path(slot)
    if (host._signature(path) != evidence['signature'] or
            hashlib.sha256(path.read_bytes()).hexdigest() != evidence['sha256'] or
            host._signature(path) != evidence['signature']):
        raise ValueError('Load/save file changed since verification; nothing replayed')


def latest_read(ledger, command, session, *, after=0):
    rows = [r for r in ledger['requests'].values() if r.get('command') == command
            and r.get('session') == session and r.get('created', 0) >= after
            and r.get('response', {}).get('ok') is True]
    if not rows:
        raise ValueError('Independent native read required: ' + command)
    row = max(rows, key=lambda r: r['created'])
    return row, row['response']['result']


def prepare(host, ledger, receiver, arguments):
    if receiver.get('loadGameVersion') != 1 or receiver.get('loadGameAvailable') is not True:
        raise ValueError('Loaded receiver lacks native load v1; nothing submitted')
    session = receiver['session']
    _, state = latest_read(ledger, 'get_game_state', session, after=time.time()-10)
    _, validation = latest_read(ledger, 'get_validation_state', session, after=time.time()-10)
    if state.get('speedup') != 0 or validation.get('pending') or validation.get('session') != session:
        raise ValueError('Loading requires paused game and no native pending')
    target = verified_save(host, ledger, arguments['slot'])
    backup = verified_save(host, ledger, arguments['backup_save'])
    if (backup['session'] != session or backup['generation'] != receiver['generation']
            or not 0 <= time.time()-backup['created'] <= 120
            or backup['response']['result'].get('gameTime') != state.get('gameTime')):
        raise ValueError('Fresh verified backup of current paused progress required')
    return dict(loadSlot=arguments['slot'], loadFile=target['saveVerification'],
                loadExpected={k: target['response']['result'][k] for k in ('gameTime', 'player', 'world')
                              if k in target['response']['result']},
                loadBackup=backup['saveVerification'], loadBackupSlot=arguments['backup_save'])


def observe(host, row, response):
    from .headless_recovery import request_window, matching_rows
    _, lines = request_window(host, row)
    if any(r.get('status') == 'stopped' for r in matching_rows(lines, row)):
        raise ValueError('Native load receiver stopped with an error; preserve pending, never retry')
    result = response.get('result', {})
    pending = dict(status='timeout_unknown' if time.time()-row['created'] >= 180 else 'pending',
                   phase='awaiting_load_session', id=row['id'], retryAllowed=False)
    if (response.get('ok') is not True or result.get('requested') is not True
            or result.get('slot') != row['loadSlot'] or result.get('session') != row['session']):
        return dict(pending, status='timeout_unknown', phase='load_acknowledgement_mismatch')
    try:
        status = host.status()
    except ValueError:
        return pending  # No receiver during loading is expected; never resend.
    live = status['receiver']
    if (live['session'] == row['session'] or live['status'] != 'ready'
            or status['ageSeconds'] > 5):
        return pending
    expected_generation = row.get('loadReceiverUpgrade', {}).get('generation', row['generation'])
    if live['generation'] != expected_generation or live.get('loadGameVersion') != 1:
        raise ValueError('Unexpected receiver after load; preserve pending and inspect')
    verify_file(host, row['loadSlot'], row['loadFile'])
    verify_file(host, row['loadBackupSlot'], row['loadBackup'])
    row['loadObservedAt'] = time.time()
    return dict(status='received', response=dict(response, result=dict(result,
                newSession=live['session'], backupSlot=row['loadBackupSlot'], verified=False, reloadObserved=True,
                verification='native_readback_required')))


def verify(host, ledger, request_id):
    row = ledger['requests'].get(request_id)
    if not row or row.get('kind') != 'load':
        raise ValueError('Unknown load request')
    if row.get('response', {}).get('result', {}).get('verified') is True:
        return row['response']['result']
    if ledger.get('loadVerification') != request_id or ledger.get('pending'):
        raise ValueError('Load is not ready for independent readback')
    result = row['response']['result'];session = result['newSession']
    after = row['loadObservedAt']
    _, state = latest_read(ledger, 'get_game_state', session, after=after)
    _, world = latest_read(ledger, 'get_map_info', session, after=after)
    _, validation = latest_read(ledger, 'get_validation_state', session, after=after)
    status = host.status()
    if (status['receiver']['session'] != session or status['receiver']['status'] != 'ready'
            or status['ageSeconds'] > 5 or state.get('speedup') != 0
            or validation.get('session') != session or validation.get('pending')
            or any(state.get(k) != v for k, v in row['loadExpected'].items())):
        raise ValueError('Loaded state does not match the checkpoint; writes remain blocked')
    from .headless_client import HeadlessClient
    identity = dict(session=session, player=state['player'], world=state['world'],
                    mapDigest=HeadlessClient.map_digest(world))
    verify_file(host, row['loadSlot'], row['loadFile'])
    row['response']['result'] = dict(result, verified=True, verification='new_session_native_readback',
                                    identity=identity, state=state, checkpointFieldsVerified=sorted(row['loadExpected']),
                                    savedMapIdentityAvailable=False)
    ledger['loadVerification'] = None
    host._save(ledger)
    return row['response']['result']
