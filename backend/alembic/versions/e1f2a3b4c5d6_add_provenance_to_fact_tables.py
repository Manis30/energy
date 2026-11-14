"""add_provenance_to_fact_tables

Revision ID: e1f2a3b4c5d6
Revises: d8f2a1b3c4e5
Create Date: 2026-11-13 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd8f2a1b3c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable upload_id and ingested_at provenance columns to fact tables with foreign keys and indexes."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. fact_energy_meter_hourly
    energy_cols = {c['name'] for c in insp.get_columns('fact_energy_meter_hourly')}
    if 'upload_id' not in energy_cols:
        op.add_column('fact_energy_meter_hourly', sa.Column('upload_id', sa.String(length=50), nullable=True))
    if 'ingested_at' not in energy_cols:
        op.add_column('fact_energy_meter_hourly', sa.Column('ingested_at', sa.DateTime(timezone=False), nullable=True))
    
    energy_fks = {fk['name'] for fk in insp.get_foreign_keys('fact_energy_meter_hourly')}
    if 'fk_fact_energy_upload_id' not in energy_fks:
        op.create_foreign_key(
            'fk_fact_energy_upload_id',
            'fact_energy_meter_hourly',
            'upload_history',
            ['upload_id'],
            ['upload_id'],
            ondelete='SET NULL',
        )
    energy_indexes = {idx['name'] for idx in insp.get_indexes('fact_energy_meter_hourly')}
    if 'idx_energy_upload_id' not in energy_indexes:
        op.create_index('idx_energy_upload_id', 'fact_energy_meter_hourly', ['upload_id'])
    if 'idx_energy_upload_date' not in energy_indexes:
        op.create_index('idx_energy_upload_date', 'fact_energy_meter_hourly', ['upload_id', 'date'])

    # 2. fact_hourly_production
    prod_cols = {c['name'] for c in insp.get_columns('fact_hourly_production')}
    if 'upload_id' not in prod_cols:
        op.add_column('fact_hourly_production', sa.Column('upload_id', sa.String(length=50), nullable=True))
    if 'ingested_at' not in prod_cols:
        op.add_column('fact_hourly_production', sa.Column('ingested_at', sa.DateTime(timezone=False), nullable=True))
    
    prod_fks = {fk['name'] for fk in insp.get_foreign_keys('fact_hourly_production')}
    if 'fk_fact_production_upload_id' not in prod_fks:
        op.create_foreign_key(
            'fk_fact_production_upload_id',
            'fact_hourly_production',
            'upload_history',
            ['upload_id'],
            ['upload_id'],
            ondelete='SET NULL',
        )
    prod_indexes = {idx['name'] for idx in insp.get_indexes('fact_hourly_production')}
    if 'idx_prod_upload_id' not in prod_indexes:
        op.create_index('idx_prod_upload_id', 'fact_hourly_production', ['upload_id'])
    if 'idx_prod_upload_date' not in prod_indexes:
        op.create_index('idx_prod_upload_date', 'fact_hourly_production', ['upload_id', 'event_date'])


def downgrade() -> None:
    """Remove provenance columns, foreign keys, and indexes from fact tables."""
    # 1. fact_hourly_production
    op.drop_index('idx_prod_upload_date', table_name='fact_hourly_production')
    op.drop_index('idx_prod_upload_id', table_name='fact_hourly_production')
    op.drop_constraint('fk_fact_production_upload_id', 'fact_hourly_production', type_='foreignkey')
    op.drop_column('fact_hourly_production', 'ingested_at')
    op.drop_column('fact_hourly_production', 'upload_id')

    # 2. fact_energy_meter_hourly
    op.drop_index('idx_energy_upload_date', table_name='fact_energy_meter_hourly')
    op.drop_index('idx_energy_upload_id', table_name='fact_energy_meter_hourly')
    op.drop_constraint('fk_fact_energy_upload_id', 'fact_energy_meter_hourly', type_='foreignkey')
    op.drop_column('fact_energy_meter_hourly', 'ingested_at')
    op.drop_column('fact_energy_meter_hourly', 'upload_id')

