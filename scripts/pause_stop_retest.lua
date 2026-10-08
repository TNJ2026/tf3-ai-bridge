local out={before=B.commands.get_game_state()}
B.commands.set_game_speed({speed=0},function(ok,r)out.paused=ok end)
out.after=B.commands.get_game_state();assert(out.after.speedup==0,'pause failed')
return B.json.encode(out)
