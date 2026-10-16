"""New-channel migration: guards, immutable paging and orchestration failures."""
import asyncio
import copy
import json

import pytest

from tf3_mcp.no_gui_client import NoGuiClient, NoGuiOutcomeUnknown
from tf3_mcp.no_gui_workflows import VehicleBatches, OperationsMonitor
from tf3_mcp.ui_log import validate_build_arguments
from test_ui_extended_reads import query


class Requests:
    def __init__(self):
        self.session = 'current'
        self.calls = []
        self.pending = None
        self.responses = {}
        self.outcome = 'received'

    def status(self):
        return dict(receiver=dict(session=self.session, status='ready'), ageSeconds=0, pending=self.pending)

    def send(self, command, arguments, **kwargs):
        assert kwargs['expected_session'] == self.session
        ident = str(len(self.calls))
        self.calls.append((command, copy.deepcopy(arguments)))
        return dict(id=ident)

    def read(self, ident):
        command, args = self.calls[int(ident)]
        if self.outcome != 'received':
            return {'status': self.outcome}
        value = self.responses.get(command, {'ok': True})
        if callable(value):
            value = value(args)
        return dict(status='received', response=dict(ok=True, result=value))


def test_named_transport_does_not_use_file_fallback(monkeypatch):
    from tf3_mcp import server
    r = Requests()
    r.responses['get_game_state'] = {'speedup': 0}
    monkeypatch.setenv('TF3_MCP_TRANSPORT', 'no_gui')
    monkeypatch.setattr(server, '_no_gui_client', NoGuiClient(r, 0))
    monkeypatch.setattr(server, 'bridge', lambda: pytest.fail('file bridge used'))
    assert asyncio.run(server.get_game_state()) == {'speedup': 0}
    with pytest.raises(Exception, match='not implemented'):
        asyncio.run(server._call('eval', code='error("unsafe")'))
    assert len(r.calls) == 1


def test_timeout_never_retries_and_session_change_blocks():
    async def run():
        r = Requests()
        c = NoGuiClient(r, 0)
        r.outcome = 'timeout_unknown'
        with pytest.raises(NoGuiOutcomeUnknown, match='read this ID'):
            await c.call('get_game_state')
        assert len(r.calls) == 1
        r.session = 'reloaded'
        with pytest.raises(ValueError, match='session changed'):
            await c.call('get_game_state')
        assert len(r.calls) == 1
    asyncio.run(run())


def test_cached_planner_rejects_reloaded_session(monkeypatch):
    from tf3_mcp import server
    from tf3_mcp.map_cache import MapCache
    r = Requests()
    client = NoGuiClient(r, 0)
    client.session = 'previous'
    cache = MapCache(None)
    cache.snapshot = {'no_guiSession': 'previous'}
    monkeypatch.setenv('TF3_MCP_TRANSPORT', 'no_gui')
    monkeypatch.setattr(server, '_no_gui_client', client)
    monkeypatch.setattr(server, '_map_cache', cache)
    with pytest.raises(Exception, match='session changed'):
        asyncio.run(server.plan_rail_connection(1, 2))
    assert cache.snapshot is None and not r.calls


def test_map_poll_stops_after_first_error():
    from tf3_mcp.map_cache import MapCache
    async def run():
        calls = []
        async def fetch(args):
            calls.append(args)
            if len(calls) > 1:
                raise ValueError('receiver lost')
            return dict(grid={}, obstacles=[], domain='test', revisions={}, terrainRevisions={})
        cache = MapCache(fetch, interval=.001)
        await cache.start(1, 2)
        await asyncio.wait_for(cache.task, timeout=1)
        assert len(calls) == 2 and cache.error == 'receiver lost'
        assert not cache.status()['polling']
    asyncio.run(run())


def test_vehicle_batch_stops_on_purchase_readback_mismatch(tmp_path):
    class WrongDepot(WorkflowClient):
        async def request(self, command, args, **kwargs):
            if command == 'get_entity':
                return dict(components={'TRANSPORT_VEHICLE': {'depot': 999}})
            return await super().request(command, args, **kwargs)
    async def run():
        client = WrongDepot()
        operations = [dict(command='buy_vehicles', arguments=dict(depot=1, model='truck', count=1)),
                      dict(command='assign_vehicles', arguments=dict(purchase_index=0, line=5, stop_index=0))]
        result = await VehicleBatches(client, tmp_path).execute('mismatch', operations, 'current')
        assert result['status'] == 'stopped_incomplete'
        assert 'depot readback mismatch' in result['error']
        assert not any(command == 'assign_vehicles' for command, _ in client.calls)
    asyncio.run(run())


