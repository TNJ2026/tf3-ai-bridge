# Build 40420 compatibility blocker during recovery — 2026-10-08

**Recovery acceptance is blocked: the checkpoint loads visually, but the updated game rejects the bridge userdata directory. Do not mark recovery passed or release this build as compatible.** Evidence: `output/live-validation-20261008/abrupt_recovery/` and `update_40420/`.

- Before interruption, paused the original map, saved a separate verified backup `tf3_before_abrupt_recovery_0f77d4fe77930bdd`, and guarded-save/reloaded fixed slot `tf3_fullmap_auto_map_0f77d4fe77930bdd`. Persisted full map/vehicle/line/task/account baseline. Set stopped=true once on in-depot train46821 and independently confirmed the unsaved marker; no save followed that marker.
- Terminated only the exact TransportFever3.exe process20244. Heartbeat became stale. This was an authorized process-loss test, not an injected native engine assertion or partially applied construction.
- Steam required an update before restart: build25533170 →25754343; game logs show40408 →40420. New process30496. Computer Use was interrupted by the user, then explicitly resumed. The user had loaded the exact fixed slot; clicked Start Game to enter it. Screen shows the expected paused March5,1969 map.
- Current Lua startup log reports GUI transport save=false and load=false: `The directory you trying to access is not available or invalid`, at bridge.script.lua:321/4468. USERDATA_DIR is tf3_mcp, and the existing folder is present. The old heartbeat remains unchanged. Engine/GUI mod initialization occurs, but successful file transport does not.
- The local40420 API declarations still document loadUserdata/saveUserdata with directory/fileName arguments; installed native callers use editor/preset directories. No supported custom-mod directory registration or replacement transport was established. Do not redirect bridge commands into unrelated native directories or patch engine restrictions as a workaround. No production source was changed and no world command was dispatched after stale heartbeat detection.
- The attempted independent recovery verifier stopped at its heartbeat precondition. Therefore vehicle marker rollback, complete object equivalence, task/cash persistence and simulation restoration are **not independently verified after this restart**. Game remains paused; existing stable checkpoint/backup are retained. Monitoring and autoaccept remain off.

Next prerequisite is a documented supported userdata namespace/registration or an official game fix; alternatively the user may choose a compatible game build. A game update is not evidence that historical crashes were fixed. Earlier694+4 offline results and prior live results belong to the earlier validated environment.

---

# Ordinary-money subsidy settlement — 2026-10-08

**Real nonzero upfront payment and natural-expiry failure deduction passed in ordinary-money mode.** Evidence: ignored `output/live-validation-20261008/money_acceptance/`.

- Preserved independent backup `tf3_before_money_test_0f77d4fe77930bdd`, then used the guarded save/reload workflow with a task-local adapter for native SaveGameDetails. Removed only `urbangames_no_costs_1`; retained sandbox, tycoon, no-end-year, deluxe and bridge mods. Fresh map identity and three vehicle IDs were checked. Native readback: noCosts=false, sandbox=true, player28629, balance0, loan0.
- Fresh Proposed UID57263: Penzance → Pateley Bridge passenger connection, upfront10,870,000, failure10,870,000, completion cash0, duration1,582,750ms. This was an explicitly authorized disposable-map failure test, not an operational task acceptance. No service was built for it. Acceptance was submitted once with expected target and financial terms.
- At paused gameTime11,499,400, independent Active and finance readbacks showed balance/accountBalance **0 → 10,870,000**, loan0. This verifies actual money settlement rather than merely monetary offer terms.
- Advanced under bounded observation at16x, stopped shortly before deadline, then sampled at1x around expiry. Native status became Failed. Adjacent balances were **10,979,800 → 109,800**, exactly **−10,870,000**. Other operating receipts/costs during the full interval are retained in samples and are not attributed to the subsidy. No account or task state was edited; failure reputation effects were not numerically verified.
- Restored the official no-costs mod through guarded loading, then saved and reloaded the restored configuration. Independent final readback confirmed noCosts=true, sandbox=true, accountBalance109,800, loan0, UID57263 Failed, prior UID57273 Complete, unchanged map identity and all three vehicles/noPath=false. Restored original1x speed. Fixed slot remains `tf3_fullmap_auto_map_0f77d4fe77930bdd`; monitoring and autoaccept stayed off.
- A metadata inspection attempted to consume the same native Async:get result twice and was rejected with `no state` before any world mutation. Re-issued only the read-only metadata query, consumed once and retained the result. Mode switching did not reuse stale save metadata: it read the freshly verified saved file and rechecked file signature, pause and map before loading.

This closes the ordinary-money **upfront/expiry failure** gap for the tested passenger task. Completion cash was zero by native terms; nonzero completion bonuses, every subsidy kind and all reputation effects are not thereby tested. Broad native crash/partial-construction recovery and long-duration/high-load stability remain limitations. No production code changed in this phase; latest full offline baseline remains **694 passed + 4 subtests**.

---

# Native passenger completion and Complete persistence — 2026-10-08

**A real passenger task reached Complete and remained Complete after a guarded save/reload. This closes the successful-subvention persistence gap.** Local evidence: `output/live-validation-20261008/final_acceptance/`.

- Current sandbox map `0f77d4fe77930bdd`, player 28629; independent pre-test backup `tf3_before_final_acceptance_0f77d4fe77930bdd`. Monitoring and autoaccept stayed off.
- Read installed native `deliver_passengers.script.tl`: completion requires an actual person starting use of a direct line between the named towns. No task state, synthetic event, passenger or money was injected.
- Previewed and built two central two-sided stops (groups 59029 and 59050) in Snodland and Leatherhead. Both independent directed BUS path queries returned 134 steps, one query per engine call. Two depot candidates were blocked and not built. Revised road depot 57264/construction 58199 and its connector passed build/readback.
- Created line 43324, bought two GM Fishbowl buses 43323/43308, independently confirmed assignment and noPath=false. Quotes: stops 391,921; depot 582,876; buses 708,780; total 1,683,577 excluding any separately charged connector. No-costs quotes are not actual spending.
- Re-read UID 57273 terms: Snodland → Leatherhead, upfront/failure 6,870,000, complete cash 0, duration 1,582,750 ms. Persisted intent, accepted once, and separately confirmed Active at gameTime 10,496,800. Controlled 16x observation found Complete at 11,245,600 and immediately paused. These status samples plus native source establish native fulfillment; they do not quantify all carried passengers or prove steady throughput.
- Guarded fixed-slot save changed and stabilized before a single reload. Independent readback confirmed Complete and the same acceptedTime, full map identity, all three vehicle IDs, noPath=false, both lines and stop order. Vehicle enumeration order changed; per-ID comparison retained every line field and only sorted the unordered vehicle membership. No save/reload was repeated for that comparison. Original 1x speed restored.
- Pause-menu inspection temporarily stopped heartbeat; no game requests were dispatched while disconnected. Closing the menu restored heartbeat. The settings pages inspected exposed no ordinary-money toggle. Initial `kind=passenger` stop preview and nonexistent `get_line` read were rejected before mutation; corrected using documented kind=auto and list_lines. These were test-client mistakes, not native construction failures.

