"""Window layout and the list of open windows (§10.2 ``windows.*``, S08).

"this" / no name means the window Sharan is using: the topmost app window that is not ACE's own.
Every change is verified by reading the window back (state or frame rectangle).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, Literal

from pydantic import Field, JsonValue

from ace_core.os.base import Rect, ShowState, WindowInfo
from ace_core.security.tiers import Tier
from ace_core.skills.apps import (
    ELEVATED,
    NOT_READY,
    NOT_RUNNING,
    AppParams,
    AppsPorts,
    _pick,
    _ready,
    _wait_for,
    _windows_of,
)
from ace_core.skills.base import (
    NoParams,
    RuleCheckResult,
    Skill,
    SkillContext,
    SkillError,
    SkillParams,
    StepResult,
)

NO_WINDOW: Final = "E_NO_WINDOW"
ARRANGE_FAILED: Final = "E_ARRANGE_FAILED"
ACE_EXE: Final = "ace-desktop.exe"
SETTLE_S: Final = 1.5
TOLERANCE_PX: Final = 8

Action = Literal["snap_left", "snap_right", "maximize", "minimize", "restore"]
_STATES: Final[dict[str, ShowState]] = {
    "maximize": "maximize",
    "minimize": "minimize",
    "restore": "restore",
}
_VERBS: Final[dict[str, str]] = {
    "snap_left": "Snapped {} to the left.",
    "snap_right": "Snapped {} to the right.",
    "maximize": "Maximized {}.",
    "minimize": "Minimized {}.",
    "restore": "Restored {}.",
}


class ArrangeParams(SkillParams):
    action: Action
    name: str | None = Field(default=None, max_length=100)  # None: the window in use
    target: str | None = Field(default=None, max_length=500)  # set by a clarification choice


def _close_to(a: Rect, b: Rect) -> bool:
    return all(abs(x - y) <= TOLERANCE_PX for x, y in zip(a, b, strict=True))


def _user_window(windows: Sequence[WindowInfo]) -> WindowInfo | None:
    return next((w for w in windows if w.exe_name != ACE_EXE), None)


def _settled(window: WindowInfo, action: Action, target: Rect | None) -> bool:
    if action == "minimize":
        return window.minimized
    if action == "maximize":
        return window.maximized
    if action == "restore":
        return not window.minimized and not window.maximized
    return target is not None and not window.minimized and _close_to(window.rect, target)


class WindowsArrangeSkill(Skill[ArrangeParams]):
    id = "windows.arrange"
    description = "Snap, maximize, minimize or restore a window"
    params_model = ArrangeParams
    timeout_s = 12.0
    examples = ("snap vs code left", "maximize this", "minimize spotify", "chrome ko left karo")

    def __init__(self, ports: AppsPorts | None) -> None:
        self._ports = ports

    def tier_for(self, params: ArrangeParams) -> Tier:
        return Tier.T1

    def describe(self, params: ArrangeParams) -> str:
        subject = params.name or "the current window"
        return {
            "snap_left": f"Snap {subject} to the left half",
            "snap_right": f"Snap {subject} to the right half",
            "maximize": f"Maximize {subject}",
            "minimize": f"Minimize {subject}",
            "restore": f"Restore {subject}",
        }[params.action]

    def _need(self) -> AppsPorts:
        if self._ports is None:
            raise SkillError(NOT_READY, "Window control is not available on this system.")
        return self._ports

    async def _target(self, ports: AppsPorts, params: ArrangeParams) -> tuple[WindowInfo, str]:
        windows = await ports.windows.windows()
        if params.name is None:
            window = _user_window(windows)
            if window is None:
                raise SkillError(NO_WINDOW, "I can't see a window to arrange.")
            return window, "the window"
        await _ready(ports)
        running = {app.target for app in ports.index.apps if _windows_of(app, windows)}
        app = _pick(AppParams(name=params.name, target=params.target), ports.index.apps, running)
        owned = _windows_of(app, windows)
        if not owned:
            raise SkillError(NOT_RUNNING, f"{app.name} is not open.")
        return owned[0], app.name

    async def execute(self, ctx: SkillContext, params: ArrangeParams) -> StepResult:
        ports = self._need()
        window, label = await self._target(ports, params)
        if window.elevated:
            raise SkillError(ELEVATED, f"{label} runs as administrator, so I can't move it.")
        target: Rect | None = None
        if params.action in ("snap_left", "snap_right"):
            side: Literal["left", "right"] = "left" if params.action == "snap_left" else "right"
            target = await ports.windows.snap(window.hwnd, side)
        else:
            await ports.windows.show(window.hwnd, _STATES[params.action])

        async def done() -> bool:
            now = next((w for w in await ports.windows.windows() if w.hwnd == window.hwnd), None)
            return now is not None and _settled(now, params.action, target)

        if not await _wait_for(done, SETTLE_S):
            raise SkillError(ARRANGE_FAILED, f"{label} did not end up where I put it.")
        return StepResult(
            spoken=_VERBS[params.action].format(label),
            data={
                "hwnd": window.hwnd,
                "action": params.action,
                "target_rect": list(target) if target else None,
            },
        )

    async def verify(
        self, ctx: SkillContext, params: ArrangeParams, result: StepResult
    ) -> RuleCheckResult:
        ports = self._need()
        hwnd = int(str(result.data.get("hwnd", 0)))
        raw = result.data.get("target_rect")
        target: Rect | None = None
        if isinstance(raw, list) and len(raw) == 4:
            target = (int(str(raw[0])), int(str(raw[1])), int(str(raw[2])), int(str(raw[3])))
        now = next((w for w in await ports.windows.windows() if w.hwnd == hwnd), None)
        ok = now is not None and _settled(now, params.action, target)
        return RuleCheckResult(ok, None if ok else "the window is not in the expected state")


class WindowsListSkill(Skill[NoParams]):
    id = "windows.list"
    description = "List the open app windows"
    params_model = NoParams
    timeout_s = 5.0
    examples = ("what's open", "kya khula hai")

    def __init__(self, ports: AppsPorts | None) -> None:
        self._ports = ports

    def tier_for(self, params: NoParams) -> Tier:
        return Tier.T0

    def describe(self, params: NoParams) -> str:
        return "List the open windows"

    async def execute(self, ctx: SkillContext, params: NoParams) -> StepResult:
        if self._ports is None:
            raise SkillError(NOT_READY, "Window control is not available on this system.")
        windows = [w for w in await self._ports.windows.windows() if w.exe_name != ACE_EXE]
        apps = self._ports.index.apps
        names: list[str] = []
        lines: list[str] = []
        for window in windows:
            owner = next((app.name for app in apps if app.owns(window)), None)
            name = owner or window.exe_name.removesuffix(".exe") or "Unknown app"
            if name not in names:
                names.append(name)
            lines.append(f"• {name}: {window.title}")
        if not names:
            return StepResult(spoken="No app windows are open.", data={"count": 0})
        shown = ", ".join(names[:4])
        more = f" and {len(names) - 4} more" if len(names) > 4 else ""
        return StepResult(
            spoken=f"Open now: {shown}{more}.",
            detail="\n".join(lines),
            data={"count": len(windows), "apps": list[JsonValue](names)},
        )

    async def verify(
        self, ctx: SkillContext, params: NoParams, result: StepResult
    ) -> RuleCheckResult:
        return RuleCheckResult(True)  # read-only
