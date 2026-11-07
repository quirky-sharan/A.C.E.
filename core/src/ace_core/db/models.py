"""ORM models (ACE_MASTER_PLAN.md §13.3). Every schema change needs an Alembic migration too.

The test ``test_models_match_migrations`` fails if these models and the migrations ever drift apart.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, MetaData, String, Text
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


# ---- S07: conversations, messages, tasks, steps, confirmations ----


class ConversationRow(Base):
    __tablename__ = "conversations"
    __table_args__ = (CheckConstraint("channel IN ('voice','text')", name="channel"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    channel: Mapped[str] = mapped_column(String(8), nullable=False)


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','ace','system')", name="role"),
        CheckConstraint("source IN ('voice','text','notification')", name="source"),
        Index("ix_messages_conversation_id_ts", "conversation_id", "ts"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    stt_confidence: Mapped[float | None] = mapped_column(Float)
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class TaskRow(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("origin IN ('voice','text','routine','schedule','mcp')", name="origin"),
        CheckConstraint("mode IN ('fast','balanced','paranoid')", name="mode"),
        CheckConstraint(
            "status IN ('queued','running','waiting_user','verifying','succeeded','failed',"
            "'cancelled','interrupted')",
            name="status",
        ),
        Index("ix_tasks_status_created_at", "status", "created_at"),
        Index("ix_tasks_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL")
    )
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    utterance: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    allowed_caps_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    result_summary: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))


class TaskStepRow(Base):
    __tablename__ = "task_steps"
    __table_args__ = (
        CheckConstraint("tier IN ('T0','T1','T2','T3')", name="tier"),
        CheckConstraint(
            "status IN ('pending','running','waiting_user','succeeded','failed','cancelled',"
            "'refused')",
            name="status",
        ),
        Index("ix_task_steps_task_id_idx", "task_id", "idx", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    params_json: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    observation_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_code: Mapped[str | None] = mapped_column(String(64))


class ConfirmationRow(Base):
    __tablename__ = "confirmations"
    __table_args__ = (
        CheckConstraint("response IS NULL OR response IN ('yes','no','timeout')", name="response"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_steps.id", ondelete="CASCADE"), nullable=False
    )
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    response: Mapped[str | None] = mapped_column(String(8))
    channel: Mapped[str | None] = mapped_column(String(16))
    responded_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
