"""Prepare the sampled flat-ground layer before collection siting; no game calls."""
import argparse,json,time
from pathlib import Path
from fullmap_workflow import write_json,atomic_write
from tf3_mcp.flat_areas import FlatTerrain

def run(snapshot_path,output):
    started=time.perf_counter();s=json.loads(Path(snapshot_path).read_text('utf8'))
    report=FlatTerrain(s['grid']).report()
    report.update(snapshot=str(Path(snapshot_path).resolve()),seconds=time.perf_counter()-started)
    output=Path(output);write_json(output/'flat_areas.json',report)
    from tf3_mcp.flat_areas import svg_layer
    atomic_write(output/'flat_areas.svg',svg_layer(report))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=run(a.snapshot,a.output);print(json.dumps(dict(r['summary'],seconds=r['seconds'],gameCalls=0)))