@pytest.mark.parametrize('corrupt', [False, True])
def test_snapshot_reassembly_checks_byte_identity(corrupt):
    async def run():
        r = Requests()
        c = NoGuiClient(r, 0)
        raw = json.dumps(dict(state={'player': 2}, grid='中文' * 5000), ensure_ascii=False).encode()
        r.responses['begin_snapshot'] = dict(snapshot='token', bytes=len(raw), session='current', state={'player': 2})
        def page(args):
            offset = args['offset']
            data = raw[offset:offset+6000]
            return dict(snapshot='other' if corrupt else 'token', offset=offset, session='current', totalBytes=len(raw),
                        nextOffset=offset+len(data), hex=data.hex())
        r.responses['read_snapshot_page'] = page
        if corrupt:
            with pytest.raises(ValueError, match='page mismatch'):
                await c.call('get_planning_snapshot', {'spacing': 250})
            assert r.calls[-1][0] == 'read_snapshot_page'
        else:
            assert (await c.call('get_planning_snapshot', {'spacing': 250}))['grid'] == '中文' * 5000
            assert r.calls[-1][0] == 'release_snapshot'
    asyncio.run(run())


def test_speed_readback_precondition_and_unsupported_bulk():
    async def run():
        r = Requests()
        r.responses['get_game_state'] = {'speedup': 4}
        c = NoGuiClient(r, 0)
        await c.call('set_game_speed', {'speed': 0})
        assert r.calls[-1] == ('set_game_speed', {'speed': 0, 'expected_speed': 4})
        with pytest.raises(ValueError, match='batch'):
            await c.call('buy_vehicles', {'count': 3})
        with pytest.raises(ValueError, match='preview'):
            await c.call('build_road', {'preview': False})
        assert len(r.calls) == 2
    asyncio.run(run())


def test_legacy_defaults_adapt_without_discarding_meaningful_options():
    async def run():
        r = Requests()
        client = NoGuiClient(r, 0)
        await client.call('build_warehouse', dict(x=1, y=2, z=3, rotation=0, name='', preview=True, module_count=4))
        assert r.calls[-1] == ('build_warehouse', dict(x=1, y=2, z=3, rotation=0, module_count=4))
        await client.call('list_facility_resources', dict(kind='construction', search='', limit=100, offset=0))
        assert 'search' not in r.calls[-1][1]
        result = await client.call('get_terrain_grid', dict(spacing=64, offset=0, limit=512, mode='surface'))
        assert r.calls[-1][1]['limit'] == 100 and result['requestedLimit'] == 512
        await client.call('configure_facility', dict(entity=1, parameters={'capacity': 2}, modules=[]))
        assert r.calls[-1] == ('preview_facility_parameter', dict(entity=1, key='capacity', value=2))
        with pytest.raises(ValueError, match='combined replacement'):
            await client.call('configure_facility', dict(entity=1, parameters={'x': 1, 'y': 2}))
        with pytest.raises(ValueError, match='Unsupported no_gui option'):
            await client.call('build_road', dict(preview=True, allow_collisions=True))
    asyncio.run(run())


def test_terrain_named_commit_uses_verified_no_gui_save(monkeypatch, tmp_path):
    from tf3_mcp import server
    class BridgeDir:
        dir = tmp_path / 'bridge'
    monkeypatch.setattr(server, 'bridge', lambda: BridgeDir())
    monkeypatch.setenv('TF3_MCP_TRANSPORT', 'no_gui')
    calls = []
    async def call(command, **args):
        calls.append((command, args))
        if command == 'save_game': return dict(verified=True, file={'path': 'test.sav'})
        assert command == 'commit_flatten_terrain'
        assert args['backup_save'] == calls[0][1]['slot']
        return {'verified': True}
    monkeypatch.setattr(server, '_call', call)
    assert asyncio.run(server.commit_flatten_terrain('token'))['verified']
    assert [name for name, _ in calls] == ['save_game', 'commit_flatten_terrain']


