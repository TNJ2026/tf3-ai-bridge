"""Read-only batched native construction/road previews from an explicit plan.

No commit/save/speed commands. Writes evidence after each batch; unknown result stops.
"""
import argparse,asyncio,json,time,hashlib
from pathlib import Path
from batch_warehouses import Bridge,ROOT,batch_lock,write_json
from planning_pipeline_core import select_preview_rows

NATIVE=r'''
local task=TASK
local modules={};for k,v in pairs(task.params.modules or{})do modules[assert(tonumber(k))]=v end;task.params.modules=modules
local p=task.position;local z=api.engine.terrain.getHeightAt(api.type.Vec2f.new(p.x,p.y));local a=math.rad(task.rotation or 0)
local V=api.type.Vec4f.new;local ce=api.type.SimpleProposal.ConstructionEntity.new();ce.fileName=task.resource;ce.params=task.params;ce.playerEntity=api.engine.util.getPlayer();ce.name=task.id
ce.transf=api.type.Mat4f.new(V(math.cos(a),math.sin(a),0,0),V(-math.sin(a),math.cos(a),0,0),V(0,0,1,0),V(p.x,p.y,z,1))
local proposal=api.type.SimpleProposal.new();proposal.constructionsToAdd={ce};local context=api.type.Context.new();context.player=api.engine.util.getPlayer();context.checkTerrainAlignment=true
local pd=api.engine.util.proposal.makeProposalData(proposal,context);local es=pd.errorState;local collisions={};for _,c in ipairs(pd.collisionInfo.collisionEntities)do collisions[#collisions+1]=c.entity end
local bounds={};for _,d in ipairs(pd.toAddData)do local b=d.boundingVolume.bbox;bounds[#bounds+1]={min={x=b.min.x,y=b.min.y,z=b.min.z},max={x=b.max.x,y=b.max.y,z=b.max.z}}end
return {id=task.id,previewOnly=true,previewPassed=not es.critical and #es.messages==0 and #es.infos==0 and #es.warnings==0 and #collisions==0,critical=es.critical,messages=B.toPlain(es.messages),infos=B.toPlain(es.infos),warnings=B.toPlain(es.warnings),collisions=collisions,bounds=bounds,z=z,reputation={available=false,reason='Module-layout SimpleProposal: do not regenerate a create-template construction for statistics',scope='immediate_construction_preview'}}
'''

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--section',choices=['facilities','roads','stops','groups'],default='facilities');ap.add_argument('--limit',type=int);ap.add_argument('--owners',help='Comma-separated planning owners; only inspect affected groups');ap.add_argument('--ids',help='Comma-separated object IDs');a=ap.parse_args()
 plan=json.loads(a.plan.read_text('utf8'));rows=select_preview_rows(plan,a.section,a.owners.split(',')if a.owners else None,a.ids.split(',')if a.ids else None)
 if a.limit:rows=rows[:a.limit]
 if not rows:raise ValueError('Empty preview scope; no game call made')
 b=Bridge();assert b.heartbeat().get('connected');src=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8')
 pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+src+']========],"=planning_preview","t",env))()._internal;'
 generic=(ROOT/'scripts/fullmap_facility.lua').read_text('utf8');results=[];times=[];started=time.time()
 def encoded(x):return 'B.json.decode([======['+json.dumps(x,ensure_ascii=False)+']======])'
 with batch_lock(b.dir):
  for offset in range(0,len(rows),8):
   chunks=[]
   for row in rows[offset:offset+8]:
    if a.section=='groups':
     left,right=NATIVE.split('local proposal=')
     left=left.replace('local task=TASK','local group='+encoded(row)+';local cs={};local z=0;for _,task in ipairs(group.facilities)do')+'cs[#cs+1]=ce end;local task={id=group.id};'
     right=right.replace('proposal.constructionsToAdd={ce}','proposal.constructionsToAdd=cs')
     code=left+'local proposal='+right
    elif a.section=='facilities':
     code=NATIVE.replace('TASK',encoded(row)) if 'params'in row else generic.replace('local task=TASK','local task='+encoded(row)).replace('local action=ACTION',"local action='preview'")
    elif a.section=='roads':
     args=dict(start={'node':row['from_node_hint']}if 'from_node_hint'in row else row['path'][0],end=row['path'][-1],via=row['path'][1:-1],preview=True,allow_collisions=False,snap_radius=0,street_type=row.get('street_type','country/country_new_small'))
     code='return B.commands.build_road('+encoded(args)+')'
    else:
     args=dict(edge=row['edge_hint'],param=row['param'],side=row['side'],kind=row['kind'],two_sided=True,preview=True)
     code='return B.commands.build_street_stop('+encoded(args)+')'
    chunks.append('do local v=(function() '+code+' end)();if type(v)=="string"then v=B.json.decode(v)end;out[#out+1]={id='+json.dumps(row['id'])+',result=v}end')
   code=pre+'assert(api.engine.util.getPlayer()=='+str(plan['session']['player'])+',"Map player changed");local out={};'+'\n'.join(chunks)+';return B.json.encode(out)'
   start=time.time();res=await b.call('eval',{'code':code},engine=True,timeout=60)
   if isinstance(res,str):res=json.loads(res)
   if not isinstance(res,list):raise RuntimeError(str(res))
   results.extend(res);times.append({'offset':offset,'count':len(res),'seconds':time.time()-start});write_json(a.output,{'section':a.section,'plan_hash':hashlib.sha256(a.plan.read_bytes()).hexdigest(),'results':results,'batches':times,'seconds':time.time()-started,'preview_only':True})
   print(json.dumps({'offset':offset,'count':len(res),'seconds':times[-1]['seconds']}),flush=True)
 print(json.dumps({'count':len(results),'seconds':time.time()-started}))
if __name__=='__main__':asyncio.run(main())
