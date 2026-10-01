local CT=api.type.ComponentType
local out={terrain=B.commands.get_terrain_grid({x=1500,y=-2900,spacing=25,columns=25,rows=33,limit=1024}),demand={},coverage={},stations={}}
local wanted={}
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(868,-244),2500,CT.TOWN_BUILDING)) do
 local b=api.engine.getComponent(id,CT.TOWN_BUILDING)
 if b.town==48457 and b.stockList>=0 then local d=api.engine.util.stock.getCargoMaxConsumptionPerYear(b.stockList,6);if d>0 then wanted[b.stockList]=d;out.demand[#out.demand+1]={id=id,stock=b.stockList,amount=d} end end
end
for _,g in ipairs(B.commands.list_stations({}).stationGroups) do
 local covered={};local sum=0
 for _,s in ipairs(g.stations) do
  for _,e in ipairs(api.engine.system.catchmentAreaSystem.getStationCatchables(s,true)) do if wanted[e] and not covered[e] then covered[e]=true;sum=sum+wanted[e] end end
 end
 out.coverage[#out.coverage+1]={group=g.id,name=g.name,demand=sum,stocks=covered}
end
for _,id in ipairs({79847,48513}) do out.stations[#out.stations+1]=B.commands.get_entity({id=id}) end
return B.json.encode(out)
