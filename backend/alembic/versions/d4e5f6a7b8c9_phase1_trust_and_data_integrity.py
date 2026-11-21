"""Phase 1: Trust & Data Integrity migration.

Adds immutable fact source revisions, versioned dataset factor assumptions,
durable PostgreSQL downstream pipeline runs, and multi-source occurrence lineage tracking.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-18 20:50:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. fact_source_revisions
    if not insp.has_table('fact_source_revisions'):
        op.create_table(
            'fact_source_revisions',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('revision_id', sa.String(length=60), nullable=False),
            sa.Column('source_table', sa.String(length=50), nullable=False),
            sa.Column('source_record_id', sa.String(length=50), nullable=False),
            sa.Column('business_key', sa.String(length=160), nullable=False),
            sa.Column('plant_id', sa.String(length=50), nullable=False),
            sa.Column('upload_id', sa.String(length=50), nullable=True),
            sa.Column('revision_timestamp', sa.DateTime(timezone=False), nullable=False),
            sa.Column('source_values_json', sa.Text(), nullable=False),
            sa.Column('factor_version_id', sa.String(length=60), nullable=True),
            sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.PrimaryKeyConstraint('id', name='pk_fact_source_revisions'),
            sa.UniqueConstraint('revision_id', name='uq_fact_source_revisions_rev_id'),
            sa.ForeignKeyConstraint(
                ['upload_id'],
                ['upload_history.upload_id'],
                name='fk_fact_source_rev_upload_id',
                ondelete='SET NULL',
            ),
        )
        op.create_index('idx_fsr_revision_id', 'fact_source_revisions', ['revision_id'])
        op.create_index('idx_fsr_source_rec', 'fact_source_revisions', ['source_table', 'source_record_id'])
        op.create_index('idx_fsr_business_key', 'fact_source_revisions', ['source_table', 'business_key'])
        op.create_index('idx_fsr_plant_id', 'fact_source_revisions', ['plant_id'])
        op.create_index('idx_fsr_upload_id', 'fact_source_revisions', ['upload_id'])
        op.create_index('idx_fsr_is_current', 'fact_source_revisions', ['is_current'])

    # 2. dataset_factor_assumptions
    if not insp.has_table('dataset_factor_assumptions'):
        op.create_table(
            'dataset_factor_assumptions',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('factor_id', sa.String(length=60), nullable=False),
            sa.Column('factor_type', sa.String(length=40), nullable=False),
            sa.Column('factor_scope', sa.String(length=50), nullable=False, server_default='DEFAULT'),
            sa.Column('numeric_value', sa.Numeric(precision=12, scale=6), nullable=False),
            sa.Column('unit', sa.String(length=30), nullable=False),
            sa.Column('source_dataset_version', sa.String(length=100), nullable=False),
            sa.Column('approval_status', sa.String(length=40), nullable=False, server_default='UNKNOWN'),
            sa.Column('effective_from', sa.Date(), nullable=True),
            sa.Column('effective_to', sa.Date(), nullable=True),
            sa.Column('is_hypothetical', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id', name='pk_dataset_factor_assumptions'),
            sa.UniqueConstraint('factor_id', name='uq_dataset_factors_factor_id'),
        )
        op.create_index('idx_dfa_factor_id', 'dataset_factor_assumptions', ['factor_id'])
        op.create_index('idx_dfa_factor_type', 'dataset_factor_assumptions', ['factor_type'])

        # Seed default dataset assumptions
        factors_table = sa.table(
            'dataset_factor_assumptions',
            sa.column('factor_id', sa.String),
            sa.column('factor_type', sa.String),
            sa.column('factor_scope', sa.String),
            sa.column('numeric_value', sa.Numeric),
            sa.column('unit', sa.String),
            sa.column('source_dataset_version', sa.String),
            sa.column('approval_status', sa.String),
            sa.column('is_hypothetical', sa.Boolean),
            sa.column('notes', sa.Text),
        )
        op.bulk_insert(
            factors_table,
            [
                {
                    'factor_id': 'FAC-TARIFF-DATASET-8.25',
                    'factor_type': 'ELECTRICITY_TARIFF',
                    'factor_scope': 'DEFAULT',
                    'numeric_value': 8.250000,
                    'unit': 'INR/kWh',
                    'source_dataset_version': 'synthetic_daily_reports_nov_2026',
                    'approval_status': 'UNKNOWN',
                    'is_hypothetical': False,
                    'notes': 'Supplied dataset constant ₹8.25/kWh assumption with unverified contractual status.',
                },
                {
                    'factor_id': 'FAC-EMISSIONS-DATASET-0.716',
                    'factor_type': 'GRID_EMISSIONS_FACTOR',
                    'factor_scope': 'DEFAULT',
                    'numeric_value': 0.716000,
                    'unit': 'kg CO2e/kWh',
                    'source_dataset_version': 'synthetic_daily_reports_nov_2026',
                    'approval_status': 'UNKNOWN',
                    'is_hypothetical': False,
                    'notes': 'Supplied dataset implied ~0.716 kg CO2e/kWh emission factor with unverified grid baseline.',
                },
            ],
        )

    # 3. daily_pipeline_runs
    if not insp.has_table('daily_pipeline_runs'):
        op.create_table(
            'daily_pipeline_runs',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('run_id', sa.String(length=60), nullable=False),
            sa.Column('reporting_date', sa.Date(), nullable=False),
            sa.Column('plant_id', sa.String(length=50), nullable=False),
            sa.Column('input_batch_id', sa.String(length=120), nullable=True),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='PENDING'),
            sa.Column('current_stage', sa.String(length=50), nullable=False, server_default='data_upload'),
            sa.Column('stage_states_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('items_prepared_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('findings_synchronized_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('new_findings_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('reused_findings_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('started_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('completed_at', sa.DateTime(timezone=False), nullable=True),
            sa.PrimaryKeyConstraint('id', name='pk_daily_pipeline_runs'),
            sa.UniqueConstraint('run_id', name='uq_daily_pipeline_runs_run_id'),
        )
        op.create_index('idx_dpr_run_id', 'daily_pipeline_runs', ['run_id'])
        op.create_index('idx_dpr_date_plant', 'daily_pipeline_runs', ['reporting_date', 'plant_id'])
        op.create_index('idx_dpr_status', 'daily_pipeline_runs', ['status'])
        op.create_index('idx_dpr_is_current', 'daily_pipeline_runs', ['is_current'])

    # 4. finding_occurrence_sources
    if not insp.has_table('finding_occurrence_sources'):
        op.create_table(
            'finding_occurrence_sources',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('occurrence_id', sa.String(length=60), nullable=False),
            sa.Column('revision_id', sa.String(length=60), nullable=True),
            sa.Column('source_table', sa.String(length=50), nullable=False),
            sa.Column('source_record_id', sa.String(length=50), nullable=False),
            sa.Column('role', sa.String(length=50), nullable=False),
            sa.Column('upload_id', sa.String(length=50), nullable=True),
            sa.PrimaryKeyConstraint('id', name='pk_finding_occurrence_sources'),
            sa.ForeignKeyConstraint(
                ['occurrence_id'],
                ['finding_occurrences.occurrence_id'],
                name='fk_occ_src_occ_id',
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['revision_id'],
                ['fact_source_revisions.revision_id'],
                name='fk_occ_src_rev_id',
                ondelete='SET NULL',
            ),
        )
        op.create_index('idx_fos_occurrence_id', 'finding_occurrence_sources', ['occurrence_id'])
        op.create_index('idx_fos_revision_id', 'finding_occurrence_sources', ['revision_id'])
        op.create_index('idx_fos_source_rec', 'finding_occurrence_sources', ['source_table', 'source_record_id'])

    # 5. Add columns to finding_occurrences
    occ_cols = [c['name'] for c in insp.get_columns('finding_occurrences')]
    if 'revision_id' not in occ_cols:
        op.add_column('finding_occurrences', sa.Column('revision_id', sa.String(length=60), nullable=True))
        op.create_foreign_key(
            'fk_finding_occ_rev_id',
            'finding_occurrences',
            'fact_source_revisions',
            ['revision_id'],
            ['revision_id'],
            ondelete='SET NULL',
        )
        op.create_index('idx_occ_revision_id', 'finding_occurrences', ['revision_id'])

    if 'qualification_status' not in occ_cols:
        op.add_column('finding_occurrences', sa.Column('qualification_status', sa.String(length=30), nullable=True))
    if 'trust_level' not in occ_cols:
        op.add_column('finding_occurrences', sa.Column('trust_level', sa.String(length=30), nullable=True))
    if 'confidence' not in occ_cols:
        op.add_column('finding_occurrences', sa.Column('confidence', sa.String(length=30), nullable=True))
    if 'reason_codes' not in occ_cols:
        op.add_column('finding_occurrences', sa.Column('reason_codes', sa.String(length=255), nullable=True))
    if 'comparison_window' not in occ_cols:
        op.add_column('finding_occurrences', sa.Column('comparison_window', sa.String(length=100), nullable=True))

    # 6. Add columns to operational_findings
    finding_cols = [c['name'] for c in insp.get_columns('operational_findings')]
    if 'latest_qualification_status' not in finding_cols:
        op.add_column('operational_findings', sa.Column('latest_qualification_status', sa.String(length=30), nullable=True))
    if 'latest_trust_level' not in finding_cols:
        op.add_column('operational_findings', sa.Column('latest_trust_level', sa.String(length=30), nullable=True))
    if 'latest_confidence' not in finding_cols:
        op.add_column('operational_findings', sa.Column('latest_confidence', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('operational_findings', 'latest_confidence')
    op.drop_column('operational_findings', 'latest_trust_level')
    op.drop_column('operational_findings', 'latest_qualification_status')

    op.drop_constraint('fk_finding_occ_rev_id', 'finding_occurrences', type_='foreignkey')
    op.drop_index('idx_occ_revision_id', 'finding_occurrences')
    op.drop_column('finding_occurrences', 'comparison_window')
    op.drop_column('finding_occurrences', 'reason_codes')
    op.drop_column('finding_occurrences', 'confidence')
    op.drop_column('finding_occurrences', 'trust_level')
    op.drop_column('finding_occurrences', 'qualification_status')
    op.drop_column('finding_occurrences', 'revision_id')

    op.drop_table('finding_occurrence_sources')
    op.drop_table('daily_pipeline_runs')
    op.drop_table('dataset_factor_assumptions')
    op.drop_table('fact_source_revisions')
