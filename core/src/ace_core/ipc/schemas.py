"""IPC message schemas (ACE_MASTER_PLAN.md §5.5).

These Pydantic models are the single source of truth: ``export_schema`` turns them into JSON Schema
and ``json2ts`` turns that into ``apps/desktop/src/ipc/generated.ts`` for the UI.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from ace_core.app.health import HealthStatus
from ace_core.app.state import ConversationState
from ace_core.brain.records import MessageRole, MessageSource, Origin, StepStatus, TaskStatus
from ace_core.security.tiers import Tier

PROTOCOL_VERSION: Final = 1
MAX_MESSAGE_BYTES: Final = 1024 * 1024  # 1 MiB
METHOD_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"


class ErrorCode(StrEnum):
    BAD_MESSAGE = "E_IPC_BAD_MESSAGE"
    UNKNOWN_METHOD = "E_IPC_UNKNOWN_METHOD"
    BAD_PARAMS = "E_IPC_BAD_PARAMS"
    RATE_LIMITED = "E_IPC_RATE_LIMITED"
    DEV_ONLY = "E_IPC_DEV_ONLY"
    INTERNAL = "E_IPC_INTERNAL"


class _Model(BaseModel):
    # The core always sends every field, so outgoing schemas mark defaulted fields as required.
    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_serialization_defaults_required=True
    )


# ---- client -> core ----


class AuthMessage(_Model):
    """Must be the first message on every connection, within 2 seconds."""

    v: Literal[1] = 1
    type: Literal["auth"]
    token: str = Field(min_length=1, max_length=512)


class RequestMessage(_Model):
    v: Literal[1] = 1
    type: Literal["request"]
    id: str = Field(min_length=1, max_length=64)
    method: str = Field(max_length=64, pattern=METHOD_NAME_PATTERN)
    params: dict[str, JsonValue] = Field(default_factory=dict)


IncomingMessage = Annotated[AuthMessage | RequestMessage, Field(discriminator="type")]


# ---- core -> client ----


class ErrorInfo(_Model):
    code: ErrorCode
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ResponseMessage(_Model):
    v: Literal[1] = 1
    type: Literal["response"] = "response"
    id: str
    method: str
    result: JsonValue
    ts: datetime


class ErrorMessage(_Model):
    v: Literal[1] = 1
    type: Literal["error"] = "error"
    id: str | None = None
    method: str | None = None
    error: ErrorInfo
    ts: datetime


class EventMessage(_Model):
    v: Literal[1] = 1
    type: Literal["event"] = "event"
    method: str
    params: dict[str, JsonValue]
    ts: datetime


OutgoingMessage = Annotated[
    ResponseMessage | ErrorMessage | EventMessage, Field(discriminator="type")
]


# ---- shared shapes ----


class CoreStateInfo(_Model):
    conversation: ConversationState
    game_mode: bool
    offline: bool
    dnd: bool
    paused_overlay: bool


class SubsystemHealthInfo(_Model):
    name: str
    status: HealthStatus
    detail: str | None
    since: datetime


class StepInfo(_Model):
    id: str
    idx: int
    skill_id: str
    label: str
    tier: Tier
    status: StepStatus
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None


class ConfirmationInfo(_Model):
    id: str
    task_id: str
    step_id: str
    prompt: str
    requested_at: datetime
    expires_at: datetime


class ClarifyOptionInfo(_Model):
    id: str
    label: str


class ClarificationInfo(_Model):
    id: str
    task_id: str
    step_id: str
    question: str
    options: list[ClarifyOptionInfo]
    requested_at: datetime
    expires_at: datetime


class TaskInfo(_Model):
    id: str
    conversation_id: str | None
    origin: Origin
    utterance: str
    intent: str
    mode: str
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result_summary: str | None
    error_code: str | None
    steps: list[StepInfo]
    confirmation: ConfirmationInfo | None  # set only while the task waits for Sharan's answer
    clarification: ClarificationInfo | None  # set only while it waits for a choice


class MessageInfo(_Model):
    id: str
    conversation_id: str
    ts: datetime
    role: MessageRole
    text: str
    source: MessageSource
    detail: str | None
    task_id: str | None
    reply_to: str | None


# ---- method params and results ----


class EmptyParams(_Model):
    pass


class HealthResult(_Model):
    overall: HealthStatus
    subsystems: list[SubsystemHealthInfo]


class SettingsGetParams(_Model):
    key: str = Field(min_length=1, max_length=256)


class SettingsGetResult(_Model):
    key: str
    found: bool
    value: JsonValue  # null when not found (no default: json2ts mistypes "$ref" + "default")


class SettingsSetParams(_Model):
    key: str = Field(min_length=1, max_length=256)
    value: JsonValue


class SettingsSetResult(_Model):
    key: str
    saved: bool


class LogTailParams(_Model):
    lines: int = Field(default=50, ge=1, le=500)


class LogTailResult(_Model):
    lines: list[str]


class CommandSubmitParams(_Model):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("the command is empty")
        return text


class CommandSubmitResult(_Model):
    conversation_id: str
    message_id: str
    intent: str
    task_id: str | None  # the new task, or the task a yes / no answered


class TaskListParams(_Model):
    limit: int = Field(default=50, ge=1, le=200)
    query: str | None = Field(default=None, max_length=200)


class TaskListResult(_Model):
    tasks: list[TaskInfo]


class TaskCancelParams(_Model):
    task_id: str = Field(min_length=1, max_length=36)


class TaskCancelResult(_Model):
    cancelled: bool


class ConfirmRespondParams(_Model):
    confirmation_id: str = Field(min_length=1, max_length=36)
    answer: Literal["yes", "no"]


class ConfirmRespondResult(_Model):
    accepted: bool  # false when the confirmation was already answered or has expired


class ClarifyRespondParams(_Model):
    clarification_id: str = Field(min_length=1, max_length=36)
    option_id: str = Field(min_length=1, max_length=128)


class ClarifyRespondResult(_Model):
    accepted: bool  # false when the question was already answered, expired or the option is unknown


class AppsListParams(_Model):
    query: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=200, ge=1, le=1000)


class AppInfo(_Model):
    name: str
    kind: str  # aumid (Store app) / exe (desktop app) / other
    target: str
    launch_count: int


class AppsListResult(_Model):
    available: bool  # false where app control is not supported
    apps: list[AppInfo]


class AppsRefreshResult(_Model):
    count: int


class AudioDeviceInfo(_Model):
    name: str
    is_default: bool  # the Windows default device


class DevicesResult(_Model):
    available: bool  # false where audio is not supported
    muted: bool
    capturing: bool  # the microphone is open right now
    input: str | None  # the chosen device name; null = the Windows default
    output: str | None
    inputs: list[AudioDeviceInfo]
    outputs: list[AudioDeviceInfo]


class DevicesSelectParams(_Model):
    kind: Literal["input", "output"]
    name: str | None = Field(default=None, max_length=256)  # null = the Windows default


class DevicesSelectResult(_Model):
    saved: bool


class DevicesRecordParams(_Model):
    seconds: float = Field(default=5.0, ge=0.5, le=8.0)


class DevicesRecordResult(_Model):
    ok: bool
    error: str | None
    seconds: float
    peak: float  # 0..1
    level: float  # 0..1 (dB scale)


class DevicesPlayResult(_Model):
    ok: bool
    error: str | None
    seconds: float


class DevicesEarconParams(_Model):
    name: Literal["wake", "done", "error", "mute", "unmute", "test"] = "test"


class DevicesMuteParams(_Model):
    muted: bool


class DevicesMuteResult(_Model):
    muted: bool


class MessageListParams(_Model):
    limit: int = Field(default=50, ge=1, le=200)


class MessageListResult(_Model):
    messages: list[MessageInfo]  # oldest first


# ---- event payloads ----


class SessionReadyPayload(_Model):
    version: str
    protocol: int
    dev: bool
    state: CoreStateInfo


class StateChangedPayload(_Model):
    state: CoreStateInfo
    previous: CoreStateInfo


class HealthChangedPayload(_Model):
    subsystem: str
    status: HealthStatus
    previous: HealthStatus | None
    detail: str | None


class SystemStoppingPayload(_Model):
    reason: str


class DatabaseRecoveredPayload(_Model):
    corrupt_copy: str
    restored_from: str | None


class TaskEventPayload(_Model):
    task: TaskInfo


class ConfirmRequestedPayload(_Model):
    confirmation: ConfirmationInfo


class ClarifyRequestedPayload(_Model):
    clarification: ClarificationInfo


class AudioLevelPayload(_Model):
    level: float  # 0..1, about 20 times a second while the microphone is open


class MessageCreatedPayload(_Model):
    message: MessageInfo


class SettingsChangedPayload(_Model):
    key: str
    deleted: bool
