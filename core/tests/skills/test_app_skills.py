"""Apps & windows skills on a fake desktop (S08): resolution, clarification, launch, close, focus,
arrange, list, elevated windows (§10.2)."""

from __future__ import annotations

import dataclasses

import pytest

from ace_core.brain.records import Origin
from ace_core.os.base import AppKind
from ace_core.os.fakes import fake_window
from ace_core.skills import apps as apps_module
from ace_core.skills import windows as windows_module
from ace_core.skills.app_index import IndexedApp, normalize_name
from ace_core.skills.apps import (
    AppParams,
    AppsCloseSkill,
    AppsFocusSkill,
    AppsOpenSkill,
    CloseParams,
)
from ace_core.skills.base import NeedsChoice, NoParams, SkillContext, SkillError
from ace_core.skills.fakes import (
    CHROME,
    NOTEPAD,
    PYTHON_312,
    SPOTIFY,
    VS_CODE,
    fake_desktop,
    window_for,
)
from ace_core.skills.resolve import resolve
from ace_core.skills.windows import ArrangeParams, WindowsArrangeSkill, WindowsListSkill

CTX = SkillContext(task_id="t", step_id="s", origin=Origin.TEXT, utterance="test")


@pytest.fixture(autouse=True)
def _short_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps_module, "WINDOW_WAIT_S", 0.3)
    monkeypatch.setattr(apps_module, "CLOSE_WAIT_S", 0.3)
    monkeypatch.setattr(windows_module, "SETTLE_S", 0.3)


# ---- resolution ----


def indexed(name: str, *, kind: AppKind = AppKind.DESKTOP, launches: int = 0) -> IndexedApp:
    return IndexedApp(name, kind, f"id-{name}", None, None, launch_count=launches)


def test_names_aliases_and_prefixes_resolve() -> None:
    apps = [indexed("Spotify"), indexed("Visual Studio Code"), indexed("Sticky Notes")]
    assert resolve("spotify", apps).best == apps[0]
    assert resolve("spot", apps).best == apps[0]  # "open spot"
    assert resolve("vs code", apps).best == apps[1]
    assert resolve("Visual Studio", apps).best == apps[1]
    assert resolve("photoshop", apps).best is None
    assert resolve("  ", apps).best is None
    assert resolve("spotfy", apps).best == apps[0]  # a typo still matches


def test_one_shared_word_is_not_a_match() -> None:
    manager = indexed("Python install manager")
    assert resolve("task manager", [manager]).best is None  # found live at S08
    assert resolve("python", [manager]).best == manager
    assert resolve("install manager", [manager]).best == manager


def test_close_names_are_ambiguous_and_history_breaks_ties() -> None:
    py311, py312 = indexed("Python 3.11 (64-bit)"), indexed("Python 3.12 (64-bit)")
    docs = indexed("Python 3.12 Manual", kind=AppKind.OTHER)
    result = resolve("python", [py311, py312, docs])
    assert result.ambiguous
    assert [c.app for c in result.candidates][:2] == [py311, py312]
    assert docs not in [c.app for c in result.candidates][:2]  # documents rank lower
    favourite = dataclasses.replace(py312, launch_count=12)
    assert resolve("python", [py311, favourite]).best == favourite
    assert not resolve("python", [py311, favourite]).ambiguous
    assert resolve("python", [py311, py312], running={py311.target}).best == py311


def test_windows_belong_to_apps_by_aumid_or_exe() -> None:
    spotify = IndexedApp("Spotify", AppKind.PACKAGED, SPOTIFY.app_id, SPOTIFY.aumid, None)
    chrome = IndexedApp("Google Chrome", AppKind.DESKTOP, "Chrome", "Chrome", CHROME.exe_path)
    assert spotify.owns(window_for(SPOTIFY, 1))
    assert chrome.owns(window_for(CHROME, 2))
    assert chrome.owns(fake_window(3, "x", exe=CHROME.exe_path.upper() if CHROME.exe_path else ""))
    assert not chrome.owns(window_for(SPOTIFY, 4))
    assert normalize_name("  Microsoft®  Teams™ ") == "microsoft teams"


