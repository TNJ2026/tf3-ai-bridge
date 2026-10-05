-- Request-local read index. Never injected into a build operation.
local facilityReadIndex={constructions={},warehouses={}}
local CT=api.type.ComponentType
api.engine.forEachEntityWithComponent(function(id)
 local c=api.engine.getComponent(id,CT.CONSTRUCTION)
 local rows=facilityReadIndex.constructions[c.fileName]or{}
 rows[#rows+1]={id=id,component=c};facilityReadIndex.constructions[c.fileName]=rows
end,CT.CONSTRUCTION)
api.engine.forEachEntityWithComponent(function(id)
 local w=api.engine.getComponent(id,CT.WAREHOUSE)
 local ids=facilityReadIndex.warehouses[w.construction]or{}
 ids[#ids+1]=id;facilityReadIndex.warehouses[w.construction]=ids
end,CT.WAREHOUSE)
