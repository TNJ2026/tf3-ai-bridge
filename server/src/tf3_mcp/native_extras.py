"""Bounded GUI controls and read-only diagnostics; no arbitrary API invocation."""
from __future__ import annotations

import math
import re

# All fields are required on the wire. Public tools supply their defaults.
SCHEMAS = {
    "get_native_extras_capabilities": {},
    "focus_game_entity": {"entity": "entity"},
    "focus_game_position": {"x": "number", "y": "number", "z": "number", "distance": "distance"},
    "follow_game_entity": {"entity": "entity", "jump": "bool"},
    "enter_vehicle_cockpit": {"vehicle": "entity"},
    "leave_vehicle_cockpit": {},
    "take_game_screenshot": {"scale": "scale"},
    "get_game_camera": {},
    "set_map_marker": {"key": "key", "x": "number", "y": "number", "z": "number", "marker_type": "text", "scaling": "scaling"},
    "remove_map_marker": {"key": "key"},
    "set_map_circle": {"key": "key", "x": "number", "y": "number", "radius": "distance", "r": "ratio", "g": "ratio", "b": "ratio", "alpha": "ratio"},
    "remove_map_circle": {"key": "key"},
    "show_vehicle_path": {"key": "key", "vehicle": "entity", "r": "ratio", "g": "ratio", "b": "ratio"},
    "remove_vehicle_path": {"key": "key"},
    "highlight_game_ui": {"target": "text", "highlighted": "bool", "style": "style", "r": "ratio", "g": "ratio", "b": "ratio"},
    "show_game_guide": {"target": "text", "tooltip": "text", "caption": "text"},
    "reset_game_guide": {},
    "show_entity_hud_icon": {"entity": "entity", "icon": "resource", "duration": "duration"},
    "sound_vehicle_horn": {"vehicle": "entity"},
    "play_game_sound": {"resource": "resource"},
    "play_game_voiceover": {"resource": "resource", "delay": "delay"},
    "stop_game_voiceover": {},
    "get_game_voiceover": {},
    "play_game_cutscene": {"resource": "resource", "resolve_language": "bool"},
    "get_game_cutscene": {},
    "get_game_performance": {"limit": "limit"},
    "get_blocked_trains": {"offset": "offset", "limit": "limit"},
    "get_line_terminal_suggestions": {"line": "entity", "allow_terminal_changes": "bool"},
    "get_destination_persons": {"destination": "entity", "offset": "offset", "limit": "limit"},
    "sample_environment": {"x": "number", "y": "number", "use_average": "bool"},
}
ENGINE_READS = {"get_blocked_trains", "get_line_terminal_suggestions", "get_destination_persons", "sample_environment"}
GUI_READS = {"get_native_extras_capabilities", "get_game_camera", "get_game_voiceover", "get_game_cutscene", "get_game_performance"}


def validate(command, arguments):
    schema = SCHEMAS[command]
    if not isinstance(arguments, dict) or arguments.keys() != schema.keys():
        raise ValueError("Missing or unexpected native extras arguments")
    for key, kind in schema.items():
        value = arguments[key]
        valid = False
        if kind == "bool":
            valid = type(value) is bool
        elif kind in {"text", "key", "resource", "style"}:
            valid = isinstance(value, str) and 0 < len(value.encode("utf-8")) <= 512 and not any(ord(c) < 32 for c in value)
            if valid and kind == "key":
                valid = re.fullmatch(r"[A-Za-z0-9_-]{1,48}", value) is not None
            if valid and kind == "style":
                valid = value in {"Circle", "Square", "Mask"}
            if valid and kind == "resource":
                valid = (re.fullmatch(r"(?:[A-Za-z0-9_-]+)?::/[^\\]+", value) is not None
                         and not any(p in {".", "..", ""} for p in value.split("::/", 1)[1].split("/")))
        else:
            bounds = {"entity": (0, 2147483646), "offset": (0, 10000000), "limit": (1, 200),
                      "scale": (1, 4), "ratio": (0, 1), "distance": (0.01, 100000),
                      "scaling": (0.01, 100), "duration": (0.1, 60), "delay": (0, 60),
                      "number": (-10000000, 10000000)}
            lo, hi = bounds[kind]
            valid = type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi
            if kind in {"entity", "offset", "limit", "scale"}:
                valid = valid and type(value) is int
        if not valid:
            raise ValueError(f"Invalid {command}.{key} ({kind})")
    return arguments


