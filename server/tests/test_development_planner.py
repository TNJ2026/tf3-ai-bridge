import asyncio
import copy
import json
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from tf3_mcp.development_planner import plan_global, plan_local, supply_balance, validate_snapshot, save_json
from tf3_mcp.planning_report import export_report


def snapshot():
    return dict(grid=dict(x=0,y=0,nx=21,ny=21,spacing=50,heights=[2]*441,water=[False]*441),
                map=dict(towns=[dict(id=1,name='镇江',position=dict(x=100,y=100)),
                               dict(id=2,name='邻城',position=dict(x=800,y=800))],industries=[]),
                state=dict(tickCount=42),obstacles=[])


def bounds(x,y,w=100):
    return dict(min=dict(x=x,y=y),max=dict(x=x+w,y=y+w))


def site(name='仓储园区',x=400):
    return dict(name=name,current=bounds(x,400),reserved=bounds(x,400,200),basis='估算，待原生模块尺寸核验')


def chain():
    return dict(name='鱼类',cargo='fish',time_unit='game_minute',evidence='forecast',
                demand=10,production=20,transport=15,handling=12,delivery=8,batch=100,delay=2,storage=100)


def test_global_focus_supply_and_immutability():
    s=snapshot(); original=copy.deepcopy(s)
    p=plan_global(s,1,supply_chains=[chain()])
    assert p['neighbors'][0]['town']==2
    assert p['routes'][0]['status']=='concept' and p['buildable'] is None
    assert p['supply'][0]['effectiveDelivery']==8
    assert p['supply'][0]['storageGap']==20
    assert p['supply'][0]['unmetDemand']==2
    assert s==original
    with pytest.raises(ValueError):plan_global(s,999)


def test_unknown_and_invalid_rates():
    assert plan_global(snapshot(),1)['supply']==[]
    c=chain();c['demand']=None
    with pytest.raises(ValueError):supply_balance([c])
    c=chain();c['delay']=float('nan')
    with pytest.raises(ValueError):supply_balance([c])
    with pytest.raises(ValueError):supply_balance([chain(),chain()])


def test_reserves_detect_existing_and_proposed_conflicts():
    s=snapshot();s['obstacles']=[dict(entity=9,kind='MODEL_INSTANCE_LIST',**bounds(550,450))]
    p=plan_local(s,[site(),site('工厂',550)])
    assert p['sites'][0]['conflicts']==[9]  # Current footprint is clear, upgrade space is not.
    assert p['sites'][0]['siteConflicts']==['工厂']
    assert p['sites'][1]['siteConflicts']==['仓储园区']
    assert all(r['status']=='conflict' for r in p['sites'])


def test_reserve_containment_and_outside_survey():
    entry=site();entry['reserved']=bounds(420,420)
    with pytest.raises(ValueError):plan_local(snapshot(),[entry])
    p=plan_local(snapshot(),[site(x=900)])
    assert p['sites'][0]['status']=='needs_survey'


def test_interior_water_is_detected():
    s=snapshot();s['grid']['water'][10*21+10]=True
    p=plan_local(s,[site()])
    assert p['sites'][0]['waterSamples']>0


def test_corridor_avoids_reserve_and_reports_crossing():
    s=snapshot();s['obstacles']=[dict(entity=20,kind='BASE_EDGE',**bounds(740,0,30))]
    p=plan_local(s,[site()],corridors=[dict(name='配送',mode='road',start=dict(x=100,y=500),end=dict(x=900,y=500))])
    route=p['routes'][0]
    assert route['status']=='corridor_only' and route['length']>800
    assert all(not (380<=p['x']<=620 and 380<=p['y']<=620) for p in route['path'])
    assert p['buildable'] is None


def test_blocked_corridor_and_bad_mode():
    c=dict(name='x',mode='rail',start=dict(x=450,y=450),end=dict(x=900,y=900))
    assert plan_local(snapshot(),[site()],[c])['routes'][0]['status']=='no_candidate'
    c['mode']='water'
    with pytest.raises(ValueError):plan_local(snapshot(),corridors=[c])


