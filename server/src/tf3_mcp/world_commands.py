"""Whitelisted native world commands with preview/backup/one-shot commit.

The catalog distinguishes executable adapters from native commands for which
the installed API cannot yet provide the required safe proposal/typed payload.
"""
from __future__ import annotations

import datetime
import json
import math
import re
import uuid


def action(native, fields, component=None, target="entity", *, debug=False, blocked=None):
    return dict(native=native, fields=fields, component=component, target=target, debug=debug, blocked=blocked)


CATALOG = {
    "industry_productivity": action("makeStockListSetModifiersCmd", {"entity":"entity", "productivity":"nonnegative"}, "INDUSTRY"),
    "industry_manual_development": action("makeIndustrySetManualDevelopmentCmd", {"entity":"entity", "manual":"bool"}, "INDUSTRY"),
    "industry_closure_time": action("makeIndustrySetDespawnTimeCmd", {"entity":"entity", "timestamp":"integer"}, "INDUSTRY"),
    "vehicle_manual_departure": action("makeVehicleSetManualDepartureCmd", {"entity":"entity", "manual":"bool"}, "TRANSPORT_VEHICLE"),
    "vehicle_depart": action("makeVehicleTryToDepartCmd", {"entity":"entity"}, "TRANSPORT_VEHICLE"),
    "vehicle_reverse": action("makeVehicleReverseCmd", {"entity":"entity"}, "TRANSPORT_VEHICLE"),
    "town_development": action("makeTownSetDevelopmentActiveCmd", {"entity":"entity", "active":"bool"}, "TOWN"),
    "town_initial_capacities": action("makeTownSetInitialLandUseCapacitiesCmd", {"entity":"entity", "capacities":"integers3"}, "TOWN"),
    "town_size": action("makeTownUpdateSizeCmd", {"entity":"entity", "factors":"numbers3", "update_buildings":"bool"}, "TOWN"),
    "town_distribution": action("makeTownCustomDistributionWeightsCmd", {"entity":"entity", "weights":"weights"}, "TOWN"),
    "building_protection": action("makeTownBuildingSetBlockedDevelopmentCmd", {"entity":"entity", "blocked":"bool"}, "TOWN_BUILDING"),
    "calendar_speed": action("makeGameSetCalendarSpeedCmd", {"millis_per_day":"positive_integer"}, target="world"),
    "game_date": action("makeGameSetDateCmd", {"year":"year", "month":"month", "day":"day"}, target="world"),
    "time_of_day": action("makeGameSetTimeOfDayCmd", {"seconds":"day_seconds"}, target="world"),
    "cloud_coverage": action("makeGameSetCloudCoverageCmd", {"coverage":"ratio"}, target="world"),
    "wind": action("makeWorldChangeWindCmd", {"entity":"entity", "x":"number", "y":"number"}, "EMISSION_GRID"),
    "entity_emissions": action("makeEntitySetEmissionsCmd", {"entity":"entity", "noise_power":"nonnegative", "pollution_power":"nonnegative", "noise_radius":"nonnegative", "pollution_radius":"nonnegative"}, "EMISSION_EMITTER"),
    "entity_name": action("makeEntitySetNameCmd", {"entity":"entity", "name":"text"}, "NAME"),
    "entity_owner": action("makeEntitySetPlayerCmd", {"entity":"entity", "player":"entity"}, "PLAYER_OWNED"),
    "entity_bulldozable": action("makeWorldSetBulldozableCmd", {"entity":"entity", "value":"bool"}),
    "stock_cargo_type": action("makeStockListSetStocksCargoTypeCmd", {"entity":"entity", "stock_ids":"ids", "cargo":"entity"}, "STOCK_LIST"),
    "stock_discard": action("makeStockListDiscardCargoCmd", {"entity":"entity", "stock_ids":"ids", "remaining_time":"nonnegative"}, "STOCK_LIST"),
    "custom_entity_create": action("makeCustomEntityCreateCmd", {"model":"resource"}, target="create"),
    "custom_entity_destroy": action("makeCustomEntityDestroyCmd", {"entity":"entity"}, "CUSTOM_STATE"),
    "custom_entity_state": action("makeCustomEntityUpdateStateCmd", {"entity":"entity", "state":"json_object"}, "CUSTOM_STATE"),
    "custom_entity_transform": action("makeCustomEntityUpdateTransformationCmd", {"entity":"entity", "columns":"matrix"}, "CUSTOM_STATE"),
    "animal_spawn": action("makeAnimalSpawnAtCmd", {"model":"resource", "x":"number", "y":"number", "look_x":"number", "look_y":"number"}, target="create"),
    "animal_state": action("makeAnimalSetStateCmd", {"entity":"entity", "movement_type":"entity", "target_elapsed":"nonnegative", "invalid_elapsed":"nonnegative", "speed":"nonnegative", "angular_speed":"number"}, "ANIMAL"),
    "add_player": action("makeGameAddPlayerCmd", {"name":"text", "r":"ratio", "g":"ratio", "b":"ratio"}, target="create"),
    "town_detect_connections": action("makeTownAutoDetectConnectionsCmd", {"towns":"ids"}, target="towns"),
    "debug_maintenance_cost": action("debug.makeMaintenanceCostUpdateCmd", {"entity":"entity", "amount":"nonnegative_integer", "reset_accumulated":"bool"}, "MAINTENANCE_COST", debug=True),
    "debug_person_happiness": action("debug.makeSimPersonSetHappiness", {"entity":"entity", "happiness":"ratio"}, "SIM_PERSON", debug=True),
    "debug_person_state": action("debug.makeSimPersonSetStateCmd", {"entity":"entity", "state":"entity"}, "SIM_PERSON", debug=True, blocked="Installed API exposes an integer but no validated person-state enum/transition contract; arbitrary states are rejected."),
    "debug_stock_amount": action("debug.makeStockSetCargoAmountCmd", {"entity":"entity", "stock_id":"entity", "amount":"nonnegative_integer", "cargo":"resource"}, "STOCK_LIST", debug=True),
    "debug_simulation_steps": action("debug.makeGamePerformSimulationStepsCmd", {"steps":"steps"}, target="world", debug=True),
    "debug_clear_logbooks": action("debug.makeClearLogbooksCmd", {"towns":"bool"}, target="world", debug=True),
    "journal_clear": action("makeJournalClearAllCmd", {}, target="world"),
    "journal_log": action("makeJournalLogEntryCmd", {"entity":"entity", "entries":"log_entries"}),
    # These native commands are inventoried, but deliberately cannot bypass the
    # repository's native collision/quote and typed-payload requirements.
    "industry_extend": action("makeCreateIndustryExtendProposalCmd", {"entity":"entity", "try_slots":"slots", "keep_slots":"slots"}, "CONSTRUCTION"),
    "town_create": action("makeTownCreateCmd", {"name":"text", "x":"number", "y":"number"}, target="create", blocked="TownInfo generation has no validated native cost/collision proposal adapter."),
    "town_destroy": action("makeTownDestroyCmd", {"entity":"entity"}, "TOWN", blocked="Deletes town streets and buildings; affected-entity/collision/removal preview adapter is required."),
    "town_develop_at": action("makeTownDevelopAtCmd", {"x":"number", "y":"number", "develop_streets":"bool", "upgrade_buildings":"bool"}, target="world", blocked="Native developer creates streets/buildings without a validated proposal preview."),
    "town_connect_industries": action("makeTownConnectWithIndustriesCmd", {"towns":"ids", "keep":"bool"}, target="towns", blocked="Automatic road generation/removal lacks a validated native quote/collision proposal adapter."),
    "world_replace_terrain": action("makeWorldReplaceTerrainCmd", {"seed":"text", "keep_assets":"bool"}, target="world", blocked="Whole-map GameMap/Terrain conversion and affected-entity preview are not validated; never use as a flatten shortcut."),
    "custom_vehicle": action("makeCustomVehicleCreateOrUpdateCmd", {"source_vehicle":"entity"}, target="world", blocked="Custom vehicle MovePathAircraft invariants and depot/flight lifecycle need a validated typed adapter."),
    "journal_book_asset": action("makeJournalBookAssetCmd", {"entity":"entity"}, blocked="Installed declaration leaves JournalEntry opaque; no validated constructor/financial semantics."),
    "debug_component_exchange": action("debug.makeComponentExchangeCmd", {"entity":"entity", "source_entity":"entity"}, "EMISSION_EMITTER", debug=True),
}

