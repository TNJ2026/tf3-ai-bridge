"""Connect an explicit planned collection with live ports and single-attempt journal."""
import argparse,asyncio,json,sys,time
from pathlib import Path
from fullmap_batch import ROOT,quote,StopBatch,batch_lock,unfinished,save_slot
import fullmap_batch as core
from fullmap_roads import Roads as CurrentRoads
core.save_slot=save_slot
from hub_execution import strict_road_preview

class PlannedRoads(CurrentRoads):
 async def resolve(self,s):
  descriptors=[]
  for k in (0,-1):
   p=s['path'][k];fid=None
   if s['id'].endswith('_depot_link')and k==0:fid=s['id'].replace('_depot_link','_road_depot')
   elif s.get('templateRoad'):
    h=next(h for h in self.p['hubs']if s['id'].startswith(h['owner']+'_'));template=self.p['templates'][h['template']];node=s['templateRoad']['node0'if k==0 else'node1'];roles=[role for role,ids in template['rolePortNodes'].items()if node in ids]
    if len(roles)>1:raise StopBatch('Ambiguous role')
    if roles:fid=h['facilities'][roles[0]]
   elif not any(s['id'].startswith(h['owner']+'_')for h in self.p['hubs'])and k==-1:fid=s.get('to_facility')
   d={'position':p,'required':k==0 and 'from_node_hint'in s}
   if fid:d['facility']=next(t for t in self.tasks_all if t['id']==fid)
   descriptors.append(d)
  code='''local ds=B.json.decode(DESCRIPTORS);local CT=api.type.ComponentType;local out={};local function row(id)local q=api.engine.getComponent(id,CT.BASE_NODE).position;return {id=id,position={x=q.x,y=q.y,z=q.z},segments=B.toPlain(api.engine.system.streetSystem.getNodeSegments(id))}end
for _,d in ipairs(ds)do local p=d.position;local matches={}
 if d.facility then local f=d.facility;local cs={};for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(f.position.x,f.position.y),1,CT.CONSTRUCTION))do local c=api.engine.getComponent(id,CT.CONSTRUCTION);local q=c.transf:cols(3);if math.abs(q.x-f.position.x)<.2 and math.abs(q.y-f.position.y)<.2 and (not f.resource or c.fileName==f.resource)then cs[#cs+1]=c end end;assert(#cs==1,'facility changed');local c=cs[1];local frozen={};for _,id in ipairs(c.frozenNodes)do frozen[id]=true end;local seen={};for _,eid in ipairs(c.frozenEdges)do local e=api.engine.getComponent(eid,CT.BASE_EDGE);if e and e.roadType==api.type.enum.RoadType.STREET then for _,id in ipairs({e.node0,e.node1})do if not frozen[id]and not seen[id]then seen[id]=true;matches[#matches+1]=row(id)end end end end;assert(#matches>0,'native port missing');table.sort(matches,function(a,b)return (a.position.x-p.x)^2+(a.position.y-p.y)^2<(b.position.x-p.x)^2+(b.position.y-p.y)^2 end)
 else for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(p.x,p.y),.3,CT.BASE_NODE))do local q=api.engine.getComponent(id,CT.BASE_NODE).position;if math.abs(q.x-p.x)<.2 and math.abs(q.y-p.y)<.2 and #api.engine.system.streetSystem.getNodeSegments(id)>0 then matches[#matches+1]=row(id)end end;assert(#matches<=1,'ambiguous node');if d.required then assert(#matches==1,'public anchor missing')end end
 out[#out+1]=matches[1]or{position=p,segments={}}
end;return B.json.encode(out)'''.replace('DESCRIPTORS',quote(descriptors))
  a,b=await self.eval(code)
  for n in (a,b):n.setdefault('id',None)
  if not a or not b:raise StopBatch('Missing native facility port')
  if a['id']is None and b['id']is None:raise StopBatch('Build dependency road first: '+s['id'])
  def arg(n):return {'node':n['id']}if n['id']is not None else n['position']
  args=dict(start=arg(a),end=arg(b),via=s['path'][1:-1],street_type=s.get('street_type','country/country_new_medium'),snap_radius=0,max_segment_length=50,allow_collisions=False)
  return args,{'anchor':a,'port':b}
 async def audit_road(self,item):
  c=item.get('commit',{});ids=c.get('edges',[])
  if not ids:return {'verified':False}
  nodes=[n['id']for n in item['resolved'].values()if isinstance(n,dict)and n.get('id')is not None]
  src=(ROOT/'scripts/fullmap_road_audit.lua').read_text('utf8')
  code='for _,id in ipairs(B.json.decode('+quote(ids)+'))do assert(api.engine.getComponent(id,api.type.ComponentType.TRANSPORT_NETWORK),"Missing road transport network")end;'+src.replace('TASKJSON',quote({'edges':ids,'nodes':nodes}))
  return await self.eval(code)
 async def complete_junctions(self,item):
  for row in item['audit']['junctions']:
   if row['verified']:continue
   node=next(n for n in item['resolved'].values()if n.get('id')==row['node'])
   branches={p['to']for p in row['paths']if p['to']in item['commit']['edges']}
   if len(branches)!=1:raise StopBatch('Unsupported branch count')
   task=dict(node=node['id'],branch=next(iter(branches)),x=node['position']['x'],y=node['position']['y'],existingEdges=node['segments'])
   e=item.setdefault('junctionRepairsV2',{}).setdefault(str(node['id']),{'attempts':0})
   if e['attempts']:raise StopBatch('Do not replay junction submission')
   src=(ROOT/'scripts/planned_junction_patch.lua').read_text('utf8').replace('TASKJSON',quote(task))
   e.update(input=task,preview=await self.eval(src.replace('local apply=APPLY','local apply=false')));self.flush()
   e.update(attempts=1,status='commit_started');self.flush()
   e['result']=await self.eval(src.replace('local apply=APPLY','local apply=true'));self.flush()
   if not e['result'].get('applied'):raise StopBatch('Unknown junction outcome')
   e['status']='applied';self.flush()
  item['audit']=await self.audit_road(item)
 async def run(self):
  await self.session();self.tasks_all=self.tasks()
  if unfinished(self.ledger):raise StopBatch('Unreconciled submissions '+str(unfinished(self.ledger)))
  selected=[s for s in self.p['roads']if s['id'].startswith(self.a.owner+'_')]
  extra_file=self.out/'extra_roads.json'
  if extra_file.exists():
   extras=json.loads(extra_file.read_text('utf8'))
   if extras['planDigest']!=self.ledger['planDigest']:raise StopBatch('Extra roads belong to another plan')
   all_ids=[s['id']for s in self.p['roads']+extras['roads']]
   if len(all_ids)!=len(set(all_ids)):raise StopBatch('Duplicate extra road ID')
   selected += [s for s in extras['roads']if s['id'].startswith(self.a.owner+'_')]
  amendments=self.out/'planned_road_amendments.json'
  if amendments.exists():
   patches=json.loads(amendments.read_text('utf8'))
   selected=[dict(s,**patches.get(s['id'],{}))for s in selected]
  if self.a.road_ids:selected=[s for s in selected if s['id']in self.a.road_ids.split(',')]
  # Expand outwards from public anchors and construction entrance nodes.
  pending=selected[:]
  while pending:
   chosen=pending[0]
   old=self.ledger['items'].get(chosen['id'],{})
   if old.get('attempts')and not(await self.audit_road(old))['verified']:raise StopBatch('Previously built road changed')
   pending.remove(chosen);s=chosen;key=s['id'];item=self.ledger['items'].setdefault(key,{'kind':'connection','attempts':0})
   if item['attempts']:continue
   await self.session();args,resolved=await self.resolve(s)
   v=await self.eval('return B.json.encode(B.commands.build_road(B.json.decode('+quote(dict(args,preview=True))+')))')
   if not strict_road_preview(v) and s.get('templateRoad') and 'medium'in args['street_type'] and not v.get('critical') and v.get('collisions'):
    item['rejectedWideRoadPreview']=v;self.flush()
    s=dict(s,street_type='country/country_new_small');args,resolved=await self.resolve(s)
    v=await self.eval('return B.json.encode(B.commands.build_road(B.json.decode('+quote(dict(args,preview=True))+')))')
    if strict_road_preview(v):
     patchfile=self.out/'planned_road_amendments.json';patches=json.loads(patchfile.read_text('utf8'))if patchfile.exists()else{};patches.setdefault(key,{})['street_type']='country/country_new_small';core.write_json(patchfile,patches)
   item.update(input=args,resolved=resolved,preview=v,status='preview_ready'if strict_road_preview(v)else'preview_blocked');self.flush()
   if not strict_road_preview(v):raise StopBatch('Road preview rejected: '+key)
   if self.a.action=='preview':print(key+': preview passed',flush=True);break
   fresh,rr=await self.resolve(s)
   if (fresh,rr)!=(args,resolved):raise StopBatch('Endpoints changed after preview')
   item.update(attempts=1,status='commit_started',intentTime=time.time());self.flush()
   try:
    item['commit']=await self.eval('return B.json.encode(B.commands.build_road(B.json.decode('+quote(dict(args,preview=False))+')))');self.flush()
    if item['commit'].get('built')is not True:raise StopBatch('Unknown road submission')
    item['audit']=await self.audit_road(item)
    if not item['audit']['verified']:await self.complete_junctions(item)
    if not item['audit']['verified']:raise StopBatch('Road connection failed readback')
    item['status']='connection_verified';self.flush();print(key+': connected and verified',flush=True)
   except BaseException:item['status']='needs_reconciliation';self.flush();raise
  if self.a.action=='build':await self.save('collection_roads_checkpoint')

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['preview','build']);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--owner',required=True);ap.add_argument('--road-ids');a=ap.parse_args();a.ids=None;a.limit=0;b=PlannedRoads(a)
 try:
  with batch_lock(b.b.dir):await b.run()
 except Exception as e:b.ledger['events'].append({'stopped':str(e),'at':time.time()});print('STOP:',e);return 2
 finally:b.flush()
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
