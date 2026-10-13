local ssu = require "::/gui/main/stylesheetutil.lua"

function data()
    local result = {}
    local add = ssu.makeAdder(result)
    add("#tnj.coordinates.panel", {
        padding = {4, 4, 4, 4},
        gravity = {-1, 0.5},
    })
    add("#tnj.coordinates.panel > BoxLayout", {
        innerSpacing = {8, 0},
        outerSpacing = {0, 0},
    })
    add("#tnj.coordinates.value", {
        fontSize = 13,
        minSize = {300, -1},
        gravity = {-1, 0.5},
    })
    return result
end
