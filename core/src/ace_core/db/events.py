"""Database events published on the in-process bus."""

from __future__ import annotations

from dataclasses import dataclass

from ace_core.app.events import Event


@dataclass(frozen=True, slots=True, kw_only=True)
class DatabaseRecovered(Event):
    """The database failed its integrity check at startup and was moved aside / restored."""

    corrupt_copy: str
    restored_from: str | None  # None: no valid backup existed, a fresh empty database was made
