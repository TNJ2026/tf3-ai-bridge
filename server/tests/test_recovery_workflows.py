import asyncio
import copy

import pytest

from test_recovery_runtime import Adapter, run
from tf3_mcp.no_gui_client import NoGuiClient
from tf3_mcp.recovery_runtime import RecoveryBlocked, RecoveryRuntime
from tf3_mcp.recovery_workflows import execute_vehicle_batch


class Client:
    map_digest = staticmethod(NoGuiClient.map_digest)
    def __init__(self):
        self.lock = asyncio.Lock()
        self.session = 'first'
        self.vehicle = None
        self.buys = 0
        self.bad_final = False
    async def status(self): return dict(receiver={'session': 'first'}, pending=None)
    async def call(self, cmd, args):
        result = await self.request(cmd, args)
        if self.bad_final:
            result['components']['TRANSPORT_VEHICLE']['line'] = 999
        return result
    async def request(self, cmd, args, on_ticket=None):
        if on_ticket: on_ticket({'id': 'native-request-' + cmd})
        if cmd == 'get_game_state': return dict(player=3, gameTime=100, speedup=0)
        if cmd == 'get_map_info': return dict(towns=[], industries=[], width=1, height=1)
        if cmd == 'buy_vehicles':
            self.buys += 1
            self.vehicle = dict(depot=args['depot'], line=-1, userStopped=False)
            return {'bought': [500]}
        if cmd == 'assign_vehicles':
            self.vehicle['line'] = args['line']
            self.vehicle['depot'] = -1
            return {'assigned': [500]}
        if cmd == 'get_entity':
            return {'components': {'TRANSPORT_VEHICLE': copy.deepcopy(self.vehicle)}}
        raise AssertionError(cmd)


def make(tmp_path):
    adapter = Adapter(tmp_path)
    adapter.client = Client()
    runtime = RecoveryRuntime(adapter, tmp_path / 'recovery', tmp_path / 'bridge')
    run(runtime.checkpoint())
    operations = [dict(command='buy_vehicles', arguments={'depot': 10, 'model': 'truck.mdl', 'count': 1}),
                  dict(command='assign_vehicles', arguments={'purchase_index': 0, 'line': 20, 'stop_index': 0})]
    return runtime, adapter.client, operations


def test_real_batch_journal_and_recovery_journal_never_double_buy(tmp_path):
    runtime, client, operations = make(tmp_path)
    result = run(execute_vehicle_batch(runtime, 'fleet1', operations, 'first'))
    assert result['status'] == 'verified'
    assert client.buys == 1 and client.vehicle['line'] == 20
    assert (tmp_path / 'bridge/vehicle_batches/fleet1.json').exists()
    assert run(execute_vehicle_batch(runtime, 'fleet1', operations, 'first')) == result
    assert client.buys == 1


def test_batch_name_is_not_part_of_quarantine_fingerprint(tmp_path):
    from tf3_mcp.recovery_runtime import digest
    runtime, client, operations = make(tmp_path)
    state = runtime.read()
    state['quarantinedPlans'] = [digest({'operations': operations})]
    runtime.write(state)
    with pytest.raises(RecoveryBlocked, match='quarantined'):
        run(execute_vehicle_batch(runtime, 'different-batch-id', operations, 'first'))
    assert client.buys == 0


def test_independent_fleet_readback_mismatch_stops_work(tmp_path):
    runtime, client, operations = make(tmp_path)
    client.bad_final = True
    with pytest.raises(RecoveryBlocked, match='readback'):
        run(execute_vehicle_batch(runtime, 'fleet1', operations, 'first'))
    assert runtime.read()['operations']['vehicle-batch:fleet1']['status'] == 'unknown'
    assert client.buys == 1


def test_depot_return_not_approved_by_old_empty_vehicle_record(tmp_path):
    runtime, client, _ = make(tmp_path)
    with pytest.raises(RecoveryBlocked, match='buy/assign/stopped'):
        run(execute_vehicle_batch(runtime, 'fleet1', [{'command': 'send_to_depot',
                                     'arguments': {'vehicle': 500}}], 'first'))
    assert client.buys == 0
