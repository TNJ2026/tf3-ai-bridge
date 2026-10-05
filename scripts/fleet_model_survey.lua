local out={state=B.commands.get_game_state({}),models={}}
for _,m in ipairs(B.commands.list_vehicle_models({limit=300}).models)do
 if m.model:find('/vehicle/truck/',1,true)or m.model:find('/vehicle/helicopter/',1,true)or m.model:find('/vehicle/ship/',1,true)then
  local md=api.res.modelRep.get(m.id).metadata
  m.loadSpeed=md.transportVehicle.loadSpeed
  m.arrivalDelay=md.transportVehicle.arrivalDelay;m.departureDelay=md.transportVehicle.departureDelay
  m.maintenanceFactor=md.transportVehicle.maintenanceFactor
  m.modes={};for _,v in ipairs(md.transportVehicle.transportModes)do m.modes[#m.modes+1]=v end
  m.modeNames={};for _,name in ipairs({'TRUCK','HELICOPTER','SMALL_SHIP','SHIP'})do for _,v in ipairs(m.modes)do if api.type.enum.TransportMode[name]==v then m.modeNames[#m.modeNames+1]=name end end end
  m.compartments={}
  for _,comp in ipairs(md.transportVehicle.compartments)do
   local configs={}
   for i,lc in ipairs(comp.loadConfigs)do
    local entry={index=i-1,capacity=lc.cargoEntry.capacity,cargos={}}
    api.res.cargoTypeRep.forEachCargoType(lc.cargoEntry.cargoTypeSet,function(c)entry.cargos[#entry.cargos+1]=c end)
    for _,key in ipairs({'cargoTypeSet','type','cargo','cargoType','cargoTypeId','cargoTypes','typeId'})do
     local ok,v=pcall(function()return lc.cargoEntry[key]end)
     if ok and v~=nil then entry[key]=B.toPlain(v)end
    end
    configs[#configs+1]=entry
   end
   m.compartments[#m.compartments+1]=configs
  end
  m.performance=B.toPlain(md.landVehicle or md.airVehicle or md.waterVehicle)
  out.models[#out.models+1]=m
 end
end
return B.json.encode(out)