def test_unpaused_save_is_rejected_without_sending_save():
    async def run():
        r = Requests()
        r.responses['get_game_state'] = {'speedup': 4}
        with pytest.raises(ValueError, match='Pause before saving'):
            await NoGuiClient(r, 0).call('save_game', {'slot': 'test'})
        assert [name for name, _ in r.calls] == ['get_game_state']
    asyncio.run(run())


def test_component_selection_and_paging_survive_engine_recreation(query):
    result = query('get_entity', {'id': 100, 'components': ['TOWN']})
    assert result['ok'], result
    assert set(result['result']['components']) == {'TOWN'}
    query.lua.execute('components[900]={[api.type.ComponentType.LINE]={stops={{stationGroup=200},{stationGroup=201},{stationGroup=202}}}}')
    result = query('get_component_collection', dict(id=900, component='LINE', field='stops', offset=1, limit=1))
    assert result['ok'], result
    assert result['result']['total'] == 3 and result['result']['items'][0]['value']['stationGroup'] == 201
    rejected = query('get_component_collection', dict(id=900, component='LINE', field='unknown', offset=0, limit=1))
    assert not rejected['ok']


@pytest.mark.parametrize('bad', [[], ['TOWN', 'TOWN'], ['bad-name'], [True]])
def test_component_input_bounds(bad):
    with pytest.raises(ValueError):
        validate_build_arguments('get_entity', {'id': 100, 'components': bad})


def survey_fixture(query):
    query.lua.execute('''
      local CT=api.type.ComponentType
      for i,k in ipairs({'BASE_EDGE','TOWN_BUILDING','STATION','MODEL_INSTANCE_LIST','BOUNDING_VOLUME'}) do CT[k]=800+i end
      local function p(x,y,z)return {x=x,y=y,z=z or 0}end
      api.type.Vec2f={new=function(x,y)return p(x,y)end}
      api.engine.terrain={getBoundingBox=function()return {min=p(0,0),max=p(1000,1000)}end,
        getBaseResolution=function()return p(4,4)end,getHighResolution=function()return p(1,1)end,
        getHeightAt=function()return 2 end,isOnWater=function()return false end,
        getTerrainEntityRevisions=function()return {[1]={num={1,0,0}}}end,
        makeMapFromGame=function()return {towns={},industries={},climateId='temperate'}end}
      api.engine.getRevision=function()return {num={1,0,0}}end
      api.engine.util.octree={findEntitiesInCircle=function()return {}end}
      now=1;os.clock=function()return now end
    ''')


@pytest.mark.parametrize('mode', ['normal', 'expired', 'replaced', 'bad_route'])
def test_native_snapshot_is_fixed_paged_and_released(query, mode):
    survey_fixture(query)
    if mode == 'bad_route':
        assert not query('begin_snapshot', {'snapshot_kind': 'route'})['ok']
        return
    header = query('begin_snapshot', {'snapshot_kind': 'planning', 'spacing': 25})
    assert header['ok'], header
    token = header['result']['snapshot']
    if mode == 'expired':
        query.lua.globals().now = 602
    if mode == 'replaced':
        assert query('begin_snapshot', {'snapshot_kind': 'planning'})['ok']
    offset, raw = 0, b''
    while True:
        response = query('read_snapshot_page', {'snapshot': token, 'offset': offset})
        if mode != 'normal':
            assert not response['ok']
            return
        assert response['ok'], response
        page = response['result']
        raw += bytes.fromhex(page['hex'])
        offset = page['nextOffset']
        if not page['hasMore']:
            break
    assert len(raw) == header['result']['bytes']
    assert len(json.loads(raw)['grid']['heights']) == 1681
    assert query('release_snapshot', {'snapshot': token})['ok']
    assert not query('read_snapshot_page', {'snapshot': token, 'offset': 0})['ok']


