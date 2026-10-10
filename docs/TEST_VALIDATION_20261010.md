# Offline validation — 2026-10-10

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
