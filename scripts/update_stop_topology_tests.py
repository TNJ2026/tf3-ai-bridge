from pathlib import Path
p=Path('scripts/save_stop_checkpoint.py');s=p.read_text(encoding='utf-8');s=s.replace('function() _G.tf3StopCheckpointDone=true end','function() end');p.write_text(s)
p=Path('mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua');s=p.read_text(encoding='utf-8');a=s.index('local function previewProposal');b=s.index('-- Applies a proposal',a);part=s[a:b].replace('\treturn r\nend','\treturn r, pd\nend');s=s[:a]+part+s[b:];s=s.replace('local check = previewProposal(proposal)\n\tlocal ok, pd = pcall(api.engine.util.proposal.makeProposalData, proposal, nil)\n\tlocal tn = ok and pd and pd.entity2tn[-1] or nil','local check, pd = previewProposal(proposal)\n\tlocal tn = pd and pd.entity2tn and pd.entity2tn[-1] or nil');t=p.with_suffix('.lua.tmp');t.write_text(s,encoding='utf-8');t.replace(p)
p=Path('server/tests/test_e2e.py');s=p.read_text(encoding='utf-8');s=s.replace('def test_street_stop_preview_remaps_crosswalks_and_lanes(bridge_dir):','@pytest.mark.parametrize("has_nodes", [True, False])\ndef test_street_stop_preview_remaps_crosswalks_and_lanes(bridge_dir, has_nodes):');start=s.index('def test_street_stop_preview_remaps');end=s.index('def test_bulldoze_depot',start);part=s[start:end];part=part.replace('game.lua.execute("""','game.lua.globals().STOP_HAS_NODES = has_nodes\n        game.lua.execute("""',1);part=part.replace('CT.BASE_NODE_CONFIG = 180','CT.BASE_NODE_CONFIG = 180\n            api.type.enum.TransportMode = {BUS=3}')
part=part.replace('assert(#p.streetProposal.nodeConfigsToAdd == 2)','''local sp = p.streetProposal
                assert(#sp.edgeObjectsToAdd == 2)
                assert(sp.edgeObjectsToAdd[1].left == false and sp.edgeObjectsToAdd[2].left == true)
                assert(sp.edgeObjectsToAdd[1].params.year == 1850)
                assert(sp.edgesToAdd[1].comp.objects[1][1] == -400000000)
                assert(sp.edgesToAdd[1].comp.objects[2][1] == -400000001)
                assert(#p.streetProposal.nodeConfigsToAdd == 2)''')
part=part.replace('collisionInfo={collisionEntities={}}}', '''collisionInfo={collisionEntities={}},entity2tn={[-1]={
                            nodes=STOP_HAS_NODES and {{},{},{},{}} or {},
                            edges=STOP_HAS_NODES and {
                                {conns={{entity=-1,index=0},{entity=-1,index=2}},transportModes={[0]=true}},
                                {conns={{entity=-1,index=1},{entity=-1,index=3}},transportModes={[3]=true}}} or {}}}}''')
part=part.replace('assert r["ok"] is True and r["preview"] is True','assert r["ok"] is has_nodes and r["preview"] is True\n        assert r["topology"]["valid"] is has_nodes\n        if not has_nodes:\n            assert r["code"] == "street_stop_terminal_nodes_missing"')
s=s[:start]+part+s[end:];p.write_text(s,encoding='utf-8')
