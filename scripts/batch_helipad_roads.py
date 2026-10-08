"""Survey and connect current helipads to unconfigured public street nodes."""
import asyncio
import argparse
import json
import math
import sys
from pathlib import Path
from batch_warehouses import ROOT, PLAN, Runner, Bridge, StopBatch, batch_lock, write_json, pose_matches
from batch_connections import road_preview_ok
from batch_helipads import land_tasks, RESOURCE

SURVEY = '''local CT=api.type.ComponentType;local out={facilities={},nodes={}}
api.engine.forEachEntityWithComponent(function(id)
 local c=api.engine.getComponent(id,CT.CONSTRUCTION)
 if c.fileName=="::/stations/air/helipad.con" then
  local v=c.transf:cols(3);local a=c.transf:cols(0);local b=c.transf:cols(1)
  local owner=api.engine.getComponent(id,CT.PLAYER_OWNED)
  out.facilities[#out.facilities+1]={entity=id,owner=owner and owner.player,x=v.x,y=v.y,z=v.z,ax=a.x,ay=a.y,bx=b.x,by=b.y}
 end
end,CT.CONSTRUCTION)
for _,id in ipairs(api.engine.util.octree.findEntitiesInCircle(api.type.Vec2f.new(0,0),12000,CT.BASE_NODE)) do
 local segs=api.engine.system.streetSystem.getNodeSegments(id)
 if #segs>0 then
  local owned=api.engine.system.streetConnectorSystem.getConstructionEntityForNode(id)
  local cfg=api.engine.getComponent(id,CT.BASE_NODE_CONFIG)
  if (not owned or owned<0) and (not cfg or (#segs==1 and #cfg.laneConnections==0)) then
   local p=api.engine.getComponent(id,CT.BASE_NODE).position
   local edge=api.engine.getComponent(segs[1],CT.BASE_EDGE)
   local rows={};for _,s in ipairs(segs) do rows[#rows+1]=s end
   local other=edge.node0==id and edge.position1 or edge.position0
   local tangent=edge.node0==id and edge.tangent0 or edge.tangent1
   local sign=edge.node0==id and -1 or 1
   local dx,dy=tangent.x*sign,tangent.y*sign;local len=math.sqrt(dx*dx+dy*dy)
   local ux,uy=0,0;if len>0 then ux,uy=dx/len,dy/len end
   out.nodes[#out.nodes+1]={id=id,x=p.x,y=p.y,z=p.z,edges=rows,streetType=edge.roadTemplate,ux=ux,uy=uy}
  end
 end
end
return out'''

def transform(site,x,y):
    return {'x':site['x']+site['ax']*x+site['bx']*y,'y':site['y']+site['ay']*x+site['by']*y}

