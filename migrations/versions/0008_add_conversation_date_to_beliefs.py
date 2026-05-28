"""add conversation_date column to beliefs table

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "beliefs",
        sa.Column("conversation_date", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("beliefs", "conversation_date")