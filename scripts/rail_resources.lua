local out={bridges=api.res.bridgeTypeRep.getAll(),tunnels=api.res.tunnelTypeRep.getAll(),track={}}
local t=api.res.streetTemplateRep.get(api.res.streetTemplateRep.find('::/infrastructure/track/simple/simple.street_template'));out.track.style=t.streetStyle;out.track.lanes=B.toPlain(t.laneConfigs)
return B.json.encode(out)
