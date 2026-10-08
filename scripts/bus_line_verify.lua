local CT=api.type.ComponentType;local line=api.engine.getComponent(76282,CT.LINE);assert(#line.stops==6,'stop count changed');local out={line=76282,reachable=true,legs={},problems={}}
local function node(stop)local g=api.engine.getComponent(stop.stationGroup,CT.STATION_GROUP);local s=api.engine.getComponent(g.stations[stop.station+1],CT.STATION);return s.terminals[stop.terminal+1].vehicleNodeId end
for i,s in ipairs(line.stops) do local p=api.engine.util.pathfinding.findPathNodeToNode({node(s)},{node(line.stops[i%6+1])},{api.type.enum.TransportMode.BUS});out.legs[#out.legs+1]={from=i,to=i%6+1,reachable=#p>0};out.reachable=out.reachable and #p>0 end
for _,p in ipairs(api.engine.system.lineSystem.getProblemLines(api.engine.util.getPlayer())) do if p[1]==76282 then out.problems[#out.problems+1]=B.toPlain(p[2]) end end
return B.json.encode(out)
