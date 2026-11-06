"""Lifecycle: READY line, events, hook order, failures, shutdown timeout, signal handling."""

import asyncio
import signal
from collections.abc import Callable
from pathlib import Path
from typing import Any

from structlog.testing import capture_logs

from ace_core.app.config import load_settings
from ace_core.app.container import build_container
from ace_core.app.events import AppStarted, AppStopping
from ace_core.app.health import HealthStatus
from ace_core.app.lifecycle import EXIT_FORCED, EXIT_OK, EXIT_STARTUP_FAILED, App, shutdown_signals
from ace_core.app.paths import AppPaths


def make_app(
    tmp_path: Path, *, timeout_s: float = 5.0, force_exit: Callable[[int], Any] | None = None
) -> tuple[App, list[str]]:
    lines: list[str] = []
    settings = load_settings(config_file=None, overrides={"shutdown_timeout_s": timeout_s})
    container = build_container(settings, AppPaths.under(tmp_path, portable=False))
    if force_exit is None:
        return App(container, ready_writer=lines.append), lines
    return App(container, ready_writer=lines.append, force_exit=force_exit), lines


def stop_when_started(app: App, reason: str = "test") -> None:
    async def stop(_: AppStarted) -> None:
        app.request_shutdown(reason)

    app.container.bus.subscribe(AppStarted, stop)


async def test_ready_line_events_health_and_clean_exit(tmp_path: Path) -> None:
    app, lines = make_app(tmp_path)
    seen: list[str] = []

    async def on_stopping(event: AppStopping) -> None:
        seen.append(event.reason)

    app.container.bus.subscribe(AppStopping, on_stopping)
    stop_when_started(app, "unit-test")
    assert await app.run() == EXIT_OK
    assert lines == ["ACE_READY port=0"]
    assert seen == ["unit-test"]
    assert app.container.health.snapshot().overall is HealthStatus.OK


async def test_hooks_run_in_order_and_shutdown_hooks_in_reverse(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    calls: list[str] = []

    def hook(name: str) -> Callable[[], Any]:
        async def run() -> None:
            calls.append(name)

        return run

    app.on_startup("a", hook("start-a"))
    app.on_startup("b", hook("start-b"))
    app.on_shutdown("x", hook("stop-x"))
    app.on_shutdown("y", hook("stop-y"))
    stop_when_started(app)
    assert await app.run() == EXIT_OK
    assert calls == ["start-a", "start-b", "stop-y", "stop-x"]


async def test_failing_startup_hook_fails_fast_and_still_cleans_up(tmp_path: Path) -> None:
    app, lines = make_app(tmp_path)
    cleaned: list[str] = []

    async def broken() -> None:
        raise RuntimeError("cannot start")

    async def cleanup() -> None:
        cleaned.append("done")

    app.on_startup("broken", broken)
    app.on_shutdown("cleanup", cleanup)
    with capture_logs() as logs:
        assert await app.run() == EXIT_STARTUP_FAILED
    assert lines == []
    assert cleaned == ["done"]
    assert app.container.health.snapshot().overall is HealthStatus.DOWN
    assert any(entry["event"] == "startup hook failed" for entry in logs)


async def test_slow_shutdown_hook_is_cut_off_by_the_timeout(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path, timeout_s=0.2)

    async def slow() -> None:
        await asyncio.sleep(30)

    app.on_shutdown("slow", slow)
    stop_when_started(app)
    loop = asyncio.get_running_loop()
    started = loop.time()
    with capture_logs() as logs:
        assert await app.run() == EXIT_OK
    assert loop.time() - started < 2.0
    assert any(entry["event"] == "shutdown timed out; exiting anyway" for entry in logs)


async def test_signal_handlers_are_installed_while_running_and_restored(tmp_path: Path) -> None:
    before = {sig: signal.getsignal(sig) for sig in shutdown_signals()}
    app, _ = make_app(tmp_path)
    during: dict[int, Any] = {}

    async def inspect(_: AppStarted) -> None:
        during.update({sig: signal.getsignal(sig) for sig in shutdown_signals()})
        app.request_shutdown("inspected")

    app.container.bus.subscribe(AppStarted, inspect)
    assert await app.run() == EXIT_OK
    assert all(handler == app._handle_signal for handler in during.values())
    assert {sig: signal.getsignal(sig) for sig in shutdown_signals()} == before


async def test_first_signal_requests_a_graceful_shutdown(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    reasons: list[str] = []

    async def fire(_: AppStarted) -> None:
        app._handle_signal(signal.SIGINT, None)

    async def on_stopping(event: AppStopping) -> None:
        reasons.append(event.reason)

    app.container.bus.subscribe(AppStarted, fire)
    app.container.bus.subscribe(AppStopping, on_stopping)
    assert await app.run() == EXIT_OK
    assert reasons == ["signal:SIGINT"]


async def test_second_signal_forces_exit(tmp_path: Path) -> None:
    forced: list[int] = []
    app, _ = make_app(tmp_path, force_exit=forced.append)

    async def fire_twice(_: AppStarted) -> None:
        app._handle_signal(signal.SIGINT, None)
        app._handle_signal(signal.SIGINT, None)

    app.container.bus.subscribe(AppStarted, fire_twice)
    assert await app.run() == EXIT_OK
    assert forced == [EXIT_FORCED]
