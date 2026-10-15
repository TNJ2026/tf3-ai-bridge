"""MCP server exposing Transport Fever 3 to AI agents via the tf3_mcp_bridge mod."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .bridge import Bridge, BridgeError
from .localization import translate as tr_text
from .map_cache import MapCache
from .planning_app import apps, TOOL_META, card_result
from .subventions import SubventionAutoAccept, make_policy
from .compact import compact_ping, compact_road, compact_status
from .ui_log import UiLogRequests
from .headless import HeadlessRequests
from mcp.types import CallToolResult

ALLOW_EVAL = os.environ.get("TF3_MCP_ALLOW_EVAL", "") == "1"

mcp = MCPServer(
    "tf3",
    extensions=[apps],
    instructions=(
        "Controls a running Transport Fever 3 game through the TF3 MCP Bridge mod. "
        "Call bridge_status first if calls time out: the game must be running a loaded save "
        "with the mod enabled. Entity ids are integers that stay valid while the entity exists. "
        "Planning and siting tools return data only. After completing all planning, call export_planning_report once on the final plan to show its MCP Apps card. Do not automatically open HTML; "
        "the user opens it with the card link if desired."
    ),
)

_bridge: Bridge | None = None
_ui_log_requests = UiLogRequests()
_headless_client = None
_operations_monitor = None


def transport_mode():
    mode = os.environ.get('TF3_MCP_TRANSPORT', 'headless' if os.environ.get('TF3_MCP_HEADLESS_MOD') else 'file')
    if mode not in ('file', 'headless'):
        raise ToolError('TF3_MCP_TRANSPORT must be file or headless')
    return mode


def headless_client():
    global _headless_client
    if _headless_client is None:
        from .headless_client import HeadlessClient
        _headless_client = HeadlessClient(headless())
    return _headless_client


@mcp.tool()
async def bind_headless_session(expected_session: str) -> dict:
    """Explicitly bind the current session after reload and map/entity reconciliation.
    Reads state and map; invalidates route cache. Does not replay pending work."""
    result = await headless_client().bind(expected_session)
    _map_cache.invalidate()
    return result


@mcp.tool()
async def isolate_previous_session_save(request_id: str, expected_session: str) -> dict:
    """Explicit recovery after the user has loaded another session, for an unknown SAVE only.
    Requires user authorization. Preserves the old request as outcome unknown and permanently
    quarantines its save slot against save/load. Never retries, assumes success, loads a save,
    or resumes monitoring. Reads new native identity and pending before unlocking writes.
    Cannot isolate construction, purchases, loans or load requests. Interrupted identity
    verification remains gated and may be continued with these same arguments.
    """
    _map_cache.invalidate()
    return await headless_client().isolate_previous_save(request_id, expected_session)


@mcp.tool()
async def load_game(slot: str, expected_session: str) -> dict:
    """Explicitly load a previously headless-verified local save, without GUI input.
    Requires user authorization to load/roll back, a paused native-load-v1 receiver
    and no pending. Saves current progress to a new independent backup first.
    Checks target hash, publishes once, waits for a new session and independently
    verifies checkpoint time/player/world, map identity and native pending.
    Unknown results are never retried; use verify_loaded_game with the original ID.
    Invalidates cached plans; never starts monitoring or changes game speed.
    First installation still requires loading the updated bridge once.
    """
    _map_cache.invalidate()
    return await headless_client().load_game(slot, expected_session)


@mcp.tool()
async def verify_loaded_game(request_id: str) -> dict:
    """Read back one previously submitted load; never issues another load or clears unknown pending."""
    _map_cache.invalidate()
    return await headless_client().verify_loaded_game(request_id)


@mcp.tool()
async def reconcile_subvention_rejection(request_id: str, expected_session: str) -> dict:
    """Resolve a proven legacy subvention rejection before native dispatch.
    Requires the loaded reconciliation-v1 adapter and matching engine pending.
    Validates durable error, workflow, identity and absence of submission; retains
    the original failure. Never accepts an opportunity, retries, resets quota,
    resolves unknown older submissions, reloads or resumes monitoring.
    """
    return await headless_client().reconcile_subvention_rejection(request_id, expected_session)


@mcp.tool()
async def reset_operation_quota(expected_session: str, expected_round: int, expected_used: int) -> dict:
    """Explicitly open another 256-operation round without reloading the game.
    Read get_validation_state first and supply its exact session/round/used.
    Refuses unresolved host/engine requests and stale quota values. Retains all
    historical request IDs, invalidates old previews, and independently verifies
    the new round. Never retries work, reloads, or starts monitoring. Requires
    the quota-v1 receiver to be loaded; does not revive an old stopped receiver.
    """
    return await headless_client().reset_operation_quota(expected_session, expected_round, expected_used)


@mcp.tool()
async def execute_vehicle_batch(batch_id: str, operations: list[dict], expected_session: str,
                                use_recovery: bool = False) -> dict:
    """Execute 1..64 authorized single-vehicle operations, persisted before dispatch.
    Each item is {command,arguments}. buy_vehicles requires count=1. A later
    assign_vehicles may use purchase_index instead of vehicles to reference an
    earlier purchase. Same batch_id reads its journal, NEVER repeats or resumes it.
    Stops on unknown, partial result or readback mismatch. This does not authorize
    purchases, new spending or resuming a stopped batch; review budget first.
    use_recovery explicitly wraps buy/assign/stopped batches in the persistent
    recovery ledger and requires recovery_control(checkpoint) first."""
    if use_recovery:
        from .recovery_workflows import execute_vehicle_batch as guarded_batch
        return await guarded_batch(_configured_recovery(), batch_id, operations, expected_session)
    from .headless_workflows import VehicleBatches
    return await VehicleBatches(headless_client(), bridge().dir).execute(batch_id, operations, expected_session)


def _configured_recovery():
    import json
    from pathlib import Path
    from .recovery_adapter import HeadlessRecoveryAdapter
    from .recovery_runtime import RecoveryRuntime
    configured = os.environ.get('TF3_RECOVERY_CONFIG')
    if not configured:
        raise ToolError('TF3_RECOVERY_CONFIG is not configured; no game operation sent')
    config = json.loads(Path(os.path.expandvars(configured)).expanduser().read_text(encoding='utf-8-sig'))
    directory = Path(config['stateDirectory'])
    if not directory.is_absolute():
        raise ToolError('Recovery stateDirectory must be absolute')
    return RecoveryRuntime(HeadlessRecoveryAdapter(headless(), directory, config), directory, bridge().dir)


@mcp.tool()
async def recovery_control(action: str = 'status', incident_id: str | None = None,
                           allow_launch: bool = False, max_lost_game_time: float = 0,
                           max_launches: int = 1, allow_unknown_loss: bool = False) -> dict:
    """Opt-in one-shot checkpoint/recovery; never starts a monitor or retries work.

    Configure TF3_RECOVERY_CONFIG with a local JSON file containing stateDirectory,
    gameExecutable, bounded audit queries and an independently validated bootstrap.
    status is local-only. checkpoint saves a paused, audited independent backup.
    recover_once only launches after a confirmed process exit, explicit rollback
    authorization and bounded loss evidence; checks the native loaded map on later
    calls. Unknown/pending operations remain blocked. Does not kill hung games,
    clear pending, auto-develop interfaces or claim long-term simulation safety.
    allow_unknown_loss separately authorizes discarding an unmeasurable amount
    of progress since the pinned checkpoint; defaults to false.
    """
    import json
    from pathlib import Path
    from .recovery_runtime import RecoveryRuntime
    if action not in ('status', 'checkpoint', 'recover_once'):
        raise ToolError('Unknown recovery action')
    configured = os.environ.get('TF3_RECOVERY_CONFIG')
    if not configured:
        if action == 'status':
            return dict(configured=False, monitorEnabled=False, launchEnabled=False)
        raise ToolError('TF3_RECOVERY_CONFIG is not configured; no game operation sent')
    config = json.loads(Path(os.path.expandvars(configured)).expanduser().read_text(encoding='utf-8-sig'))
    directory = Path(config['stateDirectory'])
    if not directory.is_absolute():
        raise ToolError('Recovery stateDirectory must be absolute')
    if action == 'status':
        return RecoveryRuntime(None, directory, directory).read()
    runtime = _configured_recovery()
    if action == 'checkpoint':
        return await runtime.checkpoint()
    return await runtime.recover_once(incident_id, allow_launch=allow_launch,
                                     max_lost_game_time=max_lost_game_time, max_launches=max_launches,
                                     allow_unknown_loss=allow_unknown_loss)


@mcp.tool()
async def operations_monitor(action: str = 'status', interval_seconds: float = 60) -> dict:
    """Read-only new-channel monitoring: status | run_once | start | stop.
    Never starts implicitly. start requires user monitoring authorization.
    Collects account balance, native income if exposed and debt, plus map identity;
    reports changed account risks only, skips busy rounds, no catch-up.
    Stops on errors. No construction, purchases, speed changes, saves or acceptance.
    Writes local rounds; this tool does not itself deliver desktop notifications.
    Cash floor is 1500000. Current finance adapter has no income history;
    cash changes are never reported as income. No historical business reconciliation."""
    global _operations_monitor
    from .headless_workflows import OperationsMonitor
    if _operations_monitor is None:
        _operations_monitor = OperationsMonitor(headless_client(), bridge().dir)
    if action == 'status': return _operations_monitor.status()
    if action == 'stop': return await _operations_monitor.stop()
    if action == 'run_once': return await _operations_monitor.once()
    if action == 'start': return await _operations_monitor.start(interval_seconds)
    raise ToolError('Unknown monitor action')



def headless() -> HeadlessRequests:
    directory = bridge().dir
    configured = os.environ.get("TF3_MCP_HEADLESS_MOD")
    if not configured:
        raise ValueError("Set TF3_MCP_HEADLESS_MOD to the diagnostic mod's content/tf3_mcp_bridge directory")
    from pathlib import Path
    return HeadlessRequests(directory, Path(configured))


@mcp.tool()
async def headless_status() -> dict:
    """Read the opt-in receiver and durable pending request. No game request, GUI
    input, reload or fallback. bounded mode expires after about 34 minutes;
    demand mode waits on a missing filename without consuming idle slots. Native
    cache reclamation remains unverified; do not claim unlimited memory safety."""
    try:
        return headless().status()
    except (ValueError, OSError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
async def send_headless_request(command: str, arguments: dict | None = None,
                                kind: str = "read", expected_session: str | None = None) -> dict:
    """Publish exactly one request without panel input/clicks. kind=save accepts
    save_game(slot, overwrite=False) only; requires a loaded save-capable receiver,
    verified expected_session and paused game. read_headless_result waits for a
    new nonempty stable .sav file, not just the native requested acknowledgement.
    Existing slots require explicit overwrite=True. kind=load accepts load_game
    with slot and backup_save, both previously verified by this channel; requires
    fresh paused-state/pending reads and a recent current-session backup. Prefer
    the named load_game tool, which creates that backup and verifies the new session.
    Low-level load results require verify_loaded_game before further writes.
    Same whitelist as
    prepare_ui_read_request (kind=read) or prepare_ui_build_request (kind=build).
    Engine operations require expected_session from a fresh headless_status plus
    independent map verification. build_* commands preview; commit_* consumes a
    same-session preview. create_line directly creates an empty line (no vehicle)
    and waits for the native callback. buy_vehicles buys exactly one unassigned
    vehicle; assign_vehicles assigns one separately. set_vehicle_stopped and
    send_to_depot change one vehicle. sell_vehicles requires one vehicle physically
    in its depot. get_validation_state reports the loaded command whitelist and
    remaining durable mutation budget. Road/track curves, edge edits, fixed rail
    multiple units and workflows use separate preview/commit steps. Structural-only
    previews remain explicitly labelled. Test removal only permits objects built
    and verified by this channel in the current session. Facility layout is paged;
    review all pages before cloning large facilities. Terrain commits require an
    independently verified backup_save; a filename alone is not backup proof.
    Authorization and pre-mutation save required for these direct operations.
    Durable intent precedes publication. Read the returned ID; unknown outcomes
    block subsequent publication. No retry, GUI fallback or implicit save/speed change."""
    import asyncio
    try:
        return await asyncio.to_thread(headless().send, command, arguments,
                                       kind=kind, expected_session=expected_session)
    except (ValueError, OSError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
async def read_headless_result(request_id: str) -> dict:
    """Read an existing durable request after service restart too. Pending and
    timeout_unknown never authorize resubmission. Reloaded logs require manual
    reconciliation. Saves remain pending until a new nonempty stable file is
    independently verified; an unchanged/missing file never clears the pending lock.
    A verified saved file is not proof that loading it will succeed.
    Successful replies reuse the existing framed log protocol."""
    try:
        return headless().read(request_id)
    except (ValueError, OSError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
async def prepare_ui_read_request(command: str, arguments: dict | None = None) -> dict:
    """Experimental UI/log fallback: game state, finances, map info, or lists of
    towns, lines, vehicles, stations, depots and vehicle models. List limit: 1-500;
    ownership lists accept mine_only. Models accept year (1-9999), carrier
    (ROAD/RAIL/TRAM/WATER/AIR), include_unavailable and limit. Other args rejected.
    Does NOT send it. Enter returned input in the mod panel and click Query once.
    Read the matching ID with read_ui_query_result. No mutations, eval or automatic retries."""
    try:
        return _ui_log_requests.prepare(bridge().dir.parent / "crash_dump" / "stdout.txt", command, arguments)
    except (ValueError, OSError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
async def prepare_ui_build_request(command: str, arguments: dict) -> dict:
    """Prepare, never dispatch, an experimental engine-side UI construction request.
    survey_build_site(x,y) reads nine terrain samples; list_facilities({}) resolves
    current owned construction IDs (map industry IDs are not construction IDs).
    build_warehouse(x,y,z,rotation?,module_count=1|4?) and
    build_facility(source_entity,x,y,z,rotation?) ONLY preview.
    build_helipad(x,y,z,rotation?) and build_heliport(x,y,z,rotation?) ONLY preview;
    road access, shared stock, purchase and flight operation need separate validation.
    commit_facility(preview_token) consumes a successful same-session UI preview once.
    get_facility_config(entity) independently reads back the built configuration.
    get_facility_access(entity, person_graph=True) optionally reads bounded existing HQ PERSON lanes and exact link parameters for directed graph auditing; without this option it reads native automatic links and attached road edges;
    it does not run pathfinding or certify vehicle access, shared stock or throughput.
    preview_headquarters_access(town,road,x,y,z,rotation?) returns a bounded PERSON
    graph from one native placement proposal. Audit both entrance directions before
    a separate build_headquarters preview; it creates no commit token or path query.
    get_facility_inventory(entity) maps a construction, station or station group to
    real STOCK_LIST IDs and deduplicated capacity, with per-station native catchables.
    Missing catchable inventories are explicit unknowns; this does not prove delivery.
    preview_road(start,end,street_type) previews a straight ground road without auto-snap;
    endpoints are {node:id} or {x,y,z?}. commit_road(preview_token) consumes that
    preview once within 60 seconds, rechecks endpoints and reruns native validation.
    get_entity(id) reads current components; list_street_types(filter?) discovers roads.
    get_vehicle_cargo(vehicle,cargo), get_stop_cargo(line,stop_index,cargo), and
    get_stock_cargo(stock_list,cargo,stock_quality?) read one valid cargo resource ID.
    stock_quality=true adds native quality per actual stock slot to diagnose count
    scope differences; aggregate and slot counts remain separate, never inferred.
    Stock reads require a real STOCK_LIST entity and cover at most 64 stock slots;
    use list_map_entities(kind="STOCK_LIST",ids_only=true,snapshot="new") to discover
    IDs without oversized component payloads. Vehicle/stop counts are current;
    stock annualDelivered/annualShipped are engine yearly statistics, not interval
    throughput. A decrease in onboard amount alone does not certify delivery.
    reconcile_road_rejection(request_id) clears only a saved, proven pre-dispatch
    missing-road-preview rejection; never clears native failures or retries it.
    Requires user construction authorization and a pre-build save before commit.
    create_line(station_groups,name) directly creates one empty line, with 2-8
    current station-group IDs and a 1-80 UTF-8 byte name; no vehicle purchase.
    Delayed/unknown results retain the durable mutation block; do not resubmit.
    preview_consist(depot,models=[current model IDs]) reviews 2-8 standalone rail
    parts and sums fresh native part quotes. commit_consist(preview_token) consumes
    the session-bound 60-second preview once, checks quote/resource/owner again,
    and purchases one consist without assigning it. Fixed multiple units are excluded;
    native depot/model compatibility and actual delivery still require live acceptance.
    buy_vehicles(depot,model,count=1) buys one vehicle without assignment; model is
    a resource string, not a numeric index. assign_vehicles(vehicles=[id],line,
    stop_index) is separate and checks the current stop index. set_vehicle_stopped
    (vehicle,stopped) stops/resumes one vehicle; send_to_depot(vehicle) never sells.
    Submit panel input once; read_ui_query_result reads the outcome. Never retry an
    unknown result. Street stops, demolition and arbitrary Lua are excluded.
    """
    try:
        return _ui_log_requests.prepare_build(bridge().dir.parent / "crash_dump" / "stdout.txt", command, arguments)
    except (ValueError, OSError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
async def read_ui_query_result(request_id: str) -> dict:
    """Read a prepared UI query result from the current log window. Pending or
    timeout_unknown never permits a retry. A late result can still be read.
    Reloaded/rewritten logs invalidate requests. IDs belong to this MCP process."""
    try:
        return _ui_log_requests.read(request_id)
    except (ValueError, OSError) as exc:
        raise ToolError(str(exc)) from exc


def bridge() -> Bridge:
    global _bridge
    if _bridge is None:
        _bridge = Bridge()
    return _bridge


async def _fetch_map(args):
    _map_cache.path = bridge().dir / "map_cache.json"
    return await _call("get_route_snapshot", _engine=True, _timeout=30, **args)


_map_cache = MapCache(_fetch_map)


BUILD_TIMEOUT = 30.0  # build commands may try several placements


async def _call(cmd: str, _timeout: float | None = None, _engine: bool = False, **args: Any) -> Any:
    mutation = (cmd.startswith(("build_", "commit_")) or cmd in {"upgrade_road", "bulldoze", "eval"}) and not args.get("preview", False)
    try:
        if transport_mode() == 'headless':
            return await headless_client().call(cmd, args)
        return await bridge().call(cmd, args, timeout=_timeout, engine=_engine)
    except (BridgeError, ValueError, RuntimeError) as e:
        # surface as a tool error the agent can read and react to
        raise ToolError(str(e)) from e
    finally:
        if mutation:
            _map_cache.invalidate()


@mcp.tool()
async def get_terrain_operation_capabilities() -> dict:
    """Read TF3 terrain adapter limits and calibration status. Does not change terrain."""
    return await _call("get_terrain_operation_capabilities", _engine=True)


@mcp.tool()
async def preview_flatten_terrain(bounds: dict, target_height: float,
                                 max_height_change: float = 10, max_edge_grade: float = .10,
                                 transition_width: float = 0) -> dict:
    """Read-only structural preview of a uniform-height rectangle in world metres.
    Bounds={min:{x,y},max:{x,y}} expand outward to base-grid vertices. Includes a
    16m untouched guard band; max 600m per axis, 20000 surveyed vertices. Rejects
    existing entities, water, terrain alignments, excessive cut/fill and boundary
    slopes. transition_width>0 adds a smoothstep blend to original ground (metres,
    at least two base cells, at most 128m), using up to 256 sequential native steps.
    Any partial failure stops without retry. Zero preserves the hard rectangle.
    No road construction. Native Proposal preview is unavailable
    in the tested game binding; explicitly structural_only. Returns a one-use 60s
    token only if clear. Natural flat land remains preferred. No intermediate card.
    """
    return await _call("preview_flatten_terrain", _engine=True, _timeout=30, bounds=bounds,
                       target_height=target_height, max_height_change=max_height_change,
                       max_edge_grade=max_edge_grade, transition_width=transition_width)


@mcp.tool()
async def commit_flatten_terrain(preview_token: str) -> dict:
    """Save an independent native backup, then execute a fresh terrain token ONCE.
    Requires authorized terrain construction. Waits for a new nonempty stable save
    file before submitting; an expired/stale token is rejected. Never retries writes.
    Unknown outcome: get_terrain_operation, refresh terrain, NEVER repeat commit.
    Always re-survey and re-preview facilities/roads afterwards. Optional smooth
    transition executes bounded disjoint native steps with readback after each;
    partial failure stops. No demolition, roads or automatic collection placement.
    """
    import asyncio
    import time
    import uuid
    slot = "tf3_terrain_before_" + uuid.uuid4().hex
    path = bridge().dir.parent / "save" / (slot + ".sav")
    if path.exists():
        raise ToolError("Backup slot unexpectedly exists; no terrain submission")
    if transport_mode() == 'headless':
        saved = await _call('save_game', slot=slot, overwrite=False)
        if saved.get('verified') is not True:
            raise ToolError('Backup not verified; terrain was not submitted')
        result = await _call('commit_flatten_terrain', preview_token=preview_token, backup_save=slot)
        return dict(result, backup_save=slot, backup_path=saved['file']['path'])
    await _call("eval", code=f'app.saveGame("{slot}",function() end,false,true);return {{requested=true}}')
    previous = None
    stable_since = None
    for _ in range(60):
        await asyncio.sleep(.25)
        try:
            stat = path.stat()
            current = (stat.st_size, stat.st_mtime_ns)
        except FileNotFoundError:
            current = None
        if current and current[0] > 0 and current == previous:
            stable_since = stable_since or time.monotonic()
            if time.monotonic() - stable_since >= 1:
                result = await _call("commit_flatten_terrain", _engine=True, _timeout=30,
                                     preview_token=preview_token, backup_save=slot)
                result["backup_save"] = slot
                result["backup_path"] = str(path)
                return result
        else:
            stable_since = None
        previous = current
    raise ToolError(f"Backup write not confirmed ({slot}); terrain was not submitted")


@mcp.tool()
async def get_terrain_operation(operation_id: str) -> dict:
    """Read callback and every sampled modified/guard vertex for a submitted operation.
    Unknown/reloaded operation needs manual receipt reconciliation, never resubmission.
    verified is immediate geometry readback, not proof of long-term simulation safety.
    """
    return await _call("get_terrain_operation", _engine=True, operation_id=operation_id)


@mcp.tool()
async def list_prospections() -> dict:
    """List native exploration resources, compatible industry types and current permits/cooldown."""
    return await _call("list_prospections", _engine=True)


@mcp.tool()
async def get_notifications(include_history: bool = False, offset: int = 0, limit: int = 100) -> dict:
    """Read native notification-bar candidates, or all retained entries with include_history.

    Current means membership in native history and not dismissed, matching the popup-list
    selector; actual rendered pixels/hover state are unknown. Unsupported text renderers
    retain raw params and explicit unknowns. Never dismisses, accepts, or updates notifications.
    Pagination is live, not a snapshot. Requires notificationsVersion=1.
    """
    return await _call("get_notifications", _engine=True, include_history=include_history,
                       offset=offset, limit=limit)


@mcp.tool()
async def get_prospections() -> dict:
    """Read pending native prospecting progress and available success/failure notification history.
    Missing history or disappeared tasks do not prove success. Refresh map after a discovery."""
    return await _call("get_prospections", _engine=True)


@mcp.tool()
async def preview_prospection(town: int, resource: str) -> dict:
    """Check current town, exact exploration resource from list_prospections, permits and duplicates.
    Read-only; returns a one-use 60-second token. Native placement and success are not guaranteed."""
    return await _call("preview_prospection", _engine=True, town=town, resource=resource)


@mcp.tool()
async def commit_prospection(preview_token: str) -> dict:
    """Start native prospecting ONCE using a fresh preview. Preserve a native save first.
    Consumes native permit; never bypasses rank/cooldown, even with infinite money.
    Timeout or unverified result requires readback, NEVER retry. Save operation_id for tracking."""
    return await _call("commit_prospection", _engine=True, preview_token=preview_token)


@mcp.tool()
async def get_prospection_operation(operation_id: str, tracking_receipt: dict | None = None) -> dict:
    """Reconcile one submission against native tasks and new result notifications.
    Pass saved tracking_receipt after an engine Lua state change or reload; never resubmit."""
    return await _call("get_prospection_operation", _engine=True, operation_id=operation_id, tracking_receipt=tracking_receipt)


@mcp.tool()
async def list_facility_resources(kind: str = "construction", search: str = "", offset: int = 0, limit: int = 100) -> dict:
    """Discover every installed construction, metaConstruction template or module.
    Includes availability, native parameter choices and support classification. Paginated.
    Catalog membership does not imply a resource is safely buildable by a generic proposal."""
    return await _call("list_facility_resources", _engine=True, kind=kind, search=search, offset=offset, limit=limit)


@mcp.tool()
async def list_facilities(mine_only: bool = True) -> dict:
    """List current station, warehouse, depot and maintenance construction ids. Requery after reloads."""
    return await _call("list_facilities", _engine=True, mine_only=mine_only)


@mcp.tool()
async def get_facility_config(entity: int) -> dict:
    """Read lossless native parameters, occupied modules, slots, limits and compatible module resources.
    Takes a construction id, not a station group or depot subentity id."""
    return await _call("get_facility_config", _engine=True, entity=entity)


@mcp.tool()
async def configure_facility(entity: int, parameters: dict | None = None, modules: list[dict] | None = None) -> dict:
    """Preview facility configuration ONLY. Modules: [{slot: integer, resource: full resource path}].
    Validates native slot types, availability, replacement and limits; preserves other parameters.
    Native replacement geometry preview is unsafe: this is STRUCTURAL ONLY, not collision validation.
    Removal and nondefault variants are rejected. Returns a one-use 60-second commit token."""
    return await _call("configure_facility", _engine=True, entity=entity, parameters=parameters or {}, modules=modules or [])


@mcp.tool()
async def list_industry_resources() -> dict:
    """List native industry construction resources and whether sandbox placement is enabled."""
    return await _call("list_industry_resources", _engine=True)


@mcp.tool()
async def preview_industry(resource: str, x: float, y: float, rotation: float = 0,
                           on_water: bool = False, seed: str = "tf3-mcp") -> dict:
    """Sandbox only: native industry placement preview at XY, rotation in degrees.
    Terrain elevation/layout come from native map generation. Use a resource from
    list_industry_resources. Rejects removal proposals and collisions. No mutation.
    Returns a single-use 60-second commit token and native resolved placement."""
    return await _call("preview_industry", _engine=True, _timeout=BUILD_TIMEOUT,
                       resource=resource, x=x, y=y, rotation=rotation, on_water=on_water, seed=seed)


@mcp.tool()
async def commit_industry(preview_token: str) -> dict:
    """Commit one sandbox industry after revalidation. Never retry an ambiguous submission;
    inspect get_industry_operation and actual map instead. Does not create freight service."""
    return await _call("commit_industry", _engine=True, _timeout=BUILD_TIMEOUT, preview_token=preview_token)


@mcp.tool()
async def get_industry_operation(operation_id: str) -> dict:
    """Read native callback and independent industry readback; never submits or retries.
    Operation handles expire on bridge reload; unknown does not mean not built."""
    return await _call("get_industry_operation", _engine=True, operation_id=operation_id)


@mcp.tool()
async def build_facility(source_entity: int, x: float, y: float, z: float, rotation: float = 0, name: str = "") -> dict:
    """Preview building a copy of an owned facility's existing native layout (warehouse, harbor,
    airport, station, depot or maintenance station). Explicit elevation z is required.
    Does not connect roads, create lines or buy vehicles. Unknown collisions block the build.
    Includes check.reputation: native UI penalty in percentage points, or available=false.
    Returns a one-use 60-second token; no game mutation occurs until commit_facility."""
    return await _call("build_facility", _engine=True, _timeout=BUILD_TIMEOUT, preview=True,
                       source_entity=source_entity, x=x, y=y, z=z, rotation=rotation, name=name)


@mcp.tool()
async def build_headquarters(town: int, x: float, y: float, z: float, rotation: float = 0, name: str = "") -> dict:
    """Preview the native headquarters main module near a current town (within 1000 m).
    Includes check.reputation: native UI penalty in percentage points, or available=false.
    Checks native permits, duplicate ownership and strict collisions. Does not relocate,
    expand modules or build roads. Reserve future expansion/access space separately.
    Apply once with commit_facility(preview_token); on timeout reconcile, never retry.
    """
    return await _call("build_headquarters", _engine=True, _timeout=BUILD_TIMEOUT, preview=True,
                       town=town, x=x, y=y, z=z, rotation=rotation, name=name)


@mcp.tool()
async def build_warehouse(x: float, y: float, z: float, rotation: float = 0,
                          name: str = "", module_count: int = 4) -> dict:
    """Preview a new universal warehouse without an existing template instance.
    Includes check.reputation: native UI penalty in percentage points, or available=false.
    Uses the installed native starter layout/slot encoding, with 1 or 4 large modules
    (500 or 2000 storage). Explicit dry-land elevation and strict collision validation.
    Apply once with commit_facility. Does not connect roads, build lines, buy vehicles
    or expand the reserved future footprint. Static readback is not simulation safety.
    """
    return await _call("build_warehouse", _engine=True, _timeout=BUILD_TIMEOUT, preview=True,
                       x=x, y=y, z=z, rotation=rotation, name=name, module_count=module_count)


@mcp.tool()
async def build_helipad(x: float, y: float, z: float, rotation: float = 0,
                        name: str = "") -> dict:
    """Preview the native passenger/cargo helicopter station on dry land.
    Includes check.reputation: native UI penalty in percentage points, or available=false.
    Uses module-free native parameters; apply once with commit_facility.
    Road, cargo coverage, lines and vehicles require separate verification.
    """
    return await _call("build_helipad", _engine=True, _timeout=BUILD_TIMEOUT, preview=True,
                       x=x, y=y, z=z, rotation=rotation, name=name)


@mcp.tool()
async def build_heliport(x: float, y: float, z: float, rotation: float = 0,
                         name: str = "") -> dict:
    """Preview a native helicopter station with purchase depot and maintenance.
    Includes check.reputation: native UI penalty in percentage points, or available=false.
    Native layout: 5 parking spaces, maintenance pool 4, service radius 800 m.
    Checks availability, permits, dry land and strict collisions; apply ONCE with
    commit_facility. No roads, lines or vehicles are created. Reserve expansion
    and verify cargo transfers separately. First live validation needs a test save.
    """
    return await _call("build_heliport", _engine=True, _timeout=BUILD_TIMEOUT, preview=True,
                       x=x, y=y, z=z, rotation=rotation, name=name)


@mcp.tool()
async def build_airfield(x: float, y: float, z: float, rotation: float = 0,
                         name: str = "") -> dict:
    """Preview the native small airfield without requiring an existing airport.
    Fixed starter: hangar, main building and one terminal. Checks current era,
    native permits, module resources, dry land and strict collisions. Apply once
    with commit_facility; actual road, passenger and depot service need readback.
    """
    return await _call("build_airfield", _engine=True, _timeout=BUILD_TIMEOUT, preview=True,
                       x=x, y=y, z=z, rotation=rotation, name=name)


@mcp.tool()
async def build_water_facility(kind: str, x: float, y: float, z: float, rotation: float = 0, harbor_size: str | None = None) -> dict:
    """Preview a new native water starter: harbor, shipyard or maintenance.
    Harbor defaults to one small pier (SMALL_SHIP); harbor_size="large" selects
    one medium pier (SHIP/SMALL_SHIP). Size applies only to harbor; shipyard and maintenance
    are separate module-free native facilities. Explicit water elevation is required.
    Returns a single-use commit_facility token after native collision/permission checks.
    No roads, warehouse, lines or vehicles are built. Configuration readback does not
    certify navigation or shared stock. Requires waterHarborLayoutVersion=1 for harbor;
    no legacy or arbitrary Lua fallback.
    """
    extra = {'harbor_size': harbor_size} if harbor_size is not None else {}
    return await _call("build_water_facility", _engine=True, _timeout=BUILD_TIMEOUT, preview=True,
                       kind=kind, x=x, y=y, z=z, rotation=rotation, **extra)


@mcp.tool()
async def commit_facility(preview_token: str) -> dict:
    """Apply a facility preview ONCE with strict native error checking and config readback.
    Have a pre-construction save; use an isolated test save for unvalidated replacement layouts.
    Token is invalidated on use, expiry, reload or changed source. A timeout/partial result requires
    fresh map inspection, NEVER automatic retry. Verified configuration is not simulation safety."""
    return await _call("commit_facility", _engine=True, _timeout=BUILD_TIMEOUT, preview_token=preview_token)


@mcp.tool()
async def bridge_status(verbose: bool = False) -> dict:
    """Check whether the game is connected: heartbeat age, bridge version, game time, paused flag.
    When disconnected, compact output puts historical fields under lastKnown; they are not live state.
    verbose=True adds the full heartbeat and the Lua environment probe (libraries exposed to mods)."""
    if transport_mode() == 'headless':
        status = await headless_status()
        row = status['receiver']
        return dict(status, transport='headless', connected=row['status']=='ready' and status['ageSeconds']<=5,
                    bridgeDir=str(bridge().dir))
    status = bridge().heartbeat()
    status["bridgeDir"] = str(bridge().dir)
    return status if verbose else compact_status(status)


@mcp.tool()
async def ping(echo: str = "", verbose: bool = False) -> dict:
    """Round-trip a request through the game. Useful to verify the command channel works.
    verbose=True includes the Lua environment probe."""
    result = await _call("ping", echo=echo)
    return result if verbose else compact_ping(result)


@mcp.tool()
async def get_game_state() -> dict:
    """Current date, game time, simulation speed (0 = paused), player balance and loan."""
    return await _call("get_game_state")


@mcp.tool()
async def list_towns(limit: int = 500) -> dict:
    """List towns on the map with their entity ids and names."""
    return await _call("list_towns", limit=limit)


@mcp.tool()
async def list_lines(limit: int = 500, mine_only: bool = True) -> dict:
    """List transport lines: id, name, ordered stops (station group ids and names) and assigned vehicle ids."""
    return await _call("list_lines", limit=limit, mine_only=mine_only)


@mcp.tool()
async def list_stations(limit: int = 500, mine_only: bool = True) -> dict:
    """List station groups (what a line stop refers to): id, name, member stations and world position."""
    return await _call("list_stations", limit=limit, mine_only=mine_only)


@mcp.tool()
async def list_depots(limit: int = 500, mine_only: bool = True) -> dict:
    """List vehicle depots: id, carrier (ROAD/RAIL/TRAM/WATER/AIR), position and vehicles currently inside."""
    return await _call("list_depots", limit=limit, mine_only=mine_only)


@mcp.tool()
async def list_vehicles(line: int | None = None, limit: int = 500, mine_only: bool = True) -> dict:
    """List transport vehicles (optionally only those on `line`): state, line, depot, stopped flag, noPath."""
    args: dict[str, Any] = {"limit": limit, "mine_only": mine_only}
    if line is not None:
        args["line"] = line
    return await _call("list_vehicles", **args)


@mcp.tool()
async def list_vehicle_models(
    carrier: str | None = None, year: int | None = None, include_unavailable: bool = False, limit: int = 200
) -> dict:
    """List vehicle models that can be bought (default: available in the current game year), newest first.
    Filter by carrier: ROAD, RAIL, TRAM, WATER or AIR. Returns model name (use it in buy_vehicles),
    price, capacity, top speed and availability years."""
    args: dict[str, Any] = {"limit": limit, "include_unavailable": include_unavailable}
    if carrier:
        args["carrier"] = carrier
    if year:
        args["year"] = year
    return await _call("list_vehicle_models", **args)


@mcp.tool()
async def get_finances() -> dict:
    """Player balance and loan."""
    return await _call("get_finances")


@mcp.tool()
async def get_loans() -> dict:
    """Read live native loan offers, cooldowns, outstanding contracts and repayment amounts.
    Interest is the native total-interest fraction, not APR; months use native accounting time."""
    return await _call("get_loans", _engine=True)


@mcp.tool()
async def preview_loan(action: str, offer_type: str | None = None, loan_id: int | None = None) -> dict:
    """Read-only preview: action='borrow' with an offer_type from get_loans, or 'repay' with loan_id.
    Uses exact current native terms; no custom amounts. Returns a one-use 60-second preview_token.
    Review cash change and payments before committing an authorized in-game transaction."""
    return await _call("preview_loan", _engine=True, action=action, offer_type=offer_type, loan_id=loan_id)


@mcp.tool()
async def commit_loan(preview_token: str) -> dict:
    """Execute an authorized game loan preview ONCE using native Loan events.
    Rejects changed terms, cooldowns, loan limit or insufficient repayment balance.
    On timeout/unverified result NEVER retry: preview_token is also the operation_id for
    get_loan_operation. This tool changes in-game debt and cash, not real-world finances."""
    return await _call("commit_loan", _engine=True, preview_token=preview_token)


@mcp.tool()
async def get_loan_operation(operation_id: str) -> dict:
    """Read-only reconciliation of a submitted loan operation; checks loan records and cash.
    Use the original preview_token even if commit timed out. Unresolved operations block
    further loan commits. After reload, inspect get_loans and the game's finance journal."""
    return await _call("get_loan_operation", _engine=True, operation_id=operation_id)