Current limits: ordinary-money nonzero settlement/penalties remain unverified because this loaded map has noCosts=true and no supported runtime switch was found. Broad native crash/partial-world recovery and indefinite/high-load stability are not certified. Existing client lost-ack/cancellation recovery and guarded save/reload tests remain passed; they must not be represented as native crash recovery. The latest complete offline baseline remains **694 passed + 4 subtests**, unchanged by this live-only phase.

---

# Guarded save/reload live retest — 2026-10-08

**The corrected save/reload orchestration passed a live preflight-rejection test and a successful current-state save/reload.** This closes the corrected-harness retest gap, not the missing persistence test for a successful subsidy.

Evidence: ignored `output/live-validation-20261008/save_reload_guard/`. Implemented tracked helper `scripts/save_reload_guard.py`; callers hold the common batch lock, use a fresh map/object validator and pause the simulation. A new attempt journal prevents replay. Reload requires a fixed-map slot, newly changed nonempty stable save signature, a second paused/identity check, and the same file signature immediately before dispatch. Save/validation exceptions stop the workflow; no independent shell reload command follows a failed save.

- Live controlled validator rejection stopped at preflight before save/reload. Independent readback confirmed unchanged map and paused state. This validates the orchestration gate against a connected game; it is not a native save-I/O-failure injection.
- Normal path saved the current map to `tf3_fullmap_auto_map_0f77d4fe77930bdd`, verified changed/stable file, revalidated map/vehicles, then requested exactly one reload. Independent readback confirmed map object records, vehicle ID and IN_DEPOT/noPath=false status, and task UID/status set. Restored the original 1x speed.
- Initial post-reload comparison failed because the native industry enumeration order changed. Per-ID reconciliation found no additions, removals or changed records. Added `map_identity` to canonicalize list order without dropping fields or accepting duplicate IDs; independent readback then passed. This is distinct from the earlier phase's intervening map/date/account changes and does not reconstruct its lost state.
- Thirteen offline guard tests cover preflight rejection, save exception, unchanged save, failed second validator, unpaused state, changed file signature, successful single dispatch, duplicate attempt, backup-slot rejection, enumeration order, moved/removed/replaced objects and duplicate IDs. Latest full suite: **694 passed, 4 subtests passed in 25.75s**; `pytest_final.log`.
- The old clay offer is no longer Proposed. A new Ilkeston–Horsham passenger offer appeared; no passenger service exists on this test network and it was not accepted. There are no active tasks. No recurring monitoring/autoaccept was started.

Remaining live gaps: Complete-subvention save/reload, ordinary-money nonzero settlement/penalties, broader native crash/partial-construction recovery, and long-term/high-load stability. The successful reload here preserves the actual current map; it cannot recover the previous unsaved freight test additions.

---

# Native subvention fulfilled by real freight — 2026-10-08

**The clay-delivery task reached native Complete after 70/70 real deliveries, but the final save/reload acceptance FAILED and the current game has reverted to the previous checkpoint.** Evidence: ignored `output/live-validation-20261008/subvention_success/`.

- Current sandbox map retained all original towns/industries. A new town, Nuneaton 53699 at (-1386.763,-3670.094), appeared during preparation. The old town hash assertion stopped before acceptance; a separate survey confirmed every original object unchanged, and recorded the single addition. The new town was retained, not claimed as test construction. The original fixed save slot remains `tf3_fullmap_auto_map_0f77d4fe77930bdd`.
- Temporarily paused preparation to preserve the offer window and test baseline. A separate `tf3_before_subvention_delivery_0f77d4fe77930bdd` backup was confirmed changed/stable. Source clay stock 52115 held 114 units against a 70-unit target at brickworks stock 28703. Reused both native industry stations/groups (52116/52127 and 28704/28716). Each directed TRUCK query was a separate engine call; existing routes returned 61 and 65 path steps.
- A proposed new direct road had collisions/water placement diagnostics and was not built. A first depot candidate collided with the brickworks and was not built. Revised depot construction 41399/depot 44859 at (2345,1370) passed preview and was built once; its connection to external node 28707 independently verified. No stop, industry or new long-distance road was needed.
- Bought four GMC 660 bulk trucks (63091/63093/63094/63095), 22 capacity each. Created line 63089 with source clay-only loading and destination force-unload/no-loading; independent readback verified filters, model and clay capacity. Quotes: 4 × 1,169,487 + depot 581,524 = 5,259,472, excluding any separately charged connection. Quotes are not cash deductions in no-costs mode.
- Fresh native offer UID 287030000 had target 28703, cargo 23, quantity 70, upfront 9,960,000 and failure 23,020,000. Persisted intent/terms and submitted acceptance once with all these expectations, assigned trucks and independently confirmed Active. No task/cargo/account injection occurred.
- Seventeen samples showed real loading up to 22 on each vehicle, unloading and native delivered counts 0 → 4 → 22 → 43 → 44 → 61 → 66 → 70. Sample 17 was Complete. Brick output stock rose from 0 to 76; brickworks clay stock and vehicle loads changed consistently with deliveries/production. All four trucks had noPath=false throughout these samples. Complete caps its displayed delivered quantity at 70; this is not an assertion that the trucks unloaded exactly 70 in total.
- All four trucks subsequently unloaded their carried clay and were independently observed empty/IN_DEPOT; speed was restored to 1x. However, final_state.json showed an intervening game-date/account change (2020, accountBalance -11,000,000) relative to the earlier 1965/infinite-money sample. These changes were not submitted by this test and prevent a clean monetary attribution.
- `get_finances` explicitly returned infiniteMoney=true and loan=0; base config had noCosts=true. Raw accountBalance stayed 0 around acceptance. Thus this proves fulfillment of an offer with nonzero monetary terms, **not actual nonzero money settlement**. This offer has completeMoney=0, so no separate completion cash reward is expected by its terms.

**Save/reload execution incident:** The pre-save map identity assertion rejected an original-object change before app.saveGame. The PowerShell batch nevertheless continued to the separate reload command because the Python nonzero exit was not propagated. It loaded the old fixed checkpoint (21:35:35), losing the current unsaved test additions and intervening unsaved map changes. Independent post-reload state confirms only the original train remains and the clay offer is Proposed again. This is a test-orchestration error, not evidence of native rollback or successful Complete persistence. No later automatic save was found; the newest backup is before this phase's construction. The lost post-test state cannot be reconstructed from these saves. Do not replay the acceptance on the reverted offer automatically.

The phase harness now has one save_and_reload.py entry point using subprocess.run(check=True), a receipt created after entry, the exact fixed slot and matching stable file signature before dispatching reload. Pre-save surveys are persisted before identity assertions. This correction was code-reviewed but has not been executed against the reverted map; the phase is stopped for user awareness. Successful delivery evidence remains in operation17.json; it is not the current saved game state.

No production code changed; the latest full offline baseline remains **681 tests and 4 subtests passed**. Nonzero account settlement/penalties in ordinary-money mode, broader native partial-construction recovery and long-term engine stability remain unverified. Monitoring and automatic acceptance remain off.

---

# Native subvention acceptance and expiry failure — 2026-10-08

