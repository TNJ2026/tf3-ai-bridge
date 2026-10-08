-- One engine read collects the whole planning corridor, including model-only depots.
commands.get_route_snapshot = function(args)
 local CT=api.type.ComponentType
 local spacing=roadNumber(args.spacing or 100,'spacing',25,250)
 local function revision(id) local r=api.engine.getRevision(id);return table.concat({r.num[1],r.num[2],r.num[3]},':') end
 local margin=roadNumber(args.margin or 1500,'margin',250,4000)
 local stations,ignore={},{}
 for _,id in ipairs({args.start_construction,args.end_construction}) do
  local c=api.engine.getComponent(id,CT.CONSTRUCTION)
  if not c then error('station construction does not exist: '..tostring(id),0) end
  local frozen,ports={},{}
  ignore[id]=true
  for _,n in ipairs(c.frozenNodes) do frozen[n]=true end
  for _,s in ipairs(c.stations) do ignore[s]=true end
  for _,eid in ipairs(c.frozenEdges) do
   ignore[eid]=true
   local e=api.engine.getComponent(eid,CT.BASE_EDGE)
   if e.roadType==api.type.enum.RoadType.TRACK then
    for _,n in ipairs({e.node0,e.node1}) do
     if not frozen[n] and #api.engine.system.streetSystem.getNodeSegments(n)==1 then
      local p=api.engine.getComponent(n,CT.BASE_NODE).position
      local t=e.node1==n and e.tangent1 or e.tangent0
      local sign=e.node1==n and 1 or -1
      local d=math.sqrt(t.x*t.x+t.y*t.y)
      ports[#ports+1]={node=n,edge=eid,position={x=p.x,y=p.y,z=p.z},direction={x=sign*t.x/d,y=sign*t.y/d}}
     end
    end
   end
  end
  stations[#stations+1]={construction=id,position=constructionPosition(id),ports=ports}
 end
 local a,b=stations[1].position,stations[2].position
 local bounds=api.engine.terrain.getBoundingBox()
 local x0=math.max(bounds.min.x,math.floor((math.min(a.x,b.x)-margin)/spacing)*spacing)
 local y0=math.max(bounds.min.y,math.floor((math.min(a.y,b.y)-margin)/spacing)*spacing)
 if args.whole_map then x0=bounds.min.x;y0=bounds.min.y;margin=math.max(bounds.max.x-bounds.min.x,bounds.max.y-bounds.min.y)*2 end
 local nx=math.floor((math.min(bounds.max.x,math.max(a.x,b.x)+margin)-x0)/spacing)+1
 local ny=math.floor((math.min(bounds.max.y,math.max(a.y,b.y)+margin)-y0)/spacing)+1
 if nx*ny>100000 then error('corridor exceeds 100000 terrain samples; increase spacing or reduce margin',0) end
 local grid={x=x0,y=y0,nx=nx,ny=ny,spacing=spacing,heights={},water={}}
 local terrainRevisions={}
 for id,r in pairs(api.engine.terrain.getTerrainEntityRevisions()) do terrainRevisions[tostring(id)]=table.concat({r.num[1],r.num[2],r.num[3]},':') end
 local domain=table.concat({x0,y0,nx,ny,spacing},':')
 local same=args.domain==domain and args.terrain_revisions~=nil
 if same then
  for id,r in pairs(terrainRevisions) do if args.terrain_revisions[id]~=r then same=false;break end end
  for id in pairs(args.terrain_revisions) do if not terrainRevisions[id] then same=false;break end end
 end
 if not same then
 for j=0,ny-1 do for i=0,nx-1 do
  local p=api.type.Vec2f.new(x0+i*spacing,y0+j*spacing)
  grid.heights[#grid.heights+1]=api.engine.terrain.getHeightAt(p)
  grid.water[#grid.water+1]=api.engine.terrain.isOnWater(p)
 end end
 else grid=nil end
 local cx,cy=x0+(nx-1)*spacing/2,y0+(ny-1)*spacing/2
 local radius=math.sqrt(((nx-1)*spacing)^2+((ny-1)*spacing)^2)/2+spacing
 local obstacles,seen,revisions={},{},{}
 for _,kind in ipairs({'BASE_EDGE','TOWN_BUILDING','STATION','VEHICLE_DEPOT','CONSTRUCTION','MODEL_INSTANCE_LIST'}) do
  for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(cx,cy),radius,CT[kind])) do
   if not seen[id] and not ignore[id] then
    seen[id]=true
    local rev=revision(id);revisions[tostring(id)]=rev
    if not args.revisions or args.domain~=domain or args.revisions[tostring(id)]~=rev then
    local bv=api.engine.getComponent(id,CT.BOUNDING_VOLUME)
    if bv then
     local lo,hi=bv.bbox.min,bv.bbox.max
     local vegetation=false
     local ml=api.engine.getComponent(id,CT.MODEL_INSTANCE_LIST)
     if kind=='MODEL_INSTANCE_LIST' and ml then
      vegetation=true
      for _,list in ipairs({ml.fatInstances,ml.thinInstances}) do for _,m in ipairs(list) do
       local name=api.res.modelRep.getName(m.modelId)
       if not name:find('/tree') and not name:find('/rock') and not name:find('/bush') then vegetation=false end
      end end
     end
     if not vegetation and hi.x>=x0 and hi.y>=y0 and lo.x<=x0+(nx-1)*spacing and lo.y<=y0+(ny-1)*spacing then
      local tb=api.engine.getComponent(id,CT.TOWN_BUILDING)
      local row={entity=id,kind=kind,town=tb and tb.town or nil,min={x=lo.x,y=lo.y,z=lo.z},max={x=hi.x,y=hi.y,z=hi.z}}
      if kind=='BASE_EDGE' then
       local e=api.engine.getComponent(id,CT.BASE_EDGE)
       row.node0=e.node0;row.node1=e.node1;row.roadType=e.roadType;row.roadTemplate=e.roadTemplate
       row.position0={x=e.position0.x,y=e.position0.y,z=e.position0.z};row.position1={x=e.position1.x,y=e.position1.y,z=e.position1.z}
       row.tangent0={x=e.tangent0.x,y=e.tangent0.y,z=e.tangent0.z};row.tangent1={x=e.tangent1.x,y=e.tangent1.y,z=e.tangent1.z}
      end
      obstacles[#obstacles+1]=row
     end
    end
    end
   end
  end
 end
 return {schema=2,domain=domain,revisions=revisions,terrainRevisions=terrainRevisions,delta=args.domain==domain and args.revisions~=nil,state=commands.get_game_state({}),stations=stations,grid=grid,obstacles=obstacles,
  consistency='single engine read; revalidate before construction',coverage='bounding boxes and sampled terrain; native preview required'}
end
ENGINE_COMMANDS.get_route_snapshot=true

