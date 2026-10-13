"""One expanded hub trial: explicit source clones, strict staged previews and journal."""
import asyncio,argparse,json,math,sys,time
from pathlib import Path
from types import SimpleNamespace
from fullmap_batch import Batch,ROOT,quote,StopBatch,batch_lock
from batch_warehouses import write_json
from tf3_mcp.route_planner import Terrain
from tf3_mcp.site_planner import BoxIndex

OUT=ROOT/'exports/hub_trial'
TEMPLATE=ROOT/'exports/hub_template_current/template/hub_template.json'
SNAP=OUT/'survey/snapshot-17eb655b4808.json'

def transform(t,origin,p):
 a=math.radians(t['sourceEvidence']['rotation']);c,s=math.cos(a),math.sin(a)
 return dict(x=origin['x']+c*p['x']-s*p['y'],y=origin['y']+s*p['x']+c*p['y'])

def prepare():
 s=json.loads(SNAP.read_text('utf8'));t=json.loads(TEMPLATE.read_text('utf8'));terrain=Terrain(s['grid'])
 town=next(c for c in s['map']['towns']if c['id']==44531)
 obstacles=[o for o in s['obstacles']if o['kind']in ('TOWN_BUILDING','CONSTRUCTION','BASE_EDGE')];idx=BoxIndex(obstacles)
 buildings=[o for o in obstacles if o['kind']=='TOWN_BUILDING'and math.hypot((o['min']['x']+o['max']['x'])/2-town['position']['x'],(o['min']['y']+o['max']['y'])/2-town['position']['y'])<1200]
 nodes={}
 for e in obstacles:
  if e['kind']=='BASE_EDGE'and 'street/'in e.get('roadTemplate',''):
   for k in (0,1):nodes[e['node'+str(k)]]=e['position'+str(k)]
 options=[]
 for x in range(-3850,-1450,100):
  for y in range(250,2600,100):
   o=dict(x=x,y=y);d=math.hypot(x-town['position']['x'],y-town['position']['y'])
   if not 700<d<1500:continue
   box={'min':{'x':x-105,'y':y-200},'max':{'x':x+235,'y':y+105}}
   if idx.blocked(box):continue
   def boxdistance(b):return math.hypot(max(b['min']['x']-(x+72),(x-73)-b['max']['x'],0),max(b['min']['y']-(y+71),(y-70)-b['max']['y'],0))
   if buildings and min(map(boxdistance,buildings))<500:continue
   levels=[];dry=True
   for dx in (-90,0,100,220):
    for dy in (-180,-60,60,90):
     try:z,w=terrain.sample(x+dx,y+dy)
     except ValueError:dry=False;continue
     levels.append(z);dry=dry and not w
   if not dry or max(levels)-min(levels)>4:continue
   end=transform(t,o,{'x':208.083,'y':-68})
   choices=sorted(nodes.items(),key=lambda pair:math.hypot(pair[1]['x']-end['x'],pair[1]['y']-end['y']))[:3]
   for nid,np in choices:
    roadlen=math.hypot(np['x']-end['x'],np['y']-end['y'])
    if roadlen<450:options.append(dict(origin=o,anchor=np,anchorHint=nid,score=roadlen+d*.15,heightRange=max(levels)-min(levels)))
 options.sort(key=lambda r:r['score']);write_json(OUT/'candidates.json',options[:9]);print(json.dumps(options[:3]))

def make_plan(index):
 s=json.loads(SNAP.read_text('utf8'));t=json.loads(TEMPLATE.read_text('utf8'));candidate=json.loads((OUT/'candidates.json').read_text('utf8'))[index];terrain=Terrain(s['grid']);fs=[]
 for f in t['facilities']:
  pos=transform(t,candidate['origin'],f['localPosition']);pos['z']=terrain.sample(pos['x'],pos['y'])[0]
  fs.append(dict(id='TRIAL_'+f['role'],kind=f['role'],position=pos,rotation=t['sourceEvidence']['rotation']+f['relativeRotation'],command='build_facility',args={'source_entity':t['sourceEvidence']['facilities'][f['role']]},status='trial',expectedParams=f['params'],sourcePosition=next(x['position']for x in json.loads((ROOT/'exports/hub_template_current/capture.json').read_text('utf8'))['facilities']if x['role']==f['role'])))
 p=dict(facilities=fs,ports=[],roads=[],cities=s['map']['towns'],industries=[dict(i,resource=i['fileName'])for i in s['map']['industries']],session=s['state'],focus_town=44531,candidate=candidate,template=str(TEMPLATE))
 write_json(OUT/'plan.json',p);return p

