import unittest
from pathlib import Path
from lupa import LuaRuntime,LuaError

SETUP='''
B={toPlain=function(v)return v end,json={encode=function(v)
 assert(v.critical==false and type(v.messages)=='table')
 return 'fixture proposal diagnostics'
end}}
local function e(a,b,m)return {conns={{entity=a},{entity=b}},transportModes=m}end
nodes={{entity=-5},{entity=-10},{entity=-8}}
edges={{entity=-15,comp={node0=-5,node1=-10}}}
spec={portBindings={bus={roadNode=-10},truck={roadNode=-5}}}
pd={errorState={critical=false,messages={},warnings={},infos={}},entity2tn={
 [-501]={edges={e(-501,-501,{[0]=true,[3]=true})}},
 [-502]={edges={e(-502,-502,{[1]=true,[3]=true,[4]=true})}},
 [-30]={edges={e(-21,-20,{[2]=true,[3]=true,[4]=true})}},
 [-31]={edges={e(-501,-20,{[3]=true})}},
 [-40]={edges={e(-23,-22,{[2]=true,[3]=true,[4]=true})}},
 [-41]={edges={e(-502,-22,{[4]=true})}}
}}
proposal={streetProposal={}};context={};called=0
api={engine={util={proposal={makeProposalData=function(p,c)
 called=called+1;return {entity2tn={[-21]={},[-23]={}}}
end}}}}
'''
class Tests(unittest.TestCase):
 def test_fixed_frontage_rejects_port_displacement_before_repreview(self):
  lua=LuaRuntime();lua.execute(SETUP+'''
  spec.alignGeneratedPortGeometry=true
  spec.roads={{entity=-15,buildPhase='frontage'}}
  function V3(x,y,z)return{x=x,y=y,z=z}end
  edges[1].comp.position0=V3(0,0,0);edges[1].comp.position1=V3(100,0,0)
  for _,id in ipairs({-30,-40})do for _,edge in ipairs(pd.entity2tn[id].edges)do
   edge.geometry={cubicSpline={pos={{x=7,y=0},{x=107,y=0}}},height={x=0,y=0}}
  end end
  ''')
  with self.assertRaisesRegex(LuaError,'move fixed frontage'):
   lua.execute(Path(__file__).resolve().parents[1].joinpath('hub_joint_bind_probe.lua').read_text('utf8'))
  self.assertEqual(lua.globals().called,0)
  self.assertEqual(lua.globals().edges[1].comp.position0.x,0)
  self.assertEqual(lua.globals().edges[1].comp.position1.x,100)

 def test_native_port_geometry_replaces_guessed_endpoint(self):
  lua=LuaRuntime();lua.execute(SETUP+'''
  spec.alignGeneratedPortGeometry=true
  function V3(x,y,z)return{x=x,y=y,z=z}end
  edges[1].comp.position0=V3(0,0,0);edges[1].comp.position1=V3(100,0,0)
  local function geometry(net,a,b,h)
   for _,edge in ipairs(pd.entity2tn[net].edges)do
    edge.geometry={cubicSpline={pos={a,b}},height={x=h,y=h}}
   end
  end
  geometry(-30,{x=90,y=0},{x=110,y=0},12)
  geometry(-40,{x=10,y=0},{x=30,y=0},8)
  ''')
  lua.execute(Path(__file__).resolve().parents[1].joinpath('hub_joint_bind_probe.lua').read_text('utf8'))
  g=lua.globals();self.assertEqual(g.edges[1].comp.position0.x,10)
  self.assertEqual(g.edges[1].comp.position0.z,8)
  self.assertEqual(g.edges[1].comp.position1.x,90)
  self.assertEqual(g.spec.portBindings.truck.nativePosition.z,8)
 def run_lua(self,extra=''):
  lua=LuaRuntime();lua.execute(SETUP+extra)
  lua.execute(Path(__file__).resolve().parents[1].joinpath('hub_joint_bind_probe.lua').read_text('utf8'))
  return lua
 def test_dynamic_ports_replace_both_nodes_before_preview(self):
  lua=self.run_lua();g=lua.globals()
  self.assertEqual(g.called,1);self.assertEqual(g.edges[1].comp.node0,-23);self.assertEqual(g.edges[1].comp.node1,-21)
  self.assertEqual(len(g.proposal.streetProposal.nodesToAdd),1)
  self.assertEqual(g.spec.portBindings.bus.nativeEntranceNode,-21)
 def test_missing_generated_port_stops_before_second_native_preview(self):
  with self.assertRaisesRegex(LuaError,'Generated port ambiguous.*fixture proposal diagnostics'):self.run_lua('pd.entity2tn[-40]=nil')
 def test_existing_world_nodes_are_not_selected(self):
  with self.assertRaisesRegex(LuaError,'Generated port ambiguous.*fixture proposal diagnostics'):self.run_lua('pd.entity2tn[-30].edges[1].conns[1].entity=123')
if __name__=='__main__':unittest.main()
