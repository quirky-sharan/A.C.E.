"""IPC methods (ACE_MASTER_PLAN.md §5.5): name -> validated params -> async handler -> result.

Later stages add their methods here (``command.submit``, ``task.*`` ... from S07).
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
from ace_core.ipc.schemas import (
    CoreStateInfo,
    EmptyParams,
    HealthResult,
    LogTailParams,
    LogTailResult,
    SettingsGetParams,
    SettingsGetResult,
    SettingsSetParams,
    SettingsSetResult,
    SubsystemHealthInfo,
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
        MethodSpec("log.tail", LogTailParams, LogTailResult, _log_tail, dev_only=True),
    )
}
