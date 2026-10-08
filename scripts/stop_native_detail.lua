local function dump(o,d)
 local t=type(o);if t=='number' or t=='string' or t=='boolean' or t=='nil' then return o end
 if d<=0 then return tostring(o) end
 local r={};if t=='table' then for k,v in pairs(o) do r[tostring(k)]=dump(v,d-1) end;return r end
 if t=='userdata' then for _,v in pairs(getmetatable(o) or {}) do if type(v)=='table' then for k,f in pairs(v) do if type(k)=='string' and k:sub(1,2)~='__' then local ok,x=pcall(function()return o[k]end);if ok and type(x)~='function' then r[k]=dump(x,d-1) end end end end end end
 return r
end
local CT=api.type.ComponentType;local out={}
for _,id in ipairs({62438,62425,62282,76059}) do if api.engine.entityExists(id) then local r={};for _,k in ipairs({'BASE_EDGE','EDGE_OBJECT','STATION','TRANSPORT_NETWORK'}) do local c=api.engine.getComponent(id,CT[k]);if c then r[k]=dump(c,6) end end;out[tostring(id)]=r end end
return B.json.encode(out)