COMMANDS = {"list_world_actions": {}, "preview_world_action": {}, "commit_world_action": {}, "get_world_action_operation": {}}


def _validate_value(kind, value):
    if kind == "bool": return type(value) is bool
    if kind in {"text", "resource"}:
        if not isinstance(value, str) or not 1 <= len(value.encode('utf-8')) <= 256 or any(ord(c)<32 for c in value): return False
        if kind == "resource":
            return re.fullmatch(r"(?:[A-Za-z0-9_-]+)?::/[^\\]+",value) is not None and not any(x in {'','.','..'} for x in value.split('::/',1)[1].split('/'))
        return True
    if kind == "json_object":
        def walk(v, depth=0):
            if depth>4:return False
            if isinstance(v,dict):return len(v)<=32 and all(isinstance(k,str) and 0<len(k)<=64 and walk(x,depth+1) for k,x in v.items())
            if isinstance(v,list):return len(v)<=32 and all(walk(x,depth+1) for x in v)
            return type(v) in (bool,str) or type(v) in (int,float) and math.isfinite(v)
        return isinstance(value,dict) and walk(value) and len(json.dumps(value).encode())<=2048
    if kind in {"ids","integers3","numbers3","weights","matrix","log_entries"}:
        if not isinstance(value,list):return False
        if kind=="ids":return 1<=len(value)<=32 and all(_validate_value('entity',v) for v in value) and len(set(value))==len(value)
        if kind in {"integers3","numbers3"}:return len(value)==3 and all(_validate_value('nonnegative_integer' if kind=='integers3' else 'nonnegative',v) for v in value)
        if kind in {"weights","matrix"}:return len(value)==(3 if kind=='weights' else 4) and all(isinstance(row,list) and len(row)==4 and all(_validate_value('nonnegative' if kind=='weights' else 'number',v) for v in row) for row in value)
        return 1<=len(value)<=16 and all(isinstance(row,list) and len(row)==3 and _validate_value('text',row[0]) and _validate_value('integer',row[1]) and type(row[2]) is bool for row in value)
    if type(value) not in (int,float) or not math.isfinite(value):return False
    ranges={'entity':(0,2147483646),'integer':(-2147483647,2147483646),'number':(-1e9,1e9),'nonnegative':(0,1e9),'nonnegative_integer':(0,2147483646),'positive_integer':(1,2147483646),'ratio':(0,1),'year':(1,9999),'month':(1,12),'day':(1,31),'day_seconds':(0,86399),'steps':(1,100),'slots':(1,64)}
    low,high=ranges[kind]
    return low<=value<=high and (kind in {'number','nonnegative','ratio'} or type(value) is int)


