import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hub_execution import execute_collection,StopBatch,strict_road_preview
from build_displayed_collection import layout

class Fake:
 def __init__(self):
  self.ledger={'items':{}};self.p={'roads':[{'id':'road1'},{'id':'road2'}]};self.calls=[]
  self.reject=False;self.timeout=False;self.changed=False;self.walk=True;self.road_changed=False
 def tasks(self):return [{'id':'bus','expectedParams':{'modules':{'1':{'name':'passenger'}}}}]
 async def session(self):self.calls.append('session')
 def flush(self):pass
 async def save(self,phase):self.calls.append('save:'+phase)
 async def preflight_corridors(self):self.calls.append('corridor')
 async def clone(self,t,apply=False):
  self.calls.append('clone:'+str(apply))
  if apply and self.timeout:raise TimeoutError('unknown')
  return {'safe':True,'commit':{'built':True}}
 async def facility(self,t,action):
  self.calls.append('verify')
  return {'audit':{'staticVerified':not self.changed,'params':{'modules':{'1':{'name':'passenger'}}}}}
 async def audit_road(self,item):return {'verified':not self.road_changed}
 async def resolve(self,spec):self.calls.append('resolve:'+spec['id']);return {'start':{'node':1},'end':{'node':2}},{'id':spec['id']}
 async def eval(self,code):
  ispreview='"preview":true' in code;self.calls.append('road:preview'if ispreview else'road:commit')
  return {'ok':not self.reject,'buildable':True,'built':True,'messages':['collision']if self.reject else[]}
 async def complete_junctions(self,item):raise AssertionError('unexpected repair')
 async def accept_collection(self):
  self.calls.append('accept')
  if not self.walk:raise StopBatch('walking unverified')
  await self.save('complete');return {'accepted':True}

class ExecutionTests(unittest.IsolatedAsyncioTestCase):
 async def test_one_call_finishes_in_dependency_order(self):
  b=Fake();self.assertTrue((await execute_collection(b))['accepted'])
  self.assertLess(b.calls.index('verify'),b.calls.index('road:commit'))
  self.assertEqual(b.calls.count('road:commit'),2);self.assertEqual(b.calls[-1],'save:complete')
 async def test_preview_has_no_writes(self):
  b=Fake();await execute_collection(b,preview=True)
  self.assertNotIn('clone:True',b.calls);self.assertNotIn('road:commit',b.calls);self.assertFalse(any(c.startswith('save:')for c in b.calls))
 async def test_blocked_road_stops_dependent_road(self):
  b=Fake();b.reject=True
  with self.assertRaises(StopBatch):await execute_collection(b)
  self.assertNotIn('resolve:road2',b.calls);self.assertNotIn('road:commit',b.calls);self.assertNotIn('accept',b.calls)
 async def test_timeout_never_replayed(self):
  b=Fake();b.timeout=True
  with self.assertRaises(TimeoutError):await execute_collection(b)
  b.calls=[]
  with self.assertRaises(StopBatch):await execute_collection(b)
  self.assertNotIn('clone:True',b.calls)
 async def test_resume_verifies_without_empty_site_preview_or_resubmit(self):
  b=Fake();await execute_collection(b);b.calls=[]
  await execute_collection(b)
  self.assertIn('verify',b.calls);self.assertNotIn('corridor',b.calls);self.assertNotIn('clone:True',b.calls);self.assertNotIn('road:commit',b.calls)
 async def test_changed_existing_facility_stops_all_writes(self):
  b=Fake();await execute_collection(b);b.calls=[];b.changed=True
  with self.assertRaises(StopBatch):await execute_collection(b)
  self.assertFalse(any(c.startswith('save:')or c=='road:commit' for c in b.calls))
 async def test_failed_walking_never_saves_complete(self):
  b=Fake();b.walk=False
  with self.assertRaises(StopBatch):await execute_collection(b)
  self.assertNotIn('save:complete',b.calls)
 async def test_changed_existing_road_stops_before_new_submissions(self):
  b=Fake();await execute_collection(b);b.calls=[];b.road_changed=True
  with self.assertRaises(StopBatch):await execute_collection(b)
  self.assertNotIn('road:commit',b.calls);self.assertNotIn('clone:True',b.calls)

class GeometryTests(unittest.TestCase):
 def template(self):
  points=[{'x':x,'y':-65,'z':0}for x in (-40,8,110,230)]
  return {'sourceEvidence':{'rotation':-61},'rolePortNodes':{'bus':['N1'],'truck':['N2']},
          'roads':[{'node0':'N'+str(i),'node1':'N'+str(i+1),'position0':points[i],'position1':points[i+1]}for i in range(3)]}
 def test_translation_applies_to_every_road_endpoint(self):
  t=self.template();a=layout(t,{'x':0,'y':0},{'x':12,'y':4});b=layout(t,{'x':500,'y':-90},{'x':12,'y':4})
  for p,q in zip(a['corridor'],b['corridor']):self.assertAlmostEqual(q['x']-p['x'],500);self.assertAlmostEqual(q['y']-p['y'],-90)
  self.assertEqual(b['anchor'],a['anchor'])
 def test_missing_passenger_port_rejected(self):
  t=self.template();t['rolePortNodes'].pop('bus')
  with self.assertRaises(StopBatch):layout(t,{'x':0,'y':0},{'x':1,'y':1})
 def test_native_warnings_block_even_when_buildable(self):
  self.assertFalse(strict_road_preview({'ok':True,'buildable':True,'warnings':['warning']}))
 def test_false_ok_blocks_even_when_buildable(self):
  self.assertFalse(strict_road_preview({'ok':False,'buildable':True}))

if __name__=='__main__':unittest.main()
