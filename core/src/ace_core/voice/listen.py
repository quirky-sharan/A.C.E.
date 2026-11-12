"""Push-to-talk (S10 task 3, §5.3 steps 3-5): hold the hotkey (D-29 Ctrl+Alt+A), speak, release.
The microphone is open only while the key is held (D-58); the audio is trimmed by the VAD,
transcribed locally (audio never leaves the PC, D-05) and handed to the command pipeline as a
voice command. Unsure transcripts are double-checked ("Did you say ...?"); empty ones get
"I didn't catch that"."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Final, TypeVar

import numpy as np
import structlog

from ace_core.app.events import Event, EventBus
from ace_core.app.state import ConversationState, StateStore
from ace_core.brain.pipeline import CommandPipeline
from ace_core.brain.records import Origin
from ace_core.skills.base import SettingsAccess
from ace_core.voice.audio import AudioService
from ace_core.voice.devices import AudioDeviceError
from ace_core.voice.dsp import CAPTURE_RATE, Int16
from ace_core.voice.stt import Transcriber, Verdict, cuda_available, judge, trim_silence

log = structlog.stdlib.get_logger(__name__)
T = TypeVar("T")

MODEL_SETTING: Final = "voice.stt_model"  # a models.lock.json name; unset = by hardware
LANGUAGE_SETTING: Final = "voice.stt_language"  # "en" / "hi" / "auto" (= detect)
DEFAULT_MODEL: Final = "stt-turbo"  # with a CUDA GPU: D-37, confirmed by the S10 benchmark
# Without one: turbo takes ~10 s per command on the CPU; Hinglish-Swift ~0.7 s (S10, PL-0012).
CPU_MODEL: Final = "stt-hinglish-swift"
# "en" = Roman script for English and Hinglish alike: on Sharan's recordings detection wrote Hindi
# in Devanagari (which the commands can't read) and cost a second encoder pass (S10, PL-0012).
DEFAULT_LANGUAGE: Final = "en"
MIN_SPEECH_S: Final = 0.3
KEEP_WARM_S: Final = 1.0  # while the key is held: a silent GPU transcription every second
PURPOSE: Final = "push-to-talk"
# Whisper's initial prompt (§7.4, tuned at S10, PL-0012): short example commands in ACE's own
# vocabulary steer it to ACE's words and to romanized Hinglish far better than a word list did.
# They are deliberately not the benchmark phrases. The names of Sharan's apps go before them
# ("ACE" itself is left out: commands don't contain it, and it cost "switch to chrome" at S10).
PROMPT_EXAMPLES: Final = (  # the English sentence last: nearest the speech, English held up best
    "YouTube kholo. WhatsApp band karo. Spotify pe jao. Notepad ko right karo. "
    "Music chalao, timer lagao. Open Chrome, close Spotify, switch to VS Code."
)
PROMPT_MAX: Final = 600  # characters; Whisper keeps only the last ~223 tokens of a prompt


def command_prompt(names: Sequence[str]) -> str:
    """Names not already in the examples, then the examples (kept last, so never cut off)."""
    examples = PROMPT_EXAMPLES.casefold()
    extra = [
        name
        for name in dict.fromkeys(n.strip() for n in names)
        if name and name.casefold() not in examples
    ]
    budget = PROMPT_MAX - len(PROMPT_EXAMPLES) - 2
    head = ", ".join(extra)
    if len(head) > budget:
        head = head[:budget].rsplit(", ", 1)[0]  # whole names only
    return f"{head}. {PROMPT_EXAMPLES}" if head else PROMPT_EXAMPLES


TranscriberFactory = Callable[[str, str | None], Transcriber]  # (model, language) -> loaded


@dataclass(frozen=True, slots=True, kw_only=True)
class TranscriptFinal(Event):
    text: str
    confidence: float
    language: str | None
    verdict: str  # ok / unsure / empty
    elapsed_ms: int


class VoiceService:
    def __init__(
        self,
        audio: AudioService,
        pipeline: CommandPipeline,
        *,
        state: StateStore,
        bus: EventBus,
        settings: SettingsAccess,
        factory: TranscriberFactory,
        names: Callable[[], Sequence[str]] = lambda: (),  # app names for the prompt
        gpu: Callable[[], bool] = cuda_available,
    ) -> None:
        self._audio = audio
        self._pipeline = pipeline
        self._state = state
        self._bus = bus
        self._settings = settings
        self._factory = factory
        self._names = names
        self._gpu = gpu
        self._has_gpu: bool | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ace-stt")
        self._transcriber: Transcriber | None = None
        self._loaded: tuple[str, str | None] | None = None
        self._load_lock = asyncio.Lock()  # a key press during the preload must not load twice
        self._listening = False
        self._preload: asyncio.Task[None] | None = None
        self._warm: asyncio.Task[None] | None = None

    async def _run(self, fn: Callable[..., T], *args: Any) -> T:
        return await asyncio.get_running_loop().run_in_executor(self._executor, lambda: fn(*args))

    async def _choice(self) -> tuple[str, str | None]:
        model = await self._settings.get(MODEL_SETTING)
        language = await self._settings.get(LANGUAGE_SETTING)
        language = language if isinstance(language, str) and language else DEFAULT_LANGUAGE
        if not (isinstance(model, str) and model):
            if self._has_gpu is None:
                self._has_gpu = await self._run(self._gpu)
            model = DEFAULT_MODEL if self._has_gpu else CPU_MODEL
        return model, None if language == "auto" else language

    async def transcriber(self) -> Transcriber:
        """The chosen model, loaded once (and again when the choice changes)."""
        async with self._load_lock:
            wanted = await self._choice()
            if self._transcriber is None or self._loaded != wanted:
                self._transcriber = await self._run(self._factory, *wanted)
                self._loaded = wanted
                log.info("speech model loaded", model=self._transcriber.name)
            return self._transcriber

    def start(self) -> None:
        """Load the model (and the VAD, ~240 ms on first use) in the background so the first
        push-to-talk is quick."""

        async def preload() -> None:
            try:
                await self.transcriber()
                await self._run(trim_silence, np.zeros(CAPTURE_RATE, dtype=np.int16))
            except Exception as exc:
                log.warning("speech model not loaded", error=str(exc))

        self._preload = asyncio.create_task(preload(), name="ace-stt-preload")

    async def close(self) -> None:
        for task in (self._preload, self._warm):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        if self._listening:
            self._listening = False
            await self._audio.end_take(PURPOSE)
        await asyncio.to_thread(self._executor.shutdown, True)

    @property
    def listening(self) -> bool:
        return self._listening

    async def ptt_pressed(self) -> None:
        if self._listening:
            return
        if self._audio.muted:
            await self._pipeline.notice(
                "The microphone is muted.", "Unmute it with Ctrl+Alt+Shift+M.", origin=Origin.VOICE
            )
            return
        try:
            await self._audio.begin_take(PURPOSE)
        except AudioDeviceError as exc:
            await self._pipeline.notice(
                "I can't open the microphone.", str(exc), origin=Origin.VOICE
            )
            return
        self._listening = True
        await self._state.update(conversation=ConversationState.LISTENING)
        self._warm = asyncio.create_task(self._keep_warm(), name="ace-stt-warm")

    async def _keep_warm(self) -> None:
        """While Sharan speaks, keep the model's device awake (see ``Transcriber.keep_warm``)."""
        try:
            transcriber = await self.transcriber()
            while self._listening:
                await self._run(transcriber.keep_warm)
                await asyncio.sleep(KEEP_WARM_S)
        except Exception as exc:
            log.warning("speech model not kept warm", error=str(exc))

    async def ptt_released(self) -> None:
        if not self._listening:
            return
        self._listening = False
        if self._warm is not None:
            self._warm.cancel()  # a warm-up already running finishes first (same worker thread)
        samples = await self._audio.end_take(PURPOSE)
        await self._state.update(conversation=ConversationState.TRANSCRIBING)
        try:
            await self._handle(samples)
        except Exception as exc:
            log.exception("speech recognition failed")
            await self._state.update(conversation=ConversationState.ASLEEP)
            await self._pipeline.notice(
                "Speech recognition failed.", str(exc)[:200], origin=Origin.VOICE
            )

    async def _handle(self, samples: Int16) -> None:
        speech = await self._run(trim_silence, samples)
        if len(speech) < MIN_SPEECH_S * CAPTURE_RATE:
            await self._finish(
                TranscriptFinal(
                    text="",
                    confidence=0.0,
                    language=None,
                    verdict=Verdict.EMPTY.value,
                    elapsed_ms=0,
                )
            )
            return
        transcriber = await self.transcriber()
        prompt = command_prompt(self._names())
        transcript = await self._run(transcriber.transcribe, speech, prompt)
        verdict = judge(transcript)
        log.info(
            "transcribed",
            verdict=verdict.value,
            confidence=round(transcript.confidence, 2),
            language=transcript.language,
            audio_ms=transcript.duration_ms,
            elapsed_ms=transcript.elapsed_ms,
        )
        event = TranscriptFinal(
            text=transcript.text if verdict is not Verdict.EMPTY else "",
            confidence=round(transcript.confidence, 3),
            language=transcript.language,
            verdict=verdict.value,
            elapsed_ms=transcript.elapsed_ms,
        )
        await self._finish(event)
        if verdict is not Verdict.EMPTY:
            await self._pipeline.submit(
                transcript.text, origin=Origin.VOICE, unsure=verdict is Verdict.UNSURE
            )

    async def _finish(self, event: TranscriptFinal) -> None:
        await self._bus.publish(event)
        await self._state.update(conversation=ConversationState.ASLEEP)  # the pipeline takes over
        if event.verdict == Verdict.EMPTY.value:
            await self._pipeline.notice(
                "I didn't catch that.", "Hold Ctrl+Alt+A while you speak.", origin=Origin.VOICE
            )
