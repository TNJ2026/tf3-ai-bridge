"""Manifest-driven purchases: one vehicle per persisted intent, fresh checks, stop on ambiguity."""
import argparse,asyncio,json,sys,time
from pathlib import Path
from fullmap_lines import Lines
from fullmap_batch import ROOT,quote,batch_lock,unfinished,StopBatch

def fleet_rows(policy, plan, digest):
 if policy.get('planDigest')!=digest:raise StopBatch('Fleet and route plan differ')
 modern='vehicles' in policy
 rows=[dict(id=r['line'],model=r['model'],cargos=r['cargos'],count=r['quantity'],depot=r['depot']) for r in policy['vehicles']] if modern else policy['lines']
 ids=[r['id'] for r in rows]
 if len(ids)!=len(set(ids)):raise StopBatch('Duplicate fleet line')
 if modern and set(ids)!={l['id'] for l in plan['line_specs']}:raise StopBatch('Fleet does not cover exact planned lines')
 facilities={f['id']:f for f in plan.get('facilities',[])+plan.get('ports',[])}
 lines={l['id']:l for l in plan.get('line_specs',[])}
 for r in rows:
  if type(r['count'])is not int or r['count']<=0:raise StopBatch('Positive integer fleet count required')
  if not isinstance(r['model'],str) or not r['model']:raise StopBatch('Explicit vehicle model required')
  if modern:
   line=lines[r['id']];kind={'TRUCK':'road_depot','HELICOPTER':'heliport','SMALL_SHIP':'water_depot'}[line['mode']]
   if facilities.get(r['depot'],{}).get('kind')!=kind:raise StopBatch('Wrong or missing purchase depot')
   if set(r['cargos'])!={int(c) for c in line['cargos']}:raise StopBatch('Fleet cargo mismatch')
   if r['model']!=line['vehicle_model'] or r['count']!=line['fleet_forecast']:raise StopBatch('Fleet model/count differs from plan')
 return rows

class Fleet(Lines):
 async def vehicle(self,t,action):
  source=(ROOT/'scripts/fullmap_fleet.lua').read_text(encoding='utf8')
  return await self.eval(source.replace('TASKJSON',quote(t)).replace('local action=ACTION','local action='+json.dumps(action)))
 async def run(self):
  policy=json.loads(self.a.fleet.read_text(encoding='utf8'))
  policy_rows=fleet_rows(policy,getattr(self,'p',{}),self.ledger['planDigest'])
  await self.session()
  if self.a.action=='build'and unfinished(self.ledger):raise StopBatch('Unreconciled submissions')
  if self.a.action=='build':await self.save('fleet_before')
  specs={s['id']:s for s in self.specs()};facilities=self.tasks();done=0
  rows=[r for r in policy_rows if r['id']in specs]
  if not rows:raise StopBatch('No selected fleet lines')
  # Representatives first, then round-robin so a whole line is never blindly bulk-purchased.
  rows.sort(key=lambda r:(0 if r['id']=='LINE001'else 1 if r['id']=='LINE002'else 2 if r['id']=='LINE011'else 3,r['id']))
  for ordinal in range(1,max(r['count']for r in rows)+1):
   for row in rows:
    if ordinal>row['count']:continue
    sid=row['id'];key=f'{sid}__fleet_{ordinal:02d}';item=self.ledger['items'].setdefault(key,dict(kind='vehicle',attempts=0))
    await self.session();spec=specs[sid]
    if self.ledger['items'].get(sid,{}).get('status')!='static_verified':raise StopBatch('Line not verified '+sid)
    actual=await self.line(spec,'verify')
    if not actual.get('existing')or not actual.get('verified'):raise StopBatch('Line changed '+sid)
    expected=sorted(v['id']for k,it in self.ledger['items'].items()if k.startswith(sid+'__fleet_')and it.get('status')=='static_verified'for v in it['commit']['newVehicles'])
    kind={'TRUCK':'road_depot','BUS':'road_depot','HELICOPTER':'heliport','SMALL_SHIP':'water_depot'}[spec['mode']]
    task=dict(spec,model=row['model'],cargos=row['cargos'],expectedVehicles=expected,
      origin=spec['endpoints'][0].get('position',spec['endpoints'][0].get('stop',{}).get('position')),depots=[f for f in facilities if f['kind']==kind and (not row.get('depot') or f['id']==row['depot'])])
    if row.get('depot') and len(task['depots'])!=1:raise StopBatch('Planned purchase depot missing or ambiguous')
    current=await self.vehicle(task,'verify')
    if sorted(v['id']for v in current['vehicles'])!=expected:raise StopBatch(sid+' unrecorded fleet; reconcile')
    if any(v['noPath']or v['userStopped']for v in current['vehicles']):raise StopBatch(sid+' vehicle path/stopped problem')
    if item['attempts']:
     if item.get('status')!='static_verified':raise StopBatch(key+' ambiguous purchase')
     continue
    if self.a.action=='verify':raise StopBatch(key+' not purchased')
    preview=await self.vehicle(task,'preview');item['preview']=preview;self.flush()
    if self.a.action=='preview':continue
    item.update(attempts=1,status='commit_started',intentTime=time.time(),spec=task);self.flush()
    try:
     result=await self.vehicle(task,'build');item['commit']=result;self.flush()
     if not result.get('verified'):raise StopBatch(key+' purchase/assignment/readback incomplete')
     audit=await self.vehicle(task,'verify')
     wanted=sorted(expected+[result['newVehicles'][0]['id']])
     if sorted(v['id']for v in audit['vehicles'])!=wanted or any(v['noPath']or v['userStopped']for v in audit['vehicles']):raise StopBatch(key+' independent audit failed')
     item.update(status='static_verified',audit=audit);self.flush();done+=1
     print(key+': bought once, assigned, cargo compatible, noPath=false',flush=True)
    except BaseException:
     item['status']='needs_reconciliation';self.flush();raise
    if done%10==0:await self.save('fleet_checkpoint')
    if self.a.limit and done>=self.a.limit:
     await self.save('fleet_checkpoint');return
  if self.a.action=='build':await self.save('fleet_after')

async def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['preview','build','verify'])
 ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--fleet',type=Path,required=True)
 ap.add_argument('--line-ids');ap.add_argument('--limit',type=int,default=0);a=ap.parse_args();a.ids=None;b=Fleet(a)
 try:
  with batch_lock(b.b.dir):await b.run()
 except Exception as e:
  b.ledger['events'].append(dict(stopped=str(e),time=time.time()));b.flush();print('STOP: '+str(e),file=sys.stderr);return 2
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
