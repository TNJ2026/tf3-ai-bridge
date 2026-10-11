# Offline validation — 2026-10-10

## 2026-10-11 submission validation — v40 roads and channel migration

The complete server and scripts regression passed **1710 tests and 4 subtests
in 69.43 seconds**. The source bridge passed all **12 compile-only checks**
across Lua 5.1–5.5 and LuaJIT 2.1, with zero and 16 reserved locals. The staged
diff passed whitespace checks. This submission validation did not contact the game.

The submission includes guarded road graphs, paired highways, special road
connections, headless routing/save/recovery, legacy receiver removal, and siting
performance changes with their tests and documentation. Bounded roundabout
construction, bus driving and save/reload acceptance are recorded separately in
[ROUNDABOUT.md](reference/ROUNDABOUT.md). The user subsequently clarified that successful roundabout construction satisfies
the requirement; traffic control, dynamic entry yielding and saturation behavior
are outside acceptance scope, with no further traffic trials required. Historical
observations remain evidence, not passed behavior tests. Existing isolated-test
guards remain.

## v32 channel migration

2026-10-10: the final regression ran the server and scripts suites separately:
**1158 server tests + 364 script tests = 1522 tests, plus 4 subtests**, all passed
(49.71 s and 6.63 s respectively). The 40 migration tests are included in this
total, not added twice. Source and installed bridge passed all 12 Lua compile
checks (six runtimes, zero/16 reserved locals).

The v32 implementation covers named-tool routing, component/snapshot paging,
bounded complex line edits, journaled vehicle batches, autoaccept transport and
opt-in read-only monitoring. See [migration scope](reference/HEADLESS_MIGRATION.md).
Tests use mocks and local files; they do not prove the native v32 operations.

v32 is installed with a backup and exact byte/hash verification. Evidence:
`output/live-validation-20261010/resume43/deploy/deployment.json`; regression logs:
`output/channel_parity_20261010/v32_pytest.txt`, `v32_scripts_pytest.txt`, and
`v32_compile.json`. Subsequent bounded live acceptance passed (see below). No game requests, map changes,
monitor/autoaccept activation, commits or pushes were performed during this implementation.

The subsequent live run verified named tools, component paging, local/full planning
snapshots, route cache reuse, reversing/restoring a two-stop test line, a stopped-flag
vehicle batch with restart deduplication, and two read-only operational samples.
The current opportunity failed feasibility checks; acceptance stayed dry-run.
Bulk purchase/sale orchestration and nonempty waypoint combinations remain covered
by mocks, not this live run. Evidence: `resume43/independent_audit.json` under the
live-validation directory. Pause, money, game time, fleet/lines and original save
were independently checked; backup and fixed checkpoint files were verified but
not reloaded. The actual configured MCP executable passed using the new environment;
the existing desktop MCP process still needs reconnection. No product source changed
during this live acceptance, so the prior offline counts remain applicable.

## v31 save-channel follow-up

The latest full offline run passed **1482 tests and 4 subtests in 53.97 seconds**.
The targeted save/headless run passed 41 tests. Source and installed Lua passed
the multi-version compile checks. Save-channel live file-write acceptance is
recorded separately in [HEADLESS_SAVE.md](reference/HEADLESS_SAVE.md); it does not
include a reload test. These changes have not been committed.

## Earlier committed baseline

Pre-commit verification of the current source: **1457 tests and 4 subtests passed in 53.78 seconds**, with no failures or skipped tests.

Run from the repository root in PowerShell:

```powershell
$env:PYTHONPATH='server/src;scripts'
$env:PYTHONUTF8='1'
server/.venv/Scripts/python.exe -m pytest server/tests scripts/tests -q
server/.venv/Scripts/python.exe scripts/validate_bridge_compile.py
```

The bridge passed compile-only checks on Lua 5.1, 5.2, 5.3, 5.4, 5.5 and LuaJIT 2.1, both without additional locals and with 16 reserved locals. These 12 checks do not execute the bridge or reproduce the native game loader.

The suites cover the file transport, UI/log and opt-in headless transports, request identity and persistence, guarded construction and configuration, passenger/cargo identity reads, game speed control, and planning helpers. Tests use mocks and temporary files; this validation did not connect to or change the game.

Live evidence and its limits are recorded separately in [operation acceptance](UI_OPERATION_ACCEPTANCE_20261009.md) and [headless transport](HEADLESS_TRANSPORT_20261009.md). Same-person railway alighting is deferred by user request, not marked passed. Long-term native cache reclamation, unlimited operation/building and exhaustive vehicle/cargo combinations remain unverified. Runtime evidence, saves and local configuration are excluded from Git.

中文摘要：提交前重跑全套离线测试，1457 项测试及 4 项子测试通过；六种 Lua 运行时共 12 个编译检查通过。本轮未连接游戏。铁路同人下车暂时跳过，长期稳定性与所有参数组合不在已证明范围内。
