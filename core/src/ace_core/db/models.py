"""ORM models (ACE_MASTER_PLAN.md §13.3). Every schema change needs an Alembic migration too.

The test ``test_models_match_migrations`` fails if these models and the migrations ever drift apart.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, MetaData, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ace_core.db.types import UtcDateTime

# Explicit constraint names keep Alembic's SQLite "batch" migrations reliable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Setting(Base):
    """One configuration value, stored as JSON. Never holds secrets (§15.1)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class AuditLogEntry(Base):
    """Append-only record of what happened and who did it. ``data_json`` is always redacted."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("actor IN ('user','ace','verifier','system')", name="actor"),
        CheckConstraint("tier IS NULL OR tier IN ('T0','T1','T2','T3')", name="tier"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ts: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36))
    step_id: Mapped[str | None] = mapped_column(String(36))
    tier: Mapped[str | None] = mapped_column(String(2))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
