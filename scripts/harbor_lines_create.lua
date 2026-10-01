local CT=api.type.ComponentType
local specs={
 {name='牡丹江鲜鱼水运·武汉渔场→南岸码头',stops={{79387,0,0},{106264,0,0}}},
 {name='牡丹江鲜鱼配送·南岸码头→商业中心→西北住宅',stops={{99132,0,0},{79044,0,0},{79032,0,0}}}
}
local existing=B.commands.list_lines({}).lines;local before={}
for _,r in ipairs(existing) do before[r.id]=true;for _,s in ipairs(specs) do assert(r.name~=s.name,'line already exists');if #r.stops==#s.stops then local same=true;for i,t in ipairs(r.stops) do same=same and t.stationGroup==s.stops[i][1] end;assert(not same,'equivalent line exists') end end end
local out={created={}}
for _,spec in ipairs(specs) do
 local line=api.type.Line.new();line.customFilters=true;local stops={}
 for i,row in ipairs(spec.stops) do
  local group=api.engine.getComponent(row[1],CT.STATION_GROUP);local id=group.stations[row[2]+1];local terminal=api.engine.getComponent(id,CT.STATION).terminals[row[3]+1]
  assert(i==1 and terminal.cargoLoad or i~=1 and terminal.cargoUnload,'cargo capability changed')
  local s=api.type.Line.Stop.new();s.stationGroup=row[1];s.station=row[2];s.terminal=row[3];s.maxAdditionalWaitingTime=30
  local c=api.type.Line.StopConfig.new();local loads,max={},{}
  for cargo in pairs(api.res.cargoTypeRep.getAll(true)) do loads[cargo+1]=i==1 and cargo==6;max[cargo+1]=1 end
  c.load=loads;c.maxLoad=max;c.forceUnload=false;s.stopConfig=c;stops[#stops+1]=s
 end
 line.stops=stops;local ok=false
 api.cmd.sendCommand(api.cmd.makeLineCreateCmd(spec.name,api.type.Vec3f.new(.1,.55,.8),api.engine.util.getPlayer(),line),function(_,success)ok=success end)
 out.created[#out.created+1]={name=spec.name,success=ok};if not ok then break end
end
out.lines={};for _,r in ipairs(B.commands.list_lines({}).lines) do if not before[r.id] then out.lines[#out.lines+1]=r end end
return B.json.encode(out)
