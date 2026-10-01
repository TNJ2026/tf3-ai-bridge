local e=api.type.SimpleStreetProposal.EdgeObject.new();local out={}
for k,v in pairs(getmetatable(e)) do if type(v)=='table' then local r={};for a,b in pairs(v) do r[tostring(a)]=type(b) end;out[tostring(k)]=r end end
return B.json.encode(out)
