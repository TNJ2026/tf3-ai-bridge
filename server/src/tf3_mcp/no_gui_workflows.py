"""Opt-in, journaled orchestration; no automatic start, retry or game-speed changes."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import re
import time

from .no_gui import atomic, public_lock


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8'))


class VehicleBatches:
    def __init__(self, client, directory):
        self.client, self.directory = client, Path(directory)

    async def execute(self, batch_id, operations, expected_session):
        if not isinstance(batch_id, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', batch_id):
            raise ValueError('Invalid batch_id')
        if not isinstance(operations, list) or not 1 <= len(operations) <= 64:
            raise ValueError('Expected 1..64 explicit operations')
        from .ui_log import validate_build_arguments
        plans = []
        for operation in operations:
            if not isinstance(operation, dict) or set(operation) != {'command', 'arguments'}:
                raise ValueError('Each operation requires command and arguments')
            command = operation['command']
            if command not in ('buy_vehicles', 'assign_vehicles', 'sell_vehicles', 'send_to_depot', 'set_vehicle_stopped'):
                raise ValueError('Unsupported vehicle batch command')
            args = dict(operation['arguments'])
            # A purchase result may be assigned by an explicit reference to one
            # earlier operation, avoiding guesses about newly allocated IDs.
            reference = args.pop('purchase_index', None)
            if reference is not None:
                if (command != 'assign_vehicles' or type(reference) is not int or not 0 <= reference < len(plans)
                        or plans[reference]['command'] != 'buy_vehicles' or 'vehicles' in args):
                    raise ValueError('Invalid purchase_index reference')
                validate_build_arguments(command, dict(args, vehicles=[0]))
            else:
                validate_build_arguments(command, args)
            plans.append(dict(command=command, arguments=args, purchase_index=reference))
        digest = hashlib.sha256(json.dumps(plans, sort_keys=True).encode()).hexdigest()
        path = self.directory / 'vehicle_batches' / (batch_id + '.json')
        async with self.client.lock:
            # Reserve the workflow ID across MCP processes before dispatch.
            with public_lock(self.directory):
                if path.exists():
                    previous = json.loads(path.read_text(encoding='utf-8'))
                    if previous['digest'] != digest or previous['session'] != expected_session:
                        raise ValueError('Existing batch identity differs; never repurpose batch IDs')
                    return previous  # running/unknown is NOT resumed
                status = await self.client.status()
                if status['receiver']['session'] != expected_session or status.get('pending'):
                    raise ValueError('Session mismatch or pending request')
                self.client.session = expected_session
                journal = dict(batch_id=batch_id, digest=digest, session=expected_session,
                               status='reserved', startedAt=time.time(), steps=[], retryAllowed=False)
                write(path, journal)
            try:
                journal['before'] = await self.client.request('get_game_state', {})
                world = await self.client.request('get_map_info', {})
                journal['mapDigest'] = self.client.map_digest(world)
                for index, plan in enumerate(plans):
                    args = dict(plan['arguments'])
                    if plan['purchase_index'] is not None:
                        bought = journal['steps'][plan['purchase_index']]['result']['bought']
                        if len(bought) != 1:
                            raise ValueError('Purchase did not return exactly one vehicle')
                        args['vehicles'] = bought
                    step = dict(index=index, command=plan['command'], arguments=args, status='intent')
                    journal['steps'].append(step)
                    journal['status'] = 'running'
                    write(path, journal)
                    def ticket(value):
                        step['ticket'] = value
                        write(path, journal)
                    result = await self.client.request(plan['command'], args, on_ticket=ticket)
                    step.update(result=result, status='returned')
                    write(path, journal)
                    if result.get('failures'):
                        raise ValueError('Partial vehicle result; stop without replay')
                    # Native callback alone is not a fleet/configuration audit.
                    if plan['command'] == 'buy_vehicles':
                        ids = result.get('bought', [])
                        if len(ids) != 1 or type(ids[0]) is not int:
                            raise ValueError('Purchase result lacks exactly one vehicle identity')
                    else:
                        ids = args.get('vehicles') or [args['vehicle']]
                    if plan['command'] == 'sell_vehicles':
                        inventory = await self.client.request('list_vehicles', {'limit': 500, 'mine_only': True})
                        if inventory['count'] >= 500 or any(v['id'] in ids for v in inventory['vehicles']):
                            raise ValueError('Vehicle sale inventory incomplete or still contains sold vehicle')
                        step['readback'] = inventory
                    else:
                        readback = await self.client.request('get_entity', {'id': ids[0], 'components': ['TRANSPORT_VEHICLE']})
                        vehicle = readback['components'].get('TRANSPORT_VEHICLE')
                        if not vehicle:
                            raise ValueError('Vehicle readback missing')
                        if plan['command'] == 'buy_vehicles' and vehicle.get('depot') != args['depot']:
                            raise ValueError('Purchase depot readback mismatch')
                        if plan['command'] == 'assign_vehicles' and vehicle.get('line') != args['line']:
                            raise ValueError('Assignment readback mismatch')
                        if plan['command'] == 'set_vehicle_stopped' and vehicle.get('userStopped') != args['stopped']:
                            raise ValueError('Stopped-state readback mismatch')
                        step['readback'] = readback
                        if plan['command'] == 'send_to_depot':
                            step['arrivalVerified'] = False
                            step['limitation'] = 'Command returned and vehicle reread; actual depot arrival requires later observation'
                    step['status'] = 'verified'
                    write(path, journal)
                journal['after'] = await self.client.request('get_game_state', {})
                journal['status'] = 'completed'
            except BaseException as exc:
                journal.update(status='stopped_incomplete', error=str(exc))
                write(path, journal)
                if isinstance(exc, asyncio.CancelledError):
                    raise
            journal['finishedAt'] = time.time()
            write(path, journal)
            return journal


class OperationsMonitor:
    """Read-only monitoring, explicitly started; one round at a time, stop on errors."""
    def __init__(self, client, directory):
        self.client, self.directory = client, Path(directory)
        self.task = None
        self.last = None
        self.previous = None
        self.error = None
        self.interval = 60
        latest = self.directory / 'operations_monitor' / 'latest.json'
        if latest.exists():
            self.previous = json.loads(latest.read_text(encoding='utf-8'))

    def status(self):
        return dict(running=bool(self.task and not self.task.done()), intervalSeconds=self.interval,
                    error=self.error, last=self.last, scope='account balance/income only; paused until explicitly started; no automatic borrowing')

    async def inventory(self, kind):
        first = await self.client.request('list_map_entities', dict(kind=kind, snapshot='new', ids_only=True, limit=100))
        token = first['snapshot']
        rows, page, offset = [], first, 0
        while True:
            if page['snapshot'] != token or page['offset'] != offset:
                raise ValueError('Entity page mismatch')
            rows.extend(page['items'])
            if any(isinstance(row, dict) and row.get('missing') for row in page['items']):
                raise ValueError('Entity removed during monitoring inventory; reconcile current map')
            if len(rows) > 10000:
                raise ValueError('Monitoring inventory exceeds bound')
            if not page.get('hasMore'):
                break
            next_offset = page['nextOffset']
            if next_offset <= offset:
                raise ValueError('Entity page failed to advance')
            offset = next_offset
            page = await self.client.request('list_map_entities', dict(kind=kind, snapshot=token, ids_only=True, limit=100, offset=offset))
        await self.client.request('release_map_snapshot', {'snapshot': token})
        return rows

    async def once(self):
        if self.client.lock.locked():
            return {'status': 'skipped_busy', 'catchUp': False}
        async with self.client.lock:
            started = time.time()
            try:
                status = await self.client.status()
                if status.get('pending'):
                    return {'status': 'skipped_pending_request', 'catchUp': False}
                state = await self.client.request('get_game_state', {})
                world = await self.client.request('get_map_info', {})
                from .finance_watch import assess
                current = dict(session=self.client.session, state=state, map=world,
                               mapDigest=self.client.map_digest(world), startedAt=started,
                               finances=await self.client.request('get_finances', {}),
                               scope='account_only', towns=[], vehicles=[], lines=[])
                current['accountWatch'], current['events'] = assess(current, self.previous)
                current.update(finishedAt=time.time(),
                               unknown=['income'] if current['accountWatch']['incomeStatus']=='unavailable' else [],
                               limitation='No transaction reconciliation, vehicle inventory, cargo statistics or automatic borrowing. Cash change is not income.')
                write(self.directory / 'operations_monitor' / f'round_{time.time_ns()}.json', current)
                write(self.directory / 'operations_monitor' / 'latest.json', current)
                self.previous = current
                self.last = dict(status='completed', startedAt=started, finishedAt=current['finishedAt'],
                                 events=current['events'], vehicles=len(current['vehicles']), lines=len(current['lines']), towns=len(current['towns']))
                self.error = None
                return self.last
            except BaseException as exc:
                self.error = str(exc)
                self.last = dict(status='stopped_incomplete', startedAt=started, error=self.error)
                write(self.directory / 'operations_monitor' / 'error.json', self.last)
                raise

    async def start(self, interval=60):
        if type(interval) not in (int, float) or not 60 <= interval <= 86400:
            raise ValueError('Interval must be 60..86400 seconds')
        await self.stop()
        self.interval = interval
        first = await self.once()
        async def loop():
            while True:
                await asyncio.sleep(self.interval)
                try:
                    await self.once()
                except Exception:
                    break  # no retry against a failed/disconnected receiver
        self.task = asyncio.create_task(loop())
        return dict(self.status(), firstPass=first)

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        return self.status()
