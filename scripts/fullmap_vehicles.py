"""Buy exactly one starter vehicle per verified line, never repeat a purchase intent."""
import argparse,asyncio,json,sys,time
from pathlib import Path
from fullmap_lines import Lines
from fullmap_batch import *
class Vehicles(Lines):
 async def vehicle(self,t,action):
  source=(ROOT/'scripts/fullmap_vehicles.lua').read_text(encoding='utf8');return await self.eval(source.replace('TASKJSON',quote(t)).replace('local action=ACTION','local action='+json.dumps(action)))
 async def run(self):
  if 'line_specs' in self.p:raise StopBatch('Use fullmap_fleet.py with the current fleet_manifest.json; starter purchases cannot execute this plan')
  await self.session()
  if self.a.action=='build'and unfinished(self.ledger):raise StopBatch('Unreconciled submissions')
  if self.a.action=='build':await self.save('vehicles_before')
  facilities=super().tasks();done=0
  for t in self.specs():
   if t['mode']=='SMALL_SHIP'and any(p.get('purchase_capability_verified')is False for p in self.p.get('ports',[])):
    raise StopBatch('Ship acquisition capability unresolved; maintenance is not purchase authorization')
   if self.ledger['items'].get(t['id'],{}).get('status')!='static_verified':continue
   key=t['id']+'__starter';item=self.ledger['items'].setdefault(key,dict(kind='vehicle',attempts=0));await self.session()
   kinds={'TRUCK':'road_depot','HELICOPTER':'heliport','SMALL_SHIP':'water_depot'}
   t['depots']=[f for f in facilities if f['kind']==kinds[t['mode']]]
   if t['mode']=='SMALL_SHIP':t['depots']=[f for f in t['depots']if f['id']==t['id'].replace('_ship','_shipyard')]
   t['model']={'TRUCK':self.p['fleet_policy']['road_model'],'HELICOPTER':'::/vehicle/helicopter/piasecki_h21/piasecki_h21.mdl','SMALL_SHIP':'::/vehicle/ship/votrans_universal/votrans_universal.mdl'}[t['mode']]
   r=await self.vehicle(t,'verify')
   if r.get('existing'):
    expected=item.get('commit',{}).get('vehicles',[])
    if not item['attempts']or [v['id']for v in expected]!=[v['id']for v in r['vehicles']]:raise StopBatch(key+' unrecorded vehicles; reconcile')
    if any(v['noPath']for v in r['vehicles']):raise StopBatch(key+' vehicle reports noPath')
    item.update(audit=r,status='static_verified');self.flush();continue
   if item['attempts']:raise StopBatch(key+' purchase outcome missing; no retry')
   if self.a.action=='verify':continue
   r=await self.vehicle(t,'preview');item['preview']=r;self.flush()
   if self.a.action=='preview':print(key+': purchase depot round trip verified',flush=True);continue
   item.update(attempts=1,status='commit_started',intentTime=time.time());self.flush()
   try:
    r=await self.vehicle(t,'build');item['commit']=r;self.flush()
    if not r.get('accepted')or not r.get('verified'):raise StopBatch(key+' purchase or assignment incomplete')
    r=await self.vehicle(t,'verify')
    if len(r['vehicles'])!=1 or r['vehicles'][0]['noPath']:raise StopBatch(key+' vehicle readback failed')
    item.update(audit=r,status='static_verified');self.flush();done+=1;print(key+': purchased 1 + assigned + noPath=false',flush=True)
   except BaseException:item['status']='needs_reconciliation';self.flush();raise
   if done%10==0:await self.save('vehicles_'+str(done))
   if self.a.limit and done>=self.a.limit:break
  if self.a.action=='build':await self.save('vehicles_after')
async def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['preview','build','verify'],nargs='?',default='preview');ap.add_argument('--plan',type=Path,default=PLAN);ap.add_argument('--output',type=Path,default=ROOT/'exports/fullmap_plan_20261003/execution');ap.add_argument('--line-ids');ap.add_argument('--limit',type=int,default=0);a=ap.parse_args();a.ids=None;b=Vehicles(a)
 try:
  with batch_lock(b.b.dir):await b.run()
 except Exception as e:b.ledger['events'].append(dict(stopped=str(e),time=time.time()));b.flush();print('STOP: '+str(e),file=sys.stderr);return 2
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
