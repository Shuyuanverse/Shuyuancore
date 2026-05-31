"""add personas, identities, and curator_runs tables

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-29 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 人格档案表
    op.create_table(
        "personas",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("profile", sa.Text(), nullable=False),
        sa.Column("style_vector", sa.Text(), nullable=True),
        sa.Column("anchor_vector", sa.Text(), nullable=True),
        sa.Column("created_from", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("source_text_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )

    # 身份表
    op.create_table(
        "identities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="general"),
        sa.Column("type", sa.String(16), nullable=False, server_default="work"),
        sa.Column("persona_id", sa.String(64), nullable=True),
        sa.Column("profile_path", sa.Text(), nullable=True),
        sa.Column("memory_path", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )

    op.create_index("idx_identities_mode_active", "identities", ["mode", "is_active"])

    # Curator 运行记录表
    op.create_table(
        "curator_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("phase", sa.String(16), nullable=False, server_default="phase1"),
        sa.Column("skills_examined", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skills_retained", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skills_patched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skills_merged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skills_archived", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skills_flagged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("iterations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_path", sa.Text(), nullable=True),
        sa.Column("started_at", sa.BigInteger(), nullable=False),
        sa.Column("completed_at", sa.BigInteger(), nullable=True),
    )

    op.create_index("idx_curator_runs_started", "curator_runs", ["started_at"])


def downgrade() -> None:
    op.drop_table("curator_runs")
    op.drop_table("identities")
    op.drop_table("personas")