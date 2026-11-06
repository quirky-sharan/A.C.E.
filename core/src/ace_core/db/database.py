"""The core's SQLite database (ACE_MASTER_PLAN.md §13, D-47).

All database work - reads, writes, migrations, backups, restores - runs on ONE dedicated thread
("ace-db"), one job at a time. That makes the core a single writer (no "database is locked"),
keeps every SQLite connection on the thread that created it, and gives a simple async API:
``await db.run(lambda session: ...)``. A job keeps running even if its awaiting task is cancelled.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from functools import partial
from pathlib import Path
from typing import Final, TypeVar

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ace_core.db import migrate
from ace_core.db.backup import BackupKind, BackupStore, check_integrity, copy_database
from ace_core.db.engine import create_sqlite_engine

T = TypeVar("T")
DB_THREAD_PREFIX: Final = "ace-db"
_SIDECAR_SUFFIXES: Final = ("-wal", "-shm")


@dataclass(frozen=True, slots=True)
class StartReport:
    created: bool  # a new, empty database was created
    recovered_from: Path | None  # backup restored after the file failed its integrity check
    corrupt_copy: Path | None  # where the damaged file was moved (kept for diagnostics)
    premigration_backup: Path | None
    revision_before: str | None
    revision_after: str
    journal_mode: str


class Database:
    def __init__(
        self,
        path: Path,
        *,
        backups: BackupStore,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._path = path
        self._backups = backups
        self._now = now
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=DB_THREAD_PREFIX)
        self._engine: Engine | None = None
        self._sessions: sessionmaker[Session] | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def backups(self) -> BackupStore:
        return self._backups

    # ---- async API (each call is queued on the database thread) ----

    async def start(self) -> StartReport:
        """Check integrity (recovering if needed), back up before migrations, migrate to head."""
        return await self._call(self._start)

    async def run(self, work: Callable[[Session], T]) -> T:
        """Run ``work(session)`` in one transaction: committed on success, rolled back on error."""
        return await self._call(self._run_in_transaction, work)

    async def backup(self, kind: BackupKind = BackupKind.REGULAR) -> Path:
        return await self._call(self._backup, kind)

    async def ensure_daily_backup(self, today: date) -> Path | None:
        """Make today's regular backup unless one exists. Returns the new file, if any."""
        return await self._call(self._ensure_daily_backup, today)

    async def restore(self, backup: Path) -> Path:
        """Replace the database with ``backup``; returns the safety copy taken first."""
        return await self._call(self._restore, backup)

    async def close(self) -> None:
        try:
            await self._call(self._dispose)
        finally:
            await asyncio.to_thread(self._executor.shutdown, True)

    async def _call(self, fn: Callable[..., T], *args: object) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, partial(fn, *args))

    # ---- everything below runs on the database thread only ----

    def _open(self) -> Engine:
        if self._engine is None:
            self._engine = create_sqlite_engine(self._path)
            self._sessions = sessionmaker(self._engine, expire_on_commit=False)
        return self._engine

    def _dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
        self._engine = None
        self._sessions = None

    def _run_in_transaction(self, work: Callable[[Session], T]) -> T:
        self._open()
        if self._sessions is None:  # pragma: no cover - _open() always sets it
            raise RuntimeError("database is not open")
        with self._sessions() as session, session.begin():
            return work(session)

    def _start(self) -> StartReport:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        existed = self._path.exists()
        recovered_from: Path | None = None
        corrupt_copy: Path | None = None
        if existed and not check_integrity(self._path):
            corrupt_copy = self._quarantine()
            recovered_from = self._restore_newest_valid_backup()
            existed = recovered_from is not None

        engine = self._open()
        with engine.connect() as connection:
            before = migrate.current_revision(connection)
        head = migrate.head_revision()
        premigration = self._backup(BackupKind.PREMIGRATION) if existed and before != head else None
        with engine.begin() as connection:
            migrate.upgrade(connection, "head")
        with engine.connect() as connection:
            journal_mode = str(connection.exec_driver_sql("PRAGMA journal_mode").scalar_one())
        return StartReport(
            created=not existed,
            recovered_from=recovered_from,
            corrupt_copy=corrupt_copy,
            premigration_backup=premigration,
            revision_before=before,
            revision_after=head,
            journal_mode=journal_mode,
        )

    def _backup(self, kind: BackupKind) -> Path:
        engine = self._open()
        target = self._backups.new_path(kind)
        with engine.connect() as connection:
            source = connection.connection.driver_connection
            if not isinstance(source, sqlite3.Connection):  # pragma: no cover - sqlite3 driver
                raise TypeError("expected a sqlite3 connection")
            copy_database(source, target)
        self._backups.prune(kind)
        return target

    def _ensure_daily_backup(self, today: date) -> Path | None:
        if self._backups.has_regular_backup_on(today):
            return None
        return self._backup(BackupKind.REGULAR)

    def _restore(self, backup: Path) -> Path:
        if not check_integrity(backup):
            raise ValueError(f"backup failed the integrity check: {backup}")
        safety_copy = self._backup(BackupKind.PRERESTORE)
        self._copy_into_place(backup)
        with self._open().begin() as connection:
            migrate.upgrade(connection, "head")  # an older backup may predate newer migrations
        return safety_copy

    def _quarantine(self) -> Path:
        """Move a damaged database (and its WAL files) aside; it is never deleted automatically."""
        self._dispose()
        stamp = self._now().strftime("%Y%m%d-%H%M%S")
        target = self._path.with_name(f"ace-corrupt-{stamp}.db")
        os.replace(self._path, target)
        for suffix in _SIDECAR_SUFFIXES:
            sidecar = self._path.with_name(self._path.name + suffix)
            if sidecar.exists():
                os.replace(sidecar, target.with_name(target.name + suffix))
        return target

    def _restore_newest_valid_backup(self) -> Path | None:
        for backup in self._backups.list_backups():
            if check_integrity(backup.path):
                self._copy_into_place(backup.path)
                return backup.path
        return None

    def _copy_into_place(self, source: Path) -> None:
        self._dispose()
        # A stale WAL from the old file must never be replayed onto the restored one.
        for suffix in _SIDECAR_SUFFIXES:
            self._path.with_name(self._path.name + suffix).unlink(missing_ok=True)
        staging = self._path.with_name(self._path.name + ".restoring")
        shutil.copyfile(source, staging)
        os.replace(staging, self._path)
