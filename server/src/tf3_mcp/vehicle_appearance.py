"""Journalled, bounded appearance changes through the native color command."""
import json
import os
import uuid

from .no_gui import workflow_lock
from .ui_log import validate_build_arguments


async def color_vehicles(client, vehicles, r, g, b, *, line=None, reset=False, expected_line=None):
    color = dict(r=-1, g=-1, b=-1) if reset else dict(r=r, g=g, b=b)
    command = 'reset_vehicle_color' if reset else 'set_vehicle_color'
    validate_build_arguments(command, {'vehicle': 0} if reset else dict(vehicle=0, **color))
    if vehicles is not None and (not isinstance(vehicles, list) or not 1 <= len(vehicles) <= 64
            or any(type(v) is not int or not 0 <= v < 2147483647 for v in vehicles)
            or len(set(vehicles)) != len(vehicles)):
        raise ValueError('Expected 1-64 distinct vehicle IDs')
    with workflow_lock(client.requests.directory):
        if line is not None:
            if type(line) is not int or not 0 <= line < 2147483647:
                raise ValueError('Invalid line ID')
            listing = await client.call('list_vehicles', {'line': line, 'limit': 500})
            vehicles = [v['id'] for v in listing['vehicles']]
            if len(vehicles) > 64:
                raise ValueError('Line exceeds 64 vehicles; select explicit subsets')
        if vehicles is None:
            raise ValueError('Vehicle selection required')
        state = await client.call('get_game_state', {})
        before = []
        for vehicle in vehicles:
            row = await client.call('get_vehicle_appearance', {'vehicle': vehicle})
            if row['owner'] != state['player'] or not row['complete']:
                raise ValueError('Unowned vehicle or unknown appearance; nothing changed')
            if line is not None and row.get('line') != line:
                raise ValueError('Line membership changed; nothing changed')
            before.append(row)
        operation = uuid.uuid4().hex
        folder = client.requests.directory / 'vehicle_appearance'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (operation + '.json')
        report = dict(operation_id=operation, journal=str(path), color=color, line=line,
                      session=client.session, before=before, results=[], complete=False)
        def save():
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temp, path)
        save()
        for row in before:
            vehicle = row['vehicle']
            if not row['canColor']:
                report['results'].append(dict(vehicle=vehicle, status='skipped_no_color_mask'))
                save()
                continue
            report['current'] = vehicle
            save()
            try:
                # Refresh selection before mutation; the receiver checks owner,
                # mask and exact part colors again around its native command.
                fresh = await client.call('get_vehicle_appearance', {'vehicle': vehicle})
                if line is not None and fresh.get('line') != line:
                    raise ValueError('Line membership changed; stopped before this vehicle')
                mutation = {'vehicle': vehicle} if reset else dict(vehicle=vehicle, **color)
                guard_line = line if line is not None else expected_line
                if guard_line is not None and not reset:
                    mutation['expected_line'] = guard_line
                result = await client.call(command, mutation)
                if result.get('verified') is not True:
                    raise ValueError('Unverified color result; do not retry')
                after = await client.call('get_vehicle_appearance', {'vehicle': vehicle})
                if (not after['complete'] or after['owner'] != row['owner']
                        or [p['modelId'] for p in after['parts']] != [p['modelId'] for p in fresh['parts']]
                        or any(abs(p['color'][k] - color[k]) >= .0001
                               for p in after['parts'] if p['colorable'] for k in color)):
                    raise ValueError('Independent color readback mismatch; do not retry')
                report['results'].append(dict(vehicle=vehicle, status='verified', result=result, after=after))
                report.pop('current', None)
                save()
            except Exception as exc:
                report['error'] = str(exc)
                report['status'] = 'stopped_requires_review'
                save()
                return report
        report['complete'] = True
        report['status'] = 'finished'
        save()
        return report
