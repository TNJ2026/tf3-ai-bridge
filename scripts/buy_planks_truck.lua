assert(#api.engine.system.transportVehicleSystem.getLineVehicles(90542)==0,'line already has vehicles; inspect before purchase')
local model='::/vehicle/truck/amo_f15/amo_f15_univ.mdl'
local md=api.res.modelRep.get(api.res.modelRep.find(model)).metadata
assert(md.landVehicle.engines[1].type==3,'unexpected engine type')
local out={price=md.cost.price}
B.commands.buy_vehicles({depot=77213,model=model,count=1,line=90542},function(ok,r)out.ok=ok;out.result=r end)
out.vehicles=B.commands.list_vehicles({line=90542})
return B.json.encode(out)
