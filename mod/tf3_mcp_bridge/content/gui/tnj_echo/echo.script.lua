-- Experimental GUI/log fallback. Only explicit read and staged construction commands.
local react = ug_require "::/gui/main/react.lua"
local builtin = ug_require "::/gui/main/builtin.lua"
local widgets = ug_require "::/gui/game_bar/game_bar_widgets.tl"
local EchoPanel = react.RegisterPluginRecipe(widgets.GameBarInfoDisplayExtension, "TNJBridgeEchoProbe", function()
 local input = react.useState("")
 local status = react.useState("Read / staged build")
 return builtin.BoxLayout{
  orientation = builtin.type.Orientation.Horizontal,
  children = {
   builtin.TextView{text="AI Bridge"},
   builtin.TextInputField{
    meta={id="tnj_bridge_echo_input"},
    placeholderText="ID command", value=input:old(), acceptOnFocusLoss=false,
    onTyping=function(value) input:set(value) end,
    onValueChange=function(value) input:set(value) end,
   },
   builtin.Button{
    meta={id="tnj_bridge_echo_send"}, content=builtin.TextView{text="Send"},
    onClick=function()
     local value=input:old()
     if type(value)~="string" or #value==0 or #value>512 then
      status:set("Enter 1-512 bytes");return
     end
     local result=api.gui.fireGuiScriptEvent("tnj_bridge_readonly", "tnj_bridge_readonly.request", value)
     status:set(type(result)=="string" and result or "Submitted; inspect log")
    end,
   },
   builtin.TextView{text=status:old()},
  },
 }
end)
local result={EchoPanel=EchoPanel}
function data() return result end
return result
