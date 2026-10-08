local CT=api.type.ComponentType
local choices={{{group=76245,station=0,id=76244}},{{group=79055,station=0,id=62396},{group=79055,station=1,id=61440}},{{group=62361,station=0,id=62142},{group=62361,station=1,id=62141}}}
local nodes={}
for i,opts in ipairs(choices) do nodes[i]={};for _,o in ipairs(opts) do
 assert(api.engine.entityExists(o.id),'station missing')
 for j,t in ipairs(api.engine.getComponent(o.id,CT.STATION).terminals) do
 assert(i==1 and t.cargoLoad or i~=1 and t.cargoUnload,'invalid cargo capability')
 nodes[i][#nodes[i]+1]={group=o.group,station=o.station,terminal=j-1,node=t.vehicleNodeId}
 end
end end
local cache={}
local function length(a,b)
 local key=a.node.entity..':'..a.node.index..'>'..b.node.entity..':'..b.node.index
 if cache[key] then return cache[key] end
 local path=api.engine.util.pathfinding.findPathNodeToNode({a.node},{b.node},{api.type.enum.TransportMode.TRUCK})
 local n=0;if #path==0 then return math.huge end
 for _,p in ipairs(path) do n=n+api.engine.getComponent(p[1].entity,CT.TRANSPORT_NETWORK).edges[p[1].index+1].geometry.length end
 cache[key]=n;return n
end
local best,chosen,legs=math.huge,nil,nil
for _,a in ipairs(nodes[1]) do for _,b in ipairs(nodes[2]) do for _,c in ipairs(nodes[3]) do
 for _,route in ipairs({{a,b,c},{a,c,b}}) do
 local d={length(route[1],route[2]),length(route[2],route[3]),length(route[3],route[1])};local total=d[1]+d[2]+d[3]
 if total<best then best=total;chosen=route;legs=d end
 end
end end end
assert(chosen,'no complete truck route')
local stops={};for _,s in ipairs(chosen) do stops[#stops+1]={group=s.group,station=s.station,terminal=s.terminal} end
return B.json.encode({distance=best,stops=stops,legs=legs,lines=B.commands.list_lines({})})