@mcp.tool()
async def get_subventions(assess: bool = True) -> dict:
    """Read native subventions (补贴任务): proposed, active, completed and failed, with money effects,
    cargo, target and deadlines in game days. With assess=True each proposed cargo task gets an
    estimate of which player lines already serve it, their yearly capacity and the source output."""
    return await _call("get_subventions", _engine=True, assess=assess)


async def _subvention_call(cmd: str, **args: Any) -> Any:
    result = await _call(cmd, _engine=True, **args)
    if transport_mode() == 'headless' and cmd == 'get_subventions':
        result = dict(result, transportSession=headless_client().session)
    return result


_autoaccept = SubventionAutoAccept(_subvention_call, lambda: bridge().dir / "subvention_autoaccept.json")


@mcp.tool()
async def accept_subvention(uid: int, expected_to_deliver: int | None = None, expected_target: int | None = None,
                            expected_upfront_money: int | None = None, expected_failure_money: int | None = None) -> dict:
    """Accept ONE proposed subvention by uid, exactly like the in-game Accept button. Only with user
    authorization. An explicit instruction to accept is sufficient: resolve the current UID with
    get_subventions(assess=False) if needed, then call directly. No prior contract reconciliation,
    network assessment or additional approval is required. The game pays the upfront money and
    applies failure penalties on timeout.
    Expected_* values are re-checked before sending; changed terms abort. The native script applies
    the accept on its next update: confirm with get_subventions. Never resend; a second accept for the
    same uid is refused, including persisted submissions after reload. This does not bypass an
    unrelated transport-level pending request or make an unknown send safe to repeat."""
    if uid in _autoaccept.attempted:
        raise ToolError("auto-accept already attempted this uid; inspect get_subventions")
    expect = {k: v for k, v in dict(toDeliver=expected_to_deliver, target=expected_target,
              upfrontMoney=expected_upfront_money, failureMoney=expected_failure_money).items() if v is not None}
    return await _call("accept_subvention", _engine=True, uid=uid, expect=expect or None)


