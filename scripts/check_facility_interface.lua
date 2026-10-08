local result={catalog={},facilities=B.commands.list_facilities({}),configs={}}
for _,kind in ipairs({"construction","metaConstruction","module"}) do
 result.catalog[kind]=B.commands.list_facility_resources({kind=kind,limit=200})
end
for _,f in ipairs(result.facilities.items) do
 result.configs[#result.configs+1]=B.commands.get_facility_config({entity=f.entity})
end
-- Validate one extension structurally; configure_facility never constructs a native proposal.
for _,c in ipairs(result.configs) do
 if c.category=="warehouse" then
  for _,s in ipairs(c.slots) do
   if not c.params.modules[s.id] then
    for _,m in ipairs(c.compatible_modules) do
     if m.type==s.type and m.available then
      result.structural_preview=B.commands.configure_facility({entity=c.entity,modules={{slot=s.id,resource=m.resource}}})
      result.after=B.commands.get_facility_config({entity=c.entity})
      return B.json.encode(result)
     end
    end
   end
  end
 end
end
return B.json.encode(result)
