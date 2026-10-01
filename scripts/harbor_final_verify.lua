local CT=api.type.ComponentType
local out={state=B.commands.get_game_state({}),lines={},problems=B.toPlain(api.engine.system.lineSystem.getProblemLines(api.engine.util.getPlayer())),transfer={},coverage={}}
for _,id in ipairs({110341,108945}) do
 local l=api.engine.getComponent(id,CT.LINE);local ss={}
 for _,s in ipairs(l.stops) do local loads,max={},{};for k,v in ipairs(s.stopConfig.load) do loads[#loads+1]=v end;for k,v in ipairs(s.stopConfig.maxLoad) do max[#max+1]=v end;ss[#ss+1]={group=s.stationGroup,station=s.station,terminal=s.terminal,loads=loads,maxLoad=max,forceUnload=s.stopConfig.forceUnload} end
 out.lines[#out.lines+1]={id=id,customFilters=l.customFilters,stops=ss}
end
local map=api.engine.system.catchmentAreaSystem.getStation2stationsAndDistancesMap()
out.transfer={fromHarbor=B.toPlain(map[106244]),fromTruck=B.toPlain(map[106358])}
local stocks={}
for _,id in ipairs({56180,62454}) do for _,s in ipairs(api.engine.system.catchmentAreaSystem.getStationCatchables(id,true)) do local d=api.engine.util.stock.getCargoMaxConsumptionPerYear(s,6);if d>0 then stocks[s]=d end end end
local count,total=0,0;for _,n in pairs(stocks) do count=count+1;total=total+n end;out.coverage={stocks=count,annualFishDemand=total}
return B.json.encode(out)
