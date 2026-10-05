import asyncio,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullmap_stops import Stops,StopBatch

class Harness(Stops):
 def __init__(self,path,rows):
  self.path=path;self.a=SimpleNamespace(action='verify',stop_ids=None,limit=0,read_batch_size=8)
  self.p={'city_stops':[{'id':r['id']}for r in rows]};self.ledger={'items':{},'events':[]};self.rows=rows;self.checks=0;self.reads=0
 async def session(self):self.checks+=1
 async def eval(self,code):
  start=self.reads*8;self.reads+=1;return self.rows[start:start+8]
 async def save(self,*args):raise AssertionError('No game saves in verify')

class StopBatches(unittest.TestCase):
 def test_missing_53_stops_need_seven_requests_and_no_build(self):
  with tempfile.TemporaryDirectory()as d:
   rows=[{'id':str(i),'result':{'objects':[],'verified':False}}for i in range(53)]
   h=Harness(Path(d)/'ledger.json',rows);asyncio.run(h.run())
   self.assertEqual((h.checks,h.reads),(7,7));self.assertEqual(len(h.ledger['items']),53)
 def test_historical_missing_stops_are_not_marked_unbuilt(self):
  with tempfile.TemporaryDirectory()as d:
   h=Harness(Path(d)/'ledger.json',[{'id':'A','result':{'objects':[],'verified':False}}]);h.ledger['items']['A']={'attempts':1}
   with self.assertRaises(StopBatch):asyncio.run(h.run())
   self.assertEqual(h.ledger['items']['A']['status'],'submission_absent_requires_review')
 def test_different_current_entities_require_reconciliation(self):
  with tempfile.TemporaryDirectory()as d:
   h=Harness(Path(d)/'ledger.json',[{'id':'A','result':{'objects':[{'id':3},{'id':4}],'verified':True}}]);h.ledger['items']['A']={'attempts':1,'commit':{'stations':[{'id':1},{'id':2}]}}
   with self.assertRaises(StopBatch):asyncio.run(h.run())
 def test_matching_stops_verify(self):
  with tempfile.TemporaryDirectory()as d:
   h=Harness(Path(d)/'ledger.json',[{'id':'A','result':{'objects':[{'id':1},{'id':2}],'verified':True}}]);h.ledger['items']['A']={'attempts':1,'commit':{'stations':[{'id':1},{'id':2}]}}
   asyncio.run(h.run());self.assertEqual(h.ledger['items']['A']['status'],'static_verified')
if __name__=='__main__':unittest.main()
