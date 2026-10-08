from pathlib import Path
p=Path('server/tests/test_e2e.py');s=p.read_text(encoding='utf-8');s+='''

@pytest.mark.parametrize("owner,has_station,preview", [(-1, False, True), (-1, False, False), (5004, False, False), (-1, True, False)])
def test_orphan_stop_cleanup_is_restricted(bridge_dir, owner, has_station, preview):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.globals().ORPHAN_OWNER = owner
        game.lua.globals().ORPHAN_STATION = has_station
        game.lua.execute("""
            local CT=api.type.ComponentType
            components[9001] = {[CT.EDGE_OBJECT]={edgeObjectConstruction="::/stations/street/small_stops/small_mid.con"}}
            if ORPHAN_STATION then components[9001][CT.STATION]={} end
            api.engine.system.streetSystem.getEdgeForEdgeObject = function() return ORPHAN_OWNER end
            api.engine.util.proposal.makeProposalData = function(p)
                assert(p.streetProposal.edgesToRemove == nil)
                assert(#p.streetProposal.edgeObjectsToRemove == 1)
                assert(p.streetProposal.edgeObjectsToRemove[1] == 9001)
                return {errorState={critical=false,messages={},warnings={}},collisionInfo={collisionEntities={}},costs=0}
            end
            local send=api.cmd.sendCommand
            api.cmd.sendCommand=function(cmd, cb)
                if cmd.kind=="build" then
                    builds=builds+1;components[9001]=nil;cb({},true,{})
                else send(cmd,cb) end
            end
        """)
        if owner >= 0 or has_station:
            with pytest.raises(BridgeError, match="cleanup refused"):
                run(b.call("repair_orphan_street_stop", {"entity": 9001,"preview":preview}))
            assert game.lua.globals().builds == 0
        else:
            r = run(b.call("repair_orphan_street_stop", {"entity":9001,"preview":preview}))
            assert r["removed"] is (not preview)
            assert r["mutationAttempted"] is (not preview)
            assert game.lua.globals().builds == int(not preview)
''';p.write_text(s,encoding='utf-8')
p=Path('STREET_STOP_INTERFACE.md');s=p.read_text(encoding='utf-8');s='''# Active simulation crash investigation — 2026-09-30 22:33 CST

The previous "verified" results below are static topology checks, NOT proof of
simulation safety. Both 22:26:58 and 22:33:51 crashes assert in
SimEntityUpdateHelper.cpp:384, MakePersonCapacityData. Root cause is unresolved.

All 1,253 town buildings/person-capacity records, 1,381 node references and
2,125 residents' destinations/targets passed structural checks. Orphan stop
76059 was safely removed with a standalone edge-object removal proposal.
Simulation ran 6.6 seconds successfully, then crashed after about 20 additional
seconds with the SAME assertion. Orphan cleanup is not a crash fix.

Current comparison needed: load tf3_mudanjiang_bus_line_20260930 (no vehicles),
paused. The last loaded game contained all 4 Cityrama buses despite the requested
no-vehicle baseline. Do not claim the vehicle model caused the crash without
comparison. tf3_person_capacity_repair_20260930 is an orphan-cleaned checkpoint,
NOT a proven fixed save. All earlier snapshots are preserved.

A restricted repair_orphan_street_stop interface was added, defaults to preview,
requires a recognized stop resource, no road owner and no STATION component;
it submits only one strict object removal and never changes roads.

'''+s;p.write_text(s,encoding='utf-8')
