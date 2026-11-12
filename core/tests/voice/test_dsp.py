"""Ring buffer, resampler, levels and earcons (S09 tests)."""

from __future__ import annotations

import numpy as np
import pytest

from ace_core.voice.devices import AudioDevice, pick
from ace_core.voice.dsp import (
    Resampler,
    RingBuffer,
    peak,
    rms_level,
    to_float32,
    to_int16,
)
from ace_core.voice.earcons import EARCON_RATE, EARCONS, render


def ramp(start: int, count: int) -> np.ndarray:
    return np.arange(start, start + count, dtype=np.int16)


def test_the_ring_buffer_keeps_the_newest_samples() -> None:
    ring = RingBuffer(10)
    assert len(ring.latest(5)) == 0
    ring.write(ramp(0, 4))
    assert ring.latest(10).tolist() == [0, 1, 2, 3]
    ring.write(ramp(4, 9))  # wraps around
    assert ring.written == 13
    assert ring.latest(10).tolist() == list(range(3, 13))
    assert ring.latest(3).tolist() == [10, 11, 12]
    ring.write(ramp(100, 25))  # more than the capacity at once
    assert ring.latest(10).tolist() == list(range(115, 125))
    assert ring.written == 38
    ring.clear()
    assert len(ring.latest(10)) == 0
    with pytest.raises(ValueError, match="positive"):
        RingBuffer(0)


@pytest.mark.parametrize(
    ("source", "target"), [(48_000, 16_000), (44_100, 16_000), (16_000, 48_000)]
)
def test_the_resampler_keeps_time_and_pitch_across_blocks(source: int, target: int) -> None:
    seconds, frequency = 1.0, 440.0
    t = np.arange(int(source * seconds)) / source
    signal = to_int16((0.5 * np.sin(2 * np.pi * frequency * t)).astype(np.float32))
    resampler = Resampler(source, target)
    blocks = [resampler.process(chunk) for chunk in np.array_split(signal, 37)]
    out = np.concatenate(blocks)
    assert abs(len(out) - target * seconds) <= 2  # no samples lost or invented at the seams
    spectrum = np.abs(np.fft.rfft(out.astype(np.float64)))
    strongest = np.argmax(spectrum) * target / len(out)
    assert abs(strongest - frequency) < 3  # the tone keeps its pitch
    assert Resampler(16_000, 16_000).process(signal[:100]).tolist() == signal[:100].tolist()
    with pytest.raises(ValueError, match="positive"):
        Resampler(0, 16_000)


def test_levels_and_conversions() -> None:
    silence = np.zeros(1600, dtype=np.int16)
    loud = np.full(1600, 32000, dtype=np.int16)
    assert rms_level(silence) == 0.0
    assert rms_level(np.zeros(0, dtype=np.int16)) == 0.0
    assert rms_level(loud) > 0.99
    assert 0.0 < rms_level(loud // 100) < 0.5
    assert peak(loud) == pytest.approx(32000 / 32768)
    assert to_int16(np.array([2.0, -2.0, 0.5], dtype=np.float32)).tolist() == [32767, -32767, 16383]
    assert to_float32(np.array([16384], dtype=np.int16))[0] == pytest.approx(0.5)


def test_earcons_are_short_quiet_and_click_free() -> None:
    for name in EARCONS:
        sound = render(name)
        assert sound.dtype == np.float32
        assert 0.05 < len(sound) / EARCON_RATE < 0.6
        assert np.max(np.abs(sound)) <= 0.25 + 1e-6
        assert abs(sound[0]) < 0.01 and abs(sound[-1]) < 0.01  # fades in and out
    with pytest.raises(KeyError):
        render("nope")


def test_devices_are_picked_by_name_then_default() -> None:
    devices = [
        AudioDevice(1, "Microphone Array (Realtek(R) Audio)", True, 48_000, True),
        AudioDevice(2, "Headset (WH-1000XM4)", True, 16_000, False),
        AudioDevice(3, "Speakers (Realtek(R) Audio)", False, 48_000, True),
    ]
    assert pick(devices, "Headset (WH-1000XM4)", is_input=True) == devices[1]
    assert pick(devices, "headset (wh-1000xm4)", is_input=True) == devices[1]
    assert pick(devices, "Gone (unplugged)", is_input=True) == devices[0]  # falls back
    assert pick(devices, None, is_input=False) == devices[2]
    assert pick([], None, is_input=True) is None
