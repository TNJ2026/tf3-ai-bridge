-- Native station-transfer reachability, distinct from node-only road pathfinding.
local function transfer(from,to)
 local evidence={};local complete=#from>0 and #to>0
 for _,source in ipairs(from)do local best=nil
  for _,target in ipairs(to)do local d=(reach[source]or{})[target]
   if source~=target and type(d)=='number'and d>=0 and d<math.huge and(not best or d<best.distanceM)then best={fromStation=source,toStation=target,distanceM=d}end
  end
  if best then evidence[#evidence+1]=best else complete=false end
 end
 return {verified=complete,stationPaths=evidence,basis='native getStation2stationsAndDistancesMap'}
end
