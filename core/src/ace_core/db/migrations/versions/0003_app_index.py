"""S08: app_index

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "app_index",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("aumid", sa.Text(), nullable=True),
        sa.Column("exe_path", sa.Text(), nullable=True),
        sa.Column("icon_path", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.String(length=27), nullable=False),
        sa.Column("launch_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("kind IN ('aumid','exe','other')", name=op.f("ck_app_index_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_index")),
        sa.UniqueConstraint("target", name=op.f("uq_app_index_target")),
    )
    op.create_index("ix_app_index_normalized_name", "app_index", ["normalized_name"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_app_index_normalized_name", table_name="app_index")
    op.drop_table("app_index")
