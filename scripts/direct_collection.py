"""Road-first direct-port collections using the tested native proposal sequence."""
import argparse,asyncio,copy,json,time
from pathlib import Path
from fullmap_batch import Batch,batch_lock,quote,write_json
from build_joint_collection import prepare,code_for
from road_first_collection import stage_spec,source,road_readback,SNAP_HEIGHT
from commit_joint_test import GUARD
from verify_joint_test import AUDIT,acceptance,expected_roadside_offsets
from direct_collection_parts import direct_source,CROSSWALK

async def survey(b,o):
 code='''local C=api.type.ComponentType;local out={nodes={},edges={}};local seen={};for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(X,Y),350,C.BASE_EDGE))do local e=api.engine.getComponent(id,C.BASE_EDGE);local row={id=id,node0=e.node0,node1=e.node1,roadTemplate=e.roadTemplate,roadStyle=e.roadStyle};for k=0,1 do local n=k==0 and e.node0 or e.node1;local p=api.engine.getComponent(n,C.BASE_NODE).position;row['position'..k]={x=p.x,y=p.y,z=p.z};local t=k==0 and e.tangent0 or e.tangent1;row['tangent'..k]={x=t.x,y=t.y,z=t.z};if not seen[n]then seen[n]=true;out.nodes[#out.nodes+1]={entity=n,position={x=p.x,y=p.y,z=p.z}}end end;out.edges[#out.edges+1]=row end;return B.json.encode(out)'''
 return await b.eval(code.replace('X',str(o['x'])).replace('Y',str(o['y'])))

async def commit(b,key,previewcode,buildcode):
 item=b.ledger['items'].get(key,{})
 assert not item.get('attempts'),'Never replay '+key
 await b.session();p=await b.eval(previewcode);write_json(b.out/(key+'_preview.json'),p)
 assert p.get('passed',p.get('previewPassed',False)),'Native preview blocked '+key
 item={'attempts':1,'status':'commit_started','preview':p,'time':time.time()};b.ledger['items'][key]=item;b.flush()
 try:
  r=await b.eval(buildcode);item['commit']=r;b.flush()
  assert r.get('callback',{}).get('success',r.get('success')) is True,'Commit failed '+key
  item['status']='submitted_pending_readback';b.flush();return r
 except BaseException:
  item['status']='needs_reconciliation';b.flush();raise

async def audit(b,h,s,o,tasks):
 current=await b.read_facilities(tasks,'verify',with_session=True)
 assert all(r['result'].get('audit',{}).get('staticVerified')for r in current),'Facility readback failed'
 live=await survey(b,o);ids={'constructions':[r['result']['audit']['entity']for r in current],'edges':[e['id']for e in live['edges']],'nodes':[]}
 expected=expected_roadside_offsets({role:next(t['position']for t in tasks if t['id']==fid)for role,fid in h['facilities'].items()},s)
 v=await b.eval(AUDIT.replace('IDS',quote(ids)).replace('EXPECTED',quote(expected)))
 norm=lambda m:{str(k):(v['name'],v.get('variant',0))for k,v in (m or{}).items()}
 v['modulesVerified']=all(norm(t['params'].get('modules'))==norm(r['result']['audit']['params'].get('modules'))for t,r in zip(tasks,current))
 v['accepted']=acceptance(v,False,s);write_json(b.out/'verification.json',v)
 return v

async def crosswalk(b,h,tasks):
 if 'bus'in h['facilities']:
  bus=next(t['position']for t in tasks if t['id']==h['facilities']['bus']);air=next(t['position']for t in tasks if t['id']==h['facilities']['heliport'])
  code=CROSSWALK.replace('BUS_X',str(bus['x'])).replace('BUS_Y',str(bus['y'])).replace('AIR_X','('+str(air['x'])+')').replace('AIR_Y','('+str(air['y'])+')')
  await commit(b,'crosswalk',code+'out.passed=true;return B.json.encode(out)',code+'api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(_,ok)out.success=ok==true end);return B.json.encode(out)')

async def run(a):
 b=Batch(a);h,s,o=prepare(b.p,a.owner,include_external=False);tasks=[t for t in b.tasks()if t['id']in h['facilities'].values()]
 with batch_lock(b.b.dir):
  await b.session();current=await b.read_facilities(tasks,'verify')
  existing=[r['result'].get('existing',False)for r in current]
  if all(existing):
   v=await audit(b,h,s,o,tasks)
   if v.get('acceptanceFailures')==['walking'] and b.ledger['items'].get('remaining',{}).get('status')=='submitted_pending_readback' and not b.ledger['items'].get('crosswalk',{}).get('attempts'):
    await crosswalk(b,h,tasks);v=await audit(b,h,s,o,tasks)
   assert v['accepted'],'Existing collection audit failed'
   for item in b.ledger['items'].values():item['status']='static_verified'
   b.flush();await b.save('collection_verified');print(a.owner+': existing accepted',flush=True);return
  partial=any(existing)
  if partial:
   assert b.ledger['items'].get('roads',{}).get('status')=='static_verified','Unrecorded partial roads'
   for row in current:
    if row['result'].get('existing'):
     role=next(role for role,fid in h['facilities'].items()if fid==row['id']);assert b.ledger['items'].get(role,{}).get('status')=='static_verified','Unreconciled facility '+role
  else:
   assert not any(v.get('attempts')for v in b.ledger['items'].values()),'Prior submissions require reconciliation'
   await b.save(a.owner+'_before')
   joint=await b.eval(code_for(s,o));write_json(b.out/'joint_preview.json',joint);assert joint['previewPassed']
   rs=stage_spec(s,'roads');r=await commit(b,'roads',source(rs,o,'roads'),source(rs,o,'roads',True))
   await road_readback(b,rs,o,r['added']);b.ledger['items']['roads']['status']='static_verified';b.flush()
  for role in ('truck','bus','road_depot'):
   if role not in h['facilities']:continue
   t=next(t for t in tasks if t['id']==h['facilities'][role])
   if (await b.facility(t,'verify')).get('existing'):continue
   live=await survey(b,o);code=direct_source(s,t,live)
   r=await commit(b,role,code,code.split('local diagnostic=')[0]+GUARD)
   v=await b.facility(t,'verify');assert v.get('audit',{}).get('staticVerified');b.ledger['items'][role]['status']='static_verified';b.flush()
  rest=copy.deepcopy(s);rest['facilities']=[f for f in s['facilities']if f['role']not in ('truck','bus','road_depot')]
  rest.update(nodes=[],roads=[],portBindings={},bindGeneratedPorts=False,requireWalkingPreview=False,existingRoadEntities=[e['id']for e in (await survey(b,o))['edges']])
  def remaining(build=False):
   return code_for(rest,o,build).replace('for _,f in ipairs(spec.facilities)do',SNAP_HEIGHT+'\nfor _,f in ipairs(spec.facilities)do',1).replace('local p=point(f.localPosition,f.heightPolicy)','local p=roadsideHeight(f,point(f.localPosition,f.heightPolicy))',1)
  await commit(b,'remaining',remaining(),remaining(True))
  await crosswalk(b,h,tasks)
  v=await audit(b,h,s,o,tasks);assert v['accepted'],'Collection acceptance failed '+str(v.get('acceptanceFailures'))
  for item in b.ledger['items'].values():item['status']='static_verified'
  b.flush();await b.save('collection_complete');print(a.owner+': built and accepted',flush=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--owner',required=True);a=p.parse_args();a.action='build';a.ids=None
 asyncio.run(run(a))
if __name__=='__main__':main()