@mcp.tool()
async def subvention_autoaccept(action: str = "status", min_margin: float = 1.5, max_failure_money: int = 15_000_000,
                                kinds: list[str] | None = None, min_remaining_days: int = 0, max_active: int = 5,
                                interval_seconds: float = 30, dry_run: bool = True) -> dict:
    """Rule-based auto-accept of subventions, polled from this MCP process (stops when it exits).
    action: status | start | stop | run_once. start/run_once take the policy: kinds (default
    deliver_cargo, deliver_cargo_town), min_margin (estimated yearly delivery vs required rate),
    max_failure_money, min_remaining_days, max_active. dry_run=True (default) only logs decisions;
    only start with dry_run=False when the user has authorized automatic acceptance. Each uid is
    attempted once; decisions are logged to subvention_autoaccept.json in the bridge folder.
    submitted is not accepted: accepted lists newly confirmed native Active/Complete/Failed records.
    A pending or unknown outcome blocks all further accepts until native confirmation; never retry."""
    if action == "status":
        return _autoaccept.status()
    if action == "stop":
        await _autoaccept.stop()
        return _autoaccept.status()
    if action not in {"start", "run_once"}:
        raise ToolError("action must be status, start, stop or run_once")
    try:
        policy = make_policy(kinds, min_margin, max_failure_money, min_remaining_days, max_active)
        if action == "start":
            return await _autoaccept.start(policy, interval_seconds, dry_run)
        if _autoaccept.task and not _autoaccept.task.done():
            raise ToolError("auto-accept is running; stop it before a manual run_once")
        _autoaccept.policy, _autoaccept.dry_run = policy, dry_run
        return await _autoaccept.run_once()
    except ValueError as e:
        raise ToolError(str(e)) from e


