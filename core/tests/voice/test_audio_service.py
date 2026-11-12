"""The audio service on a fake backend (S09): on-demand capture, pre-roll, levels, hard mute,
device selection, playback queue and fast stop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np
import pytest
from pydantic import JsonValue

from ace_core.app.events import EventBus
from ace_core.app.health import HealthRegistry, HealthStatus
from ace_core.app.state import ConversationState, StateStore
from ace_core.db.stores import Actor
from ace_core.voice.audio import (
    MUTED_SETTING,
    OUTPUT_BLOCK,
    AudioLevel,
    AudioService,
    MicMutedError,
)
from ace_core.voice.devices import AudioDevice, AudioDeviceError, FakeAudioBackend
from ace_core.voice.dsp import CAPTURE_RATE


class Settings:
    def __init__(self) -> None:
        self.values: dict[str, JsonValue] = {}

    async def get(self, key: str, default: JsonValue = None) -> JsonValue:
        return self.values.get(key, default)

    async def set(self, key: str, value: JsonValue, *, actor: Actor = "system") -> None:
        self.values[key] = value


MIC = AudioDevice(1, "Microphone Array (Realtek(R) Audio)", True, 48_000, True)
HEADSET = AudioDevice(2, "Headset (Bluetooth)", True, 16_000, False)
SPEAKERS = AudioDevice(3, "Speakers (Realtek(R) Audio)", False, 48_000, True)


class Env:
    def __init__(self, backend: FakeAudioBackend) -> None:
        self.backend = backend
        self.bus = EventBus()
        self.state = StateStore(self.bus)
        self.settings = Settings()
        self.health = HealthRegistry(self.bus)
        self.levels: list[float] = []
        self.audio = AudioService(
            backend,
            bus=self.bus,
            state=self.state,
            settings=self.settings,
            health=self.health,
            level_hz=100.0,
            idle_close_s=0.2,
        )

        async def remember(event: AudioLevel) -> None:
            self.levels.append(event.level)

        self.bus.subscribe(AudioLevel, remember)


@pytest.fixture
async def env() -> AsyncIterator[Env]:
    made = Env(FakeAudioBackend([MIC, HEADSET, SPEAKERS]))
    yield made
    await made.audio.close()


def tone(seconds: float = 0.08, amplitude: int = 8000) -> np.ndarray:
    t = np.arange(int(CAPTURE_RATE * seconds)) / CAPTURE_RATE
    return (amplitude * np.sin(2 * np.pi * 300 * t)).astype(np.int16)


async def test_the_microphone_opens_only_while_needed(env: Env) -> None:
    await env.audio.start()
    assert env.backend.open_streams == []  # nothing listens on start (D-58)
    assert env.health.snapshot().overall is HealthStatus.OK
    await env.audio.start_capture("meter")
    assert env.audio.capturing
    assert env.backend.input_rate == CAPTURE_RATE  # Windows resamples to 16 kHz
    for _ in range(3):
        env.backend.feed(tone())
    assert len(env.audio.ring.latest(CAPTURE_RATE * 2)) == 3 * 1280
    await asyncio.sleep(0.05)
    assert max(env.levels) > 0.5  # audio.level events while capturing
    await env.audio.stop_capture("meter")
    assert env.backend.open_streams == []
    assert env.levels[-1] == 0.0


async def test_a_device_that_refuses_windows_resampling_is_resampled_here() -> None:
    backend = FakeAudioBackend([MIC, SPEAKERS], native_only={MIC.name})
    env = Env(backend)
    try:
        await env.audio.start_capture("meter")
        assert backend.input_rate == 48_000
        backend.feed(np.zeros(3840, dtype=np.int16))  # 80 ms at 48 kHz
        assert abs(len(env.audio.ring.latest(10_000)) - 1280) <= 2  # 80 ms at 16 kHz
    finally:
        await env.audio.close()


async def test_recording_and_playback(env: Env) -> None:
    async def talk() -> None:
        await asyncio.sleep(0.02)
        for _ in range(5):
            env.backend.feed(tone())

    talker = asyncio.create_task(talk())
    samples = await env.audio.record(0.5)
    await talker
    assert len(samples) == 5 * 1280
    assert env.backend.open_streams == []  # the mic closes after the test recording
    assert await env.audio.play_recording() == pytest.approx(0.4)
    assert env.audio.playing
    played = env.backend.pull(OUTPUT_BLOCK)
    assert np.max(np.abs(played)) > 0.1  # resampled to 48 kHz and audible
    await env.audio.stop_playback()
    assert not np.any(env.backend.pull(OUTPUT_BLOCK))  # silent from the next 10 ms block
    await asyncio.sleep(0.5)
    assert env.backend.open_streams == []  # the idle output stream is closed again


async def test_mute_closes_the_microphone_and_keeps_it_closed(env: Env) -> None:
    await env.audio.start_capture("meter")
    assert await env.audio.toggle_mute() is True
    assert env.audio.muted and not env.audio.capturing
    assert all(s.kind == "output" for s in env.backend.open_streams)  # only the mute sound plays
    assert env.state.current.conversation is ConversationState.MUTED
    assert env.settings.values[MUTED_SETTING] is True
    with pytest.raises(MicMutedError):
        await env.audio.start_capture("meter")
    with pytest.raises(MicMutedError):
        await env.audio.record(1)
    await env.audio.set_muted(False)
    after: ConversationState = env.state.current.conversation
    assert after is ConversationState.ASLEEP
    await env.audio.start_capture("meter")
    assert env.audio.capturing


async def test_mute_is_remembered_across_restarts(env: Env) -> None:
    env.settings.values[MUTED_SETTING] = True
    await env.audio.start()
    assert env.audio.muted
    assert env.state.current.conversation is ConversationState.MUTED


async def test_devices_are_rescanned_and_selected_by_name(env: Env) -> None:
    devices = await env.audio.devices()
    assert env.backend.refreshes == 1  # a headset connected since the last look shows up
    assert {d.name for d in devices if d.is_input} == {MIC.name, HEADSET.name}
    await env.audio.start_capture("meter")  # opening re-scans too (no stream was open)
    scans = env.backend.refreshes
    await env.audio.devices()
    assert env.backend.refreshes == scans  # never while a stream is open
    await env.audio.select(is_input=True, name=HEADSET.name)
    assert [s.device for s in env.backend.open_streams] == [HEADSET]  # switched at once
    assert await env.audio.selection() == (HEADSET.name, None)


async def test_missing_or_broken_devices_are_reported() -> None:
    env = Env(FakeAudioBackend([SPEAKERS]))
    try:
        await env.audio.start()
        assert env.health.snapshot().overall is HealthStatus.DEGRADED
        with pytest.raises(AudioDeviceError, match="No microphone"):
            await env.audio.start_capture("meter")
        assert not env.audio.capturing
    finally:
        await env.audio.close()
