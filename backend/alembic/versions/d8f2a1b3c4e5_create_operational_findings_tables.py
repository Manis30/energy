"""create_operational_findings_tables

Revision ID: d8f2a1b3c4e5
Revises: c7a19e28f01b
Create Date: 2026-11-13 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f2a1b3c4e5'
down_revision: Union[str, Sequence[str], None] = 'c7a19e28f01b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create operational_findings, finding_occurrences, and finding_audit_log tables."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. operational_findings
    if not insp.has_table('operational_findings'):
        op.create_table(
            'operational_findings',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('finding_id', sa.String(length=60), nullable=False),
            sa.Column('finding_key', sa.String(length=160), nullable=False),
            sa.Column('anomaly_type', sa.String(length=60), nullable=False),
            sa.Column('plant_id', sa.String(length=50), nullable=False),
            sa.Column('meter_id', sa.String(length=50), nullable=True),
            sa.Column('line_id', sa.String(length=50), nullable=True),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='NEW'),
            sa.Column('severity', sa.String(length=20), nullable=False, server_default='MEDIUM'),
            sa.Column('first_detected_at', sa.DateTime(timezone=False), nullable=False),
            sa.Column('last_detected_at', sa.DateTime(timezone=False), nullable=False),
            sa.Column('occurrence_count', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('current_actual_value', sa.Numeric(precision=12, scale=4), nullable=True),
            sa.Column('current_baseline_value', sa.Numeric(precision=12, scale=4), nullable=True),
            sa.Column('current_deviation_score', sa.Float(), nullable=True),
            sa.Column('current_explanation', sa.Text(), nullable=True),
            sa.Column('acknowledged_at', sa.DateTime(timezone=False), nullable=True),
            sa.Column('investigated_at', sa.DateTime(timezone=False), nullable=True),
            sa.Column('investigation_notes', sa.Text(), nullable=True),
            sa.Column('resolved_at', sa.DateTime(timezone=False), nullable=True),
            sa.Column('resolution_notes', sa.Text(), nullable=True),
            sa.Column('reopened_at', sa.DateTime(timezone=False), nullable=True),
            sa.Column('reopen_reason', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
            sa.PrimaryKeyConstraint('id', name='pk_operational_findings'),
            sa.UniqueConstraint('finding_id', name='uq_operational_findings_finding_id'),
            sa.UniqueConstraint('finding_key', name='uq_operational_findings_finding_key'),
            sa.CheckConstraint(
                "status IN ('NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'RESOLVED', 'REOPENED')",
                name='chk_findings_status',
            ),
            sa.CheckConstraint(
                "severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL')",
                name='chk_findings_severity',
            ),
            sa.CheckConstraint('occurrence_count >= 1', name='chk_findings_occurrence_count'),
        )
        op.create_index('idx_findings_finding_id', 'operational_findings', ['finding_id'])
        op.create_index('idx_findings_finding_key', 'operational_findings', ['finding_key'])
        op.create_index('idx_findings_anomaly_type', 'operational_findings', ['anomaly_type'])
        op.create_index('idx_findings_plant_id', 'operational_findings', ['plant_id'])
        op.create_index('idx_findings_meter_id', 'operational_findings', ['meter_id'])
        op.create_index('idx_findings_line_id', 'operational_findings', ['line_id'])
        op.create_index('idx_findings_status', 'operational_findings', ['status'])
        op.create_index('idx_findings_severity', 'operational_findings', ['severity'])
        op.create_index('idx_findings_last_detected', 'operational_findings', ['last_detected_at'])
        op.create_index('idx_findings_plant_status', 'operational_findings', ['plant_id', 'status'])
        op.create_index('idx_findings_plant_meter', 'operational_findings', ['plant_id', 'meter_id'])

    # 2. finding_occurrences
    if not insp.has_table('finding_occurrences'):
        op.create_table(
            'finding_occurrences',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('occurrence_id', sa.String(length=60), nullable=False),
            sa.Column('finding_id', sa.String(length=60), nullable=False),
            sa.Column('occurrence_ts', sa.DateTime(timezone=False), nullable=False),
            sa.Column('actual_value', sa.Numeric(precision=12, scale=4), nullable=False),
            sa.Column('baseline_value', sa.Numeric(precision=12, scale=4), nullable=True),
            sa.Column('deviation_score', sa.Float(), nullable=False),
            sa.Column('severity', sa.String(length=20), nullable=False),
            sa.Column('explanation', sa.Text(), nullable=True),
            sa.Column('context_flags_json', sa.Text(), nullable=True),
            sa.Column('recorded_at', sa.DateTime(timezone=False), nullable=False),
            sa.PrimaryKeyConstraint('id', name='pk_finding_occurrences'),
            sa.UniqueConstraint('occurrence_id', name='uq_finding_occurrences_occurrence_id'),
            sa.UniqueConstraint('finding_id', 'occurrence_ts', name='uq_finding_occurrence_finding_ts'),
            sa.ForeignKeyConstraint(
                ['finding_id'],
                ['operational_findings.finding_id'],
                name='fk_finding_occurrences_finding_id',
                ondelete='CASCADE',
            ),
        )
        op.create_index('idx_occ_occurrence_id', 'finding_occurrences', ['occurrence_id'])
        op.create_index('idx_occ_finding_id', 'finding_occurrences', ['finding_id'])
        op.create_index('idx_occ_occurrence_ts', 'finding_occurrences', ['occurrence_ts'])
        op.create_index('idx_occ_finding_ts', 'finding_occurrences', ['finding_id', 'occurrence_ts'])

    # 3. finding_audit_log
    if not insp.has_table('finding_audit_log'):
        op.create_table(
            'finding_audit_log',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('finding_id', sa.String(length=60), nullable=False),
            sa.Column('action', sa.String(length=50), nullable=False),
            sa.Column('from_status', sa.String(length=30), nullable=True),
            sa.Column('to_status', sa.String(length=30), nullable=True),
            sa.Column('performed_at', sa.DateTime(timezone=False), nullable=False),
            sa.Column('comment', sa.Text(), nullable=True),
            sa.Column('audit_metadata_json', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id', name='pk_finding_audit_log'),
            sa.ForeignKeyConstraint(
                ['finding_id'],
                ['operational_findings.finding_id'],
                name='fk_finding_audit_log_finding_id',
                ondelete='CASCADE',
            ),
        )
        op.create_index('idx_audit_finding_id', 'finding_audit_log', ['finding_id'])
        op.create_index('idx_audit_performed_at', 'finding_audit_log', ['performed_at'])
        op.create_index('idx_audit_finding_performed', 'finding_audit_log', ['finding_id', 'performed_at'])


def downgrade() -> None:
    """Drop finding_audit_log, finding_occurrences, and operational_findings tables."""
    # 1. Drop finding_audit_log
    op.drop_index('idx_audit_finding_performed', table_name='finding_audit_log')
    op.drop_index('idx_audit_performed_at', table_name='finding_audit_log')
    op.drop_index('idx_audit_finding_id', table_name='finding_audit_log')
    op.drop_table('finding_audit_log')

    # 2. Drop finding_occurrences
    op.drop_index('idx_occ_finding_ts', table_name='finding_occurrences')
    op.drop_index('idx_occ_occurrence_ts', table_name='finding_occurrences')
    op.drop_index('idx_occ_finding_id', table_name='finding_occurrences')
    op.drop_index('idx_occ_occurrence_id', table_name='finding_occurrences')
    op.drop_table('finding_occurrences')

    # 3. Drop operational_findings
    op.drop_index('idx_findings_plant_meter', table_name='operational_findings')
    op.drop_index('idx_findings_plant_status', table_name='operational_findings')
    op.drop_index('idx_findings_last_detected', table_name='operational_findings')
    op.drop_index('idx_findings_severity', table_name='operational_findings')
    op.drop_index('idx_findings_status', table_name='operational_findings')
    op.drop_index('idx_findings_line_id', table_name='operational_findings')
    op.drop_index('idx_findings_meter_id', table_name='operational_findings')
    op.drop_index('idx_findings_plant_id', table_name='operational_findings')
    op.drop_index('idx_findings_anomaly_type', table_name='operational_findings')
    op.drop_index('idx_findings_finding_key', table_name='operational_findings')
    op.drop_index('idx_findings_finding_id', table_name='operational_findings')
    op.drop_table('operational_findings')

