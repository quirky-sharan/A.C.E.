"""Speech to text (ACE_MASTER_PLAN.md §7.3-§7.4, S10, D-01 / D-37).

- ``Transcriber`` interface: 16 kHz mono int16 in, text + confidence signals out.
- ``WhisperTranscriber``: faster-whisper (CTranslate2). GPU with ``int8_float16`` when CUDA works
  (NVIDIA's pip DLLs are made findable first), else CPU ``int8``. No internal VAD (we trim
  first), no conditioning on previous text, beam 5 on the GPU / greedy on the CPU (§7.4); the
  caller's prompt steers vocabulary and spelling.
- ``trim_silence``: Silero VAD (the ONNX model faster-whisper ships) cuts leading / trailing
  silence; nothing is sent anywhere — audio never leaves the PC (D-05).
- Guards (§7.4): no speech, known phantom phrases, repetition loops -> dropped; low confidence ->
  the pipeline asks "Did you say ...?".
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
import structlog

from ace_core.voice.dsp import CAPTURE_RATE, Int16, to_float32

log = structlog.stdlib.get_logger(__name__)

WARM_UP_S: Final = 1.0  # silence transcribed once at load time
NO_SPEECH_MAX: Final = 0.6  # with avg_logprob below LOGPROB_MIN: treat as no speech (§7.4)
LOGPROB_MIN: Final = -1.0
CONFIRM_BELOW: Final = 0.55  # confidence below this -> "Did you say ...?"
PHANTOMS: Final = (  # Whisper's known inventions on silence / noise (lower case, no punctuation)
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "subscribe to my channel",
    "like and subscribe",
    "see you in the next video",
    "subtitles by",
    "amara org",
    "thank you",
)
_WORDS = re.compile(r"[\w']+", re.UNICODE)


class Verdict(StrEnum):
    OK = "ok"
    UNSURE = "unsure"  # ask "Did you say ...?"
    EMPTY = "empty"  # nothing usable was said


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str | None
    avg_logprob: float  # mean over segments; 0 = certain, -1 = poor
    no_speech_prob: float
    duration_ms: int  # audio length
    elapsed_ms: int  # time spent transcribing
    segments: tuple[str, ...] = field(default=())

    @property
    def confidence(self) -> float:
        """0..1 from the decoder's average log probability."""
        return float(min(1.0, max(0.0, np.exp(self.avg_logprob))))


class Transcriber(Protocol):
    @property
    def name(self) -> str: ...

    def transcribe(self, audio: Int16, prompt: str | None = None) -> Transcript:
        """Blocking: call it from a worker thread, never the event loop or the audio callback.
        ``prompt``: text that steers spelling and vocabulary (Whisper's initial prompt)."""

    def keep_warm(self) -> None:
        """Blocking and cheap: keep the device ready for the next transcription while Sharan
        speaks (a GPU idles down within seconds); a no-op where that does not matter."""


def words(text: str) -> list[str]:
    return _WORDS.findall(text.casefold())


def _is_phantom(phrase: str, phantom: str) -> bool:
    """Short phantoms ("thank you") only as the whole result; long ones also as its start."""
    if phrase == phantom:
        return True
    return len(phantom.split()) >= 3 and phrase.startswith(phantom + " ")


