local out={};for k,v in pairs(api.engine.util.proposal) do out[k]=type(v) end
local p=api.engine.util.proposal.replaceSegment(62116);out.replace={added={},removed={},maps={new2old=B.toPlain(p.proposal.new2oldSegments),old2new=B.toPlain(p.proposal.old2newSegments)},configs={}}
for _,e in ipairs(p.proposal.addedSegments) do out.replace.added[#out.replace.added+1]={id=e.entity,params=B.toPlain(e.params),objects=B.toPlain(e.comp.objects)} end
for _,e in ipairs(p.proposal.removedSegments) do out.replace.removed[#out.replace.removed+1]=e.entity end
for _,c in ipairs(p.proposal.nodeConfigsToAdd) do out.replace.configs[#out.replace.configs+1]={id=c.entity,count=#c.comp.laneConnections} end
return B.json.encode(out)
