"""Explicit dependency container: everything the core needs, built once at startup."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from ace_core.app.config import Settings
from ace_core.app.events import EventBus
from ace_core.app.health import HealthRegistry
from ace_core.app.paths import AppPaths
from ace_core.app.state import StateStore
from ace_core.brain.pipeline import CommandPipeline
from ace_core.brain.router import Router
from ace_core.brain.supervisor import Supervisor
from ace_core.db.app_index import AppIndexStore
from ace_core.db.backup import BackupKind, BackupStore
from ace_core.db.database import Database
from ace_core.db.history import HistoryStore
from ace_core.db.maintenance import Maintenance, audit_retention_job
from ace_core.db.stores import AuditLog, SettingsStore
from ace_core.os.com import ComThread
from ace_core.skills.app_index import AppIndex
from ace_core.skills.apps import AppsPorts
from ace_core.skills.catalog import build_registry
from ace_core.skills.registry import SkillRegistry

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
    history: HistoryStore
    skills: SkillRegistry
    supervisor: Supervisor
    pipeline: CommandPipeline
    com: ComThread
    apps: AppsPorts | None  # None where app control is unavailable (not Windows)


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
    state = StateStore(bus)
    settings_store = SettingsStore(db, audit, bus=bus)
    history = HistoryStore(db)
    com = ComThread()
    apps = _desktop_ports(db, com)
    skills = build_registry(settings=settings_store, dev=settings.dev, apps=apps)
    supervisor = Supervisor(history=history, audit=audit, bus=bus)
    pipeline = CommandPipeline(
        registry=skills,
        router=Router(skills),
        supervisor=supervisor,
        history=history,
        audit=audit,
        bus=bus,
        state=state,
        settings=settings_store,
    )
    return Container(
        settings=settings,
        paths=paths,
        bus=bus,
        health=HealthRegistry(bus),
        state=state,
        db=db,
        audit=audit,
        settings_store=settings_store,
        maintenance=maintenance,
        history=history,
        skills=skills,
        supervisor=supervisor,
        pipeline=pipeline,
        com=com,
        apps=apps,
    )


def _desktop_ports(db: Database, com: ComThread) -> AppsPorts | None:
    """The Win32 adapters for the apps & windows skills (D-57); None off Windows."""
    if sys.platform != "win32":
        return None
    from ace_core.os.win32 import ExplorerLauncher, Win32StartMenu, Win32Windows

    index = AppIndex(AppIndexStore(db), Win32StartMenu(com))
    return AppsPorts(index=index, windows=Win32Windows(com), launcher=ExplorerLauncher(com))
