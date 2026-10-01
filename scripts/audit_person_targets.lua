local CT=api.type.ComponentType;local out={bad={},types={},missing={},pcTypes={}}
for _,id in ipairs(api.engine.getEntitiesWithComponent(CT.SIM_PERSON)) do local p=api.engine.getComponent(id,CT.SIM_PERSON);local d=p.targetOrAtEntity
 if d>=0 then if not api.engine.entityExists(d) then out.missing[#out.missing+1]={person=id,target=d} else local c=api.engine.getComponent(d,CT.PERSON_CAPACITY);if not c then out.bad[#out.bad+1]={person=id,target=d,atBuilding=api.engine.getComponent(id,CT.SIM_ENTITY_AT_BUILDING)~=nil} else out.pcTypes[tostring(c.type)]=(out.pcTypes[tostring(c.type)] or 0)+1 end end end end
return B.json.encode(out)
