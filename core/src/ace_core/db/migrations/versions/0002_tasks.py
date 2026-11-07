"""S07: conversations, messages, tasks, task_steps, confirmations

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.String(length=27)  # UtcDateTime (D-48)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("ended_at", TS, nullable=True),
        sa.Column("channel", sa.String(length=8), nullable=False),
        sa.CheckConstraint("channel IN ('voice','text')", name=op.f("ck_conversations_channel")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("ts", TS, nullable=False),
        sa.Column("role", sa.String(length=8), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("stt_confidence", sa.Float(), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=False),
        sa.CheckConstraint("role IN ('user','ace','system')", name=op.f("ck_messages_role")),
        sa.CheckConstraint(
            "source IN ('voice','text','notification')", name=op.f("ck_messages_source")
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_conversation_id_ts", "messages", ["conversation_id", "ts"], unique=False
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("utterance", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("allowed_caps_json", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("started_at", TS, nullable=True),
        sa.Column("finished_at", TS, nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "origin IN ('voice','text','routine','schedule','mcp')", name=op.f("ck_tasks_origin")
        ),
        sa.CheckConstraint("mode IN ('fast','balanced','paranoid')", name=op.f("ck_tasks_mode")),
        sa.CheckConstraint(
            "status IN ('queued','running','waiting_user','verifying','succeeded','failed',"
            "'cancelled','interrupted')",
            name=op.f("ck_tasks_status"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_tasks_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index("ix_tasks_status_created_at", "tasks", ["status", "created_at"], unique=False)
    op.create_index("ix_tasks_created_at", "tasks", ["created_at"], unique=False)
    op.create_table(
        "task_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column("tier", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", TS, nullable=True),
        sa.Column("finished_at", TS, nullable=True),
        sa.Column("observation_json", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint("tier IN ('T0','T1','T2','T3')", name=op.f("ck_task_steps_tier")),
        sa.CheckConstraint(
            "status IN ('pending','running','waiting_user','succeeded','failed','cancelled',"
            "'refused')",
            name=op.f("ck_task_steps_status"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_steps_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_steps")),
    )
    op.create_index("ix_task_steps_task_id_idx", "task_steps", ["task_id", "idx"], unique=True)
    op.create_table(
        "confirmations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=36), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("requested_at", TS, nullable=False),
        sa.Column("response", sa.String(length=8), nullable=True),
        sa.Column("channel", sa.String(length=16), nullable=True),
        sa.Column("responded_at", TS, nullable=True),
        sa.CheckConstraint(
            "response IS NULL OR response IN ('yes','no','timeout')",
            name=op.f("ck_confirmations_response"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_confirmations_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["task_steps.id"],
            name=op.f("fk_confirmations_step_id_task_steps"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_confirmations")),
    )
    op.create_index(op.f("ix_confirmations_task_id"), "confirmations", ["task_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_confirmations_task_id"), table_name="confirmations")
    op.drop_table("confirmations")
    op.drop_index("ix_task_steps_task_id_idx", table_name="task_steps")
    op.drop_table("task_steps")
    op.drop_index("ix_tasks_created_at", table_name="tasks")
    op.drop_index("ix_tasks_status_created_at", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_messages_conversation_id_ts", table_name="messages")
    op.drop_table("messages")
    op.drop_table("conversations")
