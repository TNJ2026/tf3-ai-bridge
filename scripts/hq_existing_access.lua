-- Read-only. Resolve the current player's sole HQ, no proposal or construction.
local CT=api.type.ComponentType
local sc=api.engine.system.streetConnectorSystem
local hq=nil
api.engine.forEachEntityWithComponent(function(id)
 local c=api.engine.getComponent(id,CT.CONSTRUCTION)
 local owner=api.engine.getComponent(id,CT.PLAYER_OWNED)
 if c.fileName=='::/landmarks/hq/headquarter.con' and owner and owner.player==api.engine.util.getPlayer() then
  assert(not hq,'Multiple owned headquarters');hq=id
 end
end,CT.CONSTRUCTION)
assert(hq,'No existing owned headquarters')
local config=B.commands.get_facility_config({entity=hq})
local out={headquarters=hq,position=config.position,transform=config.transform,params=config.params,
 nativeProposalCalls=0,commitEnabled=false,check={clear=true},networks={},links={},hqEntities={},nativePaths={}}
local seen,entities,owned,roads={},{},{},{}
local function belongs(id)return id==hq or sc.getConstructionEntityForSubconstruction(id)==hq end
local function endpoint(p)
 assert(p and p.edgeId and type(p.param)=='number' and p.param>=0 and p.param<=1,'Unreadable link')
 return {entity=p.edgeId.entity,index=p.edgeId.index,param=p.param}
end
local scanned=0
for _,ids in pairs(api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities())do
 for _,id in ipairs(ids)do if not seen[id]then
  seen[id]=true;scanned=scanned+1;assert(scanned<=100000,'Link scan budget exceeded')
  local l=assert(api.engine.getComponent(id,CT.TP_NET_LINK),'Missing link')
  local a,b=l.from.edgeId.entity,l.to.edgeId.entity
  if belongs(a)or belongs(b)then
   assert(#out.links<64,'HQ link budget exceeded')
   out.links[#out.links+1]={entity=id,from=endpoint(l.from),to=endpoint(l.to)}
   for _,e in ipairs({a,b})do
    entities[e]=true
    if belongs(e)then owned[e]=true
    elseif api.engine.getComponent(e,CT.BASE_EDGE)then roads[e]=true end
   end
  end
 end end
end
-- No observed links is unknown without a full subconstruction inventory.
assert(next(owned) and next(roads),'No HQ-to-road links; requires resurvey, not a positive audit')
local roadList={};for id in pairs(roads)do roadList[#roadList+1]=id end;table.sort(roadList)
assert(#roadList==1,'Multiple frontage roads require explicit target selection');out.road=roadList[1]
local starts,goals={},{}
for id in pairs(entities)do
 local net=assert(api.engine.getComponent(id,CT.TRANSPORT_NETWORK),'Missing network')
 local row={entity=id,edges={}}
 if owned[id]then out.hqEntities[#out.hqEntities+1]=id end
 for i,e in ipairs(net.edges)do
  assert(i<=4096,'Network budget exceeded')
  if e.transportModes[0]then
   assert(type(e.forwardOnly)=='boolean','Missing direction')
   local a,b=e.conns[1],e.conns[2]
   row.edges[#row.edges+1]={index=i-1,from={entity=a.entity,index=a.index},to={entity=b.entity,index=b.index},forwardOnly=e.forwardOnly}
   for _,n in ipairs({a,b})do
    if owned[id]then starts[tostring(n.entity)..':'..n.index]=n
    elseif id==out.road then goals[#goals+1]=n end
   end
  end
 end
 out.networks[#out.networks+1]=row
end
assert(#goals>0,'No road PERSON nodes')
for _,n in pairs(starts)do
 assert(#out.nativePaths<128,'Path query budget exceeded')
 local a=api.engine.util.pathfinding.findPathNodeToNode({n},goals,{api.type.enum.TransportMode.PERSON})
 local b=api.engine.util.pathfinding.findPathNodeToNode(goals,{n},{api.type.enum.TransportMode.PERSON})
 out.nativePaths[#out.nativePaths+1]={entity=n.entity,index=n.index,outbound=#a>0,inbound=#b>0}
end
return B.json.encode(out)
