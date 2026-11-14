"""create_recommendation_and_action_audit_tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-14 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create recommendation_audit_log and action_audit_log tables with foreign keys and indexes."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. recommendation_audit_log
    if not insp.has_table('recommendation_audit_log'):
        op.create_table(
            'recommendation_audit_log',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('audit_id', sa.String(length=60), nullable=False),
            sa.Column('recommendation_id', sa.String(length=60), nullable=True),
            sa.Column('entity_id', sa.String(length=60), nullable=False),
            sa.Column('action', sa.String(length=50), nullable=False),
            sa.Column('from_status', sa.String(length=30), nullable=True),
            sa.Column('to_status', sa.String(length=30), nullable=True),
            sa.Column('performed_at', sa.DateTime(timezone=False), nullable=False),
            sa.Column('comment', sa.Text(), nullable=True),
            sa.Column('changed_fields_json', sa.Text(), nullable=True),
            sa.Column('audit_metadata_json', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id', name='pk_recommendation_audit_log'),
            sa.UniqueConstraint('audit_id', name='uq_rec_audit_id'),
            sa.ForeignKeyConstraint(
                ['recommendation_id'],
                ['operational_recommendations.recommendation_id'],
                name='fk_rec_audit_rec_id',
                ondelete='SET NULL',
            ),
        )
        op.create_index('idx_rec_audit_id', 'recommendation_audit_log', ['audit_id'])
        op.create_index('idx_rec_audit_rec_id', 'recommendation_audit_log', ['recommendation_id'])
        op.create_index('idx_rec_audit_entity_id', 'recommendation_audit_log', ['entity_id'])
        op.create_index('idx_rec_audit_performed_at', 'recommendation_audit_log', ['performed_at'])
        op.create_index('idx_rec_audit_rec_perf', 'recommendation_audit_log', ['recommendation_id', 'performed_at'])
        op.create_index('idx_rec_audit_entity_perf', 'recommendation_audit_log', ['entity_id', 'performed_at'])

    # 2. action_audit_log
    if not insp.has_table('action_audit_log'):
        op.create_table(
            'action_audit_log',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('audit_id', sa.String(length=60), nullable=False),
            sa.Column('action_id', sa.String(length=60), nullable=True),
            sa.Column('recommendation_id', sa.String(length=60), nullable=True),
            sa.Column('entity_id', sa.String(length=60), nullable=False),
            sa.Column('action', sa.String(length=50), nullable=False),
            sa.Column('from_status', sa.String(length=30), nullable=True),
            sa.Column('to_status', sa.String(length=30), nullable=True),
            sa.Column('performed_at', sa.DateTime(timezone=False), nullable=False),
            sa.Column('comment', sa.Text(), nullable=True),
            sa.Column('changed_fields_json', sa.Text(), nullable=True),
            sa.Column('audit_metadata_json', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id', name='pk_action_audit_log'),
            sa.UniqueConstraint('audit_id', name='uq_act_audit_id'),
            sa.ForeignKeyConstraint(
                ['action_id'],
                ['corrective_actions.action_id'],
                name='fk_act_audit_act_id',
                ondelete='SET NULL',
            ),
            sa.ForeignKeyConstraint(
                ['recommendation_id'],
                ['operational_recommendations.recommendation_id'],
                name='fk_act_audit_rec_id',
                ondelete='SET NULL',
            ),
        )
        op.create_index('idx_act_audit_id', 'action_audit_log', ['audit_id'])
        op.create_index('idx_act_audit_act_id', 'action_audit_log', ['action_id'])
        op.create_index('idx_act_audit_rec_id', 'action_audit_log', ['recommendation_id'])
        op.create_index('idx_act_audit_entity_id', 'action_audit_log', ['entity_id'])
        op.create_index('idx_act_audit_performed_at', 'action_audit_log', ['performed_at'])
        op.create_index('idx_act_audit_act_perf', 'action_audit_log', ['action_id', 'performed_at'])
        op.create_index('idx_act_audit_rec_perf', 'action_audit_log', ['recommendation_id', 'performed_at'])
        op.create_index('idx_act_audit_entity_perf', 'action_audit_log', ['entity_id', 'performed_at'])


def downgrade() -> None:
    """Drop action_audit_log and recommendation_audit_log tables."""
    op.drop_index('idx_act_audit_entity_perf', table_name='action_audit_log')
    op.drop_index('idx_act_audit_rec_perf', table_name='action_audit_log')
    op.drop_index('idx_act_audit_act_perf', table_name='action_audit_log')
    op.drop_index('idx_act_audit_performed_at', table_name='action_audit_log')
    op.drop_index('idx_act_audit_entity_id', table_name='action_audit_log')
    op.drop_index('idx_act_audit_rec_id', table_name='action_audit_log')
    op.drop_index('idx_act_audit_act_id', table_name='action_audit_log')
    op.drop_index('idx_act_audit_id', table_name='action_audit_log')
    op.drop_table('action_audit_log')

    op.drop_index('idx_rec_audit_entity_perf', table_name='recommendation_audit_log')
    op.drop_index('idx_rec_audit_rec_perf', table_name='recommendation_audit_log')
    op.drop_index('idx_rec_audit_performed_at', table_name='recommendation_audit_log')
    op.drop_index('idx_rec_audit_entity_id', table_name='recommendation_audit_log')
    op.drop_index('idx_rec_audit_rec_id', table_name='recommendation_audit_log')
    op.drop_index('idx_rec_audit_id', table_name='recommendation_audit_log')
    op.drop_table('recommendation_audit_log')

