"""Resumable full-map construction batches. Default action is read-only preview.
Fresh native preview and one commit share an engine invocation. Unknown outcomes
lock further writes until read-only reconciliation; never replay historical IDs.
"""
from __future__ import annotations
import argparse,asyncio,functools,hashlib,json,sys,time,uuid
from pathlib import Path
from batch_warehouses import ROOT,Bridge,StopBatch,batch_lock,write_json,fingerprint
from fullmap_identity import unique_ids
PLAN=ROOT/'exports/fullmap_plan_20261003/network_plan.json'

def quote(v):
 text=json.dumps(v,ensure_ascii=False,separators=(',',':'));eq='======'
 while ']'+eq+']' in text:eq+='='
 return '['+eq+'['+text+']'+eq+']'

def preview_ok(r):return r.get('previewPassed')is True

def unfinished(ledger):return[k for k,v in ledger['items'].items()if v.get('attempts',0)>0 and v.get('status')not in ['static_verified','connection_verified','not_applicable','reconciled_rejected']]

def map_save_key(plan):
 # Town centres survive plan revisions, renaming and resource exploration.
 # Do not use mutable industries, task IDs, or plan bytes as a save identity.
 points=sorted((round(t['position']['x'],2),round(t['position']['y'],2)) for t in plan['cities'])
 if not points:raise StopBatch('Cannot identify map save slot without town centres')
 return hashlib.sha256(json.dumps(points,separators=(',',':')).encode()).hexdigest()[:16]

def save_slot(phase,map_key):
 # Keep recovery baselines and abnormal-world evidence outside the rolling slot.
 if 'before' in phase.split('_') or any(word in phase for word in ('map_changed','failure','crash','diagnostic')):
  return 'tf3_fullmap_'+phase+'_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6],False
 return 'tf3_fullmap_auto_map_'+map_key[:16],True

def save_signature(path):
 try:
  st=path.stat();return st.st_size,st.st_mtime_ns,st.st_ctime_ns,st.st_ino
 except FileNotFoundError:return None

def timed_stage(label):
 def decorate(fn):
  @functools.wraps(fn)
  async def wrapped(self,*args,**kwargs):
   started=time.perf_counter();failed=True
   try:
    result=await fn(self,*args,**kwargs);failed=False;return result
   finally:self.record_timing(label,started,failed)
  return wrapped
 return decorate

