"""Apps & windows (§10.2, S08): open, close and switch to apps by name.

The skills only decide and verify; every Windows call goes through the ports in :class:`AppsPorts`
(the Win32 adapters in ``ace_core.os.win32`` on Windows, fakes in the tests). Without ports (not
Windows) the skills say that app control is not available here.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import Field

from ace_core.os.base import Launcher, LaunchError, WindowControl, WindowInfo
from ace_core.security.tiers import Tier
from ace_core.skills.app_index import AppIndex, IndexedApp
from ace_core.skills.base import (
    Choice,
    NeedsChoice,
    RuleCheckResult,
    Skill,
    SkillContext,
    SkillError,
    SkillParams,
    StepResult,
)
from ace_core.skills.resolve import resolve

NOT_READY: Final = "E_SKILL_NOT_READY"
NOT_FOUND: Final = "E_APP_NOT_FOUND"
NOT_RUNNING: Final = "E_APP_NOT_RUNNING"
ELEVATED: Final = "E_APP_ELEVATED"
NOT_VISIBLE: Final = "E_APP_NOT_VISIBLE"
FOCUS_DENIED: Final = "E_FOCUS_DENIED"
STILL_OPEN: Final = "E_APP_STILL_OPEN"
LAUNCH_FAILED: Final = "E_LAUNCH_FAILED"

INDEX_WAIT_S: Final = 5.0
WINDOW_WAIT_S: Final = 8.0
CLOSE_WAIT_S: Final = 5.0
POLL_S: Final = 0.1


@dataclass(frozen=True, slots=True)
class AppsPorts:
    index: AppIndex
    windows: WindowControl
    launcher: Launcher


class AppParams(SkillParams):
    name: str = Field(min_length=1, max_length=100)
    target: str | None = Field(default=None, max_length=500)  # set by a clarification choice


class CloseParams(AppParams):
    force: bool = False  # end the app's processes instead of asking its windows to close (T2)


def _windows_of(app: IndexedApp, windows: Sequence[WindowInfo]) -> list[WindowInfo]:
    return [window for window in windows if app.owns(window)]


def _by_target(apps: Sequence[IndexedApp], target: str) -> IndexedApp | None:
    return next((app for app in apps if app.target == target), None)


async def _ready(ports: AppsPorts) -> None:
    if not await ports.index.wait_ready(INDEX_WAIT_S):
        raise SkillError(NOT_READY, "The app list is not ready yet. Try again in a moment.")


def _pick(params: AppParams, apps: Sequence[IndexedApp], running: set[str]) -> IndexedApp:
    """The app Sharan meant: the chosen one after a clarification, else the best match. Raises
    ``NeedsChoice`` when the top matches are too close to call."""
    if params.target is not None:
        app = _by_target(apps, params.target)
        if app is None:
            raise SkillError(NOT_FOUND, f"I can no longer find {params.name}.")
        return app
    resolution = resolve(params.name, apps, running=running)
    if resolution.best is None:
        raise SkillError(NOT_FOUND, f"I couldn't find an app called {params.name}.")
    if resolution.ambiguous:
        choices = [
            Choice(id=c.app.target, label=c.app.name, params={"target": c.app.target})
            for c in resolution.candidates
        ]
        raise NeedsChoice(f"Which {params.name} did you mean?", choices)
    return resolution.best


async def _wait_for(check: Callable[[], Awaitable[bool]], timeout: float) -> bool:
    """Poll an async predicate until it is true or the timeout passes."""
    deadline = time.monotonic() + timeout
    while True:
        if await check():
            return True
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(POLL_S)


class _AppsSkill[P: AppParams](Skill[P]):
    params_model: type[P]
    unavailable: str = "App control is not available on this system."

    def __init__(self, ports: AppsPorts | None) -> None:
        self._ports = ports

    def _need(self) -> AppsPorts:
        if self._ports is None:
            raise SkillError(NOT_READY, self.unavailable)
        return self._ports

    async def _windows_and_running(self, ports: AppsPorts) -> tuple[list[WindowInfo], set[str]]:
        windows = await ports.windows.windows()
        running = {app.target for app in ports.index.apps if _windows_of(app, windows)}
        return windows, running


class AppsOpenSkill(_AppsSkill[AppParams]):
    id = "apps.open"
    description = "Open an app by name"
    params_model = AppParams
    timeout_s = WINDOW_WAIT_S + INDEX_WAIT_S + 4.0
    examples = ("open spotify", "spotify khol do")

    def tier_for(self, params: AppParams) -> Tier:
        return Tier.T1

    def describe(self, params: AppParams) -> str:
        return f"Open {params.name}"

    async def execute(self, ctx: SkillContext, params: AppParams) -> StepResult:
        ports = self._need()
        await _ready(ports)
        windows, running = await self._windows_and_running(ports)
        app = _pick(params, ports.index.apps, running)
        was_open = bool(_windows_of(app, windows))
        started = time.monotonic()
        try:
            await ports.launcher.launch(app.target)
        except LaunchError as exc:
            raise SkillError(LAUNCH_FAILED, f"I couldn't start {app.name}: {exc}") from exc

        async def visible() -> bool:
            return bool(_windows_of(app, await ports.windows.windows()))

        if not await _wait_for(visible, WINDOW_WAIT_S):
            raise SkillError(NOT_VISIBLE, f"{app.name} started, but no window appeared.")
        elapsed_ms = round((time.monotonic() - started) * 1000)
        owned = _windows_of(app, await ports.windows.windows())
        front = await ports.windows.foreground()
        if owned and all(window.hwnd != front for window in owned):
            await ports.windows.focus(owned[0].hwnd)  # e.g. it was open behind other windows
        await ports.index.note_launch(app)
        spoken = (
            f"{app.name} was already open; it's in front now."
            if was_open
            else f"Opened {app.name}."
        )
        return StepResult(
            spoken=spoken,
            detail=f"{app.name}: a window was visible after {elapsed_ms} ms.",
            data={"target": app.target, "elapsed_ms": elapsed_ms, "was_open": was_open},
        )

    async def verify(
        self, ctx: SkillContext, params: AppParams, result: StepResult
    ) -> RuleCheckResult:
        ports = self._need()
        app = _by_target(ports.index.apps, str(result.data.get("target", "")))
        if app is None:
            return RuleCheckResult(False, "the app is not in the index")
        ok = bool(_windows_of(app, await ports.windows.windows()))
        return RuleCheckResult(ok, None if ok else f"no window of {app.name} is open")


class AppsCloseSkill(_AppsSkill[CloseParams]):
    id = "apps.close"
    description = "Close an app by name (force ends its processes, T2)"
    params_model = CloseParams
    timeout_s = CLOSE_WAIT_S + 6.0
    examples = ("close chrome", "chrome band karo", "force close notepad")

    def tier_for(self, params: CloseParams) -> Tier:
        return Tier.T2 if params.force else Tier.T1

    def describe(self, params: CloseParams) -> str:
        if params.force:
            return f"Force close {params.name}: all its processes end and unsaved work is lost"
        return f"Close {params.name}"

    async def execute(self, ctx: SkillContext, params: CloseParams) -> StepResult:
        ports = self._need()
        await _ready(ports)
        windows, running = await self._windows_and_running(ports)
        app = _pick(params, ports.index.apps, running)
        owned = _windows_of(app, windows)
        if not owned:
            raise SkillError(NOT_RUNNING, f"{app.name} is not open.")
        if any(window.elevated for window in owned):
            raise SkillError(ELEVATED, f"{app.name} runs as administrator, so I can't close it.")
        if params.force:
            for pid in sorted({window.pid for window in owned}):
                await ports.windows.terminate(pid)
        else:
            for window in owned:
                await ports.windows.close(window.hwnd)

        async def gone() -> bool:
            return not _windows_of(app, await ports.windows.windows())

        if not await _wait_for(gone, CLOSE_WAIT_S):
            raise SkillError(
                STILL_OPEN,
                f"{app.name} is still open. It may be asking to save changes.",
            )
        return StepResult(spoken=f"Closed {app.name}.", data={"target": app.target})

    async def verify(
        self, ctx: SkillContext, params: CloseParams, result: StepResult
    ) -> RuleCheckResult:
        ports = self._need()
        app = _by_target(ports.index.apps, str(result.data.get("target", "")))
        if app is None:
            return RuleCheckResult(False, "the app is not in the index")
        still = _windows_of(app, await ports.windows.windows())
        return RuleCheckResult(not still, None if not still else f"{app.name} is still open")


class AppsFocusSkill(_AppsSkill[AppParams]):
    id = "apps.focus"
    description = "Switch to an open app by name"
    params_model = AppParams
    timeout_s = 6.0
    examples = ("switch to whatsapp", "whatsapp pe jao", "switch to chrome")

    def tier_for(self, params: AppParams) -> Tier:
        return Tier.T0

    def describe(self, params: AppParams) -> str:
        return f"Switch to {params.name}"

    async def execute(self, ctx: SkillContext, params: AppParams) -> StepResult:
        ports = self._need()
        await _ready(ports)
        windows, running = await self._windows_and_running(ports)
        app = _pick(params, ports.index.apps, running)
        owned = _windows_of(app, windows)
        if not owned:
            raise SkillError(NOT_RUNNING, f"{app.name} is not open.")
        target = next((window for window in owned if not window.elevated), None)
        if target is None:
            raise SkillError(
                ELEVATED, f"{app.name} runs as administrator, so I can't switch to it."
            )
        if not await ports.windows.focus(target.hwnd):
            raise SkillError(FOCUS_DENIED, "Windows kept the focus on another window.")
        return StepResult(
            spoken=f"Switched to {app.name}.",
            detail=f"Switched to {app.name}",
            data={"target": app.target, "hwnd": target.hwnd},
        )

    async def verify(
        self, ctx: SkillContext, params: AppParams, result: StepResult
    ) -> RuleCheckResult:
        ports = self._need()
        hwnd = int(str(result.data.get("hwnd", 0)))
        ok = await ports.windows.foreground() == hwnd
        return RuleCheckResult(ok, None if ok else "another window is in front")
