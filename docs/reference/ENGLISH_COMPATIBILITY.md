# English game validation

Live check: 2026-10-13, game build 40420, English town names Kirkby Stephen, Penkridge and Oswestry. Windows display language was outside this test's scope.

Passed:

- Current session, map, player, cash and native operation-state reads.
- English town/model names and stable native resource IDs.
- Town cargo supply/demand by cargo ID; industry worker and cargo bonuses, including the native name `Fertilizer`.
- Current notification-list read (empty in this map; English notification-body rendering was not exercised).
- Local terrain snapshot and English HTML/SVG/PNG report generation.
- Native warehouse preview: no collisions or blocking errors, quoted cost 950,478. No commit was sent.
- Independent backup save verified by a new stable nonempty file and hash.
- Pause → speed 1 → pause, with independent game-state readback. Original paused state restored.

Limits: available cash was 0 and infinite money was false. No station groups were available. Paid construction, line creation, vehicle purchase and actual operation were not tested. This does not certify every interface or long-term simulation. The coordinate panel's hidden default has an offline recipe test, not a live pixel-level check.

## Unknown save from a previous session

`isolate_previous_session_save(request_id, expected_session)` is an explicit, user-authorized recovery tool. It applies only to an unresolved `save_game` request from a different session in demand mode. It does not handle construction, purchases, loans or load requests.

The original request and unknown outcome remain in the durable ledger. Its save slot is quarantined against future save/load through this channel. During the transition only game-state, map and native validation reads are allowed. Fresh successful readbacks, matching session/generation and no native pending are required before new operations are enabled. The known v40 native response omits nil `pending`; other response versions require an explicit field.

The tool never replays the old save, reports it as successful, loads a save, or resumes monitoring. Interrupted verification can continue with the same request/session arguments. The live test recovered a previous-session save in this way, then successfully verified a new backup save under a different slot.
