local out={}
for _,name in ipairs({'EdgeObject','Proposal','ModelInstance'}) do local t=api.type[name];out[name]=type(t);if t then local ok,o=pcall(function()return t.new()end);if ok then local ks={};for _,v in pairs(getmetatable(o) or {}) do if type(v)=='table' then for k,f in pairs(v) do if type(k)=='string' and type(f)=='function' then ks[k]=true end end end end;out[name..'Members']=ks end end end
local ok,o=pcall(function()return api.type.Proposal.EdgeObject.new()end);out.nestedOk=ok;if ok then local ks={};for _,v in pairs(getmetatable(o)) do if type(v)=='table' then for k,f in pairs(v) do if type(k)=='string' and type(f)=='function' then ks[k]=true end end end end;out.nestedMembers=ks end
return B.json.encode(out)
