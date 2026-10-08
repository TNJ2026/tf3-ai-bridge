local CT=api.type.ComponentType;local out={count=0,issues={},samples={}}
for _,id in ipairs(api.engine.getEntitiesWithComponent(CT.SIM_PERSON)) do
 local p=api.engine.getComponent(id,CT.SIM_PERSON);out.count=out.count+1
 if #out.samples<2 then out.samples[#out.samples+1]={id=id,dest=B.toPlain(p.destinations),target=p.targetOrAtEntity} end
 for _,d in ipairs(p.destinations) do if d>=0 then
 if not api.engine.entityExists(d) then out.issues[#out.issues+1]={person=id,entity=d,kind='missing_destination'}
 elseif not api.engine.getComponent(d,CT.PERSON_CAPACITY) then out.issues[#out.issues+1]={person=id,entity=d,kind='destination_without_capacity'} end
 end end
end
return B.json.encode(out)