@mcp.tool()
async def create_line(station_groups: list[int], name: str = "Line", color: list[float] | None = None) -> dict:
    """Create a line visiting `station_groups` (ids from list_stations) in order; vehicles loop back to the
    first stop. `color` is [r, g, b] in 0..1. Returns the new line id."""
    args: dict[str, Any] = {"station_groups": station_groups, "name": name}
    if color:
        args["color"] = color
    return await _call("create_line", **args)


@mcp.tool()
async def delete_line(line: int) -> dict:
    """Delete a line. The game refuses while vehicles are still assigned to it."""
    return await _call("delete_line", line=line)


@mcp.tool()
async def buy_vehicles(depot: int, model: str, count: int = 1, line: int | None = None) -> dict:
    """Buy `count` vehicles of `model` (name or id from list_vehicle_models) into `depot`, and optionally
    send them to `line` right away. The model's carrier must match the depot's. Returns bought vehicle ids
    and per-vehicle failures (e.g. not enough money)."""
    args: dict[str, Any] = {"depot": depot, "model": model, "count": count}
    if line is not None:
        args["line"] = line
    return await _call("buy_vehicles", **args)


@mcp.tool()
async def assign_vehicles(line: int, vehicles: list[int], stop_index: int = 0) -> dict:
    """Assign existing vehicles to a line, sending them first to stop `stop_index` (0-based)."""
    return await _call("assign_vehicles", line=line, vehicles=vehicles, stop_index=stop_index)


