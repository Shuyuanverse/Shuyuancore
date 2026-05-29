"""add_evolution_tables

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-29 10:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 自演化模块表
    op.create_table(
        "evolution_modules",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("memory_partition", sa.String(255), nullable=True),
        sa.Column("skill_subgraph", sa.Text, nullable=True),
        sa.Column("trigger_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_trigger_at", sa.BigInteger, nullable=True, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("archived_at", sa.BigInteger, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
    )

    # 模块协作记录表
    op.create_table(
        "evolution_collaborations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("from_module", sa.String(64), nullable=False),
        sa.Column("to_module", sa.String(64), nullable=False),
        sa.Column("timestamp", sa.BigInteger, nullable=False),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
    )

    op.create_index("idx_collaboration_modules", "evolution_collaborations", ["from_module", "to_module"])
    op.create_index("idx_collaboration_timestamp", "evolution_collaborations", ["timestamp"])


def downgrade() -> None:
    op.drop_table("evolution_collaborations")
    op.drop_table("evolution_modules")
