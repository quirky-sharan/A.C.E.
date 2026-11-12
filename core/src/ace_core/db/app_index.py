"""Stores the app index (§13.3 ``app_index``). A refresh replaces the list but keeps each app's id
and launch count, matched by its AppsFolder target."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ace_core.db.database import Database
from ace_core.db.ids import new_id
from ace_core.db.models import AppIndexRow
from ace_core.db.repositories import AppIndexRepository
from ace_core.os.base import AppKind
from ace_core.skills.app_index import IndexedApp, normalize_name


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _app(row: AppIndexRow) -> IndexedApp:
    return IndexedApp(
        name=row.name,
        kind=AppKind(row.kind),
        target=row.target,
        aumid=row.aumid,
        exe_path=row.exe_path,
        launch_count=row.launch_count,
    )


class AppIndexStore:
    def __init__(self, db: Database, *, clock: Callable[[], datetime] = _utcnow) -> None:
        self._db = db
        self._clock = clock

    async def all(self) -> list[IndexedApp]:
        def load(session: Session) -> list[IndexedApp]:
            return [_app(row) for row in AppIndexRepository.all(session)]

        return await self._db.run(load)

    async def replace(self, apps: list[IndexedApp]) -> int:
        now = self._clock()
        unique = {app.target: app for app in apps}  # one row per AppsFolder id

        def save(session: Session) -> int:
            existing = AppIndexRepository.by_target(session)
            for target, app in unique.items():
                row = existing.get(target)
                if row is None:
                    AppIndexRepository.add(
                        session,
                        AppIndexRow(
                            id=new_id(),
                            name=app.name,
                            normalized_name=normalize_name(app.name),
                            kind=app.kind.value,
                            target=target,
                            aumid=app.aumid,
                            exe_path=app.exe_path,
                            last_seen_at=now,
                            launch_count=0,
                        ),
                    )
                else:
                    row.name = app.name
                    row.normalized_name = normalize_name(app.name)
                    row.kind = app.kind.value
                    row.aumid = app.aumid
                    row.exe_path = app.exe_path
                    row.last_seen_at = now
            AppIndexRepository.delete_targets(
                session, [target for target in existing if target not in unique]
            )
            return len(unique)

        return await self._db.run(save)

    async def note_launch(self, target: str) -> None:
        def save(session: Session) -> None:
            row = AppIndexRepository.get_by_target(session, target)
            if row is not None:
                row.launch_count += 1

        await self._db.run(save)
