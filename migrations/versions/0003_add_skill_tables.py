"""add skill tables (skill_nodes, skill_edges, skill_usage)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-26

"""
from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: str = "0002"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "skill_nodes",
        sa.Column("node_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column(
            "node_type",
            sa.String(16),
            nullable=False,
            server_default="skill",
        ),
        sa.Column("belief_id", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("tags", sa.Text, nullable=False, server_default="[]"),
        sa.Column(
            "preconditions", sa.Text, nullable=False, server_default="[]"
        ),
        sa.Column(
            "causality_level0", sa.Text, nullable=False, server_default=""
        ),
        sa.Column(
            "causality_level1", sa.Text, nullable=False, server_default=""
        ),
        sa.Column(
            "causality_level2", sa.Text, nullable=False, server_default=""
        ),
        sa.Column(
            "boundaries", sa.Text, nullable=False, server_default="[]"
        ),
        sa.Column(
            "failure_modes", sa.Text, nullable=False, server_default="[]"
        ),
        sa.Column(
            "dependencies", sa.Text, nullable=False, server_default="[]"
        ),
        sa.Column(
            "version_history", sa.Text, nullable=False, server_default="[]"
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "is_pinned", sa.Boolean, nullable=False, server_default="0"
        ),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("updated_at", sa.BigInteger, nullable=False),
    )

    op.create_index(
        "idx_skill_nodes_status", "skill_nodes", ["status"]
    )
    op.create_index(
        "idx_skill_nodes_belief", "skill_nodes", ["belief_id"]
    )
    op.create_index(
        "idx_skill_nodes_name", "skill_nodes", ["name"]
    )

    op.create_table(
        "skill_edges",
        sa.Column("edge_id", sa.String(64), primary_key=True),
        sa.Column("from_node", sa.String(128), nullable=False),
        sa.Column("to_node", sa.String(128), nullable=False),
        sa.Column(
            "edge_type",
            sa.String(20),
            nullable=False,
            server_default="enables",
        ),
        sa.Column("created_at", sa.BigInteger, nullable=False),
    )

    op.create_index(
        "idx_skill_edges_from", "skill_edges", ["from_node"]
    )
    op.create_index(
        "idx_skill_edges_to", "skill_edges", ["to_node"]
    )

    op.create_table(
        "skill_usage",
        sa.Column("usage_id", sa.String(64), primary_key=True),
        sa.Column("skill_name", sa.String(128), nullable=False),
        sa.Column(
            "conversation_id", sa.String(64), nullable=False, server_default=""
        ),
        sa.Column("invoked_at", sa.BigInteger, nullable=False),
        sa.Column("success", sa.Boolean, nullable=True),
        sa.Column(
            "user_feedback",
            sa.String(16),
            nullable=True,
        ),
        sa.Column("duration_ms", sa.Integer, nullable=True),
    )

    op.create_index(
        "idx_skill_usage_name", "skill_usage", ["skill_name"]
    )
    op.create_index(
        "idx_skill_usage_conversation",
        "skill_usage",
        ["conversation_id"],
    )

    # Foreign key relationship is enforced at the application level
    # since SQLite does not support ALTER TABLE ADD CONSTRAINT.


def downgrade() -> None:
    op.drop_table("skill_usage")
    op.drop_table("skill_edges")
    op.drop_table("skill_nodes")