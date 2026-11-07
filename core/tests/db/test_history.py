"""HistoryStore: conversations, messages, tasks, steps and confirmations (§13.3, S07)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import JsonValue
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
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
from ace_core.db.history import HistoryStore
from ace_core.db.ids import new_id
from ace_core.db.models import ConfirmationRow, ConversationRow, TaskStepRow
from ace_core.security.tiers import Tier

T0 = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def make_task(
    utterance: str, *, created_at: datetime = T0, params: dict[str, JsonValue] | None = None
) -> Task:
    task = Task(
        id=new_id(),
        conversation_id=None,
        origin=Origin.TEXT,
        utterance=utterance,
        intent="system.echo",
        mode="balanced",
        allowed_caps=["system.echo"],
        created_at=created_at,
    )
    task.steps.append(
        Step(
            id=new_id(),
            task_id=task.id,
            idx=0,
            skill_id="system.echo",
            label=f'Echo "{utterance}"',
            params=params or {"text": utterance},
            tier=Tier.T0,
        )
    )
    return task


async def test_tasks_round_trip_with_their_steps(history: HistoryStore) -> None:
    task = make_task("echo hello")
    await history.save_task(task)
    task.status = TaskStatus.SUCCEEDED
    task.steps[0].status = StepStatus.SUCCEEDED
    task.steps[0].observation = {"text": "hello"}
    task.result_summary = "hello"
    await history.save_task(task)  # an update, not a second row
    loaded = await history.get_task(task.id)
    assert loaded == task
    assert await history.get_task("missing") is None


async def test_step_params_and_observations_are_redacted(history: HistoryStore) -> None:
    fake_key = "sk-live-1234567890abcdef"  # pragma: allowlist secret
    task = make_task("x", params={"text": "x", "api_key": fake_key})
    sample = "abc"
    task.steps[0].observation = {"token": sample}
    await history.save_task(task)
    loaded = await history.get_task(task.id)
    assert loaded is not None
    assert loaded.steps[0].params["text"] == "x"
    assert fake_key[8:] not in str(loaded.steps[0].params["api_key"])
    assert loaded.steps[0].observation["token"] != sample


async def test_listing_is_newest_first_and_searchable(history: HistoryStore) -> None:
    for minutes, utterance in enumerate(["echo one", "echo 100% sure", "echo two_three"]):
        await history.save_task(make_task(utterance, created_at=T0 + timedelta(minutes=minutes)))
    tasks = await history.list_tasks(limit=10)
    assert [t.utterance for t in tasks] == ["echo two_three", "echo 100% sure", "echo one"]
    assert [t.utterance for t in await history.list_tasks(limit=1)] == ["echo two_three"]
    assert [t.utterance for t in await history.list_tasks(limit=10, query="100%")] == [
        "echo 100% sure"
    ]
    # % and _ are literal characters, not LIKE wildcards
    assert [t.utterance for t in await history.list_tasks(limit=10, query="o_t")] == [
        "echo two_three"
    ]
    assert await history.list_tasks(limit=10, query="%") == [tasks[1]]
    assert await history.list_tasks(limit=10, query="'; DROP TABLE tasks; --") == []
    assert len(await history.list_tasks(limit=10, query="ECHO")) == 3  # case-insensitive


async def test_messages_keep_their_details(history: HistoryStore) -> None:
    conversation_id = new_id()
    await history.start_conversation(conversation_id, channel="text", started_at=T0)
    user = Message(
        id=new_id(),
        conversation_id=conversation_id,
        ts=T0,
        role=MessageRole.USER,
        text="help",
        source=MessageSource.TEXT,
    )
    ace = Message(
        id=new_id(),
        conversation_id=conversation_id,
        ts=T0 + timedelta(seconds=1),
        role=MessageRole.ACE,
        text="Here's what I can do",
        source=MessageSource.TEXT,
        detail="• echo",
        task_id=None,
        reply_to=user.id,
    )
    await history.add_message(ace)
    await history.add_message(user)
    assert await history.recent_messages(10) == [user, ace]
    assert await history.recent_messages(1) == [ace]
    await history.end_conversation(conversation_id, T0 + timedelta(minutes=1))
    await history.end_conversation(conversation_id, T0 + timedelta(minutes=5))  # first end wins


async def test_messages_need_a_conversation(history: HistoryStore) -> None:
    orphan = Message(
        id=new_id(),
        conversation_id="no-such-conversation",
        ts=T0,
        role=MessageRole.USER,
        text="x",
        source=MessageSource.TEXT,
    )
    with pytest.raises(IntegrityError):
        await history.add_message(orphan)


async def test_confirmations_are_answered_once(db: Database, history: HistoryStore) -> None:
    task = make_task("demo dangerous")
    await history.save_task(task)
    confirmation = PendingConfirmation(
        id=new_id(),
        task_id=task.id,
        step_id=task.steps[0].id,
        prompt="Run the demo dangerous action",
        requested_at=T0,
        expires_at=T0 + timedelta(seconds=30),
    )
    await history.add_confirmation(confirmation)
    await history.resolve_confirmation(
        confirmation.id, answer=ConfirmationAnswer.NO, channel="click", responded_at=T0
    )
    await history.resolve_confirmation(
        confirmation.id, answer=ConfirmationAnswer.YES, channel="text", responded_at=T0
    )

    def load(session: Session) -> tuple[str | None, str | None]:
        row = session.scalars(select(ConfirmationRow)).one()
        return row.response, row.channel

    assert await db.run(load) == ("no", "click")


async def test_deleting_a_task_removes_its_steps_and_confirmations(
    db: Database, history: HistoryStore
) -> None:
    task = make_task("demo dangerous")
    await history.save_task(task)
    await history.add_confirmation(
        PendingConfirmation(
            id=new_id(),
            task_id=task.id,
            step_id=task.steps[0].id,
            prompt="x",
            requested_at=T0,
            expires_at=T0,
        )
    )

    def delete_and_count(session: Session) -> tuple[int, int, int]:
        session.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task.id})
        return (
            len(list(session.scalars(select(TaskStepRow)))),
            len(list(session.scalars(select(ConfirmationRow)))),
            len(list(session.scalars(select(ConversationRow)))),
        )

    assert await db.run(delete_and_count) == (0, 0, 0)
