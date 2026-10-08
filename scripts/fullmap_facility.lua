-- Runs inside an isolated bridge scope. All callback state is local.
local task=TASK
local action=ACTION
local CT=api.type.ComponentType
-- Only read-only batch wrappers inject an index, scoped to one engine call.
local readIndex=nil
local function eachConstruction(resource,fn)
 if readIndex then for _,row in ipairs(readIndex.constructions[resource]or{})do fn(row.id,row.component)end
 else api.engine.forEachEntityWithComponent(fn,CT.CONSTRUCTION)end
end
local function eachWarehouse(construction,fn)
 if readIndex then for _,id in ipairs(readIndex.warehouses[construction]or{})do fn(id)end
 else api.engine.forEachEntityWithComponent(fn,CT.WAREHOUSE)end
end
local resources={headquarters='::/landmarks/hq/headquarter.con',warehouse='::/warehouses/warehouse.con',helipad='::/stations/air/helipad.con',heliport='::/stations/air/heliport.con',truck='::/stations/street/modular_street_station/modular_terminal.con',road_depot='::/depots/road/road_depot/road_depot.con',water_depot='::/depots/water/water_depot.con',road_maintenance='::/depots/road/road_maint_station.con',harbor='::/stations/water/harbor_modular.con'}
resources.bus=resources.truck
resources.helipad2=resources.helipad
resources.water_maintenance='::/depots/water/water_maint_station.con'
local resource=assert(resources[task.kind],'unsupported facility kind')
local function scan()
 local found={}
 eachConstruction(resource,function(id,cached)
  local c=cached or api.engine.getComponent(id,CT.CONSTRUCTION)
  if c.fileName==resource then
   local t=c.transf;local p=t:cols(3)
   if math.abs(p.x-task.position.x)<.2 and math.abs(p.y-task.position.y)<.2 then
    found[#found+1]={id=id,c=c,position={x=p.x,y=p.y,z=p.z}}
   end
  end
 end)
 assert(#found<=1,'multiple matching constructions at site')
 return found[1]
end
local function audit(x)
 local c=x.c;local out={entity=x.id,resource=c.fileName,position=x.position,params=B.toPlain(c.params),stations={},depots={},roadNodes={},frozenNodes=B.toPlain(c.frozenNodes),frozenEdges=B.toPlain(c.frozenEdges),staticVerified=false,operationalAccepted=false}
 local a=math.rad(task.rotation or 0);local v=c.transf:cols(0)
 out.poseVerified=math.abs(v.x-math.cos(a))<.002 and math.abs(v.y-math.sin(a))<.002
 for _,id in ipairs(c.stations)do
  local st=api.engine.getComponent(id,CT.STATION);local row={id=id,terminals={},catchables={}}
  for k,t in ipairs(st.terminals)do row.terminals[#row.terminals+1]={index=k-1,load=t.cargoLoad,unload=t.cargoUnload,vehicleNodeId=B.toPlain(t.vehicleNodeId),modes=B.toPlain(t.transportModes)}end
  for _,id2 in pairs(api.engine.system.catchmentAreaSystem.getStationCatchables(id,true))do row.catchables[#row.catchables+1]=id2 end
  out.stations[#out.stations+1]=row
 end
 out.service={}
 for _,id in ipairs(c.depots)do
  out.depots[#out.depots+1]=id
  local d=api.engine.getComponent(id,CT.VEHICLE_DEPOT)
  if d then out.service[#out.service+1]={id=id,pool=d.maintenancePool,radius=d.catchmentArea and d.catchmentArea.radius,modes=B.toPlain(d.transportModes)}end
 end
 local seen={}
 for _,eid in ipairs(c.frozenEdges)do
  local e=api.engine.getComponent(eid,CT.BASE_EDGE)
  if e then for _,nid in ipairs({e.node0,e.node1})do
   if not seen[nid]then seen[nid]=true;local nd=api.engine.getComponent(nid,CT.BASE_NODE)
    out.roadNodes[#out.roadNodes+1]={id=nid,position={x=nd.position.x,y=nd.position.y,z=nd.position.z},edge=eid}
   end
  end end
 end
 out.componentVerified=true
 if task.kind=='bus'then
  local passenger=false;local cargo=false
  for _,m in pairs(c.params.modules)do
   passenger=passenger or string.find(m.name,'passenger',1,true)~=nil
   cargo=cargo or string.find(m.name,'cargo',1,true)~=nil
  end
  out.passengerVerified=passenger and not cargo and #out.stations>0
  out.componentVerified=out.passengerVerified
 end
 if task.kind=='truck'or task.kind=='helipad'or task.kind=='helipad2'or task.kind=='heliport'or task.kind=='harbor'then out.componentVerified=#out.stations>0 end
 if task.kind=='road_depot'or task.kind=='water_depot'or task.kind=='heliport'then out.componentVerified=out.componentVerified and #out.depots>0 end
 if task.kind=='road_maintenance'then
  out.componentVerified=false;for _,d in ipairs(out.service)do if d.pool==16 and d.radius==600 then out.componentVerified=true end end
 end
 if task.kind=='water_maintenance'then
  out.componentVerified=false
  for _,d in ipairs(out.service)do if d.pool==12 and d.radius==1400 then out.componentVerified=true end end
 end
 if task.kind=='warehouse'then
  out.warehouses={};out.capacity=0
  eachWarehouse(x.id,function(id)
   local w=api.engine.getComponent(id,CT.WAREHOUSE)
   if w.construction==x.id then
    out.warehouses[#out.warehouses+1]={id=id,stockList=w.stockList}
    local list=api.engine.getComponent(w.stockList,CT.STOCK_LIST)
    for _,stock in ipairs(list.stocks)do out.capacity=out.capacity+stock.capacity end
   end
  end)
  out.componentVerified=#out.warehouses>0 and out.capacity>=500*(task.args.module_count or 1)
 end
 local owner=api.engine.getComponent(x.id,CT.PLAYER_OWNED);out.owner=owner and owner.player;out.ownerVerified=out.owner==api.engine.util.getPlayer()
 out.staticVerified=out.poseVerified and out.componentVerified and out.ownerVerified
 return out
end
local existing=scan()
if existing then return B.json.encode({existing=true,audit=audit(existing)})end
assert(not task.reuseOnly,'Reuse-only facility missing or moved; resurvey, never construct a replacement')
if action=='verify'then return B.json.encode({existing=false,built=false})end
local args=task.args or {};args.x=task.position.x;args.y=task.position.y;args.z=api.engine.terrain.getHeightAt(api.type.Vec2f.new(args.x,args.y));args.rotation=task.rotation or 0;args.name=task.id;args.connect=false;args.preview=true;args.allow_collisions=false
if task.kind=='headquarters'then
 local nearest=nil
 for _,t in ipairs(B.commands.get_map_info({}).towns)do
  if t.name==task.town_name then assert(not nearest,'ambiguous headquarters town');nearest=t.id end
 end
 args.town=assert(nearest,'headquarters town missing')
end
local preview,proposal,context
if task.params or task.kind=='road_maintenance'or task.kind=='harbor'or task.kind=='water_depot'or task.kind=='water_maintenance'then
 local params=task.params or{seed=1,modules={}}
 params.year=B.commands.get_game_state({}).date.year
 local modules={};for slot,m in pairs(params.modules or{})do local id=assert(tonumber(slot),'module slot must be numeric');assert(id%1==0,'module slot must be integral');modules[id]=m end;params.modules=modules
 if task.kind=='harbor'then
  local function add(i,j,f,n)
   local name='::/stations/water/'..n..'.module';local id=api.res.moduleRep.find(name);assert(id>=0,name);local d=api.res.moduleRep.get(id)
   params.modules[1000000*(i+100)+100*(j+100)+f]={name=name,variant=0,metadata=d.metadata,updateScript={fileName=d.updateScript.fileName,params=d.updateScript.params}}
  end
  add(0,1,50,'pedestrian_entrance');add(-1,1,50,'pedestrian_entrance');add(-1,0,53,'passenger_dock_25_25');add(0,-2,4,'passenger_dock_50_12');add(0,-3,36,'small_pier');args.z=2
 end
 if task.kind=='water_depot'or task.kind=='water_maintenance'or task.kind=='harbor'then
  args.z=assert(api.engine.getComponent(api.engine.util.getWorld(),CT.TERRAIN),'Missing terrain').waterLevel+2
 end
 local ce=api.type.SimpleProposal.ConstructionEntity.new();ce.fileName=resource;ce.params=params;ce.playerEntity=api.engine.util.getPlayer();ce.name=task.id
 local V=api.type.Vec4f.new;local a=math.rad(args.rotation)
 ce.transf=api.type.Mat4f.new(V(math.cos(a),math.sin(a),0,0),V(-math.sin(a),math.cos(a),0,0),V(0,0,1,0),V(args.x,args.y,args.z,1))
 proposal=api.type.SimpleProposal.new();proposal.constructionsToAdd={ce}
 context=api.type.Context.new();context.checkTerrainAlignment=true;context.player=api.engine.util.getPlayer()
 local pd=api.engine.util.proposal.makeProposalData(proposal,context)
 local blocking,waterContacts={},{}
 for _,c in ipairs(pd.collisionInfo.collisionEntities)do
  if (task.kind=='harbor'or task.kind=='water_depot')and api.engine.getComponent(c.entity,CT.WATER_MESH)then waterContacts[#waterContacts+1]=c.entity else blocking[#blocking+1]=c.entity end
 end
 preview={waterSurfaceContacts=waterContacts,blockingCollisions=blocking,ok=not pd.errorState.critical and #blocking==0,critical=pd.errorState.critical,infos=B.toPlain(pd.errorState.infos),warnings=B.toPlain(pd.errorState.warnings),collisions=(function()local r={};for _,c in ipairs(pd.collisionInfo.collisionEntities)do r[#r+1]=c.entity end;return r end)(),messages=B.toPlain(pd.errorState.messages),reputation=B.previewReputation(proposal,pd)}
else preview=B.commands[task.command](args)end
local check=preview.check or preview
local safe=check.ok==true and not check.critical and not check.blocked
-- Native placement constraints (including coastline) are returned in infos.
if check.infos and #check.infos>0 then safe=false end
if check.messages and #check.messages>0 then safe=false end
if check.warnings and #check.warnings>0 then safe=false end
-- Native infos, messages and warnings must all be checked above, in addition to geometry.
if task.kind=='harbor'then
 -- Fixed native one-small-pier template: AddSlot(0,-3,36), grid 12.5.
 -- Local pier center = (0,-29.375); entrances are on the landward side.
 local a=math.rad(task.rotation or 0);local samples={};local valid=task.shoreline_revision=='native_small_pier_v1'
 for _,v in ipairs({{0,-29.375,true},{-20,-29.375,true},{20,-29.375,true},{0,13.75,false}})do
  local x=args.x+v[1]*math.cos(a)-v[2]*math.sin(a);local y=args.y+v[1]*math.sin(a)+v[2]*math.cos(a)
  local p=api.type.Vec2f.new(x,y);local water=api.engine.terrain.isOnWater(p);local h=api.engine.terrain.getHeightAt(p)
  samples[#samples+1]={x=x,y=y,water=water,height=h,expectedWater=v[3]};valid=valid and water==v[3]
 end
 preview.shorelineSamples=samples;preview.shorelinePlacementVerified=valid;preview.geometryPreviewPassed=safe
 if not valid then preview.blockedReason='native pier must be in water and entrance on land';safe=false end
end
if task.kind=='water_maintenance'then
 local a=math.rad(args.rotation)
 -- The water-obstacle collider may straddle shore; it is not a submerged-area requirement.
 local q=api.type.Vec2f.new(args.x+40*math.sin(a),args.y-40*math.cos(a))
 local rear=api.type.Vec2f.new(args.x-40*math.sin(a),args.y+40*math.cos(a))
 preview.shorelineSamplingPassed=api.engine.terrain.isOnWater(q)and not api.engine.terrain.isOnWater(rear)
 preview.shorelinePlacementVerified=preview.shorelineSamplingPassed and safe
 safe=safe and preview.shorelinePlacementVerified
end
if task.kind=='water_depot'then
 local a=math.rad(task.rotation or 0);local p=api.type.Vec2f.new(args.x+40*math.sin(a),args.y-40*math.cos(a));local land=api.type.Vec2f.new(args.x,args.y)
 local dry=0
 -- Native water_depot collidersForWaterObstacles: BOX center (0,-30), half-extents (15,25).
 for u=-15,15,2.5 do for v=-55,-5,2.5 do
  local q=api.type.Vec2f.new(args.x+u*math.cos(a)-v*math.sin(a),args.y+u*math.sin(a)+v*math.cos(a));if not api.engine.terrain.isOnWater(q)then dry=dry+1 end
 end end
 local rear=api.type.Vec2f.new(args.x-40*math.sin(a),args.y+40*math.cos(a))
 preview.waterColliderDrySamples=dry;preview.shorelinePlacementVerified=api.engine.terrain.isOnWater(p)and dry==0 and not api.engine.terrain.isOnWater(rear)
 preview.waterPoint={x=p.x,y=p.y,height=api.engine.terrain.getHeightAt(p)};preview.shorelineSamplingPassed=preview.shorelinePlacementVerified;preview.nativePlacementClear=#(preview.infos or {})==0 and #(preview.messages or {})==0 and #(preview.warnings or {})==0;preview.shorelinePlacementVerified=preview.shorelineSamplingPassed and preview.nativePlacementClear;safe=safe and preview.shorelinePlacementVerified
 if not safe then preview.blockedReason='Native placement infos/messages/warnings, collision, or shoreline sampling failed' end
end
if action=='preview'or not safe then return B.json.encode({preview=preview,previewPassed=safe,built=false})end
local result
if proposal then
 local success=false;local errors={}
 api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(proposal,context,false,true),function(res,ok)
  success=ok==true
  if res.resultProposalData then errors=B.toPlain(res.resultProposalData.errorState.messages)end
 end)
 result={built=success,messages=errors}
elseif preview.preview_token then result=B.commands.commit_facility({preview_token=preview.preview_token})
else args.preview=false;result=B.commands[task.command](args)end
local after=scan()
return B.json.encode({preview=preview,previewPassed=safe,commit=result,audit=after and audit(after)or nil})
