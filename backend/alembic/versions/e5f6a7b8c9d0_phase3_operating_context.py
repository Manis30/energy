"""Phase 3: Operating Context migration.

Adds dim_machine, dim_shift_calendar, and fact_machine_telemetry_hourly tables
to support machine-state, shift-calendar, and stoppage episode operating context.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-18 23:05:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. dim_machine
    if not insp.has_table('dim_machine'):
        op.create_table(
            'dim_machine',
            sa.Column('machine_id', sa.String(50), primary_key=True),
            sa.Column('machine_name', sa.String(100), nullable=False),
            sa.Column('machine_type', sa.String(50), nullable=False),
            sa.Column('line_id', sa.String(50), nullable=False),
            sa.Column('plant_id', sa.String(50), nullable=False),
            sa.Column('criticality', sa.String(10), nullable=False),
            sa.Column('commissioned_date', sa.Date(), nullable=False),
            sa.Column('planned_maintenance_interval_days', sa.Integer(), nullable=False),
        )
        op.create_index('idx_dim_machine_plant_line', 'dim_machine', ['plant_id', 'line_id'])

    # 2. dim_shift_calendar
    if not insp.has_table('dim_shift_calendar'):
        op.create_table(
            'dim_shift_calendar',
            sa.Column('calendar_date', sa.Date(), primary_key=True),
            sa.Column('shift_id', sa.String(20), primary_key=True),
            sa.Column('shift_start', sa.DateTime(), nullable=False),
            sa.Column('shift_end', sa.DateTime(), nullable=False),
            sa.Column('planned_minutes', sa.Integer(), nullable=False),
            sa.Column('break_minutes', sa.Integer(), nullable=False),
            sa.Column('is_working_day', sa.Boolean(), nullable=False),
        )
        op.create_index('idx_dim_shift_cal_date', 'dim_shift_calendar', ['calendar_date'])

    # 3. fact_machine_telemetry_hourly
    if not insp.has_table('fact_machine_telemetry_hourly'):
        op.create_table(
            'fact_machine_telemetry_hourly',
            sa.Column('telemetry_id', sa.String(50), primary_key=True),
            sa.Column('timestamp', sa.DateTime(), nullable=False),
            sa.Column('date', sa.Date(), nullable=False),
            sa.Column('machine_id', sa.String(50), sa.ForeignKey('dim_machine.machine_id'), nullable=False),
            sa.Column('plant_id', sa.String(50), nullable=False),
            sa.Column('line_id', sa.String(50), nullable=False),
            sa.Column('shift_id', sa.String(20), nullable=False),
            sa.Column('temperature_c', sa.Numeric(6, 2), nullable=True),
            sa.Column('vibration_mm_s', sa.Numeric(7, 3), nullable=True),
            sa.Column('motor_current_a', sa.Numeric(6, 2), nullable=True),
            sa.Column('pressure_bar', sa.Numeric(6, 2), nullable=True),
            sa.Column('rpm', sa.Numeric(8, 1), nullable=True),
            sa.Column('machine_state', sa.String(50), nullable=False),
            sa.Column('alarm_code', sa.String(50), nullable=False),
            sa.Column('sensor_health', sa.String(50), nullable=False),
            sa.Column('is_anomaly', sa.Boolean(), nullable=False),
        )
        op.create_index(
            'idx_fact_mach_telem_plant_line_ts',
            'fact_machine_telemetry_hourly',
            ['plant_id', 'line_id', 'timestamp'],
        )
        op.create_index(
            'idx_fact_mach_telem_mach_ts',
            'fact_machine_telemetry_hourly',
            ['machine_id', 'timestamp'],
        )
        op.create_index(
            'idx_fact_mach_telem_date',
            'fact_machine_telemetry_hourly',
            ['date'],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table('fact_machine_telemetry_hourly'):
        op.drop_table('fact_machine_telemetry_hourly')
    if insp.has_table('dim_shift_calendar'):
        op.drop_table('dim_shift_calendar')
    if insp.has_table('dim_machine'):
        op.drop_table('dim_machine')
