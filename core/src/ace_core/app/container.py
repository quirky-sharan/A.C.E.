"""Explicit dependency container: everything the core needs, built once at startup."""

from __future__ import annotations

from dataclasses import dataclass

from ace_core.app.config import Settings
from ace_core.app.events import EventBus
from ace_core.app.health import HealthRegistry
from ace_core.app.paths import AppPaths
from ace_core.app.state import StateStore
from ace_core.db.backup import BackupKind, BackupStore
from ace_core.db.database import Database
from ace_core.db.maintenance import Maintenance, audit_retention_job
from ace_core.db.stores import AuditLog, SettingsStore

DB_FILE_NAME = "ace.db"


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    paths: AppPaths
    bus: EventBus
    health: HealthRegistry
    state: StateStore
    db: Database
    audit: AuditLog
    settings_store: SettingsStore
    maintenance: Maintenance


def build_container(settings: Settings, paths: AppPaths) -> Container:
    """Create every service. Nothing touches the disk until the app's startup hooks run."""
    bus = EventBus()
    backups = BackupStore(
        paths.data / "backups", keep={BackupKind.REGULAR: settings.db_backups_keep}
    )
    db = Database(paths.data / DB_FILE_NAME, backups=backups)
    audit = AuditLog(db)
    maintenance = Maintenance(db)
    maintenance.register(audit_retention_job(settings.audit_retention_days))
    return Container(
        settings=settings,
        paths=paths,
        bus=bus,
        health=HealthRegistry(bus),
        state=StateStore(bus),
        db=db,
        audit=audit,
        settings_store=SettingsStore(db, audit, bus=bus),
        maintenance=maintenance,
    )
