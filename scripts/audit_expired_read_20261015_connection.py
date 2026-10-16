"""Narrow evidence audit for one unconsumed read; never dispatches or replays."""
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server/src'))
from tf3_mcp.no_gui import NoGuiRequests, workflow_lock
from tf3_mcp.no_gui_recovery import request_window, matching_rows, check_no_dispatch

REQUEST = '0158b41b0eb547b783d01913645afc45'
SOURCE = 'c7408af676f2cd131b1a95afb4205c8dec5d2be271d8a30495b911235738073b'

def audit(host, row):
    assert row['id'] == REQUEST and row['kind'] == 'read'
    assert row['command'] == 'get_game_state' and row['input'] == REQUEST + ' get_game_state'
    assert 'response' not in row and 'reconciliation' not in row
    source = (host.mod / 'bridge.script.lua').read_bytes()
    assert hashlib.sha256(source).hexdigest() == SOURCE
    # Audited image checks expiry before ID reservation, consumption and dispatch.
    filename = 's' + re.sub('[^a-zA-Z0-9]', '_', row['session']) + '_' + str(row['slot']) + '.lua'
    payload = (host.mod / 'no_gui' / row['generation'] / filename).read_bytes()
    assert re.fullmatch(rb'return "(?:\\[0-9]{3})+"\n', payload)
    envelope = json.loads(bytes(int(n) for n in re.findall(rb'\\([0-9]{3})', payload)))
    assert envelope == {k: row[k] for k in ('session','generation','slot','expires','kind','input')}
    data, lines = request_window(host, row)
    matches = matching_rows(lines, row)
    check_no_dispatch(lines, matches, row)
    assert len(matches) >= 2 and all(x['status'] == 'ready' for x in matches)
    current = host.status()['receiver']
    assert current['status'] == 'ready' and current['mode'] == 'demand'
    assert all(current[k] == row[k] for k in ('session','generation','slot'))
    assert current['clock'] > row['expires'] + 5
    assert max(x['clock'] for x in matches) > row['expires'] + 5
    return dict(kind='expired_unconsumed_read_audit', requestId=row['id'],
                dispatchAttempted=False, retryAllowed=False, sourceSha256=SOURCE,
                logWindowSha256=hashlib.sha256(data).hexdigest(),
                payloadSha256=hashlib.sha256(payload).hexdigest(), receiver=current,
                scope='Only this get_game_state request; not a generic pending reset')

if __name__ == '__main__':
    host = NoGuiRequests(Path('D:/Program Files/Steam/userdata/1112836998/3493540/local/tf3_mcp'),
                           Path('C:/Users/Public/mod.io/10640/mods/6449979/content/tf3_mcp_bridge'))
    with workflow_lock(host.directory):
        ledger = host._load()
        assert ledger.get('pending') == REQUEST
        proof = audit(host, ledger['requests'][REQUEST])
        out = Path('output/mcp_connection_repair_168600debeb54768bdee07f3cb93a813/expired_second_read_audit.json')
        out.write_text(json.dumps(proof, indent=2), encoding='utf-8')
        if '--apply' in sys.argv:
            # Terminal evidence classification, retaining the original envelope
            # and publication forever. This request may never be replayed.
            backup = out.with_name('ledger_before_expired_read_reconciliation.json')
            with backup.open('x', encoding='utf-8') as stream:
                json.dump(ledger, stream, ensure_ascii=False, indent=2)
            row = ledger['requests'][REQUEST]
            row['reconciliation'] = proof
            row['status'] = 'rejected_before_dispatch'
            ledger['pending'] = None
            host._save(ledger)
            result = host.read(REQUEST)
            assert result['status'] == 'rejected' and result['retryAllowed'] is False
            proof['independentReadback'] = result
        print(json.dumps(proof, indent=2))