async def test_a_refresh_keeps_launch_counts() -> None:
    desktop = await fake_desktop()
    index = desktop.ports.index
    spotify = next(app for app in index.apps if app.name == "Spotify")
    await index.note_launch(spotify)
    desktop.start_menu.items = [SPOTIFY, NOTEPAD]
    assert await index.refresh() == 2
    assert {app.name: app.launch_count for app in index.apps} == {"Notepad": 0, "Spotify": 1}


# ---- open ----


async def test_open_launches_and_waits_for_the_window() -> None:
    desktop = await fake_desktop(delay_s=0.05)
    skill = AppsOpenSkill(desktop.ports)
    result = await skill.execute(CTX, AppParams(name="spot"))
    assert desktop.launcher.launched == [SPOTIFY.app_id]
    assert result.spoken == "Opened Spotify."
    assert result.data["was_open"] is False
    assert isinstance(result.data["elapsed_ms"], int)
    assert (await skill.verify(CTX, AppParams(name="spot"), result)).ok
    assert next(a for a in desktop.ports.index.apps if a.name == "Spotify").launch_count == 1


async def test_open_brings_an_open_app_to_the_front() -> None:
    desktop = await fake_desktop(windows=[window_for(CHROME, 2), window_for(VS_CODE, 1)])
    desktop.windows.foreground_hwnd = 2
    result = await AppsOpenSkill(desktop.ports).execute(CTX, AppParams(name="vs code"))
    assert result.data["was_open"] is True
    assert "already open" in result.spoken
    assert desktop.windows.foreground_hwnd == 1


async def test_open_asks_which_one_when_names_are_close() -> None:
    desktop = await fake_desktop()
    with pytest.raises(NeedsChoice) as asked:
        await AppsOpenSkill(desktop.ports).execute(CTX, AppParams(name="python"))
    labels = [choice.label for choice in asked.value.choices]
    assert labels[:2] == ["Python 3.11 (64-bit)", "Python 3.12 (64-bit)"]
    chosen = asked.value.choices[1]
    result = await AppsOpenSkill(desktop.ports).execute(
        CTX, AppParams.model_validate({"name": "python", **chosen.params})
    )
    assert desktop.launcher.launched == [PYTHON_312.app_id]
    assert result.spoken == "Opened Python 3.12 (64-bit)."


@pytest.mark.parametrize(
    ("name", "setup", "code"),
    [
        ("photoshop", None, "E_APP_NOT_FOUND"),
        ("spotify", "fail", "E_LAUNCH_FAILED"),
        ("spotify", "silent", "E_APP_NOT_VISIBLE"),
    ],
)
async def test_open_failures(name: str, setup: str | None, code: str) -> None:
    desktop = await fake_desktop()
    if setup == "fail":
        desktop.launcher.fail.add(SPOTIFY.app_id)
    if setup == "silent":
        desktop.launcher.silent.add(SPOTIFY.app_id)
    with pytest.raises(SkillError) as failed:
        await AppsOpenSkill(desktop.ports).execute(CTX, AppParams(name=name))
    assert failed.value.code == code


# ---- close / focus ----


async def test_close_asks_the_windows_and_checks_they_are_gone() -> None:
    desktop = await fake_desktop(windows=[window_for(NOTEPAD, 1), window_for(NOTEPAD, 2)])
    skill = AppsCloseSkill(desktop.ports)
    result = await skill.execute(CTX, CloseParams(name="notepad"))
    assert desktop.windows.closed == [1, 2]
    assert (await skill.verify(CTX, CloseParams(name="notepad"), result)).ok


