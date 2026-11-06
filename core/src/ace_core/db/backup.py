"""Database backup files (ACE_MASTER_PLAN.md §13.4, D-49).

Names (local time):  ace-YYYYMMDD-HHMMSS.db               regular: daily + on demand, keep 7
                     ace-premigration-YYYYMMDD-HHMMSS.db  before a schema upgrade, keep 5
                     ace-prerestore-YYYYMMDD-HHMMSS.db    safety copy before a restore, keep 5
A ``-N`` suffix is added when two backups of a kind land in the same second.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final


class BackupKind(StrEnum):
    REGULAR = "regular"
    PREMIGRATION = "premigration"
    PRERESTORE = "prerestore"


DEFAULT_KEEP: Final[Mapping[BackupKind, int]] = {
    BackupKind.REGULAR: 7,
    BackupKind.PREMIGRATION: 5,
    BackupKind.PRERESTORE: 5,
}

_NAME: Final = re.compile(r"^ace-(?:(premigration|prerestore)-)?(\d{8}-\d{6})(?:-(\d+))?\.db$")


@dataclass(frozen=True, slots=True)
class BackupFile:
    path: Path
    kind: BackupKind
    stamp: str  # YYYYMMDD-HHMMSS, local time
    seq: int

    @property
    def day(self) -> date:
        return datetime.strptime(self.stamp[:8], "%Y%m%d").date()


def parse_backup_name(path: Path) -> BackupFile | None:
    match = _NAME.match(path.name)
    if match is None:
        return None
    kind = BackupKind(match.group(1)) if match.group(1) else BackupKind.REGULAR
    return BackupFile(path, kind, match.group(2), int(match.group(3) or 0))


class BackupStore:
    """Names, lists and prunes backup files in one directory. Does no database work itself."""

    def __init__(
        self,
        directory: Path,
        *,
        keep: Mapping[BackupKind, int] = DEFAULT_KEEP,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.directory = directory
        self._keep = dict(DEFAULT_KEEP) | dict(keep)
        self._now = now

    def list_backups(self, kind: BackupKind | None = None) -> list[BackupFile]:
        """Backups, newest first (optionally of one kind). Unrelated files are ignored."""
        if not self.directory.is_dir():
            return []
        found = [parse_backup_name(p) for p in self.directory.glob("ace-*.db")]
        backups = [b for b in found if b is not None and (kind is None or b.kind is kind)]
        return sorted(backups, key=lambda b: (b.stamp, b.seq), reverse=True)

    def new_path(self, kind: BackupKind) -> Path:
        """A unique path for a new backup of ``kind`` taken now."""
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = self._now().strftime("%Y%m%d-%H%M%S")
        prefix = "ace-" if kind is BackupKind.REGULAR else f"ace-{kind.value}-"
        seq = 0
        while True:
            name = f"{prefix}{stamp}{f'-{seq}' if seq else ''}.db"
            candidate = self.directory / name
            if not candidate.exists():
                return candidate
            seq += 1

    def prune(self, kind: BackupKind) -> list[Path]:
        """Delete the oldest backups of ``kind`` beyond its keep count."""
        removed: list[Path] = []
        for backup in self.list_backups(kind)[self._keep[kind] :]:
            backup.path.unlink(missing_ok=True)
            removed.append(backup.path)
        return removed

    def has_regular_backup_on(self, day: date) -> bool:
        return any(b.day == day for b in self.list_backups(BackupKind.REGULAR))


def copy_database(source: sqlite3.Connection, target: Path) -> None:
    """Consistent copy of a live database via the SQLite backup API (temp file, then rename)."""
    partial = target.with_name(target.name + ".partial")
    partial.unlink(missing_ok=True)
    with closing(sqlite3.connect(partial)) as destination:
        source.backup(destination)
    os.replace(partial, target)


def check_integrity(path: Path) -> bool:
    """True if ``path`` is a readable SQLite database that passes ``PRAGMA quick_check``."""
    if not path.is_file():
        return False
    try:
        with closing(sqlite3.connect(path)) as connection:
            rows = [row[0] for row in connection.execute("PRAGMA quick_check")]
    except sqlite3.DatabaseError:
        return False
    return rows == ["ok"]
