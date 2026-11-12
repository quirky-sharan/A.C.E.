"""Push-to-talk on fakes (S10): the mic opens only while held, the transcript reaches the pipeline,
unsure ones are flagged, empty / muted / broken cases get a plain answer."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast

import numpy as np
import pytest
from pydantic import JsonValue

from ace_core.app.events import EventBus
from ace_core.app.state import ConversationState, StateChanged, StateStore
from ace_core.brain.pipeline import CommandPipeline
from ace_core.brain.records import Origin
from ace_core.db.stores import Actor
from ace_core.voice import listen
from ace_core.voice.audio import AudioService
from ace_core.voice.devices import AudioDevice, FakeAudioBackend
from ace_core.voice.listen import TranscriptFinal, VoiceService
from ace_core.voice.stt import Transcript

MIC = AudioDevice(1, "Microphone Array", True, 48_000, True)
SPEAKERS = AudioDevice(3, "Speakers", False, 48_000, True)


class Settings:
    def __init__(self) -> None:
        self.values: dict[str, JsonValue] = {}

    async def get(self, key: str, default: JsonValue = None) -> JsonValue:
        return self.values.get(key, default)

    async def set(self, key: str, value: JsonValue, *, actor: Actor = "system") -> None:
        self.values[key] = value


class Pipeline:
    def __init__(self) -> None:
        self.submitted: list[tuple[str, Origin, bool]] = []
        self.notices: list[str] = []

    async def submit(self, text: str, *, origin: Origin, unsure: bool = False) -> None:
        self.submitted.append((text, origin, unsure))

    async def notice(self, spoken: str, detail: str | None = None, *, origin: Origin) -> None:
        self.notices.append(spoken)


class FakeTranscriber:
    def __init__(self, text: str, logprob: float = -0.1) -> None:
        self.text, self.logprob = text, logprob
        self.calls: list[tuple[int, str | None]] = []
        self.warmed = 0

    @property
    def name(self) -> str:
        return "fake"

    def transcribe(self, audio: Any, prompt: str | None = None) -> Transcript:
        self.calls.append((len(audio), prompt))
        return Transcript(self.text, "en", self.logprob, 0.01, len(audio) // 16, 120)

    def keep_warm(self) -> None:
        self.warmed += 1


class Env:
    def __init__(self, transcriber: FakeTranscriber) -> None:
        self.backend = FakeAudioBackend([MIC, SPEAKERS])
        self.bus = EventBus()
        self.state = StateStore(self.bus)
        self.settings = Settings()
        self.pipeline = Pipeline()
        self.audio = AudioService(
            self.backend, bus=self.bus, state=self.state, settings=self.settings
        )
        self.loads: list[tuple[str, str | None]] = []
        self.gpu = True

        def factory(model: str, language: str | None) -> FakeTranscriber:
            self.loads.append((model, language))
            return transcriber

        self.voice = VoiceService(
            self.audio,
            cast(CommandPipeline, self.pipeline),
            state=self.state,
            bus=self.bus,
            settings=self.settings,
            factory=factory,
            names=lambda: ["Discord"],
            gpu=lambda: self.gpu,
        )
        self.states: list[ConversationState] = []
        self.finals: list[TranscriptFinal] = []

        async def on_state(event: StateChanged) -> None:
            self.states.append(event.state.conversation)

        async def on_final(event: TranscriptFinal) -> None:
            self.finals.append(event)

        self.bus.subscribe(StateChanged, on_state)
        self.bus.subscribe(TranscriptFinal, on_final)

    async def say(self, seconds: float = 1.0) -> None:
        await self.voice.ptt_pressed()
        for _ in range(int(seconds / 0.08)):
            self.backend.feed(np.full(1280, 4000, dtype=np.int16))
        await self.voice.ptt_released()


@pytest.fixture(autouse=True)
def _no_vad(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(listen, "trim_silence", lambda audio: audio)  # fakes are not speech


@pytest.fixture
async def make() -> AsyncIterator[Any]:
    envs: list[Env] = []

    def build(text: str = "open spotify", logprob: float = -0.1) -> Env:
        env = Env(FakeTranscriber(text, logprob))
        envs.append(env)
        return env

    yield build
    for env in envs:
        await env.voice.close()
        await env.audio.close()


async def test_push_to_talk_sends_the_transcript_to_the_pipeline(make: Any) -> None:
    env = make()
    await env.voice.ptt_pressed()
    assert env.audio.capturing and env.voice.listening  # the mic is open only while held
    assert env.state.current.conversation is ConversationState.LISTENING
    for _ in range(12):
        env.backend.feed(np.full(1280, 4000, dtype=np.int16))
    await env.voice.ptt_released()
    assert not env.audio.capturing
    assert env.pipeline.submitted == [("open spotify", Origin.VOICE, False)]
    assert env.states[:3] == [
        ConversationState.LISTENING,
        ConversationState.TRANSCRIBING,
        ConversationState.ASLEEP,
    ]
    assert env.finals[0].verdict == "ok"
    assert env.loads == [("stt-turbo", "en")]  # the S10 benchmark default (PL-0012)
    transcriber = await env.voice.transcriber()
    assert transcriber.calls[0][1] == f"Discord. {listen.PROMPT_EXAMPLES}"


async def test_unsure_transcripts_are_flagged_and_settings_choose_the_model(make: Any) -> None:
    env = make(text="spotify kholo", logprob=-1.2)
    env.settings.values[listen.MODEL_SETTING] = "stt-hinglish-swift"
    env.settings.values[listen.LANGUAGE_SETTING] = "auto"
    await env.say()
    assert env.pipeline.submitted == [("spotify kholo", Origin.VOICE, True)]
    assert env.loads == [("stt-hinglish-swift", None)]  # "auto" = detect the language


async def test_silence_or_a_phantom_phrase_is_not_a_command(make: Any) -> None:
    env = make(text="Thank you for watching!")
    await env.say()
    assert env.pipeline.submitted == []
    assert env.pipeline.notices == ["I didn't catch that."]
    assert env.finals[0].verdict == "empty"
    short = make()
    await short.voice.ptt_pressed()
    await short.voice.ptt_released()  # released at once: nothing was said
    assert short.pipeline.notices == ["I didn't catch that."]
    assert short.loads == []  # no model needed for nothing


async def test_a_muted_mic_or_a_broken_model_is_explained(make: Any) -> None:
    env = make()
    await env.audio.set_muted(True)
    await env.voice.ptt_pressed()
    assert not env.voice.listening
    assert env.pipeline.notices == ["The microphone is muted."]

    broken = make()

    def fail(model: str, language: str | None) -> FakeTranscriber:
        raise FileNotFoundError("the speech model stt-turbo is not downloaded")

    broken.voice._factory = fail
    await broken.say()
    assert broken.pipeline.notices == ["Speech recognition failed."]
    assert broken.state.current.conversation is ConversationState.ASLEEP


async def test_preloading_happens_in_the_background(make: Any) -> None:
    env = make()
    env.voice.start()
    await asyncio.sleep(0.05)
    assert env.loads == [("stt-turbo", "en")]
    await env.say()
    assert env.loads == [("stt-turbo", "en")]  # loaded once


def test_the_prompt_puts_names_before_the_examples() -> None:
    examples = listen.PROMPT_EXAMPLES
    assert listen.command_prompt([]) == examples
    # repeats, blanks and names the examples already contain drop out
    assert listen.command_prompt(["ACE", " Discord ", "ACE", "", "spotify"]) == (
        f"ACE, Discord. {examples}"
    )
    names = [f"App{n:03d}" for n in range(200)]
    long = listen.command_prompt(names)
    assert len(long) <= listen.PROMPT_MAX and long.endswith(examples)  # the examples stay whole
    assert long.split(". ")[0].split(", ")[-1] in names  # whole names only


async def test_without_a_gpu_the_cpu_model_is_used_unless_one_is_chosen(make: Any) -> None:
    env = make()
    env.gpu = False
    await env.say()
    assert env.loads == [(listen.CPU_MODEL, "en")]  # turbo would take ~10 s per command
    env.settings.values[listen.MODEL_SETTING] = "stt-small"
    await env.say()
    assert env.loads[-1] == ("stt-small", "en")


async def test_the_model_is_kept_warm_only_while_the_key_is_held(
    make: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(listen, "KEEP_WARM_S", 0.01)
    env = make()
    transcriber = await env.voice.transcriber()
    await env.voice.ptt_pressed()
    await asyncio.sleep(0.1)
    assert transcriber.warmed >= 2  # the GPU stays awake while Sharan speaks
    env.backend.feed(np.full(16_000, 4000, dtype=np.int16))
    await env.voice.ptt_released()
    warmed = transcriber.warmed
    await asyncio.sleep(0.05)
    assert transcriber.warmed == warmed  # and stops with the key
    assert env.pipeline.submitted == [("open spotify", Origin.VOICE, False)]


async def test_a_key_press_during_the_preload_loads_the_model_once(make: Any) -> None:
    env = make()
    env.voice.start()  # preload running
    await env.say()
    await asyncio.sleep(0.05)
    assert env.loads == [("stt-turbo", "en")]
