"""Finite, read-only soak of demand ingress; never claims mathematical infinity."""
from __future__ import annotations
import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def map_identity(value):
    """Identity, not population/production: preserve every original entity."""
    rows = {}
    for kind, key, label in [('town', 'towns', 'name'), ('industry', 'industries', 'fileName')]:
        for item in value[key]:
            entity = item['id']
            if type(entity) is not int or entity < 0 or entity in rows:
                raise ValueError('Invalid or duplicate map entity identity')
            rows[entity] = (kind, item[label], item['position'])
    return {'width': value['width'], 'height': value['height'], 'entities': rows}


def compare_map_identity(before, after):
    old, new = map_identity(before), map_identity(after)
    if (old['width'], old['height']) != (new['width'], new['height']):
        raise ValueError('Map dimensions changed')
    for entity, identity in old['entities'].items():
        if new['entities'].get(entity) != identity:
            raise ValueError(f'Map entity removed, moved or replaced: {entity}')
    additions = sorted(set(new['entities']) - set(old['entities']))
    if any(new['entities'][entity][0] != 'industry' for entity in additions):
        raise ValueError('Unexpected new town identity')
    return {'allOriginalObjectsPreserved': True,
            'industryAdditions': [{'id': entity, 'identity': new['entities'][entity]} for entity in additions],
            'basis': 'same session and dimensions, exact original IDs/resources/positions; strictly additive industries only'}


def describe_failure(exc):
    """Preserve nested MCP TaskGroup causes without retrying a request."""
    children = getattr(exc, 'exceptions', None)
    if children:
        return '; '.join(describe_failure(child) for child in children)
    return f'{type(exc).__name__}: {exc}'


def memory_sample():
    if os.name != 'nt':
        return {'available': False}
    try:
        proc = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
            'Get-Process TransportFever3 -ErrorAction Stop | Select-Object Id,PrivateMemorySize64,WorkingSet64,CPU | ConvertTo-Json -Compress'],
            capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if proc.returncode:
            return {'available': False, 'reason': 'process metrics unavailable'}
        return {'available': True, 'process': json.loads(proc.stdout)}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'available': False, 'reason': 'process metrics unavailable'}


