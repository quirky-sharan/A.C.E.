"""The assembled app: database + maintenance start and stop with the lifecycle."""

from pathlib import Path

from ace_core.app.bootstrap import create_app
from ace_core.app.config import load_settings
from ace_core.app.events import AppStarted
from ace_core.app.health import HealthStatus
from ace_core.app.lifecycle import EXIT_OK, App
from ace_core.app.paths import AppPaths
from ace_core.db.events import DatabaseRecovered


def build(tmp_path: Path) -> tuple[App, AppPaths, list[str]]:
    paths = AppPaths.under(tmp_path, portable=False)
    paths.ensure()
    lines: list[str] = []
    app = create_app(load_settings(config_file=None), paths, ready_writer=lines.append)

    async def stop(_: AppStarted) -> None:
        app.request_shutdown("test")

    app.container.bus.subscribe(AppStarted, stop)
    return app, paths, lines


def subsystem_status(app: App, name: str) -> HealthStatus:
    (item,) = [s for s in app.container.health.snapshot().subsystems if s.name == name]
    return item.status


async def test_app_starts_the_database_and_stops_cleanly(tmp_path: Path) -> None:
    app, paths, lines = build(tmp_path)
    assert await app.run() == EXIT_OK
    assert lines == ["ACE_READY port=0"]
    assert (paths.data / "ace.db").is_file()
    assert subsystem_status(app, "database") is HealthStatus.OK


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
