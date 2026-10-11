"""Explicit headless transport for named tools. Never falls back or replays."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

from .ui_log import SCHEMAS, BUILD_SCHEMAS


class HeadlessOutcomeUnknown(RuntimeError):
    pass


class HeadlessRequestRejected(ValueError):
    """Confirmed rejection before dispatch; never automatically resubmit."""


class HeadlessClient:
    def __init__(self, requests, poll_interval=.2):
        self.requests = requests
        self.poll_interval = poll_interval
        self.lock = asyncio.Lock()
        self.session = None
        self.identity = None

    async def status(self):
        status = await asyncio.to_thread(self.requests.status)
        row = status['receiver']
        if row['status'] != 'ready' or status['ageSeconds'] > 5:
            raise ValueError('Headless receiver is not fresh and ready')
        if self.session is not None and row['session'] != self.session:
            raise ValueError('Game session changed; explicitly bind the new session before using entity IDs')
        return status

    async def bind(self, expected_session):
        async with self.lock:
            status = await asyncio.to_thread(self.requests.status)
            if status['receiver']['session'] != expected_session or status.get('pending'):
                raise ValueError('Session mismatch or unresolved request; cannot bind')
            previous = self.session
            self.session = expected_session
            try:
                state = await self.request('get_game_state', {})
                world = await self.request('get_map_info', {})
                self.identity = dict(session=self.session, player=state['player'], world=state['world'],
                                     mapDigest=self.map_digest(world))
                return self.identity.copy()
            except BaseException:
                self.session = previous
                raise

    @staticmethod
    def map_digest(world):
        data = {k: sorted(world.get(k, []), key=lambda r: r['id']) for k in ('towns', 'industries')}
        data.update(width=world.get('width'), height=world.get('height'))
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    async def request(self, command, args, *, on_ticket=None):
        """Caller holds client lock; the host also enforces the public process lock."""
        status = await self.status()
        if self.session is None:
            self.session = status['receiver']['session']
        kind = 'read' if command in SCHEMAS else 'save' if command == 'save_game' else 'build'
        if kind == 'build' and command not in BUILD_SCHEMAS:
            raise ValueError(f'{command} is not implemented by the headless channel; no file fallback')
        ticket = await asyncio.to_thread(self.requests.send, command, args, kind=kind, expected_session=self.session)
        if on_ticket:
            on_ticket(ticket)
        deadline = time.monotonic() + (125 if kind == 'save' else 65)
        while True:
            result = await asyncio.to_thread(self.requests.read, ticket['id'])
            if result['status'] == 'rejected':
                raise HeadlessRequestRejected(f"Request {ticket['id']} rejected before dispatch; inspect reconciliation")
            if result['status'] == 'received':
                response = result['response']
                if not response['ok']:
                    raise HeadlessOutcomeUnknown(f"Request {ticket['id']} failed; inspect original result, never replay: {response.get('error')}")
                return response['result']
            if result['status'] == 'timeout_unknown' or time.monotonic() >= deadline:
                raise HeadlessOutcomeUnknown(f"Request {ticket['id']} has unknown outcome; read this ID, never replay")
            await asyncio.sleep(self.poll_interval)

    async def call(self, command, arguments=None):
        async with self.lock:
            args = {k: v for k, v in (arguments or {}).items() if v is not None}
            if command in ('get_planning_snapshot', 'get_route_snapshot'):
                return await self.snapshot(command, args)
            if command == 'ping':
                state = await self.request('get_game_state', {})
                return dict(echo=args.get('echo', ''), state=state, transport='headless', session=self.session)
            if command == 'accept_subvention':
                preview = await self.request('preview_subvention', {'uid': args['uid']})
                task = preview['task']
                for key, value in (args.get('expect') or {}).items():
                    actual = task.get(key)
                    if key == 'target' and isinstance(actual, dict):
                        actual = actual.get('id', actual.get('entity'))
                    if actual != value:
                        raise ValueError('Subvention terms changed before commit')
                token = preview['preview_token']
                result = await self.request('commit_subvention', {'preview_token': token})
                if result.get('verified') is not True:
                    result = await self.request('get_subvention_operation', {'operation_id': token})
                return result
            if command == 'configure_facility':
                parameters, modules = args.get('parameters', {}), args.get('modules', [])
                if len(parameters) == 1 and not modules:
                    key, value = next(iter(parameters.items()))
                    return await self.request('preview_facility_parameter', dict(entity=args['entity'], key=key, value=value))
                if len(modules) == 1 and not parameters and set(modules[0]) <= {'slot', 'resource'}:
                    return await self.request('preview_facility_module', dict(entity=args['entity'], **modules[0]))
                raise ValueError('Headless facility configuration accepts one parameter or module per preview; combined replacement is not implemented')
            if command.startswith('build_') and command in BUILD_SCHEMAS:
                if args.get('preview') is True:
                    args.pop('preview')  # these native handlers only create a preview
                if args.get('name') == '':
                    args.pop('name')
            if command == 'list_facility_resources' and args.get('search') == '':
                args.pop('search')
            # Old convenience wrappers may preview but cannot silently bypass new
            # token-based commits or discard materially different old arguments.
            aliases = {'build_road': 'preview_road', 'upgrade_road': 'preview_road_upgrade',
                       'build_street_stop': 'preview_street_stop', 'build_depot': 'preview_depot',
                       'build_station': 'preview_station', 'build_rail_station': 'preview_rail_station'}
            if command in aliases:
                if args.pop('preview', False) is not True:
                    raise ValueError('Headless construction requires explicit preview=True, then a single token commit')
                harmless = {'allow_collisions': False, 'snap_radius': 5, 'max_segment_length': 50,
                            'connect': False, 'kind': 'auto', 'radius': 50}
                target = aliases[command]
                for key, default in harmless.items():
                    if key in args and key not in BUILD_SCHEMAS[target]:
                        if args[key] != default:
                            raise ValueError(f'Unsupported headless option: {key}; use explicit planning')
                        args.pop(key)
                command = target
            if command == 'list_vehicles' and 'line' in args:
                line = args.pop('line')
                result = await self.request(command, args)
                if result['count'] >= args.get('limit', 500):
                    raise ValueError('Vehicle list may be truncated; use paged entity inventory')
                rows = [r for r in result['vehicles'] if r.get('line') == line]
                return dict(result, vehicles=rows, count=len(rows))
            if command == 'list_facilities' and args.get('mine_only') is True:
                args.pop('mine_only')
            if command == 'send_to_depot' and args.get('sell_on_arrival') is False:
                args.pop('sell_on_arrival')
            if command == 'set_game_speed' and 'expected_speed' not in args:
                args['expected_speed'] = (await self.request('get_game_state', {}))['speedup']
            if command == 'buy_vehicles' and (args.get('count', 1) != 1 or 'line' in args):
                raise ValueError('Use execute_vehicle_batch with an explicit batch_id for multi-step purchases/assignment')
            if command == 'save_game':
                if (await self.request('get_game_state', {}))['speedup'] != 0:
                    raise ValueError('Pause before saving; no save request was sent')
            requested_limit = None
            if command in BUILD_SCHEMAS and BUILD_SCHEMAS[command].get('limit') == 'page_limit' and type(args.get('limit')) is int and 100 < args['limit'] <= 1024:
                requested_limit, args['limit'] = args['limit'], 100
            result = await self.request(command, args)
            if requested_limit is not None:
                result = dict(result, requestedLimit=requested_limit, effectiveLimit=100,
                              transportPaging='bounded headless page; follow nextOffset/hasMore')
            return result

    async def snapshot(self, command, args):
        # Do not send potentially megabytes of revision dictionaries in a request.
        # Refreshes use full immutable snapshots; the existing host cache still
        # reuses a fresh result between refreshes.
        allowed = ('bounds', 'spacing') if command == 'get_planning_snapshot' else ('start_construction', 'end_construction', 'spacing', 'whole_map')
        unsupported = set(args) - set(allowed) - {'domain', 'revisions', 'terrain_revisions'}
        if unsupported:
            raise ValueError('Unsupported snapshot options: ' + ', '.join(sorted(unsupported)))
        query = {k: args[k] for k in allowed if k in args}
        query['snapshot_kind'] = 'planning' if command == 'get_planning_snapshot' else 'route'
        start = await self.request('begin_snapshot', query)
        if start['session'] != self.session or not 0 < start['bytes'] <= 8388608:
            raise ValueError('Invalid snapshot identity or byte bound')
        token, offset, parts = start['snapshot'], 0, []
        while offset < start['bytes']:
            page = await self.request('read_snapshot_page', {'snapshot': token, 'offset': offset})
            raw = bytes.fromhex(page['hex'])
            if (page['snapshot'] != token or page['session'] != self.session or page['offset'] != offset
                    or page['totalBytes'] != start['bytes'] or not raw or len(raw) > 24000
                    or page['nextOffset'] != offset + len(raw) or page['nextOffset'] > start['bytes']):
                raise ValueError('Snapshot page mismatch; do not combine different snapshots')
            parts.append(raw)
            offset = page['nextOffset']
        value = json.loads(b''.join(parts).decode('utf-8'))
        if value.get('state') != start['state']:
            raise ValueError('Snapshot header and body state disagree')
        await self.request('release_snapshot', {'snapshot': token})
        value['headlessSession'] = self.session
        return value
