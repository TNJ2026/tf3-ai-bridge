"""Road-first city/dual-pad production collections with role-specific acceptance."""
import argparse, asyncio, copy, json, time
from pathlib import Path
from fullmap_batch import Batch, StopBatch, batch_lock, quote, unfinished, write_json
from build_joint_collection import prepare
from hub_joint_prototype import probe
from commit_joint_test import GUARD
from verify_joint_test import AUDIT, acceptance, expected_roadside_offsets

WALK = Path(__file__).with_name('road_first_walk.lua').read_text('utf8')
SNAP_HEIGHT = Path(__file__).with_name('road_snap_height.lua').read_text('utf8')
STRICT = "assert(not pd.errorState.critical,'Critical preview error');for _,k in ipairs({'messages','warnings','infos'})do assert(#pd.errorState[k]==0,'Preview rejected: '..k)end;assert(#collisions==0,'Collision blocks submission');"
COMMIT = GUARD[GUARD.index('local CT=api.type.ComponentType'):]


def stage_spec(base, stage, road_nodes=None, road_entities=None):
    roles={f['role']for f in base['facilities']}
    if roles not in ({'heliport','bus','truck','warehouse','road_depot'},
                     {'heliport','bus','truck','warehouse','road_depot','road_maintenance'},
                     {'heliport','truck','warehouse','road_maintenance'},
                     {'helipad','helipad2','truck','warehouse'}) or len(roles)!=len(base['facilities']):
        raise ValueError('Road-first requires a complete city or dual-pad production collection')
    if stage not in ('roads','facilities'):raise ValueError('Unknown phase')
    if any(r.get('buildPhase')not in ('frontage','entrance')for r in base['roads']):
        raise ValueError('Every internal road requires an explicit buildPhase')
    s = copy.deepcopy(base)
    # Explicit phase tags, never infer stage from road ordering or historical IDs.
    wanted = 'frontage' if stage == 'roads' else 'entrance'
    s['roads'] = [r for r in s['roads'] if r.get('buildPhase') == wanted]
    if not s['roads']: raise ValueError('Missing explicit road phase: '+wanted)
    used = {r[k] for r in s['roads'] for k in ('node0','node1')}
    s['nodes'] = [n for n in s['nodes'] if n['entity'] in used]
    if stage == 'roads':
        s.update(facilities=[], portBindings={}, bindGeneratedPorts=False)
    else:
        if not road_nodes or not road_entities: raise ValueError('Fresh road readback required')
        mapping = {n['entity']:road_nodes[str(n['name'])] for n in s['nodes'] if str(n['name']) in road_nodes}
        s['existingBaseNodes'] = [dict(entity=mapping[n['entity']],position=n['position']) for n in s['nodes'] if n['entity'] in mapping]
        for r in s['roads']:
            for k in ('node0','node1'): r[k] = mapping.get(r[k],r[k])
        s['nodes'] = [n for n in s['nodes'] if n['entity'] not in mapping]
        s['existingRoadEntities'] = list(road_entities)
    return s


def source(spec, origin, stage, build=False, diagnostic=False):
    code = probe(spec).replace('local isolatedTestConfirmed=false','local isolatedTestConfirmed=true')
    code = code.replace('local origin=nil -- {x=...,y=...,rotation=...}; choose empty land in the test save',
                        'local origin=B.json.decode('+quote(origin)+')')
    code = code.split('return B.json.encode({previewOnly=true')[0]
    if stage=='facilities' and any(f.get('roadSnap') for f in spec['facilities']):
        code=code.replace('for _,f in ipairs(spec.facilities)do',SNAP_HEIGHT+'\nfor _,f in ipairs(spec.facilities)do',1)
        code=code.replace('local p=point(f.localPosition,f.heightPolicy)',
                          'local p=roadsideHeight(f,point(f.localPosition,f.heightPolicy))',1)
    code = code.replace('for _,row in ipairs(spec.roads)do', '''for _,row in ipairs(spec.existingBaseNodes or{})do
 local n=assert(api.engine.getComponent(row.entity,api.type.ComponentType.BASE_NODE),'Existing node missing')
 local expected=point(row.position);local q=n.position
 assert(math.abs(q.x-expected.x)<.1 and math.abs(q.y-expected.y)<.1,'Existing road moved')
 positions[row.entity]={x=q.x,y=q.y,z=q.z}
end
for _,row in ipairs(spec.roads)do''')
    city = any(f['role']=='bus' for f in spec['facilities'])
    if stage == 'facilities':
        if city:code += WALK
        if diagnostic:
            return code+"return B.json.encode({walking="+('walkPreview' if city else 'nil')+",errorState={critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),warnings=B.toPlain(pd.errorState.warnings),infos=B.toPlain(pd.errorState.infos)},collisions=collisions})"
        if city:code += "assert(walkPreview.busNodes>0 and walkPreview.airportNodes>0 and walkPreview.outbound and walkPreview.inbound,'Walking preview failed; no facility submission');"
        code += GUARD.split('local CT=api.type.ComponentType')[0]
    else:
        code += STRICT+'local paths={};'
    if build:
        return code+COMMIT
    return code+"return B.json.encode({previewPassed=true,walking="+('walkPreview' if stage=='facilities' and city else 'nil')+",previewPaths=paths})"


