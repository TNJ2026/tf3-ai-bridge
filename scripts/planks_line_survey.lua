local CT=api.type.ComponentType;local out={lines=B.commands.list_lines({}),stations={},demand={}};local wanted={}
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(868,-244),1800,CT.TOWN_BUILDING)) do local b=api.engine.getComponent(id,CT.TOWN_BUILDING);if b.town==48457 and b.stockList>=0 and api.engine.entityExists(b.stockList) then local amount=api.engine.util.stock.getCargoMaxConsumptionPerYear(b.stockList,13);if amount>0 then wanted[b.stockList]={building=id,demand=amount};out.demand[#out.demand+1]={building=id,stock=b.stockList,demand=amount} end end end
for _,g in ipairs(B.commands.list_stations({}).stationGroups) do local row={group=g.id,name=g.name,stations={}}
 for j,id in ipairs(g.stations) do local c=api.engine.getComponent(id,CT.STATION);local r={id=id,index=j-1,cargo=api.engine.util.station.isStationOfType(id,true),coverage={},coveredDemand=0,terminals={}}
 for _,e in ipairs(api.engine.system.catchmentAreaSystem.getStationCatchables(id,true)) do if wanted[e] then r.coverage[#r.coverage+1]=e;r.coveredDemand=r.coveredDemand+wanted[e].demand end end
 for k,t in ipairs(c.terminals) do r.terminals[#r.terminals+1]={index=k-1,load=t.cargoLoad,unload=t.cargoUnload,node={entity=t.vehicleNodeId.entity,index=t.vehicleNodeId.index}} end
 row.stations[#row.stations+1]=r end;out.stations[#out.stations+1]=row
end
return B.json.encode(out)
