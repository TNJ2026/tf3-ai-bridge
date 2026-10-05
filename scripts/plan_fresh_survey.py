"""Read-only refinement of selected collections, roads and coastal terrain."""
import argparse,asyncio,json,math
from pathlib import Path
from batch_warehouses import Bridge,ROOT,batch_lock,write_json
from fullmap_batch import quote
from tf3_mcp.flat_areas import FlatTerrain

async def main():
    ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    plan=json.loads(a.plan.read_text('utf8'));b=Bridge();assert b.heartbeat().get('connected')
    src=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8')
    pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+src+']========],"=fresh_survey","t",env))()._internal;'
    async def read(code):
        r=await b.call('eval',{'code':pre+'assert(api.engine.util.getPlayer()=='+str(plan['session']['player'])+',"Map changed");'+code},engine=True,timeout=45)
        return json.loads(r) if isinstance(r,str) else r
    summary=[]
    with batch_lock(b.dir):
        for h in plan['hubs']:
            bounds=json.loads(json.dumps(h['terrain_screen']['reserveBounds']))
            roads=[r for r in plan['roads'] if r['id'] in h['roads']]
            for side,fn,margin in [('min',min,-25),('max',max,25)]:
                for axis in ('x','y'):bounds[side][axis]=fn([bounds[side][axis]]+[v[axis] for r in roads for v in r['path']])+margin
            args={'bounds':bounds,'spacing':25}
            s=await read('return B.json.encode(B.commands.get_planning_snapshot(B.json.decode('+quote(args)+')))')
            assert s['scope']=='local' and s['grid']['spacing']==25,'Survey args were not applied; stop batch'
            write_json(a.output/(h['owner']+'.json'),s)
            flat=FlatTerrain(s['grid']);profile=flat.profile(h['terrain_screen']['reserveBounds'])
            summary.append({'owner':h['owner'],'bounds':bounds,'samples':len(s['grid']['heights']),'terrain':profile,'snapshot':str((a.output/(h['owner']+'.json')).resolve())})
        # Entire coastal collection and its upgrade water/land envelope.
        for p in plan['ports']:
            pos=p['position'];bounds={side:{axis:pos[axis]+offset for axis in ('x','y')} for side,offset in [('min',-400),('max',400)]}
            s=await read('return B.json.encode(B.commands.get_planning_snapshot(B.json.decode('+quote({'bounds':bounds,'spacing':5})+')))')
            assert s['scope']=='local' and s['grid']['spacing']==5,'Coastal survey args were not applied; stop batch'
            write_json(a.output/(p['id']+'.json'),s)
        write_json(a.output/'summary.json',{'previewOnly':True,'worldMutations':0,'collections':summary})
    print(json.dumps({'collections':len(summary),'coasts':len(plan['ports']),'samples':sum(x['samples']for x in summary)}))

if __name__=='__main__':asyncio.run(main())
