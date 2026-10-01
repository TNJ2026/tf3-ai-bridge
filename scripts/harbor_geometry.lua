local modules={}
local function add(i,j,f,n)
 local name='::/stations/water/'..n..'.module';local id=api.res.moduleRep.find(name);assert(id>=0,name)
 local d=api.res.moduleRep.get(id)
 modules[1000000*(i+100)+100*(j+100)+f]={name=name,variant=0,metadata=d.metadata,updateScript={fileName=d.updateScript.fileName,params=d.updateScript.params}}
end
add(0,1,50,'pedestrian_entrance');add(-1,1,50,'pedestrian_entrance');add(-1,0,53,'passenger_dock_25_25');add(0,-2,4,'passenger_dock_50_12');add(0,-3,36,'small_pier')
local params={seed=1,year=B.commands.get_game_state({}).date.year,modules=modules}
local r=api.engine.util.construction.getConstructionResult('::/stations/water/harbor_modular.con',0,params)
local subs={};for _,s in ipairs(r.subconstructions) do subs[#subs+1]={station=B.toPlain(s.station),transportNetwork=B.toPlain(s.transportNetwork)} end
return B.json.encode({params=B.toPlain(params),subconstructions=subs})
