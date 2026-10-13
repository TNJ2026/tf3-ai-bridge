"""Quota rollover against the real Lua adapter with a mocked native engine."""
import asyncio
import json
import re

import pytest

from test_e2e import SCRIPT
from test_warehouses import warehouse_game
from test_headless import GEN, host
from test_channel_migration import Requests
from tf3_mcp.headless import TAG
from tf3_mcp.headless_client import HeadlessClient, HeadlessOutcomeUnknown, HeadlessRequestRejected
from tf3_mcp.ui_log import validate_build_arguments


class QuotaChannel:
    def __init__(self, lua):
        self.lua = lua
        lua.execute('''
            now=1;os.clock=function()return now end;payload=nil
            resolveutil={loadfile=function()return function()return payload end end}
            api.cmd.makeScriptingSendEventCmd=function(src,id,name,param)
                return {event=true,id=id,name=name,param=param}
            end
            local send=api.cmd.sendCommand
            api.cmd.sendCommand=function(cmd,cb)
                if cmd.event then forwarded=cmd else send(cmd,cb) end
            end
        ''')
        source = SCRIPT.read_text(encoding='utf-8').replace(
            'local HEADLESS_GENERATION = "disabled"', f'local HEADLESS_GENERATION = "{GEN}"').replace(
            'local HEADLESS_ON_DEMAND = false', 'local HEADLESS_ON_DEMAND = true')
        self.script = lua.execute(source)
        self.state = lua.execute('local s={v={}};function s:get()return self.v end;function s:set(v)self.v=v end;return s')
        lua.globals().quotaTestState = self.state
        self.events, self.output, self.rows = [], [], []
        lua.globals().print = lambda *v: self.output.append(' '.join(map(str, v)))
        lua.globals().debugPrint = lambda s: self.rows.append(json.loads(s.split(TAG, 1)[1])) if TAG in s else None
        self.script['guiUpdate'](None, None, None)
        self.serial = 100000

    def query(self, command, args=None):
        row = self.rows[-1]
        assert row['status'] == 'ready'
        self.serial += 1
        ident = f'{self.serial:032x}'
        self.output.clear()
        self.lua.globals().forwarded = None
        self.lua.globals().payload = json.dumps(dict(generation=GEN, session=row['session'],
            slot=row['slot'], expires=row['due']+20, kind='build',
            input=ident+' '+command+' '+json.dumps(args or {})))
        self.lua.globals().now = row['due']
        self.script['guiUpdate'](None, None, None)
        e = self.lua.globals().forwarded
        assert e is not None
        event = {k: e[k] for k in ('id', 'name', 'param')}
        self.events.append(event)
        self.script['handleEvent'](None, self.state, '', e['id'], e['name'], e['param'])
        pieces = [line.split('hex=', 1)[1] for line in self.output if 'id='+ident+' ' in line]
        assert pieces, self.output
        return json.loads(bytes.fromhex(''.join(pieces)))

    def quota(self):
        r = self.query('get_validation_state')
        assert r['ok'], r
        return r['result']['operationQuota']

    def reset(self, **override):
        q = self.quota()
        args = dict(expected_round=q['round'], expected_used=q['used'], expected_count=q['activeRequestCount'])
        args.update(override)
        return self.query('reset_operation_quota', args)


