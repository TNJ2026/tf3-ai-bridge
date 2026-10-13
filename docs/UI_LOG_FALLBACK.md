# Experimental GUI/log fallback

## Current UI (2026-10-10)

The input field, Send button and remaining status indicator have all been removed
at the user's request. The game-bar plugin resource, script and stylesheet are
removed from the source and local installation, so AI Bridge no longer adds a
widget or uses space in the bottom information bar after a fresh game load.
The headless transport and existing event handlers are unchanged. Historical
manual-panel instructions below no longer describe the current UI. Removal has
been checked on disk; visual verification still requires a fresh game load.

The GUI/event/game-query/log path passed live acceptance in build 40420 for `get_game_state`, `list_towns`, `list_lines`, `list_vehicles` and `list_stations`. All five were exercised through a separate real MCP stdio client/server and the loaded game. Initial network lists were empty. After the user created a route, a follow-up live pass returned one line, two ROAD vehicles, five station groups and one depot, with matching cross-references.

## Protocol

1. `prepare_ui_read_request(command, arguments=None)` creates a unique ID and captures the current log offset. It does not dispatch a game request.
2. Enter the returned `input` in **AI Bridge query**, then click **Send once** (older panels label it **Query**) using the game UI.
3. `read_ui_query_result(request_id)` reads matched, bounded `[TNJ_UI_READ_V1]` hex/JSON frames.

Phase 3 adds `get_finances`, `get_map_info`, `list_depots` and `list_vehicle_models`. After the user reloaded the mod, all four passed live acceptance through a separate real MCP stdio client/server. Parameterized town limits and ROAD model filtering also passed. All queries reuse existing handlers. The read-only endpoint rejects Lua evaluation and mutations. A separate staged construction endpoint is described below. The official GUI event `tnj_bridge_readonly.request` is explicitly subscribed by the game script, including migration of existing saves.

| Commands | Optional arguments |
| --- | --- |
| `get_game_state`, `get_finances`, `get_map_info` | None |
| `list_towns` | `limit`: integer 1–500 |
| `list_lines`, `list_vehicles`, `list_stations`, `list_depots` | `limit`: integer 1–500; `mine_only`: boolean |
| `list_vehicle_models` | `limit`: integer 1–500; `year`: integer 1–9999; `carrier`: ROAD/RAIL/TRAM/WATER/AIR; `include_unavailable`: boolean |

Parameters are validated on both sides and encoded as an optional JSON object after `ID command`. Input is capped at 512 bytes; replies at 65,536 bytes. Oversized or unencodable results produce an error frame and **Error logged**, rather than a success status. Use a smaller list limit after reconciling that error; no automatic replay is performed.

Requests are process-local, limited to 256 per MCP process and 256 unique requests per loaded game script. After 60 seconds, an unanswered request becomes `timeout_unknown`; a late response can still be reconciled. Neither pending nor timeout permits automatic resubmission. The reader rejects log rotation/truncation, changed pre-request bytes, duplicate or inconsistent frames, and observed `Game is ready` / bridge GUI startup markers after preparation. Reload detection depends on these native log markers, not a guaranteed map identity token. Renew entity investigation after reload; restarting MCP invalidates its old tickets.

## Verification

- Populated network pass (2026-10-09): `output/live-validation-20261009/ui_network_reads/RESULT.md` and `acceptance.json`. Five serial live queries passed. Independent native-log decoding matched every MCP response, including Chinese names; line/vehicle, vehicle/depot and stop/station-group references matched. Both ROAD vehicles reported `EN_ROUTE`, `noPath=false`, `userStopped=false`. This is read-channel acceptance for the current fixture, not long-term operational assurance.
- Read completion pass (2026-10-09): `output/live-validation-20261009/ui_read_completion/RESULT.md` and `acceptance.json`. Seven additional serial live requests passed; all 11 native frames independently match MCP responses with valid UTF-8. Nonempty facility discovery returned the warehouse. TRAM, RAIL, WATER and AIR model filters passed, including explicit year, limit and `include_unavailable=true` behavior. Together with the earlier ROAD query, all five carrier filters have live examples. Financial response in this sandbox contains `infiniteMoney=true` and `loan=0`, not operating income/expense history. The related UI/build/recovery/stale-status regression selection passed 30 tests. Original file transport work is temporarily set aside at the user's request; it has not been removed or repaired.
- Phase 3: 85 regression tests passed; after strengthening the MCP parameter protocol test, all 16 UI/log tests passed again. Coverage includes Lua handler/allowlist/deduplication, argument validation, subscription migration, partial and multi-frame Unicode assembly, oversized response errors, timeout/late results, reload and rewrite detection, and existing bridge regressions.
- A separate MCP stdio process was actually initialized, tools listed, forbidden commands rejected, and a prepared request/result exchanged. That protocol test uses a synthetic log response; it does not count as a new live game query.
- Prior live evidence: `output/live-validation-20261009/ui_query_integration/subscription_fix/RESULT.md`.
- Phase 2 live acceptance: `output/live-validation-20261009/ui_query_phase2/RESULT.md` and `acceptance.json`; all five matched log frames were independently decoded with no duplicates.
- Latest live acceptance: `output/live-validation-20261009/ui_query_phase3/RESULT.md` and `acceptance.json`. Six serial queries passed after mod reload. Their 11 frames independently decode to the exact MCP responses, with no duplicate or missing parts. Map info used four frames; ten ROAD models used three. Town limit 2 returned two entries; the model result identified year 1964 and 35 available ROAD models before limit 10. Depots returned an empty list.

