local out={}
for _,n in ipairs({72647,70933,72653,59863}) do
 local c=api.engine.getComponent(n,api.type.ComponentType.BASE_NODE_CONFIG);local row={node=n,lanes={}}
 if c then row.userModified=c.userModifiedLaneConnections;row.trafficModified=c.userModifiedTrafficLightStates;row.crosswalks=B.toPlain(c.crosswalks);row.trafficPreference=c.trafficLightPreference
 for _,l in ipairs(c.laneConnections) do row.lanes[#row.lanes+1]={segment0=l.segment0,segment1=l.segment1,lane0=l.lane0,lane1=l.lane1,road=l.withRoad} end end
 out[#out+1]=row
end
return B.json.encode(out)
