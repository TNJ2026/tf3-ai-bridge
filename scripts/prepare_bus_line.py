import json
from pathlib import Path
p=json.loads(Path('bus_line_plan.json').read_text(encoding='utf-8'))
code='local plan=B.json.decode('+json.dumps(json.dumps(p))+');\n'+'''
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
'''
Path('scripts/bus_line_create.lua').write_text(code,encoding='utf-8')