def line_fixture(query):
    query.lua.execute('''
      now=1;os.clock=function()return now end;calls=0
      local CT=api.type.ComponentType
      components[700]={[CT.LINE]={customFilters=false,reservationPriority=1,stops={}},[CT.PLAYER_OWNED]={player=2}}
      components[300]={}
      for i=1,3 do
       components[199+i]={[CT.STATION_GROUP]={stations={209+i}}}
       components[209+i]={[CT.STATION]={terminals={{vehicleNodeId={entity=300,index=0},personNodes={},cargoLoad=true,cargoUnload=true,passengersLoad=true,passengersUnload=true}}}}
       components[700][CT.LINE].stops[i]={stationGroup=199+i,station=0,terminal=0,
        waypoints={{tag=7}},alternativeTerminals={{station=0,terminal=0}},maxAdditionalWaitingTime=3,
        stopConfig={load={true,true},maxLoad={1,1},forceUnload=false,destroyForConfigChange=false,destroyForRefresh=false}}
      end
      api.type.Line.StopConfig={new=function()return {}end}
      api.res.cargoTypeRep={getAll=function()return {[0]='PASSENGERS',[1]='COAL'}end}
      api.cmd.makeLineUpdateCmd=function(id,config)return {id=id,config=config}end
      api.cmd.sendCommand=function(cmd,cb)
       if cmd.name then forwarded=cmd;return end
       calls=calls+1;components[cmd.id][CT.LINE]=cmd.config;cb({},true,{})
      end
    ''')


@pytest.mark.parametrize('mode', ['normal', 'changed', 'expired', 'missing_terminal', 'readback_bad'])
def test_complex_line_reorder_add_remove_and_stale_guard(query, mode):
    line_fixture(query)
    edits = [{'source_index': 2, 'max_load': .5}, {'station_group': 200, 'station': 0, 'terminal': 0, 'loads': [1]}]
    preview = query('preview_line_edit', {'line': 700, 'stops': edits})
    assert preview['ok'], preview
    assert query.lua.globals().calls == 0
    if mode == 'changed':
        query.lua.execute('components[700][api.type.ComponentType.LINE].stops[1].waypoints={{tag=8}}')
    if mode == 'expired':
        query.lua.globals().now = 100
    if mode == 'missing_terminal':
        query.lua.execute('components[210][api.type.ComponentType.STATION].terminals={}')
    if mode == 'readback_bad':
        query.lua.execute('api.cmd.makeLineUpdateCmd=function(id,config)config.stops[1].terminal=1;return {id=id,config=config}end')
    response = query('commit_line_stop', {'preview_token': preview['result']['preview_token']})
    assert response['ok'] == (mode == 'normal'), response
    if mode in ('changed', 'expired', 'missing_terminal'):
        assert query.lua.globals().calls == 0
    if mode == 'normal':
        line = query.lua.globals().components[700][query.lua.globals().api.type.ComponentType.LINE]
        assert len(line['stops']) == 2
        assert line['stops'][1]['stationGroup'] == 202
        assert line['stops'][1]['waypoints'][1]['tag'] == 7
        assert line['stops'][1]['stopConfig']['maxLoad'][1] == .5
        assert line['stops'][2]['stopConfig']['load'][2]
        assert not line['stops'][2]['stopConfig']['load'][1]
    assert not query('commit_line_stop', {'preview_token': preview['result']['preview_token']})['ok']


def test_line_edit_supports_more_than_eight_stops_and_long_payload(query):
    line_fixture(query)
    args = {'line': 700, 'stops': [{'source_index': i % 3, 'extra_wait': 50} for i in range(32)]}
    preview = query('preview_line_edit', args)
    assert preview['ok'] and preview['result']['stopCount'] == 32, preview
    assert query('commit_line_stop', {'preview_token': preview['result']['preview_token']})['ok']


@pytest.mark.parametrize('edit', [[{'source_index': 0}], [{'source_index': True}] * 2,
    [{'source_index': 0, 'station_group': 200}] * 2, [{'station_group': 200}] * 2,
    [{'source_index': 0, 'loads': [1, 1]}] * 2, [{'source_index': 0, 'max_load': float('nan')}] * 2])
def test_invalid_line_edits_rejected_before_dispatch(edit):
    with pytest.raises(ValueError):
        validate_build_arguments('preview_line_edit', {'line': 700, 'stops': edit})


