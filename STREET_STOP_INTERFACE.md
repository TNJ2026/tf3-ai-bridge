# Historical roadside-stop investigation — 2026-09-30

> 最新状态：下文保留多个历史阶段，包含后来失效的“apply 禁用”“尚未测试”和旧实体 ID，不能直接作为当前施工指令。当前接口已完成边对象引用、车道/横道映射及终端网络校验；用户从稳定存档重建六处停靠点后报告未闪退，后续线路装载修正后报告正常。旧故障存档的 `MakePersonCapacityData` 根因仍未解决。受控 1 倍速观察已经执行，记录见 `controlled_simulation_trace.json`；因此下文“尚未执行”仅是当时状态。执行流程及证据边界统一见 [AGENT_PLAYBOOK.md](docs/guides/AGENT_PLAYBOOK.md)，本文件保留为历史诊断依据。

## Historical simulation crash investigation — 2026-09-30 22:33 CST

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

# Current status: verified live construction (2026-09-30 22:16 CST)

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

# Roadside stop interface status (2026-09-30)

`build_street_stop` is exposed through MCP and defaults to a geometry preview.
Supply `edge`, or `x` and `y`; optional `two_sided` (default true), `param`
(0.15–0.85), `side`, `kind`, and `name`. Results include cost, collisions,
position, `preview`, `built`, `mutationAttempted`, and `applySupported`.

A successful preview is **not** proof that the engine can build the terminal.
`preview=False` and the legacy `experimental=True` bypass both return
`street_stop_apply_unavailable` without submitting a world mutation.

## Confirmed fixes

Replacing a street for a stop must update endpoint lane segment references
and crosswalk references in the same proposal. Omitting crosswalk remapping
causes the native map lookup assertion even without an edge object.
The interface now clones endpoint configurations and remaps both references.
The old blind apply/retry loop has been removed.

## Remaining native blocker

The repaired proposal passed live preview, but applying it asserted in
`construction_util_terminal.cpp:99`, `CalcNodeIndex`. The native command was
not atomic: original road 62116 was replaced by 76060 (62014 to 61589), and
edge object 76059 remained without a station. Road 76060's objects list was
empty. No further live stop construction or automatic cleanup was attempted.
The 15-node planned bus circuit remained reachable in both directions after
this failure. This does not establish that the orphan object is save-safe.

Before enabling apply, determine and reproduce the native stop terminal
network topology in a disposable test save, validate station and edge-object
ownership, both directions of pedestrian/bus connectivity, and save/reload.
Do not retry a failed apply using the original road ID: it may already be gone.

Evidence: stop_reconcile.json, stop_reconcile_connectivity.json,
stop_interface_preview.json. The six planned dual-sided stops have not been
successfully built. Normal game UI placement remains the available path.


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

22:36:42: the no-vehicle line save also asserted in MakePersonCapacityData.
The user reports switching to 4x triggers the failure. Previous test scripts
set speedup=1 but did not sample later speed changes, so they do not establish
that the failure occurred at a constant 1x. Do not claim a low-speed reproduction.
A controlled trace script now samples actual speed and ticks every 0.5 seconds,
records progress before a crash, and invalidates the comparison if speed changes.
It has not been executed. Crash root cause remains unresolved.
