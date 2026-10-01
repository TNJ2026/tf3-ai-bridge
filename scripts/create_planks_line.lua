local CT=api.type.ComponentType
local name='牡丹江木板专线·锯木厂→工业区'
local selected={{76245,0,0},{62361,0,0},{79055,1,0}}
local before={}
for _,row in ipairs(B.commands.list_lines({}).lines) do
 before[row.id]=true;assert(row.name~=name,'line already exists')
 if #row.stops==3 then local groups={};for _,s in ipairs(row.stops) do groups[s.stationGroup]=true end;assert(not(groups[76245] and groups[62361] and groups[79055]),'equivalent line exists') end
end
local line=api.type.Line.new();line.customFilters=true;local stops={}
for i,row in ipairs(selected) do
 local s=api.type.Line.Stop.new();s.stationGroup=row[1];s.station=row[2];s.terminal=row[3];s.maxAdditionalWaitingTime=30
 local c=api.type.Line.StopConfig.new();local loads,max={},{}
 for id in pairs(api.res.cargoTypeRep.getAll(true)) do loads[id+1]=i==1 and id==13;max[id+1]=1 end
 c.load=loads;c.maxLoad=max;c.forceUnload=false;s.stopConfig=c;stops[#stops+1]=s
end
line.stops=stops;local ok=false
api.cmd.sendCommand(api.cmd.makeLineCreateCmd(name,api.type.Vec3f.new(.80,.56,.18),api.engine.util.getPlayer(),line),function(_,success)ok=success end)
local ids={};for _,id in ipairs(api.engine.system.lineSystem.getLines()) do if not before[id] then ids[#ids+1]=id end end
return B.json.encode({created=ok,newLines=ids,lines=B.commands.list_lines({})})
