"""Read compatible purchase bases and endpoint maintenance, without route searches."""
import argparse
import asyncio
import json
from pathlib import Path
from fullmap_lines import Lines
from fullmap_batch import ROOT, quote, batch_lock, write_json

async def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();a.action='preview';a.ids=None;a.line_ids=None
    b=Lines(a)
    with batch_lock(b.b.dir):
        await b.session()
        tasks=[]
        for spec in b.specs():
            preview=b.ledger['items'][spec['id']]['preview']
            assert preview['stops'] and not b.ledger['items'][spec['id']]['attempts']
            tasks.append(dict(id=spec['id'],mode=spec['mode'],stops=preview['stops'],
                positions=[ep.get('position') or ep['stop']['position'] for ep in spec['endpoints']]))
        source=(ROOT/'scripts/route_support_preview.lua').read_text(encoding='utf8')
        result=await b.eval(source.replace('TASKJSON',quote(tasks)))
        result['session']=b.prev
        write_json(a.output/'support.json',result)
        print(json.dumps({'lines':len(result['lines']),
            'noCompatiblePurchaseBase':[r['id'] for r in result['lines'] if not r['purchaseCandidates']],
            'noEndpointMaintenance':[r['id'] for r in result['lines'] if not r['maintenanceCandidates']]}))

if __name__=='__main__':asyncio.run(main())
