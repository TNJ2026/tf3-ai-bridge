# Custom userdata transport failure after build 40420

Status: reproducible in the current loaded game; cause and supported remedy unknown. Prepared for upstream reporting, not submitted.

Alternative-channel proof, 2026-10-09: an experimental mod-owned GUI plugin using the native GameBarInfoDisplayExtension successfully accepted UI text and printed a framed hex payload to stdout. External decoding matched the unique 33-byte UTF-8 input, including Chinese characters, exactly once; UI showed Logged #1. This validates only the minimal GUI/input/log echo route, not the existing file transport or full MCP integration. No world command was issued. Evidence: `output/live-validation-20261009/ui_log_probe/RESULT.md` and `live_roundtrip.json`.

Clean reinstall retest, 2026-10-09: after user deletion of the old installation and communication directories, installed and hash-verified a fresh five-file source copy. On restart (40420), the GUI bridge initialized at 06:54:55 +08:00 but both userdata save/load probes failed identically. No new heartbeat was created. This is not merely an old cached-heartbeat result. Evidence: `output/live-validation-20261009/clean_reinstall/RESULT.md` and `post_restart_log.txt`. Reinstallation did not restore the transport.

Mod-ID directory probe, 2026-10-09 06:41:13 +08:00: one GUI `saveUserdata` call to the existing mod-owned `tnj_tf3_ai_bridge` directory failed with the same unavailable/invalid-directory error. Readback was skipped on save failure. No transport migration was made. The temporary staging script was restored from a verified backup; evidence is in `output/live-validation-20261009/modid_probe/`. Simply changing the directory to the mod ID is not a working fix in this environment.

New-map retest on 2026-10-09: failure persists. New process 18168, native build 40420, map seed `mK22bC6Akx`; at 06:27:35 +08:00 the GUI bridge startup again reports both save and load failing with the same invalid/unavailable-directory error. Heartbeat remains stale. No world request or game modification was issued. Evidence: `output/live-validation-20261009/newmap_40420/`. The failure is therefore not confined to the previous checkpoint; its internal cause is still unknown.

## Environment

- Windows, Steam app 3493540.
- Previously working native build: 40408 (Steam build 25533170).
- Current failing native build: 40420 (Steam build 25754343).
- Mod ID: `tnj_tf3_ai_bridge`; bridge version: 0.12.9.
- Script runs in the GUI state; initialization also occurs in the engine state.
- The custom `tf3_mcp` folder already exists under the active userdata root.

## Minimal API operation

The bridge's GUI-state startup invokes the equivalent of:

```lua
local ok, err = pcall(app.saveUserdata, "tf3_mcp", "probe", { value = 1 })
print(ok, err)
```

This is a reduction of the observed failing call, not a separately executed minimal mod. The actual bridge serializes its payload into a `{ hex = ... }` table. Its subsequent `app.loadUserdata` startup probe fails with the same directory error.

Observed result:

```text
The directory you trying to access is not available or invalid
```

Expected from the published API contract: save a custom Lua table in the specified userdata subfolder. The same bridge transport worked before the update. This timing does not establish the internal cause or prove an intentional security restriction.

## Documentation and investigation