def stage_key(b, owner, stage):
    # Historical single-collection ledgers remain readable; never share receipts
    # between owners in a full-map run.
    legacy='ROAD_FIRST_'+stage
    hubs=b.p.get('hubs',[])
    if legacy in b.ledger['items'] and len(hubs)==1 and hubs[0]['owner']==owner:
        return legacy
    if legacy in b.ledger['items'] and len(hubs)!=1:
        raise StopBatch('Ambiguous legacy road-first ledger; reconcile owner before continuing')
    return 'ROAD_FIRST_'+owner+'_'+stage


def evidence_dir(b, owner):
    return b.out/('road_first_'+owner)


async def road_readback(b, spec, origin, ids):
    points={str(n['name']):n['position'] for n in spec['nodes']}
    code='''local o=B.json.decode(ORIGIN);local wanted=B.json.decode(POINTS);local ids=B.json.decode(IDS)
local CT=api.type.ComponentType;local a=math.rad(o.rotation or 0);local c,s=math.cos(a),math.sin(a)
local out={nodes={},entities={}};local candidates={}
for _,id in ipairs(ids.edges)do assert(api.engine.entityExists(id),'Road disappeared');local e=assert(api.engine.getComponent(id,CT.BASE_EDGE),'Road missing');assert(api.engine.getComponent(id,CT.TRANSPORT_NETWORK),'Road network missing');out.entities[#out.entities+1]=id;candidates[e.node0]=true;candidates[e.node1]=true;out.entities[#out.entities+1]=e.node0;out.entities[#out.entities+1]=e.node1 end
for name,p in pairs(wanted)do local x,y=o.x+c*p.x-s*p.y,o.y+s*p.x+c*p.y
 for id in pairs(candidates)do local q=api.engine.getComponent(id,CT.BASE_NODE).position
  if math.abs(q.x-x)<.1 and math.abs(q.y-y)<.1 then assert(not out.nodes[name],'Ambiguous road node');out.nodes[name]=id end
 end;assert(out.nodes[name],'Road endpoint not found')
end;return B.json.encode(out)'''
    return await b.eval(code.replace('ORIGIN',quote(origin)).replace('POINTS',quote(points)).replace('IDS',quote(ids)))


