"""What the apps & windows skills need from Windows (S08, D-57), as plain data and interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

Rect = tuple[int, int, int, int]  # left, top, right, bottom in physical pixels
ShowState = Literal["minimize", "maximize", "restore"]
Side = Literal["left", "right"]


class AppKind(StrEnum):
    PACKAGED = "aumid"  # a packaged (Store) app: launched and recognised by its AUMID
    DESKTOP = "exe"  # a desktop app: recognised by its exe (and its AUMID if it sets one)
    OTHER = "other"  # documents, links and folders listed in Start


@dataclass(frozen=True, slots=True)
class StartApp:
    """One entry of the Start menu's app list (shell:AppsFolder)."""

    name: str
    app_id: str  # the AppsFolder parsing name: launch it as shell:AppsFolder\<app_id>
    aumid: str | None  # System.AppUserModel.ID
    exe_path: str | None  # System.Link.TargetParsingPath (desktop apps)

    @property
    def kind(self) -> AppKind:
        if "!" in self.app_id:
            return AppKind.PACKAGED
        if self.exe_path and self.exe_path.lower().endswith(".exe"):
            return AppKind.DESKTOP
        return AppKind.OTHER


@dataclass(frozen=True, slots=True)
class WindowInfo:
    """A visible top-level app window."""

    hwnd: int
    title: str
    pid: int
    exe_path: str  # "" when the process cannot be opened
    process_aumid: str | None  # packaged processes only
    window_aumid: str | None  # the window's System.AppUserModel.ID property
    rect: Rect  # the visible frame (without invisible resize borders)
    minimized: bool
    maximized: bool
    elevated: bool  # runs with higher rights than ACE (UIPI blocks most control)
    work_area: Rect  # the work area of the window's monitor

    @property
    def exe_name(self) -> str:
        return self.exe_path.replace("/", "\\").rsplit("\\", 1)[-1].lower()


class LaunchError(Exception):
    pass


class StartMenu(Protocol):
    async def apps(self) -> list[StartApp]: ...


class Launcher(Protocol):
    async def launch(self, app_id: str) -> None:
        """Start an app like a click in Start (through Explorer, outside ACE's Job Object)."""


class WindowControl(Protocol):
    """All calls are quick; verification loops live in the skills."""

    async def windows(self) -> list[WindowInfo]: ...

    async def foreground(self) -> int: ...

    async def focus(self, hwnd: int) -> bool: ...

    async def close(self, hwnd: int) -> bool:
        """Ask the window to close (WM_CLOSE). False if Windows refused (e.g. UIPI)."""

    async def terminate(self, pid: int) -> bool: ...

    async def show(self, hwnd: int, state: ShowState) -> bool: ...

    async def snap(self, hwnd: int, side: Side) -> Rect:
        """Move the window to one half of its monitor's work area; returns the target rect."""

    async def ace_elevated(self) -> bool:
        """Whether ACE itself runs as administrator."""
