"""Alembic environment for ACE.

The app passes its own connection (``ace_core.db.migrate``). The fallback below exists only for the
developer CLI (``alembic.ini``), which works on a throwaway dev database.
"""

from __future__ import annotations

from pathlib import Path

from alembic import context
from sqlalchemy import Connection, make_url

from ace_core.db.engine import create_sqlite_engine
from ace_core.db.models import Base

config = context.config
target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    url = make_url(config.get_main_option("sqlalchemy.url") or "")
    if not url.database:
        raise RuntimeError("alembic.ini needs sqlalchemy.url for command-line use")
    db_path = Path(url.database)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_sqlite_engine(db_path)
    try:
        with engine.begin() as dev_connection:
            _run(dev_connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) migrations are not supported for ACE.")
run_migrations_online()
