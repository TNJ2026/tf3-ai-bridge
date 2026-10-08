local CT=api.type.ComponentType;local ends={};local seen={};local counts={roads=0,tracks=0,nodes=0}
for n,edges in pairs(api.engine.system.streetSystem.getNode2SegmentMap()) do
 counts.nodes=counts.nodes+1
 if #edges==1 and #ends<2 then local e=api.engine.getComponent(edges[1],CT.BASE_EDGE);if e.roadType==api.type.enum.RoadType.STREET then ends[#ends+1]=n end end
 for _,id in ipairs(edges) do if not seen[id] then seen[id]=true;local e=api.engine.getComponent(id,CT.BASE_EDGE);if e.roadType==api.type.enum.RoadType.STREET then counts.roads=counts.roads+1 elseif e.roadType==api.type.enum.RoadType.TRACK then counts.tracks=counts.tracks+1 end end end
end
local result=B.commands.get_route_snapshot({start_node=ends[1],end_node=ends[2],whole_map=true,spacing=100})
-- Route surveys omit anchor edges; add them back for a complete map inventory.
for _,n in ipairs(ends) do
 local id=api.engine.system.streetSystem.getNodeSegments(n)[1]
 local e=api.engine.getComponent(id,CT.BASE_EDGE);local v=api.engine.getComponent(id,CT.BOUNDING_VOLUME).bbox
 local function xyz(p)return {x=p.x,y=p.y,z=p.z}end
 result.obstacles[#result.obstacles+1]={entity=id,kind='BASE_EDGE',node0=e.node0,node1=e.node1,roadType=e.roadType,roadTemplate=e.roadTemplate,
  position0=xyz(e.position0),position1=xyz(e.position1),tangent0=xyz(e.tangent0),tangent1=xyz(e.tangent1),min=xyz(v.min),max=xyz(v.max)}
 local r=api.engine.getRevision(id);result.revisions[tostring(id)]=table.concat({r.num[1],r.num[2],r.num[3]},':')
end
result.networkCounts=counts;result.anchorPurpose='arbitrary road anchors for whole-map collection; no route planned'
return B.json.encode(result)
