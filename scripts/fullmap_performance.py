"""Summarize measured ledger stages and compare offline runs; never connects."""
import argparse,json
from pathlib import Path

def summarize(ledger):
 rows=[]
 for name,v in ledger.get('performance',{}).items():
  count=v.get('calls',0);seconds=v.get('seconds',0)
  rows.append({'stage':name,'calls':count,'seconds':round(seconds,4),'averageSeconds':round(seconds/count,4)if count else None,'maxSeconds':round(v.get('maxSeconds',0),4),'failures':v.get('failures',0)})
 return sorted(rows,key=lambda r:r['seconds'],reverse=True)

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('ledger',type=Path);ap.add_argument('--baseline',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args()
 result={'stages':summarize(json.loads(a.ledger.read_text('utf8'))),'note':'Nested stage times overlap. Compare equivalent workloads; no total or live speedup inferred.'}
 if a.baseline:
  old={r['stage']:r for r in summarize(json.loads(a.baseline.read_text('utf8')))}
  result['comparison']=[{'stage':r['stage'],'baselineCalls':old[r['stage']]['calls'],'currentCalls':r['calls'],'baselineSeconds':old[r['stage']]['seconds'],'currentSeconds':r['seconds']}for r in result['stages']if r['stage']in old]
 text=json.dumps(result,ensure_ascii=False,indent=2)
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text,encoding='utf8')
 print(text)
if __name__=='__main__':main()
