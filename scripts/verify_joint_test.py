"""Independent readback and native checkpoint for one joint construction test."""
import argparse,asyncio,json,time
from pathlib import Path
from batch_warehouses import Bridge,ROOT,batch_lock,write_json,StopBatch
from fullmap_batch import quote,save_signature
from fullmap_workflow import atomic_write

AUDIT='''
local ids=B.json.decode(IDS);local expected=B.json.decode(EXPECTED);local CT=api.type.ComponentType
local out={facilities={},roads={},coverage={},paths={},links={}};local f={}
for _,id in ipairs(ids.constructions)do
 local c=assert(api.engine.getComponent(id,CT.CONSTRUCTION),'Construction missing')
 local role=c.fileName:find('warehouse')and'warehouse'or c.fileName:find('road_maint_station.con',1,true)and'road_maintenance'or c.fileName:find('road_depot.con',1,true)and'road_depot'or c.fileName:find('helipad')and'helipad'or c.fileName:find('heliport')and'heliport'or'truck'
 if role=='helipad'then local p=c.transf:cols(3);local match=nil
  for k,v in pairs(expected)do if k=='helipad'or k=='helipad2'then if math.abs(p.x-v.x)<.2 and math.abs(p.y-v.y)<.2 then assert(not match,'Ambiguous pad position');match=k end end end
  role=assert(match,'Unexpected helipad position')
 end
 for _,m in pairs(c.params.modules or{})do if m.name:find('passenger_platform')then role='bus'end end
 assert(not f[role],'Duplicate role');f[role]=id
 local p=c.transf:cols(3);out.facilities[role]={entity=id,resource=c.fileName,x=p.x,y=p.y,z=p.z,params=B.toPlain(c.params)}
end
for _,id in ipairs(ids.edges)do
 local e=api.engine.getComponent(id,CT.BASE_EDGE);local r={entity=id,baseEdge=e~=nil,network=api.engine.getComponent(id,CT.TRANSPORT_NETWORK)~=nil}
 if e then r.node0=e.node0;r.node1=e.node1;r.node0Network=api.engine.getComponent(e.node0,CT.TRANSPORT_NETWORK)~=nil;r.node1Network=api.engine.getComponent(e.node1,CT.TRANSPORT_NETWORK)~=nil end
 out.roads[#out.roads+1]=r
end
local function nodes(entities,mode)
 local result={};for _,id in ipairs(entities)do local net=api.engine.getComponent(id,CT.TRANSPORT_NETWORK)
 if net then for _,e in ipairs(net.edges)do if e.transportModes[mode]then result[#result+1]=e.conns[1];result[#result+1]=e.conns[2]end end end end;return result
end
local function stations(role)local ids={};for _,id in ipairs(api.engine.getComponent(f[role],CT.CONSTRUCTION).stations)do ids[#ids+1]=id end;return ids end
local internal={};for _,role in ipairs({'bus','truck','road_depot'})do if f[role]then for _,id in ipairs(api.engine.getComponent(f[role],CT.CONSTRUCTION).frozenEdges)do internal[id]=true end end end
local roads={};for _,id in ipairs(ids.edges)do if not internal[id]then roads[#roads+1]=id end end
local function path(a,b,mode)
 if #a==0 or #b==0 then return {verified=false,startNodes=#a,endNodes=#b}end
 local p=api.engine.util.pathfinding.findPathNodeToNode(a,b,{mode});return {verified=#p>0,steps=#p,startNodes=#a,endNodes=#b}
end
for _,role in ipairs({'bus','truck'})do if f[role]then local mode=role=='bus'and 3 or 4;local a,b=nodes(stations(role),mode),nodes(roads,mode)
 out.paths[role]={outbound=path(a,b,mode),inbound=path(b,a,mode)}
end end
if f.road_depot then
 out.paths.road_depot={};local c=api.engine.getComponent(f.road_depot,CT.CONSTRUCTION)
 -- Road depots purchase BUS/TRUCK, not private CAR; CAR lanes remain checked in preview.
 for _,mode in ipairs({3,4})do
  local a,z={},{};for _,id in ipairs(c.depots)do local d=api.engine.getComponent(id,CT.VEHICLE_DEPOT)
   if d and d.transportModes[mode]then for _,n in ipairs(d.outNodes)do a[#a+1]=n end;for _,n in ipairs(d.inNodes)do z[#z+1]=n end end
  end
  local r=nodes(roads,mode);out.paths.road_depot['out_'..mode]=path(a,r,mode);out.paths.road_depot['in_'..mode]=path(r,z,mode)
 end
end
if f.road_maintenance then
 local c=api.engine.getComponent(f.road_maintenance,CT.CONSTRUCTION);local p=c.transf:cols(3);local y=c.transf:cols(1)
 local snap={x=p.x-16*y.x,y=p.y-16*y.y};local nearest=math.huge;local service=false
 for _,id in ipairs(c.depots)do local d=api.engine.getComponent(id,CT.VEHICLE_DEPOT)
  if d and d.maintenancePool==16 and d.catchmentArea and d.catchmentArea.radius==600 and d.transportModes[3]and d.transportModes[4]then service=true end
 end
 for _,id in ipairs(roads)do local e=api.engine.getComponent(id,CT.BASE_EDGE)
  if e then local a=api.engine.getComponent(e.node0,CT.BASE_NODE).position;local b=api.engine.getComponent(e.node1,CT.BASE_NODE).position
   local dx,dy=b.x-a.x,b.y-a.y;local l=dx*dx+dy*dy
   if l>0 then local u=((snap.x-a.x)*dx+(snap.y-a.y)*dy)/l;if u>=0 and u<=1 then nearest=math.min(nearest,math.sqrt((snap.x-a.x-u*dx)^2+(snap.y-a.y-u*dy)^2))end end
  end
 end
 local expectedOffset=(expected.road_maintenance or{}).roadsideOffsetM or 7
 out.maintenance={serviceVerified=service,roadsideDistance=nearest<math.huge and nearest or nil,expectedRoadsideOffset=expectedOffset,roadsideVerified=math.abs(nearest-expectedOffset)<.5}
end
if f.bus then local a,b=nodes(stations('bus'),0),nodes(stations('heliport'),0)
-- Node-only pathfinding does not establish transfer reachability across automatic TP links.
-- Preserve its diagnostic, but use the engine's station transfer graph for acceptance.
out.walkingNodePathDiagnostic={outbound=path(a,b,0),inbound=path(b,a,0)}
local reach=api.engine.system.catchmentAreaSystem.getStation2stationsAndDistancesMap()
TRANSFER_HELPER
out.paths.walking={outbound=transfer(stations('bus'),stations('heliport')),inbound=transfer(stations('heliport'),stations('bus'))}
end
local stocks={};out.capacity=0
api.engine.forEachEntityWithComponent(function(id)local w=api.engine.getComponent(id,CT.WAREHOUSE);if w.construction==f.warehouse then
 stocks[w.stockList]=true;stocks[id]=true
 for _,s in ipairs(api.engine.getComponent(w.stockList,CT.STOCK_LIST).stocks)do out.capacity=out.capacity+s.capacity end
end end,CT.WAREHOUSE)
local coverageRoles={f.helipad and'helipad'or'heliport','truck'};if f.helipad2 then coverageRoles[#coverageRoles+1]='helipad2'end
for _,role in ipairs(coverageRoles)do local covered=false
 for _,st in ipairs(stations(role))do for _,id in ipairs(api.engine.system.catchmentAreaSystem.getStationCatchables(st,true))do covered=covered or stocks[id]==true end end
 out.coverage[role]=covered
end
local sc=api.engine.system.streetConnectorSystem;local seen={};local roadIds={};for _,id in ipairs(roads)do roadIds[id]=true end
out.airportRoadLinkVerified=false
if f.heliport then
for _,list in pairs(api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities())do for _,id in ipairs(list)do if not seen[id]then
 seen[id]=true;local l=api.engine.getComponent(id,CT.TP_NET_LINK);local a,b=l.from.edgeId.entity,l.to.edgeId.entity
 if a==f.heliport or b==f.heliport or sc.getConstructionEntityForSubconstruction(a)==f.heliport or sc.getConstructionEntityForSubconstruction(b)==f.heliport then
 out.links[#out.links+1]={from=a,to=b};out.airportRoadLinkVerified=out.airportRoadLinkVerified or roadIds[a]==true or roadIds[b]==true
 end
end end end
end
out.airportRoadLinkRequired=f.heliport~=nil
return B.json.encode(out)
'''

