"""Experimental UI requests; never dispatches or retries game actions."""
from __future__ import annotations

import json
import math
import re
import uuid
import time
from pathlib import Path

SCHEMAS = {
    "get_game_state": {}, "get_finances": {}, "get_map_info": {},
    "list_towns": {"limit": "limit"},
    **{name: {"limit": "limit", "mine_only": "bool"} for name in
       ("list_lines", "list_vehicles", "list_stations", "list_depots")},
    "list_vehicle_models": {"limit": "limit", "year": "year", "carrier": "carrier",
                            "include_unavailable": "bool"},
}
ALLOWED = set(SCHEMAS)


def validate_save_arguments(command: str, arguments: dict | None) -> dict:
    if command != 'save_game' or not isinstance(arguments, dict):
        raise ValueError('Expected save_game arguments')
    if not {'slot'} <= arguments.keys() <= {'slot', 'overwrite'}:
        raise ValueError('Expected slot and optional overwrite only')
    slot = arguments['slot']
    if (not isinstance(slot, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', slot)
            or re.fullmatch(r'(?i:con|prn|aux|nul|com[0-9]|lpt[0-9])', slot)):
        raise ValueError('Invalid save slot; use 1-80 ASCII letters, digits, underscores or hyphens')
    if type(arguments.get('overwrite', False)) is not bool:
        raise ValueError('overwrite must be a boolean')
    return dict(arguments)


def validate_arguments(command: str, arguments: dict | None) -> dict:
    if command not in ALLOWED:
        raise ValueError("Supported read-only commands: " + ", ".join(sorted(ALLOWED)))
    arguments = {} if arguments is None else arguments
    if not isinstance(arguments, dict):
        raise ValueError("Arguments must be an object")
    for key, value in arguments.items():
        kind = SCHEMAS[command].get(key)
        valid = ((kind == "bool" and type(value) is bool)
                 or (kind in ("limit", "year") and type(value) is int
                     and 1 <= value <= (500 if kind == "limit" else 9999))
                 or (kind == "carrier" and isinstance(value, str)
                     and value in {"ROAD", "RAIL", "TRAM", "WATER", "AIR"}))
        if not valid:
            raise ValueError(f"Invalid or unsupported argument: {key}")
    return dict(arguments)
BUILD_SCHEMAS = {
    "get_town_population": {"town":"entity"},
    "get_town_building_stats": {"ids":"entity_ids"},
    "get_component_collection": {"id":"entity", "component":"text", "field":"text", "offset":"offset", "limit":"page_limit"},
    "begin_snapshot": {"snapshot_kind":"snapshot_kind", "bounds":"bounds", "spacing":"snapshot_spacing", "start_construction":"entity", "end_construction":"entity", "whole_map":"bool"},
    "read_snapshot_page": {"snapshot":"token", "offset":"byte_offset"},
    "release_snapshot": {"snapshot":"token"},
    "preview_line_edit": {"line":"entity", "stops":"line_edits"},

    "set_game_speed": {"speed":"game_speed", "expected_speed":"game_speed"},
    "preview_headquarters_access": {"town":"entity", "road":"entity", "x":"number", "y":"number", "z":"number", "rotation":"number"},
    "preview_line_terminal": {"line":"entity", "stop_index":"stop_index", "station_index":"stop_index", "terminal":"terminal_index"},
    "preview_subvention": {"uid":"entity"}, "commit_subvention": {"preview_token":"token"}, "get_subvention_operation": {"operation_id":"token"},
    "get_facility_layout": {"entity":"entity", "offset":"offset", "limit":"page_limit"},
    "get_facility_inventory": {"entity":"entity"},
    "preview_test_removal": {"entity":"entity"}, "commit_test_removal": {"preview_token":"token"},
    "get_validation_state": {},
    "preview_flatten_terrain": {"bounds":"bounds", "target_height":"number", "max_height_change":"number", "max_edge_grade":"number", "transition_width":"number"},
    "commit_flatten_terrain": {"preview_token":"token", "backup_save":"save_slot"}, "get_terrain_operation": {"operation_id":"token"},
    "get_stock_activity": {"stock_list":"entity", "cargo":"entity"}, "get_town_deliveries": {"town":"entity"},
    "preview_road_upgrade": {"edge":"entity", "street_type":"text"},
    "preview_street_stop": {"edge":"entity", "param":"stop_param", "side":"stop_side", "two_sided":"bool"},
    "commit_edge_edit": {"preview_token":"token"},
    "preview_facility_module": {"entity":"entity", "slot":"entity", "resource":"text"},
    "preview_facility_parameter": {"entity":"entity", "key":"text", "value":"number"},
    "build_headquarters": {"town":"entity", "x":"number", "y":"number", "z":"number", "rotation":"number"},
    "preview_industry": {"resource":"text", "x":"number", "y":"number", "rotation":"number", "on_water":"bool", "seed":"text"},
    "commit_industry": {"preview_token":"token"}, "get_industry_operation": {"operation_id":"token"},
    "preview_town_cargo_needs": {"town":"entity", "residential":"cargo_ids", "commercial":"cargo_ids", "industrial":"cargo_ids", "update_buildings":"bool"},
    "commit_town_cargo_needs": {"preview_token":"token"}, "get_town_cargo_operation": {"operation_id":"token"},
    "preview_prospection": {"town":"entity", "resource":"text"}, "commit_prospection": {"preview_token":"token"}, "get_prospection_operation": {"operation_id":"token"},
    "preview_loan": {"action":"loan_action", "offer_type":"text", "loan_id":"entity"},
    "commit_loan": {"preview_token":"token"}, "get_loan_operation": {"operation_id":"token"},
    "list_network_templates": {"search":"text", "offset":"offset", "limit":"page_limit"},
    "get_network_template": {"template":"text"},
    "list_road_structures": {},
    "preview_road_graph": {"graph":"road_graph", "isolated_test":"bool"},
    "commit_road_graph": {"preview_token":"token", "backup_save":"save_slot"},
    "get_road_graph_operation": {"operation_id":"token"},
    "preview_network": {"start":"endpoint", "end":"endpoint", "via":"via_points", "template":"text", "reset_empty_rail_ports":"bool", "reset_empty_road_ports":"bool", "connect_road_junctions":"bool"},
    "commit_network": {"preview_token":"token"},
    "list_multiple_units": {"offset":"offset", "limit":"page_limit"},
    "preview_multiple_unit": {"depot":"entity", "resource":"text"},
    "get_vehicle_cargo": {"vehicle":"entity", "cargo":"entity", "include_entities":"bool", "offset":"offset", "limit":"page_limit"},
    "get_sim_entity": {"id":"entity"},
    "get_stop_cargo": {"line":"entity", "stop_index":"stop_index", "cargo":"entity"},
    "get_stock_cargo": {"stock_list":"entity", "cargo":"entity", "stock_quality":"bool", "diagnostic":"bool"},
    "preview_consist": {"depot":"entity", "models":"model_ids"},
    "commit_consist": {"preview_token":"token"},
    "preview_depot": {"x":"number", "y":"number", "z":"number", "rotation":"number", "carrier":"depot_carrier", "frontage_node":"entity"},
    "preview_station": {"x":"number", "y":"number", "z":"number", "rotation":"number", "cargo":"bool", "size":"station_size", "frontage_node":"entity"},
    "preview_rail_station": {"x":"number", "y":"number", "rotation":"number", "tracks":"tracks", "length":"rail_length", "specialization":"specialization", "cargo":"bool"},
    "commit_structure": {"preview_token":"token"},
    "delete_line": {"line": "entity"},
    "sell_vehicles": {"vehicles": "one_entity"},
    "list_cargo_types": {},
    "preview_line_stop": {"line":"entity", "stop_index":"stop_index", "loads":"cargo_ids", "max_load":"ratio", "force_unload":"bool", "extra_wait":"wait"},
    "commit_line_stop": {"preview_token":"token"},
    "get_terrain": {"x":"number", "y":"number"},
    "find_nearby": {"x":"number", "y":"number", "radius":"radius", "limit":"page_limit"},
    "list_facility_resources": {"kind":"text", "search":"text", "offset":"offset", "limit":"page_limit"},
    "list_industry_resources": {},
    "list_prospections": {}, "get_prospections": {},
    "get_loans": {}, "get_subventions": {"assess":"bool"},
    "get_town_cargo_needs": {"town":"entity"},
    "get_terrain_operation_capabilities": {},
    "list_map_entities": {"kind":"text", "offset":"offset", "limit":"page_limit", "snapshot":"token", "ids_only":"bool"},
    "release_map_snapshot": {"snapshot":"token"},
    "get_terrain_grid": {"x":"number", "y":"number", "spacing":"spacing", "columns":"page_limit", "rows":"page_limit", "offset":"offset", "limit":"page_limit", "mode":"terrain_mode"},
    "get_map_data": {"layer":"text", "offset":"offset", "limit":"page_limit"},
    "get_terrain_tile": {"tile_x":"signed_integer", "tile_y":"signed_integer"},
    "create_line": {"station_groups": "groups", "name": "line_name"},
    "buy_vehicles": {"depot": "entity", "model": "text", "count": "one"},
    "assign_vehicles": {"vehicles": "one_entity", "line": "entity", "stop_index": "stop_index"},
    "set_vehicle_stopped": {"vehicle": "entity", "stopped": "bool"},
    "send_to_depot": {"vehicle": "entity"},
    "build_helipad": {"x": "number", "y": "number", "z": "number", "rotation": "number"},
    "build_heliport": {"x": "number", "y": "number", "z": "number", "rotation": "number"},
    "build_airfield": {"x": "number", "y": "number", "z": "number", "rotation": "number"},
    "preview_road": {"start": "endpoint", "end": "endpoint", "street_type": "text"},
    "commit_road": {"preview_token": "token"},
    "reconcile_road_rejection": {"request_id": "request_id"},
    "reconcile_network_rejection": {"request_id": "request_id"},
    "reconcile_town_cargo_rejection": {"request_id": "request_id"},
    "reconcile_depot_rejection": {"request_id": "request_id"},
    "get_entity": {"id": "entity", "components":"component_names"},
    "get_vehicle_motion": {"vehicle": "entity", "resolve_native_path": "bool"},
    "list_street_types": {"filter": "text"},
    "survey_build_site": {"x": "number", "y": "number"},
    "list_facilities": {},
    "build_warehouse": {"x": "number", "y": "number", "z": "number", "rotation": "number", "module_count": "modules"},
    "build_facility": {"source_entity": "entity", "x": "number", "y": "number", "z": "number", "rotation": "number"},
    "commit_facility": {"preview_token": "token"},
    "get_facility_config": {"entity": "entity", "offset": "offset", "limit": "page_limit"},
    "get_facility_access": {"entity": "entity", "person_graph": "bool", "person_geometry": "bool"},
    "check_road_junction_path": {"node":"entity", "from_edge":"entity", "to_edge":"entity", "mode":"text"},
    "check_network_junction_path": {"node":"entity", "from_edge":"entity", "to_edge":"entity", "mode":"text"},
}


def validate_build_arguments(command, arguments):
    if command not in BUILD_SCHEMAS or not isinstance(arguments, dict):
        raise ValueError("Unsupported UI construction command or arguments")
    schema = BUILD_SCHEMAS[command]
    required = ({"x", "y", "z"} if command.startswith("build_") else set(schema))
    if command == "preview_rail_station":
        required.discard("cargo")
    if command == "preview_network":
        required.discard("via")
        required.discard("reset_empty_rail_ports")
        required.discard("reset_empty_road_ports")
        required.discard("connect_road_junctions")
    if command == "list_street_types":
        required = set()
    if command == "get_vehicle_motion":
        required.discard("resolve_native_path")
    if command == "get_vehicle_cargo":
        required = {"vehicle", "cargo"}
        if ("offset" in arguments or "limit" in arguments) and arguments.get("include_entities") is not True:
            raise ValueError("Entity pagination requires include_entities=true")
    optional_required = {'get_entity':{'id'}, 'begin_snapshot':{'snapshot_kind'}, 'get_facility_config':{'entity'}, 'get_facility_access':{'entity'}, 'get_stock_cargo':{'stock_list','cargo'}, 'preview_headquarters_access':{'town','road','x','y','z'}, 'get_facility_layout':{'entity'}, 'preview_flatten_terrain':{'bounds','target_height'}, 'preview_industry':{'resource','x','y'}, 'preview_town_cargo_needs':{'town'}, 'preview_loan':{'action'}, 'list_network_templates':set(), 'list_multiple_units':set(), 'list_facility_resources':set(), 'list_map_entities':set(),
                         'get_terrain_grid':set(), 'get_map_data':set(), 'get_subventions':set()}
    required = optional_required.get(command, required)
    if command in ('preview_depot', 'preview_station'):
        required.discard('frontage_node')
        required.discard('z')
        if 'z' in arguments and ('frontage_node' not in arguments or
                                 command == 'preview_depot' and arguments.get('carrier') not in ('ROAD', 'TRAM')):
            raise ValueError('Explicit height requires road/tram frontage')
    if command == "build_headquarters":
        required.add("town")
    if command == "build_facility":
        required.add("source_entity")
    if not required <= arguments.keys():
        raise ValueError("Missing required construction arguments")
    for key, value in arguments.items():
        kind = schema.get(key)
        from .channel_schemas import component_names, line_edits
        from .road_graph import road_graph
        valid = ((kind == 'entity_ids' and isinstance(value,list) and 1<=len(value)<=16 and all(type(v) is int and 0<=v<2147483647 for v in value) and len(set(value))==len(value))
                 or (kind == 'component_names' and component_names(value))
                 or (kind == 'line_edits' and line_edits(value))
                 or (kind == 'road_graph' and road_graph(value))
                 or (kind == 'snapshot_kind' and value in ('planning','route'))
                 or (kind == 'snapshot_spacing' and type(value) in (int,float) and math.isfinite(value) and 25<=value<=2000)
                 or (kind == 'byte_offset' and type(value) is int and 0<=value<=8388608)
                 or (kind == "game_speed" and type(value) is int and value in {0,1,2,4})
                 or (kind == "terminal_index" and type(value) is int and 0<=value<=63)
                 or (kind == "terrain_mode" and isinstance(value, str) and value in {"surface", "base"})
                 or (kind == "bounds" and valid_terrain_bounds(value))
                 or (kind == "save_slot" and isinstance(value,str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}",value) is not None)
                 or (kind == "loan_action" and isinstance(value,str) and value in {"borrow","repay"})
                 or (kind == "stop_side" and isinstance(value,str) and value in {"left","right"})
                 or (kind == "stop_param" and type(value) in (int,float) and .15<=value<=.85)
                 or (kind == "via_points" and isinstance(value,list) and len(value)<=3
                     and all(valid_road_endpoint(v) and 'node' not in v for v in value))
                 or (kind == "number" and type(value) in (int, float) and math.isfinite(value))
                 or (kind=='depot_carrier' and isinstance(value,str) and value in {'ROAD','TRAM','RAIL','WATER'})
                 or (kind=='specialization' and isinstance(value,str) and value in {'universal','liquid','bulk','flatbed','goods'})
                 or (kind=='station_size' and type(value) is int and 1<=value<=3)
                 or (kind=='tracks' and type(value) is int and 1<=value<=4)
                 or (kind=='rail_length' and type(value) is int and value in {80,120,160,240,320})
                 or (kind == "cargo_ids" and isinstance(value,list) and len(value)<=8
                     and all(type(v) is int and 0<=v<=255 for v in value) and len(set(value))==len(value))
                 or (kind == "ratio" and type(value) in (int,float) and math.isfinite(value) and 0<=value<=1)
                 or (kind in ('offset','wait','signed_integer','page_limit') and type(value) is int
                     and {'offset':(0,1000000),'wait':(0,600),'signed_integer':(-100000,100000),'page_limit':(1,100)}[kind][0]<=value
                     <={'offset':(0,1000000),'wait':(0,600),'signed_integer':(-100000,100000),'page_limit':(1,100)}[kind][1])
                 or (kind in ('spacing','radius') and type(value) in (int,float) and math.isfinite(value) and 1<=value<=1000)
                 or (kind == "model_ids" and isinstance(value,list) and 2<=len(value)<=8
                     and all(type(v) is int and 0<=v<2147483647 for v in value))
                 or (kind == "one" and type(value) is int and value == 1)
                 or (kind == "one_entity" and isinstance(value, list) and len(value) == 1
                     and type(value[0]) is int and 0 <= value[0] < 2147483647)
                 or (kind == "stop_index" and type(value) is int and 0 <= value <= 7)
                 or (kind == "bool" and type(value) is bool)
                 or (kind == "groups" and isinstance(value, list) and 2 <= len(value) <= 8
                     and all(type(v) is int and 0 <= v < 2147483647 for v in value))
                 or (kind == "line_name" and isinstance(value, str) and 1 <= len(value.encode('utf-8')) <= 80)
                 or (kind == "entity" and type(value) is int and 0 <= value < 2147483647)
                 or (kind == "modules" and type(value) is int and value in (1, 4))
                 or (kind == "text" and isinstance(value, str) and 1 <= len(value) <= 160)
                 or (kind == "endpoint" and valid_road_endpoint(value))
                 or (kind == "request_id" and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None)
                 or (kind == "token" and isinstance(value, str) and 1 <= len(value) <= 128))
        if not valid:
            raise ValueError("Invalid construction argument: " + key)
    return dict(arguments)


def valid_terrain_bounds(value):
    if not isinstance(value,dict) or set(value)!={'min','max'}:
        return False
    if not all(isinstance(p,dict) and set(p)=={'x','y'} and
               all(type(v) in (int,float) and math.isfinite(v) for v in p.values())
               for p in value.values()):
        return False
    return value['min']['x']<value['max']['x'] and value['min']['y']<value['max']['y']


def valid_road_endpoint(value):
    if not isinstance(value, dict):
        return False
    if set(value) == {"node"}:
        return type(value["node"]) is int and 0 <= value["node"] < 2147483647
    return ({"x", "y"} <= value.keys() <= {"x", "y", "z"}
            and all(type(v) in (int, float) and math.isfinite(v) for v in value.values()))


FRAME = re.compile(r"\[TNJ_UI_READ_V1\] id=([0-9a-f]{32}) part=(\d+) total=(\d+) hex=([0-9a-f]+)")


class UiLogRequests:
    def __init__(self, clock=time.monotonic):
        self.pending = {}
        self.clock = clock

    def prepare(self, path: Path, command: str, arguments: dict | None = None) -> dict:
        arguments = validate_arguments(command, arguments)
        return self._prepare(path, command, arguments)

    def prepare_build(self, path: Path, command: str, arguments: dict) -> dict:
        return self._prepare(path, command, validate_build_arguments(command, arguments))

    def prepare_save(self, path: Path, command: str, arguments: dict) -> dict:
        ticket = self._prepare(path, command, validate_save_arguments(command, arguments))
        ticket['instruction'] = 'Headless save only; no panel dispatch. Read the original ID until file verification completes.'
        return ticket

    def _prepare(self, path, command, arguments):
        if len(self.pending) >= 256:
            raise ValueError("Session request limit reached")
        stat = path.stat()
        with path.open("rb") as f:
            f.seek(max(0, stat.st_size - 256))
            anchor = f.read(stat.st_size - f.tell())
        request_id = uuid.uuid4().hex
        suffix = " " + json.dumps(arguments, separators=(",", ":"), sort_keys=True) if arguments else ""
        if len(f"{request_id} {command}{suffix}".encode("utf-8")) > (8192 if command in ("preview_line_edit", "preview_road_graph") else 512):
            raise ValueError("UI request exceeds command byte limit")
        self.pending[request_id] = (path, stat.st_ino, stat.st_size, command, anchor, self.clock())
        return {"id": request_id, "input": f"{request_id} {command}{suffix}",
                "status": "prepared_not_sent", "instruction": "Enter input in AI Bridge query and click Send once; then read this ID. No automatic UI dispatch."}

    def read(self, request_id: str) -> dict:
        if request_id not in self.pending:
            raise ValueError("Unknown request ID; do not resubmit an unknown outcome")
        path, inode, offset, command, anchor, created = self.pending[request_id]
        stat = path.stat()
        if stat.st_ino != inode or stat.st_size < offset:
            raise ValueError("Log rotated or truncated; request outcome unknown")
        if stat.st_size - offset > 16 * 1024 * 1024:
            raise ValueError("Log window exceeded; inspect outcome manually")
        with path.open("rb") as f:
            f.seek(offset - len(anchor))
            if f.read(len(anchor)) != anchor:
                raise ValueError("Log rewritten; request outcome unknown")
            f.seek(offset)
            text = f.read(16 * 1024 * 1024).decode("utf-8", errors="replace")
        if any("Game is ready" in line or "[tf3_mcp_bridge] started in gui state" in line
               for line in text.splitlines()):
            raise ValueError("Game reloaded; old request outcome requires reconciliation, do not replay")
        parts, expected = {}, None
        # Ignore unfinished last lines: the native logger may still be writing.
        for line in text.splitlines(keepends=True):
            if not line.endswith("\n"):
                continue
            match = FRAME.search(line)
            if not match or match[1] != request_id:
                continue
            part, total = int(match[2]), int(match[3])
            if not 1 <= part <= total <= 88 or len(match[4]) > 1500:
                raise ValueError("Invalid response framing")
            if expected not in (None, total) or part in parts:
                raise ValueError("Duplicate or inconsistent response; inspect manually")
            expected, parts[part] = total, match[4]
        if expected is None or len(parts) != expected:
            elapsed = max(0, self.clock() - created)
            return {"id": request_id, "status": "timeout_unknown" if elapsed >= 60 else "pending",
                    "elapsedSeconds": round(elapsed, 2), "retryAllowed": False,
                    "receivedParts": len(parts), "totalParts": expected}
        result = json.loads(bytes.fromhex("".join(parts[i] for i in range(1, expected + 1))).decode("utf-8"))
        if not isinstance(result, dict) or result.get("id") != request_id or result.get("cmd") != command or not isinstance(result.get("ok"), bool):
            raise ValueError("Response identity mismatch")
        return {"status": "received", "response": result}
