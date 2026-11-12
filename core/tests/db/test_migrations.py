"""Migrations: upgrade / downgrade round trip, and models never drift from the migrations."""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect

from ace_core.db import migrate
from ace_core.db.engine import create_sqlite_engine
from ace_core.db.models import Base

APP_TABLES = {
    "settings",
    "audit_log",
    "conversations",
    "messages",
    "tasks",
    "task_steps",
    "confirmations",
    "app_index",
}


def app_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_head_is_the_latest_revision() -> None:
    assert migrate.head_revision() == "0003"  # S08: app_index


def test_upgrade_downgrade_upgrade_round_trip(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "round-trip.db")
    try:
        with engine.begin() as connection:
            migrate.upgrade(connection, "head")
        assert app_tables(engine) == APP_TABLES
        with engine.connect() as connection:
            assert migrate.current_revision(connection) == migrate.head_revision()

        with engine.begin() as connection:
            migrate.downgrade(connection, "base")
        assert app_tables(engine) == set()
        with engine.connect() as connection:
            assert migrate.current_revision(connection) is None

        with engine.begin() as connection:
            migrate.upgrade(connection, "head")
        assert app_tables(engine) == APP_TABLES
    finally:
        engine.dispose()


def test_models_match_migrations(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "drift.db")
    try:
        with engine.begin() as connection:
            migrate.upgrade(connection, "head")
        with engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        assert differences == []
    finally:
        engine.dispose()
