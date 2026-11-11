"""create_core_source_tables

Revision ID: be415c420bad
Revises: 
Create Date: 2026-11-11 17:05:06.968525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be415c420bad'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the four approved core source tables, constraints, and indexes."""
    # 1. Table: dim_product (11 columns)
    op.create_table(
        'dim_product',
        sa.Column('product_id', sa.String(50), nullable=False),
        sa.Column('product_name', sa.String(100), nullable=False),
        sa.Column('product_family', sa.String(50), nullable=False),
        sa.Column('ram', sa.String(20), nullable=False),
        sa.Column('storage', sa.String(20), nullable=False),
        sa.Column('display', sa.String(50), nullable=False),
        sa.Column('model_revision', sa.String(20), nullable=False),
        sa.Column('standard_cycle_sec', sa.Integer(), nullable=False),
        sa.Column('standard_unit_cost_inr', sa.Numeric(12, 2), nullable=False),
        sa.Column('active_from', sa.Date(), nullable=False),
        sa.Column('active_to', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('product_id', name='pk_dim_product'),
        sa.CheckConstraint('standard_cycle_sec > 0', name='chk_dim_product_cycle_sec'),
        sa.CheckConstraint('standard_unit_cost_inr >= 0', name='chk_dim_product_unit_cost'),
        sa.CheckConstraint('active_to >= active_from', name='chk_dim_product_dates'),
    )

    # 2. Table: dim_production_line (6 columns)
    op.create_table(
        'dim_production_line',
        sa.Column('line_id', sa.String(50), nullable=False),
        sa.Column('plant_id', sa.String(50), nullable=False),
        sa.Column('line_type', sa.String(50), nullable=False),
        sa.Column('nominal_capacity_per_hour', sa.Integer(), nullable=False),
        sa.Column('takt_time_sec', sa.Numeric(6, 2), nullable=False),
        sa.Column('area', sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint('line_id', name='pk_dim_production_line'),
        sa.UniqueConstraint('line_id', 'plant_id', name='uq_dim_production_line_line_plant'),
        sa.CheckConstraint('nominal_capacity_per_hour > 0', name='chk_dim_line_capacity'),
        sa.CheckConstraint('takt_time_sec > 0', name='chk_dim_line_takt_time'),
    )
    op.create_index('idx_dim_line_plant_id', 'dim_production_line', ['plant_id'])

    # 3. Table: fact_energy_meter_hourly (14 columns)
    op.create_table(
        'fact_energy_meter_hourly',
        sa.Column('meter_reading_id', sa.String(50), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=False), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('plant_id', sa.String(50), nullable=False),
        sa.Column('meter_id', sa.String(50), nullable=False),
        sa.Column('area', sa.String(50), nullable=False),
        sa.Column('energy_source', sa.String(50), nullable=False),
        sa.Column('consumption_kwh', sa.Numeric(12, 4), nullable=False),
        sa.Column('demand_kw', sa.Numeric(12, 4), nullable=False),
        sa.Column('power_factor', sa.Numeric(6, 4), nullable=False),
        sa.Column('tariff_inr_per_kwh', sa.Numeric(8, 4), nullable=False),
        sa.Column('cost_inr', sa.Numeric(12, 2), nullable=False),
        sa.Column('co2e_kg', sa.Numeric(12, 4), nullable=False),
        sa.Column('reading_quality', sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint('meter_reading_id', name='pk_fact_energy_meter_hourly'),
        sa.UniqueConstraint('timestamp', 'plant_id', 'meter_id', name='uq_energy_meter_hourly'),
        sa.CheckConstraint('consumption_kwh >= 0', name='chk_energy_consumption_positive'),
        sa.CheckConstraint('demand_kw >= 0', name='chk_energy_demand_positive'),
        sa.CheckConstraint('power_factor >= 0.0 AND power_factor <= 1.0', name='chk_energy_power_factor_range'),
        sa.CheckConstraint('tariff_inr_per_kwh >= 0', name='chk_energy_tariff_positive'),
        sa.CheckConstraint('cost_inr >= 0', name='chk_energy_cost_positive'),
        sa.CheckConstraint('co2e_kg >= 0', name='chk_energy_co2e_positive'),
    )
    op.create_index('idx_energy_timestamp', 'fact_energy_meter_hourly', ['timestamp'])
    op.create_index('idx_energy_plant_meter', 'fact_energy_meter_hourly', ['plant_id', 'meter_id'])
    op.create_index('idx_energy_meter_area', 'fact_energy_meter_hourly', ['area'])

    # 4. Table: fact_hourly_production (23 columns)
    op.create_table(
        'fact_hourly_production',
        sa.Column('event_id', sa.String(50), nullable=False),
        sa.Column('event_ts', sa.DateTime(timezone=False), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('year', sa.SmallInteger(), nullable=False),
        sa.Column('month', sa.SmallInteger(), nullable=False),
        sa.Column('week', sa.SmallInteger(), nullable=False),
        sa.Column('day', sa.SmallInteger(), nullable=False),
        sa.Column('hour', sa.SmallInteger(), nullable=False),
        sa.Column('plant_id', sa.String(50), nullable=False),
        sa.Column('line_id', sa.String(50), nullable=False),
        sa.Column('shift_id', sa.String(10), nullable=False),
        sa.Column('product_id', sa.String(50), nullable=False),
        sa.Column('production_order_id', sa.String(50), nullable=False),
        sa.Column('target_qty', sa.Integer(), nullable=False),
        sa.Column('actual_qty', sa.Integer(), nullable=False),
        sa.Column('good_qty', sa.Integer(), nullable=False),
        sa.Column('reject_qty', sa.Integer(), nullable=False),
        sa.Column('rework_qty', sa.Integer(), nullable=False),
        sa.Column('downtime_min', sa.Integer(), nullable=False),
        sa.Column('downtime_reason', sa.String(50), nullable=False),
        sa.Column('operator_team', sa.String(50), nullable=False),
        sa.Column('source_system', sa.String(20), nullable=False),
        sa.Column('data_quality', sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint('event_id', name='pk_fact_hourly_production'),
        sa.ForeignKeyConstraint(
            ['product_id'],
            ['dim_product.product_id'],
            name='fk_production_product_id',
        ),
        sa.ForeignKeyConstraint(
            ['line_id', 'plant_id'],
            ['dim_production_line.line_id', 'dim_production_line.plant_id'],
            name='fk_production_line_plant',
        ),
        sa.UniqueConstraint('event_ts', 'plant_id', 'line_id', name='uq_production_hourly'),
        sa.CheckConstraint('hour >= 0 AND hour <= 23', name='chk_prod_hour_range'),
        sa.CheckConstraint('target_qty >= 0', name='chk_prod_target_qty_positive'),
        sa.CheckConstraint('actual_qty >= 0', name='chk_prod_actual_qty_positive'),
        sa.CheckConstraint('good_qty >= 0', name='chk_prod_good_qty_positive'),
        sa.CheckConstraint('reject_qty >= 0', name='chk_prod_reject_qty_positive'),
        sa.CheckConstraint('rework_qty >= 0', name='chk_prod_rework_qty_positive'),
        sa.CheckConstraint('downtime_min >= 0 AND downtime_min <= 60', name='chk_prod_downtime_range'),
        sa.CheckConstraint('actual_qty = good_qty + reject_qty', name='chk_prod_qty_balance'),
    )
    op.create_index('idx_prod_event_ts', 'fact_hourly_production', ['event_ts'])
    op.create_index('idx_prod_line_id', 'fact_hourly_production', ['line_id'])
    op.create_index('idx_prod_product_id', 'fact_hourly_production', ['product_id'])
    op.create_index('idx_prod_shift_id', 'fact_hourly_production', ['shift_id'])
    op.create_index('idx_prod_plant_id', 'fact_hourly_production', ['plant_id'])


def downgrade() -> None:
    """Drop the four core tables in reverse dependency order."""
    op.drop_index('idx_prod_plant_id', table_name='fact_hourly_production')
    op.drop_index('idx_prod_shift_id', table_name='fact_hourly_production')
    op.drop_index('idx_prod_product_id', table_name='fact_hourly_production')
    op.drop_index('idx_prod_line_id', table_name='fact_hourly_production')
    op.drop_index('idx_prod_event_ts', table_name='fact_hourly_production')
    op.drop_table('fact_hourly_production')

    op.drop_index('idx_energy_meter_area', table_name='fact_energy_meter_hourly')
    op.drop_index('idx_energy_plant_meter', table_name='fact_energy_meter_hourly')
    op.drop_index('idx_energy_timestamp', table_name='fact_energy_meter_hourly')
    op.drop_table('fact_energy_meter_hourly')

    op.drop_index('idx_dim_line_plant_id', table_name='dim_production_line')
    op.drop_table('dim_production_line')

    op.drop_table('dim_product')
