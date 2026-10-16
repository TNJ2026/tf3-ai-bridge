"""Evidence-only input rejection recovery. No dispatch, replay or synthetic success."""
import hashlib
import json
import re

from .no_gui import TAG

# Exact installed image independently inspected for the 2026-10-10 incident.
# Its input assertion precedes ID reservation and every dispatcher call.
LEGACY_SOURCE_SHA256 = '3562b0f7fe4046a115b5593a9fa26a926bfc61c6ccb28ce04a25a3480d2fc71c'

# Independently audited installed image from the Panjin 2026-10-11 incident.
# uiBuild.forward returns this exact limit message before sendCommand.
QUOTA_SOURCE_SHA256 = '9b90889e66ed32c78ad3fe0e112fad215c75eecce675defcc7ffffbd24d3d8f1'


def legacy_quota_rejection(host, row, source):
    """Narrow evidence migration for a BUY rejected by the audited old GUI."""
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != QUOTA_SOURCE_SHA256:
        raise ValueError('Source is not the audited quota receiver image')
    if row['kind'] != 'build' or row['command'] != 'buy_vehicles' or not row['input'].startswith(row['id']+' buy_vehicles '):
        raise ValueError('Not an audited legacy quota purchase')
    filename = 's' + re.sub('[^a-zA-Z0-9]', '_', row['session']) + '_' + str(row['slot']) + '.lua'
    payload = (host.mod / 'no_gui' / row['generation'] / filename).read_bytes()
    if not re.fullmatch(rb'return "(?:\\[0-9]{3})+"\n', payload):
        raise ValueError('Unrecognized original publication')
    envelope = json.loads(bytes(int(n) for n in re.findall(rb'\\([0-9]{3})', payload)))
    if envelope != {k: row[k] for k in ('session', 'generation', 'slot', 'expires', 'kind', 'input')}:
        raise ValueError('Publication does not match durable request')
    data, lines = request_window(host, row)
    matches = matching_rows(lines, row)
    events = [item for item in matches if item.get('status') != 'ready']
    if [e.get('status') for e in events] != ['consumed', 'dispatched', 'stopped']:
        raise ValueError('Missing or conflicting quota stop sequence')
    if any('[TNJ_UI_READ_V1] id='+row['id'] in line for line in lines):
        raise ValueError('Native response exists; do not migrate rejection')
    if (any(e.get('id') != row['id'] for e in events[:2])
            or events[1].get('detail') != 'Session request limit reached'
            or not events[2].get('error', '').endswith(':8093: Dispatch failed or unknown: Session request limit reached')
            or '/tnj_tf3_ai_bridge/content/tf3_mcp_bridge/bridge.script.lua' not in events[2].get('error', '')):
        raise ValueError('Quota rejection identity or reason mismatch')
    current = host.status()['receiver']
    if current['status'] != 'ready' or current['session'] == row['session'] or current.get('operationQuotaVersion') != 1:
        raise ValueError('Fresh quota-v1 session required')
    return dict(kind='audited_legacy_quota_rejection', requestId=row['id'], engineDispatchAttempted=False,
                sourceSha256=source_hash, publishedPayloadSha256=hashlib.sha256(payload).hexdigest(),
                logWindowSha256=hashlib.sha256(data).hexdigest(), nativeEvents=events,
                recoverySession=current['session'], requiresFreshMapVerification=True, retryAllowed=False)


def request_window(host, row):
    with host.log.open('rb') as stream:
        stat = host.log.stat()
        if stat.st_ino != row['inode'] or not row['offset'] <= stat.st_size <= row['offset'] + 16 * 1024 * 1024:
            raise ValueError('Unverifiable original log window')
        anchor = bytes.fromhex(row['anchor'])
        stream.seek(row['offset'] - len(anchor))
        if stream.read(len(anchor)) != anchor:
            raise ValueError('Original log anchor changed')
        data = stream.read(16 * 1024 * 1024)
    # Native diagnostics can use the Windows code page. Decode protocol rows
    # strictly, but do not let unrelated diagnostics block a valid receipt.
    lines = []
    for raw in data.splitlines(keepends=True):
        if not raw.endswith(b'\n'):
            continue
        protocol = TAG.encode('ascii') in raw or b'[TNJ_UI_READ_V1]' in raw
        lines.append(raw.decode('utf-8', errors='strict' if protocol else 'replace'))
    return data, lines


