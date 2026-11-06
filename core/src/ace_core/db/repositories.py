"""SQL for each table - the ONLY code that touches tables (ACE_MASTER_PLAN.md §13.2).

Every statement is built with SQLAlchemy and bound parameters; no SQL is ever assembled from
strings. Functions take an open :class:`Session` and run inside ``Database.run``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ace_core.db.models import AuditLogEntry, Setting


class SettingsRepository:
    @staticmethod
    def get(session: Session, key: str) -> Setting | None:
        return session.get(Setting, key)

    @staticmethod
    def upsert(session: Session, key: str, value_json: str, updated_at: datetime) -> None:
        statement = sqlite_insert(Setting).values(
            key=key, value_json=value_json, updated_at=updated_at
        )
        statement = statement.on_conflict_do_update(
            index_elements=[Setting.key],
            set_={
                "value_json": statement.excluded.value_json,
                "updated_at": statement.excluded.updated_at,
            },
        )
        session.execute(statement)

    @staticmethod
    def delete(session: Session, key: str) -> bool:
        setting = session.get(Setting, key)
        if setting is None:
            return False
        session.delete(setting)
        return True

    @staticmethod
    def all(session: Session) -> list[Setting]:
        return list(session.scalars(select(Setting).order_by(Setting.key)))

    @staticmethod
    def count(session: Session) -> int:
        return session.scalar(select(func.count()).select_from(Setting)) or 0


class AuditLogRepository:
    @staticmethod
    def add(session: Session, entry: AuditLogEntry) -> None:
        session.add(entry)

    @staticmethod
    def recent(
        session: Session, *, limit: int, event_type: str | None = None
    ) -> list[AuditLogEntry]:
        statement = select(AuditLogEntry).order_by(AuditLogEntry.ts.desc(), AuditLogEntry.id.desc())
        if event_type is not None:
            statement = statement.where(AuditLogEntry.event_type == event_type)
        return list(session.scalars(statement.limit(limit)))

    @staticmethod
    def delete_older_than(session: Session, cutoff: datetime) -> int:
        result = session.execute(delete(AuditLogEntry).where(AuditLogEntry.ts < cutoff))
        return cast("CursorResult[Any]", result).rowcount
