import json
from pathlib import Path
base=Path('scripts/stop_crosswalk_factory.lua').read_text();base=base[:base.index(' local pd=')]
base=base.replace(' p.streetProposal.edgesToAdd={e};p.streetProposal.edgesToRemove={id}', ' e.comp.objects={{-400000000,api.type.enum.EdgeObjectType.STOP_RIGHT},{-399999999,api.type.enum.EdgeObjectType.STOP_LEFT}}\n p.streetProposal.edgesToAdd={e};p.streetProposal.edgesToRemove={id}')
base=base.replace(' p.streetProposal.edgeObjectsToAdd={eo}',''' eo.params={year=1960,seed=0}
 local other=api.type.SimpleStreetProposal.EdgeObject.new();other.edgeEntity=-1;other.param=.5;other.oneWay=false;other.left=true;other.model=eo.model;other.playerEntity=eo.playerEntity;other.name=eo.name;other.params={year=1960,seed=0}
 p.streetProposal.edgeObjectsToAdd={eo,other}''')
base+='''
 local pd=api.engine.util.proposal.makeProposalData(p,nil)
 local tn=pd.entity2tn[-1];local modes={};local conns={}
 for _,e in ipairs(tn.edges) do for _,c in ipairs(e.conns) do if c.entity==-1 then local k=tostring(c.index);modes[k]=modes[k] or {};for m,v in pairs(e.transportModes) do if v then modes[k][tostring(m)]=true end end end end end
 return B.json.encode({critical=pd.errorState.critical,messages=B.toPlain(pd.errorState.messages),cost=pd.costs,nodes=#tn.nodes,edges=#tn.edges,modes=modes,collisions=B.toPlain(pd.collisionInfo.collisionEntities)})
end
'''
Path('scripts/stop_dual_topology_preview.lua').write_text('local f=assert(load('+json.dumps(base)+',"=stopdual","t",_ENV))();return f({edge=61156,name="inspect"},B)',encoding='utf-8')
