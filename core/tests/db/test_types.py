"""UtcDateTime: ISO-8601 UTC text, conversion, refusal of naive values, sortable text."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import sqlite

from ace_core.db.types import UtcDateTime

DIALECT = sqlite.dialect()


def test_round_trip_keeps_the_exact_utc_instant() -> None:
    column = UtcDateTime()
    value = datetime(2026, 11, 6, 15, 55, 59, 639107, tzinfo=UTC)
    stored = column.process_bind_param(value, DIALECT)
    assert stored == "2026-11-06T15:55:59.639107Z"
    assert column.process_result_value(stored, DIALECT) == value


def test_other_timezones_are_converted_to_utc() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    stored = UtcDateTime().process_bind_param(datetime(2026, 11, 6, 21, 25, tzinfo=ist), DIALECT)
    assert stored == "2026-11-06T15:55:00.000000Z"


def test_naive_datetimes_are_refused() -> None:
    with pytest.raises(ValueError, match="naive"):
        UtcDateTime().process_bind_param(datetime(2026, 11, 6), DIALECT)


def test_none_passes_through() -> None:
    column = UtcDateTime()
    assert column.process_bind_param(None, DIALECT) is None
    assert column.process_result_value(None, DIALECT) is None


def test_text_order_matches_time_order() -> None:
    column = UtcDateTime()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    offsets = (0, 1, 999_999, 1_000_000, 86_400_000_000)
    texts = [
        str(column.process_bind_param(base + timedelta(microseconds=n), DIALECT)) for n in offsets
    ]
    assert texts == sorted(texts)
