from pathlib import Path
p=Path('server/tests/test_e2e.py');s=p.read_text(encoding='utf-8');s=s.replace('@pytest.mark.parametrize("has_nodes", [True, False])\ndef test_street_stop_preview_remaps_crosswalks_and_lanes(bridge_dir, has_nodes):','@pytest.mark.parametrize("has_nodes,apply", [(True, False), (False, False), (False, True), (True, True)])\ndef test_street_stop_preview_remaps_crosswalks_and_lanes(bridge_dir, has_nodes, apply):')
a=s.index('def test_street_stop_preview_remaps');b=s.index('\ndef test_bulldoze_depot',a);part=s[a:b];part=part.replace('local CT = api.type.ComponentType','''local CT = api.type.ComponentType
            STOP_BUILD_CALLS = 0
            local send = api.cmd.sendCommand
            api.cmd.sendCommand = function(cmd, cb)
                if cmd.kind == "build" then
                    STOP_BUILD_CALLS = STOP_BUILD_CALLS + 1
                    error("native build failed after submission")
                end
                return send(cmd, cb)
            end''',1)
part=part.replace('"two_sided": True}))','"two_sided": True, "preview": not apply}))',1)
part=part.replace('assert r["ok"] is has_nodes and r["preview"] is True','''assert r["preview"] is (not apply)
        if apply and has_nodes:
            assert r["code"] == "street_stop_needs_reconciliation"
            assert r["mutationAttempted"] is True and r["built"] is False
            assert game.lua.globals().STOP_BUILD_CALLS == 1
            return
        assert r["ok"] is has_nodes
        assert game.lua.globals().STOP_BUILD_CALLS == 0''');s=s[:a]+part+s[b:];p.write_text(s,encoding='utf-8')
p=Path('STREET_STOP_INTERFACE.md');s=p.read_text(encoding='utf-8');s='''# Current status: verified live construction (2026-09-30 22:16 CST)

The native edge-object reference fix has now been applied successfully in the loaded
map. All six planned dual-sided stops (12 stop objects) were built. Replacement
roads: 75140, 62321, 61160, 62140, 75984, 62232. Both directions of the planned
15-node bus circuit pass pathfinding. No line or vehicles have been created.

MCP `build_street_stop` defaults to preview. `preview=false` now submits once,
only after geometry, collisions and terminal network checks pass, then verifies
resulting stations against the replacement road's network. Legacy experimental
bypass stays disabled. Failure returns `street_stop_needs_reconciliation` and
never retries. Existing road objects are rejected to prevent duplicate builds.

Saved to `tf3_mudanjiang_bus_stops_verified_20260930.sav` (52,228,782 bytes).
Game remained running after save. Reload of this final save is not yet tested.
The earlier orphan object 76059 remains; no unsafe removal was attempted.
Evidence: stop_first_verify.json, stop_remaining_built.json,
stop_complete_connectivity.json. The following sections are historical diagnosis.

'''+s;p.write_text(s,encoding='utf-8')
