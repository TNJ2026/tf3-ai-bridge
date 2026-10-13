"""Transport to the tf3_mcp_bridge game script through the game's userdata files.

Game scripts have neither sockets nor the io library. The only file access they get is
``app.saveUserdata`` / ``app.loadUserdata`` in the GUI state, which store Lua tables as
``<userdata>/local/<dir>/<name>.lua``. The mod polls ``request.lua`` in the ``tf3_mcp``
directory and answers in ``response.lua``; it also writes ``heartbeat.lua`` about once
per second. Each file holds ``{ hex = "<hex-encoded UTF-8 JSON>" }`` so neither side
depends on how the game escapes strings.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import uuid
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
    def __init__(self, directory: Path | None = None, timeout: float = 10.0, poll: float = 0.05):
        self.dir = directory or default_bridge_dir()
        self.timeout = timeout
        self.poll = poll
        self._lock = asyncio.Lock()
        self.dir.mkdir(parents=True, exist_ok=True)

    @property
    def request_path(self) -> Path:
        return self.dir / "request.lua"

    @property
    def response_path(self) -> Path:
        return self.dir / "response.lua"

    @property
    def heartbeat_path(self) -> Path:
        return self.dir / "heartbeat.lua"

    def heartbeat(self) -> dict[str, Any]:
        """Return the last heartbeat plus its age, or a description of why there is none."""
        try:
            stat = self.heartbeat_path.stat()
        except FileNotFoundError:
            return {
                "connected": False,
                "reason": f"no heartbeat at {self.heartbeat_path}; is the game running a loaded save "
                "with the TF3 MCP Bridge mod enabled?",
            }
        age = time.time() - stat.st_mtime
        return {
            "connected": age < HEARTBEAT_STALE_SECONDS,
            "heartbeatAgeSeconds": round(age, 2),
            "heartbeat": _read_message(self.heartbeat_path),
        }

    async def call(
        self, cmd: str, args: dict[str, Any] | None = None, timeout: float | None = None, engine: bool = False
    ) -> Any:
        """Send a command to the mod. ``engine=True`` asks the mod to run it in the engine state
        instead of the GUI state (build commands always run there)."""
        async with self._lock:
            # All local clients share one request file, including the map-cache poller.
            lock_file = open(self.dir / "client.lock", "a+b")
            acquired = False
            deadline = time.monotonic() + (timeout or self.timeout)
            try:
                lock_file.seek(0)
                if os.fstat(lock_file.fileno()).st_size == 0:
                    lock_file.write(b"0"); lock_file.flush()
                while not acquired:
                    try:
                        lock_file.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise BridgeError("timed out waiting for another bridge client")
                        await asyncio.sleep(self.poll)
                return await self._call(cmd, args or {}, timeout or self.timeout, engine)
            finally:
                if acquired:
                    lock_file.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()

    async def _call(self, cmd: str, args: dict[str, Any], timeout: float, engine: bool) -> Any:
        req_id = uuid.uuid4().hex
        request: dict[str, Any] = {"id": req_id, "cmd": cmd, "args": args}
        if engine:
            request["engine"] = True
        _write_atomic(self.request_path, encode_message(request))
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                resp = _read_message(self.response_path)
                if isinstance(resp, dict) and resp.get("id") == req_id:
                    if resp.get("ok"):
                        return resp.get("result")
                    raise BridgeError(str(resp.get("error")))
                await asyncio.sleep(self.poll)
        finally:
            # Leave an id-less placeholder instead of deleting: loading a missing userdata
            # file makes the engine log an error on every poll.
            _write_atomic(self.request_path, encode_message(IDLE_REQUEST))
        hb = self.heartbeat()
        hint = "" if hb.get("connected") else f" ({hb.get('reason') or 'heartbeat is stale'})"
        raise BridgeError(f"timed out after {timeout:.0f}s waiting for the game to answer '{cmd}'{hint}")


def _read_message(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return None
    # None when caught mid-write; the caller polls again
    return decode_message(text)


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".srv.tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            # the game may be reading the file right now
            time.sleep(0.01 * (attempt + 1))
    os.replace(tmp, path)