**The sandbox task progressed Proposed → Active → Failed with exactly one acceptance submission and zero deliveries. Active-state save/reload preserved the original accepted time and deadline.** Evidence: ignored `output/live-validation-20261008/subvention_lifecycle/`.

- Verified current map `0f77d4fe77930bdd`, player 28629, and preserved a separate changed/stable backup `tf3_before_subvention_failure_0f77d4fe77930bdd`. The user authorized unrestricted testing on this disposable sandbox map. Failure was intentional; it was not an operational supply attempt.
- Fresh offer UID 286360013 required 47 planks for Snodland (28636), with no serving line. Current native terms had zero upfront/completion/failure money, reputation effects on acceptance/failure, and experience on success. Recorded the full terms and intent before the single checked acceptance. Native readback confirmed Active at acceptedTime 3405600 with deadline 8032100, rather than treating dispatch success as acceptance.
- Saved and reloaded while Active. The same accepted time/deadline and Active status persisted. No second acceptance request was issued. No script state, deadline, cargo counts or account values were rewritten.
- Observed nine bounded samples over approximately 364 seconds after reload. Started at 4x, then used 16x (explicit readback confirmed) to accelerate this sandbox expiry test. Sample 8 was Active with 371100 game milliseconds remaining; sample 9 was Failed with delivered=0/toDeliver=47. Original speed 1x was restored and read back. This does not establish 16x safety for other maps or loaded networks.
- Saved the terminal result to the fixed map slot, confirmed changed/nonempty/stable, reloaded and independently read Failed with acceptedTime 3405600 and delivered=0. Active task count was zero, speed 1x, and the only vehicle remained IN_DEPOT/userStopped=false. Evidence: `final_reload_readback.json`.
- Added three offline regressions covering native Active/Complete/Failed records after bridge module recreation: status/timestamp survive and another acceptance cannot dispatch. Full suite: **681 passed, 4 subtests passed in 26.68s**. No production bridge code changed in this phase.

The native failure state is verified, but the town reputation change was not numerically measured. Zero-money terms in no-costs mode do not validate nonzero settlement, refunds or penalties. Successful fulfillment (Complete), nonzero subsidy accounting, broad native partial-construction interruption recovery and long-term stability remain unverified. Monitoring and automatic acceptance remain off.

---

# Live acknowledgement loss and cancellation recovery — 2026-10-08

**A real vehicle mutation was independently reconciled after an induced client timeout, without replay. Live read cancellation and the subvention changed-terms guard also passed.** Evidence: ignored `output/live-validation-20261008/recovery_live/`.

Map key `0f77d4fe77930bdd`, player 28629, sandbox/no-costs test map. Original/final speed 1x. Before testing, a separate `tf3_before_recovery_test_0f77d4fe77930bdd` backup was confirmed changed and stable. The map was re-read; newly observed industries were retained and not attributed to this test.

- **Lost acknowledgement:** starting with vehicle 46821 IN_DEPOT/userStopped=false, submitted exactly one set_vehicle_stopped(true). A test-process-only response reader captured but withheld responses from the caller. The normal bridge call timed out after 3 seconds and cleared its request to idle. The actual engine acknowledgement was retained in `timeout.json`; an independent get_entity confirmed userStopped=true. No mutation retry was sent. A separate inverse command restored false, independently confirmed with the vehicle still in depot. No native game script or production bridge code was altered by the injection.
- **Cancellation:** a read-only get_game_state response was withheld, the awaiting call was cancelled, and its request file was confirmed idle. A new Bridge instance then acquired the released request lock and returned the correct player and speed. This exercises cancellation/cleanup against the real game; it does not simulate engine interruption. The initial harness tried to read the request file after the game had consumed it and failed a local assertion; the corrected harness captures the outgoing request ID at the write boundary. No world mutation was involved in either cancellation attempt.
- **Subvention guard:** current native offer UID 286360013 requested 47 planks for Snodland. Intentionally supplied expected quantity 48. The bridge rejected with `subvention terms changed: toDeliver`; independent readback retained Proposed and zero active tasks. No acceptance event was sent. Existing rail service has no route to Snodland. This offer has zero monetary effects and reputation/experience effects, so it cannot validate cash settlement. Completion/failure and financial accounting remain untested.
- Restored vehicle settings, preserved 1x, and confirmed the fixed map checkpoint changed/nonempty/stable. This checkpoint was not reloaded in this phase; the immediately preceding rail-cargo phase separately verified reload persistence. Monitoring and background acceptance remain off.

The timeout result narrows the recovery gap to native crash/partial-construction interruption and broader operation families. It does not prove rollback, exactly-once execution for every mutation, or long-term engine stability. No production code changed; the last full offline baseline remains **678 tests and 4 subtests passed**.

---

# Rail freight delivery acceptance — 2026-10-08

**A DB V100 with one grain wagon loaded 14 units of naturally produced grain, transported them to station B, and unloaded all 14 into the destination warehouse.** This closes the basic rail-consist and cargo-delivery gap on sandbox map `0f77d4fe77930bdd`.

Evidence: ignored `output/live-validation-20261008/rail_cargo/`. The original 1x speed was preserved. No monitoring was resumed. Source farm construction 50098 / stock 48199 and warehouse construction 50798 / stock 51000 were previewed, submitted once and independently read back. Native catchments were disjoint: station A covered the farm stock; B covered the warehouse stock. No artificial stock injection was used.

- One bulk_3_steel wagon (model 4401, capacity 14, native grain compatibility) was appended to locomotive 46821 with native replacement. Independent readback confirmed two parts and the wagon's fixed grain selection. Wagon quote: 492,222; warehouse quote: 482,442. These are quotes, not cash deductions in no-costs mode.
- Baseline grain: farm 66, warehouse 0, vehicle 0. Samples 5–10 observed loading 3 → 5 → 8 → 11 → 13 → 14. Samples 13–18 observed vehicle 12 → 9 → 6 → 4 → 1 → 0 while warehouse increased 2 → 5 → 8 → 10 → 13 → 14. Source production continued independently, so its total inventory change is not the transported amount. All these samples had noPath=false and both parts' maintenanceState=1.
- The prior experimental line configuration had not persisted: both stops were still default all-cargo loading. Direct edits of nested component values did not update the actual line. An attempted top-level assignment raised a read-only-member error before dispatch; readback reconciled this without replay. Constructing a new `api.type.Line`, assigning the complete stops vector and submitting one update succeeded. Independent readback confirmed source grain-only loading and destination no-loading/force-unload. This was a test-harness correction; the public create_line defaults are unchanged.
- Returned the empty consist to depot 24082; samples 23–24 confirmed IN_DEPOT. The fixed slot was confirmed changed/nonempty/stable, then reloaded. Independent assertions passed for the two-part consist, source/destination cargo filters and all 14 grain in the warehouse; speed remained 1x. Evidence: `final_save.json`, `reload_readback.json`.
- Full offline regression after the rail connector guard additions: **678 passed, 4 subtests passed in 25.95s**. Log: `rail_cargo/full_regression.log`.

This establishes delivery into a warehouse, not city consumption, profitability, passenger rail service or long-term simulation safety. The earlier native rail-network crash remains a recorded risk; subsidy lifecycle/accounting and systematic native interrupted-mutation recovery remain outside this acceptance.

