"""Phase 5: Corrective Actions, Measurement Plans, and Savings Ledger migration.

Extends corrective_actions with review lifecycle, implementation timestamps, operational boundary,
and links to measurement plans and assessment status.
Creates intervention_plans and intervention_assessments tables for deterministic M&V and savings ledger.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-19 00:25:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Extend corrective_actions table
    if insp.has_table('corrective_actions'):
        existing_cols = {c['name'] for c in insp.get_columns('corrective_actions')}

        new_columns = [
            ('plant_id', sa.String(30), True, None),
            ('finding_id', sa.String(60), True, None),
            ('occurrence_id', sa.String(60), True, None),
            ('pinned_evidence_json', sa.Text(), True, None),
            ('affected_equipment', sa.String(100), True, None),
            ('measurement_meter_id', sa.String(60), True, None),
            ('shared_meter_limitation', sa.Text(), True, None),
            ('responsible_team', sa.String(50), True, None),
            ('review_status', sa.String(30), False, sa.text("'PENDING_REVIEW'")),
            ('reviewed_by', sa.String(100), True, None),
            ('reviewed_at', sa.DateTime(), True, None),
            ('review_decision_reason', sa.Text(), True, None),
            ('implemented_at', sa.DateTime(), True, None),
            ('implemented_by', sa.String(100), True, None),
            ('implementation_notes', sa.Text(), True, None),
            ('measurement_plan_id', sa.String(60), True, None),
            ('assessment_status', sa.String(30), False, sa.text("'NONE'")),
        ]

        for col_name, col_type, nullable, server_default in new_columns:
            if col_name not in existing_cols:
                op.add_column('corrective_actions', sa.Column(col_name, col_type, nullable=nullable, server_default=server_default))

        # Update check constraint on status
        try:
            op.drop_constraint('chk_action_status', 'corrective_actions', type_='check')
        except Exception:
            pass

        try:
            op.create_check_constraint(
                'chk_action_status',
                'corrective_actions',
                "status IN ('OPEN', 'IN_PROGRESS', 'PROPOSED', 'APPROVED', 'REJECTED', 'IMPLEMENTED', 'ASSESSMENT_REQUESTED', 'COMPLETED', 'CANCELLED')",
            )
        except Exception:
            pass

        # Create new indexes
        existing_indexes = {ix['name'] for ix in insp.get_indexes('corrective_actions')}
        if 'idx_action_plant_id' not in existing_indexes:
            op.create_index('idx_action_plant_id', 'corrective_actions', ['plant_id'])
        if 'idx_action_review_status' not in existing_indexes:
            op.create_index('idx_action_review_status', 'corrective_actions', ['review_status'])
        if 'idx_action_assessment_status' not in existing_indexes:
            op.create_index('idx_action_assessment_status', 'corrective_actions', ['assessment_status'])

    # 2. intervention_plans table
    if not insp.has_table('intervention_plans'):
        op.create_table(
            'intervention_plans',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('plan_id', sa.String(60), unique=True, nullable=False),
            sa.Column('action_id', sa.String(60), sa.ForeignKey('corrective_actions.action_id', ondelete='CASCADE'), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('is_retrospective', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('intended_change', sa.Text(), nullable=False),
            sa.Column('implementation_owner', sa.String(100), nullable=False),
            sa.Column('plant_id', sa.String(50), nullable=False),
            sa.Column('process_or_line', sa.String(100), nullable=False),
            sa.Column('eligible_meters_json', sa.Text(), nullable=False),
            sa.Column('production_denominator', sa.String(100), nullable=False),
            sa.Column('production_unit', sa.String(50), nullable=False),
            sa.Column('baseline_start', sa.DateTime(), nullable=False),
            sa.Column('baseline_end', sa.DateTime(), nullable=False),
            sa.Column('post_start', sa.DateTime(), nullable=False),
            sa.Column('post_end', sa.DateTime(), nullable=False),
            sa.Column('stabilization_start', sa.DateTime(), nullable=True),
            sa.Column('stabilization_end', sa.DateTime(), nullable=True),
            sa.Column('stabilization_exclusion_reason', sa.Text(), nullable=True),
            sa.Column('restart_exclusion_reason', sa.Text(), nullable=True),
            sa.Column('guardrail_output_min', sa.Float(), nullable=True),
            sa.Column('guardrail_output_unit', sa.String(50), nullable=True),
            sa.Column('guardrail_output_direction', sa.String(30), nullable=True, server_default="'GREATER_OR_EQUAL'"),
            sa.Column('guardrail_output_source', sa.String(100), nullable=True),
            sa.Column('guardrail_reject_max', sa.Float(), nullable=True),
            sa.Column('guardrail_reject_unit', sa.String(50), nullable=True),
            sa.Column('guardrail_reject_direction', sa.String(30), nullable=True, server_default="'LESS_OR_EQUAL'"),
            sa.Column('guardrail_reject_source', sa.String(100), nullable=True),
            sa.Column('guardrail_downtime_max_min', sa.Float(), nullable=True),
            sa.Column('guardrail_downtime_unit', sa.String(50), nullable=True),
            sa.Column('guardrail_downtime_direction', sa.String(30), nullable=True, server_default="'LESS_OR_EQUAL'"),
            sa.Column('guardrail_downtime_source', sa.String(100), nullable=True),
            sa.Column('min_coverage_pct', sa.Float(), nullable=False, server_default='90.0'),
            sa.Column('comparability_rules_json', sa.Text(), nullable=True),
            sa.Column('success_criterion', sa.Text(), nullable=False),
            sa.Column('success_criterion_metric', sa.String(50), nullable=False, server_default="'COST_INTENSITY'"),
            sa.Column('success_criterion_threshold_pct', sa.Float(), nullable=True),
            sa.Column('operating_conditions_json', sa.Text(), nullable=True),
            sa.Column('approved_by', sa.String(100), nullable=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('amendment_reason', sa.Text(), nullable=True),
            sa.Column('created_by', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('idx_intervention_plan_action', 'intervention_plans', ['action_id'])
        op.create_index('idx_intervention_plan_plant', 'intervention_plans', ['plant_id'])

    # 3. intervention_assessments table
    if not insp.has_table('intervention_assessments'):
        op.create_table(
            'intervention_assessments',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('assessment_id', sa.String(60), unique=True, nullable=False),
            sa.Column('action_id', sa.String(60), sa.ForeignKey('corrective_actions.action_id', ondelete='CASCADE'), nullable=False),
            sa.Column('plan_id', sa.String(60), nullable=False),
            sa.Column('plan_version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('assessment_revision', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('is_stale_flag', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('stale_reason', sa.Text(), nullable=True),
            sa.Column('evaluated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('evaluated_by', sa.String(100), nullable=True),
            sa.Column('calculation_method', sa.String(60), nullable=False, server_default="'DETERMINISTIC_COMPARISON_V1'"),
            sa.Column('baseline_kwh', sa.Float(), nullable=False),
            sa.Column('baseline_cost_inr', sa.Float(), nullable=False),
            sa.Column('baseline_actual_units', sa.Integer(), nullable=False),
            sa.Column('baseline_good_units', sa.Integer(), nullable=False),
            sa.Column('baseline_reject_units', sa.Integer(), nullable=False),
            sa.Column('baseline_downtime_min', sa.Integer(), nullable=False),
            sa.Column('baseline_operating_hours', sa.Integer(), nullable=False),
            sa.Column('baseline_coverage_pct', sa.Float(), nullable=False),
            sa.Column('baseline_kwh_per_good_unit', sa.Float(), nullable=True),
            sa.Column('baseline_cost_per_good_unit', sa.Float(), nullable=True),
            sa.Column('baseline_yield_pct', sa.Float(), nullable=True),
            sa.Column('post_kwh', sa.Float(), nullable=False),
            sa.Column('post_cost_inr', sa.Float(), nullable=False),
            sa.Column('post_actual_units', sa.Integer(), nullable=False),
            sa.Column('post_good_units', sa.Integer(), nullable=False),
            sa.Column('post_reject_units', sa.Integer(), nullable=False),
            sa.Column('post_downtime_min', sa.Integer(), nullable=False),
            sa.Column('post_operating_hours', sa.Integer(), nullable=False),
            sa.Column('post_coverage_pct', sa.Float(), nullable=False),
            sa.Column('post_kwh_per_good_unit', sa.Float(), nullable=True),
            sa.Column('post_cost_per_good_unit', sa.Float(), nullable=True),
            sa.Column('post_yield_pct', sa.Float(), nullable=True),
            sa.Column('kwh_change_abs', sa.Float(), nullable=True),
            sa.Column('kwh_change_pct', sa.Float(), nullable=True),
            sa.Column('intensity_change_abs', sa.Float(), nullable=True),
            sa.Column('intensity_change_pct', sa.Float(), nullable=True),
            sa.Column('cost_intensity_change_abs', sa.Float(), nullable=True),
            sa.Column('cost_intensity_change_pct', sa.Float(), nullable=True),
            sa.Column('common_rate_cost_baseline_inr', sa.Float(), nullable=True),
            sa.Column('common_rate_cost_post_inr', sa.Float(), nullable=True),
            sa.Column('common_rate_factor_inr_per_kwh', sa.Float(), nullable=True),
            sa.Column('common_rate_factor_version', sa.String(50), nullable=True),
            sa.Column('output_guardrail_met', sa.Boolean(), nullable=True),
            sa.Column('quality_guardrail_met', sa.Boolean(), nullable=True),
            sa.Column('downtime_guardrail_met', sa.Boolean(), nullable=True),
            sa.Column('guardrails_summary_json', sa.Text(), nullable=True),
            sa.Column('objective_outcome', sa.String(50), nullable=False),
            sa.Column('electricity_savings_kwh', sa.Float(), nullable=True),
            sa.Column('monetary_savings_basis', sa.String(60), nullable=False),
            sa.Column('avoided_cost_inr', sa.Float(), nullable=True),
            sa.Column('savings_claim_status', sa.String(30), nullable=False),
            sa.Column('savings_claim_description', sa.Text(), nullable=False),
            sa.Column('status_reason', sa.Text(), nullable=False),
            sa.Column('overlap_flag', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('overlap_details', sa.Text(), nullable=True),
            sa.Column('baseline_source_revisions_json', sa.Text(), nullable=True),
            sa.Column('post_source_revisions_json', sa.Text(), nullable=True),
            sa.Column('signed_off_by', sa.String(100), nullable=True),
            sa.Column('signed_off_at', sa.DateTime(), nullable=True),
            sa.Column('review_decision', sa.String(40), nullable=True),
            sa.Column('review_notes', sa.Text(), nullable=True),
        )
        op.create_index('idx_intervention_assessment_action', 'intervention_assessments', ['action_id'])
        op.create_index('idx_intervention_assessment_plan', 'intervention_assessments', ['plan_id'])
        op.create_index('idx_intervention_assessment_status', 'intervention_assessments', ['savings_claim_status'])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table('intervention_assessments'):
        op.drop_table('intervention_assessments')
    if insp.has_table('intervention_plans'):
        op.drop_table('intervention_plans')

    if insp.has_table('corrective_actions'):
        cols_to_drop = [
            'plant_id', 'finding_id', 'occurrence_id', 'pinned_evidence_json',
            'affected_equipment', 'measurement_meter_id', 'shared_meter_limitation',
            'responsible_team', 'review_status', 'reviewed_by', 'reviewed_at',
            'review_decision_reason', 'implemented_at', 'implemented_by',
            'implementation_notes', 'measurement_plan_id', 'assessment_status'
        ]
        for col in cols_to_drop:
            try:
                op.drop_column('corrective_actions', col)
            except Exception:
                pass
