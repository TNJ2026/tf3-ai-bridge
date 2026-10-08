import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from configure_hub_template import configure

def fixture():
 roles=['heliport','bus','truck','warehouse'];fs=[]
 for role in roles:
  m={'1':{'name':'passenger_platform.module'if role=='bus'else 'cargo_platform.module'if role=='truck'else 'wh_universal.module','variant':0},'2':{'name':'extra.module','variant':0}}
  if role in ('bus','truck'):m['3']={'name':'entrance_exit.module','variant':0}
  fs.append({'role':role,'resource':role,'localPosition':{'x':0,'y':0,'z':0},'relativeRotation':0,'params':{'modules':m},'availableExpansionSlots':[]})
 ps=[{'x':x,'y':-65,'z':0}for x in (-40,0,100,200)]
 roads=[{'id':str(i),'node0':str(i),'node1':str(i+1),'position0':ps[i],'position1':ps[i+1],'tangent0':{'x':1,'y':0,'z':0},'tangent1':{'x':1,'y':0,'z':0},'roadTemplate':'road','roadStyle':'style'}for i in range(3)]
 return {'facilities':fs,'roads':roads,'rolePortNodes':{'bus':['1'],'truck':['2']},'sourceEvidence':{},'sourceCoverage':{'truck':True},'requirements':[]}

class Tests(unittest.TestCase):
 def test_movement_updates_shared_port_and_preserves_modules(self):
  t=fixture();old=copy.deepcopy(t);r=configure(t,{'offsets':{'truck':{'x':-20},'warehouse':{'x':-20}}})
  self.assertEqual(t,old);self.assertEqual(r['roads'][1]['position1']['x'],80)
  self.assertEqual(r['roads'][2]['position0']['x'],80)
  self.assertEqual(r['facilities'][2]['params'],old['facilities'][2]['params'])
 def test_different_lateral_offsets_have_matching_shared_tangent_direction(self):
  r=configure(fixture(),{'offsets':{'truck':{'y':10}}});a=r['roads'][0]['tangent1'];b=r['roads'][1]['tangent0']
  self.assertAlmostEqual(a['y']/a['x'],b['y']/b['x'])
 def test_selection_preserves_entrance_and_invalidates_coverage(self):
  r=configure(fixture(),{'moduleSlots':{'bus':['1','3']}})
  self.assertEqual(set(r['facilities'][1]['params']['modules']),{'1','3'})
  self.assertEqual(r['sourceCoverage'],{});self.assertFalse(r['constructionAuthorized'])
 def test_entrance_removal_rejected(self):
  with self.assertRaises(ValueError):configure(fixture(),{'moduleSlots':{'bus':['1']}})
 def test_unknown_slot_rejected(self):
  with self.assertRaises(ValueError):configure(fixture(),{'moduleSlots':{'warehouse':['999']}})
 def test_crossed_stations_rejected(self):
  with self.assertRaises(ValueError):configure(fixture(),{'offsets':{'truck':{'x':-120}}})
 def test_nan_and_typo_rejected(self):
  with self.assertRaises(ValueError):configure(fixture(),{'offsets':{'bus':{'x':float('nan')}}})
  with self.assertRaises(ValueError):configure(fixture(),{'scale':.5})
if __name__=='__main__':unittest.main()
