"""add_working_memory_tables

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 工作记忆项目表
    op.create_table(
        "working_memory_projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_name", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.Column("last_accessed_at", sa.BigInteger, nullable=False, index=True),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
    )

    # 工作记忆待办表
    op.create_table(
        "working_memory_todos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.Column("completed_at", sa.BigInteger, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["working_memory_projects.id"], ondelete="CASCADE"
        ),
    )

    op.create_index("idx_todos_project_status", "working_memory_todos", ["project_id", "status"])
    op.create_index("idx_todos_priority", "working_memory_todos", ["priority"])


def downgrade() -> None:
    op.drop_table("working_memory_todos")
    op.drop_table("working_memory_projects")
