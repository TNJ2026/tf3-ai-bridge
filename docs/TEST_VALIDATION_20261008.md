# Offline test validation — 2026-10-08

Result: **694 passed, 4 subtests passed**, 25.75 seconds in the combined server and script suites. No failures, collection errors, exclusions, or skipped tests.

Later targeted railway regression: **67 passed in 11.44s** (`test_rail_connection_guard.py` + `test_e2e.py`), including two new guards rejecting construction-internal frozen endpoints before proposal/dispatch. The complete suite has now been rerun after these two additions and passed. Evidence: `output/live-validation-20261008/rail_repair/pytest.xml`.

## Reproduce (PowerShell, repository root)

```powershell
$env:PYTHONPATH='server/src;scripts'
$env:PYTHONUTF8='1'
server/.venv/Scripts/python.exe -m pytest server/tests scripts/tests -q
```

The latest run invoked server/tests and scripts/tests together; log: `output/live-validation-20261008/save_reload_guard/pytest_final.log`. Earlier separate-suite XML/logs remain under `output/live-validation-20261008/remaining2/`. Create the output parent directory first. Logs and XML are local, ignored artifacts.

## Changes

- Added thirteen save/reload orchestration and map-identity tests, including fail-closed validation/save failures, stale or replaced checkpoint files, duplicate attempts and enumeration-order normalization without accepting real object changes.

- Added three subvention recovery regressions: after bridge module recreation, native Active/Complete/Failed tasks retain their accepted timestamp and cannot emit another acceptance event. These are mocked-native-state tests; they do not simulate task fulfillment or native money settlement.

- Added four isolated file-transport fault tests: executed simulated mutation with lost acknowledgement and late response, cancellation cleanup/lock release, competing-client timeout preserving the owner request, and incomplete-response recovery. No real game userdata or native mutation is used by these tests.

- Added industry, town-cargo and loan workflow persistence tests with engine-module recreation, JSON storage, epoch invalidation and both immediate and deferred state writes. Deferred-state cases failed before the event-local read-your-writes fix and pass afterward.
- Added prospection persistence and native entity-generation comparison regressions.


- Extracted displayed-collection layout geometry into `scripts/displayed_collection_layout.py`. Geometry tests no longer import historical execution modules from untracked survey exports. The historical executor still requires its original survey dependencies; this change does not make it a portable construction entry point.
- Replaced historical warehouse/site data dependencies with self-contained geometry and facility-selection fixtures, including rotated footprints and marine-site exclusion.
- Supplied proposal diagnostics in the Lua mock, checked expected ambiguity errors, and deferred diagnostic serialization until an actual ambiguity occurs.
- Added the current planning-operations dependency to the pipeline fixture; retained cache invalidation checks.
- Supplied required catchment data in stop-verification fixtures and added rejection coverage for matching station IDs with insufficient building coverage.
- Moved road/depot/station success scenarios to supported degree-one street endpoints. Added start/via/end junction rejection checks proving no native build submission. The junction guard was not relaxed.

- Added facility-ticket persistence across engine module recreation, JSON state round-trips, GUI epoch invalidation and single-use commit. The later full-restart live retest passed the delayed commit; see the [live validation record](LIVE_TEST_VALIDATION_20261008.md).

- Added a native construction-ID reuse regression: a parcel rebuild may recycle an old industry construction ID for a newly created facility. Resource identity is checked before rejecting the readback; ownership/configuration checks remain mandatory. The new patch awaits fresh-process live verification.

- Added TRAM/ROAD depot regression cases verifying native catenary parameters in the actual construction proposal.

## Scope and limitations

All tests were offline; the bridge integration tests use FakeGame and temporary request files. The offline command itself performs no live game operations. Separate subsequent live tests are documented in [the live record](LIVE_TEST_VALIDATION_20261008.md). Passing this suite does not establish native-engine safety, fix historical crashes, or certify long-running save stability.

The earlier failures remain documented in [the historical checkpoint record](COMMIT_VALIDATION_20261008.md); this record supersedes its test status for the current working tree.

中文摘要：本轮离线修复后全套 694 项测试、4 项子测试通过，未跳过失败文件。修正了历史文件依赖、模拟数据和已过时的道路成功预期，保留路口施工保护。离线命令不连接游戏；后续实机测试见独立记录，仍有发布阻断问题。