class WorkflowClient:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.session = 'current'
        self.calls = []
        self.line = None
        self.fail_assign = False

    map_digest = staticmethod(NoGuiClient.map_digest)

    async def status(self):
        return dict(receiver={'session': self.session}, pending=None)

    async def request(self, command, args, on_ticket=None):
        self.calls.append((command, args))
        if on_ticket:
            on_ticket({'id': str(len(self.calls))})
        if command == 'get_game_state': return dict(balance=100, player=2, world=1, gameTime=1)
        if command == 'get_map_info': return dict(towns=[], industries=[])
        if command == 'buy_vehicles': return dict(bought=[101], failures=[])
        if command == 'assign_vehicles':
            if self.fail_assign: raise NoGuiOutcomeUnknown('lost callback')
            self.line = args['line']
            return dict(assigned=[101], line=self.line, failures=[])
        if command == 'get_entity': return dict(components={'TRANSPORT_VEHICLE': {'line': self.line, 'depot': 1}})
        raise AssertionError(command)


@pytest.mark.parametrize('failed', [False, True])
def test_vehicle_batch_durable_reference_and_no_restart_replay(tmp_path, failed):
    async def run():
        client = WorkflowClient()
        client.fail_assign = failed
        batch = VehicleBatches(client, tmp_path)
        operations = [dict(command='buy_vehicles', arguments=dict(depot=1, model='truck', count=1)),
                      dict(command='assign_vehicles', arguments=dict(purchase_index=0, line=5, stop_index=0))]
        first = await batch.execute('test', operations, 'current')
        assert first['status'] == ('stopped_incomplete' if failed else 'completed')
        assert first['steps'][1]['arguments']['vehicles'] == [101]
        calls = len(client.calls)
        assert await VehicleBatches(client, tmp_path).execute('test', operations, 'current') == first
        assert len(client.calls) == calls
        operations[0]['arguments']['model'] = 'other'
        with pytest.raises(ValueError, match='identity differs'):
            await batch.execute('test', operations, 'current')
    asyncio.run(run())


def test_monitor_busy_round_is_skipped(tmp_path):
    async def run():
        client = WorkflowClient()
        monitor = OperationsMonitor(client, tmp_path)
        async with client.lock:
            assert (await monitor.once())['status'] == 'skipped_busy'
        assert client.calls == [] and not monitor.status()['running']
    asyncio.run(run())


def test_autoaccept_restart_retains_intent_before_send(tmp_path):
    from tf3_mcp.subventions import SubventionAutoAccept
    from test_subventions import proposed
    path = tmp_path / 'auto.json'
    async def run():
        sent = []
        async def call(cmd, **args):
            if cmd == 'get_subventions': return dict(activeCount=0, tasks=[proposed(uid=1)], transportSession='s')
            saved = json.loads(path.read_text())
            assert saved['attempted']['1']['result'] == 'intent'
            sent.append(args['uid'])
            raise NoGuiOutcomeUnknown('unknown')
        one = SubventionAutoAccept(call, path)
        one.dry_run = False
        await one.run_once()
        two = SubventionAutoAccept(call, path)
        two.dry_run = False
        assert (await two.run_once())['pending'] == [1]
        assert sent == [1]
    asyncio.run(run())


def test_monitor_native_population_and_invalid_stock_not_queried(query):
    query.lua.execute('''
      api.type.enum.LandUseType={RESIDENTIAL=0}
      api.engine.util.town={getTownCapacityUsage=function(id)assert(id==100);return {{used=170,capacity=200}}end}
      local CT=api.type.ComponentType;CT.TOWN_BUILDING=901;CT.STOCK_LIST=902
      components[910]={[901]={town=100,stockList=920}}
      components[911]={[901]={town=100,stockList=-1}}
      components[920]={[902]={}}
      api.res.cargoTypeRep={getAll=function()return {[0]='PASSENGERS',[1]='COAL'}end}
      stockCalls=0
      api.engine.util.stock={
       getCargoMaxConsumptionPerYear=function(id,cargo)assert(id==920);stockCalls=stockCalls+1;return cargo==1 and 100 or 0 end,
       getCargoConsumedPerYear=function(id,cargo)assert(id==920 and cargo==1);return 30 end,
       getCargoTypeDeliveredPerYear=function(id,cargo)assert(id==920 and cargo==1);return 40 end}
    ''')
    population = query('get_town_population', {'town': 100})
    assert population['ok'] and population['result']['population'] == 170, population
    stats = query('get_town_building_stats', {'ids': [910, 911]})
    assert stats['ok'], stats
    assert stats['result']['items'][0]['cargos'][0] == dict(cargo=1, demand=100, consumed=30, delivered=40)
    assert stats['result']['items'][1]['available'] is False
    assert query.lua.globals().stockCalls == 2


