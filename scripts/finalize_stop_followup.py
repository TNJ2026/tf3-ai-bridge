from pathlib import Path
p=Path('server/tests/test_e2e.py');s=p.read_text(encoding='utf-8').replace('api.type.enum.TransportMode = {BUS=3}','api.type.enum.TransportMode = {BUS=3}\n            api.type.enum.EdgeObjectType = {STOP_LEFT=0,STOP_RIGHT=1}');p.write_text(s,encoding='utf-8')
p=Path('STREET_STOP_INTERFACE.md');s=p.read_text(encoding='utf-8');s+='''

## Follow-up: native topology identified

The user supplied the native Nanjing West Road stop group 62315. It contains
left/right objects 62425 and 62282 attached to road 62438; their station
terminals reference internal road network nodes. The failing simple proposal
had no internal nodes on its replacement road, although geometry preview passed.

Explicit `BASE_EDGE.objects` references using native reserved IDs
`-400000000`, `-400000001` and two SimpleStreetProposal edge objects produce
four internal nodes on a two-lane street (two walking, two BUS), eight network
edges, no critical errors or collisions. Evidence: stop_dual_topology_preview.json.
The production preview now constructs this topology, preserves original road
lanes/style, assigns params before the vector copies objects, and rejects a
preview lacking walking/BUS nodes. Apply remains disabled until live verification.

At 22:09:22 a separate save callback attempted to assign the forbidden global
`tf3StopCheckpointDone`, causing the GUI Lua runtime to exit. This was an agent
script error; no stop apply was submitted in this follow-up. The callback now
has an empty body. `tf3_stop_checkpoint_20260930.sav` was written before the
callback failed (52,259,911 bytes); loadability has not been verified and it may
contain the earlier orphan edge object. Preserve other saves. The game must be
loaded again before further live verification.
''';p.write_text(s,encoding='utf-8')