def routes(site,node):
    # Front road in front of the native snap point (0,-25); reserve the remaining rear.
    dx,dy=node['x']-site['x'],node['y']-site['y']
    x=dx*site['ax']+dy*site['ay'];y=dx*site['bx']+dy*site['by']
    side=node.get("approach_side",-1 if x<0 else 1)
    approaches=[]
    approaches.append([transform(site,side*30,-35),transform(site,-side*30,-35)])
    approaches.append([transform(site,side*55,y),transform(site,side*55,-35),transform(site,-side*30,-35)])
    expanded=[]
    for points in approaches:
        expanded.append(points)
        if len(node.get('edges',[]))==1:
            lead={'x':node['x']+node.get('ux',0)*40,'y':node['y']+node.get('uy',0)*40}
            expanded.append([lead]+points)
            # Outside loop: preserve the old dead-end direction before coming back.
            for clearance in (100,180):
                front=transform(site,side*55,-clearance)
                expanded.append([lead,{'x':lead['x'],'y':front['y']},front,transform(site,side*55,-35),transform(site,-side*30,-35)])
            for clearance in (64,100,180):
                rear=transform(site,side*55,clearance)
                expanded.append([lead,{'x':lead['x'],'y':rear['y']},rear,transform(site,side*55,-35),transform(site,-side*30,-35)])
    if len(node.get('edges',[]))==1:
        start={'x':node['x'],'y':node['y']};finish=transform(site,side*55,-35)
        distance=math.hypot(finish['x']-start['x'],finish['y']-start['y'])
        control=max(100,min(350,distance*.8))
        p1={'x':start['x']+node.get('ux',0)*control,'y':start['y']+node.get('uy',0)*control}
        p2={'x':finish['x']+site['ax']*side*control,'y':finish['y']+site['ay']*side*control}
        curve=[]
        for j in range(1,17):
            t=j/16;u=1-t
            curve.append({axis:u**3*start[axis]+3*u*u*t*p1[axis]+3*u*t*t*p2[axis]+t**3*finish[axis] for axis in ('x','y')})
        expanded.append(curve+[transform(site,-side*30,-35)])
    for points in expanded:
        chain=[{'x':node['x'],'y':node['y']}]+points
        # Remove coincident points before native proposal creation.
        clean=[chain[0]]
        for p in chain[1:]:
            if math.hypot(p['x']-clean[-1]['x'],p['y']-clean[-1]['y'])>=10: clean.append(p)
        if len(clean)<2: continue
        length=sum(math.hypot(a['x']-b['x'],a['y']-b['y']) for a,b in zip(clean,clean[1:]))
        yield length,{'start':{'node':node['id']},'via':clean[1:-1],'end':clean[-1],
                     'street_type':'country/country_new_small','snap_radius':0,'max_segment_length':50,'allow_collisions':False}

