"""SQLite engine with ACE's connection settings (ACE_MASTER_PLAN.md §13.1, D-47).

``autocommit=False`` (Python 3.12+) gives PEP 249 transactions, so every unit of work - schema
migrations included - is all-or-nothing. PRAGMAs that cannot run inside a transaction are applied
with autocommit switched on briefly, as SQLAlchemy's SQLite documentation shows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Final

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.pool import ConnectionPoolEntry

CONNECTION_PRAGMAS: Final = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
)


def _apply_pragmas(dbapi_connection: sqlite3.Connection, _record: ConnectionPoolEntry) -> None:
    previous = dbapi_connection.autocommit
    dbapi_connection.autocommit = True
    try:
        for pragma in CONNECTION_PRAGMAS:
            dbapi_connection.execute(pragma)
    finally:
        dbapi_connection.autocommit = previous


def create_sqlite_engine(path: Path) -> Engine:
    """Engine for the database file at ``path`` (created on first use)."""
    url = URL.create("sqlite", database=str(path))
    engine = create_engine(url, connect_args={"autocommit": False})
    event.listen(engine, "connect", _apply_pragmas)
    return engine