def test_five_rounds_keep_heartbeat_reads_and_replay_history(warehouse_game):
    c = QuotaChannel(warehouse_game[0])
    oldest = None
    first_rejected = None
    for round_number in range(5):  # Cross both the original 256 and 1024 limits.
        for _ in range(256):
            r = c.query('build_warehouse', dict(x=700, y=740, z=2))
            assert r['ok'], r
            if oldest is None:
                oldest = c.events[-1]
                old_token = r['result']['preview_token']
        q = c.quota()
        assert (q['round'], q['used'], q['remaining']) == (round_number, 256, 0)
        rejected = c.query('buy_vehicles', dict(depot=1, model='unknown.mdl', count=1))
        assert not rejected['ok'] and rejected['rejectedBeforeDispatch']
        assert rejected['code'] == 'operation_quota_rejected'
        first_rejected = first_rejected or c.events[-1]
        assert c.rows[-1]['status'] == 'ready'
        assert c.quota()['used'] == 256
        reset = c.reset()
        assert reset['ok'] and reset['result']['historyPreserved']
        assert c.quota()['used'] == 0
    assert not any(r['status'] == 'stopped' for r in c.rows)
    assert c.lua.globals().SUBMISSIONS is None  # previews only, rejected buy never reached native
    journal = c.state['v']['uiConstruction']
    assert journal['retiredCount'] >= 1280
    for e in (oldest, first_rejected):
        before = journal['quota']['used']
        c.output.clear()
        # Fresh Lua engine context still checks saved tombstones.
        fresh = c.lua.execute(SCRIPT.read_text(encoding='utf-8'))
        fresh['handleEvent'](None, c.state, '', e['id'], e['name'], e['param'])
        assert not c.output and journal['quota']['used'] == before
    old_commit = c.query('commit_facility', {'preview_token': old_token})
    assert not old_commit['ok'] and c.lua.globals().SUBMISSIONS is None


@pytest.mark.parametrize('obstacle', ['pending', 'started', 'wrong_round', 'wrong_used', 'wrong_count', 'storage'])
def test_reset_refuses_unresolved_or_stale_state(warehouse_game, obstacle):
    c = QuotaChannel(warehouse_game[0])
    assert c.query('build_warehouse', dict(x=700, y=740, z=2))['ok']
    override = {}
    if obstacle == 'pending':
        c.lua.execute("quotaTestState.v.uiConstruction.pending='unresolved'")
    elif obstacle == 'started':
        c.lua.execute("for _,r in pairs(quotaTestState.v.uiConstruction.requests)do r.status='started' end")
    elif obstacle == 'storage':
        c.lua.execute('quotaTestState.v.uiConstruction.retiredCount=65535')
    else:
        override['expected_'+obstacle.removeprefix('wrong_')] = 999
    r = c.reset(**override)
    assert not r['ok'], r
    q = c.quota()
    assert q['round'] == 0 and q['used'] == 1
    assert c.state['v']['uiConstruction']['count'] >= 1


def test_duplicate_reset_and_reset_after_reload_are_not_replayed(warehouse_game):
    c = QuotaChannel(warehouse_game[0])
    c.query('build_warehouse', dict(x=700, y=740, z=2))
    assert c.reset()['ok']
    e = c.events[-1]
    c.output.clear()
    fresh = c.lua.execute(SCRIPT.read_text(encoding='utf-8'))
    fresh['handleEvent'](None, c.state, '', e['id'], e['name'], e['param'])
    assert not c.output
    assert c.quota()['round'] == 1
    assert not c.reset()['ok']  # unused rounds cannot be rolled indefinitely


def test_all_preview_families_invalidated_on_rollover(warehouse_game):
    c = QuotaChannel(warehouse_game[0])
    c.query('build_warehouse', dict(x=700, y=740, z=2))
    fields = ('tokens', 'linePreviews', 'edgePreviews', 'workflowTokens',
              'structurePreviews', 'consistPreviews', 'removalPreviews')
    for field in fields:
        c.lua.execute('quotaTestState.v.uiConstruction.'+field+"={old={epoch='same-session'}}")
    assert c.reset()['ok']
    for field in fields:
        assert list(c.state['v']['uiConstruction'][field].items()) == []


@pytest.mark.parametrize('args', [{}, {'expected_round':-1,'expected_used':0,'expected_count':0},
    {'expected_round':True,'expected_used':256,'expected_count':256}])
def test_reset_arguments_are_strict(args):
    with pytest.raises(ValueError):
        validate_build_arguments('reset_operation_quota', args)


