"""The skill contract (ACE_MASTER_PLAN.md §10.1).

Every skill subclasses :class:`Skill` with its own Pydantic params model. The Supervisor decides
whether a step may run (tier, scope, confirmation); the skill only does the work, checks the
result deterministically (``verify``) and, where possible, undoes it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from pydantic import BaseModel, ConfigDict, JsonValue

from ace_core.brain.records import Origin
from ace_core.db.stores import Actor
from ace_core.security.tiers import Tier

SKILL_ID_PATTERN: Final = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"


class SkillParams(BaseModel):
    """Base of every params model: unknown fields are rejected and values are frozen."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class NoParams(SkillParams):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class SkillContext:
    task_id: str
    step_id: str
    origin: Origin
    utterance: str


@dataclass(frozen=True, slots=True, kw_only=True)
class StepResult:
    spoken: str  # a short reply line (spoken from S11 on)
    detail: str | None = None  # longer text for the sidebar
    data: Mapping[str, JsonValue] = field(default_factory=dict)  # stored redacted as observation


@dataclass(frozen=True, slots=True)
class RuleCheckResult:
    ok: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class UndoResult:
    ok: bool
    detail: str | None = None


class SkillError(Exception):
    """A skill could not do its job. ``message`` is shown to Sharan: short, plain English."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SettingsAccess(Protocol):
    """The part of the settings store skills may use (``SettingsStore`` satisfies it)."""

    async def get(self, key: str, default: JsonValue = None) -> JsonValue: ...

    async def set(self, key: str, value: JsonValue, *, actor: Actor = ...) -> None: ...


class Skill[P: SkillParams](ABC):
    id: str  # e.g. "apps.open"
    description: str  # one line; becomes the LLM tool description (S15)
    params_model: type[P]
    background_capable: bool = True  # False if it needs synthetic mouse / keyboard input
    timeout_s: float = 10.0
    examples: tuple[str, ...] = ()  # utterances (English + Hinglish) for help and the golden set

    @abstractmethod
    def tier_for(self, params: P) -> Tier:
        """T0..T3 (§15.3); may depend on the params (e.g. ``force``)."""

    def describe(self, params: P) -> str:
        """The exact action in one line, for task cards and confirmations (§15.3)."""
        return self.description

    async def preconditions(self, ctx: SkillContext, params: P) -> list[str]:
        """Unmet preconditions in plain English; empty when the step may run."""
        return []

    @abstractmethod
    async def execute(self, ctx: SkillContext, params: P) -> StepResult: ...

    @abstractmethod
    async def verify(self, ctx: SkillContext, params: P, result: StepResult) -> RuleCheckResult:
        """Deterministic postconditions: did the action really happen?"""

    async def undo(self, ctx: SkillContext, params: P, result: StepResult) -> UndoResult | None:
        """Reverse the action; None = not undoable."""
        return None


AnySkill = Skill[Any]
