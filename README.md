# Transport Fever 3 AI Bridge

**English** | [简体中文](README.zh-CN.md)

Connect AI assistants to Transport Fever 3 for map analysis, transport planning, and in-game operations.

![Transport Fever 3 AI Bridge](mod/tf3_mcp_bridge/_metadata/0.png)

This project includes an in-game mod and a local Python MCP server. Bring your own MCP-compatible AI client; the mod does not include an AI model or a model-service subscription.

## Features

- Inspect towns, industries, supply and demand, inventories, lines, vehicles, and finances.
- Capture map and terrain snapshots, identify facility sites, and plan transport connections.
- Export planning reports as HTML, PNG, SVG, and JSON.
- Preview, submit, and read back facility, road, line, and vehicle operations through their respective interfaces.
- Inspect opportunities, loans, and operating conditions; automation requires separate configuration.

See the [documentation index](docs/README.md) for interface capabilities and validation boundaries. A successful preview, a constructed entity, and stable long-term operation are separate milestones.

## How it works

```text
AI client → MCP (stdio) → Python server → local file bridge → game mod → game engine
```

The mod exchanges request, response, and heartbeat files with the server using `app.saveUserdata` / `app.loadUserdata` in the game's GUI environment. The default bridge directory is:

```text
<Steam>/userdata/<Steam ID>/3493540/local/tf3_mcp/
```

## Requirements

- Transport Fever 3 with a loaded save that has this mod enabled.
- Python 3.11 or newer and `uv`.
- An AI client supporting MCP over standard input/output.
- The automatic installer targets Windows / Steam. Installation on other environments has not been verified.

## Language and paths

Planning reports and cards support English and Simplified Chinese. Set `TF3_UI_LANGUAGE` to `en`, `zh-CN`, or `auto` in the MCP server's environment, then restart the server. Automatic selection uses process locale overrides (`LC_ALL`, `LC_MESSAGES`, `LANG`), then the system locale, with English as the fallback. It does not detect the game's language. Saved plans retain their presentation language; regenerate a plan to change it. Cards initially use the browser/host locale, then the report's language when available.

Native entity names, resource IDs, and custom titles remain unchanged. The in-game coordinate panel is hidden by default; coordinate sampling and the bilingual display implementation are retained. This is not a translation of every tool description or document.

Facility-siting and railway-plan labels also follow this language setting. Snapshot/plan JSON imports and recovery configuration accept UTF-8 with or without a BOM. `TF3_RECOVERY_CONFIG` supports user-directory and environment-variable expansion; reading configuration does not enable recovery or monitoring.

`TF3_MCP_DIR` overrides the bridge directory and supports `~` and environment variables. `TF3_PLANNING_FONT` optionally selects a font file for report images; use a font with CJK glyphs for Chinese names. Common Windows fonts and available Linux/macOS fonts are tried as fallbacks.

English presentation, Unicode transport, and paths containing spaces/non-ASCII characters have offline tests. An English game has passed live queries, terrain capture, report generation, native warehouse preview, save verification and speed-change readback. Paid construction and vehicle operation remain unverified in this language test (the test map had zero cash). English Windows has not been tested separately. See [English compatibility validation](docs/reference/ENGLISH_COMPATIBILITY.md).

## Quick start with an Agent

Open this repository in an AI Agent that can access local files and configure MCP connections. Enter the prompts below in its chat. The Agent handles setup and tool calls; you describe what you want to achieve.

### 1. Set up and connect

> Read this project's documentation and help me install and configure Transport Fever 3 AI Bridge. Check the local dependencies and MCP connection. Tell me when I need to enable the mod and load a save in the game, then verify the connection.

### 2. Understand the current map

> Analyze the current map, city demand, existing transport lines, and finances. Identify the main supply bottlenecks and opportunities for improvement.

### 3. Plan a project

> Plan a supply route for Chengde using nearby industries and existing infrastructure where possible. Estimate construction and operating costs, and show me the plan before building anything.

Replace Chengde with a city on your map. You can also ask for bus routes, warehouse placement, or improvements to an existing network.

### 4. Build the reviewed plan

> Implement the plan we just reviewed within its budget. Build the infrastructure, configure the lines, and purchase the vehicles included in the plan. Verify actual loading, delivery, and maintenance, and report any blockers or unfinished work.

For a follow-up operating check:

> Check the new routes for supply shortages, congestion, cargo expiry, and financial risks, and suggest improvements.

## Operating workflow and current limitations

Check connectivity and the current map before resolving target entities. For world changes, follow **survey → backup → fresh preview → single submission → independent readback**. Reconcile timeouts or unknown outcomes before retrying.

Protective restrictions remain in place for adding branches at existing road junctions and for joint submissions using generated ports across multiple facilities. Native crash causes are not fully resolved; a clean geometry preview does not establish safe submission. Resolve entity IDs again rather than reusing IDs from historical examples.

Read [AGENTS.md](AGENTS.md) and the [operating playbook](docs/guides/AGENT_PLAYBOOK.md) before live operations. Monitoring instructions and historical construction procedures are not authorization for a new task.

## Repository layout

| Path | Purpose |
|---|---|
| `mod/tf3_mcp_bridge/` | Game mod, publishing metadata, and cover image |
| `server/` | Python MCP server and the `tf3-bridge` CLI |
| `scripts/` | Installation, planning, diagnostics, and execution tools; some are historical experiments |
| `config/` | Planning templates and configuration |
| `docs/` | Interface references, operating guides, and historical records, primarily in Chinese |
| `.mcp.example.json` | Portable client configuration example |

## Development and tests

```powershell
cd server
uv sync --extra test
cd ..
$env:PYTHONPATH = 'server/src;scripts'
server/.venv/Scripts/python.exe -m pytest server/tests scripts/tests -q
```

See the [current validation record](docs/TEST_VALIDATION_20261010.md) for the latest full-suite results and compilation checks. Offline tests do not certify native game behavior or long-running save stability.

## Publishing and documentation

Publishing sources live in `mod/tf3_mcp_bridge/`; its directory name is retained for tool compatibility. Copy the complete directory to `staging_area/tnj_tf3_ai_bridge/` under the game's userdata directory, then validate and upload through **Mod Hub → My Mods** in the main menu.

`_metadata/0.png` is the cover image, and `_metadata/modinfo.json` contains the author and description. The staging copy stays outside Git. Users still need to install the local MCP server separately.

Before uploading, run `python scripts/check_mod_package.py "<staging mod directory>"`. Live tests can generate request files under `content/tf3_mcp_bridge/headless/`; these are runtime data, not release files. With the game and bridge clients stopped and no pending request, archive that directory outside the mod before publishing. Keep the request ledger and backups. This offline check does not replace the game's native validation.

`exports/`, live-game survey records, logs, and test temporary directories are not distributed with the source. References to those files in historical documents may not resolve in a public checkout.

- [Documentation index](docs/README.md)
- [Planning tools](docs/reference/PLANNING_TOOLS.md)
- [Official mod publishing guide](https://wiki.transportfever3.com/doku.php?id=modding:general:publishing)


**Live acceptance:** the recorded finite operation scenarios have been tested; same-person railway alighting is deferred by user request. Some fixed-wing flights were empty, and long-term cache reclamation, unlimited operation and all vehicle/cargo combinations are not certified. See the [operation acceptance record](docs/UI_OPERATION_ACCEPTANCE_20261009.md). The experimental [headless transport](docs/HEADLESS_TRANSPORT_20261009.md) is opt-in and disabled in the default source configuration.
