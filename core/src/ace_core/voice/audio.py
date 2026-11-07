"""Audio I/O (ACE_MASTER_PLAN.md §7.1, S09, D-58).

- Capture: 16 kHz mono int16 (Windows resamples in WASAPI shared mode; our own resampler is the
  fallback) into a 2 s pre-roll ring buffer. Until the wake word (S12) the microphone is opened
  only when something needs it (Sharan's choice, D-58): the Devices page meter and test recording.
- Playback: one output stream fed from a queue in 10 ms blocks, so ``stop_playback`` is heard
  within ~20 ms (target ≤ 100 ms); the stream closes again when idle.
- Mute closes the capture stream (the Windows mic-in-use icon goes away) and keeps it closed; it
  is stored in ``audio.mic_muted`` and shown as the MUTED state.
- The audio callbacks only copy numbers: no awaits, logging or inference (§5.7).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Final, TypeVar, cast

import numpy as np
import structlog
from pydantic import JsonValue

from ace_core.app.events import Event, EventBus
from ace_core.app.health import HealthRegistry, HealthStatus
from ace_core.app.state import ConversationState, StateStore
from ace_core.skills.base import SettingsAccess
from ace_core.voice.devices import AudioBackend, AudioDevice, AudioDeviceError, Stream, pick
from ace_core.voice.dsp import (
    CAPTURE_RATE,
    PRE_ROLL_S,
    Float32,
    Int16,
    Resampler,
    RingBuffer,
    rms_level,
    to_float32,
    to_int16,
)
from ace_core.voice.earcons import EARCON_RATE, render

log = structlog.stdlib.get_logger(__name__)
T = TypeVar("T")

INPUT_SETTING: Final = "audio.input_device"  # a device name; null = the Windows default
OUTPUT_SETTING: Final = "audio.output_device"
MUTED_SETTING: Final = "audio.mic_muted"
INPUT_BLOCK: Final = 1280  # 80 ms at 16 kHz (§7.1; the wake-word chunk size, checked at S12)
OUTPUT_RATE: Final = 48_000
OUTPUT_BLOCK: Final = 480  # 10 ms
LEVEL_HZ: Final = 20.0  # audio.level events while capturing (§5.5: 15-30 Hz)
IDLE_CLOSE_S: Final = 1.0  # close the output stream after this long with nothing to play
MAX_RECORD_S: Final = 10.0
HEALTH_SUBSYSTEM: Final = "audio"


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioLevel(Event):
    level: float  # 0..1 (dB scale)


class MicMutedError(Exception):
    pass


class AudioService:
    def __init__(
        self,
        backend: AudioBackend,
        *,
        bus: EventBus,
        state: StateStore,
        settings: SettingsAccess,
        health: HealthRegistry | None = None,
        level_hz: float = LEVEL_HZ,
        idle_close_s: float = IDLE_CLOSE_S,
    ) -> None:
        self._backend = backend
        self._bus = bus
        self._state = state
        self._settings = settings
        self._health = health
        self._level_interval = 1.0 / level_hz
        self._idle_close_s = idle_close_s
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ace-audio")
        self._lock = asyncio.Lock()  # one open / close / refresh at a time
        self.ring = RingBuffer(int(CAPTURE_RATE * PRE_ROLL_S))
        self._capture: Stream | None = None
        self._capture_users: set[str] = set()
        self._resampler: Resampler | None = None
        self._level = 0.0
        self._recording: list[Int16] | None = None
        self._last_recording: Int16 | None = None
        self._output: Stream | None = None
        self._queue: deque[Float32] = deque()
        self._current: Float32 | None = None
        self._offset = 0
        self._muted = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._level_task: asyncio.Task[None] | None = None
        self._idle_task: asyncio.Task[None] | None = None

    # ---- lifecycle ----

    async def start(self) -> None:
        self._muted = (await self._settings.get(MUTED_SETTING)) is True
        if self._muted:
            await self._state.update(conversation=ConversationState.MUTED)
        try:
            devices = await self.devices()
        except Exception:
            log.exception("audio devices could not be listed")
            devices = []
        if self._health is not None:
            if any(d.is_input for d in devices):
                await self._health.set(HEALTH_SUBSYSTEM, HealthStatus.OK)
            else:
                await self._health.set(
                    HEALTH_SUBSYSTEM, HealthStatus.DEGRADED, "no microphone was found"
                )

    async def close(self) -> None:
        for task in (self._level_task, self._idle_task, *self._tasks):
            if task is not None:
                task.cancel()
        self._capture_users.clear()
        await self._close_stream("capture")
        await self._close_stream("output")
        await asyncio.to_thread(self._executor.shutdown, True)

    async def _run(self, fn: Callable[..., T], *args: Any) -> T:
        return await asyncio.get_running_loop().run_in_executor(self._executor, lambda: fn(*args))

    # ---- devices ----

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def capturing(self) -> bool:
        return self._capture is not None

    @property
    def playing(self) -> bool:
        return self._current is not None or bool(self._queue)

    async def devices(self) -> list[AudioDevice]:
        """Re-scanned when no stream is open, so newly connected devices show up."""
        async with self._lock:
            if self._capture is None and self._output is None:
                await self._run(self._backend.refresh)
            return await self._run(self._backend.devices)

    async def selection(self) -> tuple[str | None, str | None]:
        chosen_in = await self._settings.get(INPUT_SETTING)
        chosen_out = await self._settings.get(OUTPUT_SETTING)
        return (
            chosen_in if isinstance(chosen_in, str) else None,
            chosen_out if isinstance(chosen_out, str) else None,
        )

    async def select(self, *, is_input: bool, name: str | None) -> None:
        value: JsonValue = name
        await self._settings.set(INPUT_SETTING if is_input else OUTPUT_SETTING, value, actor="user")
        if is_input and self._capture is not None:  # switch now
            users = set(self._capture_users)
            await self._close_stream("capture")
            self._capture_users = users
            await self._open_capture()
        elif not is_input and self._output is not None:
            await self._close_stream("output")

    async def _device(self, *, is_input: bool) -> AudioDevice:
        if self._capture is None and self._output is None:
            await self._run(self._backend.refresh)
        devices = await self._run(self._backend.devices)
        wanted = (await self.selection())[0 if is_input else 1]
        device = pick(devices, wanted, is_input=is_input)
        if device is None:
            kind = "microphone" if is_input else "speaker"
            raise AudioDeviceError(f"No {kind} was found.")
        return device

    # ---- capture ----

    async def start_capture(self, purpose: str) -> None:
        if self._muted:
            raise MicMutedError("The microphone is muted.")
        self._capture_users.add(purpose)
        if self._capture is None:
            try:
                await self._open_capture()
            except Exception:
                self._capture_users.discard(purpose)
                raise

    async def stop_capture(self, purpose: str) -> None:
        self._capture_users.discard(purpose)
        if not self._capture_users:
            await self._close_stream("capture")

    async def _open_capture(self) -> None:
        async with self._lock:
            if self._capture is not None:
                return
            device = await self._device(is_input=True)
            self._resampler = None
            try:
                stream = await self._run(
                    lambda: self._backend.open_input(
                        device, CAPTURE_RATE, INPUT_BLOCK, self._on_input, convert=True
                    )
                )
            except AudioDeviceError:
                rate = device.default_rate  # the device refuses Windows resampling: do it here
                self._resampler = Resampler(rate, CAPTURE_RATE)
                block = INPUT_BLOCK * rate // CAPTURE_RATE
                stream = await self._run(
                    lambda: self._backend.open_input(
                        device, rate, block, self._on_input, convert=False
                    )
                )
            self._capture = stream
            self.ring.clear()
            self._level = 0.0
            self._level_task = asyncio.create_task(self._emit_levels(), name="ace-audio-level")
            log.info("microphone open", device=device.name, resampled=self._resampler is not None)

    def _on_input(self, block: Int16) -> None:
        """The audio thread: copy and measure only."""
        resampler = self._resampler
        samples = resampler.process(block) if resampler is not None else block
        self.ring.write(samples)
        recording = self._recording
        if recording is not None:
            recording.append(samples.copy())
        self._level = rms_level(samples)

    async def _emit_levels(self) -> None:
        last = -1.0
        while True:
            await asyncio.sleep(self._level_interval)
            level = round(self._level, 3)
            if abs(level - last) >= 0.005:
                last = level
                await self._bus.publish(AudioLevel(level=level))

    async def record(self, seconds: float) -> Int16:
        """Capture ``seconds`` of audio (Devices page test); kept for ``play_recording``."""
        seconds = max(0.5, min(MAX_RECORD_S, seconds))
        self._recording = []
        await self.start_capture("record")
        try:
            await asyncio.sleep(seconds)
        finally:
            chunks, self._recording = self._recording or [], None
            await self.stop_capture("record")
        samples = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
        self._last_recording = samples
        return samples

    @property
    def last_recording(self) -> Int16 | None:
        return self._last_recording

    # ---- playback ----

    async def play(self, samples: Int16 | Float32, rate: int) -> None:
        """Queue audio; it starts at once if nothing else is playing."""
        pcm: Int16 = (
            to_int16(cast("Float32", samples))
            if samples.dtype == np.float32
            else cast("Int16", samples)
        )
        if rate != OUTPUT_RATE:
            pcm = Resampler(rate, OUTPUT_RATE).process(pcm)
        self._queue.append(to_float32(pcm))
        if self._output is None:
            async with self._lock:
                if self._output is None:
                    device = await self._device(is_input=False)
                    self._output = await self._run(
                        lambda: self._backend.open_output(
                            device, OUTPUT_RATE, OUTPUT_BLOCK, self._on_output
                        )
                    )
        if self._idle_task is None or self._idle_task.done():
            self._idle_task = asyncio.create_task(self._close_when_idle(), name="ace-audio-idle")

    async def play_recording(self) -> float:
        """Play the last test recording; returns its length in seconds (0 if none)."""
        recording = self._last_recording
        if recording is None or len(recording) == 0:
            return 0.0
        await self.play(recording, CAPTURE_RATE)
        return len(recording) / CAPTURE_RATE

    async def earcon(self, name: str) -> None:
        await self.play(render(name), EARCON_RATE)

    def _on_output(self, frames: int) -> Float32:
        """The audio thread: fill ``frames`` samples from the queue, silence when empty."""
        out = np.zeros(frames, dtype=np.float32)
        filled = 0
        while filled < frames:
            current = self._current
            if current is None:
                if not self._queue:
                    break
                current, self._offset = self._queue.popleft(), 0
                self._current = current
            take = min(frames - filled, len(current) - self._offset)
            out[filled : filled + take] = current[self._offset : self._offset + take]
            filled += take
            self._offset += take
            if self._offset >= len(current):
                self._current = None
        return out

    async def stop_playback(self) -> None:
        self._queue.clear()
        self._current = None  # the next 10 ms block is silence

    async def _close_when_idle(self) -> None:
        quiet = 0.0
        while quiet < self._idle_close_s:
            await asyncio.sleep(0.1)
            quiet = 0.0 if self.playing else quiet + 0.1
        await self._close_stream("output")

    async def _close_stream(self, kind: str) -> None:
        async with self._lock:
            stream = self._capture if kind == "capture" else self._output
            if stream is None:
                return
            if kind == "capture":
                self._capture, self._resampler = None, None
                if self._level_task is not None:
                    self._level_task.cancel()
                    self._level_task = None
            else:
                self._output = None
            with contextlib.suppress(Exception):
                await self._run(stream.close)
        if kind == "capture":
            self._level = 0.0
            await self._bus.publish(AudioLevel(level=0.0))
            log.info("microphone closed")

    # ---- mute ----

    async def set_muted(self, muted: bool) -> None:
        if muted == self._muted:
            return
        self._muted = muted
        if muted:
            self._capture_users.clear()
            self._recording = None
            await self._close_stream("capture")
        await self._settings.set(MUTED_SETTING, muted, actor="user")
        current = self._state.current.conversation
        if muted:
            await self._state.update(conversation=ConversationState.MUTED)
        elif current is ConversationState.MUTED:
            await self._state.update(conversation=ConversationState.ASLEEP)
        try:
            await self.earcon("mute" if muted else "unmute")
        except Exception:
            log.warning("the mute sound could not be played")

    async def toggle_mute(self) -> bool:
        await self.set_muted(not self._muted)
        return self._muted