async def facility_readback(b,hub,spec,commit,road_commit):
    if len(commit['added']['constructions'])!=len(spec['facilities']):raise StopBatch('Partial facilities')
    ids=copy.deepcopy(commit['added']);ids['edges']+=road_commit['added']['edges']
    by_id={f['id']:f for f in b.p['facilities']}
    expected={role:by_id[fid]['position']for role,fid in hub['facilities'].items()}
    expected=expected_roadside_offsets(expected,spec)
    tasks=[by_id[fid]for fid in hub['facilities'].values()]
    current=await b.read_facilities(tasks,'verify',with_session=True)
    if not all(r['result'].get('audit',{}).get('staticVerified')for r in current):raise StopBatch('Facility pose/resource readback failed')
    if {r['result']['audit']['entity']for r in current}!=set(ids['constructions']):raise StopBatch('Construction identities changed')
    # Native entrance edges may be regenerated without moving a facility. Resolve
    # planned public segments by geometry and native frozen edges from current components.
    # External access is built and audited by the following connection stage.
    roads=[r for r in b.p['roads']if r['id']in hub['roads'] and r.get('templateRoad')]
    code='''local roads=B.json.decode(ROADS);local cs=B.json.decode(CONSTRUCTIONS);local CT=api.type.ComponentType
local result,seen={},{};local function add(id)if not seen[id]then seen[id]=true;result[#result+1]=id end end
local function close(a,b)return math.abs(a.x-b.x)<.2 and math.abs(a.y-b.y)<.2 end
for _,r in ipairs(roads)do local a,z=r.path[1],r.path[2];local mx,my=(a.x+z.x)/2,(a.y+z.y)/2;local length=math.sqrt((a.x-z.x)^2+(a.y-z.y)^2);local found=nil
 for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(mx,my),length/2+2,CT.BASE_EDGE))do
  local e=api.engine.getComponent(id,CT.BASE_EDGE);local p=api.engine.getComponent(e.node0,CT.BASE_NODE).position;local q=api.engine.getComponent(e.node1,CT.BASE_NODE).position
  if(close(a,p)and close(z,q))or(close(a,q)and close(z,p))then assert(not found,'Ambiguous planned road');found=id end
 end;assert(found,'Planned road geometry changed');add(found)
end
for _,id in ipairs(cs)do for _,edge in ipairs(api.engine.getComponent(id,CT.CONSTRUCTION).frozenEdges)do add(edge)end end
return B.json.encode(result)'''
    ids['edges']=await b.eval(code.replace('ROADS',quote(roads)).replace('CONSTRUCTIONS',quote(ids['constructions'])))
    audit=await b.eval(AUDIT.replace('IDS',quote(ids)).replace('EXPECTED',quote(expected)))
    snaps={f['role']:f['roadSnap'] for f in spec['facilities'] if f.get('roadSnap')}
    if snaps:
        # Read geometry independently after submission. This is roadside alignment,
        # not a substitute for native links or shared inventory coverage.
        code='''local snaps=B.json.decode(SNAPS);local o=B.json.decode(ORIGIN);local fs=B.json.decode(FACILITIES);local edges=B.json.decode(EDGES)
local CT=api.type.ComponentType;local a=math.rad(o.rotation);local co,si=math.cos(a),math.sin(a);local out={}
for role,s in pairs(snaps)do
 local x,y=o.x+co*s.roadPoint.x-si*s.roadPoint.y,o.y+si*s.roadPoint.x+co*s.roadPoint.y
 local height=nil
 for _,id in ipairs(edges)do local e=api.engine.getComponent(id,CT.BASE_EDGE)
  local p=api.engine.getComponent(e.node0,CT.BASE_NODE).position;local q=api.engine.getComponent(e.node1,CT.BASE_NODE).position
  local dx,dy=q.x-p.x,q.y-p.y;local length=dx*dx+dy*dy
  if length>0 then local u=((x-p.x)*dx+(y-p.y)*dy)/length
   if u>=0 and u<=1 and (x-p.x-u*dx)^2+(y-p.y-u*dy)^2<.01 then height=p.z+u*(q.z-p.z)end
  end
 end
 out[role]={verified=height~=nil and math.abs(fs[role].z-height)<.1,roadHeight=height,facilityHeight=fs[role].z}
end;return B.json.encode(out)'''
        audit['roadsideAlignment']=await b.eval(code.replace('SNAPS',quote(snaps)).replace('ORIGIN',quote(dict(hub['position'],rotation=hub['rotation']))).replace('FACILITIES',quote(audit['facilities'])).replace('EDGES',quote(ids['edges'])))
    norm=lambda m:{str(k):(v['name'],v.get('variant',0))for k,v in (m or{}).items()}
    audit['modulesVerified']=all(norm(f['params'].get('modules'))==norm(audit['facilities'][f['role']]['params'].get('modules'))for f in spec['facilities'])
    audit['moduleDifferences']={}
    for f in spec['facilities']:
        planned=norm(f['params'].get('modules'));actual=norm(audit['facilities'][f['role']]['params'].get('modules'))
        if planned!=actual:audit['moduleDifferences'][f['role']]={
            'added':sorted(set(actual)-set(planned)), 'removed':sorted(set(planned)-set(actual)),
            'changed':sorted(k for k in set(actual)&set(planned)if actual[k]!=planned[k])}
    audit['staticAccepted']=acceptance(audit,False,spec);audit['operationalAccepted']=False
    if snaps and not all(r['verified'] for r in audit['roadsideAlignment'].values()):
        audit['staticAccepted']=False;audit['placementAccepted']=False
    write_json(evidence_dir(b,hub['owner'])/'verification.json',audit)
    return audit


