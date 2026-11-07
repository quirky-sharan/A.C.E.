"""IPC methods (ACE_MASTER_PLAN.md §5.5): name -> validated params -> async handler -> result.

S07 adds the command pipeline: ``command.submit``, ``task.list``, ``task.cancel``,
``confirm.respond`` and ``message.list``. Later stages add theirs here.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel

from ace_core.app.container import Container
from ace_core.app.logging_setup import LOG_FILE_PREFIX, LOG_FILE_SUFFIX
from ace_core.app.state import CoreState
from ace_core.brain.records import (
    ConfirmationAnswer,
    Message,
    Origin,
    PendingConfirmation,
    Task,
)
from ace_core.ipc.schemas import (
    CommandSubmitParams,
    CommandSubmitResult,
    ConfirmationInfo,
    ConfirmRespondParams,
    ConfirmRespondResult,
    CoreStateInfo,
    EmptyParams,
    HealthResult,
    LogTailParams,
    LogTailResult,
    MessageInfo,
    MessageListParams,
    MessageListResult,
    SettingsGetParams,
    SettingsGetResult,
    SettingsSetParams,
    SettingsSetResult,
    StepInfo,
    SubsystemHealthInfo,
    TaskCancelParams,
    TaskCancelResult,
    TaskInfo,
    TaskListParams,
    TaskListResult,
)

MAX_LOG_LINE_CHARS: Final = 4000


@dataclass(frozen=True, slots=True)
class MethodContext:
    container: Container


Handler = Callable[[MethodContext, Any], Awaitable[BaseModel]]


@dataclass(frozen=True, slots=True)
class MethodSpec:
    name: str
    params: type[BaseModel]
    result: type[BaseModel]
    handler: Handler
    dev_only: bool = False


def core_state_info(state: CoreState) -> CoreStateInfo:
    return CoreStateInfo(
        conversation=state.conversation,
        game_mode=state.game_mode,
        offline=state.offline,
        dnd=state.dnd,
        paused_overlay=state.paused_overlay,
    )


def health_result(container: Container) -> HealthResult:
    snapshot = container.health.snapshot()
    return HealthResult(
        overall=snapshot.overall,
        subsystems=[
            SubsystemHealthInfo(name=s.name, status=s.status, detail=s.detail, since=s.since)
            for s in snapshot.subsystems
        ],
    )


def confirmation_info(confirmation: PendingConfirmation) -> ConfirmationInfo:
    return ConfirmationInfo(
        id=confirmation.id,
        task_id=confirmation.task_id,
        step_id=confirmation.step_id,
        prompt=confirmation.prompt,
        requested_at=confirmation.requested_at,
        expires_at=confirmation.expires_at,
    )


def task_info(task: Task) -> TaskInfo:
    return TaskInfo(
        id=task.id,
        conversation_id=task.conversation_id,
        origin=task.origin,
        utterance=task.utterance,
        intent=task.intent,
        mode=task.mode,
        status=task.status,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        result_summary=task.result_summary,
        error_code=task.error_code,
        steps=[
            StepInfo(
                id=step.id,
                idx=step.idx,
                skill_id=step.skill_id,
                label=step.label,
                tier=step.tier,
                status=step.status,
                started_at=step.started_at,
                finished_at=step.finished_at,
                error_code=step.error_code,
            )
            for step in task.steps
        ],
        confirmation=confirmation_info(task.confirmation) if task.confirmation else None,
    )


def message_info(message: Message) -> MessageInfo:
    return MessageInfo(
        id=message.id,
        conversation_id=message.conversation_id,
        ts=message.ts,
        role=message.role,
        text=message.text,
        source=message.source,
        detail=message.detail,
        task_id=message.task_id,
        reply_to=message.reply_to,
    )


async def _system_health(ctx: MethodContext, _: EmptyParams) -> HealthResult:
    return health_result(ctx.container)


async def _system_state(ctx: MethodContext, _: EmptyParams) -> CoreStateInfo:
    return core_state_info(ctx.container.state.current)


async def _settings_get(ctx: MethodContext, params: SettingsGetParams) -> SettingsGetResult:
    found, value = await ctx.container.settings_store.lookup(params.key)
    return SettingsGetResult(key=params.key, found=found, value=value)


async def _settings_set(ctx: MethodContext, params: SettingsSetParams) -> SettingsSetResult:
    await ctx.container.settings_store.set(params.key, params.value, actor="user")
    return SettingsSetResult(key=params.key, saved=True)


async def _command_submit(ctx: MethodContext, params: CommandSubmitParams) -> CommandSubmitResult:
    result = await ctx.container.pipeline.submit(params.text, origin=Origin.TEXT)
    return CommandSubmitResult(
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        intent=result.intent,
        task_id=result.task_id,
    )


async def _task_list(ctx: MethodContext, params: TaskListParams) -> TaskListResult:
    tasks = await ctx.container.pipeline.list_tasks(limit=params.limit, query=params.query)
    return TaskListResult(tasks=[task_info(task) for task in tasks])


async def _task_cancel(ctx: MethodContext, params: TaskCancelParams) -> TaskCancelResult:
    return TaskCancelResult(cancelled=ctx.container.pipeline.cancel(params.task_id))


async def _confirm_respond(
    ctx: MethodContext, params: ConfirmRespondParams
) -> ConfirmRespondResult:
    accepted = ctx.container.pipeline.respond(
        params.confirmation_id, ConfirmationAnswer(params.answer), channel="click"
    )
    return ConfirmRespondResult(accepted=accepted)


async def _message_list(ctx: MethodContext, params: MessageListParams) -> MessageListResult:
    messages = await ctx.container.pipeline.recent_messages(params.limit)
    return MessageListResult(messages=[message_info(message) for message in messages])


def _tail(path: Path, count: int) -> list[str]:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            last = deque(handle, maxlen=count)
    except FileNotFoundError:
        return []
    return [line.rstrip("\n")[:MAX_LOG_LINE_CHARS] for line in last]


async def _log_tail(ctx: MethodContext, params: LogTailParams) -> LogTailResult:
    """Today's core log (already redacted when written). Dev mode only."""
    path = ctx.container.paths.logs / f"{LOG_FILE_PREFIX}{date.today():%Y%m%d}{LOG_FILE_SUFFIX}"
    return LogTailResult(lines=await asyncio.to_thread(_tail, path, params.lines))


METHODS: Final[dict[str, MethodSpec]] = {
    spec.name: spec
    for spec in (
        MethodSpec("system.health", EmptyParams, HealthResult, _system_health),
        MethodSpec("system.state.get", EmptyParams, CoreStateInfo, _system_state),
        MethodSpec("settings.get", SettingsGetParams, SettingsGetResult, _settings_get),
        MethodSpec("settings.set", SettingsSetParams, SettingsSetResult, _settings_set),
        MethodSpec("command.submit", CommandSubmitParams, CommandSubmitResult, _command_submit),
        MethodSpec("task.list", TaskListParams, TaskListResult, _task_list),
        MethodSpec("task.cancel", TaskCancelParams, TaskCancelResult, _task_cancel),
        MethodSpec("confirm.respond", ConfirmRespondParams, ConfirmRespondResult, _confirm_respond),
        MethodSpec("message.list", MessageListParams, MessageListResult, _message_list),
        MethodSpec("log.tail", LogTailParams, LogTailResult, _log_tail, dev_only=True),
    )
}
