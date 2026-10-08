return function(args,B)
 local CT=api.type.ComponentType;local pts=args.path;local n=#pts
 local function vec(p)return api.type.Vec3f.new(p.x,p.y,p.z)end
 local function dir(a,b)local x,y,z=b.x-a.x,b.y-a.y,b.z-a.z;local d=math.sqrt(x*x+y*y);return {x=x/d,y=y/d,z=z/d},d end
 local dirs,lens,tans={},{},{}
 for i=1,n do dirs[i],lens[i]=dir(pts[i],pts[i%n+1]) end
 for i=1,n do local a,b=dirs[(i-2)%n+1],dirs[i];local x,y=a.x+b.x,a.y+b.y;local d=math.sqrt(x*x+y*y);tans[i]={x=x/d,y=y/d,z=(a.z+b.z)/2} end
 local name='::/infrastructure/street/town/town_new_large.street_template'
 local tpl=api.res.streetTemplateRep.get(api.res.streetTemplateRep.find(name))
 local p=api.type.SimpleProposal.new();local nodes,edges={},{}
 for i=1,n do local v=api.type.NodeAndEntity.new();v.entity=-i;v.comp.position=vec(pts[i]);nodes[#nodes+1]=v end
 for i=1,n do local j=i%n+1;local e=api.type.SegmentAndEntity.new();e.entity=-n-i;e.type=0;local c=e.comp
  c.node0=-i;c.node1=-j;c.position0=vec(pts[i]);c.position1=vec(pts[j]);local a,b=tans[i],tans[j];local l=lens[i]
  c.tangent0=vec({x=a.x*l,y=a.y*l,z=a.z*l});c.tangent1=vec({x=b.x*l,y=b.y*l,z=b.z*l})
  c.type=api.type.enum.BaseEdgeType.NORMAL;c.typeIndex=-1
  if pts[i].z-pts[i].h>6 or pts[j].z-pts[j].h>6 then c.type=api.type.enum.BaseEdgeType.BRIDGE;c.typeIndex=1 end
  c.laneConfigs=tpl.laneConfigs;c.roadTemplate=name;c.roadStyle=tpl.streetStyle;c.roadType=api.type.enum.RoadType.STREET;edges[#edges+1]=e
 end
 p.streetProposal.nodesToAdd=nodes;p.streetProposal.edgesToAdd=edges
 local pd=api.engine.util.proposal.makeProposalData(p,nil)
 local out={built=false,segments=n,cost=pd.costs,critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),warnings=B.toPlain(pd.errorState.warnings),collisions={}}
 for _,v in ipairs(pd.collisionInfo.collisionEntities) do out.collisions[#out.collisions+1]=v.entity end
 out.buildable=not out.critical and #out.collisions==0
 if args.apply then
  assert(out.buildable,'ring preview rejected')
  api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(p,nil,false,true),function(res,ok)
   out.built=ok;out.nodes={};out.edges={}
   if ok then for _,v in ipairs(res.proposal.proposal.addedNodes) do out.nodes[#out.nodes+1]=v.entity end
    for _,v in ipairs(res.proposal.proposal.addedSegments) do out.edges[#out.edges+1]=v.entity end
   end
  end)
 end
 return B.json.encode(out)
end
