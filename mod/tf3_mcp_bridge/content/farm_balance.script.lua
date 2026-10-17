-- Only the base vegetable/grain farm; other agricultural industries are unchanged.
-- Keep the resource identity so existing constructions still reference this farm.
function data()
    return {
        runFn = function(_captureParams, _configDict, _allModParams)
            local applied = setmetatable({}, { __mode = "k" })
            addModifier("loadConstruction", function(fileName, construction)
                if fileName ~= "::/industries/farm/farm.con" then
                    return construction
                end
                local config = construction.updateScript
                    and construction.updateScript.params
                    and construction.updateScript.params.stockListConfig
                assert(config and config.stocks and config.rules,
                    "AI Bridge farm balance: missing native stock configuration")
                if applied[config] then return construction end

                -- Validate everything before modifying the resource.
                for _, stock in ipairs(config.stocks) do
                    assert(type(stock.capacity) == "number" and stock.capacity >= 0,
                        "AI Bridge farm balance: invalid stock capacity")
                end
                for _, rule in ipairs(config.rules) do
                    if not rule.booster then
                        for _, amount in pairs(rule.output or {}) do
                            assert(type(amount) == "number" and amount >= 0,
                                "AI Bridge farm balance: invalid production amount")
                        end
                    end
                end
                for _, stock in ipairs(config.stocks) do
                    stock.capacity = stock.capacity * 10
                end
                for _, rule in ipairs(config.rules) do
                    if not rule.booster then
                        for cargo, amount in pairs(rule.output or {}) do
                            rule.output[cargo] = amount * 5
                        end
                    end
                end
                -- Do not change fertilizer consumption, production timing or worker bonuses.
                applied[config] = true
                return construction
            end)
        end,
    }
end
