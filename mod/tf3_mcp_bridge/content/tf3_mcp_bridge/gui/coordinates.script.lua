-- GUI-only readout. Never sends engine commands or stores anything in the save.
local react = ug_require "::/gui/main/react.lua"
local builtin = ug_require "::/gui/main/builtin.lua"
local gameBar = ug_require "::/gui/game_bar/game_bar_widgets.tl"
local coordinates = {}
local PANEL_VISIBLE = false
local loggedReadErrors = {}
local readErrorCount = 0

local function reportReadError(stage, detail)
    local message = stage .. ": " .. tostring(detail)
    -- Preserve the cause without flooding the log on every GUI timer tick.
    if not loggedReadErrors[message] and readErrorCount < 3 then
        loggedReadErrors[message] = true
        readErrorCount = readErrorCount + 1
        print("[TNJ_COORDINATES_V1] " .. message)
    end
end

local function readPosition()
    local stage = "hasTerrainPosition"
    local ok, text = pcall(function()
        if not api.gui.mouse.hasTerrainPosition() then
            return "Not pointing at terrain / 未指向地面"
        end
        stage = "getTerrainPosition"
        local p = api.gui.mouse.getTerrainPosition()
        stage = "read Vec3f fields"
        local values = {p.x, p.y, p.z}
        for i = 1, 3 do
            local v = values[i]
            if type(v) ~= "number" or v ~= v or math.abs(v) == math.huge then
                reportReadError("validate coordinate " .. i, "type=" .. type(v) .. ", value=" .. tostring(v))
                return "Coordinates unavailable / 坐标暂不可用"
            end
            if math.abs(v) < 0.05 then values[i] = 0 end
        end
        stage = "format coordinates"
        return string.format("X  %.1f    Y  %.1f    Z  %.1f m", values[1], values[2], values[3])
    end)
    if not ok then reportReadError(stage, text) end
    return ok and text or "Coordinates unavailable / 坐标暂不可用"
end

coordinates.Panel = react.RegisterPluginRecipe(
    gameBar.GameBarInfoDisplayExtension, "TnjMouseCoordinatePanel", function()
        local position = react.useState("Move mouse over terrain / 将鼠标移到地面")
        -- Mouse APIs require the synchronous GUI step context.
        -- onStepTimer defers callbacks into a scope where these APIs are restricted.
        react.onStep(function()
            local text = readPosition()
            if position:old() ~= text then position:set(text) end
        end)

        -- Keep coordinate updates and the panel implementation; render no widget.
        if not PANEL_VISIBLE then
            return builtin.BoxLayout{
                orientation = builtin.type.Orientation.Horizontal,
                children = {},
            }
        end

        local children = {
            builtin.TextView{
                meta = {
                    id = "tnj.coordinates.value",
                    class = "tnj-coordinate-value",
                    tooltip = "Terrain coordinates (m): X/Y position, Z elevation. / 鼠标地面坐标：X、Y 为平面位置，Z 为地面高度，单位：米。",
                },
                text = position:old(),
            },
        }
        -- Custom recipes must return a layout, as native game-bar plugins do.
        return builtin.BoxLayout{
            orientation = builtin.type.Orientation.Horizontal,
            children = {
                builtin.Component{
                    meta = {id = "tnj.coordinates.panel", class = "tnj-coordinate-panel"},
                    layout = builtin.BoxLayout{
                        orientation = builtin.type.Orientation.Horizontal,
                        children = children,
                    },
                },
            },
        }
    end)

-- Native .script@Panel resource loading resolves exports through data().
function data()
    return coordinates
end

return coordinates