async def run(a):
    b=Batch(a);hub,base,origin=prepare(b.p,a.owner,include_external=False)
    if a.stage not in ('roads','facilities'):raise ValueError('Unknown phase')
    if not a.current_map_test and not getattr(a,'isolated_test_save',False):raise StopBatch('Explicit current-map test or isolated test save authorization required')
    if a.action=='build' and not a.authorize_build:raise StopBatch('Build authorization required')
    with batch_lock(b.b.dir):
        try:
            state=await b.session()
            if state['speedup']!=0:raise StopBatch('Pause required')
            if a.action=='verify':
                item=b.ledger['items'].get(stage_key(b,a.owner,'facilities'),{})
                roads=b.ledger['items'].get(stage_key(b,a.owner,'roads'),{})
                if not item.get('commit')or not roads.get('commit'):raise StopBatch('Both submission receipts required')
                audit=await facility_readback(b,hub,base,item['commit'],roads['commit'])
                item['audit']=audit
                if not audit['staticAccepted']:raise StopBatch('Read-only acceptance still incomplete')
                item['status']='static_verified';item['reconciledBy']='Fresh native role-specific readback; no build replay';b.flush()
                await b.save('road_first_verified_complete')
                print(json.dumps({'verified':True,'walking':audit['paths'].get('walking'),'buildSubmissions':0}));return
            if unfinished(b.ledger):raise StopBatch('Unreconciled prior submission')
            key=stage_key(b,a.owner,a.stage);item=b.ledger['items'].get(key,{})
            if item.get('attempts'):raise StopBatch('Stage already attempted; no automatic replay')
            if a.stage=='roads':s=stage_spec(base,'roads')
            else:
                prior=b.ledger['items'].get(stage_key(b,a.owner,'roads'),{})
                if prior.get('status')!='static_verified':raise StopBatch('Road stage not verified')
                read=await road_readback(b,stage_spec(base,'roads'),origin,prior['commit']['added'])
                s=stage_spec(base,'facilities',read['nodes'],read['entities'])
                tasks=[t for t in b.tasks()if t['id']in hub['facilities'].values()]
                current=await b.read_facilities(tasks,'verify',with_session=True)
                if any(x['result'].get('existing')for x in current):raise StopBatch('Facilities already exist')
            await b.save('road_first_'+a.stage+'_preview_before')
            result=await b.eval(source(s,origin,a.stage,diagnostic=a.action=='diagnostic'))
            write_json(evidence_dir(b,a.owner)/(a.stage+'_'+a.action+'_preview.json'),result)
            if a.action!='build':print(json.dumps(result));return
            if result.get('previewPassed')is not True:raise StopBatch('Preview failed')
            await b.save('road_first_'+a.stage+'_before');await b.session()
            item=dict(attempts=1,status='commit_started',intentTime=time.time());b.ledger['items'][key]=item;b.flush()
            try:
                result=await b.eval(source(s,origin,a.stage,build=True));item['commit']=result;b.flush()
                write_json(evidence_dir(b,a.owner)/(a.stage+'_commit.json'),result)
                if result.get('callback',{}).get('success')is not True:raise StopBatch('Commit unknown/failed')
                if a.stage=='roads':
                    if result['added']['constructions'] or len(result['added']['edges'])!=len(s['roads']):raise StopBatch('Unexpected road-stage changes')
                    item['readback']=await road_readback(b,s,origin,result['added'])
                else:
                    audit=await facility_readback(b,hub,s,result,prior['commit']);item['audit']=audit
                    if not audit['staticAccepted']:raise StopBatch('Native post-build acceptance failed; no further construction')
                item['status']='static_verified';b.flush();await b.save('road_first_'+a.stage+'_complete')
                print(json.dumps({'stage':a.stage,'singleSubmission':True,'verified':True}))
            except BaseException:
                item['status']='needs_reconciliation';b.flush();raise
        finally:b.flush()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['preview','diagnostic','build','verify']);p.add_argument('--stage',choices=['roads','facilities'],required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--owner',required=True);p.add_argument('--current-map-test',action='store_true');p.add_argument('--isolated-test-save',action='store_true');p.add_argument('--authorize-build',action='store_true')
    a=p.parse_args();a.ids=None;a.limit=0;asyncio.run(run(a))


if __name__=='__main__':main()
