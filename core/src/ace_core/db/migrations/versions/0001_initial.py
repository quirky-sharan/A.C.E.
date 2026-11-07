"""initial: settings and audit_log

Revision ID: 0001
Revises:
Create Date: 2026-11-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=256), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ts", sa.String(length=27), nullable=False),
        sa.Column("actor", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("step_id", sa.String(length=36), nullable=True),
        sa.Column("tier", sa.String(length=2), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "actor IN ('user','ace','verifier','system')", name=op.f("ck_audit_log_actor")
        ),
        sa.CheckConstraint(
            "tier IS NULL OR tier IN ('T0','T1','T2','T3')", name=op.f("ck_audit_log_tier")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_ts"), "audit_log", ["ts"], unique=False)
    op.create_index(op.f("ix_audit_log_event_type"), "audit_log", ["event_type"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_audit_log_event_type"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_ts"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("settings")
