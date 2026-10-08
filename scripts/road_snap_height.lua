-- Align roadside construction height to the freshly resolved straight frontage.
-- Geometry is validated offline; native collision/alignment preview remains mandatory.
local function roadsideHeight(f,p)
 if not f.roadSnap then return p end
 local target=point(f.roadSnap.roadPoint);local CT=api.type.ComponentType
 local height=nil
 for _,id in ipairs(spec.existingRoadEntities or{})do
  local e=api.engine.getComponent(id,CT.BASE_EDGE)
  if e then
   local a=api.engine.getComponent(e.node0,CT.BASE_NODE).position
   local z=api.engine.getComponent(e.node1,CT.BASE_NODE).position
   local dx,dy=z.x-a.x,z.y-a.y;local length=dx*dx+dy*dy
   if length>0 then local u=((target.x-a.x)*dx+(target.y-a.y)*dy)/length
    local error=(target.x-a.x-u*dx)^2+(target.y-a.y-u*dy)^2
    if u>=-0.001 and u<=1.001 and error<0.01 then
     local h=a.z+u*(z.z-a.z)
     assert(not height or math.abs(height-h)<0.05,'Inconsistent snap road heights')
     height=h
    end
   end
  end
 end
 assert(height,'Fresh frontage missing for roadside facility')
 p.z=height
 return p
end