AUDIT = AUDIT.replace('TRANSFER_HELPER', Path(__file__).with_name('station_walk_transfer.lua').read_text('utf8'))

def expected_roadside_offsets(expected, spec):
    """Carry template geometry into readback without mutating plan positions."""
    result={role:dict(position) for role,position in expected.items()}
    for f in spec['facilities']:
        if f['role']=='road_maintenance' and f['role'] in result:
            result[f['role']]['roadsideOffsetM']=f.get('roadSnap',{}).get('roadsideOffsetM',7)
    return result

async def main():
 p=argparse.ArgumentParser();p.add_argument('--preview',required=True,type=Path);p.add_argument('--defer-walking',action='store_true');a=p.parse_args();out=a.preview
 commit=json.loads((out/'commit_result.json').read_text('utf8'));spec=json.loads((out/'joint_spec.json').read_text('utf8'))
 b=Bridge();assert b.heartbeat().get('connected')
 source=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8')
 pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+source+']========],"=joint_verify","t",env))()._internal;'
 async def call(code,engine=True):
  r=await b.call('eval',{'code':code},engine=engine,timeout=45);return json.loads(r)if isinstance(r,str)else r
 with batch_lock(b.dir):
  import math
  origin=json.loads((out/'receipt.json').read_text('utf8'))['origin'];angle=math.radians(origin['rotation']);cs,sn=math.cos(angle),math.sin(angle)
  expected={f['role']:{'x':origin['x']+cs*f['localPosition']['x']-sn*f['localPosition']['y'],'y':origin['y']+sn*f['localPosition']['x']+cs*f['localPosition']['y']}for f in spec['facilities']}
  expected=expected_roadside_offsets(expected,spec)
  code=AUDIT.replace('IDS',quote(commit['added'])).replace('EXPECTED',quote(expected));atomic_write(out/'verify.lua',code)
  r=await call(pre+code)
  norm=lambda d:{str(k):(v['name'],v.get('variant',0))for k,v in (d or {}).items()}
  r['modulesVerified']=all(norm(f['params'].get('modules'))==norm(r['facilities'][f['role']]['params'].get('modules'))for f in spec['facilities'])
  r['staticAccepted']=acceptance(r,a.defer_walking,spec)
  r['operationalAccepted']=False;r['externalPublicConnectionVerified']=False
  write_json(out/'verification.json',r)
  import hashlib
  name='tf3_joint_auto_'+hashlib.sha256(str(out.resolve()).encode()).hexdigest()[:10];path=b.dir.parent/'save'/(name+'.sav');before=save_signature(path)
  await call('app.saveGame("'+name+'",function()end,false,true);return {requested=true}',False)
  prev=None
  for _ in range(60):
   sig=save_signature(path)
   if sig and sig!=before and sig==prev and sig[0]>0:break
   prev=sig;await asyncio.sleep(.5)
  else:raise StopBatch('Checkpoint not confirmed')
  r['save']={'path':str(path),'signature':sig};write_json(out/'verification.json',r);print(json.dumps(r,ensure_ascii=False))
