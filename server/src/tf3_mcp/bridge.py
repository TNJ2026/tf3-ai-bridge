"""Shared path and userdata encoding helpers; the legacy file transport is removed."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

DIR_NAME = "tf3_mcp"
TF3_APP_ID = "3493540"
HEARTBEAT_STALE_SECONDS = 5.0
IDLE_REQUEST = {"idle": True}  # no "id": the mod ignores it and leaves it in place
_HEX_RE = re.compile(r'hex\s*=\s*"([0-9a-fA-F]*)"')


def _steam_path() -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        return None


def default_bridge_dir() -> Path:
    """``TF3_MCP_DIR`` if set, else ``<Steam>/userdata/<id>/3493540/local/tf3_mcp`` for the
    most recently used Steam account that has played the game."""
    explicit = os.environ.get("TF3_MCP_DIR")
    if explicit:
        return Path(os.path.expandvars(explicit)).expanduser()
    steam = _steam_path()
    if steam:
        locals_ = [p for p in (steam / "userdata").glob(f"*/{TF3_APP_ID}/local") if p.is_dir()]
        if locals_:
            newest = max(locals_, key=lambda p: p.stat().st_mtime)
            return newest / DIR_NAME
    raise RuntimeError(
        "Could not find the Transport Fever 3 userdata folder; set TF3_MCP_DIR to "
        "<Steam>/userdata/<id>/3493540/local/tf3_mcp"
    )


def encode_message(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8").hex()
    return f'function data()\nreturn {{\n\thex = "{payload}",\n}}\nend\n'


def decode_message(text: str) -> Any:
    m = _HEX_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(bytes.fromhex(m.group(1)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


class BridgeError(RuntimeError):
    """The game reported an error, or could not be reached."""


class Bridge:
    """Compatibility error for historical scripts; never sends a request."""
    def __init__(self, directory=None, **kwargs):
        self.dir = directory or default_bridge_dir()

    async def call(self, *args, **kwargs):
        raise BridgeError("Legacy file transport removed; use the no_gui MCP client")

    def heartbeat(self):
        raise BridgeError("Legacy file transport removed; use no_gui_status")