---

# Rail crash diagnosis and corrected movement acceptance — 2026-10-08

**One locomotive completed depot departure, A → B → A, return to depot and save/reload on the new sandbox map. A native crash was encountered and retained as a release-risk finding. Freight/passenger delivery is not covered.**

Evidence: ignored `output/live-validation-20261008/rail_live/` and `rail_repair/`. Map key `0f77d4fe77930bdd`, original/final speed 1x, sandbox and no-costs enabled. No monitoring was started.

## Failure and correction

Initial station/rail-depot construction and A–B connection succeeded. The experimental depot-port survey incorrectly selected degree-one nodes **inside** the depot's frozenNodes. A clean native connection preview did not catch this. The subsequent connection submission timed out as the engine crashed at 20:54:40 local: `TransportNetworkSystem.cpp:635 AreAllNodesEmpty`, followed by `:743 !nodeData.ports.empty()` involving station endpoint 49755. This run used ignoreErrors=false. No retry was sent. Logs were preserved. A newly started process later connected with the test facilities absent; its state was re-surveyed before further mutations. The original crashed submission's partial effects are not established by that later reload.

The corrected survey takes endpoints of frozenEdges and excludes frozenNodes, matching the rail-station adapter. The depot's actual external port was on the opposite side from the mistaken internal endpoint, so the empty test depot was reoriented. A new independent backup preceded the corrected connection. New straight depot–station and A–B links passed native preview, single submission and readback. Both directed TRAIN queries from depot exterior to station A exterior returned 14 path entries, one query per engine call.

`scripts/rail_connection.lua` now rejects any construction-internal frozen endpoint before proposal generation and uses ignoreErrors=false. Two regression cases prove rejection of either endpoint without proposal or command submission. Targeted regression (guard + bridge end-to-end tests): **67 passed in 11.44s**. The last complete offline baseline remains 676 tests and 4 subtests; the complete suite was not rerun after these two additions. Historical embedded connector scripts are not made safe by this change and must not be replayed.

An earlier preview-only helper attempt failed Lua compilation because JSON ASCII escaping produced invalid Lua unicode escapes; fixed in the test harness before construction. The station preview's reputation result was unavailable and was not treated as zero. These diagnostics are separate from the native crash.

## Successful bounded acceptance

- Current retained objects: station A construction 48333/group 50236 at (800,-1250); station B construction 48473/group 50004 at (800,-950); depot construction 47638/depot 24082 at (812.2,-720). External track edges are 48359 and 49675. All were freshly resolved during this run.
- Public buy_vehicles purchased one diesel DB V100, vehicle 46821; quote 3,663,000. This is a single locomotive, no wagons. Created line 49983; a configuration attempt was made before assignment, but the later cargo test found the live configuration still at defaults; the earlier configuration acceptance claim is withdrawn. No cargo source or cargo transport is asserted.
- Eight operational samples recorded EN_ROUTE and AT_TERMINAL at both stops, all noPath=false. Departures progressed to [1973800,2005000], then [2036200,2005000], proving A–B–A with a second departure from A.
- Issued return-to-depot once. Independent samples recorded GOING_TO_DEPOT then IN_DEPOT in depot 24082. After saving and reloading the fixed slot, all three facilities, the line and locomotive persisted; locomotive remained IN_DEPOT/noPath=false and maintenanceState=1.0. The 1x speed and original modes persisted.

The fixed checkpoint was confirmed changed/nonempty/stable before reload. Wrong-facing empty test depots were removed with separate readback. The current test objects remain for further testing. This result supports the frozen-node diagnosis on this layout, not a blanket fix for native transport-network assertions. Remaining gaps: rail consist and cargo loading/delivery, subsidy lifecycle/accounting, systematic interrupted-mutation reconciliation and long-term native stability.

---

# New sandbox map: positive prospection acceptance — 2026-10-08

**Latest-build grain prospection completed successfully after saving/reloading while pending.** This closes the previously permit-blocked positive lifecycle test; it does not complete all live acceptance.

Evidence: ignored `output/live-validation-20261008/new_sandbox/`. This is a different eight-town map, key `0f77d4fe77930bdd`, player 28629, initially 1960-01-13, no-costs and sandbox enabled, original speed 1x. Old-map IDs were discarded. Independent backup `tf3_sandbox_before_tests_0f77d4fe77930bdd` was confirmed updated/stable before testing. The initial map had no player facilities or vehicles.

- Eleven exploration resources were available; rubber had no matching industry. Penzance grain preview survived a six-second delay and intervening state query. Exactly one native submission was registered at gameTime 101400.
- Temporarily used 4x to observe. Saved to the new map's fixed slot and reloaded while pending. The original operation ID/tracking receipt still returned verified pending. No second submission occurred.
- Native notification 4 reported succeeded at gameTime 600000, approximately 124.65 current game days after registration. Independent queue read showed no pending exploration and the matching success history.
- Independent map/component read found a new farm industry 46229 / construction 47520 at (88,-2356), resource `::/industries/farm/farm.con`. **The notification's result entity 47512 is a nearby BASE_NODE at (127.423,-2452.086), not the farm construction/industry ID.** Native success and the new farm's existence are verified separately; do not treat the notification ID as a construction ID. No farm production, access route or deliveries are certified.
- A fishing ground also appeared at (-3396,4204), industry 45315. This run submitted no fish exploration; that addition is recorded separately, not credited as an agent test. Every original industry remained unchanged in the final comparison.
- Restored original 1x speed, retained sandbox/no-costs, and confirmed the fixed save updated/stable. The final checkpoint has not been reloaded again. No monitoring, publication or Git push was started.

A proposed 71-grain delivery subsidy to Tow Law livestock farm existed in the later snapshot, but no serving network existed; it was not accepted. Remaining live gaps: connected train operation, subsidy lifecycle/accounting, native in-flight partial-mutation recovery and long-term stability. Code was unchanged; latest offline result remains 676 tests and 4 subtests passed.

---

# Remaining-condition check and transport fault tests — 2026-10-08

**Four new isolated transport fault tests passed; complete offline coverage is now 676 tests and 4 subtests passed. Native release acceptance is still partial.**

Evidence: ignored `output/live-validation-20261008/remaining2/`. The live bridge was connected, town identities matched the recovered test map, and all 19 vehicles had noPath=false in the current snapshot. Game speed remained 4x. This phase made no game mutations and did not start monitoring.

- New file-transport integration tests use temporary directories. A simulated mutation executes before its acknowledgement is lost; the caller times out without resending. A later query ignores the old acknowledgement and receives its own readback. Separate cases verify cancellation cleanup/lock release, lock-contention timeout preserving the owner's request, and recovery from incomplete response text.
- These tests exercise the actual Python file transport against a simulated peer. They do not inject a fault into a native engine command, prove native rollback, or prove safe recovery after partial construction.
- Live prospection resources still had no available permit. The current Proposed meat subsidy (UID 293800007) required 43 units at Penwortham, with 11,360,000 upfront and the same failure deduction. At observation it had 13 game days left to accept and no serving network in the assessment. It was not accepted; these are snapshot terms, not a reusable offer.
- The public rail-station API explicitly omits external railway construction; the public rail-connection interface only plans. A complete running train remains a missing live scenario, not a passing station test.

