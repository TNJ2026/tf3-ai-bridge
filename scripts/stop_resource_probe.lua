local out={}
for _,n in ipairs({'::/stations/street/small_stops/small_mid.con','::/stations/street/small_stops/small_mid_twosided.con','::/stations/street/small_stops/small_mid.mdl'}) do out[#out+1]={name=n,model=api.res.modelRep.find(n),construction=api.res.constructionRep.find(n)} end
local e=api.type.SimpleStreetProposal.EdgeObject.new();local mt=getmetatable(e);out.meta={};if type(mt)=='table' then for k,v in pairs(mt) do out.meta[tostring(k)]=type(v) end end
return B.json.encode(out)
