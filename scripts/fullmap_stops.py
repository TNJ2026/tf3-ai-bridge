"""Current build_street_stop interface with endpoint re-resolution and one-shot journal."""
import argparse,asyncio,json,time,sys
from pathlib import Path
from fullmap_batch import Batch,PLAN,ROOT,quote,batch_lock,unfinished,StopBatch

def receipt_matches(task,item,audit,items):
 """Read-only acceptance of a submitted stop or a recorded one-hop reuse."""
 receipt=item
 if item.get('alias'):
  if item.get('attempts') or item['alias']==task['id']:return False
  receipt=items.get(item['alias'],{})
  if receipt.get('alias') or receipt.get('kind')!='street_stop' or receipt.get('status')!='static_verified':return False
 expected={s['id']for s in receipt.get('commit',{}).get('stations',[])}
 actual={s['id']for s in audit.get('objects',[])}
 covered=set().union(*(set(s.get('catchables',[]))for s in audit.get('objects',[])))
 return bool(expected) and bool(audit.get('verified')) and expected==actual and set(task['covered_building_hints'])<=covered

class Stops(Batch):
 async def audit(self,t):return await self.eval((ROOT/'scripts/fullmap_stop_audit.lua').read_text(encoding='utf-8-sig').replace('TASKJSON',quote(t)))
 async def verify_batches(self):
  size=getattr(self.a,'read_batch_size',8)
  if not 1<=size<=16:raise ValueError('read_batch_size must be 1..16')
  tasks=[t for t in self.p['city_stops']if not self.a.stop_ids or t['id']in self.a.stop_ids.split(',')]
  if self.a.limit:tasks=tasks[:self.a.limit]
  body=(ROOT/'scripts/fullmap_stop_audit.lua').read_text('utf-8-sig').replace('local task=B.json.decode(TASKJSON);','')
  for offset in range(0,len(tasks),size):
   await self.session();chunk=tasks[offset:offset+size]
   code='local tasks=B.json.decode('+quote(chunk)+');local function inspect(task) '+body+' end;local out={};for _,task in ipairs(tasks)do out[#out+1]={id=task.id,result=B.json.decode(inspect(task))}end;return B.json.encode(out)'
   rows=await self.eval(code)
   if not isinstance(rows,list)or [r.get('id')for r in rows]!=[t['id']for t in chunk]:raise StopBatch('Incomplete stop audit batch')
   failed=False
   for t,row in zip(chunk,rows):
    item=self.ledger['items'].setdefault(t['id'],{'kind':'street_stop','attempts':0});audit=row['result']
    if not audit['objects']:status='submission_absent_requires_review'if item['attempts']else'not_built'
    else:
     # Unrecorded objects are evidence to reconcile, never implicit adoption.
     status='static_verified'if receipt_matches(t,item,audit,self.ledger['items']) else'needs_reconciliation'
    item.update(audit=audit,status=status);failed|=status in ('needs_reconciliation','submission_absent_requires_review')
   self.flush()
   if failed:raise StopBatch('Stop audit requires reconciliation')
  self.ledger['lastAction']='verify';self.flush()
 async def run(self):
  if self.a.action=='verify'and getattr(self.a,'read_batch_size',8)>1:return await self.verify_batches()
  await self.session()
  # Historical business ledger entries do not gate unrelated work.
  if self.a.action=='build':await self.save('stops_before')
  done=0
  for t in self.p['city_stops']:
   if self.a.stop_ids and t['id']not in self.a.stop_ids.split(','):continue
   key=t['id'];item=self.ledger['items'].setdefault(key,{'kind':'street_stop','attempts':0});await self.session();audit=await self.audit(t)
   if audit['objects']:
    if not item['attempts']:
     actual={s['id']for s in audit['objects']};covered=set().union(*(set(s['catchables'])for s in audit['objects']))
     owners=[k for k,v in self.ledger['items'].items()if k!=key and v.get('kind')=='street_stop'and v.get('status')=='static_verified'and {s['id']for s in v.get('audit',{}).get('objects',[])}==actual]
     if len(owners)!=1 or not audit['verified']or not set(t['covered_building_hints'])<=covered:raise StopBatch(key+' unrecorded/insufficient existing stop coverage; inspect before reuse')
     item.update(audit=audit,status='static_verified',alias=owners[0],reason='Same road already has verified stop pair covering every planned target; reuse without duplicate street objects');self.flush();print(key+': coverage verified, reuse '+owners[0],flush=True);continue
    expected={s['id']for s in item.get('commit',{}).get('stations',[])}
    if not audit['verified']or expected!={s['id']for s in audit['objects']}:raise StopBatch(key+' stop readback mismatch')
    item.update(audit=audit,status='static_verified');self.flush();continue
   if item['attempts']:raise StopBatch(key+' previous stop submit missing; no automatic retry')
   if self.a.action=='verify':item['status']='not_built';self.flush();continue
   args={'edge':audit['edge'],'param':t['param'],'side':t['side'],'kind':t['kind'],'two_sided':t['two_sided'],'name':key,'preview':True}
   preview=await self.eval('return B.json.encode(B.commands.build_street_stop(B.json.decode('+quote(args)+')))');item['preview']=preview;self.flush()
   if not preview.get('ok')or not preview.get('topology',{}).get('valid')or preview.get('collisions'):raise StopBatch(key+' topology/geometry preview rejected')
   if self.a.action=='preview':print(key+': stop preview passed',flush=True);continue
   fresh=await self.audit(t)
   if fresh!=audit:raise StopBatch('Stop road changed')
   item.update(attempts=1,status='commit_started');self.flush();args['preview']=False
   try:
    result=await self.eval('return B.json.encode(B.commands.build_street_stop(B.json.decode('+quote(args)+')))');item['commit']=result;self.flush()
    if not result.get('built')or not result.get('verified'):raise StopBatch(key+' stop commit incomplete')
    readback=await self.audit(t);item['audit']=readback
    if not readback['verified']:raise StopBatch(key+' stop topology audit failed')
    item['status']='static_verified';self.flush();done+=1;print(key+': built once + topology verified',flush=True)
   except BaseException:item['status']='needs_reconciliation';self.flush();raise
   if done%10==0:await self.save('stops_'+str(done))
   if self.a.limit and done>=self.a.limit:break
  if self.a.action=='build':await self.save('stops_after')
async def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['preview','build','verify'],nargs='?',default='preview');ap.add_argument('--plan',type=Path,default=PLAN);ap.add_argument('--output',type=Path,default=ROOT/'exports/fullmap_plan_20261003/execution');ap.add_argument('--stop-ids');ap.add_argument('--limit',type=int,default=0);ap.add_argument('--read-batch-size',type=int,choices=range(1,17),default=8);a=ap.parse_args();a.ids=None;b=Stops(a)
 try:
  with batch_lock(b.b.dir):await b.run()
 except Exception as e:b.ledger['events'].append({'stopped':str(e),'time':time.time()});b.flush();print('STOP: '+str(e),file=sys.stderr);return 2
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
