local out={};for k,v in pairs(api.type.StreetProposal) do if type(k)=='string' then out[k]=type(v) end end
local ok,o=pcall(function()return api.type.StreetProposal.EdgeObject.new()end);out.ok=ok;if ok then out.fields={};for _,v in pairs(getmetatable(o)) do if type(v)=='table' then for k,f in pairs(v) do if type(k)=='string' and type(f)=='function' then out.fields[k]=true end end end end end
return B.json.encode(out)
