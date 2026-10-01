local out={}
for _,m in ipairs(B.commands.list_vehicle_models({carrier='ROAD',limit=300}).models) do
 if m.model:find('/truck/',1,true) then
 local r=api.res.modelRep.get(m.id);local engines={};for _,e in ipairs(r.metadata.landVehicle.engines) do engines[#engines+1]=e.type end
 local cargo={};for _,c in ipairs(r.metadata.transportVehicle.compartments) do for _,lc in ipairs(c.loadConfigs) do cargo[#cargo+1]={capacity=lc.cargoEntry.capacity,types=B.toPlain(lc.cargoEntry.cargoTypeSet)} end end
 out[#out+1]={info=m,engines=engines,cargo=cargo}
 end
end
return B.json.encode(out)
