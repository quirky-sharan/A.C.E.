"""Tasks, steps, confirmations and messages (ACE_MASTER_PLAN.md §5.4, §8.4, §13.3) and the
in-process events that report their changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pydantic import JsonValue

from ace_core.app.events import Event
from ace_core.security.tiers import Tier


class Origin(StrEnum):
    VOICE = "voice"
    TEXT = "text"
    ROUTINE = "routine"
    SCHEDULE = "schedule"
    MCP = "mcp"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

    @property
    def finished(self) -> bool:
        return self in _FINISHED_TASK


_FINISHED_TASK = frozenset(
    {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.INTERRUPTED}
)


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUSED = "refused"


class ConfirmationAnswer(StrEnum):
    YES = "yes"
    NO = "no"
    TIMEOUT = "timeout"


class MessageRole(StrEnum):
    USER = "user"
    ACE = "ace"
    SYSTEM = "system"


class MessageSource(StrEnum):
    VOICE = "voice"
    TEXT = "text"
    NOTIFICATION = "notification"


@dataclass(slots=True, kw_only=True)
class Step:
    id: str
    task_id: str
    idx: int
    skill_id: str
    label: str  # the exact action in one line (Skill.describe)
    params: dict[str, JsonValue]
    tier: Tier
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    observation: dict[str, JsonValue] = field(default_factory=dict)
    error_code: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PendingConfirmation:
    id: str
    task_id: str
    step_id: str
    prompt: str
    requested_at: datetime
    expires_at: datetime


@dataclass(slots=True, kw_only=True)
class Task:
    id: str
    conversation_id: str | None
    origin: Origin
    utterance: str
    intent: str
    mode: str  # verification mode when the task was created (D-09)
    allowed_caps: list[str]
    created_at: datetime
    status: TaskStatus = TaskStatus.QUEUED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result_summary: str | None = None
    error_code: str | None = None
    steps: list[Step] = field(default_factory=list)
    confirmation: PendingConfirmation | None = None  # only while waiting for Sharan's answer


@dataclass(frozen=True, slots=True, kw_only=True)
class Message:
    id: str
    conversation_id: str
    ts: datetime
    role: MessageRole
    text: str
    source: MessageSource
    detail: str | None = None  # the longer sidebar text of an ACE reply (D-04)
    task_id: str | None = None
    reply_to: str | None = None  # the user message an ACE reply answers
    stt_confidence: float | None = None


class TaskChange(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    FINISHED = "finished"


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskChanged(Event):
    """``task`` is a private copy, safe to read after later changes."""

    change: TaskChange
    task: Task


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfirmationRequested(Event):
    confirmation: PendingConfirmation


@dataclass(frozen=True, slots=True, kw_only=True)
class MessageCreated(Event):
    message: Message
