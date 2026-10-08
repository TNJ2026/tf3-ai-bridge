"""Track real task wall time separately from explicitly marked exclusive waits."""
import argparse,datetime,json,time
from pathlib import Path
from fullmap_workflow import write_json

def update(data, action, now):
    if action=='start':
        if data:raise ValueError('Clock already exists; use another file for a new task')
        return {'started':now,'waits':[],'events':[]}
    if not data or 'started'not in data:raise ValueError('Start clock first')
    data=json.loads(json.dumps(data))
    if data.get('finished')is not None:raise ValueError('Clock already finished')
    if now<data['started'] or (data['events'] and now<data['events'][-1]['at']):raise ValueError('Clock moved backwards')
    if action=='wait-start':
        if data.get('waitingSince')is not None:raise ValueError('Already waiting')
        data['waitingSince']=now
    elif action=='wait-end':
        if data.get('waitingSince')is None:raise ValueError('No exclusive wait active')
        data['waits'].append([data.pop('waitingSince'),now])
    elif action=='finish':
        if data.get('waitingSince')is not None:data['waits'].append([data.pop('waitingSince'),now])
        data['finished']=now;data['wallSeconds']=now-data['started'];data['exclusiveWaitSeconds']=sum(b-a for a,b in data['waits']);data['planningSeconds']=data['wallSeconds']-data['exclusiveWaitSeconds']
    else:raise ValueError('Unknown action')
    data['events'].append({'action':action,'at':now})
    return data

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','wait-start','wait-end','finish']);p.add_argument('--file',type=Path,required=True);a=p.parse_args()
    d=json.loads(a.file.read_text('utf8'))if a.file.exists()else None
    d=update(d,a.action,time.time());write_json(a.file,d);print(json.dumps(d))
