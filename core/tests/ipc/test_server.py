"""IPC server end to end: real Uvicorn on 127.0.0.1 and real WebSocket clients in the same loop."""

from __future__ import annotations

import asyncio
import http.client
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from ipc_harness import Harness, start_harness, stop_harness
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.typing import Origin

from ace_core.app.config import load_settings
from ace_core.app.container import build_container
from ace_core.app.events import AppStopping
from ace_core.app.health import HealthStatus
from ace_core.app.paths import AppPaths
from ace_core.app.state import ConversationState
from ace_core.ipc.schemas import MAX_MESSAGE_BYTES
from ace_core.ipc.server import IpcLimits, IpcServer


@pytest.fixture
async def harness(tmp_path: Path) -> AsyncIterator[Harness]:
    started = await start_harness(tmp_path)
    yield started
    await stop_harness(started)


async def authed(harness: Harness, **options: Any) -> ClientConnection:
    ws = await connect(harness.url, **options)
    await ws.send(json.dumps({"v": 1, "type": "auth", "token": harness.server.token}))
    ready = json.loads(await ws.recv())
    assert ready["method"] == "session.ready"
    return ws


async def request(
    ws: ClientConnection, method: str, params: dict[str, Any] | None = None, rid: str = "1"
) -> dict[str, Any]:
    message = {"v": 1, "type": "request", "id": rid, "method": method, "params": params or {}}
    await ws.send(json.dumps(message))
    async with asyncio.timeout(5):
        while True:
            reply: dict[str, Any] = json.loads(await ws.recv())
            if reply.get("id") == rid:
                return reply


async def next_event(ws: ClientConnection, name: str) -> dict[str, Any]:
    async with asyncio.timeout(5):
        while True:
            message: dict[str, Any] = json.loads(await ws.recv())
            if message.get("type") == "event" and message["method"] == name:
                return message


async def close_code(ws: ClientConnection) -> int | None:
    try:
        async with asyncio.timeout(5):
            while True:
                await ws.recv()
    except ConnectionClosed as closed:
        return closed.rcvd.code if closed.rcvd is not None else None


