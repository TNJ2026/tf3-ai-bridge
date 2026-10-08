local p=api.engine.util.proposal.replaceSegment(72665)
local out={};for _,key in ipairs({'nodesToAdd','nodesToRemove','edgesToAdd','edgesToRemove','nodeConfigsToAdd','nodeConfigsToRemove','addedSegments','removedSegments'}) do local ok,v=pcall(function()return p[key]end);if ok and v then out[key]={};for _,r in ipairs(v) do if type(r)=='number' then out[key][#out[key]+1]=r else local o={};pcall(function()o.entity=r.entity end);pcall(function()o.lanes=#r.comp.laneConnections end);out[key][#out[key]+1]=o end end end end
return B.json.encode(out)