def register(mcp, call):
    """Register explicit typed tools, not an eval or arbitrary native-function proxy."""
    @mcp.tool()
    async def get_native_extras_capabilities() -> dict:
        """Read per-tool native availability for GUI controls and diagnostics. Requires nativeExtrasVersion=1."""
        return await call("get_native_extras_capabilities")

    @mcp.tool()
    async def focus_game_entity(entity: int) -> dict:
        """Move the user's game camera to an existing entity. GUI effect only."""
        return await call("focus_game_entity", entity=entity)

    @mcp.tool()
    async def focus_game_position(x: float, y: float, z: float, distance: float = 300) -> dict:
        """Focus game camera on a world position; distance in meters."""
        return await call("focus_game_position", x=x, y=y, z=z, distance=distance)

    @mcp.tool()
    async def follow_game_entity(entity: int, jump: bool = True) -> dict:
        """Follow an existing entity with the game camera."""
        return await call("follow_game_entity", entity=entity, jump=jump)

    @mcp.tool()
    async def enter_vehicle_cockpit(vehicle: int) -> dict:
        """Enter native vehicle cockpit camera; does not move or modify the vehicle."""
        return await call("enter_vehicle_cockpit", vehicle=vehicle)

    @mcp.tool()
    async def leave_vehicle_cockpit() -> dict:
        """Leave the native cockpit camera."""
        return await call("leave_vehicle_cockpit")

    @mcp.tool()
    async def take_game_screenshot(scale: int = 1) -> dict:
        """Request native screenshot (scale 1-4). Receipt does not verify a saved file or return image bytes."""
        return await call("take_game_screenshot", scale=scale)

    @mcp.tool()
    async def get_game_camera() -> dict:
        """Read camera eye/center/follow entity, with per-field availability."""
        return await call("get_game_camera")

    @mcp.tool()
    async def set_map_marker(key: str, x: float, y: float, z: float, marker_type: str, scaling: float = 1) -> dict:
        """Show a namespaced map marker. marker_type must be a native supported marker type; no guessed default."""
        return await call("set_map_marker", key=key, x=x, y=y, z=z, marker_type=marker_type, scaling=scaling)

    @mcp.tool()
    async def remove_map_marker(key: str) -> dict:
        """Remove only the bridge-namespaced marker with this key."""
        return await call("remove_map_marker", key=key)

    @mcp.tool()
    async def set_map_circle(key: str, x: float, y: float, radius: float, r: float = 0, g: float = 1, b: float = 0, alpha: float = 0.3) -> dict:
        """Draw a namespaced circle in meters. Always prohibitBuilding=false; this is not verified service coverage."""
        return await call("set_map_circle", key=key, x=x, y=y, radius=radius, r=r, g=g, b=b, alpha=alpha)

    @mcp.tool()
    async def remove_map_circle(key: str) -> dict:
        """Remove only the bridge-namespaced circle with this key."""
        return await call("remove_map_circle", key=key)

    @mcp.tool()
    async def show_vehicle_path(key: str, vehicle: int, r: float = 0, g: float = 1, b: float = 0) -> dict:
        """Ask the native GUI to visualize a vehicle move path; does not calculate or change routes."""
        return await call("show_vehicle_path", key=key, vehicle=vehicle, r=r, g=g, b=b)

    @mcp.tool()
    async def remove_vehicle_path(key: str) -> dict:
        """Remove the bridge-namespaced vehicle path visualization."""
        return await call("remove_vehicle_path", key=key)

    @mcp.tool()
    async def highlight_game_ui(target: str, highlighted: bool = True, style: str = "Circle", r: float = 0, g: float = 1, b: float = 0) -> dict:
        """Highlight a native UI ID (idOnly=true); pass highlighted=false to clear. Does not click it."""
        return await call("highlight_game_ui", target=target, highlighted=highlighted, style=style, r=r, g=g, b=b)

    @mcp.tool()
    async def show_game_guide(target: str, tooltip: str, caption: str) -> dict:
        """Try to show a native guide at a visible UI target; returns the actual boolean result."""
        return await call("show_game_guide", target=target, tooltip=tooltip, caption=caption)

    @mcp.tool()
    async def reset_game_guide() -> dict:
        """Reset the native guide system; may also dismiss a guide opened outside this bridge."""
        return await call("reset_game_guide")

    @mcp.tool()
    async def show_entity_hud_icon(entity: int, icon: str, duration: float = 5) -> dict:
        """Show a temporary native HUD icon using an explicit game resource URI, for at most 60 seconds."""
        return await call("show_entity_hud_icon", entity=entity, icon=icon, duration=duration)

    @mcp.tool()
    async def sound_vehicle_horn(vehicle: int) -> dict:
        """Play the native horn for an existing vehicle."""
        return await call("sound_vehicle_horn", vehicle=vehicle)

    @mcp.tool()
    async def play_game_sound(resource: str) -> dict:
        """Play one explicit game sound resource URI. No arbitrary OS paths."""
        return await call("play_game_sound", resource=resource)

    @mcp.tool()
    async def play_game_voiceover(resource: str, delay: float = 0) -> dict:
        """Play a native voiceover resource, with delay in seconds (0-60)."""
        return await call("play_game_voiceover", resource=resource, delay=delay)

    @mcp.tool()
    async def stop_game_voiceover() -> dict:
        """Stop current native voiceover, including voiceover not started by this bridge."""
        return await call("stop_game_voiceover")

    @mcp.tool()
    async def get_game_voiceover() -> dict:
        """Read current native voiceover state."""
        return await call("get_game_voiceover")

    @mcp.tool()
    async def play_game_cutscene(resource: str, resolve_language: bool = False) -> dict:
        """Play a trusted native cutscene resource. Takes over presentation; no completion claim from dispatch."""
        return await call("play_game_cutscene", resource=resource, resolve_language=resolve_language)

    @mcp.tool()
    async def get_game_cutscene() -> dict:
        """Read native cutscene playing flag and elapsed time."""
        return await call("get_game_cutscene")

    @mcp.tool()
    async def get_game_performance(limit: int = 60) -> dict:
        """Read up to 200 samples per native timing series. Units/order remain native; missing series are not zero."""
        return await call("get_game_performance", limit=limit)

    @mcp.tool()
    async def get_blocked_trains(offset: int = 0, limit: int = 100) -> dict:
        """Read native blocked-train pairs, paginated; does not resolve deadlocks or infer pair direction."""
        return await call("get_blocked_trains", offset=offset, limit=limit)

    @mcp.tool()
    async def get_line_terminal_suggestions(line: int, allow_terminal_changes: bool = True) -> dict:
        """Read native best assignments for the current line component; never applies the recommendation."""
        return await call("get_line_terminal_suggestions", line=line, allow_terminal_changes=allow_terminal_changes)

    @mcp.tool()
    async def get_destination_persons(destination: int, offset: int = 0, limit: int = 100) -> dict:
        """Persons with this home/work/shopping destination; not proof they are currently traveling there. Live pagination."""
        return await call("get_destination_persons", destination=destination, offset=offset, limit=limit)

    @mcp.tool()
    async def sample_environment(x: float, y: float, use_average: bool = True) -> dict:
        """Sample native noise and pollution at one coordinate. Raw engine values, not 0-100 model scores."""
        return await call("sample_environment", x=x, y=y, use_average=use_average)
