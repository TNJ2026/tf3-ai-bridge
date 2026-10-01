"""MCP server exposing Transport Fever 3 to AI agents via the tf3_mcp_bridge mod."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .bridge import Bridge, BridgeError
from .map_cache import MapCache
from .planning_app import apps, TOOL_META, card_result
from mcp.types import CallToolResult

ALLOW_EVAL = os.environ.get("TF3_MCP_ALLOW_EVAL", "") == "1"

mcp = MCPServer(
    "tf3",
    extensions=[apps],
    instructions=(
        "Controls a running Transport Fever 3 game through the TF3 MCP Bridge mod. "
        "Call bridge_status first if calls time out: the game must be running a loaded save "
        "with the mod enabled. Entity ids are integers that stay valid while the entity exists. "
        "Planning tools automatically render an MCP Apps image card. Do not automatically open HTML; "
        "the user opens it with the card link if desired."
    ),
)

_bridge: Bridge | None = None


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
    mutation = (cmd.startswith("build_") or cmd in {"upgrade_road", "commit_facility", "bulldoze", "eval"}) and not args.get("preview", False)
    try:
        return await bridge().call(cmd, args, timeout=_timeout, engine=_engine)
    except BridgeError as e:
        # surface as a tool error the agent can read and react to
        raise ToolError(str(e)) from e
    finally:
        if mutation:
            _map_cache.invalidate()


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
async def build_facility(source_entity: int, x: float, y: float, z: float, rotation: float = 0, name: str = "") -> dict:
    """Preview building a copy of an owned facility's existing native layout (warehouse, harbor,
    airport, station, depot or maintenance station). Explicit elevation z is required.
    Does not connect roads, create lines or buy vehicles. Unknown collisions block the build.
    Returns a one-use 60-second token; no game mutation occurs until commit_facility."""
    return await _call("build_facility", _engine=True, _timeout=BUILD_TIMEOUT, preview=True,
                       source_entity=source_entity, x=x, y=y, z=z, rotation=rotation, name=name)


@mcp.tool()
async def commit_facility(preview_token: str) -> dict:
    """Apply a facility preview ONCE with strict native error checking and config readback.
    Have a pre-construction save; use an isolated test save for unvalidated replacement layouts.
    Token is invalidated on use, expiry, reload or changed source. A timeout/partial result requires
    fresh map inspection, NEVER automatic retry. Verified configuration is not simulation safety."""
    return await _call("commit_facility", _engine=True, _timeout=BUILD_TIMEOUT, preview_token=preview_token)


@mcp.tool()
async def bridge_status() -> dict:
    """Check whether the game is connected: returns the mod's last heartbeat, its age,
    and the Lua environment probe (which libraries the game exposes to mods)."""
    status = bridge().heartbeat()
    status["bridgeDir"] = str(bridge().dir)
    return status


@mcp.tool()
async def ping(echo: str = "") -> dict:
    """Round-trip a request through the game. Useful to verify the command channel works."""
    return await _call("ping", echo=echo)


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
async def list_map_entities(kind: str = "CONSTRUCTION", offset: int = 0, limit: int = 100, snapshot: str | None = None) -> dict:
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
    Unreadable fields are explicitly marked; this is not a complete save export."""
    args = dict(kind=kind, offset=offset, limit=limit)
    if snapshot is not None:
        args["snapshot"] = snapshot
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
async def capture_planning_snapshot(output_dir: str, bounds: dict | None = None, spacing: float = 250) -> dict:
    """Read-only full-map or local survey without requiring existing stations; never pauses/builds.
    bounds={min:{x,y},max:{x,y}} in world metres; omit for whole map. spacing=25..2000,
    <=100000 samples. Saves terrain, available obstacle bounds, towns/industries and state as JSON.
    Returns snapshot_path for plan_global_development / plan_local_development.
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
    return dict(snapshot_path=path, scope=snapshot['scope'], state=snapshot['state'],
                terrainSamples=len(snapshot['grid']['heights']), obstacles=len(snapshot['obstacles']),
                towns=snapshot['map']['towns'], industries=snapshot['map']['industries'],
                coverage=snapshot['coverage'], consistency=snapshot['consistency'])


async def _planning_card(plan, output_dir, summary, width=1600, height=1100):
    import asyncio
    from .planning_report import export_report
    report = await asyncio.to_thread(export_report, plan, output_dir, width, height)
    return await asyncio.to_thread(card_result, plan, report, summary)


@mcp.tool(meta=TOOL_META)
async def plan_global_development(snapshot_path: str, focus_town: int, output_dir: str,
                                  neighbor_count: int = 2, supply_chains: list[dict] | None = None) -> CallToolResult:
    """Offline regional plan: focus city, nearby-city candidates, industry inventory, phases and supply balance.
    snapshot_path from capture_planning_snapshot. Distances only screen candidates, not passenger demand.
    Optional supply_chains: [{name,cargo,time_unit,evidence:'measured'|'forecast',demand,production,
    transport,handling,delivery,batch,delay,storage}]. Rates must share ONE time unit and finished-cargo
    equivalents; sum all cities sharing a chain. delay uses that unit; batch/storage are cargo quantities.
    Missing demand is UNKNOWN, not zero. Automatically exports and shows an MCP Apps planning image card; never opens HTML or builds.
    """
    import asyncio
    from .development_planner import plan_global, read_snapshot, save_json
    plan = await asyncio.to_thread(plan_global, read_snapshot(snapshot_path), focus_town, neighbor_count, supply_chains)
    path = save_json(plan, output_dir, 'global-plan')
    summary = dict(plan_path=path, neighbors=plan['neighbors'], supply=plan['supply'], phases=plan['phases'],
                warnings=plan['warnings'], buildable=None)
    return await _planning_card(plan, output_dir, summary)


@mcp.tool(meta=TOOL_META)
async def plan_local_development(snapshot_path: str, output_dir: str, sites: list[dict] | None = None,
                                 corridors: list[dict] | None = None, supply_chains: list[dict] | None = None,
                                 title: str = '局部布局规划') -> CallToolResult:
    """Offline local layout validation and road/rail corridor search; never builds or assumes ports connect.
    sites=[{name,current:{min:{x,y},max:{x,y}},reserved:{min:{x,y},max:{x,y}},basis:'estimate or native dimensions'}].
    reserved includes current footprint PLUS upgrade/access space. Detects native and proposed overlaps.
    corridors=[{name,mode:'road'|'rail',start:{x,y},end:{x,y}}]; endpoints must be outside facilities/reserves.
    Avoids building bounds and reserves; reports water, ground grade and road crossings, not designed grades.
    supply_chains schema matches plan_global_development. For rail engineering use plan_rail_connection
    with fresh real construction IDs next. Automatically exports and shows an MCP Apps planning image card; does not open HTML.
    """
    import asyncio
    from .development_planner import plan_local, read_snapshot, save_json
    plan = await asyncio.to_thread(plan_local, read_snapshot(snapshot_path), sites, corridors, supply_chains, title)
    path = save_json(plan, output_dir, 'local-plan')
    summary = dict(plan_path=path, sites=plan['sites'], routes=[{k:v for k,v in r.items() if k!='path'} for r in plan['routes']],
                supply=plan['supply'], warnings=plan['warnings'], buildable=None)
    return await _planning_card(plan, output_dir, summary)


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
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    return await _planning_card(plan, output_dir, dict(plan_path=plan_path), width, height)


@mcp.tool(meta=TOOL_META)
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
    Automatically shows the planning image card. output_dir defaults to TF3_PLANNING_DIR or exports/plans.
    """
    from .staged_planner import plan_staged
    if start_construction == end_construction:
        raise ToolError("Choose two different station constructions")
    if not 1 <= max_candidates <= 10:
        raise ToolError("max_candidates must be 1..10")
    snapshot, status = await _map_cache.refresh(start_construction, end_construction, spacing=spacing)
    import asyncio
    result = await asyncio.to_thread(plan_staged, snapshot, max_candidates)
    result["cache"] = status
    result["stats"]["bridgeRequests"] = 0 if status["hit"] else 1
    if output_dir is None:
        output_dir = os.environ.get('TF3_PLANNING_DIR', 'exports/plans')
    if output_dir is not None:
        from .development_planner import base_plan, save_json
        plan = base_plan(snapshot, '铁路连接候选方案', 'rail', [])
        plan['routes'] = [dict(c, name=f'候选 {i+1}', mode='rail', status='sampled_candidate') for i,c in enumerate(result['candidates'])]
        plan['phases'] = [dict(name='工程复核', actions=['刷新站端口、曲率、坡度与桥隧条件', '比较候选，执行原生预览'], gate='原生预览及用户建设授权')]
        plan['warnings'].append(result['limitation'])
        result['plan_path'] = save_json(plan, output_dir, 'rail-plan')
    return await _planning_card(plan, output_dir, result)


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
) -> dict:
    """Build a straight street from `start` to `end`, optionally through `via` points.
    Each point is {"node": id} for an existing street node, or {"x": .., "y": ..}; a coordinate within
    `snap_radius` metres of an existing STREET node joins that node (via points only snap with their own
    `snap` value). Optional `z` sets elevation; legs touching such points interpolate elevation, otherwise
    they follow terrain. `max_segment_length` is 10..200 metres (default 50); at most 128 points/512 segments.
    Preview returns cost, blocking entities, resolved `points`, sampled `path` and `buildable`; it never builds.
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
    return await _call("build_road", _timeout=BUILD_TIMEOUT, **args)


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
) -> dict:
    """Build a through cargo railway station with 1..4 tracks and 80/120/160/240/320 m platforms.
    Rotation is degrees counterclockwise; tracks run along local Y. Uses unelectrified simple track.
    Specialization: universal, liquid, bulk, flatbed or goods. Defaults to preview with cost/errors.
    Set preview=False to construct. Returns construction, stations, stationGroups and railPorts/roadPorts.
    External roads/railways are NOT built; verified checks station/rail ports, not train route reachability.
    """
    args: dict[str, Any] = {"x": x, "y": y, "tracks": tracks, "length": length,
        "rotation": rotation, "specialization": specialization, "preview": preview,
        "allow_collisions": allow_collisions}
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
    street node, so place it ~20 m from the street. Returns stationGroup for create_line. (Roadside
    stops on existing streets can't be built by script yet.)"""
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
async def bulldoze(entity: int) -> dict:
    """Remove a construction (depot, station group or station, or any construction id) or a street
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
