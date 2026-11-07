"""Database events published on the in-process bus."""

from __future__ import annotations

from dataclasses import dataclass

from ace_core.app.events import Event


@dataclass(frozen=True, slots=True, kw_only=True)
class DatabaseRecovered(Event):
    """The database failed its integrity check at startup and was moved aside / restored."""

    corrupt_copy: str
    restored_from: str | None  # None: no valid backup existed, a fresh empty database was made


@dataclass(frozen=True, slots=True, kw_only=True)
class SettingChanged(Event):
    """A setting was stored or deleted (the value is not included; read it from the store)."""

    key: str
    actor: str
    deleted: bool = False
