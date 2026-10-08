"""Explicit test submission of an already recorded joint preview; never retries."""
import argparse,asyncio,json,time
from pathlib import Path
from batch_warehouses import Bridge,ROOT,batch_lock,write_json,StopBatch
from fullmap_batch import quote,save_signature
from fullmap_workflow import atomic_write

GUARD = '''
assert(not pd.errorState.critical,'Critical preview error')
for _,k in ipairs({'messages','warnings','infos'})do assert(#pd.errorState[k]==0,'Preview rejected: '..k)end
assert(#collisions==0,'Collision blocks submission')
local function key(n)return tostring(n.entity)..':'..tostring(n.index)end
local function reachable(start,goal,mode)
 local graph={}
 for _,net in pairs(pd.entity2tn)do for _,e in ipairs(net.edges)do if e.transportModes[mode]then
  local a,b=key(e.conns[1]),key(e.conns[2]);graph[a]=graph[a]or{};graph[a][b]=true
 end end end
 local queue,seen={},{};for k in pairs(start)do queue[#queue+1]=k;seen[k]=true end
 local i=1;while i<=#queue do local k=queue[i];i=i+1;if goal[k]then return true end
  for v in pairs(graph[k]or{})do if not seen[v]then seen[v]=true;queue[#queue+1]=v end end
 end;return false
end
local paths={}
for _,role in ipairs({'bus','truck'})do
 if spec.portBindings[role]then
 local mode=role=='bus'and 3 or 4;local a,b={},{}
 for id,net in pairs(pd.entity2tn)do
  local hasBus,hasLoad,hasCar=false,false,false
  for _,e in ipairs(net.edges)do hasBus=hasBus or e.transportModes[3];hasLoad=hasLoad or e.transportModes[role=='bus'and 0 or 1];hasCar=hasCar or e.transportModes[2]end
  local station=hasBus and hasLoad and not hasCar
  local road=false;for _,r in ipairs(spec.roads)do if r.entity==id then road=true end end
  for _,e in ipairs(net.edges)do if e.transportModes[mode]then for _,n in ipairs(e.conns)do
   if station then a[key(n)]=true end;if road then b[key(n)]=true end
  end end end
 end
 paths[role]={outbound=reachable(a,b,mode),inbound=reachable(b,a,mode)}
 assert(paths[role].outbound and paths[role].inbound,'Vehicle preview path failed: '..role)
 end
end
if spec.portBindings.road_depot then
 local port=spec.portBindings.road_depot.nativeEntranceNode
 assert(port,'Depot port not bound')
 paths.road_depot={}
 for _,mode in ipairs({2,3,4})do
  local a,b={},{}
  for id,net in pairs(pd.entity2tn)do
   local road=false;for _,r in ipairs(spec.roads)do if r.entity==id then road=true end end
   for _,e in ipairs(net.edges)do if e.transportModes[mode]then for _,n in ipairs(e.conns)do
    if n.entity==port then a[key(n)]=true end;if road then b[key(n)]=true end
   end end end
  end
  local valid=reachable(a,b,mode)and reachable(b,a,mode)
  paths.road_depot[tostring(mode)]=valid;assert(valid,'Depot preview path failed')
 end
end
local CT=api.type.ComponentType
local function inventory()
 local ids={constructions={},edges={},nodes={}}
 api.engine.forEachEntityWithComponent(function(id)ids.constructions[id]=true end,CT.CONSTRUCTION)
 for node,segments in pairs(api.engine.system.streetSystem.getNode2SegmentMap())do
  ids.nodes[node]=true;for _,id in pairs(segments)do ids.edges[id]=true end
 end
 return ids
end
local before=inventory()
local callback={received=false}
api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(proposal,context,false,true),function(res,ok)
 callback.received=true;callback.success=ok==true
 if res and res.resultProposalData then callback.errors=B.toPlain(res.resultProposalData.errorState)end
end)
local added={constructions={},edges={},nodes={}}
for k,ids in pairs(inventory())do
 for id in pairs(ids)do if not before[k][id]then added[k][#added[k]+1]=id end end
end
return B.json.encode({callback=callback,added=added,previewPaths=paths,portBindings=spec.portBindings})
'''

async def main():
 p=argparse.ArgumentParser();p.add_argument('--preview',required=True,type=Path);a=p.parse_args();out=a.preview
 receipt=json.loads((out/'receipt.json').read_text('utf8'));result=json.loads((out/'result.json').read_text('utf8'))
 if (out/'commit_receipt.json').exists():raise StopBatch('Submission already attempted; read back, never replay')
 es=result['errorState']
 if es['critical']or any(es[k]for k in ('messages','warnings','infos'))or result['collisions']:raise StopBatch('Recorded preview not clear')
 b=Bridge();assert b.heartbeat().get('connected')
 source=(ROOT/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text('utf8')
 pre='local env=setmetatable({},{__index=_G});local B=assert(load([========['+source+']========],"=joint_commit_test","t",env))()._internal;'
 async def call(code,engine=True):
  r=await b.call('eval',{'code':code},engine=engine,timeout=45);return json.loads(r)if isinstance(r,str)else r
 with batch_lock(b.dir):
  state=await call(pre+'return B.json.encode(B.commands.get_game_state({}))');old=receipt['state']
  if state['speedup']!=0 or any(state[k]!=old[k]for k in ('world','player','gameTime'))or state['tickCount']<old['tickCount']:raise StopBatch('Session changed')
  backup=Path(receipt['backup']['path'])
  if list(save_signature(backup)or[])!=receipt['backup']['signature']:raise StopBatch('Backup changed/missing')
  code=(out/'attempt.lua').read_text('utf8').split('return B.json.encode({previewOnly=true')[0]
  assert 'sendCommand'not in code and 'local networks='in code
  check='local state=B.commands.get_game_state({});assert(state.speedup==0 and state.world=='+str(state['world'])+' and state.player=='+str(state['player'])+' and state.gameTime=='+str(state['gameTime'])+',"Session changed");'
  code=check+code+GUARD;atomic_write(out/'commit_attempt.lua',code)
  audit={'attempted':True,'time':time.time(),'state':state,'outcome':'pending','backup':str(backup)};write_json(out/'commit_receipt.json',audit)
  try:
   r=await call(pre+code);write_json(out/'commit_result.json',r);audit['outcome']='returned';write_json(out/'commit_receipt.json',audit);print(json.dumps(r))
  except BaseException as e:
   audit.update(outcome='unknown_or_error',error=str(e));write_json(out/'commit_receipt.json',audit);raise
if __name__=='__main__':asyncio.run(main())
