"""add messages and sessions tables

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-29 12:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 消息表 — schema matches src/core/conversation.py CREATE TABLE IF NOT EXISTS
    op.create_table(
        "messages",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
    )

    op.create_index("idx_messages_conversation", "messages", ["conversation_id", "created_at"])
    op.create_index("idx_messages_role", "messages", ["role"])

    # FTS5 全文检索虚拟表（由 conversation.py 触发器管理，
    # 此处仅创建结构，INSERT/UPDATE/DELETE 触发器由运行时代码通过
    # CREATE TRIGGER IF NOT EXISTS 注册，确保不会重复创建）
    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts "
        "USING fts5(content, content='messages', content_rowid='rowid')"
    )

    # 会话表
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("platform", sa.String(32), nullable=False, server_default="cli"),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("identity_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("current_model", sa.String(64), nullable=False, server_default="dashscope/qwen-max"),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("archived_at", sa.BigInteger(), nullable=True),
    )

    op.create_index("idx_sessions_user_updated", "sessions", ["user_id", "updated_at"])
    op.create_index("idx_sessions_status", "sessions", ["status", "updated_at"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS messages_fts")
    op.drop_table("messages")
    op.drop_table("sessions")
