local plan=B.json.decode("{\"length\": 1220.4116001129, \"stops\": [{\"group\": 76399, \"station\": 1, \"stationEntity\": 62237, \"nextLeg\": 175.99641799927, \"terminal\": 0}, {\"group\": 76345, \"station\": 1, \"stationEntity\": 75139, \"nextLeg\": 174.79393386841, \"terminal\": 0}, {\"group\": 76357, \"station\": 1, \"stationEntity\": 62322, \"nextLeg\": 175.99948883057, \"terminal\": 0}, {\"group\": 76364, \"station\": 0, \"stationEntity\": 62396, \"nextLeg\": 175.26106643677, \"terminal\": 0}, {\"group\": 62134, \"station\": 1, \"stationEntity\": 62141, \"nextLeg\": 255.78817558289, \"terminal\": 0}, {\"group\": 76383, \"station\": 0, \"stationEntity\": 62361, \"nextLeg\": 262.57251739502, \"terminal\": 0}]}");

local CT=api.type.ComponentType;local before={};for _,id in ipairs(api.engine.system.lineSystem.getLines()) do before[id]=true end
local line=api.type.Line.new();local stops={}
for _,s in ipairs(plan.stops) do
 local g=api.engine.getComponent(s.group,CT.STATION_GROUP);assert(g.stations[s.station+1]==s.stationEntity,'station changed')
 local stop=api.type.Line.Stop.new();stop.stationGroup=s.group;stop.station=s.station;stop.terminal=s.terminal;stops[#stops+1]=stop
end
line.stops=stops
local accepted=false
api.cmd.sendCommand(api.cmd.makeLineCreateCmd('牡丹江1路·三区环线',api.type.Vec3f.new(.12,.55,.88),api.engine.util.getPlayer(),line),function(_,ok)accepted=ok end)
local out={accepted=accepted,lines=B.commands.list_lines({}),newLines={}}
for _,id in ipairs(api.engine.system.lineSystem.getLines()) do if not before[id] then out.newLines[#out.newLines+1]=id end end
return B.json.encode(out)
