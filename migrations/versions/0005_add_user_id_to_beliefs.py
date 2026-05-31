"""add user_id column to beliefs table for multi-tenant support

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-26

"""
from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: str = "0004"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.execute("ALTER TABLE beliefs ADD COLUMN user_id TEXT NOT NULL DEFAULT 'anonymous'")
    op.create_index("idx_beliefs_user_id", "beliefs", ["user_id"])
    op.create_index(
        "idx_beliefs_user_conversation",
        "beliefs",
        ["user_id", "conversation_id", "layer"],
    )


def downgrade() -> None:
    op.drop_index("idx_beliefs_user_conversation", table_name="beliefs")
    op.drop_index("idx_beliefs_user_id", table_name="beliefs")
    op.execute("ALTER TABLE beliefs DROP COLUMN user_id")