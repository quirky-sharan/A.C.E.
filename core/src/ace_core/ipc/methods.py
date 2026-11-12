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
    PendingClarification,
    PendingConfirmation,
    Task,
)
from ace_core.ipc.schemas import (
    AppInfo,
    AppsListParams,
    AppsListResult,
    AppsRefreshResult,
    AudioDeviceInfo,
    ClarificationInfo,
    ClarifyOptionInfo,
    ClarifyRespondParams,
    ClarifyRespondResult,
    CommandSubmitParams,
    CommandSubmitResult,
    ConfirmationInfo,
    ConfirmRespondParams,
    ConfirmRespondResult,
    CoreStateInfo,
    DevicesEarconParams,
    DevicesMuteParams,
    DevicesMuteResult,
    DevicesPlayResult,
    DevicesRecordParams,
    DevicesRecordResult,
    DevicesResult,
    DevicesSelectParams,
    DevicesSelectResult,
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
from ace_core.voice.audio import MicMutedError
from ace_core.voice.devices import AudioDeviceError
from ace_core.voice.dsp import CAPTURE_RATE, peak, rms_level

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


def clarification_info(question: PendingClarification) -> ClarificationInfo:
    return ClarificationInfo(
        id=question.id,
        task_id=question.task_id,
        step_id=question.step_id,
        question=question.question,
        options=[ClarifyOptionInfo(id=option, label=label) for option, label in question.options],
        requested_at=question.requested_at,
        expires_at=question.expires_at,
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
        clarification=clarification_info(task.clarification) if task.clarification else None,
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


async def _clarify_respond(
    ctx: MethodContext, params: ClarifyRespondParams
) -> ClarifyRespondResult:
    accepted = ctx.container.pipeline.answer_clarification(
        params.clarification_id, params.option_id
    )
    return ClarifyRespondResult(accepted=accepted)


async def _apps_list(ctx: MethodContext, params: AppsListParams) -> AppsListResult:
    ports = ctx.container.apps
    if ports is None:
        return AppsListResult(available=False, apps=[])
    wanted = (params.query or "").casefold()
    apps = [app for app in ports.index.apps if wanted in app.normalized_name]
    apps.sort(key=lambda app: (-app.launch_count, app.normalized_name))
    return AppsListResult(
        available=True,
        apps=[
            AppInfo(name=a.name, kind=a.kind.value, target=a.target, launch_count=a.launch_count)
            for a in apps[: params.limit]
        ],
    )


async def _apps_refresh(ctx: MethodContext, _: EmptyParams) -> AppsRefreshResult:
    ports = ctx.container.apps
    return AppsRefreshResult(count=await ports.index.refresh() if ports is not None else 0)


NO_AUDIO: Final = "Audio is not available on this system."


async def _devices_list(ctx: MethodContext, _: EmptyParams) -> DevicesResult:
    audio = ctx.container.audio
    if audio is None:
        return DevicesResult(
            available=False,
            muted=False,
            capturing=False,
            input=None,
            output=None,
            inputs=[],
            outputs=[],
        )
    devices = await audio.devices()
    chosen_in, chosen_out = await audio.selection()
    return DevicesResult(
        available=True,
        muted=audio.muted,
        capturing=audio.capturing,
        input=chosen_in,
        output=chosen_out,
        inputs=[
            AudioDeviceInfo(name=d.name, is_default=d.is_default) for d in devices if d.is_input
        ],
        outputs=[
            AudioDeviceInfo(name=d.name, is_default=d.is_default) for d in devices if not d.is_input
        ],
    )


async def _devices_select(ctx: MethodContext, params: DevicesSelectParams) -> DevicesSelectResult:
    audio = ctx.container.audio
    if audio is None:
        return DevicesSelectResult(saved=False)
    await audio.select(is_input=params.kind == "input", name=params.name)
    return DevicesSelectResult(saved=True)


async def _devices_record(ctx: MethodContext, params: DevicesRecordParams) -> DevicesRecordResult:
    audio = ctx.container.audio
    if audio is None:
        return DevicesRecordResult(ok=False, error=NO_AUDIO, seconds=0, peak=0, level=0)
    try:
        samples = await audio.record(params.seconds)
    except (MicMutedError, AudioDeviceError) as exc:
        return DevicesRecordResult(ok=False, error=str(exc), seconds=0, peak=0, level=0)
    return DevicesRecordResult(
        ok=True,
        error=None,
        seconds=round(len(samples) / CAPTURE_RATE, 2),
        peak=round(peak(samples), 3),
        level=round(rms_level(samples), 3),
    )


async def _devices_play(ctx: MethodContext, _: EmptyParams) -> DevicesPlayResult:
    audio = ctx.container.audio
    if audio is None:
        return DevicesPlayResult(ok=False, error=NO_AUDIO, seconds=0)
    try:
        seconds = await audio.play_recording()
    except AudioDeviceError as exc:
        return DevicesPlayResult(ok=False, error=str(exc), seconds=0)
    if seconds == 0:
        return DevicesPlayResult(ok=False, error="Nothing has been recorded yet.", seconds=0)
    return DevicesPlayResult(ok=True, error=None, seconds=round(seconds, 2))


async def _devices_stop(ctx: MethodContext, _: EmptyParams) -> DevicesPlayResult:
    audio = ctx.container.audio
    if audio is not None:
        await audio.stop_playback()
    return DevicesPlayResult(ok=audio is not None, error=None if audio else NO_AUDIO, seconds=0)


async def _devices_earcon(ctx: MethodContext, params: DevicesEarconParams) -> DevicesPlayResult:
    audio = ctx.container.audio
    if audio is None:
        return DevicesPlayResult(ok=False, error=NO_AUDIO, seconds=0)
    try:
        await audio.earcon(params.name)
    except AudioDeviceError as exc:
        return DevicesPlayResult(ok=False, error=str(exc), seconds=0)
    return DevicesPlayResult(ok=True, error=None, seconds=0)


async def _devices_mute(ctx: MethodContext, params: DevicesMuteParams) -> DevicesMuteResult:
    audio = ctx.container.audio
    if audio is None:
        return DevicesMuteResult(muted=False)
    await audio.set_muted(params.muted)
    return DevicesMuteResult(muted=audio.muted)


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
        MethodSpec("clarify.respond", ClarifyRespondParams, ClarifyRespondResult, _clarify_respond),
        MethodSpec("message.list", MessageListParams, MessageListResult, _message_list),
        MethodSpec("apps.list", AppsListParams, AppsListResult, _apps_list),
        MethodSpec("apps.refresh", EmptyParams, AppsRefreshResult, _apps_refresh),
        MethodSpec("devices.list", EmptyParams, DevicesResult, _devices_list),
        MethodSpec("devices.select", DevicesSelectParams, DevicesSelectResult, _devices_select),
        MethodSpec(
            "devices.record_test", DevicesRecordParams, DevicesRecordResult, _devices_record
        ),
        MethodSpec("devices.play_test", EmptyParams, DevicesPlayResult, _devices_play),
        MethodSpec("devices.stop", EmptyParams, DevicesPlayResult, _devices_stop),
        MethodSpec("devices.earcon", DevicesEarconParams, DevicesPlayResult, _devices_earcon),
        MethodSpec("devices.mute", DevicesMuteParams, DevicesMuteResult, _devices_mute),
        MethodSpec("log.tail", LogTailParams, LogTailResult, _log_tail, dev_only=True),
    )
}
