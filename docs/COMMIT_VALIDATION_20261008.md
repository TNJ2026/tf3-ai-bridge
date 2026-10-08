# 2026-10-08 source checkpoint validation

This commit collects the existing bridge, planning, documentation and test work,
and synchronizes the publishing metadata and cover for Transport Fever 3 AI Bridge
(author TNJ2026). This is a source checkpoint, not a verified public release.

Local MCP settings, generated surveys, execution ledgers, test temporary files and
one map-specific noise-trial runner are excluded. Historical documentation may
refer to local evidence under `exports/`; these files are not portable fixtures.

## Offline checks

- `git diff --check`: passed before staging.
- Staged-file scan for common private-key, GitHub-token, OpenAI-key and AWS-key
  patterns: no matches. This is a limited pattern scan, not a security audit.
- Full pytest collection failed because `scripts/tests/test_hub_execution.py`
  imports the unavailable historical `construct_roads` module through
  `hub_trial_roads.py`.
- With only that collection-blocking file excluded, the run completed:
  **627 passed, 15 failed, 4 subtests passed**.

Command (PowerShell, from repository root):

```powershell
$env:PYTHONPATH='server/src;scripts'
server/.venv/Scripts/python.exe -m pytest server/tests scripts/tests -q --ignore=scripts/tests/test_hub_execution.py --basetemp=output/commit-tests-rest-20261008
```

Remaining failures occurred in:

- `server/tests/test_e2e.py`: four depot/station/road connection expectations.
- `scripts/tests/test_batch_connections_helipads.py`: two missing historical
  `exports/supply_warehouse_20261002/optimized_network.json` fixture failures.
- `scripts/tests/test_city_joint_collection.py`: four depot/port binding tests.
- `scripts/tests/test_flat_collection_siting.py`: one pipeline assertion.
- `scripts/tests/test_fullmap_stop_batches.py`: one missing
  `covered_building_hints` fixture field.
- `scripts/tests/test_hub_joint_bind.py`: three Lua fixtures missing `B`.

The existing native junction and multi-facility submission guards remain enabled.
No game requests, construction, reload, or publication were performed for this
commit. No GitHub remote was configured at validation time; committing does not
upload the project.