The two complete offline suites passed: server/tests 352 tests in 20.73s; scripts/tests 324 tests and 4 subtests in 6.18s, no skips/failures. No production code changed in this phase. Remaining live gaps are connected train operation, another positive latest-build prospection lifecycle, subsidy lifecycle/accounting, native in-flight partial-mutation recovery and long-term stability.

---

# Fresh-process recovery acceptance — 2026-10-08

**Orderly disconnect/restart recovery and a fresh-process town-cargo mutation passed. Overall release coverage remains partial.**

Evidence: local ignored `output/live-validation-20261008/recovery/`. The fixed-slot save was confirmed updated and stable before normal `app.quit(false)`. The old process (17812) exited and the bridge reported disconnected. A new process (5076, started 20:17:05 local) loaded the same save through the game UI. The loading screen required clicking Start Game before the GUI bridge resumed; no engine requests were sent while disconnected. The previously failing `app.restart()` was not repeated.

- Source and staging SHA256 matched `EA937B9B0EBA8570697F8ECE9D431C2542ADDF2F8D1C50FCE174C8900B0A2F35`. No code changed during this run; the unchanged offline result remains 672 tests and 4 subtests passed.
- Fresh reads exactly matched all town and industry identities/positions against the pre-exit map. Both new water facilities persisted with matching resources/positions. The sold test vessel and deleted temporary line remained absent. All 19 vehicles had noPath=false in the recovered snapshot.
- The verified loan repayment and industry operation journals survived the process boundary. These are historical operation receipts; their recorded balances are not a fresh financial audit.
- A new town-cargo preview survived a six-second delay and intervening query. With simulation temporarily paused, public commit changed Kidderminster commercial cargo 6 → 3, independent readback verified it, then a fresh preview/commit restored 6. Original needs and weighted needs matched exactly. This test used update_buildings=false; building propagation was covered in the preceding run.
- Speed returned to 4x; no-costs remained enabled and sandbox remained disabled. The final checkpoint was saved with an independently verified changed/stable file. That final updated checkpoint has not been reloaded again. No recurring monitoring was started.

This covers an orderly idle disconnect, normal launch, reattachment and persisted state, not an interrupted in-flight mutation, forced crash or every workflow after a fresh process. Current subsidy tasks were empty, so acceptance/completion/failure accounting remains untested. Other remaining gaps include connected train operation, another positive prospection lifecycle on the latest build (permits unavailable), partial-mutation recovery and long-term stability. Earlier gap lists are superseded only for the specific new acceptance above.

---

# Water construction and building propagation acceptance — 2026-10-08

**New shipyard/harbor construction, a test vessel circuit, town-demand building propagation and a read-only timeout recovery passed. Overall release coverage remains partial.**

Evidence: local ignored `output/live-validation-20261008/water_build/`. Independent backup: `tf3_acceptance_before_water_20261008`. Current entities were resolved against the eight-town English map. No recurring monitor was started.

- Public facility cloning built shipyard 66772 / depot 68455 at (-451.886,470), and harbor 68734 / station 62492 / group 51566 at (-565.997,1000). Native previews and independent layout/component readbacks passed. Quotes were 2,427,285 and 653,524; no-costs mode was active, so these are not cash deductions. Both retained the source layouts' 1961 parameters. Shipyard maintenance pool is 8, radius 1,000.
- Initial candidates were rejected for shoreline placement/collisions. One candidate disclosed parcel removal and was abandoned; the final harbor preview had no collisions or warnings. Early previews mistakenly supplied radians to the degrees-based rotation parameter; no mutation was submitted with those previews. Shoreline refinement produced clean candidates without additional terrain tools.
- Fresh endpoint checks independently verified new shipyard ↔ new harbor and new harbor ↔ existing harbor using SMALL_SHIP, one directed native path query per engine request. This is not blanket acceptance for all ship sizes.
- Bought one MS Stadt Kiel (438,912 quoted), vehicle 57766, in the new shipyard. Independent readback confirmed it in that depot before assigning temporary line 62726. It left the shipyard and completed new harbor → existing harbor → new harbor. Departure arrays progressed from [0,0] to [32336000,32396200], then [32465200,32396200]. All samples had noPath=false and maintenance 1.0. Passenger count remained zero: movement is verified, passenger service is not.
- Returned the test vessel once. The native command chose the nearest **existing** depot 46239, where IN_DEPOT and daysInDepot=7 were independently observed. The vessel was sold and the empty temporary line deleted, both independently verified. The new shipyard's reverse path is verified, but actual re-entry into that specific new shipyard was not observed. New facilities remain in the test map; original vessels and services remain.
- With simulation paused, Kidderminster commercial demand changed cargo 6 → 3 → 6 using update_buildings=true. All 12 commercial building stock types changed accordingly; 11 industrial building stocks remained cargo 33. All 23 stores were confirmed empty before the test. Independent final readback exactly matched original building IDs, stock IDs, cargo types, capacities and counts. Speed restored to 4x.
- A read-only get_game_state request with a deliberately tiny client timeout failed as expected. The request file became the id-less idle marker, heartbeat remained fresh, and a later normal query succeeded. No mutation was injected or resent. This covers client timeout cleanup/recovery only; it does not establish partial-mutation or disconnect safety.

Code was unchanged during this run; the latest unchanged offline suite remains 672 tests and 4 subtests passed. The fixed-slot checkpoint was saved and reloaded. Fresh resource/position matching independently confirmed both new facilities persisted; the sold vessel and deleted line remained absent, original town demand persisted, no-costs mode remained active, sandbox remained off, and speed remained 4x. All 19 vehicles in the final snapshot had noPath=false.

Remaining gaps: connected train operation (public API has no complete external track-building workflow), latest-build positive prospection (no available permits), subsidy acceptance/completion/failure accounting, live disconnect/partial-mutation recovery, fresh-process regression of every latest patch, and long-term stability. Earlier sections' lists are superseded where this section records new acceptance.

---

# Latest workflow acceptance — 2026-10-08

**Loan, industry placement and town-cargo mutation/readback passed after a further state-checkpoint fix. Full release coverage remains incomplete.**

Evidence: ignored `output/live-validation-20261008/fresh/` and `fresh/patched/`; prior completion evidence is in `completion/`. The current eight-town English test map was rediscovered, paused throughout financial tests, and the user authorized test-map mutations.

