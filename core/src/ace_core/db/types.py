"""Column types. Timestamps are fixed-width ISO-8601 UTC text, so text order = time order."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

TIMESTAMP_FORMAT: Final = "%Y-%m-%dT%H:%M:%S.%fZ"  # e.g. 2026-11-06T15:55:59.639107Z (27 chars)
TIMESTAMP_LENGTH: Final = 27


class UtcDateTime(TypeDecorator[datetime]):
    """Aware datetime stored as ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (UTC); naive values are refused."""

    impl = String(TIMESTAMP_LENGTH)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; use timezone-aware UTC datetimes")
        return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return datetime.strptime(str(value), TIMESTAMP_FORMAT).replace(tzinfo=UTC)
