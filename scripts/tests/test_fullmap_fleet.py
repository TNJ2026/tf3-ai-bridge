import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fullmap_fleet import Fleet
from fullmap_batch import StopBatch

class FleetTests(unittest.IsolatedAsyncioTestCase):
 def harness(self,path):
  path.write_text(json.dumps({'planDigest':'same','lines':[{'id':'LINE001','model':'truck','cargos':[6],'count':1}]}),encoding='utf8')
  b=Fleet.__new__(Fleet);b.a=SimpleNamespace(fleet=path,action='build',limit=0)
  b.ledger={'planDigest':'same','items':{'LINE001':{'status':'static_verified','attempts':1}}}
  b.session=AsyncMock();b.save=AsyncMock();b.flush=lambda:None
  b.specs=lambda:[{'id':'LINE001','name':'line','mode':'TRUCK','endpoints':[{'position':{'x':0,'y':0}}]}]
  b.tasks=lambda:[];b.line=AsyncMock(return_value={'existing':True,'verified':True})
  return b
 async def test_unrecorded_vehicle_blocks_purchase(self):
  with tempfile.TemporaryDirectory()as d:
   b=self.harness(Path(d)/'fleet.json');b.vehicle=AsyncMock(return_value={'vehicles':[{'id':99}]})
   with self.assertRaisesRegex(StopBatch,'unrecorded fleet'):await b.run()
   self.assertEqual([c.args[1]for c in b.vehicle.call_args_list],['verify'])
   self.assertEqual(b.ledger['items']['LINE001__fleet_01']['attempts'],0)
 async def test_ambiguous_purchase_locks_retry(self):
  with tempfile.TemporaryDirectory()as d:
   b=self.harness(Path(d)/'fleet.json');b.vehicle=AsyncMock(side_effect=[{'vehicles':[]},{'selected':1},{'verified':False,'accepted':True}])
   with self.assertRaisesRegex(StopBatch,'incomplete'):await b.run()
   row=b.ledger['items']['LINE001__fleet_01']
   self.assertEqual(row['attempts'],1);self.assertEqual(row['status'],'needs_reconciliation')
   with self.assertRaisesRegex(StopBatch,'Unreconciled'):await b.run()
   self.assertEqual(b.vehicle.call_count,3)

if __name__=='__main__':unittest.main()
