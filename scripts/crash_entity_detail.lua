local out={};for _,id in ipairs({76059,76286,62237}) do out[tostring(id)]=B.commands.get_entity({id=id}) end
return B.json.encode(out)
