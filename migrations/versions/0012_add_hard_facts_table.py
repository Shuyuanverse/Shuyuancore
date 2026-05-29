"""add_hard_facts_table

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-29 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hard_facts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("category", sa.String(64), nullable=False, index=True),
        sa.Column("sub_category", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("verified", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("verification_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_verified_at", sa.BigInteger, nullable=True),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
    )

    op.create_index("idx_hard_facts_category_sub", "hard_facts", ["category", "sub_category"])
    op.create_index("idx_hard_facts_verified", "hard_facts", ["verified"])


def downgrade() -> None:
    op.drop_table("hard_facts")
