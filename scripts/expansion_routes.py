"""Incremental native route previews/builds using existing facilities and fresh industry identities."""
import argparse,asyncio,json,math
from pathlib import Path
from fullmap_lines import Lines
from fullmap_batch import ROOT,batch_lock,write_json,quote

class ExpansionLines(Lines):
 def specs(self):
  rows=json.loads((self.out.parent/'new_lines.json').read_text(encoding='utf8'))
  facilities={f['id']:f for f in self.p['facilities']+self.p['ports']};industry={i['id']:i for i in self.p['industries']}
  industry.update({i['id']:i for i in self.ledger.get('sessionAdditions',{}).get('industries',[])})
  def endpoint(key,loads,terminal):
   pos=industry[key]['position']if isinstance(key,int)else facilities[key]['position']
   out=dict(id=str(key),position=pos,loads=loads)
   if terminal is not None:out['terminal_index']=terminal
   return out
  return [dict(id=r['id'],name='全图供给·'+r['id'],mode=r['mode'],endpoints=[endpoint(r['source'],r['cargos'],r.get('sourceTerminal')),endpoint(r['destination'],[],r.get('destinationTerminal'))])for r in rows if not self.a.line_ids or r['id']in self.a.line_ids.split(',')]

async def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['preview','build','verify']);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--line-ids');a=ap.parse_args();a.plan=a.root/'plan.json';a.output=a.root/'execution';a.ids=None;a.limit=0;b=ExpansionLines(a)
 with batch_lock(b.b.dir):await b.run()

if __name__=='__main__':asyncio.run(main())
