"""Fixed, journaled copy of the selected template at the newly requested camera site."""
import argparse,asyncio,json,math,time,hashlib
from pathlib import Path
from types import SimpleNamespace
from hub_trial import Trial,transform
from hub_trial_roads import CurrentRoads,AirportRoads
from fullmap_batch import ROOT,Batch,quote,batch_lock,StopBatch,unfinished
from fullmap_roads import Roads
from batch_warehouses import Bridge,write_json
OUT=ROOT/'exports/hub_copy_displayed'
TEMPLATE=ROOT/'exports/hub_template_displayed/template/hub_template.json'

from displayed_collection_layout import layout

async def prepare(output=OUT, template_path=TEMPLATE, anchor=None):
 b=Bridge();assert b.heartbeat().get('connected')
 camera=await b.call('eval',{'code':'local p=api.gui.camera.getCenter();return {x=p.x,y=p.y,z=p.z}'},engine=False)
 if isinstance(camera,str):camera=json.loads(camera)
 template=json.loads(template_path.read_text('utf8'));capture=json.loads((template_path.parent.parent/'capture.json').read_text('utf8'))
 if anchor is None:raise StopBatch('A surveyed public anchor is required for a new collection')
 geometry=layout(template,camera,anchor)
 # Temporary read-only batch shell is not tied to a historical world.
 source=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8')
 assert ']========]'not in source
 pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+source+']========],"=capture","t",env))()._internal;'
 r=await b.call('eval',{'code':pre+'return B.json.encode({state=B.commands.get_game_state({}),map=B.commands.get_map_info({})})'},engine=True)
 if isinstance(r,str):r=json.loads(r)
 fs=[]
 for f in template['facilities']:
  pos=transform(template,camera,f['localPosition'])
  fs.append(dict(id='COPY_'+f['role'],kind=f['role'],position=pos,rotation=template['sourceEvidence']['rotation']+f['relativeRotation'],args={'source_entity':template['sourceEvidence']['facilities'][f['role']]},command='build_facility',status='planned',expectedParams=f['params'],sourcePosition=next(x['position']for x in capture['facilities']if x['role']==f['role'])))
 p=dict(facilities=fs,ports=[],roads=[],cities=r['map']['towns'],industries=[dict(i,resource=i['fileName'])for i in r['map']['industries']],session=r['state'],candidate={'origin':camera},template=str(template_path),templateDigest=hashlib.sha256(template_path.read_bytes()).hexdigest(),collection=geometry)
 write_json(output/'plan.json',p)

