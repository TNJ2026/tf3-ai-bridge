import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullmap_prepare import RoadSurvey,shortlist,execution_order
from fullmap_performance import summarize

def snapshot():return {'grid':{'x':-100,'y':-100,'nx':41,'ny':41,'spacing':10,'heights':[0]*1681,'water':[False]*1681},'obstacles':[]}
def road():return {'id':'R','path':[{'x':0,'y':0},{'x':150,'y':0}]}

class PreparationTests(unittest.TestCase):
 def test_shared_survey_reuses_samples_but_new_snapshot_does_not(self):
  s=RoadSurvey(snapshot());r=shortlist(s,road());count=s.sample_calls
  self.assertTrue(r['candidates']);self.assertLessEqual(len(r['candidates']),3)
  shortlist(s,road());self.assertEqual(s.sample_calls,count);self.assertGreater(s.sample_hits,0)
  changed=snapshot();changed['grid']['water']=[True]*1681
  self.assertFalse(shortlist(RoadSurvey(changed),road())['candidates'])
 def test_obstacle_and_outside_are_rejected(self):
  data=snapshot();data['obstacles']=[{'min':{'x':60,'y':-30},'max':{'x':90,'y':30},'kind':'CONSTRUCTION'}]
  self.assertEqual(RoadSurvey(data).score(road()['path'])['rejected'],'obstacle_or_crossing')
  self.assertEqual(RoadSurvey(data).score([{'x':0,'y':0},{'x':1000,'y':0}])['rejected'],'obstacle_or_crossing')
  self.assertEqual(RoadSurvey(snapshot()).score([{'x':500,'y':0},{'x':1000,'y':0}])['rejected'],'outside_snapshot')
 def test_grade_and_nonfinite_do_not_reach_shortlist(self):
  data=snapshot();data['grid']['heights']=[i%41*10 for i in range(1681)]
  self.assertEqual(RoadSurvey(data).score(road()['path'])['rejected'],'terrain_grade_requires_design')
  self.assertEqual(RoadSurvey(snapshot()).score([{'x':float('nan'),'y':0},{'x':1,'y':1}])['rejected'],'invalid_coordinate')
 def test_dependency_order_preserves_stage_and_authorization(self):
  jobs=[{'id':'C','depends_on':['B'],'authorization':'vehicles_required'},{'id':'B','depends_on':['A']},{'id':'A','depends_on':[]}]
  out=execution_order(jobs,2);self.assertEqual([[j['id']for j in b]for b in out],[['A','B'],['C']]);self.assertEqual(out[1][0]['authorization'],'vehicles_required')
 def test_invalid_dependencies_stop(self):
  for jobs in ([{'id':'A','depends_on':['X']}],[{'id':'A','depends_on':['B']},{'id':'B','depends_on':['A']}],[{'id':'A'},{'id':'A'}]):
   with self.assertRaises(ValueError):execution_order(jobs)
 def test_metrics_do_not_add_nested_times(self):
  rows=summarize({'performance':{'bridge.eval':{'calls':2,'seconds':4,'failures':1},'facility.verify':{'calls':1,'seconds':3}}})
  self.assertEqual(rows[0]['averageSeconds'],2);self.assertEqual(rows[0]['failures'],1)

if __name__=='__main__':unittest.main()
