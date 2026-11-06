"""Builds the running core: container + App + the startup / shutdown hooks of every service."""

from __future__ import annotations

from typing import Any

import structlog

from ace_core.app.config import Settings
from ace_core.app.container import Container, build_container
from ace_core.app.health import HealthStatus
from ace_core.app.lifecycle import App
from ace_core.app.paths import AppPaths
from ace_core.db.database import StartReport
from ace_core.db.events import DatabaseRecovered

log = structlog.stdlib.get_logger(__name__)


def create_app(settings: Settings, paths: AppPaths, **app_options: Any) -> App:
    """``app_options`` are passed to :class:`App` (tests inject the READY writer, for example)."""
    container = build_container(settings, paths)
    app = App(container, **app_options)

    async def start_database() -> None:
        report = await container.db.start()
        await _announce_database(container, report)

    app.on_startup("database", start_database)
    app.on_startup("maintenance", container.maintenance.start)
    # Shutdown hooks run in reverse: maintenance stops first, then the database closes.
    app.on_shutdown("database", container.db.close)
    app.on_shutdown("maintenance", container.maintenance.stop)
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
