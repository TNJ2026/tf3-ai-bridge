"""Receiver-side batch tests; mocked engine, not live performance claims."""
import json

import pytest

from test_e2e import SCRIPT
from test_facilities import game
from test_no_gui import host
from test_ui_consolidated import Channel
from tf3_mcp.ui_log import validate_read_batch


def item(command='get_game_state', **args):
    return {'command': command, 'arguments': args}


@pytest.mark.parametrize('rows', [[], [item()] * 17, [item('read_batch')],
    [item('build_road')], [item('preview_road')], [item('save_game')],
    [item('run_lua')], [item('list_towns', limit=True)],
    [item('get_town_overview')], [{'command': 'get_game_state'}]])
def test_host_rejects_invalid(rows):
    with pytest.raises(ValueError):
        validate_read_batch({'requests': rows})


def test_single_dispatch_order(tmp_path):
    c = Channel(tmp_path)
    response = c.query('read_batch', {'requests': [item(), item('list_towns')]})
    assert response['ok'], response
    result = response['result']
    assert result['complete'] and result['count'] == 2
    assert [r['index'] for r in result['results']] == [0, 1]
    assert all(r['ok'] and r['executed'] for r in result['results'])
    assert c.lua.globals().dispatches == 0


def batch_runtime(game, setup):
    lua, _ = game
    script = lua.execute(SCRIPT.read_text(encoding='utf-8'))
    lua.globals().batchCommands = script['_internal']['commands']
    lua.execute(setup)
    def run(rows):
        result = script['_internal']['commands']['read_batch'](
            lua.table_from({'requests': rows}, recursive=True))
        return json.loads(script['_internal']['json']['encode'](result))
    return lua, run


def test_receiver_validates_all_before_execution(game):
    lua, run = batch_runtime(game, 'calls=0;batchCommands.get_game_state=function() calls=calls+1;return {} end')
    with pytest.raises(Exception, match='not allowed'):
        run([item(), item('build_road')])
    assert lua.globals().calls == 0


@pytest.mark.parametrize('bad', [item('list_towns', limit=True),
    item('get_town_overview'), item('get_game_state', unknown=1), item('read_batch')])
def test_receiver_rejects_bad_children(game, bad):
    lua, run = batch_runtime(game, 'calls=0;batchCommands.get_game_state=function() calls=calls+1;return {} end')
    with pytest.raises(Exception):
        run([item(), bad])
    assert lua.globals().calls == 0


def test_max_count_through_dispatcher(tmp_path):
    c = Channel(tmp_path)
    response = c.query('read_batch', {'requests': [item()] * 16})
    assert response['ok'], response
    assert response['result']['count'] == 16
    assert response['result']['complete']


def test_public_tool_forwards_one_request(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from tf3_mcp import server
    call = AsyncMock(return_value={'readBatchVersion': 1})
    monkeypatch.setattr(server, '_call', call)
    rows = [item(), item('get_finances')]
    assert asyncio.run(server.read_batch(rows)) == {'readBatchVersion': 1}
    call.assert_awaited_once_with('read_batch', _engine=True, requests=rows)


def test_item_errors_and_output_budget(game):
    _, run = batch_runtime(game, '''
      batchCommands.get_game_state=function() return {huge=string.rep('x',49000)} end
      batchCommands.get_finances=function() error('native failure') end
      batchCommands.list_towns=function() return {towns={}} end
    ''')
    result = run([item(), item('get_finances'), item('list_towns')])
    assert not result['complete']
    assert result['results'][0]['error'] == 'response_size_limit'
    assert 'native failure' in result['results'][1]['error']
    assert result['results'][2]['ok']
    assert len(json.dumps(result)) < 65536


def test_soft_time_budget(game):
    _, run = batch_runtime(game, '''
      clock=0;os.clock=function() return clock end
      batchCommands.get_game_state=function() clock=0.2;return {} end
    ''')
    result = run([item(), item()])
    assert result['results'][0]['ok']
    assert result['results'][1]['error'] == 'time_budget_exceeded'
    assert not result['results'][1]['executed']


def test_old_receiver_no_publication(host):
    with pytest.raises(ValueError, match='readBatchVersion'):
        host.send('read_batch', {'requests': [item()]}, kind='build', expected_session='session')
    assert not host.ledger.exists()
