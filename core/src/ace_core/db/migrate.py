"""Programmatic Alembic: the app migrates its own database (ACE_MASTER_PLAN.md §13.1).

Each call runs on a connection the caller opened with ``engine.begin()``, so a migration either
completes fully or leaves the database unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection

MIGRATIONS_DIR: Final = Path(__file__).resolve().parent / "migrations"


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if head is None:
        raise RuntimeError(f"no migrations found in {MIGRATIONS_DIR}")
    return head


def current_revision(connection: Connection) -> str | None:
    """The revision the database is at, or None for an empty database."""
    return MigrationContext.configure(connection).get_current_revision()


def upgrade(connection: Connection, target: str = "head") -> None:
    command.upgrade(alembic_config(connection), target)


def downgrade(connection: Connection, target: str) -> None:
    command.downgrade(alembic_config(connection), target)
