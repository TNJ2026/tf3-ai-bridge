local vehicles=B.commands.list_vehicles({line=90542})
local problems={};for _,p in ipairs(api.engine.system.lineSystem.getProblemLines(api.engine.util.getPlayer())) do if p[1]==90542 then problems[#problems+1]=B.toPlain(p[2]) end end
return B.json.encode({vehicles=vehicles,problems=problems})
