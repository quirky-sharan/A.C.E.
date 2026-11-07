"""The command pipeline over the real WebSocket: submit -> expected event sequence (S07 tests)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from ipc_harness import Harness, start_harness, stop_harness
from websockets.asyncio.client import ClientConnection, connect


@pytest.fixture
async def harness(tmp_path: Path) -> AsyncIterator[Harness]:
    started = await start_harness(tmp_path)
    yield started
    await stop_harness(started)


async def authed(harness: Harness) -> ClientConnection:
    ws = await connect(harness.url)
    await ws.send(json.dumps({"v": 1, "type": "auth", "token": harness.server.token}))
    assert json.loads(await ws.recv())["method"] == "session.ready"
    return ws


class Session:
    """One client: sends requests and keeps every event it receives, in order."""

    def __init__(self, ws: ClientConnection) -> None:
        self.ws = ws
        self.events: list[tuple[str, dict[str, Any]]] = []
        self._ids = 0

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ids += 1
        rid = f"r{self._ids}"
        message = {"v": 1, "type": "request", "id": rid, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(message))
        async with asyncio.timeout(5):
            while True:
                incoming: dict[str, Any] = json.loads(await self.ws.recv())
                if incoming.get("type") == "event":
                    self.events.append((incoming["method"], incoming["params"]))
                elif incoming.get("id") == rid:
                    return incoming

    async def until(self, name: str, **match: Any) -> dict[str, Any]:
        """The first event called ``name`` whose payload contains ``match`` (seen or upcoming)."""

        def matches(params: dict[str, Any]) -> bool:
            body = next(iter(params.values())) if len(params) == 1 else params
            return all(body.get(key) == value for key, value in match.items())

        seen = 0
        async with asyncio.timeout(5):
            while True:
                for event_name, params in self.events[seen:]:
                    if event_name == name and matches(params):
                        return params
                seen = len(self.events)
                incoming = json.loads(await self.ws.recv())
                if incoming.get("type") == "event":
                    self.events.append((incoming["method"], incoming["params"]))

    def names(self) -> list[str]:
        return [name for name, _ in self.events]


async def test_submit_produces_the_expected_event_sequence(harness: Harness) -> None:
    session = Session(await authed(harness))
    try:
        response = await session.call("command.submit", {"text": "  echo hello  "})
        result = response["result"]
        assert result["intent"] == "system.echo"
        task_id = result["task_id"]
        finished = await session.until("task.finished", id=task_id)
        assert finished["task"]["status"] == "succeeded"
        assert finished["task"]["steps"][0]["label"] == 'Echo "hello"'
        reply = await session.until("message.created", role="ace", task_id=task_id)
        assert reply["message"]["text"] == "hello"
        assert reply["message"]["reply_to"] == result["message_id"]
        names = session.names()
        order = [
            names.index("message.created"),  # Sharan's message first
            names.index("task.created"),
            names.index("task.finished"),
            len(names) - 1 - names[::-1].index("message.created"),  # ACE's reply last
        ]
        assert order == sorted(order)
        assert "state.changed" in names
        tasks = (await session.call("task.list", {"limit": 5}))["result"]["tasks"]
        assert [t["id"] for t in tasks] == [task_id]
        messages = (await session.call("message.list"))["result"]["messages"]
        assert [(m["role"], m["text"]) for m in messages] == [
            ("user", "echo hello"),
            ("ace", "hello"),
        ]
    finally:
        await session.ws.close()


async def test_confirmations_over_ipc(harness: Harness) -> None:
    session = Session(await authed(harness))
    try:
        result = (await session.call("command.submit", {"text": "demo dangerous"}))["result"]
        requested = await session.until("confirm.requested", task_id=result["task_id"])
        confirmation = requested["confirmation"]
        waiting = await session.until("task.updated", id=result["task_id"], status="waiting_user")
        assert waiting["task"]["confirmation"]["id"] == confirmation["id"]
        listed = (await session.call("task.list"))["result"]["tasks"]
        assert listed[0]["confirmation"]["id"] == confirmation["id"]
        answer = {"confirmation_id": confirmation["id"], "answer": "yes"}
        assert (await session.call("confirm.respond", answer))["result"] == {"accepted": True}
        finished = await session.until("task.finished", id=result["task_id"])
        assert finished["task"]["status"] == "succeeded"
        assert finished["task"]["confirmation"] is None
        assert (await session.call("confirm.respond", answer))["result"] == {"accepted": False}
    finally:
        await session.ws.close()


async def test_refusal_cancel_and_settings_events(harness: Harness) -> None:
    session = Session(await authed(harness))
    try:
        result = (await session.call("command.submit", {"text": "demo forbidden"}))["result"]
        finished = await session.until("task.finished", id=result["task_id"])
        assert finished["task"]["error_code"] == "E_SUPERVISOR_FORBIDDEN"
        assert finished["task"]["steps"][0]["status"] == "refused"

        result = (await session.call("command.submit", {"text": "demo dangerous"}))["result"]
        await session.until("confirm.requested", task_id=result["task_id"])
        cancel = await session.call("task.cancel", {"task_id": result["task_id"]})
        assert cancel["result"] == {"cancelled": True}
        finished = await session.until("task.finished", id=result["task_id"])
        assert finished["task"]["status"] == "cancelled"
        missing = await session.call("task.cancel", {"task_id": "no-such-task"})
        assert missing["result"] == {"cancelled": False}

        await session.call("command.submit", {"text": "paranoid mode"})
        changed = await session.until("settings.changed", key="verification.mode")
        assert changed == {"key": "verification.mode", "deleted": False}
    finally:
        await session.ws.close()


@pytest.mark.parametrize("text", ["", "   ", "x" * 2001])
async def test_bad_commands_are_rejected(harness: Harness, text: str) -> None:
    session = Session(await authed(harness))
    try:
        response = await session.call("command.submit", {"text": text})
        assert response["type"] == "error"
        assert response["error"]["code"] == "E_IPC_BAD_PARAMS"
    finally:
        await session.ws.close()