@mcp.tool()
async def sell_vehicles(vehicles: list[int]) -> dict:
    """Sell vehicles immediately, wherever they are."""
    return await _call("sell_vehicles", vehicles=vehicles)


@mcp.tool()
async def send_to_depot(vehicle: int, sell_on_arrival: bool = False) -> dict:
    """Send a vehicle to the nearest reachable depot, optionally selling it when it arrives."""
    return await _call("send_to_depot", vehicle=vehicle, sell_on_arrival=sell_on_arrival)


@mcp.tool()
async def set_vehicle_stopped(vehicle: int, stopped: bool = True) -> dict:
    """Stop or restart a vehicle, like the stop button in the vehicle window."""
    return await _call("set_vehicle_stopped", vehicle=vehicle, stopped=stopped)


@mcp.tool()
async def get_industry_bonuses(industry: int) -> dict:
    """Read one current industry's worker and cargo bonuses and internal transfer targets.
    Citizens must reach the industry internal passenger transfer; booster goods must
    reach its internal cargo transfer/stock. Nearby warehouse inventory is not delivery.
    Reports native worker capacity, threshold, visitor window/counts, applied multiplier,
    and potential multiplier only when safely available. Cargo input alternatives map
    stock indices to actual cargo IDs/names/quantities; configuration is not activation.
    Unknown fields stay explicit. Read-only: no routing, purchases, speed/RNG changes.
    Requires loaded industryBonusesVersion=1; accepts industry entity, not construction ID.
    """
    return await _call("get_industry_bonuses", _engine=True, industry=industry)


@mcp.tool()
async def get_entity(id: int, components: list[str] | None = None) -> dict:
    """Inspect an entity by id. `components` is a list of component type names such as
    NAME, TOWN, LINE, STATION, INDUSTRY, TRANSPORT_VEHICLE, CONSTRUCTION; defaults to common ones."""
    args: dict[str, Any] = {"id": id}
    if components:
        args["components"] = components
    return await _call("get_entity", **args)


@mcp.tool()
async def get_map_info() -> dict:
    """Whole-map bounds in metres, terrain resolutions, climate, and all town/industry
    ids, names or types and coordinates. Does not export a heightmap or all simulation data."""
    return await _call("get_map_info")


@mcp.tool()
async def list_map_entities(kind: str = "CONSTRUCTION", offset: int = 0, limit: int = 100, snapshot: str | None = None, ids_only: bool = False) -> dict:
    """Read a page of whole-map entities, including other players' entities.
    Kinds: TOWN, INDUSTRY, CONSTRUCTION, TOWN_BUILDING, BASE_NODE, BASE_EDGE,
    STATION, STATION_GROUP, VEHICLE_DEPOT, TRANSPORT_VEHICLE, SIM_PERSON, LINE,
    WATER_MESH, MODEL_INSTANCE_LIST, ASSET_GROUP, SIM_CARGO, STOCK_LIST,
    TERRAIN_TILE_BRUSH. Model/asset entities return instance counts; use
    get_component_collection on fatInstances/thinInstances for models and transforms.
    The spatial model index covers renderable entities, not only trees. Asset,
    cargo, stock and brush queries scan the full entity index on each call.
    Limit is 1..500. Follow nextOffset while hasMore; total is the full index count.
    For stable pagination, pass snapshot="new" at offset 0, then reuse the returned
    snapshot token. This fixes IDs only; fields remain live and deleted entities
    return missing=true. Snapshots last 300 seconds; at most 4 are retained, each
    capped at 250000 IDs. Release when done. Without a snapshot, entity changes
    can shift offsets. Reloading the save invalidates snapshots.
    ids_only=true omits component payloads, useful for large stock records.
    Unreadable fields are explicitly marked; this is not a complete save export."""
    args = dict(kind=kind, offset=offset, limit=limit)
    if snapshot is not None:
        args["snapshot"] = snapshot
    if ids_only:
        args["ids_only"] = True
    return await _call("list_map_entities", **args)


@mcp.tool()
async def release_map_snapshot(snapshot: str) -> dict:
    """Release an ID snapshot after a paginated map traversal. Does not affect the game."""
    return await _call("release_map_snapshot", snapshot=snapshot)


@mcp.tool()
async def get_terrain_grid(
    x: float | None = None, y: float | None = None, spacing: float = 64,
    columns: int | None = None, rows: int | None = None,
    offset: int = 0, limit: int = 512, mode: str = "surface",
) -> dict:
    """Page through terrain heights and water flags, in row-major order (x fastest).
    Defaults cover the whole map starting at its minimum corner, sampled every 64 m.
    Supply x/y and columns/rows for a region. Spacing >=1 m; limit 1..1024 samples.
    mode=surface includes terrain alignments, base reads the underlying 4 m terrain.
    Follow nextOffset with the same grid parameters. Live samples, not a fixed snapshot;
    coarse spacing does not capture all terrain detail or exact water boundaries."""
    args = dict(spacing=spacing, offset=offset, limit=limit, mode=mode)
    for name, value in (("x", x), ("y", y), ("columns", columns), ("rows", rows)):
        if value is not None:
            args[name] = value
    return await _call("get_terrain_grid", **args)


@mcp.tool()
async def get_component_collection(id: int, component: str, field: str, offset: int = 0, limit: int = 100) -> dict:
    """Page a supported component collection without the normal 2000-item truncation.
    Examples: WATER_MESH vertices/indices/contours; MODEL_INSTANCE_LIST fatInstances/
    thinInstances; TERRAIN_TILE_HEIGHTMAP vertices; STOCK_LIST stocks/rules.
    Returns original Lua keys with values, sorted by key; offsets are zero-based,
    original keys retain their game indexing. Limit 1..1024, live data."""
    return await _call("get_component_collection", id=id, component=component, field=field, offset=offset, limit=limit)


@mcp.tool()
async def get_terrain_tile(tile_x: int, tile_y: int) -> dict:
    """Get the entity and available data of a 256 m terrain tile. Tile coordinates
    are world coordinates divided by 256, including negative coordinates.
    Use its id with get_component_collection for raw height vertices or brush data.
    Missing brush data is reported explicitly; raw heights are not metres."""
    return await _call("get_terrain_tile", tile_x=tile_x, tile_y=tile_y)


@mcp.tool()
async def get_map_data(layer: str | None = None, offset: int = 0, limit: int = 512) -> dict:
    """List terrain data layers, or page one layer's raw cells (limit 1..1024).
    May include biome*, forest_mask and river_mask. Row-major, x varies fastest.
    These are simulation/generation data layers, not rendered texture pixels."""
    args = dict(offset=offset, limit=limit)
    if layer is not None:
        args["layer"] = layer
    return await _call("get_map_data", **args)


@mcp.tool()
async def set_game_speed(speed: int) -> dict:
    """Set the simulation speed multiplier. 0 pauses; 1, 2, 4 are the usual in-game speeds."""
    return await _call("set_game_speed", speed=speed)


