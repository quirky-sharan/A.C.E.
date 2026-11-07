"""Shared by the brain tests: an in-memory settings store, test skills and an event recorder."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import JsonValue

from ace_core.app.events import Event, EventBus
from ace_core.app.state import StateStore
from ace_core.brain.pipeline import CommandPipeline
from ace_core.brain.records import Origin, Step, Task
from ace_core.brain.supervisor import Supervisor
from ace_core.db.history import HistoryStore
from ace_core.db.ids import new_id
from ace_core.db.stores import Actor, AuditLog, SettingsStore
from ace_core.security.tiers import Tier
from ace_core.skills.base import (
    NoParams,
    RuleCheckResult,
    Skill,
    SkillContext,
    StepResult,
)


class MemorySettings:
    """Satisfies ``SettingsAccess`` without a database."""

    def __init__(self) -> None:
        self.values: dict[str, JsonValue] = {}

    async def get(self, key: str, default: JsonValue = None) -> JsonValue:
        return self.values.get(key, default)

    async def set(self, key: str, value: JsonValue, *, actor: Actor = "system") -> None:
        self.values[key] = value


@dataclass
class EventRecorder:
    """Records every bus event and lets a test wait for one that matches."""

    events: list[Event] = field(default_factory=list)
    _changed: asyncio.Event = field(default_factory=asyncio.Event)

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(Event, self._record)

    async def _record(self, event: Event) -> None:
        self.events.append(event)
        self._changed.set()

    def of_type[E: Event](self, kind: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, kind)]

    async def wait_for[E: Event](
        self, kind: type[E], predicate: Callable[[E], bool] = lambda _: True, timeout: float = 3.0
    ) -> E:
        async with asyncio.timeout(timeout):
            while True:
                for event in self.events:
                    if isinstance(event, kind) and predicate(event):
                        return event
                self._changed.clear()
                await self._changed.wait()


class ConfigurableSkill(Skill[NoParams]):
    """A T0 / T1 / T2 test skill whose behaviour each test chooses."""

    params_model = NoParams
    examples = ()

    def __init__(
        self,
        skill_id: str,
        *,
        tier: Tier = Tier.T0,
        delay_s: float = 0.0,
        timeout_s: float = 2.0,
        verify_ok: bool = True,
        unmet: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.id = skill_id
        self.description = f"test skill {skill_id}"
        self.timeout_s = timeout_s
        self._tier = tier
        self._delay_s = delay_s
        self._verify_ok = verify_ok
        self._unmet = unmet or []
        self._error = error
        self.calls = 0

    def tier_for(self, params: NoParams) -> Tier:
        return self._tier

    async def preconditions(self, ctx: SkillContext, params: NoParams) -> list[str]:
        return list(self._unmet)

    async def execute(self, ctx: SkillContext, params: NoParams) -> StepResult:
        self.calls += 1
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        if self._error is not None:
            raise self._error
        return StepResult(spoken=f"{self.id} done", detail="test detail", data={"ok": True})

    async def verify(
        self, ctx: SkillContext, params: NoParams, result: StepResult
    ) -> RuleCheckResult:
        return RuleCheckResult(self._verify_ok, None if self._verify_ok else "test check failed")


@dataclass
class Env:
    bus: EventBus
    state: StateStore
    history: HistoryStore
    audit: AuditLog
    settings: SettingsStore
    supervisor: Supervisor
    pipeline: CommandPipeline
    events: EventRecorder


EnvFactory = Callable[..., Env]


async def stored_task(history: HistoryStore, *, tier: Tier = Tier.T2) -> Task:
    """A task + step row, so confirmations have something to point at."""
    task = Task(
        id=new_id(),
        conversation_id=None,
        origin=Origin.TEXT,
        utterance="demo dangerous",
        intent="demo.dangerous",
        mode="balanced",
        allowed_caps=["demo.dangerous"],
        created_at=datetime.now(UTC),
    )
    task.steps.append(
        Step(
            id=new_id(),
            task_id=task.id,
            idx=0,
            skill_id="demo.dangerous",
            label="Run the demo dangerous action",
            params={},
            tier=tier,
        )
    )
    await history.save_task(task)
    return task
