"""Desktop link (D-52): snapshots to the shell, messages from the shell, end of input = shutdown."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

import pytest
from structlog.testing import capture_logs

from ace_core.app.config import load_settings
from ace_core.app.container import Container, build_container
from ace_core.app.events import AppStarted
from ace_core.app.health import HealthStatus
from ace_core.app.modes import MODE_SETTING, VerificationMode
from ace_core.app.paths import AppPaths
from ace_core.brain.records import TaskStatus
from ace_core.ipc.desktop_link import (
    DEFAULT_HOTKEYS,
    HEALTH_SUBSYSTEM,
    MAX_LINE_BYTES,
    SHUTDOWN_REASON,
    SNAPSHOT_PREFIX,
    DesktopAction,
    DesktopInput,
    DesktopLink,
    OverlayEdge,
    OverlayMonitor,
    overlay_settings,
    shell_settings,
)
from ace_core.skills.demo import DemoDangerousSkill


@dataclass
class Link:
    container: Container
    link: DesktopLink
    shell_end: BinaryIO  # what the shell writes into the core's stdin
    lines: list[str] = field(default_factory=list)
    shutdowns: list[str] = field(default_factory=list)
    inputs: list[DesktopInput] = field(default_factory=list)

    def send(self, message: dict[str, Any] | bytes) -> None:
        data = message if isinstance(message, bytes) else json.dumps(message).encode() + b"\n"
        self.shell_end.write(data)
        self.shell_end.flush()

    def snapshots(self) -> list[dict[str, Any]]:
        assert all(line.startswith(SNAPSHOT_PREFIX + " ") for line in self.lines), self.lines
        return [json.loads(line.split(" ", 1)[1]) for line in self.lines]


async def eventually(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        assert asyncio.get_running_loop().time() < deadline, "condition not met in time"
        await asyncio.sleep(0.01)


@pytest.fixture
async def link(tmp_path: Path) -> AsyncIterator[Link]:
    paths = AppPaths.under(tmp_path, portable=False)
    paths.ensure()
    container = build_container(load_settings(config_file=None), paths)
    await container.db.start()
    read_fd, write_fd = os.pipe()
    core_end = os.fdopen(read_fd, "rb")
    shell_end = os.fdopen(write_fd, "wb")
    lines: list[str] = []
    shutdowns: list[str] = []
    desktop_link = DesktopLink(container, shutdowns.append, stdin=core_end, write_line=lines.append)
    harness = Link(container, desktop_link, shell_end, lines, shutdowns)

    async def remember(event: DesktopInput) -> None:
        harness.inputs.append(event)

    container.bus.subscribe(DesktopInput, remember)
    await desktop_link.start()
    try:
        yield harness
    finally:
        if not shell_end.closed:
            shell_end.close()  # end of file lets the reader thread finish
        await desktop_link.stop()
        await container.db.close()
        core_end.close()


async def started(link: Link) -> None:
    await link.container.bus.publish(AppStarted(version="test"))
    await eventually(lambda: len(link.lines) == 1)


async def test_first_snapshot_comes_after_ready_with_the_defaults(link: Link) -> None:
    await asyncio.sleep(0.05)
    assert link.lines == []  # nothing before the READY line
    await started(link)
    (snapshot,) = link.snapshots()
    assert snapshot == {
        "state": {
            "conversation": "asleep",
            "game_mode": False,
            "offline": False,
            "dnd": False,
            "paused_overlay": False,
        },
        "hotkeys": {action.value: shortcut for action, shortcut in DEFAULT_HOTKEYS.items()},
        "autostart": False,
        "mode": "balanced",
        "overlay": {"edge": "right", "orb_y": 0.5, "monitor": "cursor"},
    }


async def test_state_and_shell_settings_send_new_snapshots(link: Link) -> None:
    await started(link)
    await link.container.state.update(dnd=True)
    await link.container.settings_store.set("hotkeys.summon", "Ctrl+Shift+Space", actor="user")
    await link.container.settings_store.set("desktop.autostart", True, actor="user")
    await link.container.settings_store.set("ui.theme", "dark")  # not a shell setting
    await link.container.settings_store.set("hotkeys.summon", "Ctrl+Shift+Space")  # no change
    snapshots = link.snapshots()
    assert len(snapshots) == 4
    assert snapshots[1]["state"]["dnd"] is True
    assert snapshots[2]["hotkeys"]["summon"] == "Ctrl+Shift+Space"
    assert snapshots[3]["autostart"] is True


def test_invalid_settings_fall_back_to_the_defaults() -> None:
    with capture_logs() as logs:
        hotkeys, autostart, mode = shell_settings(
            {
                "hotkeys.summon": 5,
                "hotkeys.push_to_talk": "x" * 65,
                "hotkeys.mic_mute": None,
                "hotkeys.toggle_overlay": "",
                "desktop.autostart": "yes",
                "verification.mode": "turbo",
            }
        )
    assert hotkeys[DesktopAction.SUMMON] == DEFAULT_HOTKEYS[DesktopAction.SUMMON]
    assert hotkeys[DesktopAction.PUSH_TO_TALK] == DEFAULT_HOTKEYS[DesktopAction.PUSH_TO_TALK]
    assert hotkeys[DesktopAction.MIC_MUTE] is None  # switched off
    assert hotkeys[DesktopAction.TOGGLE_OVERLAY] is None
    assert hotkeys[DesktopAction.EMERGENCY_STOP] == "Ctrl+Alt+Escape"
    assert autostart is False
    assert mode is VerificationMode.BALANCED
    assert sum(entry["event"] == "ignoring an invalid setting" for entry in logs) == 4
    assert shell_settings({"verification.mode": "paranoid"})[2] is VerificationMode.PARANOID


async def test_input_is_logged_and_published_in_order(link: Link) -> None:
    with capture_logs() as logs:
        link.send({"type": "input", "action": "push_to_talk", "source": "hotkey"})
        link.send(
            {"type": "input", "action": "push_to_talk", "source": "hotkey", "phase": "released"}
        )
        link.send({"type": "input", "action": "mic_mute", "source": "tray"})
        await eventually(lambda: len(link.inputs) == 3)
    assert [(e.action, e.source, e.phase) for e in link.inputs] == [
        (DesktopAction.PUSH_TO_TALK, "hotkey", "pressed"),
        (DesktopAction.PUSH_TO_TALK, "hotkey", "released"),
        (DesktopAction.MIC_MUTE, "tray", "pressed"),
    ]
    assert sum(entry["event"] == "desktop input" for entry in logs) == 3


async def test_mode_change_is_stored_as_the_user_and_sent_back(link: Link) -> None:
    await started(link)
    link.send({"type": "set_mode", "mode": "fast"})
    await eventually(lambda: len(link.lines) == 2)
    assert link.snapshots()[1]["mode"] == "fast"
    assert await link.container.settings_store.get(MODE_SETTING) == "fast"
    (entry,) = await link.container.audit.recent(event_type="settings.changed")
    assert entry.actor == "user"
    assert entry.data == {"key": MODE_SETTING}


async def test_desktop_status_drives_the_desktop_health(link: Link) -> None:
    def desktop_health() -> tuple[HealthStatus, str | None] | None:
        for item in link.container.health.snapshot().subsystems:
            if item.name == HEALTH_SUBSYSTEM:
                return item.status, item.detail
        return None

    link.send(
        {
            "type": "desktop_status",
            "hotkey_problems": [
                {
                    "action": "emergency_stop",
                    "shortcut": "Ctrl+Alt+Escape",
                    "error": "already registered by another app",
                    "suggestion": "Ctrl+Alt+Shift+Escape",
                }
            ],
            "autostart_error": "access denied",
        }
    )
    await eventually(lambda: desktop_health() is not None)
    status, detail = desktop_health() or (None, None)
    assert status is HealthStatus.DEGRADED
    assert detail is not None
    assert "Ctrl+Alt+Escape (emergency_stop)" in detail
    assert "try Ctrl+Alt+Shift+Escape" in detail
    assert "autostart: access denied" in detail

    link.send({"type": "desktop_status"})
    await eventually(lambda: (desktop_health() or (None,))[0] is HealthStatus.OK)


async def test_invalid_lines_are_ignored_and_the_link_keeps_working(link: Link) -> None:
    with capture_logs() as logs:
        link.send(b"not json\n")
        link.send({"type": "input", "action": "fly", "source": "hotkey"})
        link.send({"type": "input", "action": "summon", "source": "hotkey", "extra": 1})
        link.send({"type": "nope"})
        link.send(b"x" * (MAX_LINE_BYTES + 10) + b"\n")
        link.send({"type": "input", "action": "summon", "source": "hotkey"})
        await eventually(lambda: len(link.inputs) == 1)
    warnings = [e for e in logs if e["event"] == "desktop link: invalid message ignored"]
    assert len(warnings) == 5
    logged = json.dumps([entry["errors"] for entry in warnings])
    assert "fly" not in logged  # rejected values are never echoed
    assert "xxxxxxxx" not in logged
    assert link.inputs[0].action is DesktopAction.SUMMON


async def test_end_of_input_requests_a_shutdown(link: Link) -> None:
    link.send({"type": "input", "action": "emergency_stop", "source": "hotkey"})
    link.shell_end.close()
    await eventually(lambda: link.shutdowns == [SHUTDOWN_REASON])
    assert [event.action for event in link.inputs] == [DesktopAction.EMERGENCY_STOP]


async def test_a_broken_output_pipe_stops_further_snapshots(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path, portable=False)
    paths.ensure()
    container = build_container(load_settings(config_file=None), paths)
    await container.db.start()
    calls: list[str] = []

    def broken(line: str) -> None:
        calls.append(line)
        raise OSError("pipe closed")

    read_fd, write_fd = os.pipe()
    core_end = os.fdopen(read_fd, "rb")
    shell_end = os.fdopen(write_fd, "wb")
    link = DesktopLink(container, lambda _: None, stdin=core_end, write_line=broken)
    await link.start()
    try:
        with capture_logs() as logs:
            await container.bus.publish(AppStarted(version="test"))
            await container.state.update(dnd=True)
        assert len(calls) == 1
        events = [entry["event"] for entry in logs]
        assert "desktop link: cannot write to the desktop shell" in events
    finally:
        shell_end.close()
        await link.stop()
        await container.db.close()
        core_end.close()


def test_overlay_settings_fall_back_to_the_defaults() -> None:
    with capture_logs() as logs:
        bad = overlay_settings(
            {"overlay.edge": "top", "overlay.orb_y": 1.5, "overlay.monitor": ["x"]}
        )
    assert (bad.edge, bad.orb_y, bad.monitor) == (OverlayEdge.RIGHT, 0.5, OverlayMonitor.CURSOR)
    assert sum(entry["event"] == "ignoring an invalid setting" for entry in logs) == 3
    good = overlay_settings(
        {"overlay.edge": "left", "overlay.orb_y": 0, "overlay.monitor": "primary"}
    )
    assert (good.edge, good.orb_y, good.monitor) == (OverlayEdge.LEFT, 0.0, OverlayMonitor.PRIMARY)
    assert overlay_settings({"overlay.orb_y": True}).orb_y == 0.5  # a bool is not a number here


async def test_overlay_setting_changes_send_a_snapshot(link: Link) -> None:
    await started(link)
    await link.container.settings_store.set("overlay.orb_y", 0.25, actor="user")
    assert link.snapshots()[-1]["overlay"]["orb_y"] == 0.25


async def test_overlay_input_is_accepted(link: Link) -> None:
    link.send({"type": "input", "action": "mic_mute", "source": "overlay"})
    await eventually(lambda: len(link.inputs) == 1)
    assert link.inputs[0].source == "overlay"


async def test_the_emergency_stop_cancels_running_tasks(link: Link) -> None:
    link.container.skills.register(DemoDangerousSkill())  # a task that waits for a yes
    result = await link.container.pipeline.submit("demo dangerous")
    assert result.task_id is not None
    for _ in range(200):  # the question is on screen
        messages = await link.container.history.recent_messages(10)
        if messages and messages[-1].text.endswith("Yes or no."):
            break
        await asyncio.sleep(0.01)
    assert link.container.supervisor.pending()
    link.send({"type": "input", "action": "emergency_stop", "source": "hotkey"})
    await eventually(lambda: not link.container.supervisor.pending())
    task = None
    for _ in range(200):
        task = await link.container.history.get_task(result.task_id)
        if task is not None and task.status is TaskStatus.CANCELLED:
            break
        await asyncio.sleep(0.01)
    assert task is not None
    assert (task.status, task.result_summary) == (TaskStatus.CANCELLED, "Stopped.")
    messages = await link.container.history.recent_messages(10)
    assert messages[-1].text == "Stopped."
    await eventually(lambda: [e.action for e in link.inputs] == [DesktopAction.EMERGENCY_STOP])
    await link.container.pipeline.close()
