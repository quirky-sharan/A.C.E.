"""The real WASAPI backend on the dev PC (S09). Local only: marked ``hardware`` (CI skips it) and
opt-in with ACE_HARDWARE_TESTS=1, because it opens the microphone and plays a short sound."""

from __future__ import annotations

import os
import sys
import time

import pytest

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(
        sys.platform != "win32" or os.environ.get("ACE_HARDWARE_TESTS") != "1",
        reason="set ACE_HARDWARE_TESTS=1 on a PC with a microphone and speakers to run",
    ),
]


async def test_capture_playback_and_cpu() -> None:
    from ace_core.app.events import EventBus
    from ace_core.app.state import StateStore
    from ace_core.voice.audio import AudioService
    from ace_core.voice.devices import SoundDeviceBackend
    from ace_core.voice.dsp import CAPTURE_RATE

    class Settings:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}

        async def get(self, key: str, default: object = None) -> object:
            return self.values.get(key, default)

        async def set(self, key: str, value: object, *, actor: str = "system") -> None:
            self.values[key] = value

    bus = EventBus()
    audio = AudioService(
        SoundDeviceBackend(),
        bus=bus,
        state=StateStore(bus),
        settings=Settings(),  # type: ignore[arg-type]
    )
    try:
        devices = await audio.devices()
        assert any(d.is_input for d in devices) and any(not d.is_input for d in devices)
        cpu_before, wall_before = time.process_time(), time.perf_counter()
        samples = await audio.record(2.0)
        cpu = (time.process_time() - cpu_before) / (time.perf_counter() - wall_before)
        assert abs(len(samples) / CAPTURE_RATE - 2.0) < 0.3
        assert cpu < 0.05, f"capture used {cpu:.1%} of one core"
        await audio.earcon("test")
        started = time.perf_counter()
        await audio.stop_playback()
        assert time.perf_counter() - started < 0.1
    finally:
        await audio.close()
