local out={}
for _,r in ipairs({{name='east',via={{x=820,y=-1529.5},{x=820,y=-1320}},finish={x=818,y=-1244}},{name='west',via={{x=300,y=-1529.5},{x=300,y=-1320}},finish={x=318,y=-1244}}}) do
 out[r.name]=B.commands.build_road({start={node=59863},['end']=r.finish,via=r.via,street_type='country/country_new_medium',preview=true})
end
return B.json.encode(out)