def validate(command, args):
    if not isinstance(args,dict):raise ValueError('Expected arguments object')
    keys={'list_world_actions':set(), 'preview_world_action':{'action','parameters'}, 'commit_world_action':{'preview_token','backup_save'}, 'get_world_action_operation':{'operation_id'}}[command]
    if args.keys()!=keys:raise ValueError('Missing or unknown world action argument')
    if command=='preview_world_action':
        spec=CATALOG.get(args['action']) if isinstance(args['action'],str) else None
        p=args['parameters']
        if spec is None or not isinstance(p,dict) or p.keys()!=spec['fields'].keys():raise ValueError('Unknown action or parameters')
        for key,kind in spec['fields'].items():
            if not _validate_value(kind,p[key]):raise ValueError(f'Invalid {key}: {kind}')
        if args['action']=='game_date':datetime.date(p['year'],p['month'],p['day'])
        if args['action']=='custom_entity_transform' and [p['columns'][i][3] for i in range(4)]!=[0,0,0,1]:raise ValueError('Expected affine matrix columns')
        if args['action']=='town_distribution' and any(sum(row)<=0 for row in p['weights']):raise ValueError('Distribution rows need positive total')
    else:
        for key,value in args.items():
            if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}',value):raise ValueError('Invalid token or backup slot')
    return args


def register(mcp, call, get_client):
    @mcp.tool()
    async def list_world_actions() -> dict:
        """Read all whitelisted world command schemas, native availability and explicit blocked adapters. No writes."""
        return await call('list_world_actions')

    @mcp.tool()
    async def preview_world_action(action: str, parameters: dict) -> dict:
        """Preview a catalog action without dispatch. Requires paused game. Returns exact before/desired, risk,
        native-preview status and one-use token only when executable. Not an eval or arbitrary command proxy.
        Structural/opaque native commands without verified adapters return blocked, never a commit token.
        """
        validate('preview_world_action',dict(action=action,parameters=parameters))
        return await call('preview_world_action',action=action,parameters=parameters)

    @mcp.tool()
    async def commit_world_action(preview_token: str) -> dict:
        """Back up current paused game, consume an authorized world-action preview ONCE, then read original operation.
        Never retry unknown outcomes. Debug/destructive actions require explicit user intent, not monitoring inference.
        """
        from .no_gui import workflow_lock
        validate('commit_world_action',dict(preview_token=preview_token,backup_save='preflight'))
        client=get_client()
        with workflow_lock(client.requests.directory):
            status=await client.status()
            if status.get('pending') or status.get('receiver',{}).get('worldActionsVersion')!=1:raise ValueError('Ready worldActionsVersion=1 receiver without pending required')
            state=await client.call('get_game_state',{})
            if state.get('speedup')!=0:raise ValueError('Pause required before backup')
            slot='world_action_'+uuid.uuid4().hex
            saved=await client.call('save_game',dict(slot=slot,overwrite=False))
            if saved.get('verified') is not True:raise ValueError('Backup not verified')
            result=await client.call('commit_world_action',dict(preview_token=preview_token,backup_save=slot))
            return await client.call('get_world_action_operation',dict(operation_id=result['operation_id']))

    @mcp.tool()
    async def get_world_action_operation(operation_id: str) -> dict:
        """Independent readback of one original world action. No resubmission, no clearing unknown results."""
        return await call('get_world_action_operation',operation_id=operation_id)
