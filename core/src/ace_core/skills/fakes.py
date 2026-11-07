"""A fake desktop for tests (§16.1): in-memory app index storage, a Start menu with real-looking
apps (ids as found on the dev PC at S08), and windows that appear when an app is launched."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from ace_core.os.base import StartApp, WindowInfo
from ace_core.os.fakes import FakeLauncher, FakeStartMenu, FakeWindows, fake_window
from ace_core.skills.app_index import AppIndex, IndexedApp
from ace_core.skills.apps import AppsPorts

SPOTIFY = StartApp(
    "Spotify",
    "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify",
    "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify",
    None,
)
VS_CODE = StartApp(
    "Visual Studio Code",
    "Microsoft.VisualStudioCode",
    "Microsoft.VisualStudioCode",
    r"C:\Users\me\AppData\Local\Programs\Microsoft VS Code\Code.exe",
)
CHROME = StartApp(
    "Google Chrome", "Chrome", "Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)
NOTEPAD = StartApp(
    "Notepad",
    "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
    "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
    None,
)
PYTHON_311 = StartApp(
    "Python 3.11 (64-bit)",
    r"C:\Python311\python.exe",
    None,
    r"C:\Python311\python.exe",
)
PYTHON_312 = StartApp(
    "Python 3.12 (64-bit)",
    r"C:\Python312\python.exe",
    None,
    r"C:\Python312\python.exe",
)
PYTHON_DOCS = StartApp(
    "Python 3.12 Manual", r"C:\Python312\Doc\index.html", None, r"C:\Python312\Doc\index.html"
)
APPS = [SPOTIFY, VS_CODE, CHROME, NOTEPAD, PYTHON_311, PYTHON_312, PYTHON_DOCS]


def window_for(app: StartApp, hwnd: int, title: str | None = None, **changes: object) -> WindowInfo:
    """A window that ``app`` owns (matched the way the real adapters see it)."""
    packaged = "!" in app.app_id
    window = fake_window(
        hwnd,
        title or app.name,
        exe=app.exe_path or rf"C:\Program Files\WindowsApps\{app.name}\{app.name}.exe",
        process_aumid=app.aumid if packaged else None,
        window_aumid=app.aumid if app.aumid and not packaged else None,
    )
    return dataclasses.replace(window, **changes)  # type: ignore[arg-type]


class MemoryAppIndexStorage:
    def __init__(self) -> None:
        self.rows: dict[str, IndexedApp] = {}

    async def all(self) -> list[IndexedApp]:
        return sorted(self.rows.values(), key=lambda app: app.normalized_name)

    async def replace(self, apps: list[IndexedApp]) -> int:
        rows: dict[str, IndexedApp] = {}
        for app in apps:
            old = self.rows.get(app.target)
            rows[app.target] = dataclasses.replace(app, launch_count=old.launch_count if old else 0)
        self.rows = rows
        return len(rows)

    async def note_launch(self, target: str) -> None:
        app = self.rows.get(target)
        if app is not None:
            self.rows[target] = dataclasses.replace(app, launch_count=app.launch_count + 1)


@dataclass
class FakeDesktop:
    start_menu: FakeStartMenu
    windows: FakeWindows
    launcher: FakeLauncher
    storage: MemoryAppIndexStorage
    ports: AppsPorts


async def fake_desktop(
    apps: list[StartApp] | None = None,
    windows: list[WindowInfo] | None = None,
    *,
    delay_s: float = 0.0,
) -> FakeDesktop:
    items = list(APPS if apps is None else apps)
    start_menu = FakeStartMenu(items)
    fake_windows = FakeWindows(windows)
    templates = {app.app_id: window_for(app, 0) for app in items}
    launcher = FakeLauncher(fake_windows, templates, delay_s)
    storage = MemoryAppIndexStorage()
    index = AppIndex(storage, start_menu)
    await index.refresh()
    ports = AppsPorts(index=index, windows=fake_windows, launcher=launcher)
    return FakeDesktop(start_menu, fake_windows, launcher, storage, ports)
