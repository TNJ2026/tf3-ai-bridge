"""Refresh operating forecasts and consistent deliverables; entirely offline."""
import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
from fullmap_workflow import write_json
from planning_operations import enrich
from carrier_acceptance import policy as carrier_policy
from build_joint_collection import prepare, prepared_for_file
from fullmap_fleet import fleet_rows
from plan_report import write_report
from ship_route_checks import compile_checks


def read(path): return json.loads(path.read_text('utf8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_pack(root):
    plan=read(root/'network_plan.json');digest=sha(root/'network_plan.json')
    manifest=read(root/'execution_manifest.json');integrity=read(root/'delivery_integrity.json')
    if manifest.get('planDigest')!=digest or integrity['planDigest']!=digest:
        raise ValueError('Plan/manifest/report digest mismatch')
    if manifest.get('commit_enabled') is not False:raise ValueError('Finalized planning pack must keep commits disabled')
    for name,expected in integrity['artifacts'].items():
        if sha(root/name)!=expected:raise ValueError('Stale derived artifact: '+name)
    jobs={j['id']:j for j in manifest['jobs']}
    if len(jobs)!=len(manifest['jobs']):raise ValueError('Duplicate job')
    if any(set(j.get('depends_on',[]))-set(jobs) for j in jobs.values()):raise ValueError('Unknown dependency')
    for line in plan['line_specs']:
        if jobs[line['id']]['spec']!=line:raise ValueError('Stale line task: '+line['id'])
    fleet_rows(read(root/'fleet_manifest.json'),plan,digest)
    for hub in plan['hubs']:
        _,spec,_=prepared_for_file(root/'network_plan.json',plan,hub['owner'],root/'compiled_groups')
        for rid in spec['consumedRoadIds']:
            if jobs[rid].get('consumedByCollection')!=hub['owner']:raise ValueError('Road consumption mismatch')
    with (root/'FACILITIES.csv').open(encoding='utf8',newline='') as stream: rows={r['id']:r for r in csv.DictReader(stream)}
    facilities=plan['facilities']+plan.get('ports',[])
    if set(rows)!={f['id'] for f in facilities}:raise ValueError('CSV facility set mismatch')
    for f in facilities:
        if any(abs(float(rows[f['id']][k])-f['position'][k])>1e-8 for k in ('x','y')) or abs(float(rows[f['id']]['rotation'])-f['rotation'])>1e-8:
            raise ValueError('CSV pose mismatch: '+f['id'])
    gates=root/'acceptance_gates.json'
    if gates.exists() and read(gates).get('planDigest')!=digest:raise ValueError('Stale acceptance gates')
    if read(root/'ship_route_checks.json')!=compile_checks(plan):raise ValueError('Stale ship route checks')
    return dict(passed=True,gameCalls=0,lines=len(plan['line_specs']),groups=len(plan['hubs']),planDigest=digest)


def finalize(root, operations_analysis=None):
    # Offline output refresh preserves any existing execution ledger verbatim.
    plan=read(root/'network_plan.json');manifest=read(root/'execution_manifest.json')
    # Preserve the pre-update planning package once, including compiled geometry.
    backup=root/'before_operations_update'
    if not backup.exists():
        backup.mkdir()
        for path in list(root.glob('*.json'))+list(root.glob('*.md'))+list(root.glob('*.csv'))+list((root/'compiled_groups').glob('*.json')):
            dest=backup/path.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    details=root/'details.json'
    if details.exists():
        plan['cargo_deadlines_seconds']={str(c['id']):c['timeToDeliverInSeconds'] for c in read(details)['cargos'] if c.get('timeToDeliverInSeconds',0)>0}
    if operations_analysis is not None:
        plan['operationsAnalysis']=operations_analysis
    plan['carrierAcceptance']=carrier_policy()
    enrich(plan)
    by_id={f['id']:f for f in plan['facilities']+plan.get('ports',[])}
    existing_fleet=read(root/'fleet_manifest.json') if (root/'fleet_manifest.json').exists() else None
    if existing_fleet is None:
        vehicles=[]
        for line in plan['line_specs']:
            kind={'TRUCK':'road_depot','HELICOPTER':'heliport','SMALL_SHIP':'water_depot','SHIP':'water_depot'}[line['mode']]
            candidates=[f for f in by_id.values() if f['kind']==kind]
            if not candidates:raise ValueError('Missing purchase depot kind: '+kind)
            selected=line.get('purchase_base')
            if not selected:
                source=line['path'][0]
                selected=min(candidates,key=lambda f:math.hypot(f['position']['x']-source['x'],f['position']['y']-source['y']))['id']
            vehicles.append(dict(id=line['id']+'_FLEET',line=line['id'],model=line['vehicle_model'],quantity=line['fleet_forecast'],
                depot=selected,cargos=[int(k) for k in line['cargos']],depotReachabilityVerified=False,authorization='not_granted'))
        existing_fleet=dict(commit_enabled=False,vehicles=vehicles)
    # Retain reviewed model/count choices. Only explicit line purchase references
    # are synchronized; maintenance and purchase are independent decisions.
    for row in existing_fleet['vehicles']:
        line=next(l for l in plan['line_specs'] if l['id']==row['line'])
        if line['vehicle_model']!=row['model'] or line['fleet_forecast']!=row['quantity']:raise ValueError('Fleet forecast disagrees with reviewed manifest')
        line['purchase_base']=row['depot']
    jobs={j['id']:j for j in manifest['jobs']}
    for line in plan['line_specs']:
        endpoints={line[k] for k in ('source','destination','warehouse','purchase_base','maintenance_base') if isinstance(line.get(k),str)}
        deps=endpoints & set(jobs)
        deps.update(line.get('prerequisite_jobs',[]))
        deps.update(r['id'] for r in plan['roads'] if r.get('to_facility') in endpoints)
        deps.update(s for e in ('source','destination') if isinstance(line[e],dict) for s in line[e].get('unload_stops',[]))
        jobs[line['id']].update(spec=copy.deepcopy(line),depends_on=sorted(deps))
    write_json(root/'network_plan.json',plan);digest=sha(root/'network_plan.json')
    for hub in plan['hubs']:
        _,spec,origin=prepare(plan,hub['owner'])
        write_json(root/'compiled_groups'/(hub['owner']+'.json'),dict(spec=spec,origin=origin,planDigest=digest,
            commitEnabled=False,externalIncluded=bool(spec.get('externalAnchor')),nativePreviewReusable=False))
        for rid in spec['consumedRoadIds']:jobs[rid]['consumedByCollection']=hub['owner']
    manifest.update(planDigest=digest,commit_enabled=False)
    manifest['access_execution']=dict(mode='joint_collection_with_external_road',compiled_groups='compiled_groups',exclusive_external_jobs=True,
        freshNativePreviewRequired=True,buildAdapterReleaseStatus='offline_tested; representative native acceptance pending')
    write_json(root/'execution_manifest.json',manifest)
    existing_fleet.update(planDigest=digest,commit_enabled=False);write_json(root/'fleet_manifest.json',existing_fleet)
    gates_path=root/'acceptance_gates.json'
    if gates_path.exists():
        gates=read(gates_path);gates['planDigest']=digest
        gates['phaseGates']={
            'beforeBuild':dict(status='pending_current_session',checks=['user scope','backup','fresh joint preview','existing HQ reuse']),
            'afterEachCollection':dict(status='pending',checks=['physical inventory','external paths','primary warehouse','maintenance','role-specific transfer']),
            'beforeFleet':dict(status='pending',checks=['line cargo and terminals','compatible purchase base','model availability and compartments']),
            'operation':dict(status='pending',checks=carrier_policy()['required'])}
        gates['operatingForecastReviewRequired']=False
        gates['operatingForecastRole']='planning_reference_not_commissioning_gate'
        write_json(gates_path,gates)
    write_json(root/'ship_route_checks.json',compile_checks(plan))
    write_report(root)
    return validate_pack(root)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack',type=Path,required=True);parser.add_argument('--check',action='store_true')
    parser.add_argument('--operations-analysis', choices=['basic','detailed'],
                        help='Detailed forecasts only for an explicitly requested optimization task')
    args=parser.parse_args()
    if args.check and args.operations_analysis is not None:
        parser.error('--check cannot change the operations analysis mode')
    print(json.dumps(validate_pack(args.pack) if args.check else finalize(args.pack,args.operations_analysis)))

if __name__=='__main__':main()