async def run(args):
    out=args.evidence.resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'soak_state.json').exists():
        raise RuntimeError('Existing soak evidence; never restart or overwrite')
    deployment=json.loads((out/'deployment.json').read_text(encoding='utf-8'))
    assert deployment['mode']=='demand'
    env=dict(os.environ,PYTHONPATH=str(ROOT/'server/src'),TF3_MCP_DIR=str(args.bridge_dir),
             TF3_MCP_NO_GUI_MOD=deployment['modContent'])
    log=args.bridge_dir.parent/'crash_dump/stdout.txt'
    state={'status':'waiting_for_receiver','startedAt':time.time(),'requests':[],
           'idleSamples':[],'guiInputs':0,'worldMutations':0,'speedChanges':0,
           'idleTargetSeconds':args.idle_seconds,'burstTarget':args.burst,
           'generation':deployment['generation'],'mathematicalInfinityProven':False}
    session=None

    def save():
        target=out/'soak_state.json';temp=out/'soak_state.tmp'
        temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,target)

    def check_stop():
        if (out/'STOP').exists():
            raise RuntimeError('Stopped by operator; no replay')

    @asynccontextmanager
    async def connect():
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','tf3_mcp.server'],env=env)) as (rd,wr):
            async with ClientSession(rd,wr) as client:
                await client.initialize();yield client

    async def call(client,name,arguments):
        check_stop()
        response=await client.call_tool(name,arguments)
        if response.is_error:
            raise RuntimeError(str(response.content))
        return response.structured_content or json.loads(response.content[0].text)

    async def status(client):
        value=await call(client,'no_gui_status',{})
        row=value['receiver']
        assert row['generation']==deployment['generation'] and row['mode']=='demand',value
        assert row['status']=='ready' and row['session']==session,value
        assert value['pending'] is None,value
        return value

    async def query(client,command='get_game_state'):
        started=time.time()
        ticket=await call(client,'send_no_gui_request',dict(command=command,kind='read',arguments={},expected_session=session))
        record={'command':command,'ticket':ticket,'startedAt':started,'status':'published'}
        state['requests'].append(record);save()
        deadline=time.monotonic()+65
        while time.monotonic()<deadline:
            reply=await call(client,'read_no_gui_result',{'request_id':ticket['id']})
            if reply['status']=='received':
                assert reply['response']['ok'],reply
                record.update(status='received',response=reply['response'],elapsedSeconds=time.time()-started)
                save();return record
            if reply['status']=='timeout_unknown':
                raise RuntimeError('Unknown request outcome; no resubmission')
            await asyncio.sleep(.2)
        raise RuntimeError('Request deadline exceeded; no resubmission')

    def fingerprint(value):
        rows=[('town',x['name'],x['position']) for x in value['towns']]
        rows += [('industry',x['fileName'],x['position']) for x in value['industries']]
        return hashlib.sha256(json.dumps(sorted(rows,key=lambda x:json.dumps(x,sort_keys=True)),sort_keys=True).encode()).hexdigest()

    save()
    try:
        async with connect() as client:
            print('Waiting for the new demand receiver; no GUI input or game reload.',flush=True)
            deadline=time.monotonic()+900
            while time.monotonic()<deadline:
                check_stop()
                with log.open('rb') as f:
                    f.seek(max(0,log.stat().st_size-65536));tail=f.read()
                if deployment['generation'].encode() in tail:
                    value=await call(client,'no_gui_status',{})
                    row=value['receiver']
                    assert row['generation']==deployment['generation'] and row['mode']=='demand'
                    assert row['status']=='ready' and value['pending'] is None
                    session=row['session'];state['session']=session;break
                await asyncio.sleep(1)
            else:
                raise RuntimeError('No new demand receiver within 15 minutes')
            state['status']='initial_queries';save()
            first=await query(client)
            baseline=await query(client,'get_map_info')
            state['mapFingerprintBefore']=fingerprint(baseline['response']['result'])
            idle_slot=(await status(client))['receiver']['slot']
            start=time.monotonic();state.update(status='idle',idleSlot=idle_slot,idleStartedAt=time.time());save()
            while time.monotonic()-start<args.idle_seconds:
                check_stop();value=await status(client)
                assert value['receiver']['slot']==idle_slot,'Idle consumed a slot or another client submitted work'
                sample={'elapsedSeconds':time.monotonic()-start,'slot':idle_slot,'utc':time.time(),
                        'memory':await asyncio.to_thread(memory_sample)}
                state['idleSamples'].append(sample);save()
                print(f'IDLE {sample["elapsedSeconds"]:.0f}s slot={idle_slot}',flush=True)
                await asyncio.sleep(min(30,max(0,args.idle_seconds-(time.monotonic()-start))))
            state['idleActualSeconds']=time.monotonic()-start
            state['status']='burst_first_half';save()
            await query(client)  # First actual query beyond the former idle lifetime.
            state['resumedAfterIdle']=True;save()
            for n in range(args.burst//2):
                await query(client)
                if n%25==24:print(f'BURST {n+1}/{args.burst}',flush=True)
        # A completely new MCP process reads the first result before continuing.
        state['status']='mcp_restart';save()
        async with connect() as client:
            recovered=await call(client,'read_no_gui_result',{'request_id':first['ticket']['id']})
            assert recovered['response']==first['response']
            state['mcpRestartRecoveryPassed']=True;state['status']='burst_second_half';save()
            for n in range(args.burst-args.burst//2):
                await query(client)
                if n%25==24:print(f'BURST {n+1+args.burst//2}/{args.burst}',flush=True)
            final_map=await query(client,'get_map_info')
            state['mapFingerprintAfter']=fingerprint(final_map['response']['result'])
            state['mapReconciliation']=compare_map_identity(baseline['response']['result'], final_map['response']['result'])
            recovered=await call(client,'read_no_gui_result',{'request_id':first['ticket']['id']})
            assert recovered['response']==first['response']
            state['archivedResultRecoveryPassed']=True
            state['finalReceiver']=await status(client)
            state['finalMemory']=await asyncio.to_thread(memory_sample)
        state.update(status='finite_soak_passed',finishedAt=time.time())
    except Exception as exc:
        state.update(status='stopped_incomplete',error=describe_failure(exc),finishedAt=time.time(),retryAllowed=False)
    finally:
        save()
        print(json.dumps({k:v for k,v in state.items() if k not in ('requests','idleSamples')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--bridge-dir',type=Path,required=True)
    parser.add_argument('--idle-seconds',type=int,default=2160)
    parser.add_argument('--burst',type=int,default=300)
    args=parser.parse_args()
    if not 1<=args.idle_seconds<=14400 or not 2<=args.burst<=500:
        parser.error('Keep this acceptance bounded: idle 1..14400 seconds; burst 2..500 queries')
    asyncio.run(run(args))
