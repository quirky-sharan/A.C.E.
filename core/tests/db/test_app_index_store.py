"""AppIndexStore: a refresh replaces the list but keeps ids and launch counts (§13.3 app_index)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from ace_core.db.app_index import AppIndexStore
from ace_core.db.database import Database
from ace_core.db.models import AppIndexRow
from ace_core.os.base import AppKind
from ace_core.skills.app_index import IndexedApp


def app(name: str, target: str, kind: AppKind = AppKind.PACKAGED) -> IndexedApp:
    return IndexedApp(name, kind, target, target if kind is AppKind.PACKAGED else None, None)


@pytest.fixture
def store(db: Database) -> AppIndexStore:
    return AppIndexStore(db)


async def test_refresh_keeps_ids_and_launch_counts(db: Database, store: AppIndexStore) -> None:
    assert await store.replace([app("Spotify", "s!a"), app("Notepad", "n!a")]) == 2

    def ids(session: Session) -> dict[str, str]:
        return {row.target: row.id for row in session.scalars(select(AppIndexRow))}

    before = await db.run(ids)
    await store.note_launch("s!a")
    await store.note_launch("s!a")
    await store.note_launch("unknown")  # ignored
    assert (
        await store.replace([app("Spotify Music", "s!a"), app("Chrome", "c", AppKind.DESKTOP)]) == 2
    )
    after = {a.target: a for a in await store.all()}
    assert set(after) == {"s!a", "c"}  # Notepad left the Start menu
    assert after["s!a"].name == "Spotify Music"
    assert after["s!a"].launch_count == 2
    assert (await db.run(ids))["s!a"] == before["s!a"]
    assert [a.name for a in await store.all()] == ["Chrome", "Spotify Music"]  # by normalized name


async def test_duplicate_targets_are_stored_once(store: AppIndexStore) -> None:
    assert await store.replace([app("A", "x!1"), app("A again", "x!1")]) == 1
    assert [a.name for a in await store.all()] == ["A again"]
