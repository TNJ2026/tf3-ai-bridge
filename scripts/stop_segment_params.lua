local p=api.engine.util.proposal.replaceSegment(62116);local o=p.proposal.addedSegments[1].params;local out={}
for _,v in pairs(getmetatable(o) or {}) do if type(v)=='table' then for k,f in pairs(v) do if type(k)=='string' and type(f)=='function' and k:sub(1,2)~='__' then local ok,x=pcall(function()return o[k]end);out[k]=ok and B.toPlain(x) or 'error' end end end end
return B.json.encode(out)
