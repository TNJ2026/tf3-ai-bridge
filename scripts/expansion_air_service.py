"""Roadside helicopter service bases: native placement plus bidirectional walking gate."""
import argparse,asyncio,json,math
from pathlib import Path
from fullmap_batch import Batch,ROOT,batch_lock,write_json,StopBatch,quote

class AirService(Batch):
 def tasks(self):return json.loads((self.out.parent/'air_service_selected.json').read_text(encoding='utf8'))
 async def facility(self,task,action):
  walk=(ROOT/'scripts/road_first_walk.lua').read_text(encoding='utf8').replace('if id<0 and person and not car then','if person then').replace('local target=bus and starts or heli and goals or nil','local target=id<0 and starts or goals')
  source=self.lua
  source=source.replace('local modules={};for slot,m in pairs(params.modules or{})do', "local modules={};for slot,m in pairs(params.modules or{})do local mr=api.res.moduleRep.get(api.res.moduleRep.find(m.name));m={name=m.name,variant=m.variant or 0,metadata=mr.metadata,updateScript={fileName=mr.updateScript.fileName,params=mr.updateScript.params}};")
  injection="local personAccess;do local spec={existingRoadEntities={}};for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(args.x,args.y),170,CT.BASE_EDGE))do spec.existingRoadEntities[#spec.existingRoadEntities+1]=id end;\n"+walk+'\npersonAccess=walkPreview;end\n'
  source=source.replace('local blocking,waterContacts={},{}',injection+'local blocking,waterContacts={},{}')
  source=source.replace('preview={waterSurfaceContacts=', 'preview={personAccess=personAccess,waterSurfaceContacts=')
  source=source.replace('local safe=check.ok==true and not check.critical and not check.blocked','local safe=check.ok==true and not check.critical and not check.blocked and check.personAccess and check.personAccess.inbound and check.personAccess.outbound')
  return await self.eval(source.replace('local task=TASK','local task=B.json.decode('+quote(task)+')').replace('local action=ACTION','local action='+json.dumps(action)))

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['select','build','verify']);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();a.plan=a.root/'plan.json';a.output=a.root/'execution';a.ids=None;a.limit=0;a.read_batch_size=1;b=AirService(a)
 with batch_lock(b.b.dir):
  await b.session()
  if a.action!='select':return await b.run()
  targets=[dict(id=f['id'],position=f['position'])for f in b.p['facilities']if f['id']in ('I4845_helipad','I14805_helipad')]
  survey=await b.eval((ROOT/'scripts/maintenance_survey.lua').read_text(encoding='utf8').replace('TARGETS',quote(targets)));write_json(a.root/'air_service_survey.json',survey)
  template=json.loads((ROOT/'config/planning_templates/city.json').read_text(encoding='utf8'))['facilities'][0]
  params={'seed':1,'modules':{k:dict(name=v['name'],variant=v.get('variant',0))for k,v in template['params']['modules'].items()}}
  selected=[];trials=[]
  for area in survey['areas']:
   roads=sorted(area['roads'],key=lambda r:math.hypot((r['p0']['x']+r['p1']['x'])/2-area['center']['x'],(r['p0']['y']+r['p1']['y'])/2-area['center']['y']))
   found=False
   for road in roads[:24]:
    dx=road['p1']['x']-road['p0']['x'];dy=road['p1']['y']-road['p0']['y'];angle=math.atan2(dy,dx);mx=(road['p0']['x']+road['p1']['x'])/2;my=(road['p0']['y']+road['p1']['y'])/2
    for side in (1,-1):
     rot=angle if side==1 else angle+math.pi
     task=dict(id='AIR_SERVICE_'+area['id'],kind='heliport',position=dict(x=mx-67*math.sin(rot),y=my+67*math.cos(rot)),rotation=math.degrees(rot),params=params,args={},status='planned',accessRoad=road)
     r=await b.facility(task,'preview');trials.append(dict(task=task,result=r));write_json(a.root/'air_service_previews.json',trials)
     if r.get('previewPassed'):
      selected.append(task);found=True;print(task['id']+': placement and walking passed',flush=True);break
    if found:break
   if not found:raise StopBatch(area['id']+' no road-linked heliport candidate passed')
  write_json(a.root/'air_service_selected.json',selected)

if __name__=='__main__':asyncio.run(main())
