local CT=api.type.ComponentType;local mode=api.type.enum.TransportMode.TRUCK
local choices={{{group=99132,id=106358,station=0}},{{group=79044,id=56180,station=0},{group=79044,id=56174,station=1}},{{group=79032,id=62454,station=0},{group=79032,id=62443,station=1}}}
local function leg(a,b,m)
 local p=api.engine.util.pathfinding.findPathNodeToNode({a.node},{b.node},{m});if #p==0 then return nil end;local n=0;for _,s in ipairs(p) do n=n+api.engine.getComponent(s[1].entity,CT.TRANSPORT_NETWORK).edges[s[1].index+1].geometry.length end;return n
end
for i,opts in ipairs(choices) do for _,o in ipairs(opts) do local t=api.engine.getComponent(o.id,CT.STATION).terminals[1];assert(i==1 and t.cargoLoad or i~=1 and t.cargoUnload);o.node=t.vehicleNodeId;o.terminal=0 end end
local best,route,legs=math.huge,nil,nil
for _,a in ipairs(choices[1]) do for _,b in ipairs(choices[2]) do for _,c in ipairs(choices[3]) do for _,r in ipairs({{a,b,c},{a,c,b}}) do
 local x,y,z=leg(r[1],r[2],mode),leg(r[2],r[3],mode),leg(r[3],r[1],mode)
 if x and y and z and x+y+z<best then best=x+y+z;route=r;legs={x,y,z} end
end end end end
assert(route,'truck loop unreachable');local stops={};for _,r in ipairs(route) do stops[#stops+1]={group=r.group,station=r.station,terminal=0} end
local a={node=api.engine.getComponent(79847,CT.STATION).terminals[1].vehicleNodeId};local b={node=api.engine.getComponent(106244,CT.STATION).terminals[1].vehicleNodeId}
local shipForward,shipReturn=leg(a,b,api.type.enum.TransportMode.SMALL_SHIP),leg(b,a,api.type.enum.TransportMode.SMALL_SHIP)
assert(shipForward and shipReturn,'ship loop unreachable')
return B.json.encode({truck={stops=stops,length=best,legs=legs},ship={stops={{group=79387,station=0,terminal=0},{group=106264,station=0,terminal=0}},nativePathsBothDirections=true},cargo=6,lines=B.commands.list_lines({})})
