"""Check load limits without running native commands or bridge callbacks."""
from pathlib import Path

import pytest

from validate_bridge_compile import check_bridge_compile

SOURCE = Path(__file__).resolve().parents[2] / 'mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua'


@pytest.mark.parametrize('demand', [False, True])
def test_bridge_compiles_with_loader_headroom(demand):
    text = SOURCE.read_text(encoding='utf-8')
    if demand:
        text = text.replace('local HEADLESS_GENERATION = "disabled"',
                            'local HEADLESS_GENERATION = "' + 'a' * 32 + '"')
        text = text.replace('local HEADLESS_ON_DEMAND = false', 'local HEADLESS_ON_DEMAND = true')
    result = check_bridge_compile(text)
    assert len(result['checks']) == 12 and not result['executed']


def test_compile_preflight_rejects_exhausted_locals():
    text = 'local ' + ','.join(f'v{i}' for i in range(200)) + '\nreturn {}'
    with pytest.raises(ValueError, match='reserved locals 16'):
        check_bridge_compile(text)


def test_compile_preflight_does_not_execute_source():
    assert check_bridge_compile('error("must not run")')['executed'] is False
