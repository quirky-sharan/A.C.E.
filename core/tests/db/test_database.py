"""Database: fresh start, one thread, rollback, pre-migration backup, restore, recovery."""

import asyncio
import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ace_core.db import migrate
from ace_core.db.backup import BackupKind, check_integrity
from ace_core.db.database import DB_THREAD_PREFIX, Database
from ace_core.db.repositories import SettingsRepository
from ace_core.db.stores import AuditLog, SettingsStore

DatabaseFactory = Callable[..., Database]


def store_for(db: Database) -> SettingsStore:
    return SettingsStore(db, AuditLog(db))


def table_names(session: Session) -> set[str]:
    query = text("SELECT name FROM sqlite_master WHERE type = 'table'")
    return set(session.execute(query).scalars())


def corrupt(path: Path) -> None:
    with path.open("r+b") as handle:
        handle.write(b"this is definitely not an SQLite header!!")


async def test_fresh_start_creates_a_wal_database_at_head(make_database: DatabaseFactory) -> None:
    db = make_database()
    report = await db.start()
    try:
        assert report.created is True
        assert report.revision_before is None
        assert report.revision_after == migrate.head_revision()
        assert report.journal_mode == "wal"
        assert report.premigration_backup is None
        assert report.corrupt_copy is None
        assert db.path.is_file()
        assert {"settings", "audit_log", "alembic_version"} <= await db.run(table_names)
        foreign_keys = await db.run(lambda s: s.execute(text("PRAGMA foreign_keys")).scalar_one())
        assert foreign_keys == 1
    finally:
        await db.close()


async def test_all_work_runs_on_one_thread_one_job_at_a_time(db: Database) -> None:
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}
    threads: set[str] = set()

    def job(_: Session) -> None:
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        threads.add(threading.current_thread().name)
        time.sleep(0.001)
        with lock:
            state["active"] -= 1

    await asyncio.gather(*(db.run(job) for _ in range(50)))
    assert state["peak"] == 1
    assert len(threads) == 1
    assert next(iter(threads)).startswith(DB_THREAD_PREFIX)


async def test_failed_work_is_rolled_back(db: Database) -> None:
    def write_then_fail(session: Session) -> None:
        SettingsRepository.upsert(session, "half-done", "1", datetime.now(UTC))
        raise RuntimeError("fail after writing")

    with pytest.raises(RuntimeError):
        await db.run(write_then_fail)
    assert await store_for(db).get("half-done") is None


async def test_older_schema_is_backed_up_before_migrating(make_database: DatabaseFactory) -> None:
    first = make_database()
    await first.start()
    await first.run(lambda session: migrate.downgrade(session.connection(), "base"))
    await first.close()

    second = make_database()
    report = await second.start()
    try:
        assert report.revision_before is None
        assert report.premigration_backup is not None
        assert report.premigration_backup.name.startswith("ace-premigration-")
        assert check_integrity(report.premigration_backup)
        assert {"settings", "audit_log"} <= await second.run(table_names)
    finally:
        await second.close()


async def test_backup_then_restore_brings_back_old_data(db: Database) -> None:
    store = store_for(db)
    await store.set("theme", "dark")
    backup = await db.backup()
    assert backup.name.startswith("ace-")
    assert check_integrity(backup)

    await store.set("theme", "light")
    safety_copy = await db.restore(backup)

    assert await store.get("theme") == "dark"
    assert safety_copy.name.startswith("ace-prerestore-")
    assert check_integrity(safety_copy)


async def test_restore_refuses_a_damaged_backup(db: Database, tmp_path: Path) -> None:
    bad = tmp_path / "ace-20261106-000000.db"
    bad.write_bytes(b"garbage")
    with pytest.raises(ValueError, match="integrity"):
        await db.restore(bad)


async def test_damaged_database_is_moved_aside_and_restored_from_backup(
    make_database: DatabaseFactory,
) -> None:
    first = make_database()
    await first.start()
    await store_for(first).set("theme", "dark")
    backup = await first.backup()
    await first.close()
    corrupt(first.path)

    second = make_database()
    report = await second.start()
    try:
        assert report.corrupt_copy is not None
        assert report.corrupt_copy.is_file()
        assert report.corrupt_copy.name.startswith("ace-corrupt-")
        assert report.recovered_from == backup
        assert await store_for(second).get("theme") == "dark"
    finally:
        await second.close()


async def test_damaged_database_without_backups_starts_empty(
    make_database: DatabaseFactory,
) -> None:
    first = make_database()
    await first.start()
    await first.close()
    corrupt(first.path)

    second = make_database()
    report = await second.start()
    try:
        assert report.corrupt_copy is not None
        assert report.recovered_from is None
        assert report.created is True
        assert await store_for(second).all() == {}
    finally:
        await second.close()


async def test_daily_backup_is_made_once_per_day(make_database: DatabaseFactory) -> None:
    db = make_database(backup_clock=lambda: datetime(2026, 11, 6, 9, 0, 0))
    await db.start()
    try:
        made = await db.ensure_daily_backup(date(2026, 11, 6))
        again = await db.ensure_daily_backup(date(2026, 11, 6))
        assert made is not None
        assert again is None
        assert len(db.backups.list_backups(BackupKind.REGULAR)) == 1
    finally:
        await db.close()


async def test_work_after_close_is_refused(make_database: DatabaseFactory) -> None:
    db = make_database()
    await db.start()
    await db.close()
    with pytest.raises(RuntimeError):
        await db.run(lambda _: None)
