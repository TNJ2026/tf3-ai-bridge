import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hub_joint_diagnostics import analyze

class Tests(unittest.TestCase):
 def spec(self):return {'nodes':[{'entity':-5}],'roads':[{'entity':-6}],'portBindings':{'bus':{'roadNode':-5}}}
 def result(self):return {'collisions':[-5,-5,-8,123],'errorState':{'critical':False,'messages':['collision']},'networks':[],'links':{'_unavailable':'opaque'}}
 def test_classification_and_deduplication(self):
  d=analyze(self.spec(),self.result());self.assertEqual(d['collisions'],{'existing_world':[123],'explicit_roads':[-5],'generated_or_unmapped':[-8]});self.assertFalse(d['commitAllowed'])
 def test_opaque_collisions_not_assumed_clear(self):
  r=self.result();r.update(collisions={'_unavailable':'opaque'},errorState={'critical':False})
  self.assertFalse(analyze(self.spec(),r)['nativePreviewClear'])
 def test_shared_incidence_does_not_pass_connection(self):
  r=self.result();r['networks']=[{'edges':[{'from':{'entity':-5},'to':{'entity':-9},'modes':[3]}]}]
  d=analyze(self.spec(),r);self.assertTrue(d['portBindings']['bus']['sharesEntityIncidenceWithGeneratedNodes']);self.assertFalse(d['connectionsVerified'])
 def test_opaque_links_not_absent(self):self.assertFalse(analyze(self.spec(),self.result())['linksInspectable'])
 def test_empty_serialized_links_not_claimed_inspectable(self):
  r=self.result();r['links']={'toAdd':[[]],'toRemove':[]}
  self.assertFalse(analyze(self.spec(),r)['linksInspectable'])
if __name__=='__main__':unittest.main()
