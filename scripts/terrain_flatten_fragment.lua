-- BEGIN TERRAIN FLATTEN ADAPTER
-- Kept as a source fragment for atomic installation into bridge.script.lua.
do
 local tickets,operations={},{}
 local serial=0
 local pending=nil
 local checkpoint=function()end
 -- Engine script modules may be reconstructed between events. Persist only plain
 -- data in the game-owned script state, never globals; GUI epoch invalidates tokens
 -- after reload. Keep unresolved operations across epochs for reconciliation.
 terrainStateBind=function(state,epoch)
  assert(type(epoch)=='string','terrain GUI session epoch required')
  local root=state:get() or {}
  local saved=root.terrainAdapter or {}
  tickets=saved.epoch==epoch and (saved.tickets or {}) or {}
  operations=saved.operations or {};serial=saved.serial or 0;pending=saved.pending
  checkpoint=function()
   local current=state:get() or {}
   current.terrainAdapter={epoch=epoch,tickets=tickets,operations=operations,serial=serial,pending=pending}
   state:set(current)
  end
  checkpoint()
 end
 local function signature(v)
  if type(v)~='table' then return tostring(v) end
  local keys={};for k in pairs(v)do keys[#keys+1]=k end
  table.sort(keys,function(a,b)return tostring(a)<tostring(b)end)
  local out={};for _,k in ipairs(keys)do out[#out+1]=tostring(k)..'='..signature(v[k])end
  return '{'..table.concat(out,',')..'}'
 end
 local function identity()
  local s=commands.get_game_state({})
  return {world=s.world,player=s.player,gameTime=s.gameTime,tickCount=s.tickCount}
 end
 local function sameSession(a,b)
  return a.world==b.world and a.player==b.player and b.gameTime>=a.gameTime and b.tickCount>=a.tickCount
 end
 local function capabilities()
  return {operation='flatten_rectangle',native_calibrated=true,
   native_preview_supported=false,commit_available=true,transition_supported=true,max_native_steps=256,
   reason='Rectangle and bounded smooth transition; native Proposal preview binding unavailable',
   native_api='Proposal.terrain.baseHeightMod',max_vertices=20000,
   verification='survey only; no native proposal sent'}
 end
 local function survey(args)
  assert(type(args.bounds)=='table' and type(args.bounds.min)=='table' and type(args.bounds.max)=='table','bounds.min/max required')
  local b={min={},max={}}
  for _,a in ipairs({'x','y'})do
   b.min[a]=roadNumber(args.bounds.min[a],'bounds.min.'..a)
   b.max[a]=roadNumber(args.bounds.max[a],'bounds.max.'..a)
   assert(b.max[a]>b.min[a] and b.max[a]-b.min[a]<=600,'flatten extent must be positive and <=600m per axis')
  end
  local z=roadNumber(args.target_height,'target_height')
  local width=roadNumber(args.transition_width or 0,'transition_width',0,128)
  local margin=16
  local grade=roadNumber(args.max_edge_grade or 0.10,'max_edge_grade',0.01,0.20)
  local limit=roadNumber(args.max_height_change or 10,'max_height_change',0.05,50)
  local res=api.engine.terrain.getBaseResolution()
  local sx,sy=roadNumber(res.x,'resolution.x',0.1,25),roadNumber(res.y,'resolution.y',0.1,25)
  local quantum=roadNumber(res.z,'resolution.z',0.001,1)
  local t=assert(getComponent(api.engine.util.getWorld(),'TERRAIN'),'terrain unavailable')
  assert(z>roadNumber(t.waterLevel,'water level')+1,'target must remain above water level + 1m')
  local flattened={min={x=math.floor(b.min.x/sx)*sx,y=math.floor(b.min.y/sy)*sy},
                   max={x=math.ceil(b.max.x/sx)*sx,y=math.ceil(b.max.y/sy)*sy}}
  assert(width==0 or width>=2*math.max(sx,sy),'transition width must span at least two base-grid cells')
  local modified={min={x=flattened.min.x-math.ceil(width/sx)*sx,y=flattened.min.y-math.ceil(width/sy)*sy},
                  max={x=flattened.max.x+math.ceil(width/sx)*sx,y=flattened.max.y+math.ceil(width/sy)*sy}}
  local area={min={x=modified.min.x-math.ceil(margin/sx)*sx,y=modified.min.y-math.ceil(margin/sy)*sy},
              max={x=modified.max.x+math.ceil(margin/sx)*sx,y=modified.max.y+math.ceil(margin/sy)*sy}}
  local map=api.engine.terrain.getBoundingBox()
  for _,a in ipairs({'x','y'})do assert(area.min[a]>=map.min[a] and area.max[a]<=map.max[a],'guard area outside map')end
  local nx=math.floor((area.max.x-area.min.x)/sx+.5)+1
  local ny=math.floor((area.max.y-area.min.y)/sy+.5)+1
  assert(nx*ny<=20000,'terrain vertex budget exceeded; reduce area')
  local cx,cy=(area.min.x+area.max.x)/2,(area.min.y+area.max.y)/2
  local radius=math.sqrt((area.max.x-area.min.x)^2+(area.max.y-area.min.y)^2)/2
  local obstacles,seen={},{}
  for _,kind in ipairs({'BASE_EDGE','BASE_NODE','TOWN_BUILDING','CONSTRUCTION','MODEL_INSTANCE_LIST'})do
   local ct=assert(api.type.ComponentType[kind],'missing component type: '..kind)
   for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(V2(cx,cy),radius,ct))do
    if not seen[id]then
     seen[id]=true
     local bv=getComponent(id,'BOUNDING_VOLUME')
     if not bv then obstacles[#obstacles+1]={entity=id,kind=kind,reason='unknown_bounds'}
     elseif bv.bbox.max.x>=area.min.x and bv.bbox.min.x<=area.max.x and bv.bbox.max.y>=area.min.y and bv.bbox.min.y<=area.max.y then
      obstacles[#obstacles+1]={entity=id,kind=kind,reason='inside_affected_area'}
     end
    end
   end
  end
  local points,blocked={},{}
  if #obstacles>0 then blocked[#blocked+1]='existing_entities_in_affected_area'end
  local cut,fill,maxChange,changed=0,0,0,0
  for j=0,ny-1 do for i=0,nx-1 do
   local x,y=area.min.x+i*sx,area.min.y+j*sy
   local v=V2(x,y);local h=roadNumber(api.engine.terrain.getBaseHeightAt(v),'base height')
   local surface=roadNumber(api.engine.terrain.getHeightAt(v),'surface height')
   local inside=x>=flattened.min.x and x<=flattened.max.x and y>=flattened.min.y and y<=flattened.max.y
   local dx=math.max(flattened.min.x-x,0,x-flattened.max.x)
   local dy=math.max(flattened.min.y-y,0,y-flattened.max.y)
   local distance=math.sqrt(dx*dx+dy*dy)
   local transition=not inside and width>0 and distance<width
   local expected=inside and z or h
   if transition then
    local t=distance/width;local weight=1-t*t*(3-2*t)
    expected=h+(z-h)*weight
    expected=math.floor(expected/quantum+.5)*quantum
   end
   local delta=expected-h
   if api.engine.terrain.isOnWater(v)~=false then blocked[#blocked+1]='water_or_unknown';break end
   if math.abs(surface-h)>0.25 then blocked[#blocked+1]='surface_base_difference_requires_review';break end
   if math.abs(delta)>limit then blocked[#blocked+1]='height_change_limit';break end
   if expected<=t.waterLevel+1 then blocked[#blocked+1]='water_clearance';break end
   points[#points+1]={x=x,y=y,before=h,surface_before=surface,expected=expected,inside=inside,transition=transition}
   if math.abs(delta)>quantum/2 then changed=changed+1 end
   maxChange=math.max(maxChange,math.abs(delta))
   cut=cut+math.max(0,-delta)*sx*sy;fill=fill+math.max(0,delta)*sx*sy
  end;if #blocked>0 and #points<nx*(j+1) then break end end
  local edgeGrade=0
  if #points==nx*ny then
   for j=0,ny-1 do for i=0,nx-1 do
    local a=points[j*nx+i+1]
    for _,step in ipairs({{1,sx,i+1<nx},{nx,sy,j+1<ny}})do
     if step[3]then local q=points[j*nx+i+1+step[1]]
      if a.inside~=q.inside or a.transition or q.transition then edgeGrade=math.max(edgeGrade,math.abs(a.expected-q.expected)/step[2])end
     end
    end
   end end
   if width>0 then
    for j=0,ny-2 do for i=0,nx-2 do
     local a,b,c,d=points[j*nx+i+1],points[j*nx+i+2],points[(j+1)*nx+i+1],points[(j+1)*nx+i+2]
     if a.transition or b.transition or c.transition or d.transition then
      local gx=math.max(math.abs(b.expected-a.expected),math.abs(d.expected-c.expected))/sx
      local gy=math.max(math.abs(c.expected-a.expected),math.abs(d.expected-b.expected))/sy
      edgeGrade=math.max(edgeGrade,math.sqrt(gx*gx+gy*gy))
     end
    end end
   end
   if edgeGrade>grade then blocked[#blocked+1]='edge_grade_requires_separate_transition_design'end
  end
  local patches={{bounds=flattened,height=z}}
  -- No mutable native grid accessor: a disjoint constant-height run per row.
  local last=nil
  for _,p in ipairs(points)do
   if p.transition and math.abs(p.expected-p.before)>quantum/2 then
    if last and last.height==p.expected and last.bounds.max.y==p.y and last.bounds.max.x+sx==p.x then
     last.bounds.max.x=p.x
    else
     last={bounds={min={x=p.x,y=p.y},max={x=p.x,y=p.y}},height=p.expected}
     patches[#patches+1]=last
    end
   else last=nil end
  end
  if #patches>256 then blocked[#blocked+1]='native_step_budget_exceeded_reduce_area_or_transition'end
  local revisions={}
  for id,r in pairs(api.engine.terrain.getTerrainEntityRevisions())do revisions[tostring(id)]={r.num[1],r.num[2],r.num[3]}end
  return {args={bounds=b,target_height=z,max_edge_grade=grade,max_height_change=limit,transition_width=width},area=area,flattened=flattened,modified=modified,patches=patches,
   resolution={x=sx,y=sy,z=quantum},nx=nx,ny=ny,points=points,blocked=blocked,obstacles=obstacles,
   revisions=signature(revisions),session=identity(),changed=changed,
   summary={native_steps=#patches,max_edge_grade=edgeGrade,vertices=nx*ny,changed_vertices=changed,max_height_change=maxChange,
    estimated_cut_m3=cut,estimated_fill_m3=fill,volume_basis='base-grid vertex estimate; not native cost'}}
 end
 commands.get_terrain_operation_capabilities=function()return capabilities()end
 commands.preview_flatten_terrain=function(args)
  local s=survey(args);local c=capabilities()
  local result={preview=true,bounds=s.args.bounds,affected_bounds=s.area,target_height=s.args.target_height,
   flattened_bounds=s.flattened,modified_bounds=s.modified,transition_width=s.args.transition_width,summary=s.summary,obstacles=s.obstacles,blockers=s.blocked,
   blocked=#s.blocked>0,validation='structural_only',native_preview=false,
   transition_supported=true,warning='Smoothstep transition uses bounded sequential native steps; partial failure stops without retry',
   commit_available=c.commit_available,capability=c,requires_post_operation_survey=true}
  if #s.blocked>0 or not c.commit_available or s.changed==0 then return result end
  for k,t in pairs(tickets)do if wallClock()-t.created>60 then tickets[k]=nil end end
  serial=serial+1;local token='terrain:'..tostring(wallClock())..':'..serial
  tickets[token]={survey=s,created=wallClock()};checkpoint();result.preview_token=token;result.expires_in_seconds=60
  return result
 end
 local function readback(op)
  local current=identity()
  if not sameSession(op.session,current)then
   return {operation_id=op.id,status='needs_reconciliation',verified=false,reason='session changed; inspect saved receipt',receipt=op.receipt}
  end
  local mismatches,maxError=0,0
  for _,p in ipairs(op.points)do
   local h=api.engine.terrain.getBaseHeightAt(V2(p.x,p.y))
   local err=math.abs(h-p.expected);maxError=math.max(maxError,err)
   if err>op.tolerance then mismatches=mismatches+1 end
  end
  local verified=op.callback==true and op.success==true and not op.error and mismatches==0 and (not op.total_steps or op.completed_steps==op.total_steps)
  if verified and pending==op.id then pending=nil;checkpoint() end
  return {operation_id=op.id,status=verified and 'verified' or 'needs_reconciliation',verified=verified,
   submitted=true,completed_steps=op.completed_steps,total_steps=op.total_steps,callback_received=op.callback,native_success=op.success,error=op.error,
   mismatched_vertices=mismatches,max_error_m=maxError,receipt=op.receipt,
   requires_fresh_snapshot=true,requires_fresh_facility_and_road_preview=true}
 end
 commands.commit_flatten_terrain=function(args)
  local token=args.preview_token;local ticket=tickets[token];tickets[token]=nil;checkpoint()
  assert(ticket,'unknown, consumed or reloaded terrain preview token')
  assert(not pending,'previous terrain operation needs reconciliation; do not resubmit')
  assert(wallClock()-ticket.created<=60,'terrain preview expired')
  assert(type(args.backup_save)=='string' and args.backup_save:match('^[%w_-]+$'),'backup_save slot required')
  local s=ticket.survey;assert(sameSession(s.session,identity()),'session changed')
  local fresh=survey(s.args)
  assert(#fresh.blocked==0,'terrain/obstacles changed or blocked; preview again')
  assert(s.revisions==fresh.revisions and signature(s.points)==signature(fresh.points),'terrain changed; preview again')
  local rx,ry=s.resolution.x,s.resolution.y
  local op={id=token,session=identity(),points=s.points,tolerance=s.resolution.z+0.025,
   callback=false,completed_steps=0,total_steps=#s.patches}
  op.receipt={operation_id=token,session=op.session,args=s.args,flattened_bounds=s.flattened,
   modified_bounds=s.modified,guard_bounds=s.area,patches=s.patches,
   backup_save=args.backup_save,expected_points=s.points,tolerance_m=op.tolerance}
  operations[token]=op;pending=token;checkpoint()
  for index,patch in ipairs(s.patches)do
   local f=patch.bounds
   local proposal=api.type.Proposal.new()
   proposal.terrain.baseHeightMod=api.type.GridVec2f.new(math.floor(f.min.x/rx+.5),math.floor(f.min.y/ry+.5),
    math.floor((f.max.x-f.min.x)/rx+.5)+1,math.floor((f.max.y-f.min.y)/ry+.5)+1,V2(patch.height,patch.height))
   op.callback=false;op.success=false;op.attempted_step=index;checkpoint()
   local ok,err=pcall(function()
    api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(proposal,nil,false,true),function(_,success)
     op.callback=true;op.success=success==true
    end)
   end)
   if not ok then op.error=tostring(err)end
   if not op.callback or not op.success then op.error=op.error or 'native step not confirmed'end
   if not op.error then
    for y=f.min.y,f.max.y,ry do for x=f.min.x,f.max.x,rx do
     local h=api.engine.terrain.getBaseHeightAt(V2(x,y))
     if type(h)~='number' or h~=h or math.abs(h-patch.height)>op.tolerance then op.error='native step readback mismatch'end
    end end
   end
   if op.error then checkpoint();break end
   op.completed_steps=index;checkpoint()
  end
  return readback(op)
 end
 commands.get_terrain_operation=function(args)
  local op=operations[args.operation_id]
  assert(op,'unknown operation; reconcile from saved receipt and terrain survey, never resubmit')
  return readback(op)
 end
 for _,name in ipairs({'get_terrain_operation_capabilities','preview_flatten_terrain','commit_flatten_terrain','get_terrain_operation'})do ENGINE_COMMANDS[name]=true end
end
-- END TERRAIN FLATTEN ADAPTER
