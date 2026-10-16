# Save games through the no_gui channel

The v31 receiver adds a dedicated `save` request kind. No input field, button,
mouse automation, old userdata-file transport or automatic reload is required.
The game must still be running a loaded, paused map. This calls the official
[`app.saveGame`](https://wiki.transportfever3.com/script-doc/app.html#App.saveGame)
from the existing GUI-script update context; removing the visible panel does not
remove that script context.

## Procedure

1. Read `no_gui_status`. Require a fresh ready receiver, no pending request and
   `receiver.saveGameAvailable=true`. Independently verify the current map/session
   and pause through the validated speed interface if authorized.
2. Choose the same fixed map checkpoint slot for ordinary checkpoints. Use a
   separate slot for a pre-construction backup or acceptance test. Slot names are
   1–80 ASCII letters/digits/underscores/hyphens, beginning with a letter or digit;
   extensions, path components and Windows device names are rejected.
3. Submit **once** through `send_no_gui_request`:

   ```json
   {
     "command": "save_game",
     "kind": "save",
     "arguments": {"slot": "tf3_fullmap_auto_map_<verified_map_hash>", "overwrite": true},
     "expected_session": "<fresh independently verified session>"
   }
   ```

   Replace placeholders with real values. `overwrite` defaults to false and is
   required to be explicitly true if the host finds an existing `.sav` file.
   Do not use an arbitrary existing user save as a checkpoint.
4. Poll `read_no_gui_result` with the returned request ID. A native
   `requested=true` acknowledgement is insufficient: the host requires a changed,
   nonempty file whose size/mtime/inode are stable for at least one second, checks
   the same current session/generation, hashes the file and rechecks its signature.
   Only then does the returned result contain `verified=true`, the path, signature
   and SHA-256. This is write verification, **not** a successful reload test.

The save location is `<TF3_MCP_DIR parent>/save/<slot>.sav`. Local installation
paths must correspond to the game's active Steam profile. The native callback
is intentionally empty; file verification does not write to game globals.

## Failure and persistence

The shared batch lock and durable request intent precede publication. Native
save IDs have a separate, non-evicting 256-save bound per loaded GUI session;
read-result archival does not erase them. NoGui status reports the save count
and limit. The existing 256-entry construction guard is unchanged.

Missing, empty, unchanged or changing files retain the pending lock. After 120
seconds the file-verification result becomes `timeout_unknown`; absence of a
native acknowledgement uses the existing 60-second response deadline. Neither
permits a retry. Reading the **original** request ID may later verify a completed
write. Host restarts preserve intent and verification progress; verified results
remain readable from durable history even if the file is subsequently removed.
Log reload/rotation, a changed session, native failure or uncertain submission
stops further dispatch until independently reconciled. No automatic overwrite,
speed change, reload or request replay is performed.

## Validation status

Offline coverage checks both the Lua receiver and host: invalid slots, stale
sessions, paused-state enforcement, missing native API, duplicate saves after
read archival, native errors, explicit overwrite, old/empty/growing files,
timeouts and late results after host restart. Deployment and live save-file
verification are separate acceptance steps; do not infer live success from these
mocked tests.

Live acceptance on 2026-10-10 passed on v31: creating an independent test save,
explicitly overwriting only that test slot, rejecting implicit overwrite before
publication, and retrieving the original verified response after MCP restart.
Both writes produced changed, nonempty, stable files and verified SHA-256 hashes.
The original `2222.sav` was unchanged; game time, paused state, money, map, lines
and vehicles matched before/after. The test save was not reloaded
(`reloadVerified=false`). Evidence: `output/live-validation-20261010/resume42/`.
The full offline suite passed 1482 tests and 4 subtests after the v31 change.
