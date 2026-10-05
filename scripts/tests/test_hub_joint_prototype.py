import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hub_joint_prototype import compile_spec,probe,adapt_ports

def fixture():
 fs=[{'role':r,'resource':r,'localPosition':{'x':0,'y':0,'z':0},'relativeRotation':0,'params':{'modules':{'1':{'name':r}}}}for r in ('bus','truck','heliport','warehouse')]
 points=[{'x':i*30,'y':-65,'z':0}for i in range(4)]
 roads=[{'node0':str(i),'node1':str(i+1),'position0':points[i],'position1':points[i+1],'tangent0':{'x':30,'y':0,'z':0},'tangent1':{'x':30,'y':0,'z':0},'roadTemplate':'road','roadStyle':'style'}for i in range(3)]
 return {'facilities':fs,'roads':roads,'rolePortNodes':{'bus':['1'],'truck':['2']},'sourceEvidence':{'facilities':{'bus':12345}}}

class JointTests(unittest.TestCase):
 def test_all_road_ids_are_unique_and_reserve_construction_ids(self):
  s=compile_spec(fixture());ids=[n['entity']for n in s['nodes']]+[r['entity']for r in s['roads']]
  self.assertEqual(len(ids),len(set(ids)));self.assertTrue(all(i<-4 for i in ids))
  self.assertTrue(all(r[k]in {n['entity']for n in s['nodes']}for r in s['roads']for k in ('node0','node1')))
 def test_source_is_not_mutated_or_source_ids_carried_over(self):
  t=fixture();old=copy.deepcopy(t);s=compile_spec(t);self.assertEqual(old,t);self.assertNotIn('12345',str(s))
 def test_probe_has_no_submission_and_bindings_remain_unverified(self):
  s=compile_spec(fixture());lua=probe(s)
  self.assertNotIn('sendCommand(',lua);self.assertIn('local isolatedTestConfirmed=false',lua)
  self.assertFalse(s['commitEnabled']);self.assertFalse(s['connectionsVerified'])
  self.assertIsNone(s['portBindings']['bus']['nativeEntranceNode'])
 def test_missing_port_is_not_guessed(self):
  t=fixture();t['rolePortNodes']['bus']=[]
  with self.assertRaises(ValueError):compile_spec(t)
 def test_conflicting_node_positions_fail(self):
  t=fixture();t['roads'][1]['position0']={'x':999,'y':0,'z':0}
  with self.assertRaises(ValueError):compile_spec(t)
 def test_port_adaptation_updates_both_attached_roads_without_binding_ids(self):
  s=compile_spec(fixture());old=copy.deepcopy(s);p={'x':30,'y':-71,'z':0};r=adapt_ports(s,{'bus':p});nid=r['portBindings']['bus']['roadNode']
  self.assertEqual(s,old)
  for edge in r['roads']:
   for k in (0,1):
    if edge['node'+str(k)]==nid:self.assertEqual(edge['position'+str(k)],p)
  self.assertIsNone(r['portBindings']['bus']['nativeEntranceNode']);self.assertFalse(r['commitEnabled'])
 def test_adaptation_rejects_nonfinite(self):
  with self.assertRaises(ValueError):adapt_ports(compile_spec(fixture()),{'bus':{'x':float('nan'),'y':0,'z':0}})
if __name__=='__main__':unittest.main()
