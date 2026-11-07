"""devices.* over the real WebSocket (S09): without audio, and with a fake audio backend."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np
from ipc_harness import start_harness, stop_harness
from websockets.asyncio.client import ClientConnection, connect

from ace_core.ipc.server import IpcServer
from ace_core.voice.audio import AudioService
from ace_core.voice.devices import AudioDevice, FakeAudioBackend

MIC = AudioDevice(1, "Microphone Array (Realtek(R) Audio)", True, 48_000, True)
SPEAKERS = AudioDevice(3, "Speakers (Realtek(R) Audio)", False, 48_000, True)


async def call(ws: ClientConnection, method: str, params: dict[str, Any] | None = None) -> Any:
    await ws.send(
        json.dumps(
            {"v": 1, "type": "request", "id": method, "method": method, "params": params or {}}
        )
    )
    async with asyncio.timeout(10):
        while True:
            message = json.loads(await ws.recv())
            if message.get("id") == method:
                return message.get("result", message.get("error"))


async def open_client(server: IpcServer) -> ClientConnection:
    ws = await connect(f"ws://127.0.0.1:{server.port}/ws")
    await ws.send(json.dumps({"v": 1, "type": "auth", "token": server.token}))
    await ws.recv()  # session.ready
    return ws


async def test_without_audio_everything_says_so(tmp_path: Path) -> None:
    harness = await start_harness(tmp_path)  # tests run with audio_enabled = false
    ws = await open_client(harness.server)
    try:
        listed = await call(ws, "devices.list")
        assert listed["available"] is False
        recorded = await call(ws, "devices.record_test", {"seconds": 1})
        assert (recorded["ok"], recorded["error"]) == (
            False,
            "Audio is not available on this system.",
        )
    finally:
        await ws.close()
        await stop_harness(harness)


async def test_devices_over_ipc_with_a_fake_backend(tmp_path: Path) -> None:
    harness = await start_harness(tmp_path)
    await harness.server.stop()
    backend = FakeAudioBackend([MIC, SPEAKERS])
    container = harness.container
    audio = AudioService(
        backend, bus=container.bus, state=container.state, settings=container.settings_store
    )
    container = dataclasses.replace(container, audio=audio)
    server = IpcServer(container)
    await server.start()
    ws = await open_client(server)
    try:
        listed = await call(ws, "devices.list")
        assert listed["available"] is True
        assert listed["inputs"] == [{"name": MIC.name, "is_default": True}]
        assert (await call(ws, "devices.select", {"kind": "input", "name": MIC.name}))["saved"]
        assert (await call(ws, "devices.list"))["input"] == MIC.name

        async def talk() -> None:
            while not backend.open_streams:
                await asyncio.sleep(0.01)
            for _ in range(5):
                backend.feed(np.full(1280, 6000, dtype=np.int16))

        talker = asyncio.create_task(talk())
        recorded = await call(ws, "devices.record_test", {"seconds": 0.5})
        await talker
        assert recorded["ok"] and recorded["seconds"] == 0.4 and recorded["peak"] > 0.15
        played = await call(ws, "devices.play_test")
        assert played == {"ok": True, "error": None, "seconds": 0.4}
        assert (await call(ws, "devices.stop"))["ok"]
        assert (await call(ws, "devices.mute", {"muted": True})) == {"muted": True}
        muted = await call(ws, "devices.record_test", {"seconds": 1})
        assert (muted["ok"], muted["error"]) == (False, "The microphone is muted.")
        bad = await call(ws, "devices.record_test", {"seconds": 30})
        assert bad["code"] == "E_IPC_BAD_PARAMS"
    finally:
        await ws.close()
        await server.stop()
        await audio.close()
        await container.pipeline.close()
        await container.db.close()
