import asyncio
import copy
from tf3_mcp.map_cache import MapCache
from tf3_mcp.staged_planner import plan_staged, detour, profile, town_regions
from test_route_planner import snapshot
from test_e2e import bridge_dir


def test_staged_straight():
    r=plan_staged(snapshot())
    assert r['candidates'] and r['candidates'][0]['length']==4000
    assert r['stages'][0]=='straight'


def test_town_detour_and_endpoint_exception():
    s=snapshot();town=dict(entity='town:1',kind='TOWN_REGION',min=dict(x=1700,y=-200,z=0),max=dict(x=2300,y=200,z=0))
    p=detour((0,0),(4000,0),[],[town],s['grid'])
    assert len(p)>2 and any(abs(y)>200 for x,y in p)
    assert detour((1900,0),(4000,0),[],[town],s['grid'])==[(1900,0),(4000,0)]


def test_bridge_ramp_and_impossible_endpoint():
    xy=[(i*50,0) for i in range(81)];ground=[(2,False)]*len(xy)
    road=dict(entity=7,kind='BASE_EDGE',min=dict(x=1990,y=-5,z=2),max=dict(x=2010,y=5,z=3))
    z,d,c=profile(xy,ground,[road],2,2,.025,'over')
    assert z[40]>=13 and z[0]==z[-1]==2 and c==[7]
    assert all(abs(a-b)<=1.25+1e-8 for a,b in zip(z,z[1:]))
    road['min']['x']=0;road['max']['x']=20
    assert profile(xy,ground,[road],2,2,.025,'over') is None


def test_cache_delta_deletion_and_terrain_reuse(tmp_path):
    async def run():
        s=snapshot();s.update(domain='a',revisions={'7':'1','8':'1'},terrainRevisions={'1':'1'},delta=False)
        s['obstacles']=[{'entity':7},{'entity':8}]
        calls=[]
        async def fetch(args):
            calls.append(args)
            if len(calls)==1:return copy.deepcopy(s)
            return dict(domain='a',revisions={'7':'2'},terrainRevisions={'1':'1'},delta=True,
                        obstacles=[{'entity':7,'changed':True}],stations=s['stations'],state=s['state'])
        c=MapCache(fetch,tmp_path/'cache.json')
        first,_=await c.refresh(1,2);_,status=await c.refresh(1,2)
        assert status['hit'] and len(calls)==1
        second,_=await c.refresh(1,2,force=True)
        assert second['grid']==first['grid'] and second['obstacles']==[{'entity':7,'changed':True}]
        assert calls[-1]['revisions']=={'7':'1','8':'1'}
        c.invalidate();assert c.snapshot is None
    asyncio.run(run())


def test_background_stop_and_error():
    async def run():
        async def fetch(args):raise RuntimeError('offline')
        c=MapCache(fetch)
        try:await c.start(1,2)
        except RuntimeError:pass
        assert not c.status()['polling'] and c.status()['error']=='offline'
        await c.stop()
    asyncio.run(run())

def test_staged_building_detour():
    s=snapshot();s['obstacles']=[dict(entity=5,kind='MODEL_INSTANCE_LIST',
        min=dict(x=1850,y=-150,z=0),max=dict(x=2150,y=150,z=30))]
    r=plan_staged(s)
    assert r['candidates'] and r['candidates'][0]['length']>4000


def test_two_clients_serialize(bridge_dir):
    from test_e2e import FakeGame
    from legacy_file_transport_fixture import Bridge
    async def run():
        a,b=Bridge(bridge_dir,timeout=5),Bridge(bridge_dir,timeout=5)
        responses=await asyncio.gather(a.call('ping',{'echo':'first'}),b.call('ping',{'echo':'second'}))
        assert responses[0]['echo']=='first' and responses[1]['echo']=='second'
    with FakeGame(bridge_dir):asyncio.run(run())

def test_lua_snapshot_full_then_delta(bridge_dir):
    from test_e2e import FakeGame, run
    from legacy_file_transport_fixture import Bridge
    with FakeGame(bridge_dir) as game:
        game.lua.execute('''
        local CT=api.type.ComponentType
        for i,k in ipairs({'MODEL_INSTANCE_LIST','TOWN_BUILDING','BOUNDING_VOLUME','STATION','VEHICLE_DEPOT'}) do
          if not CT[k] then CT[k]=9000+i end
        end
        local function p(x,y,z)return {x=x,y=y,z=z}end
        for i=1,2 do
          components[60000+i]={[CT.CONSTRUCTION]={transf={getTransl=function()return p(i*100,100,0)end},
            frozenNodes={},frozenEdges={61000+i},stations={}}}
          components[61000+i]={[CT.BASE_EDGE]={roadType=api.type.enum.RoadType.TRACK,node0=62000+i,node1=63000+i,
            tangent0=p(1,0,0),tangent1=p(1,0,0)}}
          components[62000+i]={[CT.BASE_NODE]={position=p(i*100,100,0)}}
          components[63000+i]={[CT.BASE_NODE]={position=p(i*100+50,100,0)}}
        end
        components[64000]={[CT.TOWN_BUILDING]={town=77},[CT.BOUNDING_VOLUME]={bbox={min=p(200,200,0),max=p(220,220,20)}}}
        api.engine.system.streetSystem.getNodeSegments=function(n)return {61000+n%1000}end
        api.engine.terrain.getBoundingBox=function()return {min=p(0,0,0),max=p(500,500,0)}end
        api.engine.terrain.getHeightAt=function()return 0 end
        api.engine.terrain.isOnWater=function()return false end
        api.engine.terrain.getTerrainEntityRevisions=function()return {[1]={num={1,0,0}}}end
        api.engine.getRevision=function(id)return {num={1,0,0}}end
        api.engine.util.octree.findEntitiesInCircle=function(p,r,ct)
          if ct==CT.TOWN_BUILDING then return {64000}end
          return {}
        end
        ''')
        b=Bridge(bridge_dir,timeout=5)
        args=dict(start_construction=60001,end_construction=60002,whole_map=True,spacing=100)
        first=run(b.call('get_route_snapshot',args))
        assert len(first['grid']['heights'])==36
        assert first['obstacles'][0]['town']==77
        args.update(domain=first['domain'],revisions=first['revisions'],terrain_revisions=first['terrainRevisions'])
        second=run(b.call('get_route_snapshot',args))
        assert second['delta'] and 'grid' not in second and second['obstacles']==[]
