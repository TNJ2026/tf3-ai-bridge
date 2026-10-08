local c=api.engine.getComponent(36847,api.type.ComponentType.LINE);local o={customFilters=c.customFilters,stops={}}
for _,s in ipairs(c.stops) do o.stops[#o.stops+1]={load=B.toPlain(s.stopConfig.load),maxLoad=B.toPlain(s.stopConfig.maxLoad),forceUnload=s.stopConfig.forceUnload} end
return B.json.encode(o)