def raw_get(port: int, path: str, headers: dict[str, str]) -> tuple[int, str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.putrequest("GET", path, skip_host=True)
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        connection.close()


# ---- authentication ----


async def test_session_ready_after_auth(harness: Harness) -> None:
    ws = await connect(harness.url)
    await ws.send(json.dumps({"v": 1, "type": "auth", "token": harness.server.token}))
    ready = json.loads(await ws.recv())
    assert ready["type"] == "event"
    assert ready["method"] == "session.ready"
    assert ready["params"]["protocol"] == 1
    assert ready["params"]["state"]["conversation"] == "asleep"
    await ws.close()


async def test_wrong_token_is_closed(harness: Harness) -> None:
    ws = await connect(harness.url)
    await ws.send(json.dumps({"v": 1, "type": "auth", "token": "x" * 43}))
    assert await close_code(ws) == 4401


async def test_first_message_must_authenticate(harness: Harness) -> None:
    ws = await connect(harness.url)
    await ws.send(json.dumps({"type": "request", "id": "1", "method": "system.health"}))
    assert await close_code(ws) == 4401


async def test_silent_client_is_dropped_after_the_auth_timeout(tmp_path: Path) -> None:
    harness = await start_harness(tmp_path, limits=IpcLimits(auth_timeout_s=0.3))
    try:
        ws = await connect(harness.url)
        assert await close_code(ws) == 4401
    finally:
        await stop_harness(harness)


async def test_short_token_is_refused_at_start(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path, portable=False)
    container = build_container(load_settings(config_file=None), paths)
    with pytest.raises(ValueError, match="at least"):
        await IpcServer(container, token="x" * 8).start()


# ---- origins and hosts ----


async def test_foreign_origin_gets_http_403(harness: Harness) -> None:
    with pytest.raises(InvalidStatus) as excinfo:
        await connect(harness.url, origin=Origin("https://evil.example"))
    assert excinfo.value.response.status_code == 403


async def test_tauri_origin_is_accepted(harness: Harness) -> None:
    ws = await authed(harness, origin=Origin("http://tauri.localhost"))
    await ws.close()


async def test_dev_server_origin_only_in_dev_mode(tmp_path: Path) -> None:
    harness = await start_harness(tmp_path, dev=False)
    try:
        with pytest.raises(InvalidStatus) as excinfo:
            await connect(harness.url, origin=Origin("http://localhost:1420"))
        assert excinfo.value.response.status_code == 403
    finally:
        await stop_harness(harness)


async def test_unknown_host_header_is_rejected(harness: Harness) -> None:
    status, _ = await asyncio.to_thread(
        raw_get, harness.server.port, "/api/v1/health", {"Host": "evil.example"}
    )
    assert status == 400


async def test_rest_health_requires_the_bearer_token(harness: Harness) -> None:
    port = harness.server.port
    host = {"Host": f"127.0.0.1:{port}"}
    status, _ = await asyncio.to_thread(raw_get, port, "/api/v1/health", host)
    assert status == 401
    bearer = {**host, "Authorization": f"Bearer {harness.server.token}"}
    status, body = await asyncio.to_thread(raw_get, port, "/api/v1/health", bearer)
    assert status == 200
    assert json.loads(body)["overall"] == "ok"


# ---- limits and bad input ----


async def test_oversized_message_closes_the_connection(harness: Harness) -> None:
    ws = await authed(harness)
    await ws.send("x" * (MAX_MESSAGE_BYTES + 1024))
    assert await close_code(ws) == 1009


async def test_bad_messages_get_errors_and_the_connection_stays_open(harness: Harness) -> None:
    ws = await authed(harness)
    await ws.send("not json")
    bad = json.loads(await ws.recv())
    assert bad["error"]["code"] == "E_IPC_BAD_MESSAGE"

    unknown = await request(ws, "nope.method", rid="u")
    assert unknown["error"]["code"] == "E_IPC_UNKNOWN_METHOD"

    params = await request(ws, "settings.get", {"key": ""}, rid="p")
    assert params["error"]["code"] == "E_IPC_BAD_PARAMS"

    await ws.send(b"\x00\x01")
    binary = json.loads(await ws.recv())
    assert binary["error"]["code"] == "E_IPC_BAD_MESSAGE"

    healthy = await request(ws, "system.health", rid="h")
    assert healthy["type"] == "response"
    await ws.close()


async def test_rate_limit_answers_with_an_error(tmp_path: Path) -> None:
    harness = await start_harness(tmp_path, limits=IpcLimits(rate_per_s=1.0, rate_burst=3))
    try:
        ws = await authed(harness)
        for i in range(10):
            message = {"v": 1, "type": "request", "id": f"r{i}", "method": "system.health"}
            await ws.send(json.dumps(message))
        replies = [json.loads(await ws.recv()) for _ in range(10)]
        limited = [r for r in replies if r.get("error", {}).get("code") == "E_IPC_RATE_LIMITED"]
        assert len(limited) >= 5
        await ws.close()
    finally:
        await stop_harness(harness)


async def test_client_limit(tmp_path: Path) -> None:
    harness = await start_harness(tmp_path, limits=IpcLimits(max_clients=1))
    try:
        first = await authed(harness)
        with pytest.raises(InvalidStatus) as excinfo:
            await connect(harness.url)
        assert excinfo.value.response.status_code == 403
        await first.close()
    finally:
        await stop_harness(harness)


# ---- methods and events ----


async def test_settings_round_trip_is_audited_as_the_user(harness: Harness) -> None:
    ws = await authed(harness)
    saved = await request(ws, "settings.set", {"key": "theme", "value": {"mode": "dark"}})
    assert saved["result"] == {"key": "theme", "saved": True}
    loaded = await request(ws, "settings.get", {"key": "theme"}, rid="2")
    assert loaded["result"] == {"key": "theme", "found": True, "value": {"mode": "dark"}}
    missing = await request(ws, "settings.get", {"key": "absent"}, rid="3")
    assert missing["result"]["found"] is False
    (entry,) = await harness.container.audit.recent(event_type="settings.changed")
    assert entry.actor == "user"
    await ws.close()


async def test_state_and_health_changes_are_pushed(harness: Harness) -> None:
    ws = await authed(harness)
    await harness.container.state.update(conversation=ConversationState.LISTENING)
    changed = await next_event(ws, "state.changed")
    assert changed["params"]["state"]["conversation"] == "listening"
    assert changed["params"]["previous"]["conversation"] == "asleep"

    await harness.container.health.set("voice", HealthStatus.DEGRADED, "mic unplugged")
    health = await next_event(ws, "health.changed")
    assert health["params"] == {
        "subsystem": "voice",
        "status": "degraded",
        "previous": None,
        "detail": "mic unplugged",
    }
    state = await request(ws, "system.state.get")
    assert state["result"]["conversation"] == "listening"
    await ws.close()


async def test_log_tail_is_dev_only(tmp_path: Path) -> None:
    harness = await start_harness(tmp_path, dev=False)
    try:
        ws = await authed(harness)
        refused = await request(ws, "log.tail", {"lines": 5})
        assert refused["error"]["code"] == "E_IPC_DEV_ONLY"
        await ws.close()
    finally:
        await stop_harness(harness)


async def test_log_tail_in_dev_mode_returns_lines(harness: Harness) -> None:
    ws = await authed(harness)
    reply = await request(ws, "log.tail", {"lines": 5})
    assert isinstance(reply["result"]["lines"], list)
    await ws.close()


async def test_stopping_the_server_closes_clients(harness: Harness) -> None:
    ws = await authed(harness)
    await harness.server.stop()
    assert await close_code(ws) == 1001


async def test_queued_events_are_delivered_before_the_server_stops(harness: Harness) -> None:
    ws = await authed(harness)
    await harness.container.bus.publish(AppStopping(reason="test"))
    await harness.server.stop()
    stopping = await next_event(ws, "system.stopping")
    assert stopping["params"] == {"reason": "test"}
    assert await close_code(ws) == 1001


async def test_a_slow_request_does_not_hold_up_the_next(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ace_core.ipc import methods
    from ace_core.ipc.schemas import EmptyParams, HealthResult

    async def slow(ctx: methods.MethodContext, _: EmptyParams) -> HealthResult:
        await asyncio.sleep(0.5)
        return methods.health_result(ctx.container)

    spec = methods.MethodSpec("test.slow", EmptyParams, HealthResult, slow)
    monkeypatch.setitem(methods.METHODS, "test.slow", spec)
    ws = await authed(harness)
    try:
        for rid, method in (("slow", "test.slow"), ("fast", "system.health")):
            message = {"v": 1, "type": "request", "id": rid, "method": method, "params": {}}
            await ws.send(json.dumps(message))
        order: list[str] = []
        async with asyncio.timeout(5):
            while len(order) < 2:
                reply = json.loads(await ws.recv())
                if reply.get("type") == "response":
                    order.append(reply["id"])
        assert order == ["fast", "slow"]
    finally:
        await ws.close()


async def test_too_many_requests_in_flight_are_refused(tmp_path: Path) -> None:
    from ace_core.ipc import methods
    from ace_core.ipc.schemas import EmptyParams, HealthResult

    started = await start_harness(tmp_path, limits=IpcLimits(max_in_flight=1))
    gate = asyncio.Event()

    async def held(ctx: methods.MethodContext, _: EmptyParams) -> HealthResult:
        await gate.wait()
        return methods.health_result(ctx.container)

    methods.METHODS["test.held"] = methods.MethodSpec("test.held", EmptyParams, HealthResult, held)
    try:
        ws = await authed(started)
        for rid in ("one", "two"):
            message = {"v": 1, "type": "request", "id": rid, "method": "test.held", "params": {}}
            await ws.send(json.dumps(message))
        refused = await next_reply(ws, "two")
        assert refused["error"]["code"] == "E_IPC_RATE_LIMITED"
        gate.set()
        assert (await next_reply(ws, "one"))["type"] == "response"
        await ws.close()
    finally:
        methods.METHODS.pop("test.held", None)
        await stop_harness(started)


async def next_reply(ws: ClientConnection, rid: str) -> dict[str, Any]:
    async with asyncio.timeout(5):
        while True:
            reply: dict[str, Any] = json.loads(await ws.recv())
            if reply.get("id") == rid:
                return reply
