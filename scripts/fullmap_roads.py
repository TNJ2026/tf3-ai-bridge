"""Resolve actual facility ports and connect them with a journaled single road commit."""
import argparse,asyncio,json,math,sys,time
from pathlib import Path
from fullmap_batch import Batch,PLAN,ROOT,StopBatch,batch_lock,quote,unfinished
from batch_connections import road_preview_ok
class Roads(Batch):
 async def resolve(self,spec):
  fac=next(f for f in self.tasks_all if f['id']==spec['to_facility'])
  verified=await self.facility(fac,'verify')
  if not verified.get('audit',{}).get('staticVerified'):raise StopBatch('Facility not built/verified: '+fac['id'])
  audit=verified['audit'];frozen=set(audit['frozenNodes']);nodes=[n for n in audit['roadNodes']if n['id']not in frozen]
  if not nodes:return None,{'facility':audit,'noNativeRoadPort':True}
  p=spec['from_position'];code='''local p=B.json.decode(POS);local CT=api.type.ComponentType;local out={}
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(p.x,p.y),1,CT.BASE_NODE))do
 local n=api.engine.getComponent(id,CT.BASE_NODE);local q=n.position
 if math.abs(q.x-p.x)<.2 and math.abs(q.y-p.y)<.2 then
  local segments=api.engine.system.streetSystem.getNodeSegments(id)
  if #segments>0 then out[#out+1]={id=id,position={x=q.x,y=q.y,z=q.z},segments=B.toPlain(segments)}end
 end
end
return B.json.encode({nodes=out})'''.replace('POS',quote(p))
  n=(await self.eval(code))['nodes']
  if len(n)!=1:raise StopBatch('Road anchor missing/ambiguous; refresh layout')
  end=min(nodes,key=lambda x:math.hypot(x['position']['x']-p['x'],x['position']['y']-p['y']))
  args={'start':{'node':n[0]['id']},'end':{'node':end['id']},'street_type':'country/country_new_small','snap_radius':0,'max_segment_length':50,'allow_collisions':False}
  if math.hypot(end['position']['x']-p['x'],end['position']['y']-p['y'])>140:
   patches=self.out/'road_amendments.json'
   amended=json.loads(patches.read_text(encoding='utf8'))if patches.exists()else{}
   path=amended.get(spec['id'],{}).get('sampled_land_corridor',spec.get('sampled_land_corridor'))
   if not path:raise StopBatch('Long approach lacks surveyed land corridor')
   # Replace the coarse corridor's building-center approach with actual port.
   # Discard samples beyond the entrance plane, which would cause a U-turn.
   q=end['position'];dx=p['x']-q['x'];dy=p['y']-q['y'];length=math.hypot(dx,dy)
   args['via']=[v for v in path[1:-1]if ((v['x']-q['x'])*dx+(v['y']-q['y'])*dy)/length>20]
  return args,{'facility':audit['entity'],'anchor':n[0],'port':end}
 async def audit_road(self,item):
  commit=item.get('commit',{});ids=commit.get('edges',[])
  if not ids:return {'verified':False}
  source=(ROOT/'scripts/fullmap_road_audit.lua').read_text(encoding='utf-8-sig')
  return await self.eval(source.replace('TASKJSON',quote({'edges':ids,'nodes':[commit['from'],commit['to']]})))
 async def repair_known_turns(self,key,item):
  # Only after live diagnosis, and only the audited 2-old-road/1-new-road pattern.
  if item.get('junctionPatchAttempt'):raise StopBatch('Junction patch already attempted')
  resolved=item['resolved'];c=item['commit']
  if not c['edges'] or len(resolved['anchor']['segments'])not in [2,3]:raise StopBatch('Junction failure outside supported three-way repair')
  attached=await self.eval('local out={};local wanted=B.json.decode('+quote(c['edges'])+');local set={};for _,e in ipairs(wanted)do set[e]=true end;for _,e in ipairs(api.engine.system.streetSystem.getNodeSegments('+str(resolved['anchor']['id'])+'))do if set[e]then out[#out+1]=e end end;return B.json.encode(out)')
  if len(attached)!=1:raise StopBatch('Expected exactly one new branch at anchor')
  task={'node':resolved['anchor']['id'],'branch':attached[0],'x':resolved['anchor']['position']['x'],'y':resolved['anchor']['position']['y'],'existingEdges':resolved['anchor']['segments']}
  source=(ROOT/'scripts/fullmap_junction_patch.lua').read_text(encoding='utf-8-sig').replace('TASKJSON',quote(task))
  item['junctionPatchPreview']=await self.eval(source.replace('local apply=APPLY','local apply=false'));self.flush()
  item['junctionPatchAttempt']=1;self.flush()
  item['junctionPatchCommit']=await self.eval(source.replace('local apply=APPLY','local apply=true'));self.flush()
  if not item['junctionPatchCommit'].get('applied'):raise StopBatch('Junction patch outcome unknown')
 async def run(self):
  if self.a.action=='verify':
   from fullmap_road_reads import run_road_reads
   return await run_road_reads(self)
  await self.session();self.tasks_all=super().tasks();selected=[s for s in self.p['roads']if s['to_facility']in{f['id']for f in self.tasks_all}]
  if self.a.road_ids:selected=[s for s in selected if s['id']in self.a.road_ids.split(',')]
  # Historical business ledger entries do not gate unrelated work.
  if self.a.action=='build':await self.save('roads_before')
  done=0
  for spec in selected:
   key=spec['id'];item=self.ledger['items'].setdefault(key,{'kind':'connection','attempts':0});await self.session()
   if item.get('consumedByJoint'):
    raise StopBatch(key+' already consumed by joint collection; use joint readback, never resubmit')
   if item.get('attempts'):
    item['audit']=await self.audit_road(item);item['status']='connection_verified'if item['audit']['verified']else'needs_reconciliation';self.flush()
    if item['status']!='connection_verified':raise StopBatch(key+' road readback failed; do not rebuild')
    print(key+': road verified (existing)',flush=True);continue
   args,resolved=await self.resolve(spec);item['resolved']=resolved
   if args is None:
    item['status']='not_applicable';item['reason']='No native BASE_EDGE street endpoint: must audit automatic pedestrian/cargo links separately';self.flush();print(key+': no native street port',flush=True);continue
   if self.a.action=='verify':item['status']='not_built';self.flush();continue
   preview=await self.eval('return B.json.encode(B.commands.build_road(B.json.decode('+quote(dict(args,preview=True))+')))')
   item.update(input=args,preview=preview,status='preview_ready'if road_preview_ok(preview)else'preview_blocked');self.flush()
   if not road_preview_ok(preview):raise StopBatch(key+' road native preview blocked')
   if self.a.action=='preview':print(key+': road preview passed',flush=True);continue
   fresh,rr=await self.resolve(spec)
   if fresh!=args or rr!=resolved:raise StopBatch('Road/facility changed between preview and commit')
   item.update(attempts=1,status='commit_started',intentTime=time.time());self.flush()
   try:
    # The public road builder makes and validates a new proposal internally.
    result=await self.eval('return B.json.encode(B.commands.build_road(B.json.decode('+quote(dict(args,preview=False))+')))');item['commit']=result;self.flush()
    if result.get('built')is not True:raise StopBatch(key+' road commit incomplete')
    item['audit']=await self.audit_road(item)
    if not item['audit']['verified']:
     await self.repair_known_turns(key,item)
     item['audit']=await self.audit_road(item)
    if not item['audit']['verified']:raise StopBatch('Road independent readback failed')
    item['status']='connection_verified';self.flush();done+=1;print(key+': built once + junction verified',flush=True)
   except BaseException:item['status']='needs_reconciliation';self.flush();raise
   if self.a.limit and done>=self.a.limit:break
  if self.a.action=='build':await self.save('roads_after')
async def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['preview','build','verify'],default='preview',nargs='?');ap.add_argument('--plan',type=Path,default=PLAN);ap.add_argument('--output',type=Path,default=ROOT/'exports/fullmap_plan_20261003/execution');ap.add_argument('--road-ids');ap.add_argument('--limit',type=int,default=0);ap.add_argument('--read-batch-size',type=int,choices=range(1,17),default=8);args=ap.parse_args();args.ids=None;b=Roads(args)
 try:
  with batch_lock(b.b.dir):await b.run()
 except Exception as e:b.ledger['events'].append({'stopped':str(e),'time':time.time()});b.flush();print('STOP: '+str(e),file=sys.stderr);return 2
 finally:b.flush()
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
