"""IPC message schemas (ACE_MASTER_PLAN.md §5.5).

These Pydantic models are the single source of truth: ``export_schema`` turns them into JSON Schema
and ``json2ts`` turns that into ``apps/desktop/src/ipc/generated.ts`` for the UI.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ace_core.app.health import HealthStatus
from ace_core.app.state import ConversationState

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
