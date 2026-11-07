"""Shared test fixtures."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest
import structlog

from ace_core.db.backup import BackupStore
from ace_core.db.database import Database
from ace_core.db.history import HistoryStore
from ace_core.db.stores import AuditLog, SettingsStore

ACE_SETTING_ENV_VARS = (
    "ACE_LOG_LEVEL",
    "ACE_LOG_RETENTION_DAYS",
    "ACE_SHUTDOWN_TIMEOUT_S",
    "ACE_DEV",
    "ACE_DB_BACKUPS_KEEP",
    "ACE_AUDIT_RETENTION_DAYS",
    "ACE_IPC_PORT",
    "ACE_SAFE_MODE",
    "ACE_HOME",  # a dev-only paths override (S08)
)


@pytest.fixture(autouse=True)
def _isolated_logging() -> Iterator[None]:
    """Every test starts and ends with the default logging and structlog state."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    structlog.reset_defaults()
    root.handlers = handlers
    root.setLevel(level)


@pytest.fixture(autouse=True)
def _no_ace_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings must come only from what each test provides, not from the developer's shell."""
    for name in ACE_SETTING_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


# ---- database fixtures: every test gets its own database under tmp_path ----


@pytest.fixture
def make_database(tmp_path: Path) -> Callable[..., Database]:
    """New (not started) Database objects that share one file and one backups folder."""

    def factory(backup_clock: Callable[[], datetime] = datetime.now) -> Database:
        data = tmp_path / "data"
        return Database(data / "ace.db", backups=BackupStore(data / "backups", now=backup_clock))

    return factory


@pytest.fixture
async def db(make_database: Callable[..., Database]) -> AsyncIterator[Database]:
    database = make_database()
    await database.start()
    yield database
    await database.close()


@pytest.fixture
def audit(db: Database) -> AuditLog:
    return AuditLog(db)


@pytest.fixture
def settings_store(db: Database, audit: AuditLog) -> SettingsStore:
    return SettingsStore(db, audit)


@pytest.fixture
def history(db: Database) -> HistoryStore:
    return HistoryStore(db)
