"""Conversations, messages, tasks, steps and confirmations (ACE_MASTER_PLAN.md §13.3, S07).

Step params and observations are redacted before they are stored (§13.3, §15.1). All work runs
on the database thread through ``Database.run``.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from pydantic import JsonValue
from sqlalchemy.orm import Session

from ace_core.brain.records import (
    ConfirmationAnswer,
    Message,
    MessageRole,
    MessageSource,
    Origin,
    PendingConfirmation,
    Step,
    StepStatus,
    Task,
    TaskStatus,
)
from ace_core.db.database import Database
from ace_core.db.models import ConfirmationRow, ConversationRow, MessageRow, TaskRow, TaskStepRow
from ace_core.db.repositories import (
    ConfirmationRepository,
    ConversationRepository,
    MessageRepository,
    TaskRepository,
)
from ace_core.security.redaction import redact_value
from ace_core.security.tiers import Tier


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _loads_object(raw: str) -> dict[str, JsonValue]:
    value = json.loads(raw)
    return cast("dict[str, JsonValue]", value) if isinstance(value, dict) else {}


def _message_row(message: Message) -> MessageRow:
    meta = {
        key: value
        for key, value in (
            ("detail", message.detail),
            ("task_id", message.task_id),
            ("reply_to", message.reply_to),
        )
        if value is not None
    }
    return MessageRow(
        id=message.id,
        conversation_id=message.conversation_id,
        ts=message.ts,
        role=message.role.value,
        text=message.text,
        source=message.source.value,
        stt_confidence=message.stt_confidence,
        meta_json=_dumps(meta),
    )


def _message(row: MessageRow) -> Message:
    meta = _loads_object(row.meta_json)

    def text_or_none(key: str) -> str | None:
        value = meta.get(key)
        return value if isinstance(value, str) else None

    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        ts=row.ts,
        role=MessageRole(row.role),
        text=row.text,
        source=MessageSource(row.source),
        detail=text_or_none("detail"),
        task_id=text_or_none("task_id"),
        reply_to=text_or_none("reply_to"),
        stt_confidence=row.stt_confidence,
    )


def _task_rows(task: Task) -> tuple[TaskRow, list[TaskStepRow]]:
    row = TaskRow(
        id=task.id,
        conversation_id=task.conversation_id,
        origin=task.origin.value,
        utterance=task.utterance,
        intent=task.intent,
        mode=task.mode,
        status=task.status.value,
        allowed_caps_json=_dumps(task.allowed_caps),
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        result_summary=task.result_summary,
        error_code=task.error_code,
    )
    steps = [
        TaskStepRow(
            id=step.id,
            task_id=task.id,
            idx=step.idx,
            skill_id=step.skill_id,
            label=step.label,
            params_json=_dumps(redact_value(step.params)),
            tier=step.tier.value,
            status=step.status.value,
            started_at=step.started_at,
            finished_at=step.finished_at,
            observation_json=_dumps(redact_value(step.observation)),
            error_code=step.error_code,
        )
        for step in task.steps
    ]
    return row, steps


def _task(row: TaskRow, steps: list[TaskStepRow]) -> Task:
    caps = json.loads(row.allowed_caps_json)
    return Task(
        id=row.id,
        conversation_id=row.conversation_id,
        origin=Origin(row.origin),
        utterance=row.utterance,
        intent=row.intent,
        mode=row.mode,
        allowed_caps=[str(cap) for cap in caps] if isinstance(caps, list) else [],
        created_at=row.created_at,
        status=TaskStatus(row.status),
        started_at=row.started_at,
        finished_at=row.finished_at,
        result_summary=row.result_summary,
        error_code=row.error_code,
        steps=[
            Step(
                id=step.id,
                task_id=step.task_id,
                idx=step.idx,
                skill_id=step.skill_id,
                label=step.label,
                params=_loads_object(step.params_json),
                tier=Tier(step.tier),
                status=StepStatus(step.status),
                started_at=step.started_at,
                finished_at=step.finished_at,
                observation=_loads_object(step.observation_json),
                error_code=step.error_code,
            )
            for step in steps
        ],
    )


class HistoryStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---- conversations and messages ----

    async def start_conversation(
        self, conversation_id: str, *, channel: str, started_at: datetime
    ) -> None:
        row = ConversationRow(id=conversation_id, started_at=started_at, channel=channel)
        await self._db.run(lambda session: ConversationRepository.add(session, row))

    async def end_conversation(self, conversation_id: str, ended_at: datetime) -> None:
        await self._db.run(
            lambda session: ConversationRepository.end(session, conversation_id, ended_at)
        )

    async def add_message(self, message: Message) -> None:
        row = _message_row(message)
        await self._db.run(lambda session: MessageRepository.add(session, row))

    async def recent_messages(self, limit: int) -> list[Message]:
        """The newest ``limit`` messages, oldest first."""

        def load(session: Session) -> list[Message]:
            return [_message(row) for row in MessageRepository.recent(session, limit=limit)]

        return await self._db.run(load)

    # ---- tasks and steps ----

    async def save_task(self, task: Task) -> None:
        row, steps = _task_rows(task)
        await self._db.run(lambda session: TaskRepository.save(session, row, steps))

    async def get_task(self, task_id: str) -> Task | None:
        def load(session: Session) -> Task | None:
            row = TaskRepository.get(session, task_id)
            if row is None:
                return None
            return _task(row, TaskRepository.steps_for(session, [task_id]))

        return await self._db.run(load)

    async def list_tasks(self, *, limit: int, query: str | None = None) -> list[Task]:
        """Newest first, with their steps."""

        def load(session: Session) -> list[Task]:
            rows = TaskRepository.recent(session, limit=limit, query=query)
            steps: dict[str, list[TaskStepRow]] = {}
            for step in TaskRepository.steps_for(session, [row.id for row in rows]):
                steps.setdefault(step.task_id, []).append(step)
            return [_task(row, steps.get(row.id, [])) for row in rows]

        return await self._db.run(load)

    # ---- confirmations ----

    async def add_confirmation(self, confirmation: PendingConfirmation) -> None:
        row = ConfirmationRow(
            id=confirmation.id,
            task_id=confirmation.task_id,
            step_id=confirmation.step_id,
            prompt_text=confirmation.prompt,
            requested_at=confirmation.requested_at,
        )
        await self._db.run(lambda session: ConfirmationRepository.add(session, row))

    async def resolve_confirmation(
        self,
        confirmation_id: str,
        *,
        answer: ConfirmationAnswer,
        channel: str,
        responded_at: datetime,
    ) -> None:
        def save(session: Session) -> None:
            row = ConfirmationRepository.get(session, confirmation_id)
            if row is not None and row.response is None:
                row.response = answer.value
                row.channel = channel
                row.responded_at = responded_at

        await self._db.run(save)
