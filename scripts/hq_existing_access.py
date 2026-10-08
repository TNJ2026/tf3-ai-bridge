"""Read back the current owned HQ and automatic links, without native proposals."""
import argparse,asyncio,json
from pathlib import Path
from types import SimpleNamespace
from fullmap_batch import Batch
from batch_warehouses import batch_lock,write_json
from hq_access_probe import analyze

async def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    if a.output.exists():raise RuntimeError('Keep existing evidence; choose a new output')
    folder=a.output.with_suffix('.audit');folder.mkdir(parents=True,exist_ok=True)
    b=Batch(SimpleNamespace(plan=a.plan,output=folder,action='verify',ids=None,limit=0))
    with batch_lock(b.b.dir):
        await b.session()
        r=await b.eval(Path(__file__).with_suffix('.lua').read_text('utf8'))
        write_json(folder/'native_result.json',r)
        r['access']=analyze(r,existing_entities=r['hqEntities'])
        r['nativePathQueryPassed']=bool(r['nativePaths'])and all(p['outbound']and p['inbound']for p in r['nativePaths'])
        r['operationalAccepted']=False
        r['pathQueryDisagrees']=r['access']['entranceConnected']!=r['nativePathQueryPassed']
        write_json(a.output,r);b.flush()
        print(json.dumps({k:r[k]for k in ('headquarters','road','access','nativePathQueryPassed','pathQueryDisagrees','operationalAccepted')}))

if __name__=='__main__':asyncio.run(main())