def test_incomplete_snapshot_is_rejected():
    s=snapshot();s['grid']['heights'].pop()
    with pytest.raises(ValueError):validate_snapshot(s)


def test_report_exports_same_scene_and_escapes_html(tmp_path):
    p=plan_local(snapshot(),[site()],supply_chains=[chain()],title='<script>alert(1)</script>镇江')
    result=export_report(p,tmp_path)
    from pathlib import Path
    svg=Path(result['files']['svg']).read_text(encoding='utf-8')
    ET.fromstring(svg)
    html=Path(result['files']['html']).read_text(encoding='utf-8')
    assert '<script>alert(1)</script>' not in html and '&lt;script&gt;' in html
    assert 'data-toggle="reserved"' in html and '<svg' in html and 'http://' not in html.replace('http://www.w3.org/2000/svg','')
    with Image.open(result['files']['png']) as image:
        assert image.size==(1600,1100) and len(image.getcolors(2000000))>10
    assert json.loads(Path(result['files']['json']).read_text(encoding='utf-8'))['snapshotDigest']==p['snapshotDigest']
    assert export_report(p,tmp_path)['files']!=result['files']


def test_mcp_offline_pipeline_never_calls_game(tmp_path,monkeypatch):
    from tf3_mcp import server
    async def forbidden(*args,**kwargs):raise AssertionError('offline planning called game')
    monkeypatch.setattr(server,'_call',forbidden)
    path=save_json(snapshot(),tmp_path,'snapshot')
    async def run():
        g=(await server.plan_global_development(path,1,str(tmp_path),supply_chains=[chain()])).structured_content
        l=(await server.plan_local_development(path,str(tmp_path),sites=[site()])).structured_content
        assert g['plan_path'] and l['sites']
        assert (await server.export_planning_report(l['plan_path'],str(tmp_path))).structured_content['files']['png']
    asyncio.run(run())


def test_native_survey_without_stations():
    from test_e2e import MOCK_API, SCRIPT, lupa_mod
    lua=lupa_mod.LuaRuntime();lua.execute(MOCK_API)
    lua.execute('''
      local CT=api.type.ComponentType
      for i,k in ipairs({'BASE_EDGE','TOWN_BUILDING','STATION','MODEL_INSTANCE_LIST','BOUNDING_VOLUME'}) do CT[k]=800+i end
      local function p(x,y,z)return {x=x,y=y,z=z or 0}end
      api.type.Vec2f={new=function(x,y)return p(x,y)end}
      api.engine.terrain={
        getBoundingBox=function()return {min=p(0,0),max=p(1000,1000)}end,
        getBaseResolution=function()return p(4,4)end,
        getHighResolution=function()return p(1,1)end,
        getHeightAt=function()return 2 end,isOnWater=function()return false end,
        getTerrainEntityRevisions=function()return {[1]={num={1,0,0}}}end,
        makeMapFromGame=function()return {towns={},industries={},climateId='temperate'}end
      }
      components[888]={[CT.BOUNDING_VOLUME]={bbox={min=p(400,400),max=p(450,450)}}}
      api.engine.getRevision=function()return {num={1,0,0}}end
      api.engine.util.octree={findEntitiesInCircle=function(_,_,ct)if ct==CT.CONSTRUCTION then return {888}end return {}end}
      api.cmd.sendCommand=function()error('survey must not send commands')end
    ''')
    b=lua.execute(SCRIPT.read_text(encoding='utf-8'))['_internal']
    def call(args):return json.loads(b['json']['encode'](b['commands']['get_planning_snapshot'](lua.table_from(args,recursive=True))))
    s=call(dict(spacing=250))
    assert s['scope']=='global' and len(s['grid']['heights'])==25
    assert s['obstacles'][0]['entity']==888 and 'stations' not in s
    s=call(dict(spacing=50,bounds=bounds(100,200,200)))
    assert s['scope']=='local' and s['grid']['x']==100 and s['grid']['y']==200
    for args in (dict(spacing=500,bounds=bounds(0,0,100)),dict(bounds=bounds(-10,0)),dict(spacing=24)):
        with pytest.raises(Exception):call(args)
