local function dump(o)local r={};for _,v in pairs(getmetatable(o) or {}) do if type(v)=='table' then for k in pairs(v) do if type(k)=='string' and k:sub(1,2)~='__' then local ok,x=pcall(function()return o[k]end);if ok then r[k]=type(x) end end end end end;return r end
local p=api.engine.util.proposal.replaceSegment(61156)
return B.json.encode({full=dump(p),street=dump(p.proposal),eo=dump(api.type.StreetProposal.EdgeObject.new()),names=B.commands.list_stations({})})
