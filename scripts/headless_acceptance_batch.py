"""Execute an explicit reviewed acceptance batch once; stop on any unknown result."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]

async def main(spec_path):
    spec=json.loads(spec_path.read_text(encoding='utf-8'))
    target=spec_path.with_name(spec_path.stem+'_result.json')
    if target.exists():raise RuntimeError('Existing batch evidence; never replay')
    deployment=json.loads(Path(spec['deployment']).read_text(encoding='utf-8'))
    state={'status':'started','startedAt':time.time(),'requests':[]}
    def save():
        temp=target.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=True,indent=2),encoding='utf-8');os.replace(temp,target)
    save()
    env=dict(os.environ,PYTHONPATH=str(ROOT/'server/src'),TF3_MCP_DIR=spec['bridgeDir'],TF3_MCP_HEADLESS_MOD=deployment['modContent'])
    try:
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','tf3_mcp.server'],env=env)) as (rd,wr):
            async with ClientSession(rd,wr) as client:
                await client.initialize()
                async def call(name,args):
                    r=await client.call_tool(name,args)
                    if r.is_error:raise RuntimeError(str(r.content))
                    return r.structured_content or json.loads(r.content[0].text)
                state['receiverBefore']=await call('headless_status',{})
                row=state['receiverBefore']['receiver']
                assert row['generation']==deployment['generation'] and row['status']=='ready' and state['receiverBefore']['pending'] is None
                session=row['session'];state['session']=session
                if spec.get('session'):assert session==spec['session']
                save()
                for command in spec['commands']:
                    kind=command.get('kind','read')
                    if kind in ('build','save'):assert spec.get('session')==session,'Operation needs reviewed session'
                    record=dict(command);state['requests'].append(record);save()
                    ticket=await call('send_headless_request',dict(command=command['command'],arguments=command.get('args',{}),kind=kind,expected_session=session))
                    record['ticket']=ticket;save()
                    deadline=time.monotonic()+(125 if kind=='save' else 65)
                    while True:
                        reply=await call('read_headless_result',{'request_id':ticket['id']})
                        if reply['status']=='received':
                            record['response']=reply['response'];save();assert reply['response']['ok'],reply
                            break
                        if reply['status']=='timeout_unknown' or time.monotonic()>deadline:raise RuntimeError('Unknown outcome; do not replay')
                        await asyncio.sleep(.2)
                state['receiverAfter']=await call('headless_status',{})
                assert state['receiverAfter']['receiver']['session']==session and state['receiverAfter']['pending'] is None
                state['status']='completed'
    except BaseException as exc:
        state['status']='stopped_incomplete';state['error']=repr(exc)
    finally:
        state['finishedAt']=time.time();save();print(json.dumps({'status':state['status'],'error':state.get('error'),'requests':len(state['requests'])}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('spec',type=Path);asyncio.run(main(p.parse_args().spec))
