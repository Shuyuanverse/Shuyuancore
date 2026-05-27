"""add source column to skill_nodes

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-26

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str = "0006"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "skill_nodes",
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
    )
    op.create_index("idx_skill_nodes_source", "skill_nodes", ["source"])


def downgrade() -> None:
    op.drop_index("idx_skill_nodes_source", table_name="skill_nodes")
    op.drop_column("skill_nodes", "source")
