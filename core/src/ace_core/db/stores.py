"""Validated, async access to settings and the audit log (used by later stages: IPC, Supervisor...).

Inputs are validated with Pydantic before reaching the repositories (§13.2). Audit summaries and
data are redacted before they are stored (§15.1). A setting change and its audit entry are written
in the same transaction.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from sqlalchemy.orm import Session

from ace_core.app.events import EventBus
from ace_core.db.database import Database
from ace_core.db.events import SettingChanged
from ace_core.db.ids import new_id
from ace_core.db.models import AuditLogEntry
from ace_core.db.repositories import AuditLogRepository, SettingsRepository
from ace_core.security.redaction import redact_text, redact_value
from ace_core.security.tiers import Tier

Actor = Literal["user", "ace", "verifier", "system"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class SettingWrite(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1, max_length=256)
    value: JsonValue

    @field_validator("key")
    @classmethod
    def _no_nul(cls, key: str) -> str:
        if "\x00" in key:
            raise ValueError("setting keys must not contain NUL characters")
        return key


class AuditEntryIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    actor: Actor
    event_type: str = Field(pattern=r"^[a-z0-9_.-]{1,64}$")
    summary: str = Field(min_length=1, max_length=1000)
    data: dict[str, Any] = Field(default_factory=dict)
    tier: Tier | None = None
    task_id: str | None = Field(default=None, max_length=36)
    step_id: str | None = Field(default=None, max_length=36)


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: str
    ts: datetime
    actor: str
    event_type: str
    summary: str
    data: dict[str, Any]
    tier: str | None
    task_id: str | None
    step_id: str | None


class AuditLog:
    def __init__(self, db: Database, *, clock: Callable[[], datetime] = _utcnow) -> None:
        self._db = db
        self._clock = clock

    def build(self, entry: AuditEntryIn) -> AuditLogEntry:
        """A redacted row for ``entry`` - for callers that write it inside their own transaction."""
        return AuditLogEntry(
            id=new_id(),
            ts=self._clock(),
            actor=entry.actor,
            event_type=entry.event_type,
            summary=redact_text(entry.summary),
            data_json=_dumps(redact_value(entry.data)),
            tier=entry.tier.value if entry.tier is not None else None,
            task_id=entry.task_id,
            step_id=entry.step_id,
        )

    async def record(
        self,
        *,
        actor: Actor,
        event_type: str,
        summary: str,
        data: Mapping[str, Any] | None = None,
        tier: Tier | None = None,
        task_id: str | None = None,
        step_id: str | None = None,
    ) -> str:
        """Validate, redact and store an audit entry; returns its id."""
        row = self.build(
            AuditEntryIn(
                actor=actor,
                event_type=event_type,
                summary=summary,
                data=dict(data or {}),
                tier=tier,
                task_id=task_id,
                step_id=step_id,
            )
        )
        await self._db.run(lambda session: AuditLogRepository.add(session, row))
        return row.id

    async def recent(self, limit: int = 50, event_type: str | None = None) -> list[AuditRecord]:
        def load(session: Session) -> list[AuditRecord]:
            rows = AuditLogRepository.recent(session, limit=limit, event_type=event_type)
            return [
                AuditRecord(
                    id=r.id,
                    ts=r.ts,
                    actor=r.actor,
                    event_type=r.event_type,
                    summary=r.summary,
                    data=json.loads(r.data_json),
                    tier=r.tier,
                    task_id=r.task_id,
                    step_id=r.step_id,
                )
                for r in rows
            ]

        return await self._db.run(load)


class SettingsStore:
    """Settings as JSON values. With a ``bus``, every change publishes :class:`SettingChanged`."""

    def __init__(
        self,
        db: Database,
        audit: AuditLog,
        *,
        bus: EventBus | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._db = db
        self._audit = audit
        self._bus = bus
        self._clock = clock

    async def lookup(self, key: str) -> tuple[bool, JsonValue]:
        """``(found, value)`` - tells a missing key apart from a stored ``null``."""

        def load(session: Session) -> str | None:
            setting = SettingsRepository.get(session, key)
            return setting.value_json if setting is not None else None

        raw = await self._db.run(load)
        return (False, None) if raw is None else (True, json.loads(raw))

    async def get(self, key: str, default: JsonValue = None) -> JsonValue:
        """The stored value for ``key``, or ``default`` when it is not set."""
        found, value = await self.lookup(key)
        return value if found else default

    async def set(self, key: str, value: JsonValue, *, actor: Actor = "system") -> None:
        """Store ``value`` (any JSON value) under ``key`` and record it in the audit log."""
        write = SettingWrite(key=key, value=value)
        value_json = _dumps(write.value)
        audit_row = self._audit.build(
            AuditEntryIn(
                actor=actor,
                event_type="settings.changed",
                summary="setting changed",
                data={"key": write.key},
            )
        )
        now = self._clock()

        def save(session: Session) -> None:
            SettingsRepository.upsert(session, write.key, value_json, now)
            AuditLogRepository.add(session, audit_row)

        await self._db.run(save)
        if self._bus is not None:
            await self._bus.publish(SettingChanged(key=write.key, actor=actor))

    async def delete(self, key: str, *, actor: Actor = "system") -> bool:
        audit_row = self._audit.build(
            AuditEntryIn(
                actor=actor,
                event_type="settings.deleted",
                summary="setting deleted",
                data={"key": key},
            )
        )

        def remove(session: Session) -> bool:
            deleted = SettingsRepository.delete(session, key)
            if deleted:
                AuditLogRepository.add(session, audit_row)
            return deleted

        deleted = await self._db.run(remove)
        if deleted and self._bus is not None:
            await self._bus.publish(SettingChanged(key=key, actor=actor, deleted=True))
        return deleted

    async def all(self) -> dict[str, JsonValue]:
        def load(session: Session) -> dict[str, JsonValue]:
            return {s.key: json.loads(s.value_json) for s in SettingsRepository.all(session)}

        return await self._db.run(load)
