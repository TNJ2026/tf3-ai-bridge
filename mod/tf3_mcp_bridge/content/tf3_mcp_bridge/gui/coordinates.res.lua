function data()
    return {
        type = "react-plugin ::GameBarInfoDisplayExtension",
        data = {
            filePath = "tnj_tf3_ai_bridge::/tf3_mcp_bridge/gui/coordinates.script@Panel",
            -- Native getPlugins sorts order ascending; append after other info items.
            order = 10000,
        },
    }
end
