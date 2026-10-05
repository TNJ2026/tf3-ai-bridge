"""Read-only native demand-stock coverage of all city delivery stops."""
import asyncio,json,argparse
from types import SimpleNamespace
from fullmap_batch import *
async def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.action='verify';a.ids=None;a.limit=0;b=Batch(a)
 with batch_lock(b.b.dir):
  await b.session();stops=[]
  for t in b.p['city_stops']:
   v=b.ledger['items'].get(t['id'],{});stops.append(dict(town=t['town'],stations=[o['id']for o in v.get('audit',{}).get('objects',[])]))
  code="""local cities=B.json.decode(CITIES);local stops=B.json.decode(STOPS);local CT=api.type.ComponentType;local cover={}
for _,s in ipairs(stops)do cover[s.town]=cover[s.town]or{};for _,id in ipairs(s.stations)do assert(api.engine.getComponent(id,CT.STATION),'stop changed');for _,stock in pairs(api.engine.system.catchmentAreaSystem.getStationCatchables(id,true))do cover[s.town][stock]=true end end end
local out={};for _,t in ipairs(cities)do out[t.id]={town=t.id,name=t.name,stocks=0,coveredStocks=0,demand=0,coveredDemand=0,missing={}}end
api.engine.forEachEntityWithComponent(function(id)local b=api.engine.getComponent(id,CT.TOWN_BUILDING);local r=out[b.town]
 if r and b.stockList>=0 and api.engine.entityExists(b.stockList)then
  local demand=0;for c in pairs(api.res.cargoTypeRep.getAll(true))do if c>0 then demand=demand+api.engine.util.stock.getCargoMaxConsumptionPerYear(b.stockList,c)end end
  if demand>0 then r.stocks=r.stocks+1;r.demand=r.demand+demand;if cover[b.town]and cover[b.town][b.stockList]then r.coveredStocks=r.coveredStocks+1;r.coveredDemand=r.coveredDemand+demand else r.missing[#r.missing+1]={building=id,stock=b.stockList,demand=demand}end end
 end
end,CT.TOWN_BUILDING)
local rows={};for _,t in ipairs(cities)do rows[#rows+1]=out[t.id]end;return B.json.encode(rows)""".replace('CITIES',quote(b.p['cities'])).replace('STOPS',quote(stops))
  r=await b.eval(code);write_json(b.out/'city_coverage.json',r);print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
