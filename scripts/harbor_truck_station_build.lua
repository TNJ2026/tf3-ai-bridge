local a={x=1870,y=-1940,rotation=0,cargo=true,size=1,connect=false,preview=true,name='牡丹江南岸码头接驳站'}
local p=B.commands.build_station(a);assert(p.ok and not p.critical and #p.collisions==0 and #p.messages==0,'station preview rejected')
a.preview=false
local out=B.commands.build_station(a)
if out.construction then out.entity=B.commands.get_entity({id=out.construction}) end
return B.json.encode(out)
