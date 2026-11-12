"""Audio devices behind a small backend interface (S09, §7.1): WASAPI through sounddevice, or a
fake for tests. Devices are chosen by name and fall back to the Windows default.

PortAudio only re-scans devices when it is re-initialised, so ``refresh()`` (sounddevice's
``_terminate`` / ``_initialize``, checked in the installed 0.5.6 source) runs while no stream is
open, before every device list and stream start: a headset connected mid-session is found
without restarting ACE (S12 adds following device changes while a stream stays open).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

import numpy as np

from ace_core.voice.dsp import Float32, Int16

InputCallback = Callable[[Int16], None]  # mono int16 block
OutputCallback = Callable[[int], Float32]  # frames wanted -> mono float32 block of that length

WASAPI: Final = "Windows WASAPI"


class AudioDeviceError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AudioDevice:
    index: int
    name: str
    is_input: bool
    default_rate: int
    is_default: bool


class Stream(Protocol):
    def close(self) -> None: ...


class AudioBackend(Protocol):
    def refresh(self) -> None:
        """Re-scan devices. Only call while no stream is open."""

    def devices(self) -> list[AudioDevice]: ...

    def open_input(
        self,
        device: AudioDevice,
        rate: int,
        blocksize: int,
        callback: InputCallback,
        *,
        convert: bool,
    ) -> Stream:
        """A started capture stream (mono int16). ``convert``: let Windows resample (WASAPI)."""

    def open_output(
        self, device: AudioDevice, rate: int, blocksize: int, callback: OutputCallback
    ) -> Stream:
        """A started playback stream (mono float32, Windows converts to the device format)."""


def pick(
    devices: Sequence[AudioDevice], wanted: str | None, *, is_input: bool
) -> AudioDevice | None:
    """The device called ``wanted`` (exact, then ignoring case), else the Windows default."""
    pool = [d for d in devices if d.is_input == is_input]
    if wanted:
        exact = next((d for d in pool if d.name == wanted), None)
        if exact is not None:
            return exact
        folded = next((d for d in pool if d.name.casefold() == wanted.casefold()), None)
        if folded is not None:
            return folded
    return next((d for d in pool if d.is_default), pool[0] if pool else None)


class _SdStream:
    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


class SoundDeviceBackend:
    """WASAPI shared mode through sounddevice (PortAudio)."""

    def __init__(self) -> None:
        import sounddevice  # type: ignore[import-untyped]  # loads PortAudio; Windows only

        self._sd: Any = sounddevice

    def refresh(self) -> None:
        self._sd._terminate()
        self._sd._initialize()

    def _wasapi(self) -> tuple[int, dict[str, Any]] | None:
        for index, api in enumerate(self._sd.query_hostapis()):
            if api["name"] == WASAPI:
                return index, api
        return None

    def devices(self) -> list[AudioDevice]:
        found = self._wasapi()
        if found is None:
            return []
        _, api = found
        result: list[AudioDevice] = []
        for index in api["devices"]:
            info = self._sd.query_devices(index)
            for is_input, channels, default in (
                (True, info["max_input_channels"], api["default_input_device"]),
                (False, info["max_output_channels"], api["default_output_device"]),
            ):
                if channels > 0:
                    result.append(
                        AudioDevice(
                            index=index,
                            name=str(info["name"]),
                            is_input=is_input,
                            default_rate=int(info["default_samplerate"]),
                            is_default=index == default,
                        )
                    )
        return result

    def open_input(
        self,
        device: AudioDevice,
        rate: int,
        blocksize: int,
        callback: InputCallback,
        *,
        convert: bool,
    ) -> Stream:
        def on_block(indata: Any, frames: int, time: Any, status: Any) -> None:
            callback(np.ascontiguousarray(indata[:, 0]))

        try:
            stream = self._sd.InputStream(
                device=device.index,
                samplerate=rate,
                channels=1,
                dtype="int16",
                blocksize=blocksize,
                extra_settings=self._sd.WasapiSettings(auto_convert=convert),
                callback=on_block,
            )
            stream.start()
        except Exception as exc:
            raise AudioDeviceError(f"cannot open {device.name}: {exc}") from exc
        return _SdStream(stream)

    def open_output(
        self, device: AudioDevice, rate: int, blocksize: int, callback: OutputCallback
    ) -> Stream:
        def on_block(outdata: Any, frames: int, time: Any, status: Any) -> None:
            outdata[:, 0] = callback(frames)

        try:
            stream = self._sd.OutputStream(
                device=device.index,
                samplerate=rate,
                channels=1,
                dtype="float32",
                blocksize=blocksize,
                extra_settings=self._sd.WasapiSettings(auto_convert=True),
                callback=on_block,
            )
            stream.start()
        except Exception as exc:
            raise AudioDeviceError(f"cannot open {device.name}: {exc}") from exc
        return _SdStream(stream)


# ---- a fake backend for tests (§16.1) ----


class FakeStream:
    def __init__(self, backend: FakeAudioBackend, kind: str, device: AudioDevice) -> None:
        self._backend = backend
        self.kind = kind
        self.device = device
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self._backend.open_streams.remove(self)


class FakeAudioBackend:
    def __init__(self, devices: list[AudioDevice], *, native_only: set[str] | None = None) -> None:
        self.items = list(devices)
        self.refreshes = 0
        self.open_streams: list[FakeStream] = []
        self.input_callback: InputCallback | None = None
        self.output_callback: OutputCallback | None = None
        self.input_rate = 0
        self.native_only = native_only or set()  # devices that refuse Windows resampling
        self.fail: set[str] = set()

    def refresh(self) -> None:
        if self.open_streams:
            raise AudioDeviceError("refresh with a stream open")
        self.refreshes += 1

    def devices(self) -> list[AudioDevice]:
        return list(self.items)

    def open_input(
        self,
        device: AudioDevice,
        rate: int,
        blocksize: int,
        callback: InputCallback,
        *,
        convert: bool,
    ) -> Stream:
        if device.name in self.fail or (convert and device.name in self.native_only):
            raise AudioDeviceError(f"cannot open {device.name}")
        self.input_callback, self.input_rate = callback, rate
        stream = FakeStream(self, "input", device)
        self.open_streams.append(stream)
        return stream

    def open_output(
        self, device: AudioDevice, rate: int, blocksize: int, callback: OutputCallback
    ) -> Stream:
        if device.name in self.fail:
            raise AudioDeviceError(f"cannot open {device.name}")
        self.output_callback = callback
        stream = FakeStream(self, "output", device)
        self.open_streams.append(stream)
        return stream

    def feed(self, samples: Int16) -> None:
        """Deliver one captured block, as the audio thread would."""
        if self.input_callback is None:
            raise AudioDeviceError("no capture stream is open")
        self.input_callback(samples)

    def pull(self, frames: int) -> Float32:
        if self.output_callback is None:
            raise AudioDeviceError("no playback stream is open")
        return self.output_callback(frames)
