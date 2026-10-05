"""Inspect current headquarters proposal pedestrian links without building."""
import argparse,asyncio,json
from pathlib import Path
from batch_warehouses import Bridge,ROOT,batch_lock,write_json
from fullmap_batch import quote
async def main():
    ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    raise RuntimeError('Disabled after native access violation on 2026-10-05 12:09:26. Do not replay on a live save. Evidence: exports/newmap_20261005/crash_120926/')
    p=json.loads(a.plan.read_text('utf8'));hq=next(f for f in p['facilities'] if f['id']=='HQ')
    b=Bridge();assert b.heartbeat().get('connected')
    src=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8')
    pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+src+']========],"=hq_access","t",env))()._internal;'
    code='''local args=B.json.decode(ARGS);local r=B.commands.build_headquarters(args)
if r.blocked then return B.json.encode({blocked=true,check=r.check})end
local V=api.type.Vec4f.new;local a=math.rad(args.rotation);local ce=api.type.SimpleProposal.ConstructionEntity.new()
ce.fileName=r.resource;ce.params=r.params;ce.playerEntity=api.engine.util.getPlayer();ce.name='HQ preview'
ce.transf=api.type.Mat4f.new(V(math.cos(a),math.sin(a),0,0),V(-math.sin(a),math.cos(a),0,0),V(0,0,1,0),V(args.x,args.y,args.z,1))
local proposal=api.type.SimpleProposal.new();proposal.constructionsToAdd={ce};local ctx=api.type.Context.new();ctx.player=api.engine.util.getPlayer();ctx.checkTerrainAlignment=true
local pd=api.engine.util.proposal.makeProposalData(proposal,ctx)
return B.json.encode({check=r.check,params=r.params,links=B.toPlain(pd.tpNetLinkProposal),networks=B.toPlain(pd.entity2tn),addData=B.toPlain(pd.toAddData)})'''.replace('ARGS',quote({k:v for k,v in hq['args'].items() if k!='connect'}))
    with batch_lock(b.dir):
        r=await b.call('eval',{'code':pre+code},engine=True,timeout=30)
        if isinstance(r,str):r=json.loads(r)
        write_json(a.output,r)
        print(json.dumps({'check':r.get('check'),'links':r.get('links'),'networks':r.get('networks')},ensure_ascii=True)[:5000])
if __name__=='__main__':asyncio.run(main())