- A full new game process (PID 17812, started 19:48:25 local) still reproduced repayment preview-token loss. The Medium loan was independently reconciled and repaid through an isolated freshly loaded adapter, with cash restored to 24,531,677 and original loans 2/3 retained. This cleanup does not count as a public cross-request pass.
- A new deferred-state regression reproduced preview loss in industry, town-cargo and loan workflows: a later response checkpoint could overwrite an earlier workflow checkpoint when reads returned the prior snapshot. The engine event now retains its latest local state while forwarding writes. This is a demonstrated offline failure mechanism; the native implementation's complete caching behavior remains unproven.
- After atomic source/staging deployment and save reload, public Large-loan preview, six-second delay with an intervening query, single borrow, independent operation readback, public repayment preview/commit and independent repayment readback all passed. Loan 6 was removed and cash again matched 24,531,677. Native loan cooldowns/free-ID progression are retained test effects; existing loans were not rewritten.
- Public sandbox industry preview (quote 510,526), single commit and independent operation readback passed at (-2400,2600). Food-factory construction 68081 / industry 68082 remains as a test object. Preview disclosed tree removals and approximately 1.351 reputation-point penalty. External roads, production and profitable operation are not certified by this test.
- Kidderminster commercial cargo changed 6 → 3 → 6 with `update_buildings=false`. Public previews, commits, operation readback and final independent demand read passed. Original weighted needs were restored exactly; building propagation was intentionally not tested.
- Latest offline suite: **672 tests and 4 subtests passed**, 26.70 seconds, no skips.

## Additional completed tests from the preceding completion run

- Water freight: sixteen operational samples showed repeated source loading to 30 and destination unloading to zero, advancing departure timestamps and matching warehouse receipts amid concurrent truck withdrawals. Maintenance stayed at 1.0 and noPath was false. A liquid-storage module expansion was independently verified from 500 to 1,000 capacity. This is water operation and storage expansion acceptance, not new-port/shipyard construction acceptance.
- Terrain: a small clear 4×4 m area was flattened to 12.65 m using the public backed-up workflow; native readback passed with about 1.5e-6 m maximum error. The earlier tree-obstructed candidate was rejected without construction.
- Default TRAM depot: the public construction flow supplied native tramCatenary=2 and independently verified it on new empty depot 67129 / 46241. Its road connection/operation was not tested; earlier PCC passenger operation used the connected test depot.
- Prospection: one fish exploration completed and was independently reconciled to a new fishing ground. Verification now uses native entityEquals (ID and generation) rather than comparing change counters. A new positive cross-request prospection run on the latest checkpoint patch is still outstanding.

## Failures and remaining limits

The built-in `app.restart()` returned to main-menu initialization in the same process and then raised a native internal error before loading any map. Logs were retained; this does not establish a bridge-caused crash or a root-cause fix. Normal subsequent process launch recovered the saved test map. No automatic retry of the failed restart was made.

A read-only diagnostic incorrectly accessed engine-global baseConfig and returned a Lua error; it was corrected to the supported api.res.getBaseConfig() accessor before further work. No world mutation occurred in that failed query.

Still incomplete: connected train service; new port/shipyard construction; positive latest-build prospection lifecycle; building propagation of town demand; subsidy acceptance/completion/failure accounting; systematic live disconnect/timeout/partial-success recovery; fresh-process regression of every latest patch; long-term simulation safety. Historical request-file access failures have no confirmed root-cause fix. A bounded successful run is not an indefinite stability guarantee.

Final reload independently retained the new industry, restored town demand, and verified industry/repayment operation records. Official no-costs mode is restored (`noCosts=true`, `sandbox=false`) and speed is restored to 4x. Nineteen vehicles had noPath=false in the post-reload snapshot; three previously tested vehicles remain in depot. Simulation advanced from gameTime 30,140,400 to 30,316,400 between the recorded samples. This is a bounded observation, not proof of long-term operation.

The final fixed-slot save was independently confirmed changed, non-empty and stable after mode restoration; that final running checkpoint has not itself been reloaded. Current exploration permits are all unavailable (fish permit consumed; others rank-locked or unsupported by the economy), so another positive prospection submission cannot be tested on the present state. The current proposed passenger subsidy requires connecting towns not served by the existing network; it was not accepted merely to claim acceptance coverage.

No recurring monitor, Git push or publication was started. Historical final-state statements below describe earlier checkpoints only.

---

# Tram operational acceptance — 2026-10-08

**PCC departure, a complete three-stop circuit, boarding and alighting passed. Overall release coverage remains partial.**

Evidence: local ignored `output/live-validation-20261008/tram/` and its `recovered/` directory. The user authorized these test-map operations and explicitly approved enabling unlimited funds. The official `urbangames_no_costs_1` mod was enabled through native save loading, preserving the other mods; independent `baseConfig.noCosts=true` readback passed. Existing account balance and loan were not rewritten.

- Electrified 25 existing road segments and built a 764.3 m, 19-segment electrified depot connector. Each replacement retained endpoints, street stops, road lane connections and crosswalks; structural previews, single submissions and independent template readbacks were recorded. Structural checks do not imply comprehensive native safety.
- Native tram-depot construction without explicit `tramCatenary` produced a non-electric entrance. Setting the existing depot to native `tramCatenary=2` allowed PCC 44792 to be assigned and leave depot 52252. The public `build_depot` command now supplies this parameter for TRAM, with regression coverage confirming it reaches the native proposal and is absent for ROAD.
- Initial road selection lacked loops beyond the outer stops, resulting in `noPath=true`. Two loops were completed using existing streets. All three directed electric-tram paths then passed in separate engine requests; no batch pathfinding stress test was used.
- Test line 60102 reused three existing passenger groups while retaining the user's bus line. All stop departure timestamps became nonzero, then advanced through another circuit. Samples 9–12 recorded passenger counts **6 → 4 → 4 → 1**, with successive stop departures and `noPath=false`; the sample before initial boarding was empty. This proves actual boarding/alighting, not passenger throughput or profitability.
- Maintenance declined during these circuits; continuous in-service maintenance coverage is not established. A single return-to-depot command was issued after operational observation. Independent readbacks confirmed `GOING_TO_DEPOT` then `IN_DEPOT`; maintenance recovered from 0.2304 to 0.9329. The PCC remains in the depot after testing.
- Final readbacks confirm speed **4x**, official no-costs mode active and the PCC in depot with `noPath=false`. The fixed slot `tf3_fullmap_auto_map_14a343fe26b2c4cd` was saved with a changed, stable non-empty file (`final_tram_save.json`); this final checkpoint was not reloaded.

## Failure encountered and limits

An earlier test helper guessed a nonexistent `town_new_xsmall_tram_electrified` template and called native replacement during preview. The engine reported an index -1 street-template assertion / Unknown exception. No city road upgrade had been committed in that attempt. Requests stopped, the saved test state was recovered, all entities were rediscovered, and the helper gained a resource-existence guard. The successful revised route excludes those unsupported roads. This records a test-script defect and recovery, not a claim that native assertion safety is solved.

Offline validation: **664 tests and 4 subtests passed in 26.46 s**, without skips. The latest depot fix was atomically copied to staging; hashes are recorded in `tram/deployment.json`. Its default-construction behavior has not yet been tested in a freshly restarted game process; the operational test above used an independently verified native depot upgrade.

No recurring monitor was enabled. Train operation, broader mutation families and long-term stability remain unverified.

---

# Continued operational acceptance — 2026-10-08

**Air freight operational test PASSED for two deliveries. Overall release coverage remains partial.**

Evidence: local ignored `output/live-validation-20261008/operations/`. The user authorized full tests on this map. Fresh map/line/vehicle discovery preceded mutations; existing user routes were retained.

