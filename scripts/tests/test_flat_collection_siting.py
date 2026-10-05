"""Exercise collection terrain ranking and the pipeline flat-layer stage offline."""
import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from plan_template_map import collection_candidates
from plan_flat_areas import run
from tf3_mcp.flat_areas import FlatTerrain


def test_fixed_geometry_cache_invalidates_geometry_but_never_caches_modules():
    from plan_template_map import compiled_footprints,_compiled_footprints,materialize_candidate
    t=dict(facilities=[dict(role='truck',localPosition=dict(x=0,y=0),relativeRotation=0,params={'seed':1})],
           roads=[dict(position0=dict(x=-20,y=0),position1=dict(x=20,y=0))])
    sizes={'truck':(10,10)};_compiled_footprints.cache_clear()
    first=compiled_footprints(t,sizes)
    t['facilities'][0]['params']['seed']=2
    assert compiled_footprints(t,sizes) is first
    c=dict(origin=dict(x=300,y=400),rotation=0)
    result=materialize_candidate(c,t,first[0]);assert result['fac'][0][0]['params']['seed']==2
    result['boxes'][0]['min']['x']=-999
    assert materialize_candidate(c,t,first[0])['boxes'][0]['min']['x']==290
    t['facilities'][0]['upgradeReserveM']={'maxY':25}
    assert compiled_footprints(t,sizes) is not first
    assert compiled_footprints(t,{'truck':(11,10)}) is not first


def test_lazy_and_eager_candidates_have_same_rank_and_geometry():
    from plan_template_map import compiled_footprints,materialize_candidate
    g=dict(x=-1000,y=-1000,nx=81,ny=81,spacing=25,
           heights=[(i%81)*.01 for i in range(6561)],water=[False]*6561)
    t=dict(facilities=[dict(role='truck',localPosition=dict(x=13,y=7),relativeRotation=35,
           upgradeReserveM={'maxY':20})],roads=[dict(position0=dict(x=-20,y=0),position1=dict(x=20,y=0))])
    sizes={'truck':(10,15)};nodes={1:dict(x=0,y=0),2:dict(x=200,y=100)}
    args=(t,[1,2],nodes,'production',FlatTerrain(g),sizes,dict(x=0,y=0))
    eager=collection_candidates(*args);lazy=collection_candidates(*args,materialize=False)
    geometry={c['rotation']:c for c in compiled_footprints(t,sizes)}
    assert len(eager)==len(lazy)>0
    assert all('fac'not in c and 'boxes'not in c for c in lazy)
    assert eager==[materialize_candidate(c,t,geometry[c['rotation']])for c in lazy]


def test_whole_collection_ranking_checks_upgrade_area_and_prefers_flat_farther_anchor():
    g=dict(x=-500,y=-500,nx=61,ny=21,spacing=50,water=[False]*(61*21),
           heights=[max(0,25-i%61)*1.5 for i in range(61*21)])
    template=dict(facilities=[dict(role='truck',localPosition=dict(x=0,y=0),relativeRotation=0)],
                  roads=[dict(position0=dict(x=-20,y=0),position1=dict(x=20,y=0))])
    nodes={1:dict(x=0,y=0),2:dict(x=1200,y=0)};before=copy.deepcopy(template)
    candidates=collection_candidates(template,[1,2],nodes,'production',FlatTerrain(g),{'truck':(10,10)},dict(x=0,y=0))
    assert candidates[0]['node']==2 and candidates[0]['flatPreferred']
    assert candidates[0]['terrain']['heightRangeM']==0 and template==before
    # The estimated 20 m reserve is larger than the current footprint.
    best=candidates[0];assert best['terrainReserve']['min']['x']<best['boxes'][0]['min']['x']


def test_prepare_layer_exports_json_svg_and_tracks_snapshot_grid(tmp_path):
    g=dict(x=0,y=0,nx=5,ny=5,spacing=50,heights=[0]*25,water=[False]*25)
    snapshot=tmp_path/'snapshot.json';snapshot.write_text(json.dumps(dict(grid=g)),encoding='utf8')
    result=run(snapshot,tmp_path/'output')
    assert result['summary']['flatCells']==16 and result['gameCalls']==0
    assert (tmp_path/'output/flat_areas.svg').exists()
    saved=json.loads((tmp_path/'output/flat_areas.json').read_text('utf8'))
    assert saved['snapshot']==str(snapshot.resolve())and saved['sampledOnly']