class HelipadRoadRunner(Runner):
    async def survey(self):
        return await self.call('eval',{'code':SURVEY})

    def site(self,task,survey):
        p=task['position']
        rows=[s for s in survey['facilities'] if math.hypot(s['x']-p['x'],s['y']-p['y'])<.1 and s['owner']==self.previous_state['player']]
        if len(rows)!=1: raise StopBatch('停机坪会话或位置不匹配')
        s=rows[0];a=math.radians(task.get('rotation',0))
        if abs(s['ax']-math.cos(a))>.001 or abs(s['ay']-math.sin(a))>.001: raise StopBatch('停机坪朝向改变')
        return s

    async def audit(self,site,edges):
        # Native automatic pedestrian/cargo links must actually touch the facility.
        code='''local CT=api.type.ComponentType;local target=TARGET
local out={links={},roads={},facilityNetworkEntities={}}
local function belongs(id)
 if id==target then return true end
 local c=api.engine.system.streetConnectorSystem.getConstructionEntityForSubconstruction(id)
 return c==target
end
local seen={}
for _,ids in pairs(api.engine.system.tpNetLinkSystem.getEdgeId2linkEntities()) do for _,id in ipairs(ids) do if not seen[id] then seen[id]=true
 local link=api.engine.getComponent(id,CT.TP_NET_LINK)
 local a,b=link.from.edgeId,link.to.edgeId
 if belongs(a.entity) or belongs(b.entity) then
  out.links[#out.links+1]={entity=id,fromEntity=a.entity,fromIndex=a.index,toEntity=b.entity,toIndex=b.index}
 end
end end end
for _,id in ipairs(EDGES) do
 local e=api.engine.getComponent(id,CT.BASE_EDGE)
 if e then out.roads[#out.roads+1]={entity=id,node0=e.node0,node1=e.node1} end
end
return out'''.replace('TARGET',str(site['entity'])).replace('EDGES','{'+','.join(str(int(e)) for e in edges)+'}')
        native=await self.call('eval',{'code':code})
        roadset=set(edges)
        linked=any(v['fromEntity'] in roadset or v['toEntity'] in roadset for v in native['links'])
        return {'geometryVerified':len(native['roads'])==len(edges) and bool(edges),
                'facilityRoadLinkVerified':linked,'native':native,'cargoCoverageVerified':False,'simulationVerified':False}

    async def run(self):
        await self.session()
        if any(i.get('commitAttempts',0) and i.get('status')!='connected' for i in self.ledger['items'].values()) and self.action=='build':
            raise StopBatch('存在未核实提交，不重复施工')
        survey=await self.survey()
        write_json(self.output/'survey.json',survey)
        # Avoid the known disconnected warehouse spur, even if its end looks free.
        blocked=json.loads((ROOT/'exports/supply_warehouse_20261002/road_batch/ledger.json').read_text(encoding='utf-8'))['items']['W2'].get('commit',{}).get('edges',[])
        nodes=[n for n in survey['nodes'] if not set(n['edges']).intersection(blocked)]
        if self.action=='build': await self.checkpoint('helipad_roads_before')
        for task in self.plan['warehouses']:
            key=task['warehouseId'];await self.session()
            current=await self.survey();site=self.site(task,current)
            item=self.ledger['items'].setdefault(key,{'name':task['name'],'commitAttempts':0})
            if item.get('commitAttempts'):
                audit=await self.audit(site,item.get('commit',{}).get('edges',[]));item['audit']=audit;self.flush()
                if not audit['geometryVerified'] or not audit['facilityRoadLinkVerified']: raise StopBatch(key+' 接入读回不匹配')
                continue
            if self.action=='verify': continue
            candidates=[]
            for n in current['nodes']:
                if set(n['edges']).intersection(blocked): continue
                distance=math.hypot(n['x']-site['x'],n['y']-site['y'])
                if 20<distance<1800:
                    for side in (-1,1):
                        candidate=dict(n,approach_side=side)
                        candidates.extend((length,args,n) for length,args in routes(site,candidate))
            candidates.sort(key=lambda c:c[0])
            item['rejected']=[];chosen=None
            for length,args,n in candidates[:100]:
                preview=await self.call('build_road',{**args,'preview':True})
                if road_preview_ok(preview): chosen=(args,n,preview,length);break
                item['rejected'].append({'input':args,'preview':preview});self.flush()
            if not chosen:
                item['status']='no_safe_route';self.flush();print(key+': 无可施工的接路候选',flush=True);continue
            args,n,preview,length=chosen
            item.update(status='preview_ready',input=args,site=site,anchor=n,preview=preview,length=length);self.flush()
            if self.action=='preview': print(key+': 预览通过',flush=True);continue
            await self.session();fresh=await self.survey()
            if self.site(task,fresh)!=site or n not in fresh['nodes']: raise StopBatch('道路或停机坪改变；重新调查')
            item.update(status='commit_started',commitAttempts=1);self.flush()
            try:
                result=await self.call('build_road',{**args,'preview':False});item['commit']=result;self.flush()
                if not all(result.get(k) is True for k in ('built','complete','verified')): raise StopBatch(key+' 道路生成但通行未确认，禁止重复建造')
                audit=await self.audit(site,result['edges']);item['audit']=audit;self.flush()
                if not audit['geometryVerified'] or not audit['facilityRoadLinkVerified']: raise StopBatch(key+' 设施原生道路连接未确认')
                item['status']='connected';self.flush();await self.checkpoint(key+'_road_after')
                print(key+': 道路双向通行与设施接入通过',flush=True)
            except Exception:
                item['status']='needs_reconciliation';self.flush();raise

async def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('preview','build','verify'))
    a=parser.parse_args();bridge=Bridge()
    runner=HelipadRoadRunner(bridge,land_tasks(json.loads(PLAN.read_text(encoding='utf-8'))),ROOT/'exports/supply_warehouse_20261002/helipad_roads',a.action)
    try:
        with batch_lock(bridge.dir): await runner.run()
    except Exception as error:
        runner.ledger['events'].append({'stopped':str(error)});runner.flush();print('停止：'+str(error),file=sys.stderr);return 2
    return 0

if __name__=='__main__': raise SystemExit(asyncio.run(main()))
