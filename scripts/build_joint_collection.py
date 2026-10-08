"""One native proposal per collection: facilities AND internal roads, no sequential fallback."""
import argparse,asyncio,copy,json,math,time,hashlib
from pathlib import Path
from fullmap_batch import Batch,StopBatch,batch_lock,quote,write_json,unfinished
from fullmap_workflow import atomic_write
from hub_joint_prototype import compile_spec,probe
from joint_external import append_external, REBIND, PREVIEW, READBACK
from commit_joint_test import GUARD
from verify_joint_test import AUDIT,acceptance,expected_roadside_offsets

def prepared_for_file(plan_path,plan,owner,compiled_dir=None):
    hub,spec,origin=prepare(plan,owner)
    if compiled_dir:
        pinned=json.loads((compiled_dir/(owner+'.json')).read_text('utf8'))
        if pinned.get('planDigest')!=hashlib.sha256(plan_path.read_bytes()).hexdigest():
            raise StopBatch('Compiled collection is stale; regenerate offline')
        if pinned['spec']!=spec or pinned['origin']!=origin:
            raise StopBatch('Compiled geometry differs from current plan/compiler')
        spec,origin=pinned['spec'],pinned['origin']
    return hub,spec,origin

def prepare(plan,owner,include_external=True):
    hub=next(h for h in plan['hubs'] if h['owner']==owner)
    template=copy.deepcopy(plan['templates'][hub['template']])
    by_id={f['id']:f for f in plan['facilities']}
    a=math.radians(hub['rotation']);cs,sn=math.cos(a),math.sin(a)
    for f in template['facilities']:
        actual=by_id[hub['facilities'][f['role']]]
        dx=actual['position']['x']-hub['position']['x'];dy=actual['position']['y']-hub['position']['y']
        f.update(localPosition=dict(x=cs*dx+sn*dy,y=-sn*dx+cs*dy,z=0),relativeRotation=actual['rotation']-hub['rotation'],params=copy.deepcopy(actual['params']),resource=actual['resource'])
    planned=[r for r in plan['roads']if r['id'].startswith(owner+'_')and r.get('templateRoad')]
    if len(planned)!=len(template['roads']):raise ValueError('Internal road plan/template mismatch')
    template['roads']=[]
    for road in planned:
        if len(road['path'])!=2:raise ValueError('Curved internal road requires explicit joint geometry')
        row=copy.deepcopy(road['templateRoad'])
        for k,p in enumerate(road['path']):
            dx=p['x']-hub['position']['x'];dy=p['y']-hub['position']['y']
            row['position'+str(k)]=dict(x=cs*dx+sn*dy,y=-sn*dx+cs*dy,z=0)
        for k in ('tangent0','tangent1'):row.pop(k,None)
        row['roadTemplate']=road.get('street_type',row['roadTemplate'])
        template['roads'].append(row)
    spec=compile_spec(template)
    if set(hub['facilities'])!={f['role']for f in spec['facilities']}:raise ValueError('Collection role mismatch')
    origin=dict(hub['position'],rotation=hub['rotation'])
    return hub,append_external(plan,hub,spec,origin) if include_external else spec,origin

def code_for(spec,origin,build=False):
    source=probe(spec).replace('local isolatedTestConfirmed=false','local isolatedTestConfirmed=true')
    source=source.replace('local origin=nil -- {x=...,y=...,rotation=...}; choose empty land in the test save','local origin=B.json.decode('+quote(origin)+')')
    prefix=source.split('return B.json.encode({previewOnly=true')[0]
    if spec.get('externalAnchor'):
        prefix=prefix.replace('for _,row in ipairs(spec.roads)do', REBIND+'for _,row in ipairs(spec.roads)do', 1)
    # Same strict placement and directed vehicle-path checks for preview and commit.
    checks=GUARD.split('local CT=api.type.ComponentType')[0]
    if spec.get('requireWalkingPreview'):
        prefix+=Path(__file__).with_name('road_first_walk.lua').read_text('utf8')
        prefix+="\nassert(walkPreview.outbound and walkPreview.inbound,'Walking preview failed before joint submission')\n"
    extra=PREVIEW if spec.get('externalAnchor') else ''
    commit=GUARD.replace('local CT=api.type.ComponentType',extra+'local CT=api.type.ComponentType',1)
    return prefix+(commit if build else checks+extra+'return B.json.encode({previewOnly=true,previewPassed=true,previewPaths=paths,airportRoadLinks=airportRoadLinks,externalPaths=externalPaths,portBindings=spec.portBindings})')

def require_supported_commit(spec):
    """Fail before live calls for the multi-facility generated-port commit path.

    A clean proposal preview is insufficient: the isolated phase-one core
    asserted in sendCommand on 2026-10-07. Preview remains diagnostic only.
    Single-facility direct-frontage operations are a separate acceptance path.
    """
    if spec.get('bindGeneratedPorts') and len(spec.get('facilities', [])) > 1:
        raise StopBatch('Multi-facility generated-port joint submission is suspended after Engine.h:323; use a separately validated staged implementation, not another preview or retry')


