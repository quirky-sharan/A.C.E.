"""Builds the running core: container + App + the startup / shutdown hooks of every service."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from typing import Any, Final

import structlog

from ace_core.app.config import Settings
from ace_core.app.container import Container, build_container
from ace_core.app.health import HealthStatus
from ace_core.app.lifecycle import App
from ace_core.app.paths import AppPaths
from ace_core.app.version import __version__
from ace_core.db.database import StartReport
from ace_core.db.events import DatabaseRecovered
from ace_core.ipc.desktop_link import DesktopLink
from ace_core.ipc.runtime_file import IpcEndpoint, remove_runtime_file, write_runtime_file
from ace_core.ipc.server import IpcServer

log = structlog.stdlib.get_logger(__name__)

# The desktop shell passes the per-run IPC token in this variable (§5.6).
IPC_TOKEN_ENV: Final = "ACE_IPC_TOKEN"  # noqa: S105 - the variable's name, not a secret


def create_app(
    settings: Settings,
    paths: AppPaths,
    *,
    environ: MutableMapping[str, str] = os.environ,
    supervised: bool = False,
    **app_options: Any,
) -> App:
    """Build the core. ``supervised``: started by ace-desktop, which talks over stdin / stdout
    (D-52). ``app_options`` go to :class:`App` (tests inject the READY writer, for example)."""
    container = build_container(settings, paths)
    app = App(container, **app_options)
    # pop(): the token must not leak into processes the core starts later.
    ipc = IpcServer(container, port=settings.ipc_port, token=environ.pop(IPC_TOKEN_ENV, None))

    async def start_database() -> None:
        report = await container.db.start()
        await _announce_database(container, report)

    async def start_ipc() -> None:
        app.port = await ipc.start()
        write_runtime_file(
            paths.runtime,
            IpcEndpoint(port=app.port, token=ipc.token, pid=os.getpid(), version=__version__),
        )

    async def stop_ipc() -> None:
        remove_runtime_file(paths.runtime, pid=os.getpid())
        await ipc.stop()

    app.on_startup("database", start_database)
    app.on_startup("maintenance", container.maintenance.start)

    async def start_apps() -> None:
        if container.apps is not None:
            await (
                container.apps.index.start()
            )  # loads the stored index, refreshes in the background

    async def stop_apps() -> None:
        if container.apps is not None:
            await container.apps.index.stop()
        await container.com.close()

    app.on_startup("apps", start_apps)
    app.on_startup("ipc", start_ipc)
    # Shutdown hooks run in reverse: IPC closes first, then the pipeline, maintenance, database.
    app.on_shutdown("database", container.db.close)
    app.on_shutdown("maintenance", container.maintenance.stop)
    app.on_shutdown("apps", stop_apps)
    app.on_shutdown("pipeline", container.pipeline.close)  # running tasks -> interrupted
    app.on_shutdown("ipc", stop_ipc)
    if supervised:
        link = DesktopLink(container, app.request_shutdown)
        app.on_startup("desktop-link", link.start)
        app.on_shutdown("desktop-link", link.stop)  # runs first: no snapshots while stopping
    return app


async def _announce_database(container: Container, report: StartReport) -> None:
    log.info(
        "database ready",
        path=str(container.db.path),
        created=report.created,
        revision_before=report.revision_before,
        revision=report.revision_after,
        journal_mode=report.journal_mode,
        premigration_backup=str(report.premigration_backup) if report.premigration_backup else None,
    )
    if report.corrupt_copy is not None:
        restored = str(report.recovered_from) if report.recovered_from is not None else None
        log.warning(
            "database failed its integrity check and was recovered",
            corrupt_copy=str(report.corrupt_copy),
            restored_from=restored,
        )
        detail = (
            f"restored from backup {restored}"
            if restored
            else "no valid backup existed; started an empty database"
        )
        await container.health.set("database", HealthStatus.DEGRADED, detail)
        await container.audit.record(
            actor="system",
            event_type="db.recovered",
            summary=f"damaged database moved aside; {detail}",
            data={"corrupt_copy": str(report.corrupt_copy), "restored_from": restored},
        )
        await container.bus.publish(
            DatabaseRecovered(corrupt_copy=str(report.corrupt_copy), restored_from=restored)
        )
    else:
        await container.health.set("database", HealthStatus.OK)
    if report.premigration_backup is not None:
        await container.audit.record(
            actor="system",
            event_type="db.migrated",
            summary=(
                f"schema upgraded from {report.revision_before or 'empty'} "
                f"to {report.revision_after}"
            ),
            data={"backup": str(report.premigration_backup)},
        )