@mcp.tool()
async def get_town_cargo_supply(town: int, include_passengers: bool = False) -> dict:
    """Read native city-panel cargo supply, demand and ratios without building scans.

    Requires loaded townCargoSupplyVersion=2. Includes per-land-use display
    rounding, raw values and cargo-ID totals. Zero demand has no ratio.
    Native temporal window is unspecified; these are not annual delivery counts.
    include_passengers requires townPassengerSupplyVersion=1 and adds the native
    residential passenger panel metric separately: line-usage-derived supply,
    residential demand, and raw line usage. It is not a boarding counter or bus-only.
    """
    args = {"town": town}
    if include_passengers:
        args["include_passengers"] = True
    return await _call("get_town_cargo_supply", _engine=True, **args)


@mcp.tool()
async def get_town_cargo_needs(town: int) -> dict:
    """Read current residential/commercial/industrial cargo-kind IDs (not quantities)."""
    return await _call("get_town_cargo_needs", town=town)


@mcp.tool()
async def preview_town_cargo_needs(
    town: int,
    residential: list[int] | None = None,
    commercial: list[int] | None = None,
    industrial: list[int] | None = None,
    update_buildings: bool = False,
) -> dict:
    """Validate a city cargo-kind edit without changing the game; returns a 60s token.
    Omitted districts stay unchanged; each edited district must keep its original
    number of cargo kinds (no addition or removal). IDs are native
    zero-based cargo IDs, excluding passengers. At least one district is required.
    update_buildings=True requests immediate building updates and may affect capacities.
    This is structural validation, not a native construction preview or simulation test.
    Does not set annual quantities or guarantee persistence through city growth/reload.
    """
    args = dict(town=town, update_buildings=update_buildings)
    for key, value in (("residential", residential), ("commercial", commercial), ("industrial", industrial)):
        if value is not None:
            if any(type(v) is not int or v <= 0 for v in value) or len(value) != len(set(value)):
                raise ValueError("Cargo IDs must be distinct positive integers")
            args[key] = value
    if all(v is None for v in (residential, commercial, industrial)):
        raise ValueError("Provide at least one district")
    return await _call("preview_town_cargo_needs", **args)


@mcp.tool()
async def commit_town_cargo_needs(preview_token: str) -> dict:
    """Submit an authorized cargo-kind edit once after saving a backup.
    Rejects stale town/session or changed needs. Unknown/partial results require
    get_town_cargo_operation or fresh readback; never resend the same submission.
    verified covers town cargo-kind readback, not building capacities or long-term safety.
    """
    return await _call("commit_town_cargo_needs", preview_token=preview_token)


@mcp.tool()
async def get_town_cargo_operation(operation_id: str) -> dict:
    """Read back a submitted city cargo-kind edit without resending it.
    Tokens/operations are local to the loaded bridge session; after reload read town
    needs afresh and reconcile against your saved receipt, never blindly retry.
    """
    return await _call("get_town_cargo_operation", operation_id=operation_id)


# --- construction -------------------------------------------------------------------
# Coordinates are world metres (x east, y north); heights follow the terrain automatically.
# Every build tool takes preview=True for a dry run that returns cost and problems. Builds are
# refused when they would clear town buildings, streets or other constructions (listed under
# reason.blocking); pass allow_collisions=True to clear them anyway. Trees and rocks are cleared
# automatically, like in the game's own tools.


@mcp.tool()
async def get_terrain(x: float, y: float) -> dict:
    """Terrain height at a world position and whether it is water."""
    return await _call("get_terrain", x=x, y=y)


@mcp.tool()
async def find_nearby(x: float, y: float, radius: float = 100, limit: int = 15) -> dict:
    """What is around a position: street nodes (with the direction of every street leaving them, in
    degrees, 0 = east, 90 = north), street segments (with how many stops/signals they carry), station
    groups, non-town constructions, and how many town buildings. Use it to pick where to connect or
    place things; a new street joining a node needs a clear angle to the streets already there."""
    return await _call("find_nearby", x=x, y=y, radius=radius, limit=limit)


@mcp.tool()
async def list_street_types(filter: str | None = None) -> dict:
    """Street types for build_road, e.g. town/town_old_small or country/country_new_medium."""
    args: dict[str, Any] = {}
    if filter:
        args["filter"] = filter
    return await _call("list_street_types", **args)


@mcp.tool()
async def capture_planning_snapshot(output_dir: str, bounds: dict | None = None, spacing: float = 250,
                                    include_flat_areas: bool = True) -> dict:
    """Read-only full-map or local survey without requiring existing stations; never pauses/builds.
    bounds={min:{x,y},max:{x,y}} in world metres; omit for whole map. spacing=25..2000,
    <=100000 samples. Saves terrain, available obstacle bounds, towns/industries and state as JSON.
    Returns snapshot_path for plan_global_development / plan_local_development.
    By default also derives flat_areas_path locally from the same samples: connected dry,
    gentle terrain cells, not obstacle-free/buildable land. No extra game query or card.
    Coarse samples, missing bounds and stale IDs cannot authorize construction. Requires bridge 0.11.0.
    """
    from .development_planner import box, number, save_json, validate_snapshot
    number(spacing, 'spacing', 25)
    if spacing > 2000:
        raise ToolError('spacing must be <= 2000')
    if bounds is not None:
        box(bounds)
    snapshot = await _call('get_planning_snapshot', _engine=True, _timeout=30, bounds=bounds, spacing=spacing)
    validate_snapshot(snapshot)
    from datetime import datetime, timezone
    snapshot['capturedAt'] = datetime.now(timezone.utc).isoformat()
    path = save_json(snapshot, output_dir, 'snapshot')
    flat = {}
    if include_flat_areas:
        import asyncio
        from .flat_areas import FlatTerrain
        report = await asyncio.to_thread(lambda: FlatTerrain(snapshot['grid']).report())
        flat = dict(flat_areas_path=save_json(report, output_dir, 'flat-areas'),
                    flat_areas_summary=report['summary'],flat_areas_refinement=report['refinement'])
    return dict(snapshot_path=path, scope=snapshot['scope'], state=snapshot['state'],
                terrainSamples=len(snapshot['grid']['heights']), obstacles=len(snapshot['obstacles']),
                towns=snapshot['map']['towns'], industries=snapshot['map']['industries'],
                coverage=snapshot['coverage'], consistency=snapshot['consistency'], **flat)


def _planning_result(plan, summary):
    from mcp.types import TextContent
    import json
    result = dict(summary, scope=plan['scope'], display='data only; call export_planning_report once after all planning is complete')
    return CallToolResult(content=[TextContent(type='text', text=json.dumps(result, ensure_ascii=False))], structured_content=result)


async def _planning_card(plan, output_dir, summary, width=1600, height=1100):
    import asyncio
    from .planning_report import export_report
    report = await asyncio.to_thread(export_report, plan, output_dir, width, height)
    return await asyncio.to_thread(card_result, plan, report, summary)


@mcp.tool()
async def plan_global_development(snapshot_path: str, focus_town: int, output_dir: str,
                                  neighbor_count: int = 2, supply_chains: list[dict] | None = None) -> CallToolResult:
    """Offline regional plan: focus city, nearby-city candidates, industry inventory, phases and supply balance.
    snapshot_path from capture_planning_snapshot. Distances only screen candidates, not passenger demand.
    Optional supply_chains: [{name,cargo,time_unit,evidence:'measured'|'forecast',demand,production,
    transport,handling,delivery,batch,delay,storage}]. Rates must share ONE time unit and finished-cargo
    equivalents; sum all cities sharing a chain. delay uses that unit; batch/storage are cargo quantities.
    Missing demand is UNKNOWN, not zero. Saves plan JSON and returns data only. Call export_planning_report once after all planning is complete; never builds.
    """
    import asyncio
    from .development_planner import plan_global, read_snapshot, save_json
    plan = await asyncio.to_thread(plan_global, read_snapshot(snapshot_path), focus_town, neighbor_count, supply_chains)
    path = save_json(plan, output_dir, 'global-plan')
    summary = dict(plan_path=path, neighbors=plan['neighbors'], supply=plan['supply'], phases=plan['phases'],
                warnings=plan['warnings'], buildable=None)
    return _planning_result(plan, summary)


@mcp.tool()
async def plan_local_development(snapshot_path: str, output_dir: str, sites: list[dict] | None = None,
                                 corridors: list[dict] | None = None, supply_chains: list[dict] | None = None,
                                 title: str | None = None) -> CallToolResult:
    """Offline local layout validation and road/rail corridor search; never builds or assumes ports connect.
    Need candidate positions first? Use find_facility_sites to batch-screen this same snapshot locally.
    sites=[{name,current:{min:{x,y},max:{x,y}},reserved:{min:{x,y},max:{x,y}},basis:'estimate or native dimensions'}].
    reserved includes current footprint PLUS upgrade/access space. Detects native and proposed overlaps.
    corridors=[{name,mode:'road'|'rail',start:{x,y},end:{x,y}}]; endpoints must be outside facilities/reserves.
    Avoids building bounds and reserves; reports water, ground grade and road crossings, not designed grades.
    supply_chains schema matches plan_global_development. For rail engineering use plan_rail_connection
    with fresh real construction IDs next. Saves plan JSON and returns data only. Call export_planning_report once on the final plan.
    """
    import asyncio
    from .development_planner import plan_local, read_snapshot, save_json
    plan = await asyncio.to_thread(plan_local, read_snapshot(snapshot_path), sites, corridors, supply_chains, title)
    path = save_json(plan, output_dir, 'local-plan')
    summary = dict(plan_path=path, sites=plan['sites'], routes=[{k:v for k,v in r.items() if k!='path'} for r in plan['routes']],
                supply=plan['supply'], warnings=plan['warnings'], buildable=None)
    return _planning_result(plan, summary)


