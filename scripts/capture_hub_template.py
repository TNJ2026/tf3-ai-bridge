"""Read the camera and capture one current hub in a single engine snapshot. No mutations."""
import argparse,asyncio,json,math,sys
from pathlib import Path
from fullmap_batch import quote,ROOT
from batch_warehouses import Bridge,write_json

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--profile',choices=['city','production'],default='city');ap.add_argument('--include-depot',action='store_true');args=ap.parse_args();b=Bridge()
 if not b.heartbeat().get('connected'):raise RuntimeError('Game not connected')
 camera=await b.call('eval',{'code':'local p=api.gui.camera.getCenter();return {x=p.x,y=p.y,z=p.z}'},engine=False)
 if isinstance(camera,str):camera=json.loads(camera)
 source=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8')
 eq='========';assert ']'+eq+']'not in source
 pre='local env=setmetatable({},{__index=_G});local B=assert(load(['+eq+'['+source+']'+eq+'],"=hub_capture","t",env))()._internal;'
 code=r'''
local p=B.json.decode(CAMERA);local CT=api.type.ComponentType;local sc=api.engine.system.streetConnectorSystem
local targets={heliport='::/stations/air/heliport.con',truck='::/stations/street/modular_street_station/modular_terminal.con',bus='::/stations/street/modular_street_station/modular_terminal.con',warehouse='::/warehouses/warehouse.con'}
if PRODUCTION then targets.heliport=nil;targets.bus=nil;targets.helipad='::/stations/air/helipad.con'end
if INCLUDE_DEPOT then targets.road_depot='::/depots/road/road_depot/road_depot.con'end
local nearby={};for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(p.x,p.y),300,CT.CONSTRUCTION))do
 local c=api.engine.getComponent(id,CT.CONSTRUCTION);local q=c.transf:cols(3);local own=api.engine.getComponent(id,CT.PLAYER_OWNED)
 if own and own.player==api.engine.util.getPlayer()then
  local passenger=false;local cargo=false
  for _,m in pairs(c.params.modules or{})do passenger=passenger or string.find(m.name,'passenger',1,true)~=nil;cargo=cargo or string.find(m.name,'cargo',1,true)~=nil end
  nearby[#nearby+1]={id=id,resource=c.fileName,passenger=passenger,cargo=cargo,distance=(q.x-p.x)^2+(q.y-p.y)^2}
 end
end
local out={camera=p,state=B.commands.get_game_state({}),facilities={},edges={},stockLists={},catchment={},links={}}
local selected={};for role,resource in pairs(targets)do local best=nil
 for _,r in ipairs(nearby)do if r.resource==resource and(role~='bus'or r.passenger and not r.cargo)and(role~='truck'or r.cargo)and(not best or r.distance<best.distance)then best=r end end
 if role~='bus'then assert(best,'No nearby '..role)end
 if best then local config=B.commands.get_facility_config({entity=best.id});config.role=role;out.facilities[#out.facilities+1]=config;selected[best.id]=true end
end
if PRODUCTION then
 local pads={};for _,r in ipairs(nearby)do if r.resource=='::/stations/air/helipad.con'and not selected[r.id]then pads[#pads+1]=r end end
 table.sort(pads,function(a,b)return a.distance<b.distance end)
 assert(#pads>0,'Production template requires two observed helipads')
 local config=B.commands.get_facility_config({entity=pads[1].id});config.role='helipad2';out.facilities[#out.facilities+1]=config;selected[pads[1].id]=true
end
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(p.x,p.y),250,CT.BASE_EDGE))do
 local e=api.engine.getComponent(id,CT.BASE_EDGE)
 if e.roadType==api.type.enum.RoadType.STREET then local a=api.engine.getComponent(e.node0,CT.BASE_NODE).position;local b=api.engine.getComponent(e.node1,CT.BASE_NODE).position
 out.edges[#out.edges+1]={id=id,node0=e.node0,node1=e.node1,position0={x=a.x,y=a.y,z=a.z},position1={x=b.x,y=b.y,z=b.z},tangent0={x=e.tangent0.x,y=e.tangent0.y,z=e.tangent0.z},tangent1={x=e.tangent1.x,y=e.tangent1.y,z=e.tangent1.z},roadTemplate=e.roadTemplate,roadStyle=e.roadStyle,construction=sc.getConstructionEntityForEdge(id),node0Degree=#api.engine.system.streetSystem.getNodeSegments(e.node0),node1Degree=#api.engine.system.streetSystem.getNodeSegments(e.node1)}end
end
api.engine.forEachEntityWithComponent(function(id)local w=api.engine.getComponent(id,CT.WAREHOUSE);if selected[w.construction]then out.stockLists[#out.stockLists+1]={entity=id,stockList=w.stockList,construction=w.construction}end end,CT.WAREHOUSE)
for _,f in ipairs(out.facilities)do local c=api.engine.getComponent(f.entity,CT.CONSTRUCTION);for _,st in ipairs(c.stations)do out.catchment[#out.catchment+1]={construction=f.entity,station=st,catchables=B.toPlain(api.engine.system.catchmentAreaSystem.getStationCatchables(st,true))}end end
for _,f in ipairs(out.facilities)do
 local bv=api.engine.getComponent(f.entity,CT.BOUNDING_VOLUME)
 if bv then f.worldBounds={min=B.toPlain(bv.bbox.min),max=B.toPlain(bv.bbox.max)}end
end
local seen={};for _,ids in pairs(api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities())do for _,id in ipairs(ids)do if not seen[id]then seen[id]=true
 local l=api.engine.getComponent(id,CT.TP_NET_LINK);local a,b=l.from.edgeId.entity,l.to.edgeId.entity
 if selected[a]or selected[b]or selected[sc.getConstructionEntityForSubconstruction(a)]or selected[sc.getConstructionEntityForSubconstruction(b)]then out.links[#out.links+1]={from=a,to=b}end
end end end
return B.json.encode(out)
'''.replace('CAMERA',quote(camera)).replace('PRODUCTION','true'if args.profile=='production'else'false').replace('INCLUDE_DEPOT','true'if args.include_depot else'false')
 result=await b.call('eval',{'code':pre+code},engine=True,timeout=45)
 if isinstance(result,str):result=json.loads(result)
 write_json(args.output,result)
 print(json.dumps({'file':str(args.output),'facilities':[{k:f[k]for k in ['entity','role','position']}for f in result['facilities']],'edges':len(result['edges'])},ensure_ascii=True))
if __name__=='__main__':asyncio.run(main())
