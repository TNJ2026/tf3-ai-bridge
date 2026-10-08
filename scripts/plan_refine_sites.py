"""Bounded read-only candidate refinement. Never submits a world command."""
import argparse,asyncio,json,math,copy,time
from pathlib import Path
from batch_warehouses import Bridge,ROOT,batch_lock,write_json
from plan_native_preview import NATIVE
from tf3_mcp.site_planner import BoxIndex

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--coast-only',action='store_true');a=ap.parse_args();R=a.output;p=json.loads((R/'network_plan.json').read_text('utf8'));s=json.loads(Path(p['snapshot']).read_text('utf8'));idx=BoxIndex(s['obstacles']);b=Bridge();src=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8');pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+src+']========],"=site_refinement","t",env))()._internal;';body=(ROOT/'scripts/fullmap_facility.lua').read_text('utf8').replace('local task=TASK','').replace('local action=ACTION','local action="preview"');evidence=[]
 def enc(x):return 'B.json.decode([======['+json.dumps(x,ensure_ascii=False)+']======])'
 async def call(code):
  v=await b.call('eval',{'code':pre+code},engine=True,timeout=60);return json.loads(v)if isinstance(v,str)else v
 def move(f,dx,dy):
  for field in ['position']:
   f[field]['x']+=dx;f[field]['y']+=dy
  for k in ['footprint','reserved']:
   if k in f:
    for end in ['min','max']:f[k][end]['x']+=dx;f[k][end]['y']+=dy
 with batch_lock(b.dir):
  # Translate the whole template; never detach its warehouse from the shared layout.
  for owner,dx,dy in ([]if a.coast_only else[('I18489',-100,0),('I34694',0,110)]):
   h=next(h for h in p['hubs']if h['owner']==owner);h['position']['x']+=dx;h['position']['y']+=dy
   for f in p['facilities']:
    if f.get('owner')==owner:move(f,dx,dy)
   for r in p['roads']:
    if r['id'].startswith(owner+'_'):
     for v in r['path'][1:]if r['id'].endswith('_external')else r['path']:v['x']+=dx;v['y']+=dy
     if 'origin'in r:r['origin']=copy.deepcopy(h['position'])
  # Coast geometry is sampled at native resolution first; at most 3 proposal previews/site.
  for port in p['ports']:
   for kind in ['harbor','water_depot']:
    target=port if kind=='harbor'else next(f for f in p['facilities']if f['id']==port['purchase_base']);tasks=[]
    if target.get('native_preview',{}).get('previewPassed'):continue
    for c in port['candidates']:
     dx,dy=c['water_direction']['x'],c['water_direction']['y'];rot=math.degrees(math.atan2(dx,-dy))%360
     for advance in [-20,-10,0,10,20,30,40,50,60]:
      for along in ([0,-15,15]if kind=='harbor'else[0,-30,30]):
       v={'x':c['position']['x']+dx*advance-dy*along,'y':c['position']['y']+dy*advance+dx*along,'z':2}
       distance=math.dist([v['x'],v['y']],[port['position']['x'],port['position']['y']])
       if kind=='harbor'and distance>130:continue
       if kind=='water_depot'and distance<90:continue
       t=copy.deepcopy(target);t.update(position=v,rotation=rot);tasks.append(t)
    tests='{{0,13.75,false},{0,-29.375,true},{-20,-29.375,true},{20,-29.375,true}}'if kind=='harbor'else'{{0,40,false},{0,-5,true},{0,-55,true},{-15,-30,true},{15,-30,true}}'
    code='local out={};for _,t in ipairs('+enc(tasks)+')do local a=math.rad(t.rotation);local valid=true;for _,v in ipairs('+tests+')do local q=api.type.Vec2f.new(t.position.x+v[1]*math.cos(a)-v[2]*math.sin(a),t.position.y+v[1]*math.sin(a)+v[2]*math.cos(a));if api.engine.terrain.isOnWater(q)~=v[3]then valid=false;break end end;if valid then t.shoreScore=math.abs(api.engine.terrain.getHeightAt(api.type.Vec2f.new(t.position.x,t.position.y))-2);out[#out+1]=t end end;return B.json.encode(out)'
    dense='if valid then for u=-15,15,2.5 do for v=-55,-5,2.5 do local q=api.type.Vec2f.new(t.position.x+u*math.cos(a)-v*math.sin(a),t.position.y+u*math.sin(a)+v*math.cos(a));if not api.engine.terrain.isOnWater(q)then valid=false;break end end;if not valid then break end end end;'if kind=='water_depot'else'if valid then for u=-26,26,4 do for v=-42,-18,4 do local q=api.type.Vec2f.new(t.position.x+u*math.cos(a)-v*math.sin(a),t.position.y+u*math.sin(a)+v*math.cos(a));if not api.engine.terrain.isOnWater(q)then valid=false;break end end;if not valid then break end end end;'
    code=code.replace('if valid then t.shoreScore',dense+'if valid then t.shoreScore')
    candidates=await call(code);candidates.sort(key=lambda t:math.dist([t['position']['x'],t['position']['y']],[port['position']['x'],port['position']['y']])+t['shoreScore']*10);found=False
    for task in candidates[:3]:
     r=await call('local task='+enc(task)+';'+body);evidence.append({'id':target['id'],'task':task,'result':r})
     if r.get('previewPassed'):
      dx,dy=task['position']['x']-target['position']['x'],task['position']['y']-target['position']['y'];move(target,dx,dy);target['rotation']=task['rotation'];target['native_preview']=r;target['status']='native_single_placement_preview_passed';found=True;break
    print(json.dumps({'id':target['id'],'screened':len(tasks),'candidates':len(candidates),'passed':found}),flush=True)
  # Replace the rejected cement access anchor with the nearest clear public node candidate.
  if a.coast_only:
   write_json(R/'network_plan.json',p);write_json(R/'coast_refinement_evidence.json',evidence);return
  r=next(r for r in p['roads']if r['id']=='I34718_external');nodes={};frozen=set(json.loads((R/'details.json').read_text('utf8'))['frozenNodes'])
  for e in s['obstacles']:
   if e['kind']=='BASE_EDGE':
    for j in (0,1):
     if e['node'+str(j)]not in frozen:nodes[e['node'+str(j)]]=e['position'+str(j)]
  end=r['path'][-1]
  candidates=sorted((n for n in nodes if n!=r['from_node_hint']),key=lambda n:math.dist([nodes[n]['x'],nodes[n]['y']],[end['x'],end['y']]))
  for n in candidates[:3]:
   args={'start':{'node':n},'end':end,'preview':True,'snap_radius':0,'street_type':r['street_type']};v=await call('return B.json.encode(B.commands.build_road('+enc(args)+'))');evidence.append({'id':r['id'],'candidate':args,'result':v})
   if v.get('buildable'):r.update(from_node_hint=n,from_position=nodes[n],path=[nodes[n],end],native_preview=v);break
 write_json(R/'network_plan.json',p);write_json(R/'refinement_evidence.json',evidence)
 print(json.dumps({'evidence':len(evidence)}))
if __name__=='__main__':asyncio.run(main())