@mcp.tool()
async def find_facility_sites(snapshot_path: str, output_dir: str, requests: list[dict],
                              max_candidates: int = 3, max_evaluations: int = 10000,
                              reserved_areas: list[dict] | None = None) -> CallToolResult:
    """Fast offline batch siting on ONE planning snapshot; no live queries, previews or construction.
    requests (1..20): [{name,kind:'facility'|'street_stop',target:{x,y},radius:300,
      current:{min:{x,y},max:{x,y}},reserved:{min:{x,y},max:{x,y}},basis:'dimensions source',
      step:25,rotations:[0,90],max_height_range:5,terrain_policy:'advisory',
      min_separation:50,ranking:'flat_first'}].
    Footprint boxes are LOCAL offsets from placement origin; reserved must include current plus upgrade/access.
    street_stop requires edges:[snapshot edge IDs known to be streets]; searches param .25/.5/.75,
    local X along road tangent; ignores only its supporting edge, requires live street/terminal validation.
    reserved_areas are WORLD boxes already committed in other plans, never ignored as host edges.
    Screens sampled land and obstacle/upgrade bounds; defaults to flat-ground-first
    ranking (sampled ground grade, height range, then distance). ranking='distance_height'
    explicitly retains distance + 20*heightRange. Ground grade is not a native build limit.
    Buildings default to terrain_policy='advisory': max_height_range is a reference,
    not a rejection threshold; higher ground relief remains eligible for native preview.
    terrain_policy='strict' explicitly filters by max_height_range (always required for street_stop).
    Neither mode changes terrain or guarantees adaptation. Water, unknown survey bounds,
    collision reservations and separately requested road-access screening still apply.
    Returns up to 1..10 spatially separated ALTERNATIVES per request, not a simultaneous layout.
    Budget 1..20000 evaluations; narrow range/increase step if exceeded. Water facilities not supported.
    Saves candidate plan JSON and returns data only; no intermediate card. Export only the final plan using export_planning_report. Fresh entities and native
    previews are still mandatory for shortlisted sites; no candidate is a construction approval.
    """
    import asyncio
    from .development_planner import read_snapshot, save_json
    from .site_planner import search_sites
    def prepare():
        plan = search_sites(read_snapshot(snapshot_path), requests, max_candidates, max_evaluations, reserved_areas)
        path = save_json(plan, output_dir, 'site-search')
        return plan, path
    plan, path = await asyncio.to_thread(prepare)
    return _planning_result(plan, dict(plan_path=path, searches=plan['searches'],
                               metrics=plan['metrics'], warnings=plan['warnings'], buildable=None))


@mcp.tool(meta=TOOL_META)
async def export_planning_report(plan_path: str, output_dir: str, width: int = 1600, height: int = 1100) -> CallToolResult:
    """Show an MCP Apps image card and export a saved global/local plan to self-contained interactive HTML, PNG, SVG and JSON.
    HTML supports zoom/layer toggles; north is up and coordinates are world metres. No external network/game calls.
    A loopback-only link opens the report ONLY when the user clicks it; never auto-open HTML.
    Creates a unique report directory and returns absolute file paths. PNG CJK font can be set with
    TF3_PLANNING_FONT. Dimensions 800..4096 x 600..4096. Never overwrites earlier reports.
    """
    import json
    from pathlib import Path
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8-sig'))
    return await _planning_card(plan, output_dir, dict(plan_path=plan_path), width, height)


@mcp.tool()
async def plan_rail_connection(
    start_construction: int,
    end_construction: int,
    spacing: float = 100,
    max_candidates: int = 3,
    output_dir: str | None = None,
) -> CallToolResult:
    """Read-only railway planning between station CONSTRUCTION ids.
    Use revision-cached whole-map data. Start straight, detour around towns/buildings,
    then solve grades and road crossings locally. Cache hits need no game request. Never builds or pauses.
    Returns approximate candidates with sampled path, bridge/tunnel lengths and diagnostics.
    No candidate is a construction approval: native preview and fresh endpoint checks remain required.
    Prefer this to repeated get_terrain/find_nearby calls. Used ports are excluded.
    Saves plan JSON and returns data only; export_planning_report shows the final card after planning. output_dir defaults to TF3_PLANNING_DIR or exports/plans.
    """
    from .staged_planner import plan_staged
    if start_construction == end_construction:
        raise ToolError("Choose two different station constructions")
    if not 1 <= max_candidates <= 10:
        raise ToolError("max_candidates must be 1..10")
    if transport_mode() == 'headless':
        try:
            current = await headless_client().status()
            if (_map_cache.snapshot and _map_cache.snapshot.get('headlessSession')
                    != current['receiver']['session']):
                _map_cache.invalidate()
        except (ValueError, RuntimeError) as exc:
            _map_cache.invalidate()
            raise ToolError(str(exc)) from exc
    snapshot, status = await _map_cache.refresh(start_construction, end_construction, spacing=spacing)
    import asyncio
    result = await asyncio.to_thread(plan_staged, snapshot, max_candidates)
    result["cache"] = status
    result["stats"]["bridgeRequests"] = 0 if status["hit"] else 1
    if output_dir is None:
        output_dir = os.environ.get('TF3_PLANNING_DIR', 'exports/plans')
    if output_dir is not None:
        from .development_planner import base_plan, save_json
        plan = base_plan(snapshot, tr_text('铁路连接候选方案', 'Rail connection candidates'), 'rail', [])
        plan['routes'] = [dict(c, name=f"{tr_text('候选', 'Candidate')} {i+1}", mode='rail', status='sampled_candidate') for i,c in enumerate(result['candidates'])]
        plan['phases'] = [dict(name=tr_text('工程复核', 'Engineering review'), actions=[tr_text('刷新站端口、曲率、坡度与桥隧条件', 'Refresh station ports, curvature, grades and bridge/tunnel conditions'), tr_text('比较候选，执行原生预览', 'Compare candidates and run native previews')], gate=tr_text('原生预览及用户建设授权', 'Native preview and user construction authorization'))]
        plan['warnings'].append(result['limitation'])
        result['plan_path'] = save_json(plan, output_dir, 'rail-plan')
    return _planning_result(plan, result)


@mcp.tool()
async def map_cache_control(action: str = "status", start_construction: int | None = None,
                            end_construction: int | None = None) -> dict:
    """Start/stop 15-second revision polling, force refresh, invalidate, or inspect map cache.
    start/refresh need two station construction ids. Terrain is reused while revisions match.
    Polling is read-only; stops when this MCP process exits. No notification subscription is assumed.
    """
    if action == "status": return _map_cache.status()
    if action == "stop":
        await _map_cache.stop()
        return _map_cache.status()
    if action == "invalidate":
        _map_cache.invalidate()
        return _map_cache.status()
    if action not in {"start", "refresh"}:raise ToolError("invalid cache action")
    if start_construction is None or end_construction is None or start_construction == end_construction:
        raise ToolError("two different construction ids required")
    if action == "start":return await _map_cache.start(start_construction,end_construction)
    _, status = await _map_cache.refresh(start_construction,end_construction,force=True)
    return status


@mcp.tool()
async def build_road(
    start: dict,
    end: dict,
    via: list[dict] | None = None,
    street_type: str = "town/town_old_small",
    preview: bool = False,
    allow_collisions: bool = False,
    snap_radius: float = 5,
    max_segment_length: float = 50,
    include_path: bool = False,
) -> dict:
    """Build a straight street from `start` to `end`, optionally through `via` points.
    Each point is {"node": id} for an existing street node, or {"x": .., "y": ..}; a coordinate within
    `snap_radius` metres of an existing STREET node joins that node (via points only snap with their own
    `snap` value). Optional `z` sets elevation; legs touching such points interpolate elevation, otherwise
    they follow terrain. `max_segment_length` is 10..200 metres (default 50); at most 128 points/512 segments.
    Preview returns cost, blocking entities, resolved `points`, a path summary (pathPoints, minZ/maxZ,
    maxGradePercent and where) and `buildable`; it never builds. include_path=True returns the full sampled
    `path` and per-node id lists instead of summaries.
    This builds normal ground roads; it does not split existing edges or automatically create bridges/tunnels.
    On failure `reason` explains it: `blocking` lists buildings/streets in the way; `messages` holds the
    game's own errors (e.g. too sharp an angle at a junction). Returns current node and segment ids.
    built only means geometry exists; complete/verified require direct two-way CAR and TRUCK paths
    at every joined node. Failed connections are refreshed once after construction. If built=True but
    complete=False, inspect connections/reason; do NOT repeat the build (it already exists)."""
    args: dict[str, Any] = {"start": start, "end": end, "street_type": street_type, "preview": preview,
                            "allow_collisions": allow_collisions, "snap_radius": snap_radius,
                            "max_segment_length": max_segment_length}
    if via:
        args["via"] = via
    result = await _call("build_road", _timeout=BUILD_TIMEOUT, **args)
    return result if include_path else compact_road(result)


@mcp.tool()
async def upgrade_road(
    edge: int,
    street_type: str,
    preview: bool = True,
    expected_street_type: str | None = None,
) -> dict:
    """Change one existing ground road's street type, preserving geometry and junction nodes.
    Defaults to a structural preview: before/after types and endpoints, NOT cost or collision validation.
    To apply, use preview=False; optionally pass expected_street_type from preview's fromType to detect
    a changed road. The native game command rejects errors without forcing collisions. Returns changed,
    applied, verified and replacement edges (ids may change). Same-type requests return noChange.
    Tracks, bridges/tunnels, construction-owned roads and roads with stops/edge objects are unsupported.
    """
    args: dict[str, Any] = {"edge": edge, "street_type": street_type, "preview": preview}
    if expected_street_type is not None:
        args["expected_street_type"] = expected_street_type
    return await _call("upgrade_road", _timeout=BUILD_TIMEOUT, **args)


@mcp.tool()
async def repair_orphan_street_stop(entity: int, preview: bool = True) -> dict:
    """Remove a failed roadside stop only if it has neither a road owner nor a station.
    Defaults to preview. Refuses valid stops, other objects and collision overrides.
    Set preview=False to remove the one orphan, preserving roads and normal stations.
    """
    return await _call("repair_orphan_street_stop", _timeout=BUILD_TIMEOUT,
                       entity=entity, preview=preview)


