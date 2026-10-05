"""Offline readiness check; no bridge calls or local export registries."""
import argparse,json
from pathlib import Path
from planning_pipeline_core import TEMPLATE_DIR,load_templates
ROOT=Path(__file__).resolve().parents[1]
REQUIRED=['plan_flat_areas.py','plan_template_map.py','plan_network_complete.py','fullmap_workflow.py',
          'road_first_collection.py',
          'plan_report.py','plan_native_preview.py','construct_planned_map.py','build_planned_hub_roads.py',
          'fullmap_roads.py','fullmap_batch.py','audit_planned_hubs.py','fullmap_stops.py','fullmap_lines.py',
          'planning_pipeline_core.py','planning_flow.py','planning_shared_hubs.py','plan_write_report.py']
DATA_FILES=['scripts/fullmap_facility.lua','scripts/fullmap_road_audit.lua','scripts/planned_junction_patch.lua',
            'scripts/road_first_walk.lua','scripts/station_walk_transfer.lua','scripts/road_snap_height.lua',
            'scripts/fullmap_lines.lua','scripts/fullmap_stop_audit.lua',
            'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua']
def check(city_template=TEMPLATE_DIR/'city.json',production_template=TEMPLATE_DIR/'production.json'):
    templates=load_templates(city_template,production_template)
    for name in REQUIRED:
        path=ROOT/'scripts'/name
        compile(path.read_text('utf8'),str(path),'exec')
    for name in DATA_FILES:
        if not (ROOT/name).read_text('utf-8-sig').strip():raise ValueError('Empty runtime file: '+name)
    # Import reusable execution classes without running main or contacting game.
    from build_planned_hub_roads import PlannedRoads
    from fullmap_roads import Roads
    assert issubclass(PlannedRoads,Roads)
    return {'ready':True,'gameCalls':0,'templates':{k:{'facilities':len(v['facilities']),'roads':len(v['roads'])}for k,v in templates.items()},'checkedScripts':REQUIRED,'runtimeFilesReadable':DATA_FILES,'nativeResourcesVerified':False}
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--city-template',type=Path,default=TEMPLATE_DIR/'city.json')
    ap.add_argument('--production-template',type=Path,default=TEMPLATE_DIR/'production.json')
    a=ap.parse_args();print(json.dumps(check(a.city_template,a.production_template)))
if __name__=='__main__':main()
