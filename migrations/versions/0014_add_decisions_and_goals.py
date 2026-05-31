"""add decisions, decision_patterns, and goals tables

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-29 12:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 决策记录表
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("options", sa.Text(), nullable=False),
        sa.Column("chosen", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state_at_time", sa.Text(), nullable=True),
        sa.Column("verified", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )

    op.create_index("idx_decisions_user_created", "decisions", ["user_id", "created_at"])
    op.create_index("idx_decisions_tags", "decisions", ["tags"])

    # 决策模式表
    op.create_table(
        "decision_patterns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_used_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )

    op.create_index("idx_dp_created", "decision_patterns", ["created_at"])

    # 目标追踪表
    op.create_table(
        "goals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("dependencies", sa.Text(), nullable=True),
        sa.Column("parent_goal_id", sa.String(64), nullable=True),
        sa.Column("auto_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("completed_at", sa.BigInteger(), nullable=True),
    )

    op.create_index("idx_goals_user_status", "goals", ["user_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_table("goals")
    op.drop_table("decision_patterns")
    op.drop_table("decisions")