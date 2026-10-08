local task=B.json.decode(TASKJSON);local action=ACTION;local CT=api.type.ComponentType
local mode=assert(api.type.enum.TransportMode[task.mode],'unknown transport mode')
local groups={};api.engine.forEachEntityWithComponent(function(id)local g=api.engine.getComponent(id,CT.STATION_GROUP);for i,s in ipairs(g.stations)do groups[s]={group=id,station=i-1}end end,CT.STATION_GROUP)
local cons={};api.engine.forEachEntityWithComponent(function(id)local c=api.engine.getComponent(id,CT.CONSTRUCTION);local p=c.transf:cols(3);cons[#cons+1]={id=id,c=c,x=p.x,y=p.y}end,CT.CONSTRUCTION)
local choices={}
for i,ep in ipairs(task.endpoints)do
 local stationIds={}
 if ep.stop then
  for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(ep.stop.position.x,ep.stop.position.y),200,CT.BASE_EDGE))do
   local e=api.engine.getComponent(id,CT.BASE_EDGE);local a,b=ep.stop.edge_endpoints[1],ep.stop.edge_endpoints[2]
   if math.abs(e.position0.x-a.x)<.2 and math.abs(e.position0.y-a.y)<.2 and math.abs(e.position1.x-b.x)<.2 and math.abs(e.position1.y-b.y)<.2 then
    for _,ref in ipairs(e.objects)do stationIds[#stationIds+1]=ref[1]end
   end
  end
 else
  local count=0
  for _,r in ipairs(cons)do if math.abs(r.x-ep.position.x)<.2 and math.abs(r.y-ep.position.y)<.2 then
   count=count+1;for _,id in ipairs(r.c.stations)do stationIds[#stationIds+1]=id end
  end end
  assert(count==1,'endpoint construction absent/ambiguous: '..ep.id)
 end
 choices[i]={}
 for _,id in ipairs(stationIds)do local st=api.engine.getComponent(id,CT.STATION);local g=groups[id]
  if st and g then for k,t in ipairs(st.terminals)do
   if (ep.terminal_index==nil or ep.terminal_index==k-1) and (t.transportModes[mode] or (ep.stop and mode==api.type.enum.TransportMode.TRUCK)) and ((#ep.loads>0 and t.cargoLoad) or (#ep.loads==0 and t.cargoUnload))then choices[i][#choices[i]+1]={group=g.group,station=g.station,terminal=k-1,entity=id,node=t.vehicleNodeId}end
  end end
 end
 assert(#choices[i]>0,'no compatible cargo terminal: '..ep.id)
end
local costs={};local n=#choices
for i,opts in ipairs(choices)do costs[i]={};for a,x in ipairs(opts)do costs[i][a]={};for b,y in ipairs(choices[i%n+1])do
 local path=api.engine.util.pathfinding.findPathNodeToNode({x.node},{y.node},{mode});local len=0
 for _,st in ipairs(path)do local net=api.engine.getComponent(st[1].entity,CT.TRANSPORT_NETWORK);len=len+net.edges[st[1].index+1].geometry.length end
 costs[i][a][b]=#path>0 and len or 1e15
end end end
local best=1e15;local chosen={};local selection={}
local function search(i)
 if i<=n then for a=1,#choices[i]do chosen[i]=a;search(i+1)end;return end
 local total=0;for k=1,n do total=total+costs[k][chosen[k]][chosen[k%n+1]]end
 if total<best then best=total;for k=1,n do selection[k]=chosen[k]end end
end
search(1);assert(best<1e15,'no native closed cargo route: '..task.id)
local out={id=task.id,length=best,stops={},pathVerified=true}
for i=1,n do local c=choices[i][selection[i]];out.stops[i]={group=c.group,station=c.station,terminal=c.terminal,entity=c.entity,loads=task.endpoints[i].loads,lengthToNext=costs[i][selection[i]][selection[i%n+1]]}end
local matches={};for _,id in ipairs(api.engine.system.lineSystem.getLines())do local name=api.engine.getComponent(id,CT.NAME);if name and name.name==task.name then matches[#matches+1]=id end end
assert(#matches<=1,'duplicate named line')
local function audit(id)
 local l=api.engine.getComponent(id,CT.LINE);assert(l.customFilters and #l.stops==n,'line shape/config changed')
 for i,s in ipairs(l.stops)do
  local wanted=out.stops[i];assert(s.stationGroup==wanted.group and s.station==wanted.station and s.terminal==wanted.terminal,'line terminals changed')
  local allowed={};for _,c in ipairs(wanted.loads)do allowed[c]=true end
  for c in pairs(api.res.cargoTypeRep.getAll(true))do assert(s.stopConfig.load[c+1]==(allowed[c]==true) and s.stopConfig.maxLoad[c+1]==1,'cargo loading config changed')end
  assert(not s.stopConfig.forceUnload,'unexpected forced unload')
 end
 return true
end
if #matches==1 then out.line=matches[1];out.existing=true;out.verified=audit(out.line);return B.json.encode(out)end
if action~='build'then out.existing=false;return B.json.encode(out)end
local line=api.type.Line.new();line.customFilters=true;local stops={}
for _,w in ipairs(out.stops)do
 local s=api.type.Line.Stop.new();s.stationGroup=w.group;s.station=w.station;s.terminal=w.terminal;s.maxAdditionalWaitingTime=0
 local cfg=api.type.Line.StopConfig.new();local loads,maximum,allowed={},{},{};for _,c in ipairs(w.loads)do allowed[c]=true end
 for c in pairs(api.res.cargoTypeRep.getAll(true))do loads[c+1]=allowed[c]==true;maximum[c+1]=1 end
 cfg.load=loads;cfg.maxLoad=maximum;cfg.forceUnload=false;s.stopConfig=cfg;stops[#stops+1]=s
end
line.stops=stops;local accepted=false
api.cmd.sendCommand(api.cmd.makeLineCreateCmd(task.name,api.type.Vec3f.new(.12,.55,.8),api.engine.util.getPlayer(),line),function(_,ok)accepted=ok==true end)
out.accepted=accepted
for _,id in ipairs(api.engine.system.lineSystem.getLines())do local name=api.engine.getComponent(id,CT.NAME);if name and name.name==task.name then assert(not out.line,'duplicate creation');out.line=id end end
out.verified=out.line and audit(out.line)or false
return B.json.encode(out)
