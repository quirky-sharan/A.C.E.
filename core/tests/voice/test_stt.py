"""STT guards, silence trimming, DLL path, beam size and GPU fallback (S10), no real model."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import numpy as np
import pytest

from ace_core.voice import stt
from ace_core.voice.stt import Transcript, Verdict, judge, trim_silence, words


def transcript(text: str, *, logprob: float = -0.2, no_speech: float = 0.05) -> Transcript:
    return Transcript(
        text=text,
        language="en",
        avg_logprob=logprob,
        no_speech_prob=no_speech,
        duration_ms=1500,
        elapsed_ms=200,
    )


@pytest.mark.parametrize(
    ("text", "logprob", "no_speech", "verdict"),
    [
        ("open spotify", -0.2, 0.05, Verdict.OK),
        ("spotify kholo", -0.9, 0.05, Verdict.UNSURE),  # confidence exp(-0.9) = 0.41
        ("", -0.2, 0.05, Verdict.EMPTY),
        ("   ...  ", -0.2, 0.05, Verdict.EMPTY),
        ("open spotify", -1.4, 0.8, Verdict.EMPTY),  # probably silence
        ("Thank you for watching!", -0.3, 0.1, Verdict.EMPTY),  # a phantom phrase
        ("Thank you.", -0.3, 0.1, Verdict.EMPTY),
        ("the the the the the the the the", -0.3, 0.1, Verdict.EMPTY),  # a repetition loop
        ("thank you rahul for the help", -0.2, 0.05, Verdict.OK),
    ],
)
def test_judging_transcripts(text: str, logprob: float, no_speech: float, verdict: Verdict) -> None:
    assert judge(transcript(text, logprob=logprob, no_speech=no_speech)) is verdict


def test_confidence_and_words() -> None:
    assert transcript("x", logprob=0.0).confidence == 1.0
    assert transcript("x", logprob=-50.0).confidence == pytest.approx(0.0)
    assert words("Spotify kholo, ACE!") == ["spotify", "kholo", "ace"]


def test_silence_is_trimmed_to_nothing() -> None:
    silence = np.zeros(16_000, dtype=np.int16)
    assert len(trim_silence(silence)) == 0
    assert len(trim_silence(np.zeros(0, dtype=np.int16))) == 0


def test_speech_is_kept_from_the_first_to_the_last_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real speech goes through the VAD in the benchmark and live; here its chunks are faked."""
    pads: list[int] = []

    def chunks(audio: Any, options: Any, sampling_rate: int) -> list[dict[str, int]]:
        pads.append(options.speech_pad_ms)  # the VAD pads the chunks itself
        return [{"start": 4_000, "end": 9_000}, {"start": 20_000, "end": 26_000}]

    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", chunks)
    kept = trim_silence(np.arange(32_000, dtype=np.int16))
    assert (kept[0], kept[-1]) == (4_000, 25_999)  # the pause between the chunks stays
    assert pads == [500]  # S10 tuning: 200 ms cut the start of words


def test_nvidia_dll_folders_go_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("cublas", "cudnn"):
        (tmp_path / name / "bin").mkdir(parents=True)
        (tmp_path / name / "bin" / f"{name}64_x.dll").write_bytes(b"")
    (tmp_path / "cuda_nvrtc" / "include").mkdir(parents=True)  # no DLLs: not added
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PATH", r"C:\Windows")
    stt._register_cuda_dlls(tmp_path)
    stt._register_cuda_dlls(tmp_path)  # a second model load adds nothing
    assert os.environ["PATH"].split(os.pathsep) == [
        str(tmp_path / "cublas" / "bin"),
        str(tmp_path / "cudnn" / "bin"),
        r"C:\Windows",
    ]


class FakeWhisper:
    """faster_whisper.WhisperModel stand-in whose GPU cannot load cuBLAS."""

    loads: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, path: str, *, device: str, compute_type: str, **_: object) -> None:
        self.device = device
        self.transcribed = 0
        FakeWhisper.loads.append((device, compute_type))

    def transcribe(self, audio: object, **_: object) -> tuple[Iterator[object], object]:
        if self.device == "cuda":
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
        self.transcribed += 1
        return iter([]), SimpleNamespace(language="en")


def test_a_gpu_that_fails_on_first_use_falls_back_to_the_cpu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import faster_whisper  # type: ignore[import-untyped]

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeWhisper)
    monkeypatch.setattr(stt, "_register_cuda_dlls", lambda root=None: None)  # keep PATH as is
    monkeypatch.setattr(FakeWhisper, "loads", [])
    model = stt.WhisperTranscriber(tmp_path, label="stt-test", device="cuda")
    assert (model.device, model.compute_type) == ("cpu", "int8")
    assert FakeWhisper.loads == [("cuda", "int8_float16"), ("cpu", "int8")]  # warmed up on load
    assert model.name == "stt-test (cpu, int8)"
    assert model.beam_size == 1  # greedy on the CPU (5 on the GPU)
    assert model.transcribe(np.zeros(1600, dtype=np.int16)).text == ""
    done = model._model.transcribed
    model.keep_warm()  # only a GPU idles down
    assert model._model.transcribed == done
