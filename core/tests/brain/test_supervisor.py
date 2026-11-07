"""The Supervisor: tier decisions, capability scope, confirmations, timeouts (§15.3)."""

from __future__ import annotations

import asyncio

import pytest
from brain_fakes import ConfigurableSkill, EventRecorder, stored_task
from sqlalchemy import select
from sqlalchemy.orm import Session

from ace_core.app.events import EventBus
from ace_core.brain.records import ConfirmationAnswer, ConfirmationRequested
from ace_core.brain.supervisor import (
    ERR_FORBIDDEN,
    ERR_OUT_OF_SCOPE,
    Decision,
    Supervisor,
)
from ace_core.db.database import Database
from ace_core.db.history import HistoryStore
from ace_core.db.models import ConfirmationRow
from ace_core.db.stores import AuditLog
from ace_core.security.scope import CapabilityScope
from ace_core.security.tiers import Tier
from ace_core.skills.base import NoParams


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def make_supervisor(
    history: HistoryStore, audit: AuditLog, bus: EventBus, timeout_s: float = 5.0
) -> Supervisor:
    return Supervisor(history=history, audit=audit, bus=bus, timeout_s=timeout_s)


async def confirmation_row(db: Database, confirmation_id: str) -> ConfirmationRow:
    def load(session: Session) -> ConfirmationRow:
        row = session.scalars(
            select(ConfirmationRow).where(ConfirmationRow.id == confirmation_id)
        ).one()
        session.expunge(row)
        return row

    return await db.run(load)


@pytest.mark.parametrize(
    ("tier", "decision", "code"),
    [
        (Tier.T0, Decision.RUN, None),
        (Tier.T1, Decision.RUN, None),
        (Tier.T2, Decision.CONFIRM, None),
        (Tier.T3, Decision.REFUSE, ERR_FORBIDDEN),
    ],
)
def test_tiers_decide_what_runs(
    history: HistoryStore,
    audit: AuditLog,
    bus: EventBus,
    tier: Tier,
    decision: Decision,
    code: str | None,
) -> None:
    supervisor = make_supervisor(history, audit, bus)
    skill = ConfigurableSkill("test.skill", tier=tier)
    verdict = supervisor.evaluate(skill, NoParams(), CapabilityScope.of(["test.skill"]))
    assert (verdict.decision, verdict.tier, verdict.error_code) == (decision, tier, code)


def test_a_skill_outside_the_scope_never_runs(
    history: HistoryStore, audit: AuditLog, bus: EventBus
) -> None:
    supervisor = make_supervisor(history, audit, bus)
    skill = ConfigurableSkill("test.skill")
    verdict = supervisor.evaluate(skill, NoParams(), CapabilityScope.of(["other.skill"]))
    assert verdict.decision is Decision.REFUSE
    assert verdict.error_code == ERR_OUT_OF_SCOPE
    assert supervisor.evaluate(skill, NoParams(), CapabilityScope.of(["test.*"])).decision is (
        Decision.RUN
    )
    assert not CapabilityScope.of(["tes.*"]).allows("test.skill")


async def test_a_yes_is_stored_audited_and_announced(
    db: Database, history: HistoryStore, audit: AuditLog, bus: EventBus
) -> None:
    events = EventRecorder()
    events.attach(bus)
    supervisor = make_supervisor(history, audit, bus)
    task = await stored_task(history)
    confirmation = await supervisor.request(
        task_id=task.id, step_id=task.steps[0].id, prompt="Run the demo dangerous action"
    )
    assert events.of_type(ConfirmationRequested)[0].confirmation == confirmation
    assert supervisor.pending() == [confirmation]
    assert supervisor.pending_for_task(task.id) == confirmation
    waiter = asyncio.create_task(supervisor.wait(confirmation.id))
    await asyncio.sleep(0)
    assert supervisor.respond(confirmation.id, ConfirmationAnswer.YES, "click") is True
    outcome = await waiter
    assert (outcome.answer, outcome.channel) == (ConfirmationAnswer.YES, "click")
    assert supervisor.pending() == []
    row = await confirmation_row(db, confirmation.id)
    assert (row.response, row.channel, row.prompt_text) == (
        "yes",
        "click",
        "Run the demo dangerous action",
    )
    assert row.responded_at is not None
    entries = await audit.recent(10)
    assert [e.event_type for e in entries][:2] == ["confirm.answered", "confirm.requested"]
    assert entries[0].actor == "user"
    assert entries[0].tier == "T2"


async def test_no_answer_in_time_is_a_timeout(
    db: Database, history: HistoryStore, audit: AuditLog, bus: EventBus
) -> None:
    supervisor = make_supervisor(history, audit, bus, timeout_s=0.05)
    task = await stored_task(history)
    confirmation = await supervisor.request(task_id=task.id, step_id=task.steps[0].id, prompt="x")
    outcome = await supervisor.wait(confirmation.id)
    assert (outcome.answer, outcome.channel) == (ConfirmationAnswer.TIMEOUT, "system")
    assert supervisor.respond(confirmation.id, ConfirmationAnswer.YES, "click") is False
    assert (await confirmation_row(db, confirmation.id)).response == "timeout"
    assert (await audit.recent(1))[0].actor == "system"


async def test_answers_count_once(history: HistoryStore, audit: AuditLog, bus: EventBus) -> None:
    supervisor = make_supervisor(history, audit, bus)
    task = await stored_task(history)
    confirmation = await supervisor.request(task_id=task.id, step_id=task.steps[0].id, prompt="x")
    assert supervisor.respond("unknown-id", ConfirmationAnswer.YES, "click") is False
    assert supervisor.respond(confirmation.id, ConfirmationAnswer.NO, "text") is True
    assert supervisor.respond(confirmation.id, ConfirmationAnswer.YES, "click") is False
    with pytest.raises(ValueError, match="times a confirmation out"):
        supervisor.respond(confirmation.id, ConfirmationAnswer.TIMEOUT, "click")
    assert (await supervisor.wait(confirmation.id)).answer is ConfirmationAnswer.NO


async def test_newest_pending_is_the_latest_request(
    history: HistoryStore, audit: AuditLog, bus: EventBus
) -> None:
    supervisor = make_supervisor(history, audit, bus)
    first_task, second_task = await stored_task(history), await stored_task(history)
    first = await supervisor.request(
        task_id=first_task.id, step_id=first_task.steps[0].id, prompt="a"
    )
    second = await supervisor.request(
        task_id=second_task.id, step_id=second_task.steps[0].id, prompt="b"
    )
    assert supervisor.newest_pending() == second
    assert supervisor.pending() == [first, second]
    for confirmation in (first, second):
        supervisor.respond(confirmation.id, ConfirmationAnswer.NO, "text")
        await supervisor.wait(confirmation.id)
    assert supervisor.newest_pending() is None


async def test_a_cancelled_wait_leaves_the_confirmation_unanswered(
    db: Database, history: HistoryStore, audit: AuditLog, bus: EventBus
) -> None:
    supervisor = make_supervisor(history, audit, bus)
    task = await stored_task(history)
    confirmation = await supervisor.request(task_id=task.id, step_id=task.steps[0].id, prompt="x")
    waiter = asyncio.create_task(supervisor.wait(confirmation.id))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert supervisor.pending() == []
    assert (await confirmation_row(db, confirmation.id)).response is None
