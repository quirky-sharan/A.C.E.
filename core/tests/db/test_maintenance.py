"""Maintenance: daily backup, audit retention, isolated failures, background loop."""

import asyncio
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from ace_core.db.database import Database
from ace_core.db.maintenance import Maintenance, RetentionJob, audit_retention_job
from ace_core.db.stores import AuditLog

DatabaseFactory = Callable[..., Database]

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


async def test_run_once_makes_todays_backup_only_once(make_database: DatabaseFactory) -> None:
    db = make_database(backup_clock=lambda: datetime(2026, 11, 6, 9, 0))
    await db.start()
    try:
        maintenance = Maintenance(db, utcnow=lambda: NOW, today=lambda: date(2026, 11, 6))
        first = await maintenance.run_once()
        second = await maintenance.run_once()
        assert first.backup is not None
        assert second.backup is None
        assert first.failed == ()
    finally:
        await db.close()


async def test_retention_deletes_only_rows_older_than_the_rule(db: Database) -> None:
    await AuditLog(db, clock=lambda: NOW - timedelta(days=91)).record(
        actor="system", event_type="test.old", summary="old"
    )
    await AuditLog(db, clock=lambda: NOW - timedelta(days=5)).record(
        actor="system", event_type="test.recent", summary="recent"
    )
    maintenance = Maintenance(db, utcnow=lambda: NOW, today=lambda: NOW.date())
    maintenance.register(audit_retention_job(90))

    report = await maintenance.run_once()

    assert report.deleted == {"audit_log": 1}
    assert {e.summary for e in await AuditLog(db).recent(limit=10)} == {"recent"}


async def test_a_failing_job_does_not_stop_the_others(db: Database) -> None:
    calls: list[datetime] = []

    def broken(_: Session, __: datetime) -> int:
        raise RuntimeError("boom")

    def healthy(_: Session, now: datetime) -> int:
        calls.append(now)
        return 0

    maintenance = Maintenance(db, utcnow=lambda: NOW, today=lambda: NOW.date())
    maintenance.register(RetentionJob("broken", broken))
    maintenance.register(RetentionJob("healthy", healthy))

    report = await maintenance.run_once()

    assert report.failed == ("broken",)
    assert report.deleted == {"healthy": 0}
    assert calls == [NOW]


async def test_start_runs_right_away_and_stop_cancels(db: Database) -> None:
    ran = threading.Event()

    def probe(_: Session, __: datetime) -> int:
        ran.set()
        return 0

    maintenance = Maintenance(db, interval_s=3600)
    maintenance.register(RetentionJob("probe", probe))
    await maintenance.start()
    try:
        assert await asyncio.to_thread(ran.wait, 10)
    finally:
        await maintenance.stop()
    await maintenance.stop()  # stopping twice is harmless
