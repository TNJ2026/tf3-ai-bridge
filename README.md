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

The `headless` transport delivers requests through single-use Lua resource files and reads results and receiver status from the game log.

```text
AI client → MCP (stdio) → Python server → single-use request resources → game mod → game engine
                              ↑                                           ↓
                              └──────── responses in the game log ────────┘
```

Request resources reside in the installed mod's `content/tf3_mcp_bridge/headless/` directory. Local request ledgers and coordination files default to:

```text
<Steam>/userdata/<Steam ID>/3493540/local/tf3_mcp/
```

New release packages include an enabled receiver. Load the mod, set `TF3_MCP_TRANSPORT=headless` for the MCP server, and point `TF3_MCP_HEADLESS_MOD` to the installed mod's `content/tf3_mcp_bridge` directory. The local MCP server still requires separate configuration. The observed mod.io mount does not discover new request files at runtime: installer `--mode auto` selects a reusable native userdata mailbox in the existing `mod_presets` directory. Live MCP reads, native save/reload, and reads after restarting the external MCP server have passed. A fresh game load is required after installing the receiver. See [downloaded-mod compatibility](docs/reference/MODIO_CONNECTION.md) and the [headless transport guide](docs/HEADLESS_TRANSPORT_20261009.md).

## Requirements

- Transport Fever 3 with a loaded save that has this mod enabled.
- Python 3.11 or newer and `uv`.
- An AI client supporting MCP over standard input/output.
- The automatic installer targets Windows / Steam. Installation on other environments has not been verified.

## Language and paths

Planning reports and cards support English and Simplified Chinese. Set `TF3_UI_LANGUAGE` to `en`, `zh-CN`, or `auto` in the MCP server's environment, then restart the server. Automatic selection uses process locale overrides (`LC_ALL`, `LC_MESSAGES`, `LANG`), then the system locale, with English as the fallback. It does not detect the game's language. Saved plans retain their presentation language; regenerate a plan to change it. Cards initially use the browser/host locale, then the report's language when available.

Native entity names, resource IDs, and custom titles remain unchanged. The in-game coordinate panel is hidden by default; coordinate sampling and the bilingual display implementation are retained. This is not a translation of every tool description or document.

Facility-siting and railway-plan labels also follow this language setting. Snapshot/plan JSON imports and recovery configuration accept UTF-8 with or without a BOM. `TF3_RECOVERY_CONFIG` supports user-directory and environment-variable expansion; reading configuration does not enable recovery or monitoring.

`TF3_MCP_DIR` overrides the local ledger and coordination directory and supports `~` and environment variables. `TF3_PLANNING_FONT` optionally selects a font file for report images; use a font with CJK glyphs for Chinese names. Common Windows fonts and available Linux/macOS fonts are tried as fallbacks.

## Quick start with an Agent

Follow these steps to download the mod and project files, create a project in an Agent App with local file access and MCP support, then configure the server and start planning.

### 1. Download and activate the mod

Download **Transport Fever 3 AI Bridge** from the mod page below, and activate it in the mod list before starting a new game or loading a save.

Mod URL: <https://mod.io/g/transportfever3/m/transport-fever-3-ai-bridge-3-ai>

### 2. Download and extract the project

Open [GitHub Releases](https://github.com/TNJ2026/tf3-ai-bridge/releases), choose the matching version, and download **Source code (zip)** under **Assets**. Extract the archive to a local folder.

### 3. Create a project in your Agent App

Open your Agent App, create a new project, and select the extracted project folder as its directory. Use the folder containing `README.md`, `server/`, and `mod/`.

### 4. Set up and connect

> I have downloaded and activated the game mod. Read this project's documentation and help me install and configure the local MCP server and headless transport. Check the local dependencies, receiver, and MCP connection, then verify connectivity once the game has loaded.

### 5. Understand the current map

> Analyze the current map, city demand, existing transport lines, and finances. Identify the main supply bottlenecks and opportunities for improvement.

### 6. Plan a project

> Plan a supply route for Chengde using nearby industries and existing infrastructure where possible. Estimate construction and operating costs, and show me the plan before building anything.

Replace Chengde with a city on your map. You can also ask for bus routes, warehouse placement, or improvements to an existing network.

### 7. Build the reviewed plan

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

Publishing sources live in `mod/tf3_mcp_bridge/`; the local publishing copy lives under the game's userdata `staging_area/tnj_tf3_ai_bridge/`. Validate and upload through **Mod Hub → My Mods**. The current publishing workflow does not generate or upload ZIP files.

**Every upgrade must increase both the integer `revision` in `mod.json` and `BRIDGE_VERSION` in the bridge script.** The description and changelog heading must use the bridge version rather than a date. Synchronize source and local publishing copies; the two version numbers need not have the same value. The current baseline is revision `3`, bridge version `0.12.20`.

See the [publishing workflow](docs/guides/PUBLISHING.md) for version synchronization and upload checks. Keep bilingual release notes concise, describing fixes and features.

`_metadata/0.png` is the cover; `_metadata/modinfo.json` contains the author and description. Keep the production userdata receiver enabled in the publishing copy; do not overwrite it with unconfigured development defaults. Run `python scripts/check_mod_package.py "<local publishing directory>" --require-receiver` before native game validation. Users still need a separately configured local MCP server.

`exports/`, live-game survey records, logs, and test temporary directories are not distributed with the source. References to those files in historical documents may not resolve in a public checkout.

- [Documentation index](docs/README.md)
- [Planning tools](docs/reference/PLANNING_TOOLS.md)
- [Official mod publishing guide](https://wiki.transportfever3.com/doku.php?id=modding:general:publishing)
