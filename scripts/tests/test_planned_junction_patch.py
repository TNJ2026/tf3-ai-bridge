import json,unittest
from pathlib import Path
from lupa import LuaRuntime,LuaError
SOURCE=(Path(__file__).resolve().parents[1]/'planned_junction_patch.lua').read_text('utf8')
class MixedJunctionTests(unittest.TestCase):
 def run_patch(self,widths=(4,4,6),apply=False,extra=''):
  lua=LuaRuntime(unpack_returned_tuples=True);lua.globals().decode=lambda s:lua.table_from(json.loads(s),recursive=True)
  lua.execute('''B={json={decode=decode,encode=function(v)return v end},toPlain=function(v)return v end};calls=0
  api={type={ComponentType={BASE_NODE=1,BASE_EDGE=2,BASE_NODE_CONFIG=3,TRANSPORT_NETWORK=4},enum={TransportMode={CAR=2,TRUCK=4}},LaneConnection={new=function()return {}end},BaseNodeLaneConnectionAndEntity={new=function()return {}end},SimpleProposal={new=function()return {streetProposal={}}end}},engine={system={streetSystem={getNodeSegments=function()return {10,11,12}end}},util={proposal={makeProposalData=function(p) proposal=p;return {errorState={critical=false,messages={},infos={},warnings={}},collisionInfo={collisionEntities={}}}end}}},cmd={makeWorldBuildProposalCmd=function(p)return p end,sendCommand=function(p,cb)calls=calls+1;cb(nil,true)end}}
  cfg={laneConnections={{segment0=10,segment1=11},{segment0=11,segment1=10}},crosswalks={10},userModifiedTrafficLightStates=false}
  comps={[1]={[1]={position={x=0,y=0}},[3]=cfg}}
  api.engine.getComponent=function(id,k)return comps[id]and comps[id][k]end
  function road(id,count) local lanes={};for k=1,count do lanes[k]={forward=k>count/2,transportModes={[2]=k>1 and k<count,[4]=k>1 and k<count}}end;comps[id]={[2]={node0=1,node1=id,laneConfigs=lanes},[4]={}}end
  ''')
  for eid,w in zip((10,11,12),widths):lua.globals().road(eid,w)
  lua.execute(extra)
  task=json.dumps(dict(node=1,branch=12,x=0,y=0,existingEdges=[10,11]))
  result=lua.execute(SOURCE.replace('TASKJSON','[==['+task+']==]').replace('local apply=APPLY','local apply='+str(apply).lower()))
  return result,lua
 def test_mixed_lanes_preview_preserves_original(self):
  r,l=self.run_patch();self.assertEqual(len(r['addedTurns']),8);self.assertEqual(r['retainedTurns'],2);self.assertEqual(r['retainedCrosswalks'],1);self.assertEqual(l.globals().calls,0)
 def test_four_vehicle_lanes_all_sides(self):
  r,l=self.run_patch((6,6,6),True);self.assertEqual(len(r['addedTurns']),16);self.assertEqual(l.globals().calls,1);self.assertTrue(r['applied'])
 def test_unknown_lane_width_rejected(self):
  with self.assertRaises(LuaError):self.run_patch((4,4,8))
 def test_missing_network_rejected(self):
  with self.assertRaises(LuaError):self.run_patch(extra='comps[12][4]=nil')
 def test_custom_signals_rejected(self):
  with self.assertRaises(LuaError):self.run_patch(extra='cfg.userModifiedTrafficLightStates=true')
if __name__=='__main__':unittest.main()
