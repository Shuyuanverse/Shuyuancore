"""add messages and sessions tables

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-29 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 消息表
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("platform", sa.String(32), nullable=False, server_default="cli"),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )

    op.create_index("idx_messages_session_created", "messages", ["session_id", "created_at"])
    op.create_index("idx_messages_user_created", "messages", ["user_id", "created_at"])

    # FTS5 全文检索虚拟表
    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts "
        "USING fts5(content, content='messages', content_rowid='id')"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN "
        "INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN "
        "INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN "
        "INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content); "
        "INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content); END"
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
    op.execute("DROP TRIGGER IF EXISTS messages_au")
    op.execute("DROP TRIGGER IF EXISTS messages_ad")
    op.execute("DROP TRIGGER IF EXISTS messages_ai")
    op.execute("DROP TABLE IF EXISTS messages_fts")
    op.drop_table("messages")
    op.drop_table("sessions")