"""Current-plan maintenance selection/build using the common native facility gate."""
import argparse,asyncio,json,math
from pathlib import Path
from fullmap_batch import Batch,ROOT,batch_lock,write_json,StopBatch,quote

class ExpansionMaintenance(Batch):
 def tasks(self):return json.loads((self.out.parent/'maintenance_selected.json').read_text(encoding='utf8'))

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['select','build','verify']);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args()
 a.plan=a.root/'plan.json';a.output=a.root/'execution';a.ids=None;a.limit=0;a.read_batch_size=1
 b=ExpansionMaintenance(a)
 with batch_lock(b.b.dir):
  await b.session()
  if a.action!='select':return await b.run()
  survey=await b.eval((ROOT/'scripts/maintenance_survey.lua').read_text(encoding='utf8').replace('TARGETS',quote([])))
  write_json(a.root/'maintenance_before.json',survey)
  models=await b.eval((ROOT/'scripts/fleet_model_survey.lua').read_text(encoding='utf8'));write_json(a.root/'models.json',models)
  targets=[]
  for i in b.p['industries']:
   if any(x in i['resource']for x in ('oil_platform','fishing_grounds','forest')):continue
   targets.append(dict(id='IND'+str(i['id']),position=i['position']))
  for f in b.p['facilities']:
   if f['kind']=='truck' and f['id'].startswith('I'):targets.append(dict(id=f['id'],position=f['position']))
  selected=[];trials=[]
  for target in targets:
   p=target['position']
   if any(math.hypot(p['x']-f['position']['x'],p['y']-f['position']['y'])<430 for f in selected):continue
   # Native-only proposals: reject collisions/warnings; no bypass or repeated submission.
   found=False
   for radius in (90,150,230):
    for angle in (45,135,225,315,0,90,180,270):
     x=p['x']+radius*math.cos(math.radians(angle));y=p['y']+radius*math.sin(math.radians(angle))
     if abs(x)>4000 or abs(y)>4000:continue
     task=dict(id='SERVICE_'+target['id'],kind='road_maintenance',position=dict(x=x,y=y),rotation=angle,status='planned',args={},params={'seed':1,'modules':{}},serviceTarget=target)
     result=await b.facility(task,'preview');trials.append(dict(task=task,result=result));write_json(a.root/'maintenance_previews.json',trials)
     if result.get('previewPassed'):
      selected.append(task);found=True;print(task['id']+': native preview passed',flush=True);break
    if found:break
   if not found:raise StopBatch(target['id']+' no maintenance candidate passed')
  write_json(a.root/'maintenance_selected.json',selected)
  print('selected',len(selected))

if __name__=='__main__':asyncio.run(main())