- [Official app API](https://wiki.transportfever3.com/script-doc/app.html): `saveUserdata` saves a custom table, and describes `directory` as a folder in the userdata directory. `loadUserdata` has the corresponding contract.
- [Official mod types](https://wiki.transportfever3.com/script-doc/api/type/mod.html) and the installed 40420 `api/tealdef/api/type/mod.d.tl`: no custom userdata-directory registration field found in the inspected mod definitions.
- Installed `api/tealdef/app.d.tl` retains these APIs and their directory arguments.
- Installed GUI scripts use `towns_industries` for map-editor exports and `mod_presets` for mod presets. These are unrelated native features; the bridge has not been redirected into their directories.
- [Official release notes](https://wiki.transportfever3.com/doku.php?id=releasenotes) do not establish a replacement custom-mod transport contract.

Questions for the developer: Are arbitrary custom userdata subfolders still supported in 40420? If registration or a namespaced path is now required, what is the supported API/configuration? If this is a regression, which build restores the documented behavior?

## Test impact and evidence

The current bridge status is disconnected, with a stale pre-restart heartbeat. Its stale `paused` field is not evidence of the current game speed. No world requests were sent after the freshness check failed.

The interrupted-process recovery test remains unverified: the saved checkpoint loads visually, but vehicle state rollback, task/account persistence and full map equivalence cannot be independently read back through the bridge. The prior successful offline/live tests remain historical results for their tested environment.

Local evidence (ignored runtime output):

- `output/live-validation-20261008/update_40420/stdout.txt`
- `output/live-validation-20261008/update_40420/appmanifest.acf`
- `output/live-validation-20261008/update_40420/RESULT.md`
- `output/live-validation-20261008/abrupt_recovery/baseline.json`
- `output/live-validation-20261008/abrupt_recovery/unsaved_marker.json`

Keep checkpoint and backup intact. Resume live acceptance only after fresh bidirectional transport and current map identity are verified. Do not count this blocker as a passed recovery test.

## Follow-up: disconnected status presentation

The server compact status previously exposed old heartbeat values such as `paused` and `gameTime` at the top level even when `connected=false`. It now nests these values under `lastKnown` and labels them historical. Connected output remains unchanged. This is a diagnostic correction, not a repair of the 40420 userdata failure; a running MCP server needs to load the updated Python code before its tool output changes.

Validation: `python -m pytest server/tests/test_compact.py server/tests/test_stale_status.py server/tests/test_bridge_recovery.py -q` — 11 passed. The installed API search still found no supported custom-directory registration or alternate transport. Live recovery acceptance remains blocked.

## Additional local reconciliation

- Source and the active staging-area `bridge.script.lua` have identical SHA-256: `EA937B9B0EBA8570697F8ECE9D431C2542ADDF2F8D1C50FCE174C8900B0A2F35`. A stale deployed script does not explain this instance.
- The bridge directory exists as a normal directory with no reported link target. This does not prove access is permitted by the game.
- Fixed checkpoint remains 34,774,980 bytes, last written 2026-10-08 22:54:24 +08:00; separate backup remains 34,775,198 bytes, last written 22:54:22 +08:00.
- Native log records game-owned autosaves at 23:11:59 and 23:22:00, both dated 1969-03-05. No agent save request was issued during this investigation. These autosaves do not replace independent recovery verification or the preserved checkpoint.
- No new supported userdata registration requirement was found. Further live acceptance depends on restored transport; repeating world requests while disconnected cannot verify it.


## Native static-analysis finding (2026-10-09)

Read-only disassembly of installed 40420 identified the exact error's directory validator at RVA 0xdd0f90. It initializes four allowed directory strings (`towns_industries`, `biomes`, `heightmaps`, `mod_presets`) and rejects unmatched input. This provides strong evidence that our custom directory is rejected by an internal allowlist, rather than a missing folder or Windows ACL. Full Lua binding call-chain mapping and comparison with 40408 remain unverified, so the date and intent of this restriction are not established. No binary modification or use of unrelated built-in directories was attempted. Local evidence: `output/live-validation-20261009/native_userdata_analysis/RESULT.md`.


## API call-chain confirmation (2026-10-09)

Static registration and direct-call analysis now connects both loadUserdata and saveUserdata to shared path builder RVA db65c0, then directory validator dd0f90. The input directory is checked before path assembly or file I/O. Both APIs remain registered. The separate runtime restriction reports a different message (API is currently restricted). Common RIP-relative references to the allowlist container identify initialization/comparison and destruction, with no registration mutator found; indirect aliases are not exhaustively excluded. Detailed evidence and RVA chains: `output/live-validation-20261009/native_userdata_analysis/CALL_CHAIN.md`. This narrows the immediate failure to the native directory allowlist, but does not establish when or why it changed.
## 2026-10-15 supplementary explicit user-authorized test

Follow-up external-first duplex test also passed on the actual mod.io copy:
100 unique requests on the same two userdata files, 1 duplicate without repeat
processing, and 3 rejected altered/out-of-session/out-of-order messages. All
104 replies matched independently; UTF-8 and roughly 8 KB payloads round-tripped.
A 10-second idle interval did not reprocess the unchanged request. Native cleanup,
host file absence, and installed-script restoration were verified. Evidence:
`output/userdata_duplex_20261015/RESULT.md`. No world commands were sent; formal
MCP integration, crash recovery and long-duration stability remain unverified.

An independent test in the existing `mod_presets` directory passed: native
`saveUserdata` wrote A, the host atomically replaced A with B in the same file,
and native `loadUserdata` read B twice without reload. Native removal and
independent filesystem absence were verified. The test file was returned by
`getAllUserdata`, so this directory is not a hidden private namespace. The
installed script was restored; no world operations or pending changes occurred.
Evidence: `output/userdata_roundtrip_20261015/RESULT.md` and `result.json`.
This supersedes any inference that the custom-directory restriction rules out
all mutable userdata communication. It does not establish a production protocol
or authorize unrelated changes to native preset files.
