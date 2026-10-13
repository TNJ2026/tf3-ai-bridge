"""One offline prepare entry: validate -> layout -> network -> preflight -> summary.

Never connects to the game or runs native previews. Native inspection remains a
separate fresh read after this inexpensive preparation has completed.
"""
import argparse,json,subprocess,sys,time,datetime
from pathlib import Path
from fullmap_workflow import digest,write_json,atomic_write
from planning_pipeline_core import validate_inputs,layout_key,load_templates,strip_native_evidence,TEMPLATE_DIR
from planning_readiness import check as check_readiness

ROOT=Path(__file__).resolve().parents[1]

def run(snapshot_path, details_path, capacity_path, output, baseline=None, redesign=(), *, city_template=TEMPLATE_DIR/'city.json', production_template=TEMPLATE_DIR/'production.json'):
    started=time.perf_counter();started_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    if output.exists() and any(output.iterdir()):raise ValueError('Output must be empty; preserve previous runs as baselines')
    output.mkdir(parents=True,exist_ok=True);timings=[];cache={};manifest={}
    try:
        write_json(output/'readiness.json',check_readiness(city_template,production_template))
        snapshot,details,capacity=[json.loads(p.read_text('utf8')) for p in (snapshot_path,details_path,capacity_path)]
        validate_inputs(snapshot,details,capacity)
        write_json(output/'snapshot.json',snapshot);write_json(output/'details.json',details);write_json(output/'capacity.json',capacity)
        templates=load_templates(city_template,production_template)
        # Pin the exact normalized templates used for hashing and child processes.
        for kind,template in templates.items():
            write_json(output/'templates'/(kind+'.json'),template)
        source_files=['plan_pipeline.py','plan_flat_areas.py','planning_pipeline_core.py','plan_template_map.py','plan_network_complete.py','planning_flow.py','fullmap_workflow.py','fullmap_prepare.py','fullmap_hub_sets.py','fullmap_identity.py']
        source_files.extend(['planning_shared_hubs.py','planning_operations.py'])
        sources={name:(ROOT/'scripts'/name).read_text('utf8') for name in source_files}
        sources.update({name:(ROOT/'server/src/tf3_mcp'/name).read_text('utf8') for name in ['flat_areas.py','site_planner.py','route_planner.py','planning_geometry.py']})
        code=digest(sources)
        prior=json.loads((baseline/'pipeline.json').read_text('utf8')) if baseline and (baseline/'pipeline.json').exists() else {}
        if prior.get('status')!='complete':prior={}
        def intact(files):
            if not baseline:return False
            return all((baseline/f).exists() and prior.get('artifacts',{}).get(f)==digest(json.loads((baseline/f).read_text('utf8'))) for f in files)
        lk=digest([code,layout_key(snapshot,details,templates)])
        def stage(name,args):
            start=time.perf_counter()
            result=subprocess.run([sys.executable,str(ROOT/'scripts'/args[0]),*map(str,args[1:])],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
            atomic_write(output/(name+'.log'),result.stdout+result.stderr)
            timings.append(dict(stage=name,seconds=time.perf_counter()-start,cacheHit=False,success=result.returncode==0))
            if result.returncode:raise RuntimeError(name+' failed; see '+str(output/(name+'.log')))
        def reuse(name,files):
            start=time.perf_counter()
            for file in files:
                value=strip_native_evidence(json.loads((baseline/file).read_text('utf8')))
                if 'snapshot'in value:value['snapshot']=str((output/'snapshot.json').resolve())
                write_json(output/file,value)
            timings.append(dict(stage=name,seconds=time.perf_counter()-start,cacheHit=True,success=True))
        stage('flat_areas',['plan_flat_areas.py','--snapshot',output/'snapshot.json','--output',output])
        flat_report=json.loads((output/'flat_areas.json').read_text('utf8'))
        same=prior.get('keys',{}).get('layout')==lk and intact(['layout_draft.json'])
        if same and not redesign:
            reuse('layout',['layout_draft.json'])
        else:
            args=['plan_template_map.py','--snapshot',output/'snapshot.json','--output',output,
                  '--city-template',(output/'templates/city.json').resolve(),
                  '--production-template',(output/'templates/production.json').resolve()]
            if same and redesign:args+=['--baseline',baseline/'layout_draft.json','--redesign',*redesign]
            stage('layout',args)
        layout=json.loads((output/'layout_draft.json').read_text('utf8'))
        # A missing optional collection is not a missing transport service.
        # Network sizing rejects missing REQUIRED transfer endpoints after routing.
        normalized=dict(layout,snapshot='CURRENT_SNAPSHOT')
        nk=digest([code,normalized,details,capacity])
        if prior.get('keys',{}).get('network')==nk and intact(['network_plan.json','execution_manifest.json']) and not redesign:
            reuse('network',['network_plan.json','execution_manifest.json'])
        else:stage('network',['plan_network_complete.py','--output',output])
        # Geometry and dependency checks always run, including on cache hits.
        stage('preflight',['fullmap_workflow.py','--plan',output/'network_plan.json','--manifest',output/'execution_manifest.json','--snapshot',output/'snapshot.json','--output',output/'preflight'])
        review=json.loads((output/'preflight/preflight.json').read_text('utf8'))
        plan=json.loads((output/'network_plan.json').read_text('utf8'))
        refinement=[dict(owner=h['owner'],bounds=h['terrain_screen']['reserveBounds'],recommendedSpacingM=25)
                    for h in plan['hubs']if h.get('terrain_screen',{}).get('needsLocalSurvey')]
        queue=dict(buildAuthorized=False,nativePreviewsReusable=False,
            order=['shortlisted_flat_area_local_survey','representative_city_group','representative_production_group','coastal_water_sampling','remaining_building_groups','roads','stops','individual_diagnostics_only_for_rejected_groups'],
            localTerrainSurveys=refinement,
            shipRoutePolicy={'topology':'shipyard <-> harbor <-> each assigned fishing ground',
                             'directions':'diagnostics only: check outbound and return separately',
                             'diagnosticOnly':True,'requiredForCommissioning':False,
                             'cacheScope':'one engine evaluation; endpoints, direction, mode, navigation profile',
                             'readback':'ship_route_checks.py --plan <plan> --output <new-result> --readback --diagnose-round-trip',
                             'nativeVerified':False},
            maxCandidatesPerFailure=3,onUnknown='stop_and_reconcile',
            sharedHubCapacityChecks=plan.get('shared_hub_capacity_review',[]),
            citySitingComparisons=plan.get('city_siting_reviews',[]),
            collectionQuantityDecisions=plan.get('collection_quantity_decisions',{}),
            groups=[{'owner':h['owner'],'facilities':list(h['facilities'].values()),'roads':h['roads']} for h in plan['hubs']],
            standaloneFacilities=[f['id']for f in plan['facilities']+plan['ports']if f['id']not in {v for h in plan['hubs']for v in h['facilities'].values()}],
            fishPorts=[dict(port=p['id'],maintenance=p.get('maintenance_base'),purchase=p.get('purchase_base'),serviceIndustries=p['service_industries'],waterRoutes=p['water_routes_by_industry'],capacityReview=p['capacity_review'],template=p.get('collection_template'),status='experimental; separate shoreline survey then isolated joint preview',cargo='fish',oil='helicopter',buildAuthorized=False)for p in plan['ports']],
            note='Queue only. Preview groups before per-building diagnostics; never authorize construction from offline cache.')
        write_json(output/'review_queue.json',queue)
        stage('report',['plan_report.py','--output',output])
        manifest=dict(status='complete',startedAt=started_at,wallSeconds=time.perf_counter()-started,
            timingScope='this offline invocation only; NOT total user planning wall time',
            keys={'layout':lk,'network':nk},stages=timings,counters=review['counters'],
            requiresAttention=review['requires_attention']or bool(refinement)or bool(plan.get('city_siting_reviews')),nativePreviewRequired=True,buildAuthorized=False,
            flatAreas=flat_report['summary'],
            artifacts={f:digest(json.loads((output/f).read_text('utf8')))for f in ['flat_areas.json','layout_draft.json','network_plan.json','execution_manifest.json']})
        write_json(output/'pipeline.json',manifest)
        atomic_write(output/'README.md','# 规划准备结果\n\n'+
            f"离线流水线 {manifest['wallSeconds']:.3f} 秒；这是候选方案，尚未做当前游戏原生预览。\n\n"+
            '[交付索引](DELIVERY.md) · [启动检查](readiness.json) · [平整区域](flat_areas.json) · [地形图层](flat_areas.svg) · [城市供给](preflight/CITIES.md) · [设施坐标](preflight/facilities.csv) · [线路](preflight/ROUTES.md) · [问题](preflight/ISSUES.md) · [阶段计时](pipeline.json) · [原生检查队列](review_queue.json)\n\n'+
            '先处理代表性集合和岸线，再展开全图预览；失败仅诊断受影响集合，最多三个候选。未来施工前必须刷新会话、实体、端口并重新预览。\n')
        return manifest
    except Exception as error:
        write_json(output/'failure.json',dict(status='failed',error=str(error),stages=timings,seconds=time.perf_counter()-started))
        raise

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot','details','capacity','output'):ap.add_argument('--'+name,type=Path,required=True)
    for kind in ('city','production'):ap.add_argument('--'+kind+'-template',type=Path,default=TEMPLATE_DIR/(kind+'.json'),help='Portable template; defaults to repository config/planning_templates')
    ap.add_argument('--baseline',type=Path);ap.add_argument('--redesign',nargs='*',type=int,default=[])
    args=ap.parse_args();r=run(args.snapshot,args.details,args.capacity,args.output,args.baseline,args.redesign,city_template=args.city_template,production_template=args.production_template)
    print(json.dumps({k:r[k]for k in ('status','wallSeconds','stages','requiresAttention','buildAuthorized')}))
if __name__=='__main__':main()
