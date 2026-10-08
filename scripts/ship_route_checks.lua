-- New cache for each engine evaluation; never persists across world changes.
local function newShipRouteChecker()
 local cache={};local stats={queries=0,hits=0}
 local function key(nodes)
  assert(#nodes>0,'Missing ship endpoint nodes')
  local keys,seen={},{}
  for _,n in ipairs(nodes)do
   assert(type(n.entity)=='number' and n.entity>=0 and n.entity%1==0,'Invalid node entity')
   assert(type(n.index)=='number' and n.index>=0 and n.index%1==0,'Invalid node index')
   local net=assert(api.engine.getComponent(n.entity,api.type.ComponentType.TRANSPORT_NETWORK),'Missing endpoint network')
   assert(n.index<#net.nodes,'Stale endpoint node')
   local k=n.entity..':'..n.index;if not seen[k]then seen[k]=true;keys[#keys+1]=k end
  end
  table.sort(keys);return table.concat(keys,',')
 end
 local function query(a,b,mode,profile)
  assert(mode==api.type.enum.TransportMode.SMALL_SHIP or mode==api.type.enum.TransportMode.SHIP,'Non-ship mode')
  assert(type(profile)=='string' and #profile>0,'Missing navigation profile')
  local k=mode..'|'..#profile..':'..profile..'|'..key(a)..'>'..key(b)
  if cache[k]then stats.hits=stats.hits+1;return cache[k]end
  local path=api.engine.util.pathfinding.findPathNodeToNode(a,b,{mode})
  local r={reachable=#path>0,steps=#path};cache[k]=r;stats.queries=stats.queries+1
  return r
 end
 return query,stats
end
