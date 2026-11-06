"""Settings and audit stores: CRUD, JSON values, validation, SQL injection, redaction, ordering."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import JsonValue, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from ace_core.db.database import Database
from ace_core.db.stores import AuditLog, SettingsStore
from ace_core.security.redaction import redact_text

INJECTION_PAYLOADS = [
    "'; DROP TABLE settings;--",
    '" OR 1=1 --',
    "Robert'); DROP TABLE audit_log;--",
    "%' OR '1'='1",
    "\\",
    "1; ATTACH DATABASE 'evil.db' AS evil;--",
    "key\nwith\nnewlines",
    "ユニコード ✓ नमस्ते",
]


def table_names(session: Session) -> set[str]:
    query = text("SELECT name FROM sqlite_master WHERE type = 'table'")
    return set(session.execute(query).scalars())


async def test_settings_crud(settings_store: SettingsStore) -> None:
    assert await settings_store.get("theme") is None
    assert await settings_store.get("theme", default="system") == "system"
    await settings_store.set("theme", "dark")
    assert await settings_store.get("theme") == "dark"
    await settings_store.set("theme", "light")
    assert await settings_store.get("theme") == "light"
    assert await settings_store.delete("theme") is True
    assert await settings_store.delete("theme") is False
    assert await settings_store.get("theme") is None


async def test_json_values_round_trip(settings_store: SettingsStore) -> None:
    value: JsonValue = {"list": [1, 2.5, None, True], "nested": {"a": "b"}, "text": "नमस्ते"}
    await settings_store.set("complex", value)
    assert await settings_store.get("complex") == value


@pytest.mark.parametrize("key", ["", "x" * 257, "bad\x00key"])
async def test_invalid_keys_are_rejected(settings_store: SettingsStore, key: str) -> None:
    with pytest.raises(ValidationError):
        await settings_store.set(key, 1)


async def test_injection_payloads_are_stored_literally_and_tables_survive(
    db: Database, settings_store: SettingsStore, audit: AuditLog
) -> None:
    for payload in INJECTION_PAYLOADS:
        await settings_store.set(payload, payload)
        await audit.record(
            actor="user", event_type="test.injection", summary=payload, data={"payload": payload}
        )

    for payload in INJECTION_PAYLOADS:
        assert await settings_store.get(payload) == payload
    assert {"settings", "audit_log"} <= await db.run(table_names)
    assert len(await settings_store.all()) == len(INJECTION_PAYLOADS)
    entries = await audit.recent(limit=100, event_type="test.injection")
    assert {e.summary for e in entries} == {redact_text(p) for p in INJECTION_PAYLOADS}


async def test_concurrent_writes_all_land(settings_store: SettingsStore) -> None:
    await asyncio.gather(*(settings_store.set(f"k{i}", i) for i in range(100)))
    assert await settings_store.all() == {f"k{i}": i for i in range(100)}


async def test_setting_changes_are_audited_without_their_values(
    settings_store: SettingsStore, audit: AuditLog
) -> None:
    await settings_store.set("theme", "dark", actor="user")
    (entry,) = await audit.recent(event_type="settings.changed")
    assert entry.actor == "user"
    assert entry.data == {"key": "theme"}
    assert "dark" not in json.dumps(entry.data)


async def test_audit_entries_are_redacted(audit: AuditLog) -> None:
    fake_key = "gsk_" + "k" * 30
    await audit.record(
        actor="system",
        event_type="provider.added",
        summary=f"added key {fake_key}",
        data={"api_key": fake_key, "note": f"stored {fake_key}"},
    )
    (entry,) = await audit.recent(event_type="provider.added")
    assert fake_key not in entry.summary
    assert entry.data["api_key"] == "[REDACTED]"
    assert fake_key not in entry.data["note"]


async def test_audit_input_is_validated(audit: AuditLog) -> None:
    with pytest.raises(ValidationError):
        await audit.record(actor="intruder", event_type="x", summary="x")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        await audit.record(actor="system", event_type="Not Valid!", summary="x")
    with pytest.raises(ValidationError):
        await audit.record(actor="system", event_type="ok", summary="x", tier="T9")  # type: ignore[arg-type]


async def test_audit_recent_is_newest_first(db: Database) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    times = iter([start, start + timedelta(days=1), start + timedelta(days=2)])
    audit = AuditLog(db, clock=lambda: next(times))
    for name in ("first", "second", "third"):
        await audit.record(actor="system", event_type="test.order", summary=name)
    entries = await audit.recent(event_type="test.order")
    assert [e.summary for e in entries] == ["third", "second", "first"]
