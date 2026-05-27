"""add audit_logs table for persistent audit logging

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-26

"""
from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: str = "0005"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Text(), nullable=False, index=True),
        sa.Column("action", sa.Text(), nullable=False, index=True),
        sa.Column("resource", sa.Text(), nullable=False, default=""),
        sa.Column("params_json", sa.Text(), nullable=False, default="{}"),
        sa.Column("result", sa.Text(), nullable=False, default="success"),
        sa.Column("approved", sa.Boolean(), nullable=True),
        sa.Column("approval_id", sa.Text(), nullable=False, default=""),
        sa.Column("duration_ms", sa.Float(), nullable=False, default=0.0),
        sa.Column("ip_address", sa.Text(), nullable=False, default=""),
        sa.Column("error", sa.Text(), nullable=False, default=""),
        sa.Column("timestamp", sa.Float(), nullable=False),
    )
    op.create_index("idx_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    op.drop_index("idx_audit_logs_timestamp", table_name="audit_logs")
    op.drop_table("audit_logs")