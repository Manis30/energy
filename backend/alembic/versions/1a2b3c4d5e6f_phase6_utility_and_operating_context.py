"""Phase 6: Utility and Operating Context migration.

Adds fact_utility_telemetry_hourly, fact_downtime_event, and fact_maintenance_work_order tables
to support utility telemetry (compressed air, chilled water, HVAC, nitrogen, process water),
machine stoppage events, and maintenance work orders.

Revision ID: 1a2b3c4d5e6f
Revises: f6a7b8c9d0e1
Create Date: 2026-11-19 10:30:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. fact_utility_telemetry_hourly
    if not insp.has_table('fact_utility_telemetry_hourly'):
        op.create_table(
            'fact_utility_telemetry_hourly',
            sa.Column('utility_reading_id', sa.String(50), primary_key=True),
            sa.Column('timestamp', sa.DateTime(), nullable=False),
            sa.Column('plant_id', sa.String(50), nullable=False),
            sa.Column('utility_type', sa.String(50), nullable=False),
            sa.Column('zone', sa.String(50), nullable=False),
            sa.Column('flow_rate', sa.Numeric(10, 2), nullable=True),
            sa.Column('pressure_bar', sa.Numeric(6, 2), nullable=True),
            sa.Column('temperature_c', sa.Numeric(6, 2), nullable=True),
            sa.Column('consumption_unit', sa.String(20), nullable=False),
            sa.Column('equipment_id', sa.String(50), nullable=False),
            sa.Column('operating_status', sa.String(50), nullable=False),
            sa.Column('alarm_code', sa.String(50), nullable=False),
            sa.Column('upload_id', sa.String(50), nullable=True),
            sa.Column('source_revision_id', sa.String(50), nullable=True),
            sa.Column('is_corrected', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            'idx_fact_util_telem_plant_util_ts',
            'fact_utility_telemetry_hourly',
            ['plant_id', 'utility_type', 'timestamp'],
        )
        op.create_index(
            'idx_fact_util_telem_equip_ts',
            'fact_utility_telemetry_hourly',
            ['equipment_id', 'timestamp'],
        )
        op.create_index(
            'idx_fact_util_telem_type_unit',
            'fact_utility_telemetry_hourly',
            ['utility_type', 'consumption_unit'],
        )

    # 2. fact_downtime_event
    if not insp.has_table('fact_downtime_event'):
        op.create_table(
            'fact_downtime_event',
            sa.Column('downtime_id', sa.String(50), primary_key=True),
            sa.Column('machine_id', sa.String(50), nullable=False),
            sa.Column('plant_id', sa.String(50), nullable=False),
            sa.Column('line_id', sa.String(50), nullable=False),
            sa.Column('start_ts', sa.DateTime(), nullable=False),
            sa.Column('duration_min', sa.Integer(), nullable=False),
            sa.Column('reason_code', sa.String(100), nullable=False),
            sa.Column('impact_units', sa.Integer(), nullable=True),
            sa.Column('maintenance_required', sa.Boolean(), nullable=False),
            sa.Column('acknowledged_by', sa.String(50), nullable=True),
            sa.Column('closure_status', sa.String(50), nullable=False),
            sa.Column('upload_id', sa.String(50), nullable=True),
        )
        op.create_index(
            'idx_fact_dt_plant_line_ts',
            'fact_downtime_event',
            ['plant_id', 'line_id', 'start_ts'],
        )
        op.create_index(
            'idx_fact_dt_mach_ts',
            'fact_downtime_event',
            ['machine_id', 'start_ts'],
        )

    # 3. fact_maintenance_work_order
    if not insp.has_table('fact_maintenance_work_order'):
        op.create_table(
            'fact_maintenance_work_order',
            sa.Column('work_order_id', sa.String(50), primary_key=True),
            sa.Column('machine_id', sa.String(50), nullable=False),
            sa.Column('plant_id', sa.String(50), nullable=False),
            sa.Column('created_ts', sa.DateTime(), nullable=False),
            sa.Column('maintenance_type', sa.String(50), nullable=False),
            sa.Column('failure_mode', sa.String(100), nullable=True),
            sa.Column('priority', sa.String(20), nullable=False),
            sa.Column('planned_start', sa.DateTime(), nullable=True),
            sa.Column('actual_start', sa.DateTime(), nullable=True),
            sa.Column('downtime_avoided_estimate_min', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(50), nullable=False),
            sa.Column('technician_id', sa.String(50), nullable=True),
            sa.Column('upload_id', sa.String(50), nullable=True),
        )
        op.create_index(
            'idx_fact_mwo_plant_mach_ts',
            'fact_maintenance_work_order',
            ['plant_id', 'machine_id', 'created_ts'],
        )
        op.create_index(
            'idx_fact_mwo_status',
            'fact_maintenance_work_order',
            ['status'],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table('fact_maintenance_work_order'):
        op.drop_table('fact_maintenance_work_order')
    if insp.has_table('fact_downtime_event'):
        op.drop_table('fact_downtime_event')
    if insp.has_table('fact_utility_telemetry_hourly'):
        op.drop_table('fact_utility_telemetry_hourly')
