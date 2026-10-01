local CT=api.type.ComponentType;local old=api.engine.getComponent(36847,CT.LINE);assert(old and #old.stops==6,'line changed')
local c=api.type.Line.new();c.customFilters=true;c.reservationPriority=old.reservationPriority;local stops={}
for _,s in ipairs(old.stops) do
 local config=api.type.Line.StopConfig.new(s.stopConfig);local load,max={},{}
 for k in pairs(api.res.cargoTypeRep.getAll(true)) do load[k+1]=k==0;max[k+1]=1 end
 config.load=load;config.maxLoad=max;config.forceUnload=false;s.stopConfig=config;stops[#stops+1]=s
end
c.stops=stops;local success=false
api.cmd.sendCommand(api.cmd.makeLineUpdateCmd(36847,c),function(_,ok)success=ok end)
local now=api.engine.getComponent(36847,CT.LINE);local out={updated=success,stops={}}
for _,s in ipairs(now.stops) do out.stops[#out.stops+1]={passengerLoad=s.stopConfig.load[1],passengerMax=s.stopConfig.maxLoad[1],cargoSlots=#s.stopConfig.load};assert(s.stopConfig.load[1] and s.stopConfig.maxLoad[1]==1,'passenger configuration not persisted') end
return B.json.encode(out)
