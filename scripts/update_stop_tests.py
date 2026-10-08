from pathlib import Path
p=Path('server/tests/test_e2e.py');s=p.read_text(encoding='utf-8');a=s.index('def test_build_street_stop_tries_until_no_collision');b=s.index('\ndef test_bulldoze_depot',a)
s=s[:a]+'''def test_street_stop_apply_cannot_be_enabled_by_experimental_flag(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        for args in ({"preview": False}, {"experimental": True},
                     {"experimental": True, "preview": True, "allow_collisions": True}):
            r = run(b.call("build_street_stop", args))
            assert r["code"] == "street_stop_apply_unavailable"
            assert r["built"] is False and r["mutationAttempted"] is False
        assert game.lua.globals().builds == 0


def test_street_stop_preview_remaps_crosswalks_and_lanes(bridge_dir):
    b = Bridge(bridge_dir, timeout=5)
    with FakeGame(bridge_dir) as game:
        game.lua.execute("""
            local CT = api.type.ComponentType
            CT.BASE_NODE_CONFIG = 180
            api.type.LaneConnection = { new = function() return {} end }
            api.type.BaseNodeLaneConnectionAndEntity = { new = function() return {} end }
            for _, n in ipairs({STREET_A, STREET_B}) do
                components[n][180] = {crosswalks={EDGE_AB,EDGE_BC}, laneConnections={
                    {segment0=EDGE_AB, segment1=EDGE_BC,lane0=0,lane1=1,withRoad=true,withTram=false}}}
            end
            api.engine.util.proposal.makeProposalData = function(p)
                assert(#p.streetProposal.nodeConfigsToAdd == 2)
                assert(#p.streetProposal.nodeConfigsToRemove == 2)
                for _, c in ipairs(p.streetProposal.nodeConfigsToAdd) do
                    assert(c.comp.crosswalks[1] == -1)
                    assert(c.comp.crosswalks[2] == EDGE_BC)
                    assert(c.comp.laneConnections[1].segment0 == -1)
                    assert(c.comp.laneConnections[1].segment1 == EDGE_BC)
                end
                return {errorState={critical=false,messages={},warnings={}},costs=123,
                        collisionInfo={collisionEntities={}}}
            end
        """)
        r = run(b.call("build_street_stop", {"edge": game.lua.globals().EDGE_AB,
                                            "two_sided": True}))
        assert r["ok"] is True and r["preview"] is True
        assert r["cost"] == 123 and r["applySupported"] is False
        assert r["built"] is False and r["mutationAttempted"] is False
        assert r["model"].endswith("small_old_twosided.con")
        assert game.lua.globals().builds == 0


'''+s[b:];p.write_text(s,encoding='utf-8')
