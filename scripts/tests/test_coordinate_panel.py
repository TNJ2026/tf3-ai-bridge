"""Offline resource and recipe contracts; native rendering remains a live check."""
from pathlib import Path

from lupa.lua52 import LuaRuntime


SOURCE = (Path(__file__).resolve().parents[2] / "mod/tf3_mcp_bridge/content/"
          "tf3_mcp_bridge/gui/coordinates.script.lua")


def test_coordinate_panel_resource_layout_and_reading():
    lua = LuaRuntime()
    lua.execute('''
        local states = {}
        local stateIndex = 0
        local mouseApiAllowed = false
        local function scopedTick(fn, allowed)
            return function()
                mouseApiAllowed = allowed
                fn()
                mouseApiAllowed = false
            end
        end
        local builtin = {type = {Orientation = {Horizontal = 0}}}
        for _, name in ipairs({'Button', 'TextView', 'Component', 'BoxLayout'}) do
            builtin[name] = function(params)
                return {kind = name, params = params}
            end
        end
        local react = {
            RegisterPluginRecipe = function(_, _, fn) return fn end,
            useState = function(initial)
                stateIndex = stateIndex + 1
                if not states[stateIndex] then
                    states[stateIndex] = {
                        value = initial,
                        old = function(self) return self.value end,
                        set = function(self, v) self.value = v end,
                    }
                end
                return states[stateIndex]
            end,
            onStep = function(fn) tick = scopedTick(fn, true) end,
            onStepTimer = function(fn) tick = scopedTick(fn, false) end,
        }
        function ug_require(path)
            if path == '::/gui/main/react.lua' then return react end
            if path == '::/gui/main/builtin.lua' then return builtin end
            if path == '::/gui/game_bar/game_bar_widgets.tl' then
                return {GameBarInfoDisplayExtension = {}}
            end
            error('Unexpected dependency: ' .. path)
        end
        terrain = true
        reads = 0
        messages = {}
        print = function(message) messages[#messages + 1] = message end
        api = {gui = {mouse = {
            hasTerrainPosition = function()
                assert(mouseApiAllowed, 'API is currently restricted')
                return terrain
            end,
            getTerrainPosition = function()
                assert(mouseApiAllowed, 'API is currently restricted')
                reads = reads + 1
                return {x = 12.3, y = -45.6, z = 7.8}
            end,
        }}}
        data = false
        function render()
            stateIndex = 0
            local root = data().Panel()
            assert(root.kind == 'BoxLayout', 'Recipe child must be a layout')
            local panel = root.params.children[1]
            assert(panel.kind == 'Component')
            assert(panel.params.layout.kind == 'BoxLayout')
            return panel.params.layout.params.children
        end
    ''')
    lua.execute(SOURCE.read_text(encoding="utf-8"))
    lua.execute('''
        assert(type(data) == 'function' and type(data().Panel) == 'function')
        assert(data() == data())
        local children = render()
        assert(#children == 1 and children[1].kind == 'TextView')
        tick()
        children = render()
        assert(children[1].params.text == 'X  12.3    Y  -45.6    Z  7.8 米')
        assert(#messages == 0)
        terrain = false
        tick()
        children = render()
        assert(children[1].params.text == '未指向地面')
        terrain = true
        api.gui.mouse.getTerrainPosition = function() error('native read failure') end
        tick()
        tick()
        children = render()
        assert(children[1].params.text == '坐标暂不可用')
        assert(#messages == 1)
        assert(string.find(messages[1], 'getTerrainPosition', 1, true))
        assert(string.find(messages[1], 'native read failure', 1, true))
    ''')
