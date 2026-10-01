assert(#api.engine.system.transportVehicleSystem.getLineVehicles(76282)==0,'line already has vehicles; inspect before purchasing')
local out={}
B.commands.buy_vehicles({depot=76280,model='::/vehicle/bus/citroen_cityrama/citroen_cityrama.mdl',count=4,line=76282},function(ok,r)out.ok=ok;out.result=r end)
out.vehicles=B.commands.list_vehicles({line=76282});out.game=B.commands.get_game_state()
return B.json.encode(out)