def test_real_layout_entry_uses_layer_and_reports_nonflat_fallback(tmp_path,monkeypatch):
    import plan_template_map
    root=tmp_path/'project';(root/'scripts').mkdir(parents=True);(root/'exports').mkdir()
    city_positions={'heliport':(150,130),'warehouse':(150,-130),'truck':(0,70),'bus':(0,-70),'road_depot':(-130,70)}
    for kind,registry,positions in [('city','hub_template_default.json',city_positions),('production','hub_template_production_default.json',{'helipad':(100,70),'helipad2':(150,70),'warehouse':(150,-70),'truck':(0,70)})]:
        template=dict(facilities=[dict(role=r,resource=r,localPosition=dict(x=p[0],y=p[1]),relativeRotation=0,params=dict(modules={}))for r,p in positions.items()],
                      roads=[dict(node0=10,node1=11,position0=dict(x=-80,y=0),position1=dict(x=220,y=0),roadTemplate='country/country_new_small')])
        if kind=='city':template['facilities'][0]['upgradeReserveM']={'maxY':20}
        (root/'exports'/(kind+'.json')).write_text(json.dumps(template),encoding='utf8')
    g=dict(x=-2000,y=-2000,nx=81,ny=81,spacing=50,heights=[0]*6561,water=[False]*6561)
    road=dict(kind='BASE_EDGE',entity=2,node0=10,node1=11,position0=dict(x=600,y=0,z=0),position1=dict(x=850,y=0,z=0),
              tangent0=dict(x=250,y=0,z=0),tangent1=dict(x=250,y=0,z=0),min=dict(x=600,y=-3),max=dict(x=850,y=3))
    s=dict(grid=g,bounds=dict(min=dict(x=-2000,y=-2000),max=dict(x=2000,y=2000)),state=dict(player=1,date=dict(year=1960)),
           map=dict(towns=[dict(id=1,name='Test',position=dict(x=0,y=0))],industries=[]),
           obstacles=[road,dict(kind='TOWN_BUILDING',entity=4,min=dict(x=-20,y=-20),max=dict(x=20,y=20))])
    d=dict(buildings=[dict(id=4,town=1)],industries=[],frozenNodes=[])
    monkeypatch.setattr(plan_template_map,'__file__',str(root/'scripts/plan_template_map.py'))
    for kind in ('flat','sloped'):
        output=tmp_path/kind;output.mkdir();survey=output/'snapshot.json'
        if kind=='sloped':g['heights']=[(i//81)*2 for i in range(6561)]
        survey.write_text(json.dumps(s),encoding='utf8');(output/'details.json').write_text(json.dumps(d),encoding='utf8')
        monkeypatch.setattr(sys,'argv',['plan_template_map.py','--snapshot',str(survey),'--output',str(output),'--city-template',str(root/'exports/city.json'),'--production-template',str(root/'exports/production.json')])
        plan_template_map.main()
        result=json.loads((output/'layout_draft.json').read_text('utf8'));assert not result['unresolved']
        assert len(result['facilities'])==5 and result['build_authorized']is False
        airport=next(f for f in result['facilities']if f['kind']=='heliport')
        assert airport['reserved']['max']['y']-airport['footprint']['max']['y']==20
        assert airport['upgrade_reserve_m']=={'maxY':20}
        h=result['hubs'][0];assert h['city_boundary_distance_m']>=520 and h['terrain_screen']['needsLocalSurvey']
        assert h['terrain_screen']['flatPreferred']==(kind=='flat')
        assert bool(h['terrain_screen']['fallbackReason'])==(kind=='sloped')
        assert (output/'flat_areas.svg').exists()


def test_pipeline_runs_flat_stage_before_layout_and_invalidates_changed_terrain(tmp_path,monkeypatch):
    import plan_pipeline
    from types import SimpleNamespace
    root=tmp_path/'project';(root/'scripts').mkdir(parents=True);(root/'server/src/tf3_mcp').mkdir(parents=True);(root/'exports').mkdir()
    script_names=['plan_pipeline.py','plan_flat_areas.py','planning_pipeline_core.py','plan_template_map.py','plan_network_complete.py','planning_flow.py','fullmap_workflow.py','fullmap_prepare.py','fullmap_hub_sets.py','fullmap_identity.py','planning_shared_hubs.py']
    for name in script_names:(root/'scripts'/name).write_text('offline fixture',encoding='utf8')
    for name in ['flat_areas.py','site_planner.py','route_planner.py','planning_geometry.py']:(root/'server/src/tf3_mcp'/name).write_text('fixture',encoding='utf8')
    for kind,registry,roles in [('city','hub_template_default.json',['heliport','warehouse','truck','bus','road_depot']),('production','hub_template_production_default.json',['helipad','helipad2','warehouse','truck'])]:
        (root/'exports'/(kind+'.json')).write_text(json.dumps(dict(facilities=[dict(role=r,resource=r,params={},localPosition=dict(x=0,y=0),relativeRotation=0)for r in roles],roads=[dict(node0=0,node1=1,position0=dict(x=0,y=0),position1=dict(x=1,y=0),roadTemplate='road')])),encoding='utf8')
    s=dict(state=dict(player=1),map=dict(towns=[dict(id=1)],industries=[dict(id=2,fileName='farm',position=dict(x=0,y=0))]),
           grid=dict(x=0,y=0,nx=3,ny=3,spacing=50,heights=[0]*9,water=[False]*9),obstacles=[])
    d=dict(state=dict(player=1),industries=[dict(id=2,construction=3,resource='farm',position=dict(x=0,y=0))],buildings=[])
    c=dict(industries=[dict(id=2)])
    inputs=[]
    for name,value in [('snapshot',s),('details',d),('capacity',c)]:
        path=tmp_path/(name+'.json');path.write_text(json.dumps(value),encoding='utf8');inputs.append(path)
    template_args=dict(city_template=root/'exports/city.json',production_template=root/'exports/production.json')
    calls=[]
    def stage(command,**kwargs):
        name=Path(command[1]).name;output=Path(command[command.index('--output')+1]);calls.append(name)
        if name=='plan_flat_areas.py':run(Path(command[command.index('--snapshot')+1]),output)
        elif name=='plan_template_map.py':
            assert (output/'flat_areas.json').exists()
            for kind in ('city','production'):
                supplied=Path(command[command.index('--'+kind+'-template')+1])
                assert supplied==output/'templates'/(kind+'.json')
                assert supplied.exists()
            # Actual layout_draft tracks geometry inputs even when chosen sites are unchanged.
            from tf3_mcp.flat_areas import grid_digest
            surveyed=json.loads((output/'snapshot.json').read_text('utf8'))
            h=dict(owner='T1',facilities={},roads=[],terrain_screen=dict(needsLocalSurvey=True,reserveBounds=dict(min=dict(x=0,y=0),max=dict(x=100,y=100))))
            plan=dict(snapshot=str(output/'snapshot.json'),layout_input_key=grid_digest(surveyed['grid']),facilities=[],hubs=[h],roads=[],ports=[],unresolved=[],native_verified=False)
            (output/'layout_draft.json').write_text(json.dumps(plan),encoding='utf8')
        elif name=='plan_network_complete.py':
            (output/'network_plan.json').write_text((output/'layout_draft.json').read_text('utf8'),encoding='utf8')
            (output/'execution_manifest.json').write_text('{}',encoding='utf8')
        elif name=='fullmap_workflow.py':
            output.mkdir();(output/'preflight.json').write_text(json.dumps(dict(counters={},requires_attention=False)),encoding='utf8')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(plan_pipeline,'ROOT',root);monkeypatch.setattr(plan_pipeline.subprocess,'run',stage)
    first=plan_pipeline.run(*inputs,tmp_path/'first',**template_args)
    assert calls==['plan_flat_areas.py','plan_template_map.py','plan_network_complete.py','fullmap_workflow.py','plan_report.py']
    assert first['flatAreas']['flatCells']==4 and 'flat_areas.json'in first['artifacts']
    queue=json.loads((tmp_path/'first/review_queue.json').read_text('utf8'))
    assert first['requiresAttention']and queue['localTerrainSurveys'][0]['owner']=='T1'
    calls.clear();second=plan_pipeline.run(*inputs,tmp_path/'second',baseline=tmp_path/'first',**template_args)
    assert calls==['plan_flat_areas.py','fullmap_workflow.py','plan_report.py']
    assert all(x['cacheHit']for x in second['stages']if x['stage']in ('layout','network'))
    calls.clear();s['grid']['heights'][0]=1;inputs[0].write_text(json.dumps(s),encoding='utf8')
    plan_pipeline.run(*inputs,tmp_path/'third',baseline=tmp_path/'second',**template_args)
    assert calls==['plan_flat_areas.py','plan_template_map.py','plan_network_complete.py','fullmap_workflow.py','plan_report.py']

def test_city_ranking_does_not_trade_kilometres_for_tiny_slope_gain():
    from tf3_mcp.flat_areas import city_preference_key
    def profile(grade):return dict(outsideSurvey=False,dry=True,maxGroundGrade=grade,heightRangeM=3)
    assert city_preference_key(profile(.061),profile(.04),900)<city_preference_key(profile(.060),profile(.04),2100)
    assert city_preference_key(profile(.25),profile(.04),900)>city_preference_key(profile(.04),profile(.04),2100)


def test_city_candidates_exclude_disconnected_road_anchors():
    g=dict(x=-500,y=-500,nx=81,ny=61,spacing=50,heights=[0]*(81*61),water=[False]*(81*61))
    t=dict(facilities=[dict(role='truck',localPosition=dict(x=0,y=0),relativeRotation=0)],roads=[dict(position0=dict(x=-20,y=0),position1=dict(x=20,y=0))])
    rows=collection_candidates(t,[1,2],{1:dict(x=600,y=0),2:dict(x=1000,y=0)},'city',FlatTerrain(g),{'truck':(10,10)},dict(x=0,y=0),city_network_distances={2:1100})
    assert rows and {r['node']for r in rows}=={2}