class Batch:
 def __init__(self,args,bridge=None):
  self.a=args;self.b=bridge or Bridge();self.p=json.loads(args.plan.read_text(encoding='utf-8'));self.out=args.output;self.path=self.out/'ledger.json';self.source=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8');self.lua=(ROOT/'scripts/fullmap_facility.lua').read_text(encoding='utf-8-sig')
  digest=hashlib.sha256(args.plan.read_bytes()).hexdigest()
  # Fail before session queries/native previews; never silently overwrite duplicate IDs.
  unique_ids([f for f in self.p['facilities'] if not f.get('status','').startswith('reserve')]+self.p.get('ports',[]))
  self.ledger=json.loads(self.path.read_text(encoding='utf-8'))if self.path.exists()else{'schema':1,'planDigest':digest,'items':{},'events':[],'authorization':'Planning evidence grants no build authorization; build invocation requires explicit current user scope','operationalAccepted':False}
  if self.ledger['planDigest']!=digest:raise StopBatch('Plan digest changed; reconcile ledger before changing execution plan')
  self.prev=self.ledger.get('lastState')
 def flush(self):write_json(self.path,self.ledger)
 def record_timing(self,label,started,failed=False):
  elapsed=time.perf_counter()-started
  row=self.ledger.setdefault('performance',{}).setdefault(label,{'calls':0,'seconds':0,'maxSeconds':0,'failures':0})
  row['calls']+=1;row['seconds']+=elapsed;row['maxSeconds']=max(row['maxSeconds'],elapsed);row['failures']+=int(failed)
 async def call(self,command,args=None,engine=True):
  if not self.b.heartbeat().get('connected'):raise StopBatch('Bridge heartbeat stale')
  started=time.perf_counter();failed=True
  try:
   r=await self.b.call(command,args or{},engine=engine,timeout=45)
   result=json.loads(r)if isinstance(r,str)else r;failed=False;return result
  finally:self.record_timing('bridge.'+command,started,failed)
 async def eval(self,code):
  eq='========';assert ']'+eq+']'not in self.source
  pre='local env=setmetatable({},{__index=_G});local B=assert(load(['+eq+'['+self.source+']'+eq+'],"=fullmap_batch_bridge","t",env))()._internal;'
  return await self.call('eval',{'code':pre+code})
 @timed_stage('session')
 async def session(self):
  # Read both in one engine invocation, with no cross-item entity cache.
  snapshot=await self.eval('return B.json.encode({state=B.commands.get_game_state({}),world=B.commands.get_map_info({})})')
  return self.accept_session(snapshot)
 def accept_session(self,snapshot):
  state,world=snapshot['state'],snapshot['world']
  expected={'towns':self.p['cities'],'industries':[dict(i,fileName=i['resource'])for i in self.p['industries']]}
  expected['industries']+=self.ledger.get('sessionAdditions',{}).get('industries',[])
  if fingerprint(world)!=fingerprint(expected)or state['player']!=self.p['session']['player']:raise StopBatch('Current map does not match planned towns/industry resources and positions')
  if self.prev and any(state[k]<self.prev[k]for k in ['tickCount','gameTime']):raise StopBatch('Game reloaded/time regressed; explicit reconciliation required')
  if self.a.action=='build'and state['speedup']!=0:raise StopBatch('World must remain paused during batch construction')
  self.prev=state;self.ledger['lastState']=state;self.flush();return state
 @timed_stage('save')
 async def save(self,phase):
  key=map_save_key(self.p)
  name,rolling=save_slot(phase,key);path=self.b.dir.parent/'save'/(name+'.sav')
  baseline=save_signature(path)
  event={'nativeSaveRequested':name,'phase':phase,'mapSaveKey':key,'rolling':rolling,'replacesExisting':baseline is not None,'requestedAt':time.time()};self.ledger['events'].append(event);self.flush()
  await self.call('eval',{'code':f'app.saveGame("{name}",function() end,false,true);return {{requested=true}}'},False)
  previous=None
  for _ in range(60):
   current=save_signature(path)
   # An unchanged old save is not proof that an overwrite completed.
   if current is not None and current[0]>0 and current!=baseline and current==previous:
    event.update(file=str(path),bytes=current[0],complete=True,completedAt=time.time());self.flush();return
   previous=current
   await asyncio.sleep(.5)
  raise StopBatch('Native save completion unknown; no construction allowed')
 def tasks(self):
  rows=[dict(f)for f in self.p['facilities']if not f['status'].startswith('reserve')]
  rows += [dict(port,kind='harbor',args={},command='native_harbor')for port in self.p['ports']]
  amendments=self.out/'facility_amendments.json'
  if amendments.exists():
   patch=json.loads(amendments.read_text(encoding='utf8'))
   if patch['planDigest']!=self.ledger['planDigest']:raise StopBatch('Amendment belongs to another plan')
   for f in rows:
    if f['id']in patch['facilities']:f.update(patch['facilities'][f['id']])
  for f in rows:
   if f['kind']=='headquarters':f['town_name']=next(t['name']for t in self.p['cities']if t['id']==self.p['focus_town'])
  order={'headquarters':0,'road_depot':1,'truck':2,'warehouse':3,'helipad':4,'heliport':5,'road_maintenance':6,'harbor':7,'water_depot':8}
  order['bus']=2
  order['helipad2']=4
  order['water_maintenance']=8
  rows.sort(key=lambda f:(order[f['kind']],f['id']))
  if self.a.ids:
   ids=set(self.a.ids.split(','));unknown=ids-{f['id']for f in rows}
   if unknown:raise StopBatch('Unknown facility IDs '+str(unknown))
   rows=[f for f in rows if f['id']in ids]
  return rows
 async def facility(self,t,action):
  code=self.lua.replace('local task=TASK','local task=B.json.decode('+quote(t)+')').replace('local action=ACTION','local action='+json.dumps(action))
  started=time.perf_counter();failed=True
  try:
   result=await self.eval(code);failed=False;return result
  finally:self.record_timing('facility.'+action,started,failed)
 async def read_facilities(self,tasks,action,with_session=False):
  """One engine request, one local index; never retained across a mutation."""
  if action not in ('verify','preview'):raise ValueError('Batch reads cannot build')
  if not 1<=len(tasks)<=16:raise ValueError('Read chunk must contain 1..16 facilities')
  setup=(ROOT/'scripts/fullmap_facility_index.lua').read_text(encoding='utf-8-sig')
  body=self.lua.replace('local readIndex=nil','local readIndex=facilityReadIndex').replace('local task=TASK','').replace('local action=ACTION','local action='+json.dumps(action))
  code=setup+'\nlocal tasks=B.json.decode('+quote(tasks)+');local function inspect(task)\n'+body+'\nend\nlocal out={};for _,task in ipairs(tasks)do out[#out+1]={id=task.id,result=B.json.decode(inspect(task))}end;return B.json.encode(out)'
  if with_session:
   code='local session={state=B.commands.get_game_state({}),world=B.commands.get_map_info({})};\n'+code.replace('return B.json.encode(out)','return B.json.encode({session=session,results=out})')
  started=time.perf_counter();failed=True
  try:
   result=await self.eval(code)
   if with_session:
    self.accept_session(result['session']);result=result['results']
   if not isinstance(result,list) or [r.get('id')for r in result]!=[t['id']for t in tasks]:raise StopBatch('Incomplete or mismatched facility read batch')
   failed=False;return result
  finally:self.record_timing('facility.batch_'+action,started,failed)
 async def run_reads(self):
  size=getattr(self.a,'read_batch_size',8)
  if not 1<=size<=16:raise ValueError('read_batch_size must be between 1 and 16')
  tasks=self.tasks()
  if self.a.limit:tasks=tasks[:self.a.limit]
  for offset in range(0,len(tasks),size):
   chunk=tasks[offset:offset+size]
   if getattr(self.a,'combined_context',False):
    rows=await self.read_facilities(chunk,self.a.action,with_session=True)
   else:
    await self.session();rows=await self.read_facilities(chunk,self.a.action)
   for t,row in zip(chunk,rows):
    key=t.get('operation_id',t['id']);r=row['result'];item=self.ledger['items'].setdefault(key,{'attempts':0,'kind':t['kind']})
    if r.get('existing'):
     item.update(audit=r['audit'],status='static_verified'if r['audit']['staticVerified']else'needs_reconciliation')
    elif item['attempts']:
     item.update(reconciliationReadback=r,status='submission_absent_requires_review')
    elif self.a.action=='verify':item.update(status='not_built',reconciliationReadback=r)
    else:item.update(preview=r,status='preview_ready'if preview_ok(r)else'preview_blocked')
    print(key+': '+item['status'],flush=True)
   # No mutations in this chunk: persist its completed reads once. Build intent
   # journaling remains synchronous and per-operation in the construction path.
   self.flush()
   # Return all known outcomes from this read chunk, but never continue past
   # an invalid existing facility or a missing historical submission.
   if any(self.ledger['items'][t.get('operation_id',t['id'])]['status']in ('needs_reconciliation','submission_absent_requires_review')for t in chunk):raise StopBatch('Read batch needs reconciliation')
  self.ledger['lastAction']=self.a.action;self.flush()
 async def run(self):
  if self.a.action in ('verify','preview') and getattr(self.a,'read_batch_size',1)>1:
   return await self.run_reads()
  await self.session()
  if self.a.action=='build'and unfinished(self.ledger):raise StopBatch('Unreconciled submissions: '+','.join(unfinished(self.ledger)))
  if self.a.action=='build':await self.save('before')
  done=0
  for t in self.tasks():
   key=t.get('operation_id',t['id']);item=self.ledger['items'].setdefault(key,{'attempts':0,'kind':t['kind']})
   await self.session()
   # The Lua preview already resolves and audits an existing facility first.
   # Reuse that read instead of a separate verify + second full-map scan.
   existing=await self.facility(t,'verify'if self.a.action=='verify'else'preview')
   if existing.get('existing'):
    item['audit']=existing['audit'];item['status']='static_verified'if existing['audit']['staticVerified']else'needs_reconciliation';self.flush()
    if item['status']!='static_verified':raise StopBatch(key+' existing facility audit failed')
    print(key+': static verified (existing)',flush=True);continue
   if self.a.action=='verify':
    item['reconciliationReadback']=existing;item['status']='submission_absent_requires_review'if item['attempts']else'not_built';self.flush();continue
   if item['attempts']:raise StopBatch(key+' previously submitted but missing; never rebuild automatically')
   result=existing;item.update(preview=result,status='preview_ready'if preview_ok(result)else'preview_blocked');self.flush()
   if not preview_ok(result):raise StopBatch(key+' native preview blocked')
   if self.a.action=='preview':print(key+': preview passed',flush=True);continue
   item.update(attempts=1,status='commit_started',intentTime=time.time());self.flush()
   try:
    result=await self.facility(t,'build');item['result']=result;self.flush()
    if result.get('commit',{}).get('built')is not True or not result.get('audit',{}).get('staticVerified'):raise StopBatch(key+' commit/readback incomplete')
    check=await self.facility(t,'verify');item['audit']=check.get('audit')
    if not check.get('audit',{}).get('staticVerified'):raise StopBatch(key+' independent readback failed')
    item['status']='static_verified';self.flush();done+=1
    print(key+': built once + static verified',flush=True)
   except BaseException:
    item['status']='needs_reconciliation';self.flush();raise
   if done%10==0:await self.save('checkpoint_'+str(done))
   if self.a.limit and done>=self.a.limit:break
  if self.a.action=='build':await self.save('after')
  self.ledger['lastAction']=self.a.action;self.flush()
async def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('action',choices=['preview','build','verify'],nargs='?',default='preview');a.add_argument('--plan',type=Path,default=PLAN);a.add_argument('--output',type=Path,default=ROOT/'exports/fullmap_plan_20261003/execution');a.add_argument('--ids');a.add_argument('--limit',type=int,default=0);a.add_argument('--read-batch-size',type=int,choices=range(1,17),default=8);a.add_argument('--combined-context',action=argparse.BooleanOptionalAction,default=True);args=a.parse_args();b=Batch(args)
 try:
  with batch_lock(b.b.dir):await b.run()
 except Exception as e:
  b.ledger['events'].append({'stopped':str(e),'time':time.time()});b.flush();print('STOP: '+str(e),file=sys.stderr);return 2
 finally:b.flush()
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