- Built a source helipad at (340, -260) and a 500-unit receiving warehouse at (-1870, 2507). Independent native catchment readback confirms source station 54591 covers farm stock 29386 and destination station 53899 covers warehouse stock 55331. These are real stock IDs, not inferred radius overlap.
- Created line 54718 with fresh groups 49983 → 54189; explicitly enabled only grain (cargo ID 1) at the source and disabled loading / enabled unloading at the destination. Independent line configuration readback passed.
- Bought one S-64 helicopter (51851), quoted 716,316, and assigned it to this line. Facility quotes: helipad 582,131 and warehouse 521,854; total new quotes 1,820,301. Quotes are not audited total cash deductions.
- Observed source loading to 10, departure, destination unloading to zero and warehouse grain increasing 0 → 10. On the next cycle source load again reached 10; destination was sampled at warehouse 12 / vehicle 8 during unloading and finally warehouse 20 / vehicle 0. Both stop departure timestamps advanced between cycles. No `noPath` error occurred. Maintenance declined and recovered to 1.0 during the first delivery.
- A return-to-depot command was submitted once after the second delivery. The initial independent readback confirmed `GOING_TO_DEPOT`. Final `list_vehicles` readback confirmed `IN_DEPOT`, depot 53699 and `daysInDepot=5`. The fixed slot was saved with a changed, stable non-empty file; this final checkpoint was not reloaded. Speed remained 4x.
- This proves a small air cargo transfer into storage, not warehouse-to-city distribution, passenger aviation, fixed-wing aircraft, long-term throughput or profitability. The test line is being taken out of operation after acceptance to avoid filling storage indefinitely.

## New defect and test side effect

Native construction rebuilt the farm after removing one parcel and reused its previous construction ID 29385 for the new helipad; the farm now uses construction 55745, while industry/stock ID 29386 remains. Farm level changed **11 → 10**. The preview disclosed parcel removal; this is a retained test side effect, not a disappeared farm or a free operation.

The adapter returned `built=true, verified=false` because its verification treated any pre-existing numeric ID as ineligible. No construction retry was issued. Independent configuration, ownership, position, station and stock readbacks reconciled the built helipad. The fix now compares the former construction resource before treating the ID as old, while retaining position, ownership, parameters and capacity checks. A regression first failed on the old code and passes with the fix. **662 tests and 4 subtests passed** (25.35 s).

The fix is atomically copied to staging; `deployment.json` records hashes. This new patch has **not been validated in a freshly restarted game process**. The air deliveries above use the previously loaded build and independently reconciled entities; they must not be presented as live validation of the new verification code.

A final optional read-only diagnostic used an unavailable native `getVehiclesInDepot` method and stopped with a Lua error before any mutation. The supported `list_vehicles` query then independently verified arrival. This diagnostic error is not counted as a successful API check.

## Remaining coverage

- Railway station operation remains unverified. Tram operation was subsequently verified as described in the newest section above. Current public APIs expose rail planning/station construction, not a complete track-construction workflow.
- Ground and water networks are being modified by the user during the test; user additions are not claimed as agent mutation coverage.
- Other mutation families, deliberate disconnect/partial-success injection and long-term simulation safety remain unverified. Historical file-access issue was not reproduced in the preceding restart run, but has no proven root-cause fix.

中文结论：航空货运已连续完成两次装卸，20 单位粮食实际入库，维护恢复有证据。另发现并修正原生实体编号复用导致的验收误判；离线 662 项及 4 项子测试通过，新补丁尚待完整重启后的实机回归。测试机坪施工导致农场少一个地块、等级 11 降为 10。全项目尚未达到全部运营方式验收通过。

---

# Post-restart validation — 2026-10-08

**Result: targeted restart regression PASSED. Full release certification remains incomplete.**

Following the user's complete game restart, the same source/staging build passed the previously failing facility flow. The token was retained for **21.8 seconds**, with four independent engine queries between preview and commit. One heliport commit succeeded and independent facility/depot readbacks confirmed its configuration, helicopter purchase capability and maintenance pool. This supports the fix in the restarted session; it does not prove that caching was the sole cause of the earlier failures or establish indefinite reliability.

Evidence: local ignored `output/live-validation-20261008/restart/`, including timed `heliport_preview.json` / `heliport_commit.json`, independent readbacks, `RESULT.json` and `log_review.json`.

- Fresh map read confirmed the eight-town English test map; industry changes were re-read rather than inferred from old IDs.
- Source and staging SHA-256 remain `575b24de5269d4515b80cfb7502375335d74896f6e4948bc25d47deff5974214`.
- Native heliport preview quote: 977,397. Built construction 54206, depot 53699, maintenance pool 4 and radius 800. Configuration/service readback passed. Its road access and useful passenger/freight coverage are **not** certified; the test access road is isolated.
- Bought one Bell 47, quoted 120,204; independent readback found vehicle 21119 in the new depot. It is unassigned and has not flown a route.
- Saved fixed slot `tf3_fullmap_auto_map_14a343fe26b2c4cd`, verified updated non-empty stable file, reloaded it, and independently confirmed the map, heliport and helicopter persisted. Simulation continued at the original 4x speed; all ten sampled vehicles had `noPath=false`, with no reported problem lines. These are short-run observations, not sustained service acceptance.
- Current process log review found no duplicate-mod warning, request-file permission failure or matching native exception/assertion. The historical file-access failure has **not reproduced in this run**, but its root cause remains unproven.
- Offline result remains **661 tests and 4 subtests passed**; no code changed during this restart retest, so the unchanged offline suite was not needlessly repeated.

No publication or Git push was performed. The test heliport and helicopter remain in the saved test map. Full connected train/tram/air operations, other mutation families and long-term stability remain outside the completed evidence. Earlier findings below are retained for history and superseded only where this section provides newer evidence.

中文结论：完整重启后的设施令牌延迟提交、机场建造、购机、保存重载及短时运行检查通过；当前日志未重现重复模组或请求文件访问错误。仍不能宣称全部运输方式及长期稳定性已通过验收。

---

# Live release validation — 2026-10-08

**Historical result before full restart: BLOCKED. The full release test has not passed.**

The continued run fixed a reproducible offline loss of facility tickets across engine module instances, but live retesting still intermittently loses a ticket in about 12.5 seconds, before its advertised 60-second expiry. The underlying live failure is unresolved. A complete game-process restart has been requested to distinguish cached code from an incomplete fix; save reload alone is insufficient evidence. Do not publish this as a completed fix.

## Continued run: verified results

Evidence: local ignored `output/live-validation-20261008/continue/`. All game writes were explicitly authorized on the test map.

