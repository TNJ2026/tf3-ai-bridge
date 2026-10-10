"""Bounded follow-up: recover an archived result and read current map, no mutations."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    out = ROOT / 'output/live-validation-20261009/headless_read_followup'
    out.mkdir(exist_ok=True)
    target = out / 'result.json'
    if target.exists():
        raise RuntimeError('Evidence exists; do not replay this acceptance run')
    previous = json.loads((out.parent/'headless_soak/soak_state.json').read_text(encoding='utf-8'))
    deploy = json.loads((out.parent/'headless_soak/deployment.json').read_text(encoding='utf-8'))
    directory = Path('D:/Program Files/Steam/userdata/1112836998/3493540/local/tf3_mcp')
    state = {'status':'started', 'startedAt':time.time(), 'requests':[], 'worldMutations':0}
    def save():
        tmp=target.with_suffix('.tmp')
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(tmp,target)
    save()
    env=dict(os.environ,PYTHONPATH=str(ROOT/'server/src'),TF3_MCP_DIR=str(directory),TF3_MCP_HEADLESS_MOD=deploy['modContent'])
    try:
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','tf3_mcp.server'],env=env)) as (rd,wr):
            async with ClientSession(rd,wr) as client:
                await client.initialize()
                async def call(name,args):
                    r=await client.call_tool(name,args)
                    if r.is_error: raise RuntimeError(str(r.content))
                    return r.structured_content or json.loads(r.content[0].text)
                original=previous['requests'][0]
                recovery=await call('read_headless_result',{'request_id':original['ticket']['id']})
                assert recovery['response']==original['response']
                state['archivedMcpRecovery']=recovery
                state['receiverBefore']=await call('headless_status',{})
                receiver=state['receiverBefore']['receiver']
                assert receiver['status']=='ready' and state['receiverBefore']['pending'] is None
                session=receiver['session'];state['session']=session;save()
                for command,args in [
                    ('get_game_state',{}),('get_map_info',{}),('get_finances',{}),
                    ('list_towns',{'limit':100}),('list_lines',{'limit':100,'mine_only':True}),
                    ('list_vehicles',{'limit':100,'mine_only':True}),
                    ('list_stations',{'limit':100,'mine_only':True}),
                    ('list_depots',{'limit':100,'mine_only':True}),
                    ('list_vehicle_models',{'limit':50,'carrier':'ROAD','include_unavailable':False})]:
                    ticket=await call('send_headless_request',dict(command=command,arguments=args,kind='read',expected_session=session))
                    record={'command':command,'arguments':args,'ticket':ticket};state['requests'].append(record);save()
                    end=time.monotonic()+65
                    while True:
                        result=await call('read_headless_result',{'request_id':ticket['id']})
                        if result['status']=='received':
                            record['result']=result;save()
                            assert result['response']['ok'],result
                            break
                        if result['status']=='timeout_unknown' or time.monotonic()>end:
                            raise RuntimeError('Unknown outcome; no replay')
                        await asyncio.sleep(.2)
                state['receiverAfter']=await call('headless_status',{})
                assert state['receiverAfter']['receiver']['session']==session
                assert state['receiverAfter']['pending'] is None
        state['status']='read_followup_passed'
    except BaseException as exc:
        state['status']='stopped_incomplete';state['error']=repr(exc)
    finally:
        state['finishedAt']=time.time();save()
        print(json.dumps({'status':state['status'],'requests':len(state['requests']),'error':state.get('error')}))


if __name__=='__main__':
    asyncio.run(main())
