"""add_beliefs_table

Revision ID: 0001
Revises:
Create Date: 2026-05-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "beliefs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("conversation_id", sa.String(64), nullable=False, index=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("base_confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("last_accessed", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("memory_type", sa.String(16), nullable=False, server_default="chat"),
        sa.Column("layer", sa.Integer, nullable=False, server_default="3"),
        sa.Column("entities", sa.Text, nullable=False, server_default="[]"),
        sa.Column("emotion", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("depends_on", sa.Text, nullable=False, server_default="[]"),
        sa.Column("child_belief_ids", sa.Text, nullable=False, server_default="[]"),
        sa.Column("superseded_by", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("is_composite", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("timestamp", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
    )

    op.create_index("idx_beliefs_layer", "beliefs", ["layer"])
    op.create_index("idx_beliefs_status", "beliefs", ["status"])
    op.create_index("idx_beliefs_memory_type", "beliefs", ["memory_type"])
    op.create_index("idx_beliefs_conversation_layer", "beliefs", ["conversation_id", "layer"])

    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS beliefs_fts "
        "USING fts5(content, content='beliefs', content_rowid='rowid')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS beliefs_fts")
    op.drop_table("beliefs")