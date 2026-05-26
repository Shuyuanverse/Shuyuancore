"""add approvals table for persistent approval storage

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-26

"""
from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: str = "0003"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("params_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("approved", sa.Boolean, nullable=True),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("resolved_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("timeout", sa.Integer, nullable=False, server_default="300"),
        sa.Column("stream_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("resolved_at", sa.Float, nullable=False, server_default="0.0"),
    )

    op.create_index("idx_approvals_user_id", "approvals", ["user_id"])
    op.create_index("idx_approvals_status", "approvals", ["user_id", "status"])
    op.create_index("idx_approvals_stream", "approvals", ["stream_id"], unique=False)


def downgrade() -> None:
    op.drop_table("approvals")