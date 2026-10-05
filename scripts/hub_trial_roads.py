"""Road preflight and connections for the fixed Chongqing trial; no old map IDs."""
import asyncio,argparse,json,math,sys,hashlib
from types import SimpleNamespace
from hub_trial import OUT,TEMPLATE,transform
from fullmap_batch import ROOT,quote,batch_lock,StopBatch
from fullmap_batch import save_slot as trial_save_slot
import fullmap_batch as core
sys.path.insert(0,str(ROOT/'exports/newmap_plan_20261003_v2'))
from construct_roads import CurrentRoads
from connect_airports import AirportRoads
core.save_slot=trial_save_slot

class TrialRoads(AirportRoads):
 def __init__(self,a):
  super().__init__(a);t=json.loads(TEMPLATE.read_text('utf8'));o=self.p['candidate']['origin']
  self.port_position=transform(t,o,{'x':109.536,'y':-68})
  self.apron_end=transform(t,o,{'x':-43.817,'y':-68})
  self.outer_end=transform(t,o,{'x':208.083,'y':-68})
  self.p['roads']=[dict(id='TRIAL_public_access',side='public'),dict(id='TRIAL_airport_frontage',side='airport')]
 async def resolve(self,s):
  if s['side']=='public':
   a=await self.node(self.p['candidate']['anchor']);b=await self.port('TRIAL_truck',self.port_position)
   direction=await self.eval('local id='+str(b['id'])+';local ss=api.engine.system.streetSystem.getNodeSegments(id);assert(#ss==1,"port changed before first connection");local e=api.engine.getComponent(ss[1],api.type.ComponentType.BASE_EDGE);local v=e.node0==id and e.tangent0 or e.tangent1;local sign=e.node0==id and -1 or 1;return B.json.encode({x=v.x*sign,y=v.y*sign})')
   p,q=a['position'],b['position'];ln=math.hypot(direction['x'],direction['y']);control=70
   c1={'x':p['x']+control,'y':p['y']};c2={k:q[k]+control*direction[k]/ln for k in ['x','y']};via=[]
   for i in range(1,8):
    v=i/8;u=1-v;via.append({k:u**3*p[k]+3*u*u*v*c1[k]+3*u*v*v*c2[k]+v**3*q[k]for k in ['x','y']})
   args={'start':{'node':a['id']},'end':{'node':b['id']},'via':via,'street_type':'country/country_new_small','snap_radius':0,'max_segment_length':50,'allow_collisions':False}
   return args,{'anchor':a,'port':b}
  a=await self.port('TRIAL_truck',self.port_position);f=next(t for t in self.tasks_all if t['id']=='TRIAL_heliport');v=await self.facility(f,'verify')
  if not v.get('audit',{}).get('staticVerified'):raise StopBatch('Airport missing')
  return {'start':{'node':a['id']},'end':self.apron_end,'street_type':'country/country_new_small','snap_radius':0,'max_segment_length':50,'allow_collisions':False},{'anchor':a,'port':{'id':None,'position':self.apron_end},'airport':v['audit']['entity']}
 async def audit_road(self,item):
  if 'airport'in item['resolved']:return await super().audit_road(item)
  from fullmap_roads import Roads
  return await Roads.audit_road(self,item)
 async def preflight(self):
  await self.session();a=await self.node(self.p['candidate']['anchor'])
  own=await self.eval('local out={};for _,id in ipairs(api.engine.system.streetSystem.getNodeSegments('+str(a['id'])+'))do local c=api.engine.system.streetConnectorSystem.getConstructionEntityForEdge(id);if c and c>=0 then out[#out+1]=c end end;return B.json.encode(out)')
  if own:raise StopBatch('Public anchor belongs to a construction')
  jobs=[dict(start={'node':a['id']},end=self.port_position,via=[self.outer_end]),dict(start=self.port_position,end=self.apron_end)]
  rows=[]
  for job in jobs:
   args=dict(job,street_type='country/country_new_medium',snap_radius=0,max_segment_length=50,allow_collisions=False,preview=True)
   r=await self.eval('return B.json.encode(B.commands.build_road(B.json.decode('+quote(args)+')))')
   safe=r.get('ok')and not any(r.get(k)for k in ['critical','blocked','placementBlocked','messages','warnings','infos','collisions']);rows.append({'input':args,'preview':r,'safe':safe})
  from batch_warehouses import write_json
  write_json(OUT/'road_preflight.json',rows);print(json.dumps([{'safe':r['safe'],'messages':r['preview'].get('messages'),'collisions':r['preview'].get('collisions')}for r in rows]))
  if not all(r['safe']for r in rows):raise StopBatch('Road preflight rejected; do not build facilities')

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['preflight','build','verify']);a=ap.parse_args();action=a.action
 a.plan=OUT/'plan.json';a.output=OUT/'execution';a.ids=None;a.road_ids=None;a.limit=0;a.action='preview'if action=='preflight'else action
 b=TrialRoads(a)
 try:
  with batch_lock(b.b.dir):
   if action=='preflight':await b.preflight()
   elif action=='verify':
    await b.session()
    for s in b.p['roads']:
     item=b.ledger['items'][s['id']];r=await b.audit_road(item);print(s['id']+': '+str(r['verified']))
     if not r['verified']:raise StopBatch('Road readback failed')
   else:await b.run()
 finally:b.flush()
if __name__=='__main__':asyncio.run(main())
