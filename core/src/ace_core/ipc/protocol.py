"""Parse incoming and build outgoing IPC messages. Nothing acts on a message before it validates."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

from ace_core.ipc.schemas import (
    MAX_MESSAGE_BYTES,
    AuthMessage,
    ErrorCode,
    ErrorInfo,
    ErrorMessage,
    EventMessage,
    IncomingMessage,
    RequestMessage,
    ResponseMessage,
)

_INCOMING: TypeAdapter[AuthMessage | RequestMessage] = TypeAdapter(IncomingMessage)
_MAX_ERROR_ITEMS = 5


class ProtocolError(Exception):
    """A refused message. ``request_id`` / ``method`` are echoed when they were readable."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        request_id: str | None = None,
        method: str | None = None,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id
        self.method = method
        self.details = details or {}


def validation_summary(exc: ValidationError) -> dict[str, JsonValue]:
    """Field locations and messages only - never the rejected input (it could hold a secret)."""
    errors: list[JsonValue] = [
        {"loc": ".".join(str(part) for part in error["loc"]), "msg": error["msg"]}
        for error in exc.errors(include_input=False, include_url=False)[:_MAX_ERROR_ITEMS]
    ]
    return {"errors": errors}


def _readable_string(value: Any, limit: int) -> str | None:
    return value if isinstance(value, str) and len(value) <= limit else None


def parse_incoming(raw: str) -> AuthMessage | RequestMessage:
    """Validate one inbound text frame or raise :class:`ProtocolError`."""
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError(ErrorCode.BAD_MESSAGE, "message is too large")
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        raise ProtocolError(ErrorCode.BAD_MESSAGE, "message is not valid JSON") from None
    if not isinstance(data, dict):
        raise ProtocolError(ErrorCode.BAD_MESSAGE, "message must be a JSON object")
    request_id = _readable_string(data.get("id"), 64)
    method = _readable_string(data.get("method"), 64)
    try:
        return _INCOMING.validate_python(data)
    except ValidationError as exc:
        raise ProtocolError(
            ErrorCode.BAD_MESSAGE,
            "message does not match the IPC protocol",
            request_id=request_id,
            method=method,
            details=validation_summary(exc),
        ) from None


def _now() -> datetime:
    return datetime.now(UTC)


def response(request: RequestMessage, result: BaseModel) -> str:
    return ResponseMessage(
        id=request.id, method=request.method, result=result.model_dump(mode="json"), ts=_now()
    ).model_dump_json()


def error(
    code: ErrorCode,
    message: str,
    *,
    request_id: str | None = None,
    method: str | None = None,
    details: dict[str, JsonValue] | None = None,
) -> str:
    info = ErrorInfo(code=code, message=message, details=details or {})
    return ErrorMessage(id=request_id, method=method, error=info, ts=_now()).model_dump_json()


def error_from(exc: ProtocolError) -> str:
    return error(
        exc.code,
        exc.message,
        request_id=exc.request_id,
        method=exc.method,
        details=exc.details,
    )


def event(name: str, payload: BaseModel) -> str:
    return EventMessage(
        method=name, params=payload.model_dump(mode="json"), ts=_now()
    ).model_dump_json()
