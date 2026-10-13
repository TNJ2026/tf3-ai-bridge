import asyncio
import json

import pytest

from tf3_mcp import server


def test_status_unconfigured_does_not_construct_game_transport(monkeypatch):
    monkeypatch.delenv('TF3_RECOVERY_CONFIG', raising=False)
    def forbidden(): raise AssertionError('must not connect')
    monkeypatch.setattr(server, 'bridge', forbidden)
    result = asyncio.run(server.recovery_control())
    assert result == dict(configured=False, monitorEnabled=False, launchEnabled=False)
    with pytest.raises(Exception, match='not configured'):
        asyncio.run(server.recovery_control('checkpoint'))


def test_configured_status_reads_local_ledger_only(tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'stateDirectory': str(tmp_path / 'state')}), encoding='utf-8')
    monkeypatch.setenv('TF3_RECOVERY_CONFIG', str(config))
    def forbidden(): raise AssertionError('must not connect')
    monkeypatch.setattr(server, 'bridge', forbidden)
    assert asyncio.run(server.recovery_control())['launches'] == 0
    assert not (tmp_path / 'state').exists()
