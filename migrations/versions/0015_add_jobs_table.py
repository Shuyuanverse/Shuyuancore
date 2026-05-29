"""add jobs table for cron and condition-triggered tasks

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-29 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("schedule", sa.Text(), nullable=False),
        sa.Column("cron_parsed", sa.String(64), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("skill", sa.String(128), nullable=True),
        sa.Column("deliver_to", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("execution_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.BigInteger(), nullable=True),
        sa.Column("next_run_at", sa.BigInteger(), nullable=False),
        sa.Column("chain_next_job_id", sa.String(64), nullable=True),
        sa.Column("condition_trigger", sa.Text(), nullable=True),
        sa.Column("condition_state", sa.String(16), nullable=False, server_default="standby"),
        sa.Column("no_agent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )

    op.create_index("idx_jobs_active_next", "jobs", ["is_active", "next_run_at"])
    op.create_index("idx_jobs_condition", "jobs", ["condition_state"])


def downgrade() -> None:
    op.drop_table("jobs")