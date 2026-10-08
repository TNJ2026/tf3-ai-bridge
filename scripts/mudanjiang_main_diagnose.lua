local out={}
local routes={{{node=75674},{x=332,y=-3168}},{{x=332,y=-3168},{x=-868,y=-4168}},{{x=-868,y=-4168},{node=48615}},{{x=-868,y=-4000},{node=48612}}}
for i,r in ipairs(routes) do out[i]=B.commands.build_road({start=r[1],['end']=r[2],street_type='country/country_new_medium',preview=true});out[i].path=nil end
return B.json.encode(out)
