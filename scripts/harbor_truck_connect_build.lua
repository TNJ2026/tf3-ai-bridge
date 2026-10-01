local a={start={node=105189},['end']={node=70827},street_type='town/town_old_small',max_segment_length=50,preview=true}
local p=B.commands.build_road(a);assert(p.buildable and #p.collisions==0 and #p.messages==0,'preview rejected');a.preview=false
return B.json.encode(B.commands.build_road(a))
