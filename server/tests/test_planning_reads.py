import asyncio

import pytest

from tf3_mcp.planning_reads import read_planning, chunks
from tf3_mcp.frontage_workflow import RoadsidePlacement


def requests(n):
    return [{'command': 'get_entity', 'arguments': {'id': i}} for i in range(n)]


def receipt(rows):
    return {'readBatchVersion': 1, 'readOnly': True, 'count': len(rows), 'complete': True,
            'results': [dict(index=i, command=r['command'], ok=True, executed=True,
                             result={'id': r['arguments']['id'], 'components': []})
                        for i, r in enumerate(rows)]}


def test_chunks_keep_order_and_validate_whole_round():
    assert [len(g) for g in chunks(requests(19))] == [8, 8, 3]
    calls = []
    async def call(*args):
        calls.append(args)
    with pytest.raises(ValueError):
        asyncio.run(read_planning(call, requests(9) + [{'command': 'build_road', 'arguments': {}}]))
    assert calls == []


def test_default_batching_and_global_indices():
    calls = []
    async def call(cmd, args):
        assert cmd == 'read_batch'
        calls.append(args)
        return receipt(args['requests'])
    result = asyncio.run(read_planning(call, requests(19)))
    assert len(calls) == result['batchCount'] == 3
    assert result['complete']
    assert [r['index'] for r in result['results']] == list(range(19))
    assert [r['result']['id'] for r in result['results']] == list(range(19))


@pytest.mark.parametrize('error,executed', [('response_size_limit', True), ('time_budget_exceeded', False)])
def test_only_limited_items_get_one_smaller_read(error, executed):
    calls = []
    async def call(cmd, args):
        rows = args['requests']; calls.append(rows)
        result = receipt(rows)
        result['results'][-1].update(ok=False, executed=executed, error=error)
        return result
    result = asyncio.run(read_planning(call, requests(3)))
    assert [len(c) for c in calls] == [3, 1]
    assert calls[1][0]['arguments']['id'] == 2
    assert not result['complete']


def test_native_failure_keeps_other_results_without_retry():
    calls = []
    async def call(cmd, args):
        calls.append(cmd)
        result = receipt(args['requests'])
        result['results'][0].update(ok=False, error='native failure')
        return result
    result = asyncio.run(read_planning(call, requests(2)))
    assert len(calls) == 1 and not result['complete'] and result['results'][1]['ok']


@pytest.mark.parametrize('failure', ['timeout', 'wrong_index'])
def test_unknown_or_mismatched_receipt_never_retried(failure):
    calls = []
    async def call(cmd, args):
        calls.append(cmd)
        if failure == 'timeout':
            raise TimeoutError('unknown')
        result = receipt(args['requests']); result['results'][0]['index'] = 9
        return result
    with pytest.raises((TimeoutError, ValueError)):
        asyncio.run(read_planning(call, requests(9)))
    assert len(calls) == 1


def test_frontage_batches_missing_components_and_reuses_round_cache():
    calls = []
    async def call(cmd, args):
        calls.append(cmd)
        return receipt(args['requests'])
    workflow = RoadsidePlacement(call, None, {}, lambda: None)
    assert asyncio.run(workflow.components([1, 2, 1], 'BASE_NODE_CONFIG')) == [None] * 3
    assert asyncio.run(workflow.components([2, 1], 'BASE_NODE_CONFIG')) == [None] * 2
    assert calls == ['read_batch']


def test_public_planning_tool_uses_batch(monkeypatch):
    from tf3_mcp import server
    calls = []
    async def call(cmd, **args):
        calls.append(cmd)
        return receipt(args['requests'])
    monkeypatch.setattr(server, '_call', call)
    assert asyncio.run(server.read_planning_data(requests(10)))['complete']
    assert calls == ['read_batch', 'read_batch']
