"""Transport discovery must never execute the capabilities it enumerates."""
import json

import pytest

from test_e2e import MOCK_API, SCRIPT, lupa_mod


@pytest.mark.parametrize("available", [False, True])
def test_transport_discovery_is_passive_without_legacy_startup_poll(available):
    lua = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK_API)
    lua.execute('''
        app = nil
        capabilityCalls = 0
        local function forbidden()
            capabilityCalls = capabilityCalls + 1
            error("discovery invoked a capability")
        end
        ug = {readFile=forbidden}
        resolveutil = {resolve=forbidden}
        package = {loadlib=forbidden, path="do not log paths"}
        ug_require_cleanup = forbidden
    ''' if available else '''
        app=nil; ug=nil; resolveutil=nil; package=nil
        ug_require_cleanup=nil; capabilityCalls=0
    ''')
    logs = []
    lua.globals().debugPrint = logs.append
    script = lua.execute(SCRIPT.read_text(encoding="utf-8"))
    script["guiUpdate"](None, None, None)
    assert not any('userdata transport' in line or 'started in gui state' in line for line in logs)
    result = script['_internal']['commands']['ping'](lua.table())
    encoded = script['_internal']['json']['encode'](result['probe'])
    probe = json.loads(encoded)
    assert probe["transportDiscoveryVersion"] == 1
    if available:
        assert probe["ug_members"] == {"readFile": "function"}
        assert probe["package_members"]["loadlib"] == "function"
        assert "do not log paths" not in encoded
    else:
        assert not probe["ug_members"]
        assert probe["ug_require_cleanup"] == "nil"
    assert lua.globals().capabilityCalls == 0
    assert len(lua.globals().sentCommands) == 0