## Limits

Original userdata transport is not restored. The currently attached MCP connection must reload the server to expose the new tools. There is no unattended UI dispatcher and no change to existing file-channel tools. The staged warehouse construction transport passed the live acceptance described below. The input panel uses reactive state to preserve its latest text across status updates; consecutive live requests retained the correct input with no observed reversion. Populated owned ROAD network responses and live multi-frame map/model responses are verified. Other populated transport modes, multi-owner exclusion, live responses near the size limit, lifecycle coverage beyond the listed checks and other construction categories require separate acceptance. Size-limit behavior has mock coverage, not live boundary coverage.

## Staged construction transport (warehouse live acceptance passed)

`prepare_ui_build_request(command, arguments)` prepares an input without dispatching it. Submit it once with the panel's **Send** button, then call `read_ui_query_result(id)`.

| Command | Arguments | Behavior |
| --- | --- | --- |
| `list_facilities` | No arguments | Resolve current owned construction IDs |
| `survey_build_site` | x, y | Nine surface/water samples at 40 m spacing; no collision preview |
| `build_warehouse` | Required x, y, z; optional rotation, module_count (1 or 4) | Native preview only; returns a short-lived preview_token when allowed |
| `build_facility` | Required source_entity, x, y, z; optional rotation | Preview a copy of a current owned, cloneable facility layout |
| `build_helipad` / `build_heliport` | Required x, y, z; optional rotation | Native preview only; UI transport mock-tested, live acceptance pending reload. Access, shared stock and air operations are separate checks. |
| `commit_facility` | preview_token | Consume a successful UI preview from the same GUI session once; rerun native guards and submit |
| `get_facility_config` | entity | Independent current facility configuration readback |
| `preview_road` | start, end, street_type | Straight ground-road native preview; endpoint is `{node:id}` or `{x,y,z?}`, no automatic snapping or collision override |
| `commit_road` | preview_token | Consume a road preview within 60 seconds, reject changed endpoints, repeat native preview, submit once |
| `get_entity` | id | Independent current entity component readback |
| `list_street_types` | optional filter | Discover current road templates |

The GUI forwards only these allowlisted commands with the official scripting event command. The engine validates arguments again and executes the existing facility workflow, preserving its native collision, ownership, expiry and source-snapshot checks. It does not invoke engine-only construction handlers directly from the GUI thread. Neither arbitrary Lua nor arbitrary command names are accepted. The additional road commands have offline coverage and await reload and live acceptance. Street stops, new depot/station templates, demolition, configuration changes and purchases are not yet connected. Existing cloneable station/depot layouts can use build_facility; this is not a replacement for their dedicated template builders.

Before a commit, obtain construction authorization, verify the current map and site, and keep a pre-build save. The transport itself does not save or obtain authorization. Existing preview tokens expire after 60 seconds and commits revalidate the proposal. GUI dispatch IDs are reserved before sending; engine request IDs and preview provenance are recorded in game script state before execution, bounded at 256 requests. Engine duplicates are ignored rather than re-executed. This journal persists only with native game state/save persistence, not as an external durable transaction log. Reloading an older save can roll back its journal; never replay old inputs or infer an external outcome from that save.

An error, missing result, unverified build or other uncertain outcome after commit latches further commits. Readback remains available. There is deliberately no automatic retry or automatic latch reset; preserve the evidence and reconcile the actual world before implementing any recovery. A received response is not itself success: require result.built and result.verified, followed by independent get_facility_config and applicable access/stock checks. Static configuration verification does not prove simulation safety.

Offline acceptance: actual Lua GUI-to-engine routing with mocked native API, warehouse preview/commit/independent readback, duplicate events after script recreation, stale GUI epoch rejection, unresolved-result latch, and native snapshot read-your-writes behavior. The related regression suite passed 132 tests. The new MCP tool is also checked through a real stdio process; these are not live construction results. After deployment the user must reload the mod before live acceptance. Original userdata file access remains blocked.

### First live engine-channel check

On 2026-10-09 the loaded phase-1 GUI successfully forwarded get_facility_config and returned the engine error for an industry ID obtained from fresh get_map_info. That ID was not a current construction reference. No build preview or commit was sent. This verifies engine routing and error return only. To avoid guessing construction IDs or site elevations, list_facilities and survey_build_site were subsequently added, offline-tested (23 UI/build tests), and deployed; this revision awaits reload. Evidence: output/live-validation-20261009/ui_build_phase1/live/RESULT.md.

### Live warehouse acceptance after reload

On 2026-10-09, seven serial requests passed through a real MCP stdio process and the loaded game. Current facility discovery and nine-point terrain survey succeeded. After a verified prebuild save, native warehouse preview reported no blocking errors; one commit created warehouse 44084 with capacity 500. An independent get_facility_config request confirmed its position, owner and universal module. The fixed map save was written and checked stable. Evidence: output/live-validation-20261009/ui_build_phase1/live2/RESULT.md and acceptance.json. This verifies warehouse construction transport, not all builders, live facility cloning, freight operation, reload persistence or long-term simulation safety.
