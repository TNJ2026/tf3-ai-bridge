local CT=api.type.ComponentType;local groups={79023,79032,79044,79055,62361,79072};local choices={};local costs={}
for i,g in ipairs(groups) do local sg=api.engine.getComponent(g,CT.STATION_GROUP);choices[i]={};for j,id in ipairs(sg.stations) do local s=api.engine.getComponent(id,CT.STATION);for k,t in ipairs(s.terminals) do choices[i][#choices[i]+1]={station=j-1,terminal=k-1,id=id,node=t.vehicleNodeId} end end end
for i=1,6 do local j=i%6+1;costs[i]={};for a,x in ipairs(choices[i]) do costs[i][a]={};for b,y in ipairs(choices[j]) do local path=api.engine.util.pathfinding.findPathNodeToNode({x.node},{y.node},{api.type.enum.TransportMode.BUS});local len=0;for _,p in ipairs(path) do local n=api.engine.getComponent(p[1].entity,CT.TRANSPORT_NETWORK);len=len+n.edges[p[1].index+1].geometry.length end;costs[i][a][b]=#path>0 and len or 1e12 end end end
local best=1e12;local selection={};local chosen={}
local function search(i) if i<=6 then for a=1,#choices[i] do chosen[i]=a;search(i+1) end;return end;local total=0;for k=1,6 do total=total+costs[k][chosen[k]][chosen[k%6+1]] end;if total<best then best=total;for k=1,6 do selection[k]=chosen[k] end end end
search(1);assert(best<1e12,'no connected circuit')
local out={length=best,stops={}}
for i,g in ipairs(groups) do local c=choices[i][selection[i]];out.stops[i]={group=g,station=c.station,terminal=c.terminal,stationEntity=c.id,nextLeg=costs[i][selection[i]][selection[i%6+1]]} end
return B.json.encode(out)

