local function members(o)local out={};for _,v in pairs(getmetatable(o) or {}) do if type(v)=='table' then for k,f in pairs(v) do if type(k)=='string' and type(f)=='function' and k:sub(1,2)~='__' then out[k]=true end end end end;return out end
local p=api.engine.util.proposal.replaceSegment(62116)
return B.json.encode({proposal=members(p),street=members(p.proposal),edge=members(p.proposal.addedSegments[1]),ctor=members(api.type.SimpleProposal.ConstructionEntity.new())})