def judge(transcript: Transcript) -> Verdict:
    """Hallucination guards and the confidence check (§7.4)."""
    said = words(transcript.text)
    if not said:
        return Verdict.EMPTY
    if transcript.no_speech_prob > NO_SPEECH_MAX and transcript.avg_logprob < LOGPROB_MIN:
        return Verdict.EMPTY
    phrase = " ".join(said)
    if any(_is_phantom(phrase, phantom) for phantom in PHANTOMS):
        return Verdict.EMPTY
    if len(said) >= 6 and len(set(said)) <= max(2, len(said) // 4):
        return Verdict.EMPTY  # a repetition loop ("the the the the ...")
    if transcript.confidence < CONFIRM_BELOW:
        return Verdict.UNSURE
    return Verdict.OK


# ---- VAD: trim silence before transcribing ----


def trim_silence(audio: Int16, *, pad_ms: int = 500) -> Int16:
    """Keep from the first to the last speech (Silero VAD), padded; empty when no speech.

    500 ms of padding (S10 tuning, PL-0012): with 200 ms the trim cut the start of words ("switch
    to chrome" -> "Stook Room"); Whisper pads every input to 30 s, so trimming saves no time."""
    from faster_whisper.vad import (  # type: ignore[import-untyped]
        VadOptions,
        get_speech_timestamps,
    )

    if len(audio) == 0:
        return audio
    options = VadOptions(
        threshold=0.5, min_speech_duration_ms=250, min_silence_duration_ms=700, speech_pad_ms=pad_ms
    )
    chunks = get_speech_timestamps(to_float32(audio), options, sampling_rate=CAPTURE_RATE)
    if not chunks:
        return audio[:0]
    return audio[int(chunks[0]["start"]) : int(chunks[-1]["end"])]


# ---- faster-whisper ----


def _register_cuda_dlls(root: Path | None = None) -> None:
    """Put the DLL folders of NVIDIA's pip wheels (site-packages/nvidia/*/bin) on PATH.

    CTranslate2 loads cuBLAS / cuDNN by name with the standard DLL search, which reads PATH; the
    faster-whisper README says to place the libraries "in a directory included in the PATH" on
    Windows. ``os.add_dll_directory`` is not enough: found at S10, "cublas64_12.dll is not found".
    Only this process (and its children) sees the change.
    """
    root = root or Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    if sys.platform != "win32" or not root.is_dir():
        return
    folders = [str(folder) for folder in sorted({path.parent for path in root.glob("*/bin/*.dll")})]
    current = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    missing = [folder for folder in folders if folder not in current]
    if missing:
        os.environ["PATH"] = os.pathsep.join([*missing, *current])


def cuda_available() -> bool:
    """Whether CTranslate2 sees a CUDA GPU (blocking: imports CTranslate2). Whether cuBLAS and
    cuDNN really load shows at a model's warm-up, which falls back to the CPU."""
    _register_cuda_dlls()
    import ctranslate2  # type: ignore[import-untyped]

    return bool(ctranslate2.get_cuda_device_count() > 0)


@dataclass(frozen=True, slots=True)
class WhisperOptions:
    language: str | None = None  # None = detect; "en" / "hi" force a language
    beam_size: int | None = None  # None = 5 on the GPU, 1 on the CPU
    cpu_threads: int = 4


class WhisperTranscriber:
    """One loaded faster-whisper model. Construction loads and warms it up (seconds), so do it off
    the loop. A GPU that fails on first use (cuBLAS / cuDNN not loadable, out of memory) falls
    back to the CPU instead of failing every command."""

    def __init__(
        self,
        model_dir: Path,
        *,
        label: str,
        device: str = "auto",
        options: WhisperOptions | None = None,
    ) -> None:
        _register_cuda_dlls()
        self._options = options or WhisperOptions()
        self._dir = model_dir
        self._label = label
        use_cuda = device == "cuda" or (device == "auto" and cuda_available())
        self.device, self.compute_type = ("cuda", "int8_float16") if use_cuda else ("cpu", "int8")
        self._model: Any = self._load()
        try:
            self._warm_up()
        except RuntimeError as exc:
            if self.device != "cuda":
                raise
            log.warning("speech recognition on the GPU failed, using the CPU", error=str(exc))
            self.device, self.compute_type = "cpu", "int8"
            self._model = self._load()
            self._warm_up()

    def _load(self) -> Any:
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]

        return WhisperModel(
            str(self._dir),
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self._options.cpu_threads,
            local_files_only=True,
        )

    def _warm_up(self) -> None:
        """The first transcription loads cuBLAS / cuDNN and picks kernels: pay that now, not on
        Sharan's first command."""
        self.transcribe(np.zeros(round(WARM_UP_S * CAPTURE_RATE), dtype=np.int16))

    def keep_warm(self) -> None:
        """After ~5 s idle the GPU's first transcription took ~560 ms instead of ~250 ms (S10,
        PL-0012): a silent one while Sharan speaks keeps it awake. The CPU needs none."""
        if self.device == "cuda":
            self._warm_up()

    @property
    def name(self) -> str:
        return f"{self._label} ({self.device}, {self.compute_type})"

    @property
    def beam_size(self) -> int:
        """Beam 5 costs ~5 ms on the GPU and helped Hinglish (S10); the CPU stays greedy."""
        if self._options.beam_size is not None:
            return self._options.beam_size
        return 5 if self.device == "cuda" else 1

    def transcribe(self, audio: Int16, prompt: str | None = None) -> Transcript:
        started = time.perf_counter()
        segments, info = self._model.transcribe(
            to_float32(audio),
            language=self._options.language,
            beam_size=self.beam_size,
            temperature=0.0,  # no fallback re-decoding: latency first (§7.4)
            condition_on_previous_text=False,
            initial_prompt=prompt or None,
            vad_filter=False,  # we already trimmed
            without_timestamps=True,
        )
        parts = list(segments)  # decoding happens while iterating
        elapsed = time.perf_counter() - started
        texts = tuple(segment.text.strip() for segment in parts)
        logprob = float(np.mean([s.avg_logprob for s in parts])) if parts else -10.0
        no_speech = float(max((s.no_speech_prob for s in parts), default=1.0))
        return Transcript(
            text=" ".join(t for t in texts if t).strip(),
            language=info.language,
            avg_logprob=logprob,
            no_speech_prob=no_speech,
            duration_ms=round(len(audio) / CAPTURE_RATE * 1000),
            elapsed_ms=round(elapsed * 1000),
            segments=texts,
        )
