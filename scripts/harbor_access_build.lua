local a={start={node=70826},['end']={x=1915,y=-2082},street_type='town/town_old_small',max_segment_length=50,preview=true}
local p=B.commands.build_road(a);assert(p.buildable and #p.collisions==0 and #p.messages==0,'road preview rejected')
a.preview=false
return B.json.encode(B.commands.build_road(a))
