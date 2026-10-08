"""Journaled passenger lines using existing native stop, line and fleet executors."""
import argparse,asyncio,json
from pathlib import Path
from fullmap_batch import ROOT,quote,batch_lock
from fullmap_lines import Lines
from fullmap_stops import Stops
from fullmap_fleet import Fleet

class BusLines(Lines):
 def specs(self):return self.p['bus_specs']
 async def line(self,t,action):
  source=(ROOT/'scripts/fullmap_lines.lua').read_text(encoding='utf8')
  predicate='((#ep.loads>0 and t.cargoLoad) or (#ep.loads==0 and t.cargoUnload))'
  assert predicate in source,'Passenger terminal adapter requires review after freight executor change'
  source=source.replace(predicate,'(t.passengersUnload and t.passengersLoad)')
  # Native street objects expose an empty terminal mode mask; validate BUS paths
  # through their actual vehicle nodes, as the freight executor does for TRUCK.
  source=source.replace('ep.stop and mode==api.type.enum.TransportMode.TRUCK','ep.stop and mode==api.type.enum.TransportMode.BUS')
  return await self.eval(source.replace('TASKJSON',quote(t)).replace('local action=ACTION','local action='+json.dumps(action)))

class BusFleet(Fleet,BusLines):
 def tasks(self):return self.p['facilities']

class BusStops(Stops):
 async def audit(self,t):
  source=(ROOT/'scripts/fullmap_stop_audit.lua').read_text(encoding='utf-8-sig')
  source=source.replace('t.cargoUnload','t.passengersUnload').replace('t.cargoLoad','t.passengersLoad')
  source=source.replace('getStationCatchables(ref[1],true)','getStationCatchables(ref[1],false)')
  return await self.eval(source.replace('TASKJSON',quote(t)))

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['stops','lines','fleet']);ap.add_argument('action',choices=['preview','build','verify']);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args()
 a.plan=a.root/'plan.json';a.output=a.root/'execution';a.fleet=a.root/'fleet.json';a.ids=None;a.stop_ids=None;a.line_ids=None;a.limit=0;a.read_batch_size=1
 b={'stops':BusStops,'lines':BusLines,'fleet':BusFleet}[a.stage](a)
 with batch_lock(b.b.dir):await b.run()
if __name__=='__main__':asyncio.run(main())
