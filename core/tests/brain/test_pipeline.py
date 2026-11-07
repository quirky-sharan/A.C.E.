"""The command pipeline end to end with real storage: typed command -> route -> Supervisor ->
skill -> task records, replies, audit and conversation state (S07 acceptance, §5.3)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import pytest
from brain_fakes import ConfigurableSkill, Env, EnvFactory, EventRecorder
from sqlalchemy import select
from sqlalchemy.orm import Session

from ace_core.app.events import EventBus
from ace_core.app.modes import MODE_SETTING
from ace_core.app.state import ConversationState, StateChanged, StateStore
from ace_core.brain.grammar import DEFAULT_RULES, GrammarRule, rule
from ace_core.brain.pipeline import (
    ERR_INTERNAL,
    ERR_PRECONDITION,
    ERR_TIMEOUT,
    ERR_VERIFY,
    CommandPipeline,
    PipelineClosedError,
)
from ace_core.brain.records import (
    ConfirmationAnswer,
    ConfirmationRequested,
    Message,
    MessageCreated,
    MessageRole,
    StepStatus,
    Task,
    TaskChange,
    TaskChanged,
    TaskStatus,
)
from ace_core.brain.router import Router
from ace_core.brain.supervisor import ERR_FORBIDDEN, Supervisor
from ace_core.db.database import Database
from ace_core.db.history import HistoryStore
from ace_core.db.models import ConfirmationRow, ConversationRow
from ace_core.db.stores import AuditLog, SettingsStore
from ace_core.security.tiers import Tier
from ace_core.skills.apps import NOT_READY
from ace_core.skills.base import AnySkill
from ace_core.skills.catalog import build_registry


@pytest.fixture
async def make_env(
    db: Database, audit: AuditLog, history: HistoryStore
) -> AsyncIterator[EnvFactory]:
    """Builds the pipeline with every S07 skill (dev mode) plus optional test skills."""
    built: list[Env] = []

    def factory(
        *,
        timeout_s: float = 30.0,
        extra_skills: tuple[AnySkill, ...] = (),
        extra_rules: tuple[GrammarRule, ...] = (),
        clock: Callable[[], datetime] | None = None,
    ) -> Env:
        bus = EventBus()
        events = EventRecorder()
        events.attach(bus)
        state = StateStore(bus)
        settings = SettingsStore(db, audit, bus=bus)
        registry = build_registry(settings=settings, dev=True)
        for skill in extra_skills:
            registry.register(skill)
        supervisor = Supervisor(history=history, audit=audit, bus=bus, timeout_s=timeout_s)
        options = {"clock": clock} if clock is not None else {}
        pipeline = CommandPipeline(
            registry=registry,
            router=Router(registry, (*extra_rules, *DEFAULT_RULES)),
            supervisor=supervisor,
            history=history,
            audit=audit,
            bus=bus,
            state=state,
            settings=settings,
            **options,
        )
        env = Env(bus, state, history, audit, settings, supervisor, pipeline, events)
        built.append(env)
        return env

    yield factory
    for env in built:
        await env.pipeline.close()


async def eventually(check: Callable[[], bool], timeout: float = 3.0) -> None:
    async with asyncio.timeout(timeout):
        while not check():
            await asyncio.sleep(0.01)


async def finished(env: Env, task_id: str | None) -> Task:
    assert task_id is not None
    event = await env.events.wait_for(
        TaskChanged, lambda e: e.task.id == task_id and e.change is TaskChange.FINISHED
    )
    return event.task


async def ace_reply(env: Env, predicate: Callable[[Message], bool]) -> Message:
    event = await env.events.wait_for(
        MessageCreated, lambda e: e.message.role is MessageRole.ACE and predicate(e.message)
    )
    return event.message


def replies(env: Env) -> list[Message]:
    return [
        e.message for e in env.events.of_type(MessageCreated) if e.message.role is MessageRole.ACE
    ]


async def confirmation_rows(db: Database) -> list[ConfirmationRow]:
    def load(session: Session) -> list[ConfirmationRow]:
        rows = list(session.scalars(select(ConfirmationRow)))
        for row in rows:
            session.expunge(row)
        return rows

    return await db.run(load)


async def audit_types(env: Env) -> list[str]:
    return [entry.event_type for entry in await env.audit.recent(100)]


async def test_echo_runs_end_to_end(make_env: EnvFactory) -> None:
    env = make_env()
    result = await env.pipeline.submit("echo hello")
    assert result.intent == "system.echo"
    task = await finished(env, result.task_id)
    assert task.status is TaskStatus.SUCCEEDED
    assert task.steps[0].status is StepStatus.SUCCEEDED
    assert task.steps[0].tier is Tier.T0
    assert task.result_summary == "hello"
    reply = await ace_reply(env, lambda m: m.task_id == result.task_id)
    assert (reply.text, reply.detail, reply.reply_to) == (
        "hello",
        'Echo: "hello"',
        result.message_id,
    )
    await eventually(lambda: env.state.current.conversation is ConversationState.ASLEEP)
    states = [event.state.conversation for event in env.events.of_type(StateChanged)]
    assert states[0] is ConversationState.THINKING
    assert ConversationState.ACTING in states
    stored = await env.history.list_tasks(limit=5)
    assert stored[0].id == task.id
    assert stored[0].status is TaskStatus.SUCCEEDED
    assert stored[0].steps[0].observation == {"text": "hello"}
    messages = await env.history.recent_messages(10)
    assert [(m.role, m.text) for m in messages] == [
        (MessageRole.USER, "echo hello"),
        (MessageRole.ACE, "hello"),
    ]
    types = await audit_types(env)
    assert "task.created" in types
    assert "step.executed" not in types  # T0 runs without an audit entry


async def test_a_typed_yes_runs_a_dangerous_action(make_env: EnvFactory, db: Database) -> None:
    env = make_env()
    result = await env.pipeline.submit("demo dangerous")
    requested = await env.events.wait_for(ConfirmationRequested)
    assert requested.confirmation.task_id == result.task_id
    await eventually(lambda: env.state.current.conversation is ConversationState.AWAITING_CONFIRM)
    prompt = await ace_reply(env, lambda m: m.task_id == result.task_id)
    assert prompt.text.endswith("Should I go ahead? Yes or no.")
    live = await env.pipeline.list_tasks(limit=5)
    assert live[0].status is TaskStatus.WAITING_USER
    assert live[0].confirmation == requested.confirmation

    answer = await env.pipeline.submit("haan")
    assert (answer.intent, answer.task_id) == ("control.yes", result.task_id)
    task = await finished(env, result.task_id)
    assert task.status is TaskStatus.SUCCEEDED
    assert task.confirmation is None
    done = await ace_reply(env, lambda m: m.task_id == result.task_id and m.text.startswith("Done"))
    assert done.reply_to == result.message_id
    [row] = await confirmation_rows(db)
    assert (row.response, row.channel) == ("yes", "text")
    types = await audit_types(env)
    assert {"confirm.requested", "confirm.answered", "step.executed"} <= set(types)
    await eventually(lambda: env.state.current.conversation is ConversationState.ASLEEP)


async def test_no_cancels_and_is_logged(make_env: EnvFactory, db: Database) -> None:
    env = make_env()
    result = await env.pipeline.submit("demo dangerous")
    requested = await env.events.wait_for(ConfirmationRequested)
    assert env.pipeline.respond(requested.confirmation.id, ConfirmationAnswer.NO, channel="click")
    task = await finished(env, result.task_id)
    assert task.status is TaskStatus.CANCELLED
    assert task.steps[0].status is StepStatus.CANCELLED
    assert task.steps[0].observation == {}  # it never ran
    await ace_reply(env, lambda m: m.text == "Okay, cancelled.")
    [row] = await confirmation_rows(db)
    assert (row.response, row.channel) == ("no", "click")
    types = await audit_types(env)
    assert "confirm.answered" in types
    assert "step.executed" not in types


async def test_no_answer_cancels_after_the_timeout(make_env: EnvFactory, db: Database) -> None:
    env = make_env(timeout_s=0.1)
    result = await env.pipeline.submit("demo dangerous")
    task = await finished(env, result.task_id)
    assert task.status is TaskStatus.CANCELLED
    assert task.result_summary == "No answer, so I cancelled it."
    [row] = await confirmation_rows(db)
    assert (row.response, row.channel) == ("timeout", "system")


async def test_forbidden_is_refused_with_an_explanation(make_env: EnvFactory) -> None:
    env = make_env()
    result = await env.pipeline.submit("demo forbidden")
    task = await finished(env, result.task_id)
    assert task.status is TaskStatus.FAILED
    assert task.error_code == ERR_FORBIDDEN  # not E_SKILL_FORBIDDEN: the skill never ran
    assert task.steps[0].status is StepStatus.REFUSED
    reply = await ace_reply(env, lambda m: m.task_id == result.task_id)
    assert "forbidden list" in reply.text
    assert reply.detail is not None
    assert reply.detail.startswith("Refused: Run the demo forbidden action.")
    entries = await env.audit.recent(20, event_type="supervisor.refused")
    assert entries[0].tier == "T3"


async def test_stop_cancels_a_waiting_task_with_one_reply(
    make_env: EnvFactory, db: Database
) -> None:
    env = make_env()
    result = await env.pipeline.submit("demo dangerous")
    await env.events.wait_for(ConfirmationRequested)
    stop = await env.pipeline.submit("stop")
    assert (stop.intent, stop.task_id) == ("control.stop", None)
    task = await finished(env, result.task_id)
    assert task.status is TaskStatus.CANCELLED
    assert task.result_summary == "Stopped."
    await ace_reply(env, lambda m: m.reply_to == stop.message_id)
    await asyncio.sleep(0.05)
    assert [m.text for m in replies(env) if m.text in ("Stopped.", "Okay, cancelled.")] == [
        "Stopped."
    ]
    [row] = await confirmation_rows(db)
    assert (row.response, row.channel) == ("no", "stop")
    assert "task.cancelled" in await audit_types(env)


async def test_control_words_without_work_get_a_plain_answer(make_env: EnvFactory) -> None:
    env = make_env()
    stop = await env.pipeline.submit("stop")
    assert (await ace_reply(env, lambda m: m.reply_to == stop.message_id)).text == (
        "Nothing to stop, boss."
    )
    yes = await env.pipeline.submit("yes")
    assert yes.task_id is None
    assert (await ace_reply(env, lambda m: m.reply_to == yes.message_id)).text.startswith(
        "There's nothing waiting"
    )
    unknown = await env.pipeline.submit("what's the weather")
    assert (unknown.intent, unknown.task_id) == ("unknown", None)
    reply = await ace_reply(env, lambda m: m.reply_to == unknown.message_id)
    assert reply.text.startswith("Sorry boss, I don't know that one yet.")
    assert await env.history.list_tasks(limit=5) == []


async def test_mode_switch_is_stored_and_used_by_new_tasks(make_env: EnvFactory) -> None:
    env = make_env()
    result = await env.pipeline.submit("paranoid mode")
    task = await finished(env, result.task_id)
    assert task.status is TaskStatus.SUCCEEDED
    assert await env.settings.get(MODE_SETTING) == "paranoid"
    entries = await env.audit.recent(20, event_type="step.executed")
    assert entries[0].tier == "T1"
    echo = await env.pipeline.submit("echo hi")
    assert (await finished(env, echo.task_id)).mode == "paranoid"


async def test_app_commands_say_when_they_arrive(make_env: EnvFactory) -> None:
    env = make_env()
    result = await env.pipeline.submit("open spotify")
    task = await finished(env, result.task_id)
    assert (task.status, task.error_code) == (TaskStatus.FAILED, NOT_READY)
    reply = await ace_reply(env, lambda m: m.task_id == result.task_id)
    assert "Opening apps arrives in stage S08." in reply.text


async def test_cancel_stops_a_running_step(make_env: EnvFactory) -> None:
    slow = ConfigurableSkill("test.slow", delay_s=5)
    env = make_env(extra_skills=(slow,), extra_rules=(rule("test.slow", "slow"),))
    result = await env.pipeline.submit("slow")
    assert result.task_id is not None
    await eventually(lambda: slow.calls == 1)
    assert env.state.current.conversation is ConversationState.ACTING
    assert env.pipeline.cancel(result.task_id) is True
    task = await finished(env, result.task_id)
    assert task.status is TaskStatus.CANCELLED
    await ace_reply(env, lambda m: m.text == "Okay, cancelled.")
    assert env.pipeline.cancel(result.task_id) is False
    assert "task.cancelled" in await audit_types(env)


@pytest.mark.parametrize(
    ("skill", "code", "says"),
    [
        (ConfigurableSkill("test.skill", delay_s=5, timeout_s=0.05), ERR_TIMEOUT, "took too long"),
        (ConfigurableSkill("test.skill", verify_ok=False), ERR_VERIFY, "test check failed"),
        (
            ConfigurableSkill("test.skill", unmet=["it is not installed"]),
            ERR_PRECONDITION,
            "not installed",
        ),
        (ConfigurableSkill("test.skill", error=RuntimeError("boom")), ERR_INTERNAL, "my side"),
    ],
)
async def test_failures_are_reported(
    make_env: EnvFactory, skill: ConfigurableSkill, code: str, says: str
) -> None:
    env = make_env(extra_skills=(skill,), extra_rules=(rule("test.skill", "go"),))
    result = await env.pipeline.submit("go")
    task = await finished(env, result.task_id)
    assert (task.status, task.error_code) == (TaskStatus.FAILED, code)
    assert task.steps[0].status is StepStatus.FAILED
    reply = await ace_reply(env, lambda m: m.task_id == result.task_id)
    assert says in reply.text
    if code == ERR_PRECONDITION:
        assert skill.calls == 0


async def test_shutdown_interrupts_waiting_tasks(make_env: EnvFactory, db: Database) -> None:
    env = make_env()
    result = await env.pipeline.submit("demo dangerous")
    await ace_reply(env, lambda m: m.task_id == result.task_id)  # the question
    await env.pipeline.close()
    assert result.task_id is not None
    stored = await env.history.get_task(result.task_id)
    assert stored is not None
    assert stored.status is TaskStatus.INTERRUPTED
    assert stored.result_summary == "Interrupted because ACE was stopping."
    [row] = await confirmation_rows(db)
    assert row.response is None
    assert len([m for m in replies(env) if m.task_id == result.task_id]) == 1  # only the question
    with pytest.raises(PipelineClosedError):
        await env.pipeline.submit("echo hi")


async def test_a_long_pause_starts_a_new_conversation(make_env: EnvFactory, db: Database) -> None:
    now = [datetime(2026, 11, 7, 12, 0, tzinfo=UTC)]
    env = make_env(clock=lambda: now[0])
    first = await env.pipeline.submit("stop")
    second = await env.pipeline.submit("stop")
    assert first.conversation_id == second.conversation_id
    now[0] += timedelta(minutes=16)
    third = await env.pipeline.submit("stop")
    assert third.conversation_id != first.conversation_id

    def load(session: Session) -> dict[str, datetime | None]:
        return {row.id: row.ended_at for row in session.scalars(select(ConversationRow))}

    ended = await db.run(load)
    assert ended[first.conversation_id] == datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
    assert ended[third.conversation_id] is None


async def test_states_owned_by_other_stages_are_left_alone(make_env: EnvFactory) -> None:
    env = make_env()
    await env.state.update(conversation=ConversationState.MUTED)
    result = await env.pipeline.submit("echo hi")
    await finished(env, result.task_id)
    assert env.state.current.conversation is ConversationState.MUTED
