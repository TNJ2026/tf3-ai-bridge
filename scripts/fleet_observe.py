"""Bounded 1x departure observation; restore prior pause and save only healthy result."""
import argparse,asyncio,json,time
from pathlib import Path
from types import SimpleNamespace
from fullmap_lines import Lines
from fullmap_batch import ROOT,batch_lock,write_json,StopBatch

async def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seconds',type=int,default=45)
 a=ap.parse_args();a.action='preview';a.line_ids=None;a.ids=None;b=Lines(a)
 source=(ROOT/'scripts/fleet_audit.lua').read_text(encoding='utf8');trace={'samples':[],'operationalAccepted':False}
 with batch_lock(b.b.dir):
  initial=await b.session()
  if initial['speedup']!=0:raise StopBatch('Expected paused world; do not override user speed')
  trace['before']=await b.eval(source);write_json(a.output/'fleet_observation.json',trace)
  if any(v['noPath']or v['userStopped'] for v in trace['before']['vehicles']):raise StopBatch('Departure gate failed')
  healthy=False
  try:
   await b.call('set_game_speed',{'speed':1});start=time.monotonic()
   while time.monotonic()-start<a.seconds:
    await asyncio.sleep(5)
    snapshot=await b.eval(source);snapshot['wallSeconds']=time.monotonic()-start
    trace['samples'].append(snapshot);write_json(a.output/'fleet_observation.json',trace)
    if snapshot['state']['speedup']!=1:raise StopBatch('User speed changed; observation ended')
    if any(v['noPath'] for v in snapshot['vehicles']):raise StopBatch('Vehicle noPath during observation')
    print('observed %.1fs; %d vehicles; noPath=0'%(snapshot['wallSeconds'],len(snapshot['vehicles'])),flush=True)
   healthy=True
  finally:
   if b.b.heartbeat().get('connected'):
    await b.call('set_game_speed',{'speed':0})
    trace['after']=await b.eval(source);trace['restoredPaused']=trace['after']['state']['speedup']==0
   trace['observationCompleted']=healthy;write_json(a.output/'fleet_observation.json',trace)
  if healthy:await b.save('fleet_observed')

if __name__=='__main__':asyncio.run(main())