def test_old_receiver_refuses_reset_before_publication(host):
    with pytest.raises(ValueError, match='lacks quota reset'):
        host.send('reset_operation_quota', dict(expected_round=0, expected_used=256, expected_count=256),
                  kind='build', expected_session='session')
    assert not host.ledger.exists()


@pytest.mark.parametrize('obstacle', ['host_pending', 'session', 'capability', 'engine_pending', 'round', 'used'])
def test_host_reset_guards_prevent_dispatch(obstacle):
    r = Requests()
    r.status = lambda: dict(receiver=dict(session='current', status='ready',
        operationQuotaVersion=0 if obstacle=='capability' else 1), ageSeconds=0,
        pending='unknown' if obstacle=='host_pending' else None)
    r.responses['get_validation_state'] = dict(session='current', pending='unknown' if obstacle=='engine_pending' else None,
        operationQuota=dict(version=1, round=1 if obstacle=='round' else 0,
                            used=1 if obstacle=='used' else 256, activeRequestCount=256))
    c = HeadlessClient(r, 0)
    with pytest.raises(ValueError):
        asyncio.run(c.reset_operation_quota('wrong' if obstacle=='session' else 'current', 0, 256))
    assert not any(cmd == 'reset_operation_quota' for cmd, _ in r.calls)


def test_host_reset_independent_verification_and_no_retry():
    r = Requests()
    r.status = lambda: dict(receiver=dict(session='current', status='ready', operationQuotaVersion=1),
                           ageSeconds=0, pending=None)
    round_number = 0
    def validation(_):
        return dict(session='current', operationQuota=dict(version=1, round=round_number,
                    used=256 if round_number==0 else 0, activeRequestCount=256 if round_number==0 else 0))
    def reset(args):
        nonlocal round_number
        assert args == dict(expected_round=0, expected_used=256, expected_count=256)
        round_number += 1
        return dict(reset=True, round=round_number)
    r.responses.update(get_validation_state=validation, reset_operation_quota=reset)
    c = HeadlessClient(r, 0)
    assert asyncio.run(c.reset_operation_quota('current', 0, 256))['verified']
    with pytest.raises(ValueError):
        asyncio.run(c.reset_operation_quota('current', 0, 256))
    assert sum(cmd=='reset_operation_quota' for cmd, _ in r.calls) == 1


def test_lost_reset_reply_is_never_retried():
    r = Requests()
    r.status = lambda: dict(receiver=dict(session='current', status='ready', operationQuotaVersion=1),
                           ageSeconds=0, pending=r.pending)
    r.responses['get_validation_state'] = dict(session='current', operationQuota=dict(version=1,
        round=0, used=256, activeRequestCount=256))
    read = r.read
    def lost(ident):
        if r.calls[int(ident)][0] == 'reset_operation_quota':
            r.pending = ident
            return {'status':'timeout_unknown'}
        return read(ident)
    r.read = lost
    c = HeadlessClient(r, 0)
    with pytest.raises(HeadlessOutcomeUnknown):
        asyncio.run(c.reset_operation_quota('current', 0, 256))
    with pytest.raises(ValueError, match='unresolved host'):
        asyncio.run(c.reset_operation_quota('current', 0, 256))
    assert sum(cmd=='reset_operation_quota' for cmd, _ in r.calls) == 1


def test_confirmed_quota_rejection_is_not_an_unknown_outcome():
    r = Requests()
    r.read = lambda ident: dict(status='received', response=dict(ok=False,
        error='quota exhausted', code='operation_quota_rejected', rejectedBeforeDispatch=True))
    with pytest.raises(HeadlessRequestRejected, match='rejected before dispatch'):
        asyncio.run(HeadlessClient(r, 0).request('buy_vehicles', dict(depot=1, model='bus.mdl', count=1)))
    assert len(r.calls) == 1
