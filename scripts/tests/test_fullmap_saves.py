"""Offline native-save overwrite checks; no game connection."""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fullmap_batch import Batch, StopBatch, save_slot


class SaveHarness(Batch):
 def __init__(self, root, write=True):
  self.b=SimpleNamespace(dir=root/'bridge');self.b.dir.mkdir()
  (root/'save').mkdir();self.path=root/'ledger.json'
  self.ledger={'planDigest':'a'*64,'items':{},'events':[]};self.write=write
 async def call(self,command,args,engine):
  assert command=='eval' and engine is False
  assert 'function() end,false,true' in args['code']
  if self.write:
   name=self.ledger['events'][-1]['nativeSaveRequested'];path=self.b.dir.parent/'save'/(name+'.sav')
   old=path.stat().st_mtime_ns if path.exists() else None
   path.write_bytes(b'native save mock')
   if old is not None:os.utime(path,ns=(old+1000000000,old+1000000000))


class SaveTests(unittest.TestCase):
 def test_normal_phases_share_slot_and_plans_are_separate(self):
  names=[save_slot(p,'a'*64) for p in ['checkpoint_10','after','roads_after','stops_10','lines_20','vehicles_after','maintenance_recovery_after']]
  self.assertEqual(len(set(names)),1);self.assertTrue(names[0][1])
  self.assertNotEqual(names[0][0],save_slot('after','b'*64)[0])
 def test_backups_and_abnormal_evidence_are_unique(self):
  for phase in ['before','roads_before','before_heli_upgrade','fleet_observation_map_changed','crash']:
   first=save_slot(phase,'a'*64);second=save_slot(phase,'a'*64)
   self.assertFalse(first[1]);self.assertNotEqual(first[0],second[0])
 def test_overwrite_reuses_one_file_and_records_both_events(self):
  with tempfile.TemporaryDirectory() as d,patch('fullmap_batch.asyncio.sleep',new_callable=AsyncMock):
   h=SaveHarness(Path(d));asyncio.run(h.save('checkpoint_10'));asyncio.run(h.save('after'))
   self.assertEqual(len(list((Path(d)/'save').glob('*.sav'))),1)
   self.assertEqual(len(h.ledger['events']),2)
   self.assertTrue(all(e['complete'] for e in h.ledger['events']))
   self.assertTrue(h.ledger['events'][-1]['replacesExisting'])
 def test_unchanged_old_file_does_not_count_as_success(self):
  with tempfile.TemporaryDirectory() as d,patch('fullmap_batch.asyncio.sleep',new_callable=AsyncMock):
   h=SaveHarness(Path(d));asyncio.run(h.save('after'));h.write=False
   with self.assertRaises(StopBatch):asyncio.run(h.save('after'))
   self.assertNotIn('complete',h.ledger['events'][-1])
 def test_missing_file_does_not_count_as_success(self):
  with tempfile.TemporaryDirectory() as d,patch('fullmap_batch.asyncio.sleep',new_callable=AsyncMock):
   h=SaveHarness(Path(d),write=False)
   with self.assertRaises(StopBatch):asyncio.run(h.save('after'))


if __name__=='__main__':unittest.main()
