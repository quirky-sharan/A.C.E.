"""The assembled app: database, maintenance and IPC start and stop with the lifecycle."""

from pathlib import Path

from ace_core.app.bootstrap import IPC_TOKEN_ENV, create_app
from ace_core.app.config import load_settings
from ace_core.app.events import AppStarted
from ace_core.app.health import HealthStatus
from ace_core.app.lifecycle import EXIT_OK, App
from ace_core.app.paths import AppPaths
from ace_core.db.events import DatabaseRecovered
from ace_core.ipc.runtime_file import IpcEndpoint, read_runtime_file


def build(tmp_path: Path, environ: dict[str, str] | None = None) -> tuple[App, AppPaths, list[str]]:
    paths = AppPaths.under(tmp_path, portable=False)
    paths.ensure()
    lines: list[str] = []
    app = create_app(
        load_settings(config_file=None),
        paths,
        environ=environ if environ is not None else {},
        ready_writer=lines.append,
    )

    async def stop(_: AppStarted) -> None:
        app.request_shutdown("test")

    app.container.bus.subscribe(AppStarted, stop)
    return app, paths, lines


def subsystem_status(app: App, name: str) -> HealthStatus:
    (item,) = [s for s in app.container.health.snapshot().subsystems if s.name == name]
    return item.status


async def test_app_starts_database_and_ipc_then_stops_cleanly(tmp_path: Path) -> None:
    app, paths, lines = build(tmp_path)
    seen: list[IpcEndpoint | None] = []

    async def capture_runtime_file(_: AppStarted) -> None:
        seen.append(read_runtime_file(paths.runtime))

    app.container.bus.subscribe(AppStarted, capture_runtime_file)
    assert await app.run() == EXIT_OK

    (line,) = lines
    port = int(line.removeprefix("ACE_READY port="))
    assert port > 0
    (endpoint,) = seen
    assert endpoint is not None
    assert endpoint.port == port
    assert read_runtime_file(paths.runtime) is None  # removed on shutdown
    assert (paths.data / "ace.db").is_file()
    assert subsystem_status(app, "database") is HealthStatus.OK


async def test_token_from_the_shell_is_used_and_removed_from_the_environment(
    tmp_path: Path,
) -> None:
    shell_token = "s" * 43
    environ = {IPC_TOKEN_ENV: shell_token, "OTHER": "kept"}
    app, paths, _ = build(tmp_path, environ)
    tokens: list[str] = []

    async def capture_token(_: AppStarted) -> None:
        endpoint = read_runtime_file(paths.runtime)
        tokens.append(endpoint.token if endpoint else "")

    app.container.bus.subscribe(AppStarted, capture_token)
    assert await app.run() == EXIT_OK
    assert tokens == [shell_token]
    assert environ == {"OTHER": "kept"}


async def test_damaged_database_is_reported_as_degraded(tmp_path: Path) -> None:
    app, paths, _ = build(tmp_path)
    (paths.data / "ace.db").write_bytes(b"not a database at all, just bytes")
    recovered: list[DatabaseRecovered] = []

    async def remember(event: DatabaseRecovered) -> None:
        recovered.append(event)

    app.container.bus.subscribe(DatabaseRecovered, remember)
    assert await app.run() == EXIT_OK
    assert subsystem_status(app, "database") is HealthStatus.DEGRADED
    assert len(recovered) == 1
    assert recovered[0].restored_from is None
    assert list(paths.data.glob("ace-corrupt-*.db"))
