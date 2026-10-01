local out={laneType=type(api.type.LaneConnection),nodeType=type(api.type.BaseNodeLaneConnectionAndEntity)}
local ok,r=pcall(function()local v=api.type.BaseNodeLaneConnectionAndEntity.new();out.created=true;v.entity=72647;out.entity=true;v.comp.trafficLightPreference=2;out.pref=true;v.comp.laneConnections={{segment0=72665,lane0=1,segment1=72666,lane1=2,withRoad=true,withTram=false}};out.lanes=true;return v end)
out.ok=ok;if not ok then out.error=B.toPlain(r) end
return B.json.encode(out)
