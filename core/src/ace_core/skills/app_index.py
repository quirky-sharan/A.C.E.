"""The app index (S08 task 1, §13.3 ``app_index``): every app in the Start menu, refreshed at start
and daily, kept in memory for fast matching and stored with its launch count."""

from __future__ import annotations

import asyncio
import contextlib
import re
from dataclasses import dataclass
from typing import Final, Protocol

import structlog

from ace_core.os.base import AppKind, StartMenu, WindowInfo

log = structlog.stdlib.get_logger(__name__)

REFRESH_EVERY_S: Final = 24 * 3600.0
_MARKS = re.compile(r"[™®©]")
_SPACES = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    return _SPACES.sub(" ", _MARKS.sub("", name)).strip().casefold()


def _same_path(a: str, b: str) -> bool:
    return a.replace("/", "\\").casefold() == b.replace("/", "\\").casefold()


@dataclass(frozen=True, slots=True)
class IndexedApp:
    name: str
    kind: AppKind
    target: str  # the AppsFolder id: launched as shell:AppsFolder\<target>
    aumid: str | None
    exe_path: str | None
    launch_count: int = 0

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.name)

    def owns(self, window: WindowInfo) -> bool:
        """Whether ``window`` belongs to this app (by AUMID, or by exe for desktop apps)."""
        ids = {value for value in (self.aumid, self.target) if value}
        if window.window_aumid in ids or window.process_aumid in ids:
            return True
        return bool(
            self.kind is AppKind.DESKTOP
            and self.exe_path
            and window.exe_path
            and _same_path(self.exe_path, window.exe_path)
        )


class AppIndexStorage(Protocol):
    """What the index needs from the database (``db.app_index.AppIndexStore``)."""

    async def all(self) -> list[IndexedApp]: ...

    async def replace(self, apps: list[IndexedApp]) -> int: ...

    async def note_launch(self, target: str) -> None: ...


class AppIndex:
    def __init__(
        self,
        storage: AppIndexStorage,
        start_menu: StartMenu,
        *,
        refresh_every_s: float = REFRESH_EVERY_S,
    ) -> None:
        self._storage = storage
        self._start_menu = start_menu
        self._refresh_every_s = refresh_every_s
        self._apps: list[IndexedApp] = []
        self._task: asyncio.Task[None] | None = None
        self._refreshed = asyncio.Event()

    @property
    def apps(self) -> list[IndexedApp]:
        return list(self._apps)

    async def load(self) -> None:
        self._apps = await self._storage.all()

    async def refresh(self) -> int:
        """Read the Start menu, store it (launch counts are kept), and use it from now on."""
        found = await self._start_menu.apps()
        apps = [
            IndexedApp(
                name=item.name,
                kind=item.kind,
                target=item.app_id,
                aumid=item.aumid,
                exe_path=item.exe_path,
            )
            for item in found
        ]
        count = await self._storage.replace(apps)
        await self.load()
        self._refreshed.set()
        log.info("app index refreshed", apps=count)
        return count

    async def wait_ready(self, timeout: float) -> bool:
        """Wait (bounded) for the first refresh; True when the index has apps."""
        if not self._apps:
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(timeout):
                    await self._refreshed.wait()
        return bool(self._apps)

    async def note_launch(self, app: IndexedApp) -> None:
        await self._storage.note_launch(app.target)
        self._apps = [
            IndexedApp(
                name=a.name,
                kind=a.kind,
                target=a.target,
                aumid=a.aumid,
                exe_path=a.exe_path,
                launch_count=a.launch_count + 1,
            )
            if a.target == app.target
            else a
            for a in self._apps
        ]

    async def start(self) -> None:
        await self.load()
        self._task = asyncio.create_task(self._keep_fresh(), name="ace-app-index")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _keep_fresh(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception:
                log.exception("app index refresh failed")
            await asyncio.sleep(self._refresh_every_s)
