local CT=api.type.ComponentType;local groups={76242,76245};local stations={26829,76244};local comps={api.engine.getComponent(stations[1],CT.STATION),api.engine.getComponent(stations[2],CT.STATION)}
local best,choice=math.huge,nil
local function length(a,b)
 local path=api.engine.util.pathfinding.findPathNodeToNode({a},{b},{api.type.enum.TransportMode.TRUCK});if #path==0 then return math.huge end
 local l=0;for _,p in ipairs(path) do local tn=api.engine.getComponent(p[1].entity,CT.TRANSPORT_NETWORK);l=l+tn.edges[p[1].index+1].geometry.length end;return l
end
for i,a in ipairs(comps[1].terminals) do for j,b in ipairs(comps[2].terminals) do local ab=length(a.vehicleNodeId,b.vehicleNodeId);local ba=length(b.vehicleNodeId,a.vehicleNodeId);if ab+ba<best then best=ab+ba;choice={i-1,j-1,ab,ba} end end end
assert(choice,'no connected truck route')
local before={};for _,id in ipairs(api.engine.system.lineSystem.getLines()) do before[id]=true;local l=api.engine.getComponent(id,CT.LINE);if #l.stops==2 then assert(not(l.stops[1].stationGroup==groups[1] and l.stops[2].stationGroup==groups[2]),'route already exists') end end
local line=api.type.Line.new();line.customFilters=true;local stops={}
for i,g in ipairs(groups) do
 local s=api.type.Line.Stop.new();s.stationGroup=g;s.station=0;s.terminal=choice[i];s.maxAdditionalWaitingTime=30
 local c=api.type.Line.StopConfig.new();local loads,max={},{};for k in pairs(api.res.cargoTypeRep.getAll(true)) do loads[k+1]=i==1 and k==12;max[k+1]=1 end
 c.load=loads;c.maxLoad=max;c.forceUnload=false;s.stopConfig=c;stops[#stops+1]=s
end
line.stops=stops;local ok=false
api.cmd.sendCommand(api.cmd.makeLineCreateCmd('牡丹江原木专线·伐木场→锯木厂',api.type.Vec3f.new(.55,.32,.12),api.engine.util.getPlayer(),line),function(_,success)ok=success end)
local ids={};for _,id in ipairs(api.engine.system.lineSystem.getLines()) do if not before[id] then ids[#ids+1]=id end end
return B.json.encode({created=ok,newLines=ids,terminals={choice[1],choice[2]},outbound=choice[3],returnDistance=choice[4],lines=B.commands.list_lines({})})
