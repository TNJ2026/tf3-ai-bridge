"""Offline batching and Lua index safety checks; no live bridge."""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from lupa import LuaRuntime

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullmap_batch import Batch,ROOT,StopBatch

class ReadHarness(Batch):
 def __init__(self,path,action='verify',failure=None):
  self.path=path;self.a=SimpleNamespace(action=action,read_batch_size=8,limit=0)
  self.ledger={'items':{},'events':[]};self.chunks=[];self.sessions=0;self.failure=failure
 def tasks(self):return [dict(id=str(i),kind='warehouse')for i in range(17)]
 async def session(self):self.sessions+=1
 async def read_facilities(self,tasks,action):
  self.chunks.append((len(tasks),action))
  if self.failure=='timeout':raise TimeoutError('unknown read outcome')
  return [dict(id=t['id'],result={'existing':False,'previewPassed':self.failure!='blocked'})for t in tasks]
 async def facility(self,*args):raise AssertionError('Individual operation forbidden in read batch')
 async def save(self,*args):raise AssertionError('Read-only batch cannot save game')

class ReadBatchTests(unittest.TestCase):
 def test_17_sites_use_three_checks_and_three_reads(self):
  with tempfile.TemporaryDirectory()as d:
   h=ReadHarness(Path(d)/'ledger.json');asyncio.run(h.run())
   self.assertEqual(h.chunks,[(8,'verify'),(8,'verify'),(1,'verify')]);self.assertEqual(h.sessions,3)
   self.assertTrue(all(v['status']=='not_built'for v in h.ledger['items'].values()))
 def test_missing_previous_submission_stops_next_chunk(self):
  with tempfile.TemporaryDirectory()as d:
   h=ReadHarness(Path(d)/'ledger.json');h.ledger['items']['0']={'attempts':1}
   with self.assertRaises(StopBatch):asyncio.run(h.run())
   self.assertEqual(len(h.chunks),1);self.assertEqual(h.ledger['items']['0']['status'],'submission_absent_requires_review')
 def test_timeout_does_not_retry(self):
  with tempfile.TemporaryDirectory()as d:
   h=ReadHarness(Path(d)/'ledger.json',failure='timeout')
   with self.assertRaises(TimeoutError):asyncio.run(h.run())
   self.assertEqual(len(h.chunks),1)
 def test_known_preview_rejection_is_reported_without_building(self):
  with tempfile.TemporaryDirectory()as d:
   h=ReadHarness(Path(d)/'ledger.json','preview','blocked');h.a.limit=2;asyncio.run(h.run())
   self.assertEqual(len(h.ledger['items']),2)
   self.assertTrue(all(v['status']=='preview_blocked'for v in h.ledger['items'].values()))
 def test_batch_api_rejects_build_before_eval(self):
  with tempfile.TemporaryDirectory()as d:
   h=ReadHarness(Path(d)/'ledger.json')
   with self.assertRaises(ValueError):asyncio.run(Batch.read_facilities(h,[{'id':'A'}],'build'))

class LuaIndexTests(unittest.TestCase):
 def test_index_scans_once_is_fresh_per_request_and_rejects_duplicates(self):
  lua=LuaRuntime(unpack_returned_tuples=True)
  lua.execute('''
  scans={}; api={type={ComponentType={CONSTRUCTION=1,WAREHOUSE=2,PLAYER_OWNED=3}},engine={util={getPlayer=function()return 7 end}}}
  entities={};local function make(x) return {fileName='::/landmarks/hq/headquarter.con',params={},stations={},depots={},frozenNodes={},frozenEdges={},transf={cols=function(self,k)if k==0 then return {x=1,y=0}end return {x=x,y=0,z=0}end}}end
  entities[10]=make(0);entities[11]=make(10);makeConstruction=make
  api.engine.forEachEntityWithComponent=function(fn,ct)scans[ct]=(scans[ct]or 0)+1;if ct==1 then for id in pairs(entities)do fn(id)end end end
  api.engine.getComponent=function(id,ct)if ct==1 then return entities[id]elseif ct==3 then return {player=7}end end
  B={json={encode=function(x)return x end},toPlain=function(x)return x end}
  ''')
  body=(ROOT/'scripts/fullmap_facility.lua').read_text('utf-8-sig').replace('local task=TASK','').replace('local action=ACTION','local action="verify"').replace('local readIndex=nil','local readIndex=facilityReadIndex')
  setup=(ROOT/'scripts/fullmap_facility_index.lua').read_text('utf8')
  source=setup+'\nreturn function(task)\n'+body+'\nend'
  inspect=lua.execute(source)
  def task(x):return lua.table_from(dict(kind='headquarters',position={'x':x,'y':0},args={}),recursive=True)
  self.assertTrue(inspect(task(0))['audit']['staticVerified']);self.assertTrue(inspect(task(10))['audit']['staticVerified'])
  self.assertEqual(lua.globals().scans[1],1);self.assertEqual(lua.globals().scans[2],1)
  lua.execute('entities[10]=nil')
  fresh=lua.execute(source);self.assertFalse(fresh(task(0))['existing'])
  self.assertEqual(lua.globals().scans[1],2)
  lua.execute('entities[12]=makeConstruction(10)')
  with self.assertRaises(Exception):lua.execute(source)(task(10))

if __name__=='__main__':unittest.main()
