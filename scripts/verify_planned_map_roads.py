"""Read-only batched audit of current journaled collection roads."""
import argparse,asyncio,json
from pathlib import Path
from fullmap_batch import Batch,batch_lock,StopBatch,write_json
from fullmap_road_reads import audit_source
async def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.action='verify';a.ids=None;a.limit=0;b=Batch(a);tasks=[]
 for s in b.p['roads']:
  item=b.ledger['items'].get(s['id'],{});c=item.get('commit',{});rr=item.get('resolved',{})
  if not c.get('built'):raise StopBatch('Unbuilt road '+s['id'])
  ns=[v for k,v in rr.items()if isinstance(v,dict)and isinstance(v.get('id'),int)]
  tasks.append(dict(id=s['id'],edges=c['edges'],nodes=[n['id']for n in ns],expectedNodes=[dict(id=n['id'],position=n['position'])for n in ns],extensions=[]))
 with batch_lock(b.b.dir):
  allrows=[]
  for offset in range(0,len(tasks),8):
   chunk=tasks[offset:offset+8];r=await b.eval(audit_source(chunk));b.accept_session(r['session']);rows=r['results'];assert [x['id']for x in rows]==[x['id']for x in chunk]
   allrows+=rows;write_json(b.out/'final_road_audit.json',allrows)
   if any(not x['verified']for x in rows):raise StopBatch('Final road audit failed; no repairs attempted')
  print(json.dumps({'roadsVerified':len(allrows)}))
if __name__=='__main__':asyncio.run(main())
