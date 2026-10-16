"""Staged single-line acceptance; never replay an existing stage."""
import asyncio
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/live-validation-20261009/no_gui_line_adapter'
DIRECTORY=Path('D:/Program Files/Steam/userdata/1112836998/3493540/local/tf3_mcp')

async def main(stage):
    target=OUT/(stage+'.json')
    if target.exists(): raise RuntimeError('Stage already exists; reconcile, never replay')
    deployment=json.loads((OUT/'deployment.json').read_text(encoding='utf-8'))
    state={'status':'started','requests':[],'startedAt':time.time()}
    def save():
        temp=target.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=True,indent=2),encoding='utf-8');os.replace(temp,target)
    save()
    env=dict(os.environ,PYTHONPATH=str(ROOT/'server/src'),TF3_MCP_DIR=str(DIRECTORY),TF3_MCP_NO_GUI_MOD=deployment['modContent'])
    try:
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','tf3_mcp.server'],env=env)) as (rd,wr):
            async with ClientSession(rd,wr) as client:
                await client.initialize()
                async def call(name,args):
                    r=await client.call_tool(name,args)
                    if r.is_error: raise RuntimeError(str(r.content))
                    return r.structured_content or json.loads(r.content[0].text)
                status=await call('no_gui_status',{});state['receiverBefore']=status
                row=status['receiver'];assert row['generation']==deployment['generation'] and row['status']=='ready' and status['pending'] is None
                session=row['session'];state['session']=session;save()
                async def query(command,args=None,kind='read'):
                    ticket=await call('send_no_gui_request',dict(command=command,arguments=args or {},kind=kind,expected_session=session))
                    record={'command':command,'arguments':args or {},'ticket':ticket};state['requests'].append(record);save()
                    deadline=time.monotonic()+65
                    while True:
                        reply=await call('read_no_gui_result',{'request_id':ticket['id']})
                        if reply['status']=='received':
                            record['response']=reply['response'];save();assert reply['response']['ok'],reply
                            return reply['response']['result']
                        if reply['status']=='timeout_unknown' or time.monotonic()>deadline:raise RuntimeError('Unknown outcome, no replay')
                        await asyncio.sleep(.2)
                state['game']=await query('get_game_state')
                state['map']=await query('get_map_info')
                state['lines']=await query('list_lines',{'limit':100,'mine_only':True})
                state['stations']=await query('list_stations',{'limit':100,'mine_only':True})
                if stage in ('inspect','create'):
                    plan=json.loads((OUT/'live_plan.json').read_text(encoding='utf-8'))
                    assert session==plan['session']
                    assert sorted(state['map']['towns'],key=lambda x:x['id'])==plan['towns']
                    current={v['id']:v for v in state['stations']['stationGroups']}
                    for station in plan['stations']:assert current[station['id']]==station
                    assert not any(v['name']==plan['name'] for v in state['lines']['lines'])
                    for station in plan['stations']:
                        detail=await query('get_entity',{'id':station['stations'][0]},'build')
                        assert detail['components']['PLAYER_OWNED']['player']==state['game']['player']
                        terminal=detail['components']['STATION']['terminals'][0]
                        assert terminal['passengersLoad'] and not terminal['cargoLoad']
                if stage=='create':
                    inspection=json.loads((OUT/'inspect.json').read_text(encoding='utf-8'))
                    assert inspection['status']=='inspect_completed' and inspection['session']==session
                    source=Path(plan['save']);before=source.stat();assert before.st_size>0
                    digest=hashlib.sha256(source.read_bytes()).hexdigest()
                    backup=OUT/'pre_line.sav';assert not backup.exists();shutil.copy2(source,backup)
                    await asyncio.sleep(1)
                    after=source.stat()
                    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
                    assert hashlib.sha256(backup.read_bytes()).hexdigest()==digest==hashlib.sha256(source.read_bytes()).hexdigest()
                    state['backup']={'path':str(backup),'source':str(source),'sha256':digest,'size':before.st_size,'sourceMtime':before.st_mtime};save()
                    state['created']=await query('create_line',{'station_groups':[v['id'] for v in plan['stations']],'name':plan['name']},'build')
                    state['linesAfter']=await query('list_lines',{'limit':100,'mine_only':True})
                    state['entityAfter']=await query('get_entity',{'id':state['created']['line']},'build')
                    state['vehiclesAfter']=await query('list_vehicles',{'limit':100,'mine_only':True})
                state['receiverAfter']=await call('no_gui_status',{})
                assert state['receiverAfter']['receiver']['session']==session and state['receiverAfter']['pending'] is None
                state['status']=stage+'_completed'
    except BaseException as exc:
        state['status']='stopped_incomplete';state['error']=repr(exc)
    finally:
        state['finishedAt']=time.time();save();print(json.dumps({'status':state['status'],'error':state.get('error'),'requests':len(state['requests'])}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['survey','inspect','create']);asyncio.run(main(p.parse_args().stage))
