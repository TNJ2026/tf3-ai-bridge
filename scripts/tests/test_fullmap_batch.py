import asyncio,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullmap_batch import Batch,StopBatch,unfinished,write_json
class Harness(Batch):
 def __init__(self,path,fail=None):
  self.a=SimpleNamespace(action='build',limit=0);self.path=path;self.ledger={'items':{},'events':[]};self.fail=fail;self.calls=[]
 def tasks(self):return [{'id':'A','kind':'warehouse'},{'id':'B','kind':'warehouse'}]
 async def session(self):return {}
 async def save(self,phase):pass
 async def facility(self,t,action):
  self.calls.append((t['id'],action))
  if action in ('verify','preview'):
   built=(t['id'],'build')in self.calls
   if built:return {'existing':True,'audit':{'staticVerified':self.fail!='readback'}}
   if action=='verify':return {'existing':False}
  if action=='preview':return {'previewPassed':self.fail!='preview'}
  persisted=json.loads(self.path.read_text());assert persisted['items'][t['id']]['status']=='commit_started';assert persisted['items'][t['id']]['attempts']==1
  if self.fail=='timeout':raise TimeoutError('unknown outcome')
  return {'commit':{'built':True},'audit':{'staticVerified':True}}
class BatchSafety(unittest.TestCase):
 def test_duplicate_facilities_rejected_before_game_queries(self):
  with tempfile.TemporaryDirectory()as d:
   plan=Path(d)/'plan.json';plan.write_text(json.dumps({'facilities':[{'id':'A'},{'id':'A'}]}),encoding='utf8')
   with self.assertRaisesRegex(ValueError,'duplicate'):
    Batch(SimpleNamespace(plan=plan,output=Path(d)),bridge=object())
 def test_failed_independent_readback_blocks_following_item(self):
  with tempfile.TemporaryDirectory()as d:
   h=Harness(Path(d)/'ledger.json','readback')
   with self.assertRaises(StopBatch):asyncio.run(h.run())
   self.assertEqual(unfinished(h.ledger),['A']);self.assertNotIn(('B','build'),h.calls)
 def test_new_build_has_one_preflight_and_independent_readback(self):
  with tempfile.TemporaryDirectory()as d:
   h=Harness(Path(d)/'ledger.json');asyncio.run(h.run())
   self.assertEqual(h.calls,[('A','preview'),('A','build'),('A','verify'),('B','preview'),('B','build'),('B','verify')])
 def test_verify_never_previews_or_builds(self):
  with tempfile.TemporaryDirectory()as d:
   h=Harness(Path(d)/'ledger.json');h.a.action='verify';asyncio.run(h.run())
   self.assertEqual(h.calls,[('A','verify'),('B','verify')])
 def test_preview_never_builds(self):
  with tempfile.TemporaryDirectory()as d:
   h=Harness(Path(d)/'ledger.json');h.a.action='preview';asyncio.run(h.run())
   self.assertEqual(h.calls,[('A','preview'),('B','preview')])
 def test_no_mutation_after_rejected_preview(self):
  with tempfile.TemporaryDirectory()as d:
   h=Harness(Path(d)/'ledger.json','preview')
   with self.assertRaises(StopBatch):asyncio.run(h.run())
   self.assertNotIn(('A','build'),h.calls);self.assertEqual(h.ledger['items']['A']['attempts'],0)
 def test_unknown_result_stops_current_batch_but_does_not_gate_unrelated_future_work(self):
  with tempfile.TemporaryDirectory()as d:
   h=Harness(Path(d)/'ledger.json','timeout')
   with self.assertRaises(TimeoutError):asyncio.run(h.run())
   self.assertEqual(unfinished(h.ledger),['A']);self.assertNotIn(('B','build'),h.calls)
   h.fail=None
   asyncio.run(h.run())
   self.assertEqual(h.calls.count(('A','build')),1)
   self.assertEqual(h.calls.count(('B','build')),1)
 def test_verified_restart_does_not_duplicate(self):
  with tempfile.TemporaryDirectory()as d:
   h=Harness(Path(d)/'ledger.json');asyncio.run(h.run());asyncio.run(h.run())
   self.assertEqual(h.calls.count(('A','build')),1);self.assertEqual(h.calls.count(('B','build')),1);self.assertEqual(unfinished(h.ledger),[])
class SessionHarness(Batch):
 def __init__(self,path):
  self.path=path;self.a=SimpleNamespace(action='build');self.prev=None;self.ledger={'items':{},'events':[]};self.calls=[]
  self.p={'cities':[{'name':'Test','position':{'x':1,'y':2}}],'industries':[],'session':{'player':1}}
  self.snapshot={'state':{'player':1,'speedup':0,'tickCount':10,'gameTime':20},'world':{'towns':self.p['cities'],'industries':[]}}
 async def eval(self,code):self.calls.append(code);return self.snapshot
class SessionSafety(unittest.TestCase):
 def test_one_snapshot_per_check_without_reusing_cache(self):
  with tempfile.TemporaryDirectory()as d:
   h=SessionHarness(Path(d)/'ledger.json');asyncio.run(h.session());asyncio.run(h.session())
   self.assertEqual(len(h.calls),2);self.assertEqual(h.ledger['lastState']['player'],1)
 def test_changed_world_player_speed_and_time_still_block(self):
  for scenario in ['world','player','speed','time']:
   with self.subTest(scenario=scenario),tempfile.TemporaryDirectory()as d:
    h=SessionHarness(Path(d)/'ledger.json')
    if scenario=='world':h.snapshot['world']['towns']=[]
    elif scenario=='player':h.snapshot['state']['player']=2
    elif scenario=='speed':h.snapshot['state']['speedup']=1
    else:h.prev={'tickCount':11,'gameTime':21}
    with self.assertRaises(StopBatch):asyncio.run(h.session())
if __name__=='__main__':unittest.main()
