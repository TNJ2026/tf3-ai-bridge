-- Read-only, fresh town/road/building and passenger facility inventory.
local CT=api.type.ComponentType
local out={map=B.commands.get_map_info({}),state=B.commands.get_game_state({}),towns={},buildings={},roads={},stations={},depots={},lines=B.commands.list_lines({limit=1000})}
local eligible={}
for _,t in ipairs(out.map.towns)do
 local u=api.engine.util.town.getTownCapacityUsage(t.id)
 local r=u[api.type.enum.LandUseType.RESIDENTIAL+1]
 local row={id=t.id,name=t.name,position=t.position,population=r.used,residentialCapacity=r.capacity}
 out.towns[#out.towns+1]=row;if r.used>=150 then eligible[t.id]=true end
end
api.engine.forEachEntityWithComponent(function(id)
 local b=api.engine.getComponent(id,CT.TOWN_BUILDING)
 if eligible[b.town]then
  local c=api.engine.getComponent(b.construction,CT.CONSTRUCTION)
  local cap=api.engine.entityExists(b.personCapacity)and api.engine.getComponent(b.personCapacity,CT.PERSON_CAPACITY)
  if c and cap then local p=c.transf:cols(3);out.buildings[#out.buildings+1]={id=id,town=b.town,x=p.x,y=p.y,landUse=cap.type,capacity=cap.capacity}end
 end
end,CT.TOWN_BUILDING)
local seen={}
for _,t in ipairs(out.towns)do if eligible[t.id]then
 for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(t.position.x,t.position.y),1500,CT.BASE_EDGE))do
  if not seen[id]then seen[id]=true;local e=api.engine.getComponent(id,CT.BASE_EDGE)
   if e.roadType==api.type.enum.RoadType.STREET then
    local passengerStops=0;local catchables={};local covered={}
    for _,ref in ipairs(e.objects)do local st=api.engine.getComponent(ref[1],CT.STATION)
     if st then local valid=false;for _,term in ipairs(st.terminals)do valid=valid or(term.passengersLoad and term.passengersUnload)end
      if valid then passengerStops=passengerStops+1;for _,v in pairs(api.engine.system.catchmentAreaSystem.getStationCatchables(ref[1],false))do if not covered[v]then covered[v]=true;catchables[#catchables+1]=v end end end
     end
    end
    out.roads[#out.roads+1]={id=id,node0=e.node0,node1=e.node1,p0=B.toPlain(e.position0),p1=B.toPlain(e.position1),objects=B.toPlain(e.objects),passengerStops=passengerStops,catchables=catchables,construction=api.engine.system.streetConnectorSystem.getConstructionEntityForEdge(id)}
   end
  end
 end
end end
api.engine.forEachEntityWithComponent(function(id)
 local c=api.engine.getComponent(id,CT.CONSTRUCTION);local own=api.engine.getComponent(id,CT.PLAYER_OWNED)
 if own and own.player==api.engine.util.getPlayer()then local p=c.transf:cols(3)
  if #c.depots>0 then out.depots[#out.depots+1]={id=id,position={x=p.x,y=p.y},resource=c.fileName,depots=B.toPlain(c.depots)}end
  for _,sid in ipairs(c.stations)do local s=api.engine.getComponent(sid,CT.STATION)
   for _,term in ipairs(s.terminals)do if term.passengersLoad and term.passengersUnload and term.transportModes[api.type.enum.TransportMode.BUS]then out.stations[#out.stations+1]={construction=id,station=sid,position={x=p.x,y=p.y},resource=c.fileName};break end end
  end
 end
end,CT.CONSTRUCTION)
return B.json.encode(out)
