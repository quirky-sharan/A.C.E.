"""Small signal helpers for audio I/O (S09): the 2 s pre-roll ring buffer, a streaming resampler
for devices that cannot deliver 16 kHz, levels and format conversion. Pure numpy, no audio device.

The ring buffer is written from the audio callback thread and read from the event loop; the lock
is held only for a copy of at most a few kilobytes, so the callback never waits noticeably.
"""

from __future__ import annotations

import math
import threading
from typing import Final

import numpy as np
import numpy.typing as npt

Int16 = npt.NDArray[np.int16]
Float32 = npt.NDArray[np.float32]

CAPTURE_RATE: Final = 16_000  # Hz, mono int16 (§7.1)
PRE_ROLL_S: Final = 2.0


class RingBuffer:
    """The last ``capacity`` samples, plus a running count of everything ever written."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._data = np.zeros(capacity, dtype=np.int16)
        self._written = 0  # total samples ever written
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return len(self._data)

    @property
    def written(self) -> int:
        return self._written

    def write(self, samples: Int16) -> None:
        total = len(samples)
        if total == 0:
            return
        capacity = len(self._data)
        tail = samples[-capacity:] if total > capacity else samples  # older ones would be lost
        count = len(tail)
        with self._lock:
            start = (self._written + total - count) % capacity
            first = min(count, capacity - start)
            self._data[start : start + first] = tail[:first]
            if first < count:
                self._data[: count - first] = tail[first:]
            self._written += total

    def latest(self, count: int) -> Int16:
        """The newest ``count`` samples (fewer if not that many were written yet)."""
        with self._lock:
            available = min(count, self._written, len(self._data))
            end = self._written % len(self._data)
            start = end - available
            if start >= 0:
                return self._data[start:end].copy()
            return np.concatenate((self._data[start:], self._data[:end]))

    def clear(self) -> None:
        with self._lock:
            self._written = 0


def to_int16(samples: Float32) -> Int16:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)


def to_float32(samples: Int16) -> Float32:
    return (samples.astype(np.float32) / 32768.0).astype(np.float32)


def rms_level(samples: Int16) -> float:
    """Loudness 0..1 on a dB scale (-60 dBFS -> 0, 0 dBFS -> 1) for meters."""
    if len(samples) == 0:
        return 0.0
    mean_square = float(np.mean(np.square(samples.astype(np.float64)))) / (32768.0**2)
    if mean_square <= 0.0:
        return 0.0
    db = 10.0 * math.log10(mean_square)
    return max(0.0, min(1.0, (db + 60.0) / 60.0))


def peak(samples: Int16) -> float:
    return 0.0 if len(samples) == 0 else float(np.max(np.abs(samples.astype(np.int32)))) / 32768.0


class Resampler:
    """Streaming mono resampler (linear interpolation, with a moving-average anti-alias filter
    when downsampling). Keeps state between blocks so the output has no seams."""

    def __init__(self, source_rate: int, target_rate: int) -> None:
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("rates must be positive")
        self.source_rate = source_rate
        self.target_rate = target_rate
        self._step = source_rate / target_rate  # input samples per output sample
        self._position = 0.0  # next output position, relative to the start of _carry
        self._carry = np.zeros(0, dtype=np.float64)
        taps = max(1, round(self._step)) if source_rate > target_rate else 1
        self._kernel = np.full(taps, 1.0 / taps) if taps > 1 else None
        self._history = np.zeros(taps - 1, dtype=np.float64)

    def process(self, block: Int16) -> Int16:
        if self.source_rate == self.target_rate:
            return block.copy()
        data = block.astype(np.float64)
        if self._kernel is not None:
            padded = np.concatenate((self._history, data))
            self._history = (
                padded[len(padded) - len(self._history) :] if len(self._history) else self._history
            )
            data = np.convolve(padded, self._kernel, mode="valid")
        signal = np.concatenate((self._carry, data))
        if len(signal) < 2:
            self._carry = signal
            return np.zeros(0, dtype=np.int16)
        last = len(signal) - 1
        count = (
            math.floor((last - self._position) / self._step) + 1 if self._position <= last else 0
        )
        positions = self._position + self._step * np.arange(count)
        out = np.interp(positions, np.arange(len(signal)), signal)
        next_position = self._position + self._step * count
        keep_from = math.floor(next_position) - 1
        keep_from = max(0, min(keep_from, last))
        self._carry = signal[keep_from:]
        self._position = next_position - keep_from
        result: Int16 = np.clip(np.round(out), -32768, 32767).astype(np.int16)
        return result
