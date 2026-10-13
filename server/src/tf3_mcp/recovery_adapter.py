"""Current headless reads/saves plus an explicitly configured Windows bootstrap.

The project has no verified universal TF3 command-line load-save switch. Supply
a locally validated bootstrap argv containing {checkpoint}; no switch is guessed.
No process termination, background service, UI scripting or transport fallback.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import time

from .headless import atomic
from .headless_client import HeadlessClient
from .recovery_runtime import RecoveryBlocked, digest, file_digest, validate_snapshot


def windows_processes(executable):
    """Exact executable identity; AccessDenied/unknown path fails closed."""
    if os.name != 'nt':
        raise RecoveryBlocked('Windows process discovery required')
    path = Path(executable).resolve()
    # Script is constant. No configuration text is interpolated into PowerShell.
    script = ("[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
              "Get-CimInstance Win32_Process | Select-Object ProcessId,ExecutablePath,"
              "Name,CreationDate | ConvertTo-Json -Compress")
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, encoding='utf-8', errors='strict',
                            timeout=15, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    rows = json.loads(result.stdout or '[]')
    if isinstance(rows, dict):
        rows = [rows]
    found = []
    for row in rows:
        if str(row.get('Name', '')).casefold() != path.name.casefold():
            continue
        if not row.get('ExecutablePath'):
            raise RecoveryBlocked('Process executable identity inaccessible')
        if os.path.normcase(str(Path(row['ExecutablePath']).resolve())) != os.path.normcase(str(path)):
            raise RecoveryBlocked('Another game executable is running; process identity ambiguous')
        if not row.get('CreationDate') or type(row.get('ProcessId')) is not int:
            raise RecoveryBlocked('Incomplete process identity')
        found.append({'pid': row['ProcessId'], 'created': row['CreationDate'],
                      'executable': str(path)})
    if len(found) > 1:
        raise RecoveryBlocked('Multiple matching game processes')
    return found


class HeadlessRecoveryAdapter:
    def __init__(self, requests, directory, config, *, process_query=windows_processes):
        self.requests = requests
        self.client = HeadlessClient(requests)
        self.directory = Path(directory)
        self.config = config
        self.process_query = process_query
        self.binding_path = self.directory / 'process_binding.json'
        # Narrow queries only: no eval or mutation supplied as an audit query.
        probes = config.get('audit', [])
        allowed = {'get_entity', 'get_sim_entity', 'get_vehicle_cargo', 'get_stock_cargo',
                   'get_game_state', 'get_finances', 'get_loans', 'get_town_cargo_needs'}
        if not 1 <= len(probes) <= 64:
            raise ValueError('Configure 1..64 explicit audit queries')
        names = set()
        for probe in probes:
            if (not isinstance(probe, dict) or set(probe) != {'name', 'command', 'arguments', 'fields'}
                    or not isinstance(probe['name'], str) or not probe['name'] or probe['name'] in names
                    or probe['command'] not in allowed or not isinstance(probe['arguments'], dict)
                    or not isinstance(probe['fields'], list) or not probe['fields']
                    or any(not isinstance(f, str) or not f for f in probe['fields'])):
                raise ValueError('Invalid recovery audit query')
            names.add(probe['name'])
        if not Path(config['gameExecutable']).is_absolute():
            raise ValueError('Absolute game executable required')

    def save_path(self, slot):
        return self.requests._save_path(slot)

    async def _processes(self):
        return await asyncio.to_thread(self.process_query, self.config['gameExecutable'])

    async def snapshot(self):
        status = await asyncio.to_thread(self.requests.status)
        receiver = status['receiver']
        if status.get('pending') or receiver.get('status') != 'ready' or status['ageSeconds'] > 5:
            raise RecoveryBlocked('Receiver unavailable or host request unresolved')
        processes = await self._processes()
        if len(processes) != 1:
            raise RecoveryBlocked('One identified game process required')
        # Rebinding never imports IDs from an older session. The configured audit
        # describes checkpoint objects and must match independently after load.
        await self.client.bind(receiver['session'])
        state = await self.client.call('get_game_state')
        validation = await self.client.call('get_validation_state')
        world = await self.client.call('get_map_info')
        audit = {}
        for probe in self.config['audit']:
            value = await self.client.call(probe['command'], probe['arguments'])
            selected = {}
            for field in probe['fields']:
                item = value
                for part in field.split('.'):
                    item = item[int(part)] if isinstance(item, list) else item[part]
                selected[field] = item
            audit[probe['name']] = selected
        end = await self.client.call('get_game_state')
        final_validation = await self.client.call('get_validation_state')
        final_status = await asyncio.to_thread(self.requests.status)
        if (state['gameTime'] != end['gameTime'] or state['player'] != end['player']
                or state['speedup'] != 0 or end['speedup'] != 0
                or validation['session'] != final_validation['session']
                or final_status.get('pending') or final_status['ageSeconds'] > 5
                or final_status['receiver'].get('status') != 'ready'
                or final_status['receiver']['generation'] != receiver['generation']
                or final_status['receiver']['session'] != receiver['session']
                or await self._processes() != processes):
            raise RecoveryBlocked('World changed during recovery audit')
        result = dict(session=validation['session'], generation=receiver['generation'],
                      capabilityRevision=validation['capabilityRevision'],
                      pending=final_validation.get('pending'), state=end, world=world, audit=audit)
        validate_snapshot(result)
        if result['session'] != receiver['session']:
            raise RecoveryBlocked('Receiver/engine session mismatch')
        binding = dict(process=processes[0], session=result['session'], gameTime=end['gameTime'],
                       capturedAt=time.time(), configDigest=digest(self.config))
        self.directory.mkdir(parents=True, exist_ok=True)
        atomic(self.binding_path, json.dumps(binding, ensure_ascii=True).encode('utf-8'))
        return result

    async def capture_evidence(self, incident_id):
        """Keep bounded raw diagnostics before any bootstrap can replace logs."""
        folder = self.directory / 'incidents' / digest(incident_id)
        manifest = folder / 'evidence.json'
        if manifest.exists():
            return json.loads(manifest.read_text(encoding='utf-8'))
        folder.mkdir(parents=True, exist_ok=True)
        captured = {'incident': incident_id, 'capturedAt': time.time(), 'files': [],
                    'note': 'Diagnostic bytes only; absence of logs is not proof of no mutation'}
        paths = [self.requests.directory / 'headless_requests.json',
                 self.requests.directory.parent / 'crash_dump' / 'stdout.txt', self.binding_path]
        for path in paths:
            if not path.is_file():
                continue
            with path.open('rb') as stream:
                size = os.fstat(stream.fileno()).st_size
                offset = max(0, size - 2 * 1024 * 1024)
                stream.seek(offset)
                data = stream.read(2 * 1024 * 1024)
            target = folder / (path.name + '.bin')
            atomic(target, data)
            captured['files'].append(dict(source=str(path), captured=str(target),
                originalBytes=size, offset=offset, truncated=offset != 0,
                sha256=file_digest(target)['sha256'] if data else None))
        atomic(manifest, json.dumps(captured, ensure_ascii=True, indent=2).encode('utf-8'))
        return captured

    async def save(self, slot):
        return await self.client.call('save_game', {'slot': slot, 'overwrite': False})

    async def observe(self):
        binding = json.loads(self.binding_path.read_text(encoding='utf-8'))
        if binding['configDigest'] != digest(self.config):
            raise RecoveryBlocked('Recovery configuration changed since binding')
        processes = await self._processes()
        result = dict(identityVerified=True, process='running' if processes else 'exited',
                      connected=False, lastSession=binding['session'])
        try:
            status = await asyncio.to_thread(self.requests.status)
            receiver = status['receiver']
            result.update(connected=receiver.get('status') == 'ready' and status['ageSeconds'] <= 5,
                          pending=status.get('pending'), receiver=receiver)
        except (ValueError, OSError) as exc:
            result['transportError'] = str(exc)
        if processes and processes[0] != binding['process']:
            # A new process is expected during recovery, but only native
            # checkpoint verification can approve its session and contents.
            result['replacementProcess'] = processes[0]
        if not processes:
            # A paused snapshot cannot prove the player did not subsequently
            # unpause. A caller must provide an independently collected final
            # game-time observation for automatic rollback authorization.
            evidence_path = self.directory / 'exit_evidence.json'
            if evidence_path.exists():
                evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
                if (evidence.get('process') == binding['process']
                        and evidence.get('session') == binding['session']
                        and evidence.get('source') == 'native_final_game_time'
                        and evidence.get('capturedAt', 0) >= binding['capturedAt']):
                    result['lastGameTime'] = evidence['gameTime']
        return result

    async def preflight_launch(self, checkpoint):
        if await self._processes():
            raise RecoveryBlocked('Game process still exists; never terminate automatically')
        bootstrap = self.config.get('bootstrap')
        if not isinstance(bootstrap, dict) or bootstrap.get('validated') is not True:
            raise RecoveryBlocked('No validated checkpoint-loading bootstrap configured')
        argv = bootstrap.get('argv')
        if (not isinstance(argv, list) or not argv or not all(isinstance(s, str) and s for s in argv)
                or not Path(argv[0]).is_absolute() or '{checkpoint}' not in argv[1:]):
            raise RecoveryBlocked('Bootstrap needs absolute executable and standalone {checkpoint} argument')
        if file_digest(argv[0])['sha256'] != bootstrap.get('executableSha256'):
            raise RecoveryBlocked('Bootstrap executable changed')
        if file_digest(checkpoint['path']) != checkpoint['file']:
            raise RecoveryBlocked('Checkpoint changed')

    async def launch(self, checkpoint):
        await self.preflight_launch(checkpoint)
        argv = [checkpoint['path'] if s == '{checkpoint}' else s for s in self.config['bootstrap']['argv']]
        kwargs = {'shell': False, 'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL,
                  'stderr': subprocess.DEVNULL, 'cwd': str(Path(argv[0]).parent)}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        process = subprocess.Popen(argv, **kwargs)
        return {'pid': process.pid, 'argvDigest': digest(argv), 'requested': True,
                'loaded': False, 'verified': False}
