import pytest
from install_headless_diagnostic import select_receiver_mode


@pytest.mark.parametrize('path,expected,downloaded', [
    ('C:/Users/Public/mod.io/10640/mods/6449979/content/tf3_mcp_bridge', 'userdata', True),
    ('C:/Users/Public/MOD.IO/10640/mods/6449979/content/tf3_mcp_bridge', 'userdata', True),
    ('D:/game/staging_area/tnj_tf3_ai_bridge/content/tf3_mcp_bridge', 'demand', False),
    ('D:/mod.io-not-a-mount/content/tf3_mcp_bridge', 'demand', False),
])
def test_auto_mode(path, expected, downloaded):
    assert select_receiver_mode(path) == (expected, downloaded)


@pytest.mark.parametrize('mode,alias', [('demand', False), ('auto', True)])
def test_downloaded_demand_rejected_before_install(mode, alias):
    with pytest.raises(ValueError, match='mod.io mounts require userdata'):
        select_receiver_mode('C:/mod.io/mods/1/content/tf3_mcp_bridge', mode, alias)


def test_legacy_alias_and_explicit_indexed():
    assert select_receiver_mode('D:/staging_area/bridge', on_demand=True) == ('demand', False)
    assert select_receiver_mode('D:/staging_area/bridge', 'indexed') == ('indexed', False)
    with pytest.raises(ValueError, match='conflicts'):
        select_receiver_mode('D:/staging_area/bridge', 'indexed', True)
