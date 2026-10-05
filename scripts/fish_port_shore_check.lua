-- Geometry screen only. Native proposal remains authoritative; no water collision bypass.
local shoreline={}
for _,f in ipairs(spec.facilities)do
 if f.role=='harbor'or f.role=='water_maintenance'or f.role=='water_depot'then
  local p=point(f.localPosition,f.heightPolicy);local a=angle+math.rad(f.relativeRotation)
  local function sample(u,v,expected)
   local q=api.type.Vec2f.new(p.x+u*math.cos(a)-v*math.sin(a),p.y+u*math.sin(a)+v*math.cos(a))
   local water=api.engine.terrain.isOnWater(q)
   assert(water==expected,'Fish port shoreline mismatch: '..f.role)
   shoreline[#shoreline+1]={role=f.role,x=q.x,y=q.y,water=water}
  end
  if f.role=='harbor'then
   sample(0,-29.375,true);sample(-20,-29.375,true);sample(20,-29.375,true);sample(0,13.75,false)
  else
   -- collidersForWaterObstacles describes navigation obstacles, not a placement
   -- requirement that the entire collider be submerged. Keep the native water
   -- point and a conservative rear-land screen; native preview decides validity.
   sample(0,-40,true)
   sample(0,40,false)
  end
 end
end