def acceptance(result,defer_walking=False,spec=None):
 # Missing evidence is a failure, never an empty all() success.
 errors=[]
 def require(ok,label):
  if not ok:errors.append(label)
  return bool(ok)
 facilities=result.get('facilities',{})
 roles={f['role'] for f in spec['facilities']} if spec else set(facilities)
 require(bool(roles) and set(facilities)==roles,'facility_roles')
 require({'warehouse','truck'}<=roles and bool(roles & {'heliport','helipad'}),'required_roles')
 roads=result.get('roads',[])
 require(isinstance(roads,list) and bool(roads),'roads_missing')
 if spec:require(len(roads)>=len(spec['roads']),'roads_incomplete')
 for row in roads:
  require(all(row.get(k) is True for k in ('baseEdge','network','node0Network','node1Network')),'road_network')
 require(result.get('modulesVerified') is True,'modules')
 coverage=result.get('coverage',{})
 for role in roles & {'heliport','helipad','helipad2','truck'}:
  require(coverage.get(role) is True,'coverage:'+role)
 paths=result.get('paths',{})
 def pair_ok(role,keys):
  pair=paths.get(role,{})
  return all(isinstance(pair.get(k),dict) and pair[k].get('verified') is True for k in keys)
 for role in roles & {'truck','bus','road_depot'}:
  keys=('out_3','in_3','out_4','in_4') if role=='road_depot' else ('inbound','outbound')
  require(pair_ok(role,keys),'path:'+role)
 if 'road_maintenance' in roles:
  require(all(result.get('maintenance',{}).get(k) is True for k in ('serviceVerified','roadsideVerified')),'maintenance')
 linked='heliport' not in roles or result.get('airportRoadLinkVerified') is True
 require(linked,'airport_road_link')
 core=not errors
 walking='bus' not in roles or pair_ok('walking',('inbound','outbound'))
 if not walking:errors.append('walking')
 result['acceptanceFailures']=errors
 result['placementAccepted']=core and (defer_walking or walking)
 result['walkingDeferred']=defer_walking
 return core and walking

if __name__=='__main__':asyncio.run(main())
