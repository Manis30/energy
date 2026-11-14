"""create_recommendations_and_corrective_actions

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-11-14 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create operational_recommendations and corrective_actions tables."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. operational_recommendations
    if not insp.has_table('operational_recommendations'):
        op.create_table(
            'operational_recommendations',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('recommendation_id', sa.String(length=60), nullable=False),
            sa.Column('finding_id', sa.String(length=60), nullable=True),
            sa.Column('occurrence_id', sa.String(length=60), nullable=True),
            sa.Column('plant_id', sa.String(length=50), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('category', sa.String(length=50), nullable=False),
            sa.Column('priority', sa.String(length=20), nullable=False, server_default='MEDIUM'),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='OPEN'),
            sa.Column('evidence_context_json', sa.Text(), nullable=True),
            sa.Column('implemented_at', sa.DateTime(timezone=False), nullable=True),
            sa.Column('dismissed_at', sa.DateTime(timezone=False), nullable=True),
            sa.Column('dismissed_reason', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
            sa.PrimaryKeyConstraint('id', name='pk_operational_recommendations'),
            sa.UniqueConstraint('recommendation_id', name='uq_op_recommendations_rec_id'),
            sa.ForeignKeyConstraint(
                ['finding_id'],
                ['operational_findings.finding_id'],
                name='fk_op_rec_finding_id',
                ondelete='SET NULL',
            ),
            sa.ForeignKeyConstraint(
                ['occurrence_id'],
                ['finding_occurrences.occurrence_id'],
                name='fk_op_rec_occurrence_id',
                ondelete='SET NULL',
            ),
            sa.CheckConstraint(
                "status IN ('OPEN', 'IN_PROGRESS', 'IMPLEMENTED', 'DISMISSED')",
                name='chk_recommendation_status',
            ),
            sa.CheckConstraint(
                "priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL')",
                name='chk_recommendation_priority',
            ),
        )
        op.create_index('idx_rec_recommendation_id', 'operational_recommendations', ['recommendation_id'])
        op.create_index('idx_rec_finding_id', 'operational_recommendations', ['finding_id'])
        op.create_index('idx_rec_occurrence_id', 'operational_recommendations', ['occurrence_id'])
        op.create_index('idx_rec_plant_id', 'operational_recommendations', ['plant_id'])
        op.create_index('idx_rec_status', 'operational_recommendations', ['status'])
        op.create_index('idx_rec_priority', 'operational_recommendations', ['priority'])
        op.create_index('idx_rec_category', 'operational_recommendations', ['category'])
        op.create_index('idx_rec_plant_status', 'operational_recommendations', ['plant_id', 'status'])
        op.create_index('idx_rec_created_at', 'operational_recommendations', ['created_at'])

    # 2. corrective_actions
    if not insp.has_table('corrective_actions'):
        op.create_table(
            'corrective_actions',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('action_id', sa.String(length=60), nullable=False),
            sa.Column('recommendation_id', sa.String(length=60), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='OPEN'),
            sa.Column('owner', sa.String(length=100), nullable=True),
            sa.Column('due_date', sa.DateTime(timezone=False), nullable=True),
            sa.Column('completed_at', sa.DateTime(timezone=False), nullable=True),
            sa.Column('resolution_notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
            sa.PrimaryKeyConstraint('id', name='pk_corrective_actions'),
            sa.UniqueConstraint('action_id', name='uq_corrective_actions_action_id'),
            sa.ForeignKeyConstraint(
                ['recommendation_id'],
                ['operational_recommendations.recommendation_id'],
                name='fk_action_recommendation_id',
                ondelete='CASCADE',
            ),
            sa.CheckConstraint(
                "status IN ('OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
                name='chk_action_status',
            ),
        )
        op.create_index('idx_action_action_id', 'corrective_actions', ['action_id'])
        op.create_index('idx_action_recommendation_id', 'corrective_actions', ['recommendation_id'])
        op.create_index('idx_action_status', 'corrective_actions', ['status'])
        op.create_index('idx_action_owner', 'corrective_actions', ['owner'])
        op.create_index('idx_action_due_date', 'corrective_actions', ['due_date'])
        op.create_index('idx_action_created_at', 'corrective_actions', ['created_at'])


def downgrade() -> None:
    """Drop corrective_actions and operational_recommendations tables."""
    op.drop_index('idx_action_created_at', table_name='corrective_actions')
    op.drop_index('idx_action_due_date', table_name='corrective_actions')
    op.drop_index('idx_action_owner', table_name='corrective_actions')
    op.drop_index('idx_action_status', table_name='corrective_actions')
    op.drop_index('idx_action_recommendation_id', table_name='corrective_actions')
    op.drop_index('idx_action_action_id', table_name='corrective_actions')
    op.drop_table('corrective_actions')

    op.drop_index('idx_rec_created_at', table_name='operational_recommendations')
    op.drop_index('idx_rec_plant_status', table_name='operational_recommendations')
    op.drop_index('idx_rec_category', table_name='operational_recommendations')
    op.drop_index('idx_rec_priority', table_name='operational_recommendations')
    op.drop_index('idx_rec_status', table_name='operational_recommendations')
    op.drop_index('idx_rec_plant_id', table_name='operational_recommendations')
    op.drop_index('idx_rec_occurrence_id', table_name='operational_recommendations')
    op.drop_index('idx_rec_finding_id', table_name='operational_recommendations')
    op.drop_index('idx_rec_recommendation_id', table_name='operational_recommendations')
    op.drop_table('operational_recommendations')

