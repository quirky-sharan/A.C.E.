"""SQL for each table - the ONLY code that touches tables (ACE_MASTER_PLAN.md §13.2).

Every statement is built with SQLAlchemy and bound parameters; no SQL is ever assembled from
strings. Functions take an open :class:`Session` and run inside ``Database.run``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ace_core.db.models import (
    AuditLogEntry,
    ConfirmationRow,
    ConversationRow,
    MessageRow,
    Setting,
    TaskRow,
    TaskStepRow,
)


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


class ConversationRepository:
    @staticmethod
    def add(session: Session, row: ConversationRow) -> None:
        session.add(row)

    @staticmethod
    def end(session: Session, conversation_id: str, ended_at: datetime) -> None:
        row = session.get(ConversationRow, conversation_id)
        if row is not None and row.ended_at is None:
            row.ended_at = ended_at


class MessageRepository:
    @staticmethod
    def add(session: Session, row: MessageRow) -> None:
        session.add(row)

    @staticmethod
    def recent(session: Session, *, limit: int) -> list[MessageRow]:
        """The newest ``limit`` messages, oldest first."""
        statement = select(MessageRow).order_by(MessageRow.ts.desc(), MessageRow.id.desc())
        rows = list(session.scalars(statement.limit(limit)))
        rows.reverse()
        return rows


class TaskRepository:
    @staticmethod
    def save(session: Session, task: TaskRow, steps: list[TaskStepRow]) -> None:
        """Insert or update a task and its steps (the task first: steps reference it)."""
        session.merge(task)
        session.flush()
        for step in steps:
            session.merge(step)

    @staticmethod
    def get(session: Session, task_id: str) -> TaskRow | None:
        return session.get(TaskRow, task_id)

    @staticmethod
    def recent(session: Session, *, limit: int, query: str | None = None) -> list[TaskRow]:
        """Newest first; ``query`` matches the utterance, intent or reply (LIKE, escaped)."""
        statement = select(TaskRow).order_by(TaskRow.created_at.desc(), TaskRow.id.desc())
        if query:
            statement = statement.where(
                or_(
                    TaskRow.utterance.contains(query, autoescape=True),
                    TaskRow.intent.contains(query, autoescape=True),
                    TaskRow.result_summary.contains(query, autoescape=True),
                )
            )
        return list(session.scalars(statement.limit(limit)))

    @staticmethod
    def steps_for(session: Session, task_ids: list[str]) -> list[TaskStepRow]:
        if not task_ids:
            return []
        statement = (
            select(TaskStepRow)
            .where(TaskStepRow.task_id.in_(task_ids))
            .order_by(TaskStepRow.task_id, TaskStepRow.idx)
        )
        return list(session.scalars(statement))


class ConfirmationRepository:
    @staticmethod
    def add(session: Session, row: ConfirmationRow) -> None:
        session.add(row)

    @staticmethod
    def get(session: Session, confirmation_id: str) -> ConfirmationRow | None:
        return session.get(ConfirmationRow, confirmation_id)
