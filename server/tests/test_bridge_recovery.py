"""File-transport fault injection, isolated from the real game/userdata."""
import asyncio

import pytest

from tf3_mcp.bridge import Bridge, BridgeError, decode_message, encode_message


def read(path):
    return decode_message(path.read_text(encoding="utf8")) if path.exists() else None


async def request(bridge, previous=None):
    async with asyncio.timeout(3):
        while True:
            value = read(bridge.request_path)
            if value and value.get("id") and value["id"] != previous:
                return value
            await asyncio.sleep(.005)


def respond(bridge, req, result):
    bridge.response_path.write_text(encode_message({"id": req["id"], "ok": True,
                                                   "result": result}), encoding="utf8")


def test_executed_mutation_without_ack_is_not_retried(tmp_path):
    async def scenario():
        bridge = Bridge(tmp_path, timeout=.1, poll=.005)
        task = asyncio.create_task(bridge.call("test_mutation", engine=True))
        first = await request(bridge)
        # Model the engine applying the mutation, then losing its acknowledgement.
        world = {"applied": 1}
        with pytest.raises(BridgeError, match="timed out"):
            await task
        assert read(bridge.request_path) == {"idle": True}
        # A subsequent reconciliation query must not replay the mutation, nor
        # mistake its late acknowledgement for the query's response.
        query = asyncio.create_task(bridge.call("test_readback", timeout=1))
        second = await request(bridge, first["id"])
        assert second["cmd"] == "test_readback"
        respond(bridge, first, {"wrong_response": True})
        await asyncio.sleep(.025)
        assert not query.done()
        respond(bridge, second, world)
        assert await query == {"applied": 1}
        assert read(bridge.request_path) == {"idle": True}
    asyncio.run(scenario())


def test_cancelled_request_releases_lock_and_clears_request(tmp_path):
    async def scenario():
        bridge = Bridge(tmp_path, timeout=1, poll=.005)
        task = asyncio.create_task(bridge.call("test_query"))
        old = await request(bridge)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert read(bridge.request_path) == {"idle": True}
        other = Bridge(tmp_path, timeout=1, poll=.005)
        task = asyncio.create_task(other.call("test_after_cancel"))
        current = await request(other, old["id"])
        respond(other, current, "recovered")
        assert await task == "recovered"
    asyncio.run(scenario())


def test_competing_client_timeout_does_not_clear_owner_request(tmp_path):
    async def scenario():
        owner = Bridge(tmp_path, timeout=1, poll=.005)
        contender = Bridge(tmp_path, timeout=.05, poll=.005)
        task = asyncio.create_task(owner.call("test_owner"))
        original = await request(owner)
        with pytest.raises(BridgeError, match="another bridge client"):
            await contender.call("test_contender")
        assert read(owner.request_path) == original
        respond(owner, original, "owner_completed")
        assert await task == "owner_completed"
    asyncio.run(scenario())


def test_partial_response_is_ignored_until_complete(tmp_path):
    async def scenario():
        bridge = Bridge(tmp_path, timeout=1, poll=.005)
        task = asyncio.create_task(bridge.call("test_query"))
        current = await request(bridge)
        bridge.response_path.write_text('function data() return {hex="7', encoding="utf8")
        await asyncio.sleep(.025)
        assert not task.done()
        respond(bridge, current, {"complete": True})
        assert await task == {"complete": True}
    asyncio.run(scenario())
