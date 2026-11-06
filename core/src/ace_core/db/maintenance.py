"""Daily housekeeping (ACE_MASTER_PLAN.md §13.4, §13.5).

Runs once at startup and then every ``interval_s``: makes today's regular backup if it is missing,
then runs every registered retention job. Each step is isolated: one failure is logged and the rest
still run. Later stages register their own retention jobs (rules arrive with their tables).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from ace_core.db.database import Database
from ace_core.db.repositories import AuditLogRepository

log = structlog.stdlib.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class RetentionJob:
    """Deletes rows older than its rule. ``run(session, now)`` returns how many rows it deleted."""

    name: str
    run: Callable[[Session, datetime], int]


@dataclass(frozen=True, slots=True)
class MaintenanceReport:
    backup: Path | None
    deleted: dict[str, int]
    failed: tuple[str, ...]


def _bind(job: RetentionJob, now: datetime) -> Callable[[Session], int]:
    def call(session: Session) -> int:
        return job.run(session, now)

    return call


def audit_retention_job(days: int) -> RetentionJob:
    """``audit_log`` keeps ``days`` days (D-26: 90)."""

    def run(session: Session, now: datetime) -> int:
        return AuditLogRepository.delete_older_than(session, now - timedelta(days=days))

    return RetentionJob(name="audit_log", run=run)


class Maintenance:
    def __init__(
        self,
        db: Database,
        *,
        interval_s: float = 3600.0,
        utcnow: Callable[[], datetime] = _utcnow,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._db = db
        self._interval_s = interval_s
        self._utcnow = utcnow
        self._today = today
        self._jobs: list[RetentionJob] = []
        self._task: asyncio.Task[None] | None = None

    def register(self, job: RetentionJob) -> None:
        self._jobs.append(job)

    async def run_once(self) -> MaintenanceReport:
        failed: list[str] = []
        backup: Path | None = None
        try:
            backup = await self._db.ensure_daily_backup(self._today())
        except Exception:
            log.exception("daily backup failed")
            failed.append("backup")
        deleted: dict[str, int] = {}
        now = self._utcnow()
        for job in self._jobs:
            try:
                deleted[job.name] = await self._db.run(_bind(job, now))
            except Exception:
                log.exception("retention job failed", job=job.name)
                failed.append(job.name)
        log.info(
            "maintenance finished",
            backup=str(backup) if backup else None,
            deleted=deleted,
            failed=failed,
        )
        return MaintenanceReport(backup=backup, deleted=deleted, failed=tuple(failed))

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(
                self._loop(), name="ace-maintenance"
            )

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _loop(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self._interval_s)
