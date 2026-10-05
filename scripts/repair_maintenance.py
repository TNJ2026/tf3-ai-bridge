"""Supplemental maintenance batch; current map fingerprint, journal and native saves."""
import asyncio,argparse,json
from types import SimpleNamespace
from fullmap_batch import *
OUT=ROOT/'exports/maintenance_repair_20261003'
class MaintenanceBatch(Batch):
 async def session(self):
  state=await self.call('get_game_state');world=await self.call('get_map_info');baseline=json.loads((OUT/'survey.json').read_text(encoding='utf8'))
  baseline['map']['industries']+=self.ledger.get('sessionAdditions',[])
  if fingerprint(world)!=fingerprint(baseline['map'])or state['player']!=baseline['state']['player']:raise StopBatch('Maintenance survey map changed; reconcile first')
  if self.prev and any(state[k]<self.prev[k]for k in ['gameTime','tickCount']):raise StopBatch('Session regressed; reconcile first')
  if self.a.action=='build'and state['speedup']!=0:raise StopBatch('Construction requires paused game')
  self.prev=state;self.ledger['lastState']=state;self.flush();return state
 def tasks(self):return json.loads((OUT/'selected.json').read_text(encoding='utf8'))
async def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['select','build','verify']);a=ap.parse_args();b=MaintenanceBatch(SimpleNamespace(plan=PLAN,output=OUT,action=a.action,ids=None,limit=0))
 with batch_lock(b.b.dir):
  await b.session()
  if a.action=='select':
   selected=[];trials=[]
   for area in json.loads((OUT/'candidates.json').read_text(encoding='utf8')):
    for t in area['candidates']:
     r=await b.facility(t,'preview');trials.append(dict(task=t,result=r));write_json(OUT/'previews.json',trials)
     print(t['id'],r.get('previewPassed'),r.get('preview',{}).get('infos'),r.get('preview',{}).get('collisions'),flush=True)
     if r.get('previewPassed'):selected.append(t);break
    else:raise StopBatch(area['area']+' has no accepted candidate')
   write_json(OUT/'selected.json',selected)
  else:await b.run()
if __name__=='__main__':asyncio.run(main())