class Trial(Batch):
 async def clone(self,t,apply=False):
  args=dict(t['args'],**t['position'],rotation=t['rotation'],name='重庆集合试建 · '+t['kind'])
  code='''local t=B.json.decode(TASK);local args=B.json.decode(ARGS);local src=B.commands.get_facility_config({entity=args.source_entity});local p=src.position
assert(math.abs(p.x-t.sourcePosition.x)<.2 and math.abs(p.y-t.sourcePosition.y)<.2,'source moved');
local expected=t.expectedParams.modules or{};local actual=src.params.modules or{};local n,m=0,0
for k,v in pairs(expected)do n=n+1;local a=actual[k]or actual[tonumber(k)];assert(a and a.name==v.name and a.variant==v.variant,'source modules changed')end
for _ in pairs(actual)do m=m+1 end;assert(n==m,'source expanded since capture')
local r=B.commands.build_facility(args);local c=r.check;local safe=c and c.ok and not c.critical and not c.blocked and not c.placementBlocked
for _,k in ipairs({'infos','warnings','messages','collisions'})do if c and c[k]and #c[k]>0 then safe=false end end
local out={preview=r,safe=safe};if APPLY then assert(safe,'clone preview blocked');out.commit=B.commands.commit_facility({preview_token=r.preview_token})end
return B.json.encode(out)'''.replace('TASK',quote(t)).replace('ARGS',quote(args)).replace('APPLY','true'if apply else'false')
  return await self.eval(code)
 async def run_trial(self):
  await self.session()
  if self.a.action=='preview':
   for t in self.tasks():
    r=await self.clone(t);self.ledger['items'][t['id']]={'attempts':0,'preview':r,'status':'preview_ready'if r['safe']else'preview_blocked'};self.flush();print(t['id']+': '+str(r['safe']),flush=True)
   return
  from fullmap_batch import unfinished
  # Historical business ledger entries do not gate unrelated work.
  road_preflight=json.loads((OUT/'road_preflight.json').read_text('utf8'))
  if not road_preflight or not all(r.get('safe')for r in road_preflight):raise StopBatch('Missing road preflight')
  await self.save('before')
  for t in self.tasks():
   await self.session();item=self.ledger['items'].setdefault(t['id'],{'attempts':0})
   existing=await self.facility(t,'verify')
   if existing.get('existing'):item.update(audit=existing['audit'],status='static_verified');self.flush();continue
   if item['attempts']:raise StopBatch('Never replay missing submission')
   pre=await self.clone(t)
   if not pre['safe']:item.update(status='preview_blocked',preview=pre);self.flush();raise StopBatch('Clone preview rejected')
   item.update(attempts=1,status='commit_started');self.flush()
   try:
    result=await self.clone(t,True);item['result']=result;self.flush()
    if not result.get('commit',{}).get('built'):raise StopBatch('Clone outcome incomplete')
    check=await self.facility(t,'verify');item['audit']=check.get('audit');
    if not check.get('audit',{}).get('staticVerified'):raise StopBatch('Static readback failed')
    cfg=await self.eval('return B.json.encode(B.commands.get_facility_config({entity='+str(item['audit']['entity'])+'}))')
    exp=t['expectedParams']['modules'];mods=cfg['params']['modules']
    if {k:(v['name'],v.get('variant',0))for k,v in mods.items()}!={k:(v['name'],v.get('variant',0))for k,v in exp.items()}:raise StopBatch('Expansion mismatch')
    item['status']='static_verified';self.flush();print(t['id']+': cloned expansions verified',flush=True)
   except BaseException:item['status']='needs_reconciliation';self.flush();raise
  await self.save('facilities_complete')

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','preview','build']);ap.add_argument('--candidate',type=int,default=0);a=ap.parse_args()
 if a.action=='prepare':prepare();return
 if a.action=='preview':
  if (OUT/'execution/ledger.json').exists():raise StopBatch('Existing preview journal: use its fixed plan or archive read-only preview first')
  make_plan(a.candidate)
 a.plan=OUT/'plan.json';a.output=OUT/'execution';a.ids=None;a.limit=0
 b=Trial(a)
 try:
  with batch_lock(b.b.dir):await b.run_trial()
 finally:b.flush()
if __name__=='__main__':asyncio.run(main())
