"""Application lifecycle (ACE_MASTER_PLAN.md §5.6).

startup hooks -> health "core" ok -> ``ACE_READY port=<n>`` on stdout -> AppStarted -> wait ->
AppStopping -> shutdown hooks in reverse order (bounded by ``shutdown_timeout_s``) -> exit code.

Windows note: ``loop.add_signal_handler()`` is not supported on Windows, so Ctrl+C (SIGINT) and
Ctrl+Break (SIGBREAK) are caught with ``signal.signal()`` on the main thread. The first signal asks
for a graceful shutdown; a second one forces the process to exit.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from types import FrameType
from typing import Any, Final

import structlog

from ace_core.app.container import Container
from ace_core.app.events import AppStarted, AppStopping
from ace_core.app.health import HealthStatus
from ace_core.app.version import __version__

log = structlog.stdlib.get_logger(__name__)

READY_PREFIX: Final = "ACE_READY"
EXIT_OK: Final = 0
EXIT_STARTUP_FAILED: Final = 1
EXIT_FORCED: Final = 130

Hook = Callable[[], Awaitable[None]]


def _write_ready_line(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def shutdown_signals() -> tuple[int, ...]:
    """Signals that mean "please stop": Ctrl+C and Ctrl+Break on Windows (+ SIGTERM elsewhere)."""
    signals: list[int] = [signal.SIGINT]
    ctrl_break = getattr(signal, "SIGBREAK", None)
    if ctrl_break is not None:
        signals.append(ctrl_break)
    if sys.platform != "win32":
        signals.append(signal.SIGTERM)
    return tuple(signals)


class App:
    """Runs the core until a shutdown is requested."""

    def __init__(
        self,
        container: Container,
        *,
        ready_writer: Callable[[str], None] = _write_ready_line,
        force_exit: Callable[[int], Any] = os._exit,
    ) -> None:
        self._container = container
        self._startup_hooks: list[tuple[str, Hook]] = []
        self._shutdown_hooks: list[tuple[str, Hook]] = []
        self._stop = asyncio.Event()
        self._stop_reason = "unknown"
        self._stop_requested_at: float | None = None
        self._signal_count = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready_writer = ready_writer
        self._force_exit = force_exit
        self.port = 0  # IPC port; stays 0 until stage S03 adds the IPC server

    @property
    def container(self) -> Container:
        return self._container

    def on_startup(self, name: str, hook: Hook) -> None:
        self._startup_hooks.append((name, hook))

    def on_shutdown(self, name: str, hook: Hook) -> None:
        self._shutdown_hooks.append((name, hook))

    def request_shutdown(self, reason: str) -> None:
        """Ask for a graceful stop. Call on the event-loop thread (signals hop over safely)."""
        if self._stop.is_set():
            return
        self._stop_reason = reason
        self._stop_requested_at = time.monotonic()
        log.info("shutdown requested", reason=reason)
        self._stop.set()

    async def run(self) -> int:
        self._loop = asyncio.get_running_loop()
        restore_signals = self._install_signal_handlers()
        try:
            return await self._run()
        finally:
            restore_signals()

    async def _run(self) -> int:
        container = self._container
        log.info(
            "starting",
            version=__version__,
            portable=container.paths.portable,
            dev=container.settings.dev,
            root=str(container.paths.root),
        )
        for name, hook in self._startup_hooks:
            try:
                await hook()
            except Exception:
                log.exception("startup hook failed", hook=name)
                await container.health.set(
                    "core", HealthStatus.DOWN, f"startup hook failed: {name}"
                )
                await self._run_shutdown_hooks()
                return EXIT_STARTUP_FAILED

        await container.health.set("core", HealthStatus.OK)
        self._ready_writer(f"{READY_PREFIX} port={self.port}")
        log.info("ready", port=self.port)
        await container.bus.publish(AppStarted(version=__version__))

        await self._stop.wait()
        await container.bus.publish(AppStopping(reason=self._stop_reason))
        await self._run_shutdown_hooks()
        requested = self._stop_requested_at
        duration_ms = round((time.monotonic() - requested) * 1000) if requested is not None else 0
        log.info("shutdown complete", reason=self._stop_reason, duration_ms=duration_ms)
        return EXIT_OK

    async def _run_shutdown_hooks(self) -> None:
        timeout_s = self._container.settings.shutdown_timeout_s
        try:
            async with asyncio.timeout(timeout_s):
                for name, hook in reversed(self._shutdown_hooks):
                    try:
                        await hook()
                    except Exception:
                        log.exception("shutdown hook failed", hook=name)
                await self._container.bus.drain()
        except TimeoutError:
            log.warning("shutdown timed out; exiting anyway", timeout_s=timeout_s)

    def _install_signal_handlers(self) -> Callable[[], None]:
        if threading.current_thread() is not threading.main_thread():
            return lambda: None  # signal.signal() only works on the main thread
        previous = {sig: signal.getsignal(sig) for sig in shutdown_signals()}
        for sig in previous:
            signal.signal(sig, self._handle_signal)

        def restore() -> None:
            for sig, handler in previous.items():
                if handler is not None:
                    signal.signal(sig, handler)

        return restore

    def _handle_signal(self, signum: int, _frame: FrameType | None) -> None:
        """Runs on the main thread between bytecodes: only schedule work here, never log."""
        self._signal_count += 1
        if self._signal_count > 1:
            self._force_exit(EXIT_FORCED)
            return
        if self._loop is not None:
            name = signal.Signals(signum).name
            self._loop.call_soon_threadsafe(self.request_shutdown, f"signal:{name}")
