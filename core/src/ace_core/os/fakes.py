"""In-memory fakes of the OS adapters (§16.1): a small desktop the skill tests drive."""

from __future__ import annotations

import asyncio
import dataclasses
import itertools

from ace_core.os.base import LaunchError, Rect, ShowState, Side, StartApp, WindowInfo

WORK_AREA: Rect = (0, 0, 1920, 1152)


def fake_window(
    hwnd: int,
    title: str,
    *,
    exe: str = "",
    process_aumid: str | None = None,
    window_aumid: str | None = None,
    pid: int | None = None,
    elevated: bool = False,
) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        title=title,
        pid=pid if pid is not None else hwnd + 1000,
        exe_path=exe,
        process_aumid=process_aumid,
        window_aumid=window_aumid,
        rect=(100, 100, 900, 700),
        minimized=False,
        maximized=False,
        elevated=elevated,
        work_area=WORK_AREA,
    )


class FakeStartMenu:
    def __init__(self, apps: list[StartApp]) -> None:
        self.items = list(apps)
        self.calls = 0

    async def apps(self) -> list[StartApp]:
        self.calls += 1
        return list(self.items)


class FakeWindows:
    def __init__(self, windows: list[WindowInfo] | None = None) -> None:
        self.items: list[WindowInfo] = list(windows or [])
        self.foreground_hwnd = self.items[0].hwnd if self.items else 0
        self.deny_focus = False
        self.ask_before_closing: set[int] = set()  # windows that show a "save changes?" prompt
        self.elevated_ace = False
        self.closed: list[int] = []

    def add(self, window: WindowInfo, *, foreground: bool = True) -> None:
        self.items.insert(0, window)
        if foreground:
            self.foreground_hwnd = window.hwnd

    def _replace(self, hwnd: int, **changes: object) -> None:
        self.items = [
            dataclasses.replace(w, **changes) if w.hwnd == hwnd else w  # type: ignore[arg-type]
            for w in self.items
        ]

    async def windows(self) -> list[WindowInfo]:
        return list(self.items)

    async def foreground(self) -> int:
        return self.foreground_hwnd

    async def focus(self, hwnd: int) -> bool:
        if self.deny_focus or not any(w.hwnd == hwnd for w in self.items):
            return False
        self._replace(hwnd, minimized=False)
        self.foreground_hwnd = hwnd
        return True

    async def close(self, hwnd: int) -> bool:
        window = next((w for w in self.items if w.hwnd == hwnd), None)
        if window is None or window.elevated:
            return False
        self.closed.append(hwnd)
        if hwnd not in self.ask_before_closing:
            self.items = [w for w in self.items if w.hwnd != hwnd]
        return True

    async def terminate(self, pid: int) -> bool:
        if any(w.pid == pid and w.elevated for w in self.items):
            return False
        self.items = [w for w in self.items if w.pid != pid]
        return True

    async def show(self, hwnd: int, state: ShowState) -> bool:
        self._replace(hwnd, minimized=state == "minimize", maximized=state == "maximize")
        return True

    async def snap(self, hwnd: int, side: Side) -> Rect:
        left, top, right, bottom = WORK_AREA
        half = (right - left) // 2
        target = (
            (left, top, left + half, bottom)
            if side == "left"
            else (left + half, top, right, bottom)
        )
        self._replace(hwnd, rect=target, minimized=False, maximized=False)
        return target

    async def ace_elevated(self) -> bool:
        return self.elevated_ace


class FakeLauncher:
    """Opens a window for the launched app after ``delay_s`` (or never, for apps in ``silent``)."""

    def __init__(
        self, windows: FakeWindows, templates: dict[str, WindowInfo], delay_s: float = 0.0
    ):
        self._windows = windows
        self._templates = templates
        self._delay_s = delay_s
        self._hwnds = itertools.count(9000)
        self.launched: list[str] = []
        self.silent: set[str] = set()
        self.fail: set[str] = set()

    async def launch(self, app_id: str) -> None:
        if app_id in self.fail:
            raise LaunchError("Explorer could not start it")
        self.launched.append(app_id)
        template = self._templates.get(app_id)
        if template is None or app_id in self.silent:
            return
        existing = [w for w in self._windows.items if w.title == template.title]
        if existing:  # already running: the app comes to the front
            self._windows.foreground_hwnd = existing[0].hwnd
            return
        window = dataclasses.replace(template, hwnd=next(self._hwnds))

        def appear() -> None:
            self._windows.add(window)

        if self._delay_s:
            asyncio.get_running_loop().call_later(self._delay_s, appear)
        else:
            appear()
