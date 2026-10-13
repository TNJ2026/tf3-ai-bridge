"""Offline failure-path checks; never connect to the game."""
import importlib.util
import asyncio
import functools
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("batch_warehouses", Path(__file__).parents[1] / "batch_warehouses.py")
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


def async_test(function):
    @functools.wraps(function)
    def run(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))
    return run


def config():
    modules = {str(10 * (250000 * (y + 250) + x + 250)): {"name": batch.MODULE, "variant": 0}
               for x, y in ((0, 3), (4, 3), (0, 7), (4, 7))}
    return {"entity": 10, "params": {"modules": modules}, "position": {"x": 0, "y": 0},
            "transform": [{"x": 1, "y": 0}], "cloneable": True}


def plan():
    return {"warehouses": [{"warehouseId": "W1", "name": "test", "position": {"x": 0, "y": 0},
                            "rotation": 0, "initialCapacity": 2000, "initialModules": 4,
                            "moduleResource": batch.MODULE, "cargoIds": [13],
                            "reserved": {"min": {"x": -60, "y": -40}, "max": {"x": 132, "y": 152}}}]}


class FakeRunner(batch.Runner):
    def __init__(self, output, action="build", failure=None):
        super().__init__(None, plan(), output, action)
        self.calls = []
        self.failure = failure
        self.constructed = False

    async def session(self):
        self.previous_state = {"player": 1}

    async def source(self):
        if self.failure == "template":
            raise batch.StopBatch("missing template")
        return config()

    async def existing(self, task):
        return config() if self.constructed else None

    async def audit(self, task, value):
        return {"staticVerified": True, "operationalAccepted": False}

    async def checkpoint(self, phase):
        self.calls.append(("save", phase))

    async def call(self, name, args=None, engine=True):
        self.calls.append((name, args))
        if name == "get_terrain":
            return {"valid": True, "water": False, "height": 1}
        if name == "build_warehouse":
            if self.failure == "template":
                raise batch.StopBatch("native template unavailable")
            return {"preview": True, "preview_token": "fresh", "check": {"ok": True, "collisions": []}}
        if name == "commit_facility":
            # Even an apparently failed response may have changed the map.
            self.constructed = True
            if self.failure == "timeout":
                raise TimeoutError("unknown outcome")
            if self.failure == "partial":
                return {"built": True, "verified": False, "entity": 10}
            return {"built": True, "verified": True, "entity": 10}
        raise AssertionError(name)


def test_layout_rejects_four_modules_with_wrong_geometry():
    value = config()
    assert batch.module_layout(value)
    modules = value["params"]["modules"]
    key = next(iter(modules))
    modules[str(int(key) + 80)] = modules.pop(key)
    assert not batch.module_layout(value)


@pytest.mark.parametrize("field,value", [("critical", True), ("structural_only", True),
                                         ("collisions", [{}]), ("collision_data_unavailable", True)])
def test_unsafe_preview_cannot_commit(field, value):
    preview = {"preview": True, "preview_token": "token", "check": {"ok": True, "collisions": []}}
    preview["check"][field] = value
    assert not batch.preview_ok(preview)


@async_test
async def test_missing_native_template_does_not_build(tmp_path):
    runner = FakeRunner(tmp_path, "preview", failure="template")
    with pytest.raises(batch.StopBatch):
        await runner.run()
    assert [name for name, _ in runner.calls] == ["get_terrain", "build_warehouse"]


@pytest.mark.parametrize("failure", ["timeout", "partial"])
@async_test
async def test_unknown_commit_is_never_replayed(tmp_path, failure):
    runner = FakeRunner(tmp_path, failure=failure)
    with pytest.raises((TimeoutError, batch.StopBatch)):
        await runner.run()
    assert runner.ledger["items"]["W1"]["status"] == "needs_reconciliation"
    restarted = FakeRunner(tmp_path)
    with pytest.raises(batch.StopBatch):
        await restarted.run()
    assert restarted.calls == [('save', 'before')]  # No global history gate, still no replay.
    # Read-only verification reconciles an actually built warehouse.
    verify = FakeRunner(tmp_path, "verify")
    verify.constructed = True
    await verify.run()
    assert verify.ledger["items"]["W1"]["commitAttempts"] == 1
    assert verify.ledger["items"]["W1"]["status"] == "static_verified"
    assert not verify.ledger["operationalAccepted"]


@async_test
async def test_success_checkpoints_and_duplicate_skip(tmp_path):
    runner = FakeRunner(tmp_path)
    await runner.run()
    names = [name for name, _ in runner.calls]
    assert names == ["save", "get_terrain", "build_warehouse", "commit_facility", "save"]
    again = FakeRunner(tmp_path)
    again.constructed = True
    await again.run()
    assert all(name != "commit_facility" for name, _ in again.calls)


def test_changed_plan_cannot_reuse_ledger(tmp_path):
    runner = FakeRunner(tmp_path)
    runner.flush()
    changed = plan()
    changed["warehouses"][0]["position"]["x"] = 50
    with pytest.raises(batch.StopBatch):
        batch.Runner(None, changed, tmp_path, "build")


def test_batch_lock_blocks_second_runner_and_releases(tmp_path):
    with batch.batch_lock(tmp_path):
        with pytest.raises(batch.StopBatch):
            with batch.batch_lock(tmp_path):
                pass
    with batch.batch_lock(tmp_path):
        pass


class EvalBridge:
    def __init__(self):
        self.codes = []

    def heartbeat(self):
        return {"connected": True}

    async def call(self, command, args, **kwargs):
        assert command == "eval" and kwargs["engine"]
        self.codes.append(args["code"])
        if "B.commands.commit_facility" in args["code"]:
            return {"built": True, "verified": True, "freshPreview": {"preview_token": "fresh"}}
        return {"preview": True, "preview_token": "old"}


@async_test
async def test_disk_commit_repreviews_in_same_isolated_invocation(tmp_path):
    bridge = EvalBridge()
    runner = batch.Runner(bridge, plan(), tmp_path, "build", disk_bridge=True)
    await runner.call("build_warehouse", {"x": 0, "y": 0, "z": 1, "module_count": 4})
    result = await runner.call("commit_facility", {"preview_token": "discarded_preview_test_token"})
    assert result["verified"]
    code = bridge.codes[-1]
    assert "B.commands.build_warehouse(a)" in code
    assert "B.commands.commit_facility({preview_token=p.preview_token})" in code
    assert "discarded_preview_test_token" not in code
    assert "scratch[" not in code


@async_test
async def test_disk_commit_without_preview_does_not_call_game(tmp_path):
    bridge = EvalBridge()
    runner = batch.Runner(bridge, plan(), tmp_path, "build", disk_bridge=True)
    with pytest.raises(batch.StopBatch):
        await runner.call("commit_facility", {"preview_token": "old"})
    assert bridge.codes == []
