"""Resolve native terminals and closed paths, initialize cargo filters, commit once."""
import argparse,asyncio,json,sys,time
from pathlib import Path
from fullmap_batch import Batch,PLAN,ROOT,quote,batch_lock,unfinished,StopBatch
class Lines(Batch):
 def specs(self):
  facilities={f['id']:f for f in super().tasks()};industries={i['id']:i for i in self.p['industries']};stops={s['id']:s for s in self.p['city_stops']}
  def facility(key,loads):return dict(id=key,position=facilities[key]['position'],loads=loads)
  def industry(key,loads):return dict(id='industry_'+str(key),position=industries[key]['position'],loads=loads)
  def endpoints(key,loads):
   if isinstance(key,dict):return [industry(key['existing_industry'],loads)]
   if isinstance(key,list):
    unique=list(dict.fromkeys(self.ledger['items'].get(k,{}).get('alias',k)for k in key))
    return [dict(id=k,stop=stops[k],loads=loads)for k in unique]
   return [facility(key,loads)]
  rows=[]
  if 'line_specs' in self.p:
   def modern_end(key,loads,terminal):
    if isinstance(key,dict)and 'town'in key:
     return endpoints(key['unload_stops'],loads)
    result=endpoints(key,loads)
    if terminal is not None:
     for ep in result:ep['terminal_index']=terminal
    return result
   for r in self.p['line_specs']:
    air=r['mode']=='HELICOPTER'
    rows.append(dict(id=r['id'],name='全图供给·'+r['id'],mode=r['mode'],
     endpoints=modern_end(r['source'],r['load_at_source'],r.get('source_terminal_index')if air else None)+modern_end(r['destination'],r.get('load_at_destination',[]),r.get('destination_terminal_index')if air else None)))
   if self.a.line_ids:rows=[r for r in rows if r['id']in self.a.line_ids.split(',')]
   return rows
  for r in self.p['industry_shuttles']:rows.append(dict(id=r['id'],mode='TRUCK',endpoints=[industry(r['industry'],r['output_cargos']),facility(r['hub_station'],r['input_cargos'])]))
  for r in self.p['routes']:rows.append(dict(id=r['id'],mode=r['mode'],endpoints=endpoints(r['start'],[r['cargo']])+endpoints(r['end'],[])))
  for r in self.p['city_delivery']:
   if r.get('status')!='active':continue
   eps=[facility(r['start'],r['cargos'])];seen=set()
   for key in r['stops']:
    key=self.ledger['items'].get(key,{}).get('alias',key)
    if key not in seen:eps.append(dict(id=key,stop=stops[key],loads=[]));seen.add(key)
   rows.append(dict(id=r['id'],mode='TRUCK',endpoints=eps))
  for p in self.p['ports']:
   r=p['ship_route'];rows.append(dict(id=r['id'],mode='SMALL_SHIP',endpoints=[industry(r['source_industry'],[r['cargo']]),facility(r['destination'],[])]))
   r=p['feeder_route'];rows.append(dict(id=r['id'],mode='TRUCK',endpoints=[facility(r['from'],[r['cargo']]),facility(r['to'],[])]))
  for r in rows:r['name']='全图供给·'+r['id']
  if self.a.line_ids:rows=[r for r in rows if r['id']in self.a.line_ids.split(',')]
  return rows
 async def line(self,t,action):
  source=(ROOT/'scripts/fullmap_lines.lua').read_text(encoding='utf8');return await self.eval(source.replace('TASKJSON',quote(t)).replace('local action=ACTION','local action='+json.dumps(action)))
 async def run(self):
  await self.session()
  if self.a.action=='build'and unfinished(self.ledger):raise StopBatch('Unreconciled submissions')
  if self.a.action=='build':await self.save('lines_before')
  done=0
  for t in self.specs():
   key=t['id'];item=self.ledger['items'].setdefault(key,dict(kind='line',attempts=0));await self.session()
   r=await self.line(t,'preview');item['preview']=r;self.flush()
   if r.get('existing'):
    if not item['attempts']:raise StopBatch(key+' unrecorded existing line')
    item.update(audit=r,status='static_verified');self.flush();continue
   if item['attempts']:raise StopBatch(key+' submitted line missing; do not retry')
   if self.a.action!='build':print(key+': native circuit verified',flush=True);continue
   item.update(attempts=1,status='commit_started',intentTime=time.time(),spec=t);self.flush()
   try:
    r=await self.line(t,'build');item['commit']=r;self.flush()
    if not r.get('accepted')or not r.get('verified'):raise StopBatch('Line creation/readback incomplete')
    r=await self.line(t,'verify')
    if not r.get('verified'):raise StopBatch('Line verification failed')
    item.update(audit=r,status='static_verified');self.flush();done+=1;print(key+': built once + native circuit/cargo verified',flush=True)
   except BaseException:item['status']='needs_reconciliation';self.flush();raise
   if done%10==0:await self.save('lines_'+str(done))
   if self.a.limit and done>=self.a.limit:break
  if self.a.action=='build':await self.save('lines_after')
async def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['preview','build','verify'],nargs='?',default='preview');ap.add_argument('--plan',type=Path,default=PLAN);ap.add_argument('--output',type=Path,default=ROOT/'exports/fullmap_plan_20261003/execution');ap.add_argument('--line-ids');ap.add_argument('--limit',type=int,default=0);a=ap.parse_args();a.ids=None;b=Lines(a)
 try:
  with batch_lock(b.b.dir):await b.run()
 except Exception as e:b.ledger['events'].append(dict(stopped=str(e),time=time.time()));b.flush();print('STOP: '+str(e),file=sys.stderr);return 2
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
