local CT=api.type.ComponentType;local line=api.engine.getComponent(90542,CT.LINE)
assert(#line.stops==3 and line.customFilters,'unexpected line configuration')
local expected={{76245,0,0},{62361,0,0},{79055,1,0}}
for i,s in ipairs(line.stops) do
 assert(s.stationGroup==expected[i][1] and s.station==expected[i][2] and s.terminal==expected[i][3],'unexpected stop')
 for id in pairs(api.res.cargoTypeRep.getAll(true)) do assert(s.stopConfig.load[id+1]==(i==1 and id==13),'unexpected cargo load filter');assert(s.stopConfig.maxLoad[id+1]==1,'unexpected maxLoad') end
end
local wanted={};local count,demand=0,0
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(868,-244),1800,CT.TOWN_BUILDING)) do
 local b=api.engine.getComponent(id,CT.TOWN_BUILDING)
 if b.town==48457 and b.stockList>=0 and api.engine.entityExists(b.stockList) then
 local n=api.engine.util.stock.getCargoMaxConsumptionPerYear(b.stockList,13);if n>0 then wanted[b.stockList]=n;count=count+1;demand=demand+n end end
end
local covered={};for _,id in ipairs({62142,61440}) do for _,e in ipairs(api.engine.system.catchmentAreaSystem.getStationCatchables(id,true)) do if wanted[e] then covered[e]=wanted[e] end end end
local cc,cd=0,0;for _,n in pairs(covered) do cc=cc+1;cd=cd+n end
local problems={};for _,p in ipairs(api.engine.system.lineSystem.getProblemLines(api.engine.util.getPlayer())) do if p[1]==90542 then problems[#problems+1]=B.toPlain(p[2]) end end
return B.json.encode({line=90542,loadingVerified=true,buildings=count,demand=demand,coveredBuildings=cc,coveredDemand=cd,problems=problems})
