local c=api.engine.getComponent(81411,api.type.ComponentType.LINE);local out={line=81411,stops=#c.stops,loadLogs=c.stops[1].stopConfig.load[13],loadAtMill=c.stops[2].stopConfig.load[13],problems={}}
assert(out.stops==2 and out.loadLogs==true and out.loadAtMill==false,'unexpected loading configuration')
for _,p in ipairs(api.engine.system.lineSystem.getProblemLines(api.engine.util.getPlayer())) do if p[1]==81411 then out.problems[#out.problems+1]=B.toPlain(p[2]) end end
return B.json.encode(out)
