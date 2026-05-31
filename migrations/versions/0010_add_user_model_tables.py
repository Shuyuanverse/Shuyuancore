"""add_user_model_tables

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-29 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 用户心理模型表
    op.create_table(
        "user_models",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("emotional_state", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("engagement_level", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("trust_level", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("frustration_level", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("curiosity_level", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("state_updated_at", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("interaction_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_interaction_at", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
    )

    # 用户目标表
    op.create_table(
        "user_goals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.Column("completed_at", sa.BigInteger, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["user_id"], ["user_models.user_id"], ondelete="CASCADE"),
    )

    # 用户偏好表
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.String(64), primary_key=False),
        sa.Column("category", sa.String(64), primary_key=True),
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("source", sa.String(64), nullable=False, server_default="inferred"),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user_models.user_id"], ondelete="CASCADE"),
    )

    # 用户预测记录表
    op.create_table(
        "user_predictions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("predicted_action", sa.String(255), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("suggested_response", sa.Text, nullable=True),
        sa.Column("alternative_actions_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("is_correct", sa.Boolean, nullable=True),
        sa.Column("feedback_at", sa.BigInteger, nullable=True),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user_models.user_id"], ondelete="CASCADE"),
    )

    op.create_index("idx_user_goals_user_status", "user_goals", ["user_id", "status"])
    op.create_index("idx_user_predictions_user_created", "user_predictions", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("user_predictions")
    op.drop_table("user_preferences")
    op.drop_table("user_goals")
    op.drop_table("user_models")
