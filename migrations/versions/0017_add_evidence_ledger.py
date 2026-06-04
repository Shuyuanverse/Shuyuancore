"""add memory evidence ledger

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_evidence",
        sa.Column("evidence_id", sa.String(128), primary_key=True),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False, server_default="anonymous"),
        sa.Column("turn_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("speaker", sa.String(16), nullable=False, server_default="user"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("timestamp", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversation_date", sa.String(32), nullable=True),
        sa.Column("entities", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("date_mentions", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("source", sa.String(32), nullable=False, server_default="chat"),
        sa.Column("metadata_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("created_at", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_index(
        "idx_memory_evidence_conversation",
        "memory_evidence",
        ["conversation_id", "turn_id", "timestamp"],
    )
    op.create_index(
        "idx_memory_evidence_user",
        "memory_evidence",
        ["user_id", "conversation_id", "timestamp"],
    )
    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS memory_evidence_fts "
        "USING fts5(content, content='memory_evidence', content_rowid='rowid')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_evidence_fts")
    op.drop_index("idx_memory_evidence_user", table_name="memory_evidence")
    op.drop_index("idx_memory_evidence_conversation", table_name="memory_evidence")
    op.drop_table("memory_evidence")
