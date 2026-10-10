local ssu=require "::/gui/main/stylesheetutil.lua"
function data()
 local result={}; local add=ssu.makeAdder(result)
 add("R::TNJBridgeEchoProbe TextInputField", {size={260,36}})
 add("R::TNJBridgeEchoProbe BoxLayout", {innerSpacing={8,0}})
 return result
end
