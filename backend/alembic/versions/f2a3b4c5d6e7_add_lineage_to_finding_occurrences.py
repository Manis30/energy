"""add_lineage_to_finding_occurrences

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-14 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable lineage fields, foreign keys, and indexes to finding_occurrences table."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    occ_cols = {c['name'] for c in insp.get_columns('finding_occurrences')}

    if 'source_table' not in occ_cols:
        op.add_column('finding_occurrences', sa.Column('source_table', sa.String(length=50), nullable=True))
    if 'source_record_id' not in occ_cols:
        op.add_column('finding_occurrences', sa.Column('source_record_id', sa.String(length=50), nullable=True))
    if 'upload_id' not in occ_cols:
        op.add_column('finding_occurrences', sa.Column('upload_id', sa.String(length=50), nullable=True))
    if 'detector_version' not in occ_cols:
        op.add_column('finding_occurrences', sa.Column('detector_version', sa.String(length=50), nullable=True))

    occ_fks = {fk['name'] for fk in insp.get_foreign_keys('finding_occurrences')}
    if 'fk_finding_occ_upload_id' not in occ_fks:
        op.create_foreign_key(
            'fk_finding_occ_upload_id',
            'finding_occurrences',
            'upload_history',
            ['upload_id'],
            ['upload_id'],
            ondelete='SET NULL',
        )
    occ_indexes = {idx['name'] for idx in insp.get_indexes('finding_occurrences')}
    if 'idx_occ_source_record' not in occ_indexes:
        op.create_index('idx_occ_source_record', 'finding_occurrences', ['source_table', 'source_record_id'])
    if 'idx_occ_upload_id' not in occ_indexes:
        op.create_index('idx_occ_upload_id', 'finding_occurrences', ['upload_id'])


def downgrade() -> None:
    """Remove lineage fields, foreign keys, and indexes from finding_occurrences table."""
    op.drop_index('idx_occ_upload_id', table_name='finding_occurrences')
    op.drop_index('idx_occ_source_record', table_name='finding_occurrences')
    op.drop_constraint('fk_finding_occ_upload_id', 'finding_occurrences', type_='foreignkey')
    op.drop_column('finding_occurrences', 'detector_version')
    op.drop_column('finding_occurrences', 'upload_id')
    op.drop_column('finding_occurrences', 'source_record_id')
    op.drop_column('finding_occurrences', 'source_table')

