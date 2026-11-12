"""The real Win32 adapters on the dev PC (S08 [VERIFY]). Local only: marked ``windows_ui`` (CI skips
it) and opt-in with ACE_WINDOWS_UI_TESTS=1, because the launch test opens and closes Calculator."""

from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

pytestmark = [
    pytest.mark.windows_ui,
    pytest.mark.skipif(
        sys.platform != "win32" or os.environ.get("ACE_WINDOWS_UI_TESTS") != "1",
        reason="set ACE_WINDOWS_UI_TESTS=1 on a Windows desktop to run",
    ),
]

CALCULATOR = "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"


async def test_the_start_menu_lists_desktop_and_store_apps() -> None:
    from ace_core.os.base import AppKind
    from ace_core.os.com import ComThread
    from ace_core.os.win32 import Win32StartMenu

    com = ComThread()
    try:
        apps = await Win32StartMenu(com).apps()
    finally:
        await com.close()
    kinds = {app.kind for app in apps}
    assert len(apps) >= 10
    assert {AppKind.PACKAGED, AppKind.DESKTOP} <= kinds
    assert any(app.app_id == CALCULATOR for app in apps)


async def test_launch_through_explorer_then_close() -> None:
    from ace_core.os.com import ComThread
    from ace_core.os.win32 import ExplorerLauncher, Win32Windows

    com = ComThread()
    windows = Win32Windows(com)
    try:

        def calculators(items: list) -> set[int]:  # type: ignore[type-arg]
            return {w.hwnd for w in items if CALCULATOR in (w.window_aumid, w.process_aumid)}

        before = calculators(await windows.windows())
        await ExplorerLauncher(com).launch(CALCULATOR)
        deadline = time.monotonic() + 10
        new: set[int] = set()
        while not new and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
            new = calculators(await windows.windows()) - before
        assert new, "Calculator did not open"
        for hwnd in new:  # close only the window this test opened
            assert await windows.close(hwnd)
        await asyncio.sleep(1.0)
        assert not (calculators(await windows.windows()) & new)
    finally:
        await com.close()
