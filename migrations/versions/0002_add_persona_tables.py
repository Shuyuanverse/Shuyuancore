"""add persona specific tables (evolution_proposals, drift_history)

Revision ID: 0002
Create Date: 2026-05-26

"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'evolution_proposals',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('persona_id', sa.String(100), nullable=False),
        sa.Column('proposal_id', sa.String(100), nullable=False, unique=True),
        sa.Column('dimension', sa.String(100), nullable=False),
        sa.Column('current_value', sa.Float, nullable=False),
        sa.Column('proposed_value', sa.Float, nullable=False),
        sa.Column('delta', sa.Float, nullable=False),
        sa.Column('trigger_type', sa.String(50), nullable=False),
        sa.Column('reason', sa.Text),
        sa.Column('consistency_score', sa.Float, nullable=False, server_default='0.0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('idx_ep_persona', 'evolution_proposals', ['persona_id'])
    op.create_index('idx_ep_status', 'evolution_proposals', ['persona_id', 'status'])

    op.create_table(
        'drift_history',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('persona_id', sa.String(100), nullable=False),
        sa.Column('drift_score', sa.Float, nullable=False),
        sa.Column('alert_level', sa.String(20), nullable=False),
        sa.Column('dimensions', sa.Text),
        sa.Column('calibration_applied', sa.Boolean, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('idx_dh_persona', 'drift_history', ['persona_id'])
    op.create_index('idx_dh_created', 'drift_history', ['persona_id', 'created_at'])


def downgrade():
    op.drop_table('drift_history')
    op.drop_table('evolution_proposals')