async def execute(a):
    b=Batch(a);hub,spec,origin=prepared_for_file(getattr(a,'plan',None),b.p,a.owner,getattr(a,'compiled_dir',None))
    out=b.out/('joint_'+a.owner);out.mkdir(parents=True,exist_ok=True)
    if a.action=='prepare':
        write_json(out/'joint_spec.json',spec);write_json(out/'origin.json',origin)
        atomic_write(out/'isolated_preview.lua',probe(spec));return
    if not a.isolated_test_save and not getattr(a,'current_map_test',False):raise StopBatch('Unvalidated joint implementation requires a confirmed isolated test save (--isolated-test-save), or explicit user authorization for this current-map test')
    if a.action=='build'and not a.authorize_build:raise StopBatch('Explicit build authorization required')
    if a.action=='build':require_supported_commit(spec)
    with batch_lock(b.b.dir):
        try:
            state=await b.session()
            if state['speedup']!=0:raise StopBatch('Pause required for joint placement')
            if getattr(a,'current_map_test',False):
                b.ledger['testAuthorization']='Explicit user request to test at a new site on the current map; not a claim that this is an isolated save'
            if unfinished(b.ledger):raise StopBatch('Unreconciled submissions; no replay')
            for name,field in [('facility_amendments.json','facilities'),('planned_road_amendments.json',None),('extra_roads.json','roads')]:
                path=b.out/name
                if path.exists():
                    patches=json.loads(path.read_text('utf8'));patches=patches[field]if field else patches
                    ids=[r['id']for r in patches]if isinstance(patches,list)else patches
                    if any(k.startswith(a.owner+'_')for k in ids):raise StopBatch('Execution amendments exist; merge into the plan before joint placement')
            key='JOINT_'+a.owner
            old=b.ledger['items'].get(key,{})
            if old.get('attempts'):raise StopBatch('Joint placement already attempted; read back without replay')
            if any(b.ledger['items'].get(k,{}).get('attempts') for k in spec.get('consumedRoadIds',[])):raise StopBatch('Group roads already attempted; reconcile')
            tasks=[t for t in b.tasks() if t['id']in hub['facilities'].values()]
            rows=await b.read_facilities(tasks,'verify',with_session=True)
            if any(r['result'].get('existing') for r in rows):raise StopBatch('Collection wholly/partly exists; reconcile instead of overlapping placement')
            write_json(out/'joint_spec.json',spec);write_json(out/'origin.json',origin)
            # An experimental native PREVIEW can assert too; back up before it.
            await b.save('joint_preview_before')
            preview=await b.eval(code_for(spec,origin));write_json(out/'preview.json',preview)
            if preview.get('previewPassed')is not True:raise StopBatch('Joint preview rejected')
            if a.action=='preview':return
            await b.save('joint_before');await b.session()
            # Journal BEFORE the sole world command; exceptions/unknown callbacks lock the group.
            item={'kind':'joint_collection','attempts':1,'status':'commit_started','intentTime':time.time(),'facilities':list(hub['facilities'].values())}
            b.ledger['items'][key]=item;b.flush()
            try:
                result=await b.eval(code_for(spec,origin,True));item['commit']=result;b.flush();write_json(out/'commit_result.json',result)
                if result.get('callback',{}).get('success')is not True or len(result.get('added',{}).get('constructions',[]))!=len(tasks):raise StopBatch('Joint commit incomplete/unknown')
                verified=await b.read_facilities(tasks,'verify',with_session=True)
                audits={t['id']:r['result'].get('audit',{}) for t,r in zip(tasks,verified)}
                if not all(x.get('staticVerified')for x in audits.values()):raise StopBatch('Facility readback failed')
                if {x['entity'] for x in audits.values()}!=set(result['added']['constructions']):raise StopBatch('Unexpected construction set')
                expected={role:next(t['position']for t in tasks if t['id']==fid)for role,fid in hub['facilities'].items()}
                expected=expected_roadside_offsets(expected,spec)
                if spec.get('externalAnchor'):
                    road=next(r for r in b.p['roads'] if r['id'] in spec['consumedRoadIds'] and not r.get('templateRoad'))
                    expected['externalAnchor']=road['path'][0]
                audit=await b.eval(AUDIT.replace('return B.json.encode(out)',READBACK+'return B.json.encode(out)').replace('IDS',quote(result['added'])).replace('EXPECTED',quote(expected)))
                norm=lambda m:{str(k):(v['name'],v.get('variant',0)) for k,v in (m or {}).items()}
                audit['modulesVerified']=all(norm(t['params'].get('modules'))==norm(audits[t['id']]['params'].get('modules'))for t in tasks)
                audit['staticAccepted']=acceptance(audit,a.defer_walking,spec);audit['operationalAccepted']=False
                item['audit']=audit;write_json(out/'verification.json',audit)
                if not audit['placementAccepted']:raise StopBatch('Joint placement acceptance incomplete')
                for t in tasks:b.ledger['items'][t['id']]={'kind':t['kind'],'attempts':1,'jointOperation':key,'status':'static_verified','audit':audits[t['id']]}
                for rid in spec.get('consumedRoadIds',[]):b.ledger['items'][rid]={'kind':'connection','attempts':1,'jointOperation':key,'status':'static_verified','consumedByJoint':True,'audit':audit['roads']}
                item['status']='static_verified';b.flush()
                await b.save('joint_placement_complete')
                print(json.dumps({'owner':a.owner,'nativeSubmissions':1,'facilities':len(tasks),'internalRoads':len(spec['roads']),'walkingDeferred':a.defer_walking}),flush=True)
            except BaseException:
                item['status']='needs_reconciliation';b.flush();raise
        finally:b.flush()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','preview','build']);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--owner',required=True);p.add_argument('--compiled-dir',type=Path);p.add_argument('--isolated-test-save',action='store_true');p.add_argument('--current-map-test',action='store_true',help='Only after explicit user authorization to test on the current map');p.add_argument('--authorize-build',action='store_true');p.add_argument('--defer-walking',action='store_true')
    a=p.parse_args();a.ids=None;a.limit=0;asyncio.run(execute(a))
if __name__=='__main__':main()
