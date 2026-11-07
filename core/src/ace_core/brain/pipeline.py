"""The command pipeline (ACE_MASTER_PLAN.md §5.3 steps 5-9, S07).

One entry point for typed commands now, and unchanged for voice (S13), routines (S32) and MCP
(S38) later: ``submit(text, origin=...)``. Each command is stored as a message, routed, and either
becomes a one-step task (run in the background, so ``submit`` returns at once), stops what is
running, answers a pending confirmation, or gets an honest "I don't know that one yet".

Every task change is stored and published as ``TaskChanged``; every reply is a ``Message`` with a
short spoken line and optional detail (``responses``). The conversation state (§5.4) follows the
work: THINKING while routing, ACTING while tasks run, AWAITING_CONFIRM while a yes / no is pending,
then back to ASLEEP. S17 grows this into the multi-step agent runtime.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final

import structlog

from ace_core.app.events import EventBus
from ace_core.app.modes import DEFAULT_MODE, MODE_SETTING, parse_mode
from ace_core.app.state import ConversationState, StateStore
from ace_core.brain import responses
from ace_core.brain.records import (
    ConfirmationAnswer,
    Message,
    MessageCreated,
    MessageRole,
    MessageSource,
    Origin,
    Step,
    StepStatus,
    Task,
    TaskChange,
    TaskChanged,
    TaskStatus,
)
from ace_core.brain.responses import Reply
from ace_core.brain.router import Route, RouteKind, Router
from ace_core.brain.supervisor import Decision, Supervisor
from ace_core.db.history import HistoryStore
from ace_core.db.ids import new_id
from ace_core.db.stores import AuditLog
from ace_core.security.scope import CapabilityScope
from ace_core.security.tiers import Tier
from ace_core.skills.base import AnySkill, SettingsAccess, SkillContext, SkillError, SkillParams
from ace_core.skills.registry import SkillRegistry

log = structlog.stdlib.get_logger(__name__)

CONVERSATION_IDLE: Final = timedelta(minutes=15)  # a longer pause starts a new conversation
MAX_LIVE_TASKS: Final = 20  # a safety valve until S17 brings the real concurrency limits
ERR_TOO_MANY: Final = "E_PIPELINE_TOO_MANY_TASKS"
ERR_PRECONDITION: Final = "E_SKILL_PRECONDITION"
ERR_TIMEOUT: Final = "E_SKILL_TIMEOUT"
ERR_VERIFY: Final = "E_SKILL_VERIFY_FAILED"
ERR_INTERNAL: Final = "E_SKILL_INTERNAL"

_MANAGED_STATES: Final = frozenset(
    {
        ConversationState.ASLEEP,
        ConversationState.THINKING,
        ConversationState.ACTING,
        ConversationState.AWAITING_CONFIRM,
    }
)
_OPEN_STEP: Final = frozenset({StepStatus.PENDING, StepStatus.RUNNING, StepStatus.WAITING_USER})


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CancelReason(StrEnum):
    STOP = "stop"  # the "stop" command: one summary reply for everything it stopped
    CANCEL = "cancel"  # task.cancel (the Stop button): the task replies itself
    SHUTDOWN = "shutdown"  # the core is stopping: the task is interrupted, no reply


class PipelineClosedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SubmitResult:
    conversation_id: str
    message_id: str
    intent: str
    task_id: str | None  # the new task, or the task a yes / no answered


@dataclass(frozen=True, slots=True)
class _Conversation:
    id: str
    source: MessageSource
    last_activity: datetime


class CommandPipeline:
    def __init__(
        self,
        *,
        registry: SkillRegistry,
        router: Router,
        supervisor: Supervisor,
        history: HistoryStore,
        audit: AuditLog,
        bus: EventBus,
        state: StateStore,
        settings: SettingsAccess,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._registry = registry
        self._router = router
        self._supervisor = supervisor
        self._history = history
        self._audit = audit
        self._bus = bus
        self._state = state
        self._settings = settings
        self._clock = clock
        self._lock = asyncio.Lock()  # one command at a time is routed and stored
        self._live: dict[str, Task] = {}
        self._runners: dict[str, asyncio.Task[None]] = {}
        self._cancel_reasons: dict[str, CancelReason] = {}
        self._conversation: _Conversation | None = None
        self._closing = False

    # ---- public API (IPC methods, later voice / routines / MCP) ----

    async def submit(self, text: str, *, origin: Origin = Origin.TEXT) -> SubmitResult:
        if self._closing:
            raise PipelineClosedError("ace-core is stopping")
        async with self._lock:
            now = self._clock()
            source = MessageSource.VOICE if origin is Origin.VOICE else MessageSource.TEXT
            conversation_id = await self._conversation_for(source, now)
            user_message = Message(
                id=new_id(),
                conversation_id=conversation_id,
                ts=now,
                role=MessageRole.USER,
                text=text,
                source=source,
            )
            await self._history.add_message(user_message)
            await self._bus.publish(MessageCreated(message=user_message))
            await self._set_thinking()
            route: Route | None = None
            task_id: str | None = None
            try:
                route = self._router.route(text)
                task_id = await self._dispatch(route, origin, conversation_id, user_message)
            except Exception:
                log.exception("command failed", intent=route.intent if route else None)
                await self._reply(conversation_id, responses.internal_error(), user_message.id)
            finally:
                await self._refresh_state()
            intent = route.intent if route is not None else "unknown"
            return SubmitResult(conversation_id, user_message.id, intent, task_id)

    def respond(
        self, confirmation_id: str, answer: ConfirmationAnswer, *, channel: str = "click"
    ) -> bool:
        """Answer a pending confirmation (e.g. the ConfirmCard buttons)."""
        return self._supervisor.respond(confirmation_id, answer, channel)

    def cancel(self, task_id: str, *, reason: CancelReason = CancelReason.CANCEL) -> bool:
        """Cancel a live task: a pending confirmation is answered "no", a running step stops."""
        if task_id not in self._live:
            return False
        self._cancel_reasons[task_id] = reason
        pending = self._supervisor.pending_for_task(task_id)
        if pending is not None:
            return self._supervisor.respond(pending.id, ConfirmationAnswer.NO, reason.value)
        runner = self._runners.get(task_id)
        if runner is not None and not runner.done():
            runner.cancel()
            return True
        self._cancel_reasons.pop(task_id, None)
        return False

    async def stop_all(self) -> int:
        """The emergency stop (§15.1 item 10, Ctrl+Alt+Esc): cancel every live task and say so.
        S17 adds releasing held keys and the foreground lock."""
        count = self._cancel_all()
        if count and self._conversation is not None:
            await self._reply(self._conversation.id, responses.stopped(count), None)
        return count

    async def list_tasks(self, *, limit: int, query: str | None = None) -> list[Task]:
        """Newest first from the database; live tasks show their current in-memory state."""
        stored = await self._history.list_tasks(limit=limit, query=query)
        return [copy.deepcopy(self._live[t.id]) if t.id in self._live else t for t in stored]

    async def recent_messages(self, limit: int) -> list[Message]:
        return await self._history.recent_messages(limit)

    async def close(self) -> None:
        """Stop accepting commands; running tasks end as ``interrupted``."""
        self._closing = True
        runners = list(self._runners.items())
        for task_id, runner in runners:
            self._cancel_reasons[task_id] = CancelReason.SHUTDOWN
            runner.cancel()
        if runners:
            await asyncio.gather(*(runner for _, runner in runners), return_exceptions=True)
        if self._conversation is not None:
            await self._history.end_conversation(
                self._conversation.id, self._conversation.last_activity
            )
            self._conversation = None

    # ---- routing ----

    async def _dispatch(
        self, route: Route, origin: Origin, conversation_id: str, user_message: Message
    ) -> str | None:
        if route.kind is RouteKind.SKILL and route.skill_id and route.params is not None:
            skill = self._registry.get(route.skill_id)
            if skill is not None:
                return await self._start_task(
                    skill, route.params, route, origin, conversation_id, user_message
                )
        if route.kind is RouteKind.STOP:
            count = self._cancel_all()
            await self._reply(conversation_id, responses.stopped(count), user_message.id)
            return None
        if route.kind is RouteKind.CONFIRM and route.answer is not None:
            pending = self._supervisor.newest_pending()
            if pending is None:
                await self._reply(conversation_id, responses.nothing_to_confirm(), user_message.id)
                return None
            self._supervisor.respond(pending.id, route.answer, user_message.source.value)
            return pending.task_id
        await self._reply(conversation_id, responses.no_match(route.utterance.raw), user_message.id)
        return None

    async def _start_task(
        self,
        skill: AnySkill,
        params: SkillParams,
        route: Route,
        origin: Origin,
        conversation_id: str,
        user_message: Message,
    ) -> str | None:
        if len(self._live) >= MAX_LIVE_TASKS:
            await self._reply(
                conversation_id,
                responses.failed("Too many tasks are still running; try again soon.", ERR_TOO_MANY),
                user_message.id,
            )
            return None
        mode = parse_mode(await self._settings.get(MODE_SETTING)) or DEFAULT_MODE
        task = Task(
            id=new_id(),
            conversation_id=conversation_id,
            origin=origin,
            utterance=route.utterance.raw,
            intent=route.intent,
            mode=mode.value,
            allowed_caps=CapabilityScope.of([skill.id]).as_list(),
            created_at=self._clock(),
        )
        task.steps.append(
            Step(
                id=new_id(),
                task_id=task.id,
                idx=0,
                skill_id=skill.id,
                label=skill.describe(params),
                params=params.model_dump(mode="json"),
                tier=skill.tier_for(params),
            )
        )
        self._live[task.id] = task
        await self._publish(task, TaskChange.CREATED)
        await self._audit.record(
            actor="user",
            event_type="task.created",
            summary=f"command: {task.utterance}",
            task_id=task.id,
            data={"intent": task.intent, "origin": origin.value},
        )
        runner = asyncio.create_task(
            self._run(task, skill, params, user_message.id), name=f"ace-task-{task.id}"
        )
        self._runners[task.id] = runner
        task_id = task.id

        def forget(_: asyncio.Task[None]) -> None:
            self._runners.pop(task_id, None)

        runner.add_done_callback(forget)
        return task.id

    # ---- running one task ----

    async def _run(self, task: Task, skill: AnySkill, params: SkillParams, reply_to: str) -> None:
        step = task.steps[0]
        ctx = SkillContext(
            task_id=task.id, step_id=step.id, origin=task.origin, utterance=task.utterance
        )
        try:
            task.status = TaskStatus.RUNNING
            task.started_at = self._clock()
            await self._publish(task, TaskChange.UPDATED)
            verdict = self._supervisor.evaluate(
                skill, params, CapabilityScope.of(task.allowed_caps)
            )
            if verdict.decision is Decision.REFUSE:
                await self._audit.record(
                    actor="ace",
                    event_type="supervisor.refused",
                    summary=f"refused: {step.label}",
                    tier=verdict.tier,
                    task_id=task.id,
                    step_id=step.id,
                    data={"skill_id": skill.id, "error_code": verdict.error_code},
                )
                await self._finish(
                    task,
                    step,
                    StepStatus.REFUSED,
                    TaskStatus.FAILED,
                    verdict.error_code,
                    responses.refused(step.label, verdict.reason or ""),
                    reply_to,
                )
                return
            if verdict.decision is Decision.CONFIRM and not await self._confirm(
                task, step, reply_to
            ):
                return
            unmet = await skill.preconditions(ctx, params)
            if unmet:
                await self._fail(task, step, ERR_PRECONDITION, "; ".join(unmet), reply_to)
                return
            step.status = StepStatus.RUNNING
            step.started_at = self._clock()
            task.status = TaskStatus.RUNNING
            await self._publish(task, TaskChange.UPDATED)
            await self._refresh_state()
            try:
                result = await asyncio.wait_for(skill.execute(ctx, params), timeout=skill.timeout_s)
            except SkillError as exc:
                await self._fail(task, step, exc.code, exc.message, reply_to)
                return
            except TimeoutError:
                await self._fail(
                    task, step, ERR_TIMEOUT, "It took too long, so I stopped waiting.", reply_to
                )
                return
            step.observation = dict(result.data)
            task.status = TaskStatus.VERIFYING
            await self._publish(task, TaskChange.UPDATED)
            check = await skill.verify(ctx, params, result)
            if not check.ok:
                reason = check.reason or "the check failed"
                await self._fail(
                    task, step, ERR_VERIFY, f"I couldn't confirm it worked: {reason}.", reply_to
                )
                return
            await self._finish(
                task,
                step,
                StepStatus.SUCCEEDED,
                TaskStatus.SUCCEEDED,
                None,
                responses.succeeded(result),
                reply_to,
            )
        except asyncio.CancelledError:
            if not task.status.finished:
                reason = self._cancel_reasons.pop(task.id, CancelReason.SHUTDOWN)
                await self._finish_cancelled(task, step, reason, None, reply_to)
            raise
        except Exception:
            log.exception("task failed", task_id=task.id, skill_id=skill.id)
            if not task.status.finished:
                await self._finish(
                    task,
                    step,
                    StepStatus.FAILED,
                    TaskStatus.FAILED,
                    ERR_INTERNAL,
                    responses.internal_error(),
                    reply_to,
                )

    async def _confirm(self, task: Task, step: Step, reply_to: str) -> bool:
        """Ask Sharan (T2). True on "yes"; otherwise the task is finished as cancelled."""
        confirmation = await self._supervisor.request(
            task_id=task.id, step_id=step.id, prompt=step.label
        )
        task.status = TaskStatus.WAITING_USER
        step.status = StepStatus.WAITING_USER
        task.confirmation = confirmation
        await self._publish(task, TaskChange.UPDATED)
        await self._reply(
            task.conversation_id,
            responses.confirm_prompt(step.label, self._supervisor.timeout_s),
            reply_to,
            task_id=task.id,
        )
        await self._refresh_state()
        outcome = await self._supervisor.wait(confirmation.id)
        task.confirmation = None
        if outcome.answer is ConfirmationAnswer.YES:
            return True
        reason = self._cancel_reasons.pop(task.id, None)
        await self._finish_cancelled(task, step, reason, outcome.answer, reply_to)
        return False

    async def _fail(self, task: Task, step: Step, code: str, message: str, reply_to: str) -> None:
        await self._finish(
            task,
            step,
            StepStatus.FAILED,
            TaskStatus.FAILED,
            code,
            responses.failed(message, code),
            reply_to,
        )

    async def _finish_cancelled(
        self,
        task: Task,
        step: Step,
        reason: CancelReason | None,
        answer: ConfirmationAnswer | None,
        reply_to: str,
    ) -> None:
        if reason is CancelReason.SHUTDOWN:
            status, reply, summary = (
                TaskStatus.INTERRUPTED,
                None,
                "Interrupted because ACE was stopping.",
            )
        elif reason is CancelReason.STOP:
            status, reply, summary = TaskStatus.CANCELLED, None, "Stopped."
        else:
            reply = responses.cancelled(answer, self._supervisor.timeout_s)
            status, summary = TaskStatus.CANCELLED, reply.spoken
        if reason in (CancelReason.STOP, CancelReason.CANCEL):
            await self._audit.record(
                actor="user",
                event_type="task.cancelled",
                summary=f"cancelled: {step.label}",
                task_id=task.id,
                data={"reason": reason.value if reason else None},
            )
        await self._finish(
            task, step, StepStatus.CANCELLED, status, None, reply, reply_to, summary=summary
        )

    async def _finish(
        self,
        task: Task,
        step: Step,
        step_status: StepStatus,
        status: TaskStatus,
        error_code: str | None,
        reply: Reply | None,
        reply_to: str,
        *,
        summary: str | None = None,
    ) -> None:
        now = self._clock()
        executed = step.started_at is not None
        if step.status in _OPEN_STEP:
            step.status = step_status
            step.finished_at = now
            step.error_code = error_code
        task.status = status
        task.finished_at = now
        task.error_code = error_code
        task.confirmation = None
        task.result_summary = summary if summary is not None else (reply.spoken if reply else None)
        self._live.pop(task.id, None)
        self._cancel_reasons.pop(task.id, None)
        await self._publish(task, TaskChange.FINISHED)
        if executed and step.tier is not Tier.T0:  # T1+ "run + log" (§15.3)
            await self._audit.record(
                actor="ace",
                event_type="step.executed",
                summary=f"{step.status.value}: {step.label}",
                tier=step.tier,
                task_id=task.id,
                step_id=step.id,
                data={
                    "skill_id": step.skill_id,
                    "status": step.status.value,
                    "error_code": error_code,
                },
            )
        if reply is not None:
            await self._reply(task.conversation_id, reply, reply_to, task_id=task.id)
        await self._refresh_state()

    # ---- helpers ----

    def _cancel_all(self) -> int:
        return sum(
            1 for task_id in list(self._live) if self.cancel(task_id, reason=CancelReason.STOP)
        )

    async def _publish(self, task: Task, change: TaskChange) -> None:
        await self._history.save_task(task)
        await self._bus.publish(TaskChanged(change=change, task=copy.deepcopy(task)))

    async def _reply(
        self,
        conversation_id: str | None,
        reply: Reply,
        reply_to: str | None,
        *,
        task_id: str | None = None,
    ) -> None:
        if conversation_id is None:
            return
        current = self._conversation
        source = (
            current.source
            if current is not None and current.id == conversation_id
            else MessageSource.TEXT
        )
        message = Message(
            id=new_id(),
            conversation_id=conversation_id,
            ts=self._clock(),
            role=MessageRole.ACE,
            text=reply.spoken,
            source=source,
            detail=reply.detail,
            task_id=task_id,
            reply_to=reply_to,
        )
        await self._history.add_message(message)
        await self._bus.publish(MessageCreated(message=message))

    async def _conversation_for(self, source: MessageSource, now: datetime) -> str:
        current = self._conversation
        if (
            current is not None
            and current.source is source
            and now - current.last_activity <= CONVERSATION_IDLE
        ):
            self._conversation = dataclasses.replace(current, last_activity=now)
            return current.id
        if current is not None:
            await self._history.end_conversation(current.id, current.last_activity)
        conversation_id = new_id()
        await self._history.start_conversation(
            conversation_id, channel=source.value, started_at=now
        )
        self._conversation = _Conversation(conversation_id, source, now)
        return conversation_id

    async def _set_thinking(self) -> None:
        if self._state.current.conversation in (ConversationState.ASLEEP, ConversationState.ACTING):
            await self._state.update(conversation=ConversationState.THINKING)

    async def _refresh_state(self) -> None:
        current = self._state.current.conversation
        if current not in _MANAGED_STATES:
            return  # e.g. MUTED or DICTATING: owned by the voice stages
        if self._supervisor.pending():
            target = ConversationState.AWAITING_CONFIRM
        elif self._live:
            target = ConversationState.ACTING
        else:
            target = ConversationState.ASLEEP
        if target is not current:
            await self._state.update(conversation=target)
