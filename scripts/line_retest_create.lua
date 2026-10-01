local plan=B.json.decode("{\"length\": 1220.4115467072, \"stops\": [{\"terminal\": 0, \"station\": 1, \"stationEntity\": 78956, \"nextLeg\": 175.99641799927, \"group\": 79023}, {\"terminal\": 0, \"station\": 1, \"stationEntity\": 62443, \"nextLeg\": 174.79393386841, \"group\": 79032}, {\"terminal\": 0, \"station\": 1, \"stationEntity\": 56174, \"nextLeg\": 175.99948883057, \"group\": 79044}, {\"terminal\": 0, \"station\": 0, \"stationEntity\": 62396, \"nextLeg\": 175.26113128662, \"group\": 79055}, {\"terminal\": 0, \"station\": 1, \"stationEntity\": 62141, \"nextLeg\": 255.78805732727, \"group\": 62361}, {\"terminal\": 0, \"station\": 0, \"stationEntity\": 75984, \"nextLeg\": 262.57251739502, \"group\": 79072}]}");
assert(#api.engine.system.lineSystem.getLines()==0,"line already exists; do not duplicate");

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
