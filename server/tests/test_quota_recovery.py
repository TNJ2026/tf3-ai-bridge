import hashlib
import json

import pytest

from test_no_gui import host, GEN
from tf3_mcp.no_gui import TAG
from tf3_mcp import no_gui_recovery


@pytest.mark.parametrize('fault', [None, 'source', 'payload', 'reply', 'reason', 'duplicate', 'id', 'old_session'])
def test_quota_recovery_requires_complete_pinned_evidence(host, monkeypatch, tmp_path, fault):
    ready = dict(generation=GEN, session='session', slot=1, status='ready', utc=100, clock=10,
                 due=11, mode='demand', filename='ssession_1.lua')
    host.log.write_text(TAG+json.dumps(ready)+'\n')
    ticket = host.send('buy_vehicles', dict(depot=42, model='bus.mdl', count=1), kind='build', expected_session='session')
    source = tmp_path/'old.lua';source.write_text('test audited fixture')
    monkeypatch.setattr(no_gui_recovery, 'QUOTA_SOURCE_SHA256', hashlib.sha256(source.read_bytes()).hexdigest())
    if fault=='source':source.write_text('different source')
    if fault=='payload':(host.mod/'no_gui'/GEN/'ssession_1.lua').write_text('return "different"\n')
    common = dict(session='session', generation=GEN, slot=1)
    events = [dict(common,status='consumed',id=ticket['id']),
              dict(common,status='dispatched',id=ticket['id'],detail='Session request limit reached'),
              dict(common,status='stopped',error='[string "D:/local/tnj_tf3_ai_bridge/content/tf3_mcp_bridge/bridge.script.lua"]:8093: Dispatch failed or unknown: Session request limit reached')]
    if fault=='reason':events[1]['detail']='Dispatch unknown; do not retry'
    if fault=='id':events[0]['id']='f'*32
    if fault=='duplicate':events.append(events[1])
    with host.log.open('a') as f:
        for e in events:f.write(TAG+json.dumps(e)+'\n')
        if fault=='reply':f.write('[TNJ_UI_READ_V1] id='+ticket['id']+' part=1 total=1 hex=00\n')
        f.write(TAG+json.dumps(dict(ready,session='session' if fault=='old_session' else 'new',operationQuotaVersion=1))+'\n')
    before = host.ledger.read_bytes()
    if fault:
        with pytest.raises(ValueError):host.reconcile_legacy_quota_rejection(ticket['id'], source, apply=True)
        assert host.ledger.read_bytes()==before
    else:
        preview = host.reconcile_legacy_quota_rejection(ticket['id'], source)
        assert not preview['applied'] and not preview['engineDispatchAttempted']
        assert host.ledger.read_bytes()==before
        assert host.reconcile_legacy_quota_rejection(ticket['id'], source, apply=True)['applied']
        ledger = host._load()
        assert ledger['pending'] is None and ledger['requests'][ticket['id']]['input']
        assert host.read(ticket['id'])['status']=='rejected'
        assert 'response' not in ledger['requests'][ticket['id']]  # no synthetic success
