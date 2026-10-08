"""Bounded, read-only native maintenance shoreline diagnostic."""
import argparse, asyncio, json, math
from pathlib import Path
from fullmap_batch import Batch, StopBatch, batch_lock, quote, write_json

LUA = '''local rows=B.json.decode(CANDIDATES);local out={}
local state=B.commands.get_game_state({})
local water=api.engine.getComponent(api.engine.util.getWorld(),api.type.ComponentType.TERRAIN).waterLevel
for _,r in ipairs(rows)do
 local a=math.rad(r.rotation);local V=api.type.Vec4f.new
 local c=api.type.SimpleProposal.ConstructionEntity.new()
 c.fileName='::/depots/water/'..(r.resource or 'water_maint_station.con');c.params={year=state.date.year,seed=1,modules={}}
 c.name='JOINT_TEST water_maintenance';c.playerEntity=state.player
 c.transf=api.type.Mat4f.new(V(math.cos(a),math.sin(a),0,0),V(-math.sin(a),math.cos(a),0,0),V(0,0,1,0),V(r.x,r.y,water+(r.heightOffset or 2),1))
 local samples={};for _,v in ipairs({-50,-40,0,10,40})do
  local q=api.type.Vec2f.new(r.x-v*math.sin(a),r.y+v*math.cos(a))
  samples[#samples+1]={v=v,x=q.x,y=q.y,h=api.engine.terrain.getHeightAt(q),water=api.engine.terrain.isOnWater(q)}
 end
 local p=api.type.SimpleProposal.new();p.constructionsToAdd={c}
 local ctx=api.type.Context.new();ctx.player=state.player;ctx.checkTerrainAlignment=true
 local pd=api.engine.util.proposal.makeProposalData(p,ctx);local es=pd.errorState
 local collisions={};for _,v in ipairs(pd.collisionInfo.collisionEntities)do collisions[#collisions+1]=v.entity end
 out[#out+1]={candidate=r,samples=samples,errorState={critical=es.critical,infos=B.toPlain(es.infos),warnings=B.toPlain(es.warnings),messages=B.toPlain(es.messages)},collisions=collisions}
 if es.critical then break end
end
return B.json.encode(out)'''

async def execute(a):
    rows=json.loads(a.candidates.read_text('utf8'))
    if not 1<=len(rows)<=3:raise ValueError('Use 1..3 evidence-based candidates')
    for r in rows:
        if not all(math.isfinite(r[k]) for k in ('x','y','rotation')):raise ValueError('Finite coordinates required')
        if r.get('heightOffset',2) not in (0,2,4):raise ValueError('Diagnostic height outside reviewed bounds')
        if r.get('resource','water_maint_station.con') not in ('water_maint_station.con','water_depot.con'):raise ValueError('Unreviewed diagnostic resource')
    a.action='preview';a.ids=None;a.limit=0;a.output.mkdir(parents=True,exist_ok=True)
    receipt=a.output/'shore_probe_attempt.json'
    if receipt.exists():raise StopBatch('Already attempted; inspect saved evidence before redesign')
    b=Batch(a)
    with batch_lock(b.b.dir):
        state=await b.call('get_game_state',{})
        await b.save('shore_probe_before')
        write_json(receipt,{'attempted':True,'candidates':rows,'state':state})
        result=await b.eval(LUA.replace('CANDIDATES',quote(rows)))
        write_json(a.output/'shore_probe.json',result);b.flush()
        print(json.dumps(result,ensure_ascii=True))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('plan','output','candidates'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--isolated-test-save',action='store_true')
    asyncio.run(execute(p.parse_args()))
