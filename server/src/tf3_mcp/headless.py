"""Opt-in one-use resource ingress; existing UI/log validators and replies.

Bounded mode preindexes files; demand mode creates them after startup. No GUI automation, native
userdata fallback, slot recycling, automatic reload or unknown-outcome retry.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import time
import uuid

from .ui_log import UiLogRequests

TAG = "[TNJ_HEADLESS_V1]"


@contextmanager
def public_lock(directory):
    """Same nonblocking process lock used by scripts.batch_warehouses.batch_lock."""
    path = Path(directory) / "warehouse_batch.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0"); handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic(path, data):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temp.open("wb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)


class HeadlessRequests:
    def __init__(self, directory: Path, mod: Path):
        self.directory, self.mod = Path(directory), Path(mod)
        self.log = self.directory.parent / "crash_dump/stdout.txt"
        self.ledger = self.directory / "headless_requests.json"

    def _load(self):
        if not self.ledger.exists():
            return {"version": 1, "requests": {}, "pending": None}
        value = json.loads(self.ledger.read_text(encoding="utf-8"))
        if value.get("version") != 1:
            raise ValueError("Unknown headless ledger version")
        return value

    def _save(self, value):
        atomic(self.ledger, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))

    def _archive(self, ledger):
        # Keep the hot ledger bounded, retaining immutable per-request evidence
        # on disk. Never evict an unresolved request or its dispatch intent.
        excess = len(ledger["requests"]) - 256
        if excess <= 0:
            return
        history = self.directory / "headless_history"
        history.mkdir(exist_ok=True)
        for request_id, record in list(ledger["requests"].items()):
            if excess <= 0:
                break
            if "response" not in record or ledger.get("pending") == request_id:
                continue
            destination = history / (request_id + ".json")
            data = json.dumps(record, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if destination.exists() and destination.read_bytes() != data:
                raise ValueError("Conflicting archived request; stop without overwriting evidence")
            if not destination.exists():
                atomic(destination, data)
            del ledger["requests"][request_id]
            excess -= 1

    def status(self):
        # Keep only a bounded, complete-line log tail. Native stdout timestamps
        # do not provide the request identity; the session/generation do.
        with self.log.open("rb") as f:
            f.seek(max(0, self.log.stat().st_size - 2 * 1024 * 1024))
            lines = f.read().decode("utf-8", errors="replace").splitlines(keepends=True)
        latest = None
        for line in lines:
            if not line.endswith("\n"):
                continue
            if "Game is ready" in line or "[tf3_mcp_bridge] started in gui state" in line:
                latest = None
            if TAG in line:
                latest = json.loads(line.split(TAG, 1)[1])
        if latest is None:
            raise ValueError("No live headless receiver; install and load the diagnostic mod")
        generation = latest.get("generation", "")
        if not re.fullmatch(r"[0-9a-f]{32}", generation):
            raise ValueError("Invalid receiver generation")
        demand = latest.get("mode") == "demand"
        if latest.get("mode", "bounded") not in ("bounded", "demand"):
            raise ValueError("Unknown receiver mode")
        if type(latest.get("slot")) is not int or not 1 <= latest["slot"] <= (2**53-1 if demand else 1024):
            raise ValueError("Invalid receiver slot")
        if demand and not re.fullmatch(r"s[a-zA-Z0-9_]+_[0-9]+\.lua", latest.get("filename", "")):
            raise ValueError("Invalid demand resource filename")
        age = time.time() - latest["utc"]
        if not 0 <= age <= 5:
            raise ValueError("Headless heartbeat stale; no dispatch")
        return {"receiver": latest, "ageSeconds": age,
                "pending": self._load().get("pending"), "bounded": not demand,
                "nativeCacheReclamationVerified": False}

    def send(self, command, arguments=None, *, kind="read", expected_session=None):
        with public_lock(self.directory):
            ledger = self._load()
            if ledger.get("pending"):
                raise ValueError("Previous request unresolved; read its result, never resubmit")
            self._archive(ledger)
            if len(ledger["requests"]) >= 4096:
                raise ValueError("Unresolved ledger bound reached; reconcile before new work")
            reader = UiLogRequests()
            if kind == "read":
                ticket = reader.prepare(self.log, command, arguments)
            elif kind == "build":
                ticket = reader.prepare_build(self.log, command, arguments or {})
            else:
                raise ValueError("Unsupported request kind")
            if kind == "build" and not expected_session:
                raise ValueError("Engine operations require an independently verified current session")
            # Wait for a fresh ready window rather than racing a nearly expired slot.
            deadline = time.monotonic() + 6
            while True:
                status = self.status(); row = status["receiver"]
                if row["status"] == "ready" and status["ageSeconds"] < 1.25:
                    break
                if row["status"] in ("stopped", "exhausted") or time.monotonic() >= deadline:
                    raise ValueError("No fresh unconsumed slot; nothing submitted")
                time.sleep(.05)
            if expected_session is not None and row["session"] != expected_session:
                raise ValueError("Session changed; invalidate previous IDs and previews")
            demand = row.get("mode") == "demand"
            if not demand and any(x["generation"] == row["generation"] and x["session"] != row["session"]
                   for x in ledger["requests"].values()):
                raise ValueError("Generation already used by another session; install fresh slots, never recycle")
            reader.read(ticket["id"])  # rejects reload/log replacement during window selection
            path = self.mod / "headless" / row["generation"] / (row['filename'] if demand else f'{row["slot"]}.lua')
            if (demand and path.exists()) or (not demand and path.read_bytes() != b'return ""\n'):
                raise ValueError("Slot is not empty; never overwrite a request")
            if any(x["generation"] == row["generation"] and x["session"] == row["session"] and x["slot"] == row["slot"]
                   for x in ledger["requests"].values()):
                raise ValueError("Slot already reserved in durable ledger")
            key = row['generation'] + '|' + row['session']
            high_water = ledger.setdefault('highWater', {})
            if row['slot'] <= high_water.get(key, 0):
                raise ValueError("Slot already consumed/reserved; no replay after archival")
            envelope = dict(session=row["session"], generation=row["generation"],
                            slot=row["slot"], expires=row["due"] + (20 if demand else 2),
                            kind=kind, input=ticket["input"])
            encoded = json.dumps(envelope, separators=(",", ":"), ensure_ascii=True)
            # Lua decimal byte escapes avoid executing interpolation/long-bracket data.
            payload = ('return "' + ''.join('\\%03d' % c for c in encoded.encode('utf-8')) + '"\n').encode('ascii')
            _, inode, offset, cmd, anchor, _ = reader.pending[ticket["id"]]
            record = dict(envelope, id=ticket["id"], command=cmd, inode=inode,
                          offset=offset, anchor=anchor.hex(), created=time.time(), status="intent")
            ledger["requests"][ticket["id"]] = record
            ledger["pending"] = ticket["id"]
            high_water[key] = row['slot']
            self._save(ledger)  # fsync intent BEFORE publishing, even on later failure
            atomic(path, payload)
            record["status"] = "published"
            self._save(ledger)
            return {"id": ticket["id"], "status": "published", "session": row["session"],
                    "slot": row["slot"], "retryAllowed": False}

    def read(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r'[0-9a-f]{32}', request_id):
            raise ValueError("Invalid request ID")
        with public_lock(self.directory):
            ledger = self._load()
            row = ledger["requests"].get(request_id)
            if row is None:
                archived = self.directory / 'headless_history' / (request_id + '.json')
                if not archived.is_file():
                    raise ValueError("Unknown durable request ID")
                row = json.loads(archived.read_text(encoding='utf-8'))
                if row.get('id') != request_id or row.get('response', {}).get('id') != request_id:
                    raise ValueError("Archived response identity mismatch")
            if "response" in row:
                return {"status": "received", "response": row["response"]}
            reader = UiLogRequests()
            reader.pending[request_id] = (self.log, row["inode"], row["offset"], row["command"],
                bytes.fromhex(row["anchor"]), time.monotonic() - max(0, time.time() - row["created"]))
            result = reader.read(request_id)
            if result["status"] == "received":
                row["response"] = result["response"]
                row["status"] = "received"
                # Engine maintains its own unresolved-commit latch independently.
                if ledger["pending"] == request_id:
                    ledger["pending"] = None
                self._archive(ledger)
                self._save(ledger)
            return result
