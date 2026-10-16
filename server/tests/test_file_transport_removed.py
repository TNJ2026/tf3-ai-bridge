import asyncio
from pathlib import Path

import pytest

from tf3_mcp import server
from tf3_mcp.bridge import Bridge, BridgeError, encode_message, decode_message


def test_removed_configuration_never_dispatches(monkeypatch):
    monkeypatch.setenv('TF3_MCP_TRANSPORT', 'file')
    monkeypatch.setattr(server, 'no_gui_client', lambda: pytest.fail('unexpected dispatch'))
    with pytest.raises(Exception, match='file transport has been removed'):
        asyncio.run(server.get_game_state())


def test_default_is_no_gui_without_mod_path(monkeypatch):
    monkeypatch.delenv('TF3_MCP_TRANSPORT', raising=False)
    monkeypatch.delenv('TF3_MCP_NO_GUI_MOD', raising=False)
    assert server.transport_mode() == 'no_gui'  # internal compatible route


def test_historical_client_fails_without_writing(tmp_path):
    with pytest.raises(BridgeError, match='removed'):
        asyncio.run(Bridge(tmp_path).call('get_game_state'))
    assert list(tmp_path.iterdir()) == []


def test_userdata_codec_is_preserved():
    value={'id':'test', 'text':'中文'}
    assert decode_message(encode_message(value)) == value


def test_production_receiver_has_no_old_poll_or_event():
    source=(Path(__file__).parents[2]/'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua').read_text(encoding='utf-8')
    assert 'local function pollRequest' not in source
    assert 'bridgeTick(' not in source
    assert 'state:subscribeToEvent(ENGINE_EVENT)' not in source
    assert 'app.loadUserdata("mod_presets",mailbox)' in source
