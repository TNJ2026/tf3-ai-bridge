"""Opt-in line color synchronization while the MCP process remains connected."""
import asyncio
import json
import os

from .vehicle_appearance import color_vehicles


class AppearanceSync:
    def __init__(self, client):
        self.client = client
        self.path = client.requests.directory / 'appearance_sync.json'
        self.task = None
        self.wake = asyncio.Event()
        self.data = {'active': False, 'status': 'stopped', 'lines': []}
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding='utf-8')))
            self.data.update(active=False, status='stopped_after_process_restart')

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data, indent=2), encoding='utf-8')
        os.replace(temp, self.path)

    def status(self):
        return dict(self.data, running=self.task is not None and not self.task.done())

    async def once(self):
        status = await self.client.status()
        if (status['receiver']['session'] != self.data['session'] or status.get('pending')
                or status.get('loadVerification')):
            raise ValueError('Session changed or unresolved request; sync stopped')
        changes = []
        for line in self.data['lines']:
            if self.task is not None and not self.data['active']:
                break
            current = await self.client.call('get_line_appearance', {'line': line})
            color = current['color']
            for vehicle in current['vehicles']:
                if self.task is not None and not self.data['active']:
                    break
                appearance = await self.client.call('get_vehicle_appearance', {'vehicle': vehicle})
                if appearance.get('line') != line:
                    continue
                if not appearance['complete']:
                    raise ValueError('Unknown appearance; sync stopped')
                if not appearance['canColor']:
                    continue
                if all(abs(part['color'][k] - color[k]) < .0001
                       for part in appearance['parts'] if part['colorable'] for k in ('r','g','b')):
                    continue
                result = await color_vehicles(self.client, [vehicle], expected_line=line, **color)
                changes.append({'vehicle': vehicle, 'line': line, 'journal': result['journal']})
                if not result['complete']:
                    raise ValueError('Color operation unresolved: ' + result['journal'])
        self.data['lastChanges'] = changes
        self.data['rounds'] = self.data.get('rounds', 0) + 1
        self.save()

    async def loop(self):
        try:
            while self.data['active']:
                await self.once()
                if not self.data['active']:
                    break
                try:
                    await asyncio.wait_for(self.wake.wait(), self.data['intervalSeconds'])
                except asyncio.TimeoutError:
                    pass
                self.wake.clear()
        except Exception as exc:
            self.data.update(active=False, status='stopped_requires_review', error=str(exc))
        finally:
            self.save()

    async def start(self, lines, interval):
        if self.task and not self.task.done():
            raise ValueError('Stop existing color sync before changing configuration')
        if (not isinstance(lines, list) or not 1 <= len(lines) <= 16
                or any(type(x) is not int or x < 0 for x in lines) or len(set(lines)) != len(lines)
                or type(interval) is not int or not 10 <= interval <= 3600):
            raise ValueError('Use 1-16 distinct line IDs and interval 10-3600 seconds')
        status = await self.client.status()
        if status.get('pending') or status['receiver'].get('vehicleAppearanceVersion', 0) < 2:
            raise ValueError('Appearance v2 without pending required')
        self.data = dict(active=True, status='running', lines=lines, intervalSeconds=interval,
                         session=status['receiver']['session'], rounds=0)
        self.wake.clear()
        self.save()
        self.task = asyncio.create_task(self.loop())
        return self.status()

    async def stop(self):
        self.data.update(active=False, status='stopped')
        self.wake.set()
        if self.task:
            await self.task  # finish observing a submitted operation, never cancel it
        self.save()
        return self.status()