- Full offline suite: **661 tests and 4 subtests passed**, 25.43 seconds. The new regression recreates the Lua module between every request, round-trips state through JSON, invalidates a changed GUI epoch and rejects repeated commit; only one native submission occurs.
- Source and staging bridge SHA-256 match: `575b24de5269d4515b80cfb7502375335d74896f6e4948bc25d47deff5974214`. Matching files do not prove every running engine worker loaded those bytes.
- Saved and reloaded the fixed map slot, then independently read current map, lines, vehicles and test road. This verifies the earlier checkpoint reload, not reload of the final additions below.
- Warehouse construction committed once and independently found at the test location; native readback verified capacity 500. This single successful commit does not resolve the intermittent token failure.
- Double roadside stop built with two stop entities, a station group and native pedestrian/bus terminal topology. The earlier missing `BASE_NODE_CONFIG` refusal remains a valid guard; it was not bypassed.
- One 80 m railway station, one tram depot and one PCC tram built/bought and independently read back. The railway station and tram depot have no external operating network; railway/tram service is **not** verified.
- Additional test roads built and independently reported. Heliport collision previews rejected construction correctly; an adjusted candidate passed preview but its commit was rejected at the token gate. Independent nearby readback confirms **no heliport was built**. Air operations remain blocked.
- The added Fuso test bus returned to its depot, reached maintenance 1.0 and `daysInDepot=4`, then was sold once. Independent vehicle listing confirmed absence; original user vehicles remain.
- Further samples found original freight truck 46399 empty after an earlier load of 10, newer trucks carrying cargo IDs 18, 20 and 23, and passenger service carrying 12. These observations do not prove a particular freight delivery, city consumption, sustained throughput or profitability. Cargo disappearance alone can have multiple causes.
- User-created lines, trucks, vessel and an industry appeared during the run. They were read back and retained; they are not credited as bridge construction tests.
- Speed restored to **4x**. Final fixed-slot save confirmed changed, non-empty and stable. Pre-test backup remains separate. No recurring monitoring was started.

## Remaining blockers and coverage gaps

1. `heliport_preview14.json` issued token `2581.807:3`; `heliport_commit15.json` was rejected roughly 12.5 seconds later with `preview expired, already consumed, or bridge reloaded; preview again`. No automatic commit retry. The facility state persistence patch is a candidate fix with an offline regression, **not a confirmed live fix**.
2. The earlier intermittent `request.lua: Permission denied` native log remains unexplained. Later successful requests do not prove this file-access issue fixed.
3. Removing the duplicate local-mod junction leaves one on-disk installation, but a clean process startup has not yet been verified. The junction was moved intact to `local/bridge_test_backup/tf3_mcp_bridge`; repository source was not deleted.
4. Air construction/operations, connected train/tram service, water construction via the bridge, terrain/industry/loan/subvention mutations, deliberate transport faults, and long-term simulation stability are not certified. Some have offline coverage; that is not native validation.
5. A read-only diagnostic used `get_entity` with the wrong argument name; it was rejected before mutation, corrected to `id`, and read back. A documented `gameScriptRep` state method was absent at runtime; that diagnostic stopped with a Lua error. Neither is counted as a successful API test or a world mutation.

Retained test objects include warehouse 52193, stops 52198/52199, railway construction 52208, tram depot 52251/52252, tram 44792, and test roads. IDs are historical evidence and must be freshly resolved after reload. Final save: `tf3_fullmap_auto_map_14a343fe26b2c4cd`; the latest save has not yet been reloaded.

中文结论：继续测试取得了设施建造、公交回库维护与出售、存档重载等新增证据；离线 661 项与 4 项子测试通过。但设施令牌仍在有效期内间歇丢失，请求文件访问错误也未确定根因，因此发布验收仍未通过，不能称“全部测试完成”。

---

# Earlier run (historical evidence; superseded where noted)

# Live release validation — 2026-10-08

**Result: FAILED / BLOCKED. Do not treat this run as full release certification.**
The user explicitly authorized mutation tests on this test map. No historical construction script was replayed. Evidence is in local ignored `output/live-validation-20261008/full/`.

## Passed checks

- Fresh connection, GUI and engine command responses, current map identity and populated transport queries.
- Independent pre-test save, confirmed non-empty stable disk write: `tf3_fullmap_before_release_tests_20261008_171041_e9c1ed`.
- New 100 m road: native preview, one commit, independent edge/node readback. Quote: 22,330. Two new segments; one subsequently upgraded to medium country road and verified with its replacement ID.
- Line creation and readback; created empty test line then deleted it and independently verified absence.
- One Fuso B46 bus purchased for quoted 226,386, read back in depot, assigned to the existing passenger line and read back. Stop/restart toggles verified independently.
- Passenger line movement, departures at every stop, actual passenger loads and maintenance recovery. Original bus sampled at 10 then 12 passengers; added bus at 8 passengers in both samples.
- Existing freight truck observed carrying 10 units of cargo ID 9; full delivery not proven in this run.
- Final fixed-slot save confirmed updated and stable: `tf3_fullmap_auto_map_14a343fe26b2c4cd`. **Not reloaded.**

## Blocking findings

1. **Facility preview token not found after about 14.8 seconds.** Warehouse preview at 17:15:40 local returned token `1608.159:1`, `expires_in_seconds=60`, and a clean native check (quote 505,789; capacity 500). Commit at 17:15:55 returned `preview expired, already consumed, or bridge reloaded; preview again`. The error occurs before native submission. Independent nearby readback found no warehouse. No commit retry or alternate-token bypass was attempted. The current adapter stores tickets in a Lua-local table; multiple engine script instances were initialized in the session. Cross-instance loss is a hypothesis requiring a focused fix/regression test, not a proven root cause. Dependent facility mutation tests are blocked.
2. **Intermittent request-file access error.** At 17:11:27 local the game logged `cannot open .../tf3_mcp/request.lua: Permission denied` and `Failed to load userdata`. No request timeout or unknown world mutation was observed; subsequent GUI/engine round trips and state readback succeeded. An atomic-replacement/read sharing race is plausible but unproven. This was not fixed or waived as release-safe.
3. **Roadside stop preview prerequisite.** The new road initially lacked endpoint BASE_NODE_CONFIG and the stop preview safely refused before submitting. After a simulation interval two of three nodes had the component; the terminal node still did not. This is a tested refusal / applicability constraint, not a passed stop-construction test. No stop was built and no lane guard was removed.

## Not completed

- Facility commit/readback (warehouse failed at token gate); depot/station/rail/air/water construction and operations.
- Roadside stop construction, terrain/industry/loan/subvention mutations, cleanup/sale/depot-return operations and broader boundary combinations.
- Confirmed freight unloading, city consumption/revenue, full sustained freight round trip and maintenance recovery. Truck maintenance declined to approximately 37.2%; `noPath=false` and an empty problem-line list do not establish healthy long-term operation.
- Save/reload verification: only successful saving is established. The installed native API was read and a non-mutating capability probe performed; no guessed reload call was submitted.
- Clean-install verification: duplicate local/staging mod registration remains. Staging bytes matched source in earlier checks, which is not a clean installation test.
- Deliberate disconnect/partial-success fault injection and long-term stability. No native crash was intentionally provoked.

## Final state

Speed restored to original **4x**, confirmed by readback. No recurring monitor or background autoaccept was started. Original two lines and two vehicles retained. The **new test bus remains assigned to line 1**, and the **100 m test road remains** (50 m medium + 50 m small country road). The temporary empty test line was deleted. No warehouse was built. Test state saved; pre-test recovery save preserved separately. The final observation occurs shortly after saving, so dynamic vehicle positions in that observation need not exactly equal the saved frame.

中文结论：本轮实机测试发现设施预览令牌短时间内丢失及一次请求文件访问错误，发布验收未通过。已通过的道路、线路、车辆写入和载客验证有独立回执；未执行项目明确列出，不能宣称“全部测试通过”。