class Copy(CurrentRoads):
 def __init__(self,a):
  super().__init__(a);path=Path(self.p['template']);self.template=json.loads(path.read_text('utf8'));self.origin=self.p['candidate']['origin']
  if self.p.get('templateDigest') and hashlib.sha256(path.read_bytes()).hexdigest()!=self.p['templateDigest']:raise StopBatch('Template changed since preparation')
  # A station frontage is a junction, not a continuation of the entrance stub.
  begin=self.source.index('for _,v in ipairs({{1,points[1],true}')
  end=self.source.index('for i,e in ipairs(edgesToAdd)do local a,b=tangents[i]',begin)
  self.source=self.source[:begin]+self.source[end:]
  self.end=transform(self.template,self.origin,{'x':236.956,'y':-64.0})
  self.front=transform(self.template,self.origin,{'x':-41.4876,'y':-66.2552})
  self.anchor={'x':3124.3969726562,'y':-3467.8989257812}
  if self.p.get('collection'):
   self.end=self.p['collection']['end'];self.front=self.p['collection']['front'];self.anchor=self.p['collection']['anchor']
  self.p['roads']=[{'id':'COPY_between','side':'between'},{'id':'COPY_front','side':'front'},{'id':'COPY_outer','side':'outer'},{'id':'COPY_public','side':'public'}]
 async def port_for(self,role):
  f=next(f for f in self.tasks_all if f['kind']==role)
  return await self.port(f['id'],f['position'])
 async def resolve(self,s):
  side=s['side'];via=[]
  if side=='between':a=await self.port_for('bus');b=await self.port_for('truck')
  elif side=='front':a=await self.port_for('bus');b={'id':None,'position':self.front}
  elif side=='outer':a=await self.port_for('truck');b={'id':None,'position':self.end}
  else:
   a=await self.node(self.end);b=await self.node(self.anchor)
   p,q=a['position'],b['position'];ang=math.radians(self.template['sourceEvidence']['rotation'])
   c1={'x':p['x']+45*math.cos(ang),'y':p['y']+45*math.sin(ang)}
   length=math.hypot(p['x']-q['x'],p['y']-q['y']);assert length>1
   c2={k:q[k]+min(40,length/3)*(p[k]-q[k])/length for k in ('x','y')}
   for i in range(1,8):
    t=i/8;u=1-t;via.append({k:u**3*p[k]+3*u*u*t*c1[k]+3*u*t*t*c2[k]+t**3*q[k]for k in ['x','y']})
  args={'start':{'node':a['id']},'end':{'node':b['id']}if b['id']is not None else b['position'],'via':via,'street_type':'country/country_new_small','snap_radius':0,'max_segment_length':50,'allow_collisions':False}
  resolved={'anchor':a,'port':b}
  return args,resolved
 async def audit_road(self,item):
  c=item.get('commit',{});ids=c.get('edges',[])
  if not ids:return {'verified':False}
  nodes=[c['from']]
  if item['resolved']['port'].get('id')is not None:nodes.append(c['to'])
  src=(ROOT/'scripts/fullmap_road_audit.lua').read_text('utf8')
  return await self.eval(src.replace('TASKJSON',quote({'edges':ids,'nodes':nodes})))
 async def preflight_corridors(self):
  # Empty-site road corridor preview; actual ports are re-resolved after facilities.
  a=await self.node(self.anchor)
  points=[transform(self.template,self.origin,{'x':x,'y':-65})for x in [-41.5,8.2,109.5,237]]
  if self.p.get('collection'):points=self.p['collection']['corridor']
  for p,q in zip(points,points[1:]):
   r=await self.eval('return B.json.encode(B.commands.build_road(B.json.decode('+quote(dict(start=p,end=q,street_type='country/country_new_small',preview=True,allow_collisions=False,snap_radius=0))+')))')
   from hub_execution import strict_road_preview as road_preview_ok
   if not road_preview_ok(r):raise StopBatch('Road corridor preview blocked')
  self.ledger['corridorPreviewPassed']=True;self.flush()
  p,q=self.end,a['position'];ang=math.radians(self.template['sourceEvidence']['rotation'])
  c1={'x':p['x']+45*math.cos(ang),'y':p['y']+45*math.sin(ang)}
  length=math.hypot(p['x']-q['x'],p['y']-q['y']);assert length>1
  c2={k:q[k]+min(40,length/3)*(p[k]-q[k])/length for k in ('x','y')}
  via=[]
  for i in range(1,8):
   t=i/8;u=1-t;via.append({k:u**3*p[k]+3*u*u*t*c1[k]+3*u*t*t*c2[k]+t**3*q[k]for k in ['x','y']})
  r=await self.eval('return B.json.encode(B.commands.build_road(B.json.decode('+quote(dict(start=p,end={'node':a['id']},via=via,street_type='country/country_new_small',preview=True,allow_collisions=False,snap_radius=0))+')))')
  self.ledger['publicPreflight']=r;self.flush()
  if not road_preview_ok(r):raise StopBatch('Public road approach preview blocked')
 async def accept_collection(self):
  from accept_displayed_collection import accept_collection
  return await accept_collection(self)
 async def clone(self,t,apply=False):
  task=dict(t,position=dict(t['position']))
  task['position']['z']=await self.eval('return B.json.encode(api.engine.terrain.getHeightAt(api.type.Vec2f.new('+str(task['position']['x'])+','+str(task['position']['y'])+')))')
  return await Trial.clone(self,task,apply)
 async def execute(self):
  from hub_execution import execute_collection
  return await execute_collection(self,preview=self.a.action=='preview')

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','preview','build','run']);ap.add_argument('--output',type=Path,default=OUT);ap.add_argument('--template',type=Path);ap.add_argument('--anchor',type=float,nargs=2,metavar=('X','Y'));a=ap.parse_args()
 if a.action in ('prepare','run') and not (a.output/'plan.json').exists():
  if not a.anchor:raise StopBatch('New collection requires --anchor X Y from the site plan')
  template=a.template or ROOT/json.loads((ROOT/'exports/hub_template_default.json').read_text('utf8'))['template']
  await prepare(a.output,template,dict(zip(('x','y'),a.anchor)))
 elif a.action=='prepare':raise StopBatch('Fixed plan already exists')
 if a.action=='prepare':return
 if a.action=='run':a.action='build'
 a.plan=a.output/'plan.json';a.output=a.output/'execution';a.ids=None;a.road_ids=None;a.limit=0
 b=Copy(a)
 try:
  with batch_lock(b.b.dir):
   await b.execute()
 finally:b.flush()
if __name__=='__main__':asyncio.run(main())