@mcp.tool()
async def build_street_stop(
    edge: int | None = None,
    x: float | None = None,
    y: float | None = None,
    param: float | None = None,
    radius: float = 50,
    two_sided: bool = True,
    side: str = "right",
    kind: str = "auto",
    name: str | None = None,
    preview: bool = True,
) -> dict:
    """Preview a roadside bus stop on an edge or near (x,y), including cost and collisions.
    two_sided previews both directions. param is 0.15..0.85 along the street.
    Set preview=False to construct once after collision and terminal-node checks.
    Returns both station IDs, groups, and post-build verification. A failed apply may
    partially change the world: inspect the result before retrying. Collision overrides
    and legacy experimental bypasses are not supported.
    Use find_facility_sites with explicitly surveyed street edges to shortlist positions offline first.
    """
    args = {"edge": edge, "x": x, "y": y, "param": param, "radius": radius,
            "two_sided": two_sided, "side": side, "kind": kind, "name": name, "preview": preview}
    return await _call("build_street_stop", _timeout=BUILD_TIMEOUT,
                       **{k: v for k, v in args.items() if v is not None})


@mcp.tool()
async def build_depot(
    x: float,
    y: float,
    carrier: str = "ROAD",
    face_towards: dict | None = None,
    rotation: float | None = None,
    connect: bool = True,
    street_type: str = "town/town_old_small",
    preview: bool = False,
    allow_collisions: bool = False,
    name: str | None = None,
) -> dict:
    """Build a vehicle depot (carrier ROAD, TRAM, RAIL or WATER) centred at (x, y). Its entrance faces
    `face_towards` ({"x", "y"}), else `rotation` degrees, else the nearest street node. With connect=True a
    ROAD/TRAM depot's entrance is joined to the nearest reachable street node. Put it ~25 m from the
    street so the entrance lands next to it. Returns the depot id for buy_vehicles."""
    args: dict[str, Any] = {"x": x, "y": y, "carrier": carrier, "connect": connect, "street_type": street_type,
                            "preview": preview, "allow_collisions": allow_collisions}
    if face_towards:
        args["face_towards"] = face_towards
    if rotation is not None:
        args["rotation"] = rotation
    if name:
        args["name"] = name
    return await _call("build_depot", _timeout=BUILD_TIMEOUT, **args)


@mcp.tool()
async def build_rail_station(
    x: float,
    y: float,
    tracks: int = 2,
    length: int = 160,
    rotation: float = 0,
    specialization: str = "universal",
    preview: bool = True,
    allow_collisions: bool = False,
    name: str | None = None,
    cargo: bool = True,
) -> dict:
    """Build a through railway station with 1..4 tracks and 80/120/160/240/320 m platforms.
    Defaults to cargo; cargo=False creates passenger platforms, stairs and an era-specific main building.
    Passenger stations require specialization='universal'.
    Rotation is degrees counterclockwise; tracks run along local Y. Uses unelectrified simple track.
    Specialization: universal, liquid, bulk, flatbed or goods. Defaults to preview with cost/errors.
    Set preview=False to construct. Returns construction, stations, stationGroups and railPorts/roadPorts.
    External roads/railways are NOT built; verified checks station/rail ports, not train route reachability.
    """
    args: dict[str, Any] = {"x": x, "y": y, "tracks": tracks, "length": length,
        "rotation": rotation, "specialization": specialization, "preview": preview,
        "allow_collisions": allow_collisions, "cargo": cargo}
    if name is not None:
        args["name"] = name
    return await _call("build_rail_station", _timeout=BUILD_TIMEOUT, **args)


@mcp.tool()
async def build_station(
    x: float,
    y: float,
    size: int = 1,
    cargo: bool = False,
    face_towards: dict | None = None,
    rotation: float | None = None,
    connect: bool = True,
    street_type: str = "town/town_old_small",
    preview: bool = False,
    allow_collisions: bool = False,
    name: str | None = None,
) -> dict:
    """Build a street station (bus terminal, or truck station with cargo=True) centred at (x, y) and
    join its entrance to the nearest street, like build_depot. size 1-3 = number of platform pairs.
    Its entrance is 15 m from the centre towards `face_towards`, else `rotation`, else the nearest
    street node, so place it ~20 m from the street. Returns stationGroup for create_line.
    For roadside stops use build_street_stop. For batch site screening use find_facility_sites."""
    args: dict[str, Any] = {"x": x, "y": y, "size": size, "cargo": cargo, "connect": connect,
                            "street_type": street_type, "preview": preview, "allow_collisions": allow_collisions}
    if face_towards:
        args["face_towards"] = face_towards
    if rotation is not None:
        args["rotation"] = rotation
    if name:
        args["name"] = name
    return await _call("build_station", _timeout=BUILD_TIMEOUT, **args)


@mcp.tool()
async def preview_depot_removal(entity: int) -> dict:
    """Preview removal of ONE owned empty road depot (construction or depot ID).
    Requires paused simulation. Checks returning vehicles and native removal scope;
    no makeProposalData on removal proposals. Structural preview, not native acceptance.
    Returns a session-bound one-use 60-second token. Maintenance coverage will change.
    """
    return await _call("preview_depot_removal", entity=entity)


@mcp.tool()
async def commit_depot_removal(preview_token: str) -> dict:
    """Save/verify an independent backup, then remove the previewed empty road depot ONCE.
    Requires user demolition authorization, paused game and headless depotRemovalVersion=1.
    No vehicle sale, unrelated road removal or collision override. Unknown results retain
    the mutation block: use get_depot_removal_operation, NEVER repeat commit.
    """
    import uuid
    if transport_mode() != 'headless':
        raise ToolError('Guarded depot removal requires the headless channel')
    status = await headless_client().status()
    if status['receiver'].get('depotRemovalVersion') != 1 or status.get('pending'):
        raise ToolError('Depot removal v1 receiver without pending request required; nothing submitted')
    slot = 'tf3_depot_before_' + uuid.uuid4().hex
    saved = await _call('save_game', slot=slot, overwrite=False)
    if saved.get('verified') is not True:
        raise ToolError('Backup not verified; depot removal was not submitted')
    return await _call('commit_depot_removal', preview_token=preview_token, backup_save=slot)


@mcp.tool()
async def get_depot_removal_operation(operation_id: str) -> dict:
    """Read/reconcile one depot removal from its preview token; never dispatch removal.
    Checks target disappearance, adjacent roads and vehicle preservation. Different
    session/player, partial removal or altered dependencies retain the unresolved block.
    """
    return await _call('get_depot_removal_operation', operation_id=operation_id)


@mcp.tool()
async def bulldoze(entity: int) -> dict:
    """Legacy FILE channel only; unsupported on headless. For empty road depots use
    preview_depot_removal/commit_depot_removal/get_depot_removal_operation.
    Remove a construction (depot, station group or station, or any construction id) or a street
    segment, using the game's own removal. Roadside stops can't be removed by script yet."""
    return await _call("bulldoze", _timeout=BUILD_TIMEOUT, entity=entity)


if ALLOW_EVAL:

    @mcp.tool()
    async def run_lua(code: str, engine: bool = False) -> Any:
        """Run Lua code inside the game's engine script state and return its result
        (engine userdata is converted to plain data where possible). The full modding
        API is available: api.engine, api.cmd, api.type, api.res. A bare expression is
        returned directly; otherwise use `return`. Commands sent with api.cmd.sendCommand
        take effect in the live game. engine=True runs it in the engine state instead of the GUI state
        (needed e.g. to remove or replace existing streets; there command callbacks run synchronously)."""
        return await _call("eval", _engine=engine, code=code)


@mcp.tool()
async def get_network_template(template: str) -> dict:
    """Read current native lane directions, widths, modes and style for a road template."""
    return await _call("get_network_template", template=template)


@mcp.tool()
async def list_road_structures() -> dict:
    """List native bridge, tunnel and railroad-crossing resources (v37 for crossings).
    Resource existence is not construction acceptance."""
    return await _call("list_road_structures")


@mcp.tool()
async def preview_road_graph(graph: dict, isolated_test: bool = False) -> dict:
    """Preview explicit road topology (zero-based node indices) on the current map.
    isolated_test is a legacy compatibility flag, not required. Supports endpoints, split points, intersections,
    one-way lanes, ramps and explicit bridge/tunnel resources. Splits get structural checking
    only because native removal previews can assert. v37 adds opted-in stop-object
    and structure splits, explicit crossing_resource nodes, and junction signal plans.
    Query runtime capabilities first; v40 adds crossing/tunnel-chain preservation and
    constrained turns/crosswalks. Bounded native scenarios passed; see ROAD_GRAPH.md
    and ROUNDABOUT.md for accepted cases and remaining limits.
    No frozen internals/object deletion.
    Return token is single-use for 60 seconds; commit separately, then verify directed paths."""
    return await _call("preview_road_graph", graph=graph, isolated_test=isolated_test)


@mcp.tool()
async def preview_dual_highway(centerline: list[dict], template: str, median_gap: float = 4,
                               drive_side: str = "right", isolated_test: bool = False) -> dict:
    """Create and preview two opposite one-way highway carriageways from native lane widths.
    Centerline contains explicit xyz points, 10-200 m spans. Returns four independent ports;
    connecting ramps must be explicitly designed. isolated_test is a legacy compatibility flag,
    not required. Does not build or prove vehicle access."""
    from .road_graph import paired_highway
    native = await _call("get_network_template", template=template)
    plan = paired_highway(centerline, native['resource'], native['laneConfigs'], median_gap, drive_side)
    plan['preview'] = await _call("preview_road_graph", graph=plan['graph'], isolated_test=isolated_test)
    return plan


@mcp.tool()
async def commit_road_graph(preview_token: str, backup_save: str) -> dict:
    """Submit a road graph on the current map exactly once; backup_save identifies the verified
    preconstruction save. Unknown/partial outcome stays pending: never resend. Static verified
    does not establish directed vehicle paths or long-term simulation safety."""
    return await _call("commit_road_graph", _timeout=BUILD_TIMEOUT, preview_token=preview_token, backup_save=backup_save)


@mcp.tool()
async def get_road_graph_operation(operation_id: str) -> dict:
    """Read stored graph operation result using its preview token; never resubmit."""
    return await _call("get_road_graph_operation", operation_id=operation_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