@pytest.mark.parametrize(
    ("windows", "code"),
    [
        ([], "E_APP_NOT_RUNNING"),
        ([window_for(NOTEPAD, 1, elevated=True)], "E_APP_ELEVATED"),
        ([window_for(NOTEPAD, 1)], "E_APP_STILL_OPEN"),  # it asks to save changes
    ],
)
async def test_close_failures_are_explained(windows: list, code: str) -> None:  # type: ignore[type-arg]
    desktop = await fake_desktop(windows=windows)
    desktop.windows.ask_before_closing.add(1)
    with pytest.raises(SkillError) as failed:
        await AppsCloseSkill(desktop.ports).execute(CTX, CloseParams(name="notepad"))
    assert failed.value.code == code


async def test_force_close_ends_the_processes() -> None:
    desktop = await fake_desktop(windows=[window_for(NOTEPAD, 1)])
    desktop.windows.ask_before_closing.add(1)  # a prompt cannot stop a forced close
    await AppsCloseSkill(desktop.ports).execute(CTX, CloseParams(name="notepad", force=True))
    assert await desktop.windows.windows() == []


async def test_focus_switches_and_reports_refusals() -> None:
    desktop = await fake_desktop(windows=[window_for(VS_CODE, 1), window_for(CHROME, 2)])
    skill = AppsFocusSkill(desktop.ports)
    result = await skill.execute(CTX, AppParams(name="chrome"))
    assert desktop.windows.foreground_hwnd == 2
    assert (await skill.verify(CTX, AppParams(name="chrome"), result)).ok
    desktop.windows.deny_focus = True
    with pytest.raises(SkillError) as denied:
        await skill.execute(CTX, AppParams(name="vs code"))
    assert denied.value.code == "E_FOCUS_DENIED"
    with pytest.raises(SkillError) as missing:
        await skill.execute(CTX, AppParams(name="spotify"))
    assert missing.value.code == "E_APP_NOT_RUNNING"


# ---- windows ----


async def test_snap_a_named_window_and_verify_its_frame() -> None:
    desktop = await fake_desktop(windows=[window_for(CHROME, 2), window_for(VS_CODE, 1)])
    skill = WindowsArrangeSkill(desktop.ports)
    params = ArrangeParams(action="snap_left", name="vs code")
    result = await skill.execute(CTX, params)
    assert result.spoken == "Snapped Visual Studio Code to the left."
    vs_code = next(w for w in await desktop.windows.windows() if w.hwnd == 1)
    assert vs_code.rect == (0, 0, 960, 1152)
    assert (await skill.verify(CTX, params, result)).ok


async def test_this_window_means_the_top_window_that_is_not_ace() -> None:
    ace = fake_window(7, "ACE", exe=r"C:\ACE\ace-desktop.exe")
    desktop = await fake_desktop(windows=[ace, window_for(CHROME, 2)])
    params = ArrangeParams(action="maximize")
    await WindowsArrangeSkill(desktop.ports).execute(CTX, params)
    states = {w.hwnd: w.maximized for w in await desktop.windows.windows()}
    assert states == {7: False, 2: True}


async def test_arrange_refuses_elevated_windows() -> None:
    desktop = await fake_desktop(windows=[window_for(CHROME, 2, elevated=True)])
    with pytest.raises(SkillError) as failed:
        await WindowsArrangeSkill(desktop.ports).execute(
            CTX, ArrangeParams(action="minimize", name="chrome")
        )
    assert failed.value.code == "E_APP_ELEVATED"


async def test_list_names_the_open_apps() -> None:
    desktop = await fake_desktop(
        windows=[
            window_for(CHROME, 1, "Netflix"),
            window_for(CHROME, 2, "Docs"),
            window_for(SPOTIFY, 3),
            fake_window(7, "ACE", exe=r"C:\ACE\ace-desktop.exe"),
        ]
    )
    result = await WindowsListSkill(desktop.ports).execute(CTX, NoParams())
    assert result.spoken == "Open now: Google Chrome, Spotify."
    assert result.detail is not None
    assert "• Google Chrome: Docs" in result.detail
    assert "ACE" not in result.detail
    empty = await fake_desktop()
    assert (await WindowsListSkill(empty.ports).execute(CTX, NoParams())).spoken == (
        "No app windows are open."
    )