def matching_rows(lines, row):
    matches = []
    for line in lines:
        if TAG not in line:
            continue
        item = json.loads(line.split(TAG, 1)[1])
        if all(item.get(k) == row[k] for k in ('session', 'generation', 'slot')):
            matches.append(item)
    return matches


def check_no_dispatch(lines, matches, row):
    if any(item.get('status') in ('consumed', 'dispatched') for item in matches):
        raise ValueError('Dispatch evidence exists; outcome must remain unresolved')
    if any('[TNJ_UI_READ_V1] id=' + row['id'] in line for line in lines):
        raise ValueError('Native response exists; use ordinary result verification')


def native_input_rejection(host, row):
    data, lines = request_window(host, row)
    matches = matching_rows(lines, row)
    rejected = [item for item in matches if item.get('status') == 'rejected']
    if not rejected:
        return None
    check_no_dispatch(lines, matches, row)
    if len(rejected) != 1:
        raise ValueError('Conflicting rejection records')
    item = rejected[0]
    limit = 8192 if row['command'] == 'preview_line_edit' else 512
    if (item.get('id') != row['id'] or item.get('command') != row['command']
            or item.get('reason') != 'input_too_large' or item.get('dispatchAttempted') is not False
            or item.get('inputBytes') != len(row['input'].encode('utf-8'))
            or item.get('inputLimit') != limit or item['inputBytes'] <= limit):
        raise ValueError('Rejection identity mismatch')
    return dict(kind='native_input_rejection', dispatchAttempted=False, nativeRecord=item,
                logWindowSha256=hashlib.sha256(data).hexdigest(), requestId=row['id'])


def legacy_input_rejection(host, row, source):
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != LEGACY_SOURCE_SHA256:
        raise ValueError('Source is not the audited legacy receiver image')
    size = len(row['input'].encode('utf-8'))
    if (row['kind'] != 'build' or row['command'] != 'preview_line_edit'
            or not 512 < size <= 8192 or not row['input'].startswith(row['id'] + ' preview_line_edit ')):
        raise ValueError('Request is not a legacy oversized line preview')
    # Compare the exact durable envelope with the original one-use published file.
    filename = 's' + re.sub('[^a-zA-Z0-9]', '_', row['session']) + '_' + str(row['slot']) + '.lua'
    payload = (host.mod / 'no_gui' / row['generation'] / filename).read_bytes()
    if not re.fullmatch(rb'return "(?:\\[0-9]{3})+"\n', payload):
        raise ValueError('Unrecognized original publication')
    envelope = json.loads(bytes(int(n) for n in re.findall(rb'\\([0-9]{3})', payload)))
    if envelope != {k: row[k] for k in ('session', 'generation', 'slot', 'expires', 'kind', 'input')}:
        raise ValueError('Publication does not match durable request')
    data, lines = request_window(host, row)
    matches = matching_rows(lines, row)
    check_no_dispatch(lines, matches, row)
    stopped = [item for item in matches if item.get('status') == 'stopped']
    if len(stopped) != 1 or not stopped[0].get('error', '').endswith(':7215: Invalid request input'):
        raise ValueError('Missing exact legacy pre-dispatch assertion')
    error = stopped[0]['error']
    if '/tnj_tf3_ai_bridge/content/tf3_mcp_bridge/bridge.script.lua' not in error:
        raise ValueError('Unexpected assertion source')
    current = host.status()['receiver']
    if current['status'] != 'ready' or current['session'] == row['session']:
        raise ValueError('A fresh ready session is required after the stopped receiver')
    return dict(kind='audited_legacy_input_rejection', requestId=row['id'],
                dispatchAttempted=False, inputBytes=size, sourceSha256=source_hash,
                publishedPayloadSha256=hashlib.sha256(payload).hexdigest(),
                logWindowSha256=hashlib.sha256(data).hexdigest(), nativeStop=stopped[0],
                recoverySession=current['session'], requiresFreshMapVerification=True)
