"""Concrete opt-in integration with the existing vehicle batch executor."""
from .headless_workflows import VehicleBatches
from .recovery_runtime import RecoveryBlocked


async def execute_vehicle_batch(runtime, batch_id, operations, expected_session):
    """Requires a verified checkpoint; does not create one or authorize spending.

    Initial integration covers purchase, assignment and stopped-state changes.
    Return-to-depot/sale need separate arrival/cargo audits and are not opted in.
    """
    allowed = {'buy_vehicles', 'assign_vehicles', 'set_vehicle_stopped'}
    if not isinstance(operations, list) or not operations or any(
            not isinstance(op, dict) or op.get('command') not in allowed for op in operations):
        raise RecoveryBlocked('Recovery vehicle workflow supports buy/assign/stopped only')
    client = runtime.adapter.client
    batch = VehicleBatches(client, runtime.lock_directory)

    async def prepare():
        status = await client.status()
        if status['receiver']['session'] != expected_session or status.get('pending'):
            raise RecoveryBlocked('Vehicle batch session/pending mismatch')
        return {'session': expected_session, 'batch': batch_id}

    async def submit(prepared):
        return await batch.execute(batch_id, operations, prepared['session'])

    async def verify(result):
        if result.get('status') != 'completed':
            raise RecoveryBlocked('Vehicle batch incomplete; preserve both journals')
        # Later steps may assign a purchased vehicle. Compare the final native
        # readback for each identity, not obsolete intermediate depot/line state.
        expected = {}
        for step in result['steps']:
            if step['status'] != 'verified':
                raise RecoveryBlocked('Batch step not verified')
            args = step['arguments']
            ids = step['result']['bought'] if step['command'] == 'buy_vehicles' else (
                args.get('vehicles') or [args['vehicle']])
            if len(ids) != 1:
                raise RecoveryBlocked('Expected single-vehicle step')
            expected[ids[0]] = step['readback']['components']['TRANSPORT_VEHICLE']
        evidence = []
        for ident, before in expected.items():
            after = await client.call('get_entity', {'id': ident, 'components': ['TRANSPORT_VEHICLE']})
            current = after['components'].get('TRANSPORT_VEHICLE')
            if not current or any(current.get(key) != before[key]
                                  for key in ('line', 'depot', 'userStopped') if key in before):
                raise RecoveryBlocked('Final independent vehicle readback mismatch')
            evidence.append({'id': ident, 'readback': after})
        return {'verified': True, 'vehicles': evidence, 'operationalVerified': False}

    return await runtime.execute('vehicle-batch:' + batch_id,
                                 {'operations': operations}, prepare, submit, verify)