def test_monitor_samples_deltas_without_mutations_or_duplicate_notices(tmp_path):
    class MonitorClient(WorkflowClient):
        def __init__(self):
            super().__init__()
            self.fault = True
            self.maintenance = .3
        async def request(self, command, args, **kwargs):
            self.calls.append((command, args))
            if command == 'get_game_state': return dict(balance=100, player=2, world=1, gameTime=1)
            if command == 'get_map_info': return dict(towns=[{'id': 100}], industries=[])
            if command in ('get_finances', 'get_loans'): return {}
            if command == 'get_subventions': return {'tasks': [dict(uid=1, status='Proposed')]}
            if command == 'get_town_population': return {'population': 170}
            if command == 'get_town_cargo_needs': return {'weighted_needs': {'residential': [[1, 1]]}}
            if command == 'get_town_deliveries': return {'items': []}
            if command == 'list_map_entities':
                ids = {'TOWN_BUILDING': [910], 'LINE': [5], 'TRANSPORT_VEHICLE': [101]}[args['kind']]
                return dict(snapshot='token', offset=0, items=[{'id': i} for i in ids], hasMore=False)
            if command == 'release_map_snapshot': return {'released': True}
            if command == 'get_town_building_stats':
                return {'items': [dict(id=910, town=100, stock_list=920, available=True, cargos=[dict(cargo=1, demand=100, consumed=50, delivered=60)])]}
            if command == 'get_entity':
                if args['id'] == 5: return dict(id=5, components={'LINE': {}, 'PLAYER_OWNED': {'player': 2}})
                return dict(id=101, components={'PLAYER_OWNED': {'player': 2}, 'TRANSPORT_VEHICLE': dict(noPath=self.fault,
                    userStopped=False, transportVehicleConfig={'vehicles': [{'maintenanceState': self.maintenance}]})})
            raise AssertionError(command)
    async def run():
        client = MonitorClient()
        monitor = OperationsMonitor(client, tmp_path)
        first = await monitor.once()
        assert {e['type'] for e in first['events']} == {'cash_reserve_low'}
        assert (await monitor.once())['events'] == []
        restarted = OperationsMonitor(client, tmp_path)
        assert (await restarted.once())['events'] == []
        client.fault = False
        client.maintenance = .8
        assert {e['type'] for e in (await restarted.once())['events']} == set()
        assert restarted.previous['towns'] == []
        assert restarted.previous['accountWatch']['income'] is None
        assert {c for c, _ in client.calls} == {'get_game_state','get_map_info','get_finances'}
        assert not monitor.status()['running']
        assert all(c.startswith(('get_', 'list_', 'release_')) for c, _ in client.calls)
    asyncio.run(run())


@pytest.mark.parametrize('changed', [True, False])
def test_autoaccept_adapter_previews_terms_before_commit(changed):
    async def run():
        r = Requests()
        r.responses['preview_subvention'] = dict(preview_token='p', task={'toDeliver': 30 if changed else 20})
        r.responses['commit_subvention'] = dict(verified=False, submitted=True)
        r.responses['get_subvention_operation'] = dict(verified=True, submitted=True)
        client = NoGuiClient(r, 0)
        if changed:
            with pytest.raises(ValueError, match='terms changed'):
                await client.call('accept_subvention', {'uid': 1, 'expect': {'toDeliver': 20}})
            assert [c for c, _ in r.calls] == ['preview_subvention']
        else:
            assert (await client.call('accept_subvention', {'uid': 1, 'expect': {'toDeliver': 20}}))['verified']
            assert [c for c, _ in r.calls] == ['preview_subvention', 'commit_subvention', 'get_subvention_operation']
    asyncio.run(run())
