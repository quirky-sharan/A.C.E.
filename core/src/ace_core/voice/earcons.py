"""Earcons: short sounds made with numpy (no audio files). The wake chime is used from S12; the
final set is chosen with the voice at S11."""

from __future__ import annotations

from typing import Final

import numpy as np

from ace_core.voice.dsp import Float32

EARCON_RATE: Final = 48_000
VOLUME: Final = 0.25
FADE_S: Final = 0.008

# name -> (frequency Hz, seconds) notes played one after another
EARCONS: Final[dict[str, tuple[tuple[float, float], ...]]] = {
    "wake": ((880.0, 0.07), (1318.5, 0.09)),
    "done": ((1318.5, 0.06), (1760.0, 0.08)),
    "error": ((440.0, 0.12), (329.6, 0.16)),
    "mute": ((659.3, 0.06), (440.0, 0.10)),
    "unmute": ((440.0, 0.06), (659.3, 0.10)),
    "test": ((523.25, 0.12), (659.25, 0.12), (783.99, 0.18)),
}


def _note(frequency: float, seconds: float) -> Float32:
    count = int(EARCON_RATE * seconds)
    t = np.arange(count, dtype=np.float32) / EARCON_RATE
    wave = np.sin(2 * np.pi * frequency * t).astype(np.float32)
    fade = min(int(EARCON_RATE * FADE_S), count // 2)
    if fade:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        wave[:fade] *= ramp
        wave[-fade:] *= ramp[::-1]
    return (wave * VOLUME).astype(np.float32)


def render(name: str) -> Float32:
    """The earcon as mono float32 samples at ``EARCON_RATE``."""
    notes = EARCONS.get(name)
    if notes is None:
        raise KeyError(f"unknown earcon: {name}")
    return np.concatenate([_note(frequency, seconds) for frequency, seconds in notes])
