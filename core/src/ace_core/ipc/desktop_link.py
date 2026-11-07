"""Control channel between ace-desktop (the Tauri shell) and the core it started (§5.6, D-52).

ace-desktop starts the core with ``--supervised`` and talks to it over the child's stdio pipes.
Only the two processes hold those pipes, so the channel needs no token.

- core -> shell (stdout), one line each: ``ACE_READY port=<n>`` (written by the lifecycle), then
  ``ACE_DESKTOP <json>``: the conversation state plus the shell's settings (hotkeys, autostart,
  verification mode), sent after READY and again whenever any of them changes.
- shell -> core (stdin), one JSON object per line: hotkey / tray input, a verification-mode change
  and the shell's own status (hotkeys it could not register, autostart errors). End of file means
  "please shut down": the shell closes the pipe to quit, and Windows closes it if the shell dies.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, BinaryIO, Final, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError

from ace_core.app.container import Container
from ace_core.app.events import AppStarted, Event
from ace_core.app.health import HealthStatus
from ace_core.app.state import StateChanged
from ace_core.db.events import SettingChanged
from ace_core.ipc.methods import core_state_info
from ace_core.ipc.protocol import validation_summary
from ace_core.ipc.schemas import CoreStateInfo

log = structlog.stdlib.get_logger(__name__)

SNAPSHOT_PREFIX: Final = "ACE_DESKTOP"
MAX_LINE_BYTES: Final = 64 * 1024
MAX_SHORTCUT_CHARS: Final = 64
HEALTH_SUBSYSTEM: Final = "desktop"
SHUTDOWN_REASON: Final = "the desktop shell closed the control channel"

# Settings the shell applies (stored in the settings table; changed through IPC `settings.set`).
HOTKEY_SETTING_PREFIX: Final = "hotkeys."  # + action, e.g. "hotkeys.summon"; null or "" = off
AUTOSTART_SETTING: Final = "desktop.autostart"
MODE_SETTING: Final = "verification.mode"


class DesktopAction(StrEnum):
    """What a hotkey (D-29) or tray item asks for. Later stages give each one its behavior."""

    SUMMON = "summon"
    PUSH_TO_TALK = "push_to_talk"
    EMERGENCY_STOP = "emergency_stop"
    TOGGLE_OVERLAY = "toggle_overlay"
    MIC_MUTE = "mic_mute"


class VerificationMode(StrEnum):
    """D-09; the council (S18) acts on it."""

    FAST = "fast"
    BALANCED = "balanced"
    PARANOID = "paranoid"


# D-29. Ctrl+Alt+Space and Ctrl+Alt+M were taken on Sharan's PC, so those two have Shift (S04).
DEFAULT_HOTKEYS: Final[Mapping[DesktopAction, str]] = {
    DesktopAction.SUMMON: "Ctrl+Alt+Shift+Space",
    DesktopAction.PUSH_TO_TALK: "Ctrl+Alt+A",
    DesktopAction.EMERGENCY_STOP: "Ctrl+Alt+Escape",
    DesktopAction.TOGGLE_OVERLAY: "Ctrl+Alt+H",
    DesktopAction.MIC_MUTE: "Ctrl+Alt+Shift+M",
}
DEFAULT_MODE: Final = VerificationMode.BALANCED


class _Message(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---- shell -> core ----


class InputMessage(_Message):
    type: Literal["input"]
    action: DesktopAction
    source: Literal["hotkey", "tray"]
    phase: Literal["pressed", "released"] = "pressed"


class SetModeMessage(_Message):
    type: Literal["set_mode"]
    mode: VerificationMode


class HotkeyProblem(_Message):
    action: DesktopAction
    shortcut: str = Field(max_length=MAX_SHORTCUT_CHARS)
    error: str = Field(max_length=300)
    suggestion: str | None = Field(default=None, max_length=MAX_SHORTCUT_CHARS)


class DesktopStatusMessage(_Message):
    type: Literal["desktop_status"]
    hotkey_problems: list[HotkeyProblem] = Field(default_factory=list, max_length=16)
    autostart_error: str | None = Field(default=None, max_length=300)


ShellMessage = InputMessage | SetModeMessage | DesktopStatusMessage
_SHELL_MESSAGE: TypeAdapter[ShellMessage] = TypeAdapter(
    Annotated[ShellMessage, Field(discriminator="type")]
)


# ---- core -> shell ----


class DesktopSnapshot(_Message):
    """Everything the shell needs from the core; always sent whole."""

    state: CoreStateInfo
    hotkeys: dict[DesktopAction, str | None]  # None = no hotkey for this action
    autostart: bool
    mode: VerificationMode


@dataclass(frozen=True, slots=True, kw_only=True)
class DesktopInput(Event):
    """A hotkey or tray action from ace-desktop. S04 logs it; later stages act on it."""

    action: DesktopAction
    source: str
    phase: str


def shell_settings(
    stored: Mapping[str, JsonValue],
) -> tuple[dict[DesktopAction, str | None], bool, VerificationMode]:
    """Hotkeys, autostart and mode from stored settings; invalid values fall back to defaults."""
    hotkeys: dict[DesktopAction, str | None] = {}
    for action, default in DEFAULT_HOTKEYS.items():
        key = HOTKEY_SETTING_PREFIX + action.value
        value = stored.get(key, default)
        if value is None or value == "":
            hotkeys[action] = None
        elif isinstance(value, str) and len(value) <= MAX_SHORTCUT_CHARS:
            hotkeys[action] = value
        else:
            log.warning("ignoring an invalid setting", key=key)
            hotkeys[action] = default

    autostart = stored.get(AUTOSTART_SETTING, False)
    if not isinstance(autostart, bool):
        log.warning("ignoring an invalid setting", key=AUTOSTART_SETTING)
        autostart = False

    raw_mode = stored.get(MODE_SETTING, DEFAULT_MODE.value)
    try:
        mode = VerificationMode(raw_mode) if isinstance(raw_mode, str) else DEFAULT_MODE
    except ValueError:
        mode = DEFAULT_MODE
    if mode.value != raw_mode:
        log.warning("ignoring an invalid setting", key=MODE_SETTING)
    return hotkeys, autostart, mode


def _write_stdout_line(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


class DesktopLink:
    """Reads the shell's messages from stdin and keeps the shell's snapshot up to date."""

    def __init__(
        self,
        container: Container,
        request_shutdown: Callable[[str], None],
        *,
        stdin: BinaryIO | None = None,
        write_line: Callable[[str], None] = _write_stdout_line,
    ) -> None:
        self._container = container
        self._request_shutdown = request_shutdown
        self._stdin = stdin
        self._write_line = write_line
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._unsubscribers: list[Callable[[], None]] = []
        self._snapshot_lock = asyncio.Lock()
        self._ready = False  # no snapshot before the READY line
        self._output_broken = False
        self._last_line: str | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        bus = self._container.bus
        self._unsubscribers = [
            bus.subscribe(AppStarted, self._on_app_started),
            bus.subscribe(StateChanged, self._on_state_changed),
            bus.subscribe(SettingChanged, self._on_setting_changed),
        ]
        self._worker = self._loop.create_task(self._process(), name="ace-desktop-link")
        stream = self._stdin if self._stdin is not None else sys.stdin.buffer
        threading.Thread(
            target=self._read, args=(stream,), name="ace-desktop-link-reader", daemon=True
        ).start()
        log.info("desktop link enabled")

    async def stop(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers = []
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def snapshot(self) -> DesktopSnapshot:
        hotkeys, autostart, mode = shell_settings(await self._container.settings_store.all())
        return DesktopSnapshot(
            state=core_state_info(self._container.state.current),
            hotkeys=hotkeys,
            autostart=autostart,
            mode=mode,
        )

    # ---- stdin: a blocking reader thread hands complete lines to the event loop ----

    def _read(self, stream: BinaryIO) -> None:
        while True:
            try:
                raw = stream.readline(MAX_LINE_BYTES + 1)
            except (OSError, ValueError):
                raw = b""
            if not raw:
                self._hand_over(None)  # end of file: the shell wants the core to stop
                return
            if len(raw) > MAX_LINE_BYTES:
                rest = self._skip_rest_of_line(stream)
                if rest is None:
                    self._hand_over(None)
                    return
                raw = rest
            if not self._hand_over(raw):
                return

    @staticmethod
    def _skip_rest_of_line(stream: BinaryIO) -> bytes | None:
        """Drop an over-long line; returns b"" (reported as invalid) or None at end of file."""
        while True:
            try:
                rest = stream.readline(MAX_LINE_BYTES + 1)
            except (OSError, ValueError):
                return None
            if not rest:
                return None
            if rest.endswith(b"\n"):
                return b""

    def _hand_over(self, item: bytes | None) -> bool:
        loop = self._loop
        if loop is None:
            return False
        try:
            loop.call_soon_threadsafe(self._queue.put_nowait, item)
        except RuntimeError:  # the event loop is closed: the core is exiting anyway
            return False
        return True

    # ---- messages, in order, on the event loop ----

    async def _process(self) -> None:
        while True:
            raw = await self._queue.get()
            if raw is None:
                self._request_shutdown(SHUTDOWN_REASON)
                return
            try:
                message = _SHELL_MESSAGE.validate_json(raw)
            except ValidationError as exc:
                log.warning("desktop link: invalid message ignored", **validation_summary(exc))
                continue
            try:
                await self._handle(message)
            except Exception:
                log.exception("desktop link: a message failed", message_type=message.type)

    async def _handle(self, message: ShellMessage) -> None:
        if isinstance(message, InputMessage):
            log.info(
                "desktop input",
                action=message.action.value,
                source=message.source,
                phase=message.phase,
            )
            await self._container.bus.publish(
                DesktopInput(action=message.action, source=message.source, phase=message.phase)
            )
        elif isinstance(message, SetModeMessage):
            await self._container.settings_store.set(MODE_SETTING, message.mode.value, actor="user")
            log.info("verification mode set", mode=message.mode.value)
        else:
            await self._apply_status(message)

    async def _apply_status(self, message: DesktopStatusMessage) -> None:
        problems = [
            f"{p.shortcut} ({p.action.value}): {p.error}"
            + (f" - try {p.suggestion}" if p.suggestion else "")
            for p in message.hotkey_problems
        ]
        if message.autostart_error:
            problems.append(f"autostart: {message.autostart_error}")
        health = self._container.health
        if problems:
            log.warning("desktop shell problems", problems=problems)
            await health.set(HEALTH_SUBSYSTEM, HealthStatus.DEGRADED, "; ".join(problems)[:1000])
        else:
            await health.set(HEALTH_SUBSYSTEM, HealthStatus.OK)

    # ---- snapshots to the shell ----

    async def _on_app_started(self, _: AppStarted) -> None:
        self._ready = True
        await self._send_snapshot()

    async def _on_state_changed(self, _: StateChanged) -> None:
        await self._send_snapshot()

    async def _on_setting_changed(self, event: SettingChanged) -> None:
        if event.key.startswith(HOTKEY_SETTING_PREFIX) or event.key in (
            AUTOSTART_SETTING,
            MODE_SETTING,
        ):
            await self._send_snapshot()

    async def _send_snapshot(self) -> None:
        if not self._ready or self._output_broken:
            return
        async with self._snapshot_lock:  # one at a time, so the newest state is written last
            line = f"{SNAPSHOT_PREFIX} {(await self.snapshot()).model_dump_json()}"
            if line == self._last_line:
                return
            try:
                self._write_line(line)
            except (OSError, ValueError):
                self._output_broken = True
                log.warning("desktop link: cannot write to the desktop shell")
                return
            self._last_line = line
