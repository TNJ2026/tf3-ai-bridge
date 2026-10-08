"""Compile a harbor-centered set of required ship legs; optional read-only audit."""
import argparse,asyncio,json
from pathlib import Path
from fullmap_batch import Batch,quote,batch_lock,write_json

def select_port(plan,position,port_id=None):
    matches=[p['id']for p in plan.get('ports',[])if
             abs(p['position']['x']-position['x'])<.2 and abs(p['position']['y']-position['y'])<.2]
    if len(matches)!=1 or (port_id is not None and port_id!=matches[0]):
        raise ValueError('Built harbor does not match one designated plan port')
    return matches[0]

def compile_checks(plan,port_id=None):
    objects={f['id']:f for f in plan['facilities']+plan.get('ports',[])}
    ports={p['id']:p for p in plan.get('ports',[])if port_id is None or p['id']==port_id}
    if port_id is not None and not ports:raise ValueError('Unknown port')
    pairs={}
    def endpoint(value,terminal=None):
        f=objects[value]if isinstance(value,str)else value
        resource=f.get('resource')or ('::/stations/water/harbor_modular.con'if f.get('kind')=='harbor'else
            '::/depots/water/water_depot.con'if f.get('kind')=='water_depot'else None)
        if not resource:raise ValueError('Explicit ship endpoint resource required')
        if terminal is not None and (type(terminal)is not int or terminal<0):raise ValueError('Invalid terminal index')
        return dict(position=f['position'],resource=resource,terminal=terminal,
                    kind='depot'if f.get('kind')=='water_depot'else'station')
    def add(kind,port,a,b,line):
        # Model-specific by default. Sharing between models requires an explicit
        # equivalence profile whose restrictions are verified separately.
        profile=line.get('navigation_profile')or line.get('vehicle_model')
        if not isinstance(profile,str)or not profile:raise ValueError('Ship navigation profile or model required')
        row=dict(kind=kind,port=port,a=a,b=b,mode=line['mode'],profile=profile)
        k=json.dumps(row,sort_keys=True)
        if k not in pairs:pairs[k]=dict(row,lines=[])
        pairs[k]['lines'].append(line['id'])
    served={p:set()for p in ports}
    for line in plan.get('line_specs',[]):
        if line.get('mode')not in ('SHIP','SMALL_SHIP'):continue
        port=line['destination']
        if not isinstance(port,str)or port not in ports:continue
        src=line['source']
        source_identity=src if isinstance(src,str) else src.get('existing_industry') if isinstance(src,dict) else None
        # A sandbox-planned fishing facility has a logical facility ID until
        # construction. Resolve by position at readback, never fabricate a live ID.
        if isinstance(src,str):src=objects.get(src,{})
        if not isinstance(src,dict)or '/fishing_grounds/'not in src.get('resource','') or source_identity is None:
            raise ValueError('Harbor star audit only supports fishing routes')
        field=endpoint(src,line.get('source_terminal_index'))
        harbor=endpoint(port,line.get('destination_terminal_index'))
        depot=endpoint(line['purchase_base'])
        if depot['kind']!='depot':raise ValueError('Purchase endpoint must be a shipyard')
        add('depot_harbor',port,depot,harbor,line)
        add('harbor_field',port,harbor,field,line)
        served[port].add(source_identity)
    for pid,p in ports.items():
        expected=set(p.get('service_industries',[p['industry']]if 'industry'in p else []))
        if not served[pid]or expected!=served[pid]:raise ValueError('Missing/extra fishing route assignments: '+pid)
    return {'pairs':list(pairs.values()),'directionsBeforeNodeDedup':2*len(pairs),
            'cacheScope':'single engine evaluation','nativeVerified':False,'operationalAccepted':False}

def prelude():return Path(__file__).with_suffix('.lua').read_text('utf8')+'\n'

def audit_source(checks):
    return prelude()+'''local checks=B.json.decode(CHECKS);local CT=api.type.ComponentType
local cons={};api.engine.forEachEntityWithComponent(function(id)
 local c=api.engine.getComponent(id,CT.CONSTRUCTION);local p=c.transf:cols(3)
 cons[#cons+1]={id=id,c=c,x=p.x,y=p.y}
end,CT.CONSTRUCTION)
local function resolve(ep,mode)
 local found=nil
 for _,r in ipairs(cons)do if r.c.fileName==ep.resource and math.abs(r.x-ep.position.x)<.2 and math.abs(r.y-ep.position.y)<.2 then
  assert(not found,'Ambiguous ship endpoint');found=r
 end end
 assert(found,'Ship endpoint missing or moved')
 local choices={}
 if ep.kind=='depot'then
  for _,id in ipairs(found.c.depots)do local d=api.engine.getComponent(id,CT.VEHICLE_DEPOT)
   if d and d.transportModes[mode]then choices[#choices+1]={entity=id,inNodes=d.inNodes,outNodes=d.outNodes}end
  end
 else
  for _,id in ipairs(found.c.stations)do local st=assert(api.engine.getComponent(id,CT.STATION))
   for i,t in ipairs(st.terminals)do
    if (ep.terminal==nil or ep.terminal==i-1)and t.transportModes[mode]then
     choices[#choices+1]={entity=id,terminal=i-1,inNodes={t.vehicleNodeId},outNodes={t.vehicleNodeId}}
    end
   end
  end
 end
 assert(#choices==1,'Missing/ambiguous compatible ship terminal or depot')
 return choices[1]
end
local query,stats=newShipRouteChecker();local out={pairs={},verified=#checks.pairs>0,operationalAccepted=false}
for _,pair in ipairs(checks.pairs)do
 local mode=assert(api.type.enum.TransportMode[pair.mode],'Unknown mode')
 local a,b=resolve(pair.a,mode),resolve(pair.b,mode)
 local forward=query(a.outNodes,b.inNodes,mode,pair.profile)
 local back=query(b.outNodes,a.inNodes,mode,pair.profile)
 local ok=forward.reachable and back.reachable
 out.pairs[#out.pairs+1]={kind=pair.kind,port=pair.port,mode=pair.mode,profile=pair.profile,lines=pair.lines,
  fromEntity=a.entity,toEntity=b.entity,forward=forward,back=back,verified=ok}
 out.verified=out.verified and ok
end
out.cacheStats=stats;out.modelRestrictionsVerified=false
return B.json.encode(out)'''.replace('CHECKS',quote(checks))

async def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--port-id');ap.add_argument('--readback',action='store_true')
    a=ap.parse_args();p=json.loads(a.plan.read_text('utf8'));checks=compile_checks(p,a.port_id)
    if a.output.exists():raise ValueError('Output exists; preserve evidence')
    if not a.readback:write_json(a.output,checks);return
    b=Batch(argparse.Namespace(plan=a.plan,output=a.output.with_suffix('.audit'),action='verify',ids=None,limit=0))
    with batch_lock(b.b.dir):
        await b.session();r=await b.eval(audit_source(checks));write_json(a.output,r);b.flush()
        print(json.dumps({'verified':r['verified'],'cacheStats':r['cacheStats']}))

if __name__=='__main__':asyncio.run(main())
