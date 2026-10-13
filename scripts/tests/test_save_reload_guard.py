import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from save_reload_guard import map_identity, save_and_reload

SLOT = "tf3_fullmap_auto_map_0123456789abcdef"


class Game:
    def __init__(self, root, behavior="write", paused=True):
        self.dir = root / "bridge"
        self.path = root / "save" / (SLOT + ".sav")
        self.path.parent.mkdir()
        self.path.write_bytes(b"old checkpoint")
        self.calls = []
        self.behavior, self.paused = behavior, paused

    def heartbeat(self):
        return {"connected": True}

    async def call(self, cmd, args=None):
        self.calls.append((cmd, args))
        if cmd == "get_game_state":
            return {"speedup": 0 if self.paused else 1}
        if "app.saveGame" in args["code"]:
            if self.behavior == "error":
                raise RuntimeError("save rejected")
            if self.behavior == "write":
                self.path.write_bytes(b"new current checkpoint")
        return {"requested": True}

    def reloads(self):
        return [a for c, a in self.calls if c == "eval" and "app.loadGame" in a["code"]]


@pytest.mark.parametrize("case", ["preflight", "save_error", "unchanged", "postflight", "unpaused", "file_changed"])
def test_failure_never_dispatches_reload(tmp_path, case):
    game = Game(tmp_path, {"save_error": "error", "unchanged": "none"}.get(case, "write"), case != "unpaused")
    count = 0

    async def validate():
        nonlocal count
        count += 1
        if case == "preflight" or case == "postflight" and count == 2:
            raise RuntimeError("identity changed")
        if case == "file_changed" and count == 2:
            game.path.write_bytes(b"unexpected replacement checkpoint")

    with pytest.raises(RuntimeError):
        asyncio.run(save_and_reload(game, SLOT, tmp_path / "attempt.json", validate, timeout=.02, poll=.001))
    assert game.reloads() == []
    assert json.loads((tmp_path / "attempt.json").read_text())["stopped"]


def test_verified_save_reloads_once_and_attempt_cannot_replay(tmp_path):
    game = Game(tmp_path)

    async def validate():
        pass

    journal = tmp_path / "attempt.json"
    result = asyncio.run(save_and_reload(game, SLOT, journal, validate, poll=.001))
    assert result["stage"] == "reload_requested" and len(game.reloads()) == 1
    with pytest.raises(FileExistsError):
        asyncio.run(save_and_reload(game, SLOT, journal, validate))
    assert len(game.reloads()) == 1


def test_backup_slot_cannot_be_loaded_as_fixed_checkpoint(tmp_path):
    game = Game(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(save_and_reload(game, "tf3_before_test", tmp_path / "attempt.json", None))
    assert game.calls == []


def test_map_enumeration_order_is_not_identity_change():
    a = {"towns": [{"id": 1}], "industries": [{"id": 4}, {"id": 3}], "width": 100}
    b = dict(a, industries=list(reversed(a["industries"])))
    assert map_identity(a) == map_identity(b)
    assert a["industries"][0]["id"] == 4


@pytest.mark.parametrize("changed", [
    [{"id": 3, "position": {"x": 2}}], [], [{"id": 4, "position": {"x": 1}}]
])
def test_real_map_changes_are_not_ignored(changed):
    a = {"towns": [], "industries": [{"id": 3, "position": {"x": 1}}]}
    assert map_identity(a) != map_identity(dict(a, industries=changed))


def test_duplicate_map_ids_are_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        map_identity({"towns": [], "industries": [{"id": 3}, {"id": 3}]})
