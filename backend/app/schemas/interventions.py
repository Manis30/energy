"""Pydantic schemas for Measurement & Verification Plans, Deterministic Comparisons, and Savings Ledger."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# -------------------------------------------------------------------------
# Action Lifecycle Transition Requests
# -------------------------------------------------------------------------

class ReviewActionRequest(BaseModel):
    """Proposal review decision submitted by Facilities or Production."""
    decision: str = Field(..., description="Review decision: 'APPROVE' or 'REJECT'")
    reason: str = Field(..., min_length=3, description="Engineering reason or justification for decision")
    reviewer: str = Field(..., min_length=2, description="Reviewer name and department (e.g. 'Facilities Lead - A. Sharma')")
    caller_attribution: Optional[str] = None


class RecordImplementationRequest(BaseModel):
    """Implementation record submitted when the operational change is physically enacted."""
    implemented_at: datetime = Field(..., description="Timestamp when operational change was implemented")
    implemented_by: str = Field(..., min_length=2, description="Individual or team who executed implementation")
    implementation_notes: str = Field(..., min_length=5, description="Specific actions taken on physical equipment")
    work_order_id: Optional[str] = Field(None, description="Linked maintenance work order (e.g. 'MWO-00001')")
    downtime_event_id: Optional[str] = Field(None, description="Linked downtime event (e.g. 'DT-000001')")
    caller_attribution: Optional[str] = None


class RequestAssessmentRequest(BaseModel):
    """Request to initiate before/after outcome verification assessment."""
    requested_by: str = Field(..., min_length=2, description="Requester name and team")
    notes: Optional[str] = Field(None, description="Assessment context or target evaluation notes")
    caller_attribution: Optional[str] = None


# -------------------------------------------------------------------------
# Measurement Plan Schemas
# -------------------------------------------------------------------------

class MeasurementPlanResponse(BaseModel):
    """Measurement & Verification (M&V) Plan specifications."""
    id: int
    plan_id: str
    action_id: str
    version: int
    is_frozen: bool
    is_retrospective: bool
    intended_change: str
    implementation_owner: str
    plant_id: str
    process_or_line: str
    eligible_meters: List[str] = Field(default_factory=list)
    production_denominator: str
    production_unit: str
    baseline_start: str
    baseline_end: str
    post_start: str
    post_end: str
    stabilization_start: Optional[str] = None
    stabilization_end: Optional[str] = None
    stabilization_exclusion_reason: Optional[str] = None
    restart_exclusion_reason: Optional[str] = None

    guardrail_output_min: Optional[float] = None
    guardrail_output_unit: Optional[str] = None
    guardrail_output_direction: Optional[str] = "GREATER_OR_EQUAL"
    guardrail_output_source: Optional[str] = None
    guardrail_output_reason: Optional[str] = None

    guardrail_reject_max: Optional[float] = None
    guardrail_reject_unit: Optional[str] = None
    guardrail_reject_direction: Optional[str] = "LESS_OR_EQUAL"
    guardrail_reject_source: Optional[str] = None
    guardrail_reject_reason: Optional[str] = None

    guardrail_downtime_max_min: Optional[float] = None
    guardrail_downtime_unit: Optional[str] = None
    guardrail_downtime_direction: Optional[str] = "LESS_OR_EQUAL"
    guardrail_downtime_source: Optional[str] = None
    guardrail_downtime_reason: Optional[str] = None

    guardrail_restart_max_min: Optional[float] = None
    guardrail_restart_unit: Optional[str] = "minutes"
    guardrail_restart_direction: Optional[str] = "LESS_OR_EQUAL"
    guardrail_restart_source: Optional[str] = "Target Line Availability / Restart Envelope"
    guardrail_restart_reason: Optional[str] = None

    comparison_method: Optional[str] = "MATCHED_SCHEDULE"

    min_coverage_pct: float
    comparability_rules: Dict[str, Any] = Field(default_factory=dict)
    success_criterion: str
    success_criterion_metric: str
    success_criterion_threshold_pct: Optional[float] = None
    operating_conditions: Dict[str, Any] = Field(default_factory=dict)

    # Dual Boundary Architecture (Requirement Item 1)
    has_dual_boundary: bool = False
    boundary_type: Optional[str] = "SINGLE"  # "SINGLE" or "DUAL_STOPPAGE_AND_RESTART"
    boundary_a_config: Optional[Dict[str, Any]] = None  # Stoppage boundary
    boundary_b_config: Optional[Dict[str, Any]] = None  # Restart & productive shift boundary

    # Server-Side Timing Verification (Requirement Item 3)
    timing_status: Optional[str] = None  # "PROSPECTIVE_CONFIRMED", "RETROSPECTIVE_ENFORCED", "UNESTABLISHED"
    timing_reason: Optional[str] = None

    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    amendment_reason: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str


class CreateMeasurementPlanRequest(BaseModel):
    """Create a new M&V measurement plan before implementing change."""
    intended_change: str = Field(..., min_length=5, description="Intended operational or mechanical change")
    implementation_owner: str = Field(..., min_length=2, description="Assigned engineer or team owner")
    plant_id: str = Field(..., description="Target plant identifier (e.g. 'IN-KA-01')")
    process_or_line: str = Field(..., description="Process or line boundary (e.g. 'FAL-L2' or 'Final Assembly')")
    eligible_meters: List[str] = Field(..., min_items=1, description="Meters measuring target equipment")
    production_denominator: str = Field(..., description="Good finished units or process boards")
    production_unit: str = Field(..., description="Units of output (e.g. 'good units', 'boards')")
    baseline_start: datetime
    baseline_end: datetime
    post_start: datetime
    post_end: datetime
    stabilization_start: Optional[datetime] = None
    stabilization_end: Optional[datetime] = None
    stabilization_exclusion_reason: Optional[str] = None
    restart_exclusion_reason: Optional[str] = None

    guardrail_output_min: Optional[float] = Field(None, description="Minimum acceptable production output")
    guardrail_output_unit: Optional[str] = "units"
    guardrail_output_direction: Optional[str] = "GREATER_OR_EQUAL"
    guardrail_output_source: Optional[str] = "Approved Production Schedule"
    guardrail_output_reason: Optional[str] = Field(None, description="Engineering reason for minimum output target")

    guardrail_reject_max: Optional[float] = Field(None, description="Maximum allowable rejects or scrap")
    guardrail_reject_unit: Optional[str] = "units"
    guardrail_reject_direction: Optional[str] = "LESS_OR_EQUAL"
    guardrail_reject_source: Optional[str] = "Quality Specification Limit"
    guardrail_reject_reason: Optional[str] = Field(None, description="Engineering reason for maximum allowable rejects")

    guardrail_downtime_max_min: Optional[float] = Field(None, description="Maximum acceptable downtime in minutes")
    guardrail_downtime_unit: Optional[str] = "minutes"
    guardrail_downtime_direction: Optional[str] = "LESS_OR_EQUAL"
    guardrail_downtime_source: Optional[str] = "Target Line Availability"
    guardrail_downtime_reason: Optional[str] = Field(None, description="Engineering reason for maximum allowable downtime")

    guardrail_restart_max_min: Optional[float] = Field(None, description="Maximum allowable restart duration in minutes")
    guardrail_restart_unit: Optional[str] = "minutes"
    guardrail_restart_direction: Optional[str] = "LESS_OR_EQUAL"
    guardrail_restart_source: Optional[str] = "Target Line Availability / Restart Envelope"
    guardrail_restart_reason: Optional[str] = Field(None, description="Engineering reason for restart duration limit")

    comparison_method: Optional[str] = Field("MATCHED_SCHEDULE", description="MATCHED_SCHEDULE, IDENTICAL_HOUR_OF_WEEK, or EQUIVALENT_RUN_RATE")

    min_coverage_pct: float = Field(90.0, ge=50.0, le=100.0)
    comparability_rules: Dict[str, Any] = Field(default_factory=dict)
    success_criterion: str = Field(..., min_length=5, description="Explicit objective success statement")
    success_criterion_metric: str = Field("COST_INTENSITY", description="ELECTRICITY_INTENSITY, COST_INTENSITY, or AVOIDED_KWH")
    success_criterion_threshold_pct: Optional[float] = Field(-3.0, description="Target percentage reduction threshold")
    operating_conditions: Dict[str, Any] = Field(default_factory=dict)

    # Dual Boundary Architecture (Requirement Item 1)
    has_dual_boundary: bool = Field(False, description="Whether plan includes Boundary A (stoppage) and Boundary B (restart/shift)")
    boundary_type: Optional[str] = Field("SINGLE", description="SINGLE or DUAL_STOPPAGE_AND_RESTART")
    boundary_a_config: Optional[Dict[str, Any]] = Field(None, description="Configuration for Boundary A (stoppage window)")
    boundary_b_config: Optional[Dict[str, Any]] = Field(None, description="Configuration for Boundary B (restart & productive shift)")

    is_retrospective: Optional[bool] = Field(None, description="Flag explicitly if plan is defined retrospectively after outcome was known")
    created_by: Optional[str] = None


class AmendMeasurementPlanRequest(BaseModel):
    """Amend an existing M&V plan. Increments version and records amendment reason."""
    amendment_reason: str = Field(..., min_length=5, description="Engineering justification for amending plan")
    author: str = Field(..., min_length=2, description="Author submitting amendment")
    plan_data: CreateMeasurementPlanRequest


class ApproveMeasurementPlanRequest(BaseModel):
    """Approve and freeze a measurement plan."""
    reviewer: str = Field(..., min_length=2, description="Authorized reviewer name and role")
    approval_notes: Optional[str] = Field(None, description="Reviewer approval comments")


# -------------------------------------------------------------------------
# Period Analytics & Guardrails
# -------------------------------------------------------------------------

class PeriodAnalyticsSummary(BaseModel):
    """Aggregated deterministic metrics for an observation window."""
    kwh: float
    cost_inr: float
    actual_units: int
    good_units: int
    reject_units: int
    downtime_minutes: int
    operating_hours: int
    coverage_pct: Optional[float] = None
    kwh_per_good_unit: Optional[float] = None
    cost_per_good_unit: Optional[float] = None
    yield_pct: Optional[float] = None
    good_units_per_scheduled_hour: Optional[float] = None
    restart_minutes: Optional[int] = None
    source_revisions: List[str] = Field(default_factory=list)
    included_timestamps: List[str] = Field(default_factory=list)
    excluded_readings: List[Dict[str, Any]] = Field(default_factory=list)
    expected_intervals_count: int = 0
    expected_non_excluded_hours: int = 0
    complete_eligible_hours: int = 0
    missing_intervals: List[Dict[str, Any]] = Field(default_factory=list)
    conflicting_intervals: List[Dict[str, Any]] = Field(default_factory=list)
    numerator_value: Optional[float] = None
    numerator_unit: str = "kWh"
    denominator_value: Optional[int] = None
    denominator_unit: str = "good finished units"
    meter_boundary: List[str] = Field(default_factory=list)
    process_scope: str = "PROCESS"
    unrecovered_source_ids: List[str] = Field(default_factory=list)
    interval_readings: List[Dict[str, Any]] = Field(default_factory=list)


class GuardrailResult(BaseModel):
    """Evaluation result for a single production, quality, downtime, or restart guardrail."""
    guardrail_type: str = Field(..., description="OUTPUT, QUALITY_YIELD, DOWNTIME, or RESTART")
    metric_name: str
    target_value: float
    observed_value: Optional[float] = None
    unit: str
    direction: str = Field(..., description="GREATER_OR_EQUAL or LESS_OR_EQUAL")
    passed: bool
    source: str
    status: Optional[str] = Field(None, description="PASSED, BREACHED, or UNASSESSABLE")
    reason: Optional[str] = Field(None, description="Preapproved engineering reason for limit")
    failure_reason: Optional[str] = Field(None, description="Detailed reason for failure or unassessability")


class ExcludedIntervalInfo(BaseModel):
    """Information on an excluded observation interval."""
    interval_start: str
    interval_end: str
    reason: str


class ReferenceIntervalDetail(BaseModel):
    """Granular, inspectable reference interval showing baseline vs post counterfactual evaluation."""
    interval_start: str
    interval_end: str
    interval_type: str = "OBSERVATION"  # BASELINE_REFERENCE, POST_OBSERVATION, STOPPAGE_PERIOD, RESTART_SHIFT
    comparison_method: str = "MATCHED_SCHEDULE"
    eligibility_reason: str
    expected_kwh: Optional[float] = None
    observed_kwh: float
    difference_kwh: Optional[float] = None
    tolerance_kwh: Optional[float] = None
    uncertainty_pct: Optional[float] = 5.0


# -------------------------------------------------------------------------
# Comparison & Savings Response
# -------------------------------------------------------------------------

class InterventionComparisonResponse(BaseModel):
    """Side-by-side deterministic before/after comparison with guardrail and savings breakdown."""
    action_id: str
    plan_id: str
    plan_version: int
    is_frozen: bool
    is_retrospective: bool
    measurement_boundary: Dict[str, Any]

    baseline: PeriodAnalyticsSummary
    post: PeriodAnalyticsSummary
    included_intervals_count: int
    excluded_intervals: List[ExcludedIntervalInfo] = Field(default_factory=list)

    # Observed differences & percentage changes (post minus baseline)
    observed_kwh_change: Optional[float] = None
    observed_cost_change_inr: Optional[float] = None
    kwh_change_abs: Optional[float] = None
    kwh_change_pct: Optional[float] = None
    intensity_change_abs: Optional[float] = None
    intensity_change_pct: Optional[float] = None
    cost_intensity_change_abs: Optional[float] = None
    cost_intensity_change_pct: Optional[float] = None
    sign_convention: str = "Negative change indicates an improvement / reduction in consumption or intensity."

    # Attribution & methodology accountability
    attribution_method: str = "NONE_DEFENSIBLE_FOR_DATASET"
    attribution_eligibility: Dict[str, Any] = Field(default_factory=dict)
    factor_assumptions: Dict[str, Any] = Field(default_factory=dict)
    production_protection_status: str = "PROTECTED"
    restart_assessment: Optional[Dict[str, Any]] = None

    # Common-rate comparison using traceable tariff
    common_rate_baseline_cost_inr: Optional[float] = None
    common_rate_post_cost_inr: Optional[float] = None
    common_rate_cost_change_inr: Optional[float] = None
    common_rate_factor_inr_per_kwh: Optional[float] = None
    common_rate_factor_version: Optional[str] = None

    # Guardrails evaluation
    guardrails: List[GuardrailResult] = Field(default_factory=list)
    guardrails_passed: bool

    # Separated business decision & savings claims (Requirement Item 4)
    management_outcome: str = Field(
        ...,
        description="Plain-language management outcome: 'Eligible for verification — awaiting reviewer', 'Verified intervention improvement', 'Observed improvement; attribution unverified', 'Production limit breached', 'Cost objective not met', 'Inconclusive', or 'Awaiting data'",
    )
    management_outcome_detail: Optional[str] = None
    next_step: Optional[str] = Field(None, description="Concrete next steps when answer is inconclusive or unassessable")
    is_awaiting_data: bool = False
    remaining_time_minutes: Optional[int] = None
    comparison_method: Optional[str] = "MATCHED_SCHEDULE"
    work_order_link: Optional[Dict[str, Any]] = None
    downtime_event_link: Optional[Dict[str, Any]] = None

    # Inspectable comparison method & reference intervals (Requirement Item 4)
    comparison_mode: str = "DESCRIPTIVE_ONLY"  # "DESCRIPTIVE_ONLY" or "DETERMINISTIC_COUNTERFACTUAL"
    comparison_inspection_notes: Optional[str] = None
    reference_intervals: List[ReferenceIntervalDetail] = Field(default_factory=list)

    # Dual boundary breakdown (Requirement Item 1)
    has_dual_boundary: bool = False
    dual_boundary_breakdown: Optional[Dict[str, Any]] = None

    # Server-Side Timing Verification (Requirement Item 3)
    server_timing_verified: bool = False
    server_timing_reason: Optional[str] = None

    objective_outcome: str = Field(..., description="IMPROVED, NOT_IMPROVED, GUARDRAILS_BREACHED, or INCONCLUSIVE")
    electricity_savings_kwh: Optional[float] = Field(
        None,
        description="Defensible avoided kWh quantity; null if no approved reference model supports it.",
    )
    verified_electricity_savings_kwh: Optional[float] = Field(
        None,
        description="Verified electricity savings in kWh; published independently.",
    )
    monetary_savings_basis: str = Field(
        ...,
        description="SOURCE_COST_DIFF, ESTIMATED_AVOIDED_COST_VERSIONED_TARIFF, or UNAVAILABLE",
    )
    avoided_cost_inr: Optional[float] = Field(None, description="Quantified monetary savings if basis supports it")
    estimated_avoided_cost_inr: Optional[float] = Field(None, description="Estimated avoided cost in INR with assumption")
    estimated_avoided_cost_assumption: Optional[str] = Field(None, description="Factor assumption used for estimated cost")
    verified_monetary_savings_inr: Optional[float] = Field(None, description="Verified monetary savings in INR strictly under approved tariff")
    attribution_details: Optional[Dict[str, Any]] = Field(None, description="Detailed statistical attribution and uncertainty breakdown")
    savings_claim_status: str = Field(..., description="VERIFIED, NOT_VERIFIED, INCONCLUSIVE, or PENDING_REVIEW")
    savings_claim_description: str
    status_reason: str

    # Overlap detection
    overlap_flag: bool = False
    overlap_details: Optional[str] = None

    # Three Separate Answers (Requirement 3)
    three_separate_answers: Optional[Dict[str, Any]] = None


# -------------------------------------------------------------------------
# Assessment Ledger & Reviewer Sign-Off
# -------------------------------------------------------------------------

class AssessmentSignOffRequest(BaseModel):
    """Reviewer decision and sign-off on an outcome assessment."""
    reviewer: str = Field(..., min_length=2, description="Authorized reviewer name and title")
    decision: str = Field(..., description="'APPROVED_VERIFIED', 'REJECTED', or 'REQUEST_REANALYSIS'")
    notes: Optional[str] = Field(None, description="Reviewer evaluation notes")


class InterventionAssessmentResponse(BaseModel):
    """Persistent savings ledger entry."""
    id: int
    assessment_id: str
    action_id: str
    plan_id: str
    plan_version: int
    assessment_revision: int
    is_stale_flag: bool
    stale_reason: Optional[str] = None
    evaluated_at: str
    evaluated_by: Optional[str] = None
    calculation_method: str

    baseline_kwh: float
    baseline_cost_inr: float
    baseline_actual_units: int
    baseline_good_units: int
    baseline_reject_units: int
    baseline_downtime_min: int
    baseline_operating_hours: int
    baseline_coverage_pct: float
    baseline_kwh_per_good_unit: Optional[float] = None
    baseline_cost_per_good_unit: Optional[float] = None
    baseline_yield_pct: Optional[float] = None

    post_kwh: float
    post_cost_inr: float
    post_actual_units: int
    post_good_units: int
    post_reject_units: int
    post_downtime_min: int
    post_operating_hours: int
    post_coverage_pct: float
    post_kwh_per_good_unit: Optional[float] = None
    post_cost_per_good_unit: Optional[float] = None
    post_yield_pct: Optional[float] = None

    kwh_change_abs: Optional[float] = None
    kwh_change_pct: Optional[float] = None
    intensity_change_abs: Optional[float] = None
    intensity_change_pct: Optional[float] = None
    cost_intensity_change_abs: Optional[float] = None
    cost_intensity_change_pct: Optional[float] = None

    common_rate_cost_baseline_inr: Optional[float] = None
    common_rate_cost_post_inr: Optional[float] = None
    common_rate_factor_inr_per_kwh: Optional[float] = None
    common_rate_factor_version: Optional[str] = None

    output_guardrail_met: Optional[bool] = None
    quality_guardrail_met: Optional[bool] = None
    downtime_guardrail_met: Optional[bool] = None

    objective_outcome: str
    management_outcome: Optional[str] = None
    management_outcome_detail: Optional[str] = None
    next_step: Optional[str] = None
    is_awaiting_data: bool = False
    remaining_time_minutes: Optional[int] = None
    comparison_method: Optional[str] = None
    work_order_link: Optional[Dict[str, Any]] = None
    downtime_event_link: Optional[Dict[str, Any]] = None
    three_separate_answers: Optional[Dict[str, Any]] = None
    electricity_savings_kwh: Optional[float] = None
    verified_electricity_savings_kwh: Optional[float] = None
    monetary_savings_basis: str
    avoided_cost_inr: Optional[float] = None
    estimated_avoided_cost_inr: Optional[float] = None
    estimated_avoided_cost_assumption: Optional[str] = None
    verified_monetary_savings_inr: Optional[float] = None
    attribution_details: Optional[Dict[str, Any]] = None
    savings_claim_status: str
    savings_claim_description: str
    status_reason: str

    # Inspectable comparison method & reference intervals (Requirement Item 4)
    comparison_mode: Optional[str] = "DESCRIPTIVE_ONLY"
    reference_intervals: List[Dict[str, Any]] = Field(default_factory=list)

    # Dual boundary breakdown (Requirement Item 1)
    has_dual_boundary: bool = False
    dual_boundary_breakdown: Optional[Dict[str, Any]] = None

    # Server-Side Timing Verification (Requirement Item 3)
    server_timing_verified: bool = False
    server_timing_reason: Optional[str] = None

    overlap_flag: bool
    overlap_details: Optional[str] = None
    signed_off_by: Optional[str] = None
    signed_off_at: Optional[str] = None
    review_decision: Optional[str] = None
    review_notes: Optional[str] = None


class SavingsLedgerListResponse(BaseModel):
    """List response for the persistent savings ledger."""
    items: List[InterventionAssessmentResponse]
    total_count: int
    verified_count: int
    not_verified_count: int
    inconclusive_count: int
    total_verified_avoided_kwh: float
    total_estimated_avoided_cost_inr: float = 0.0
    estimated_avoided_cost_assumption: Optional[str] = None
    total_verified_monetary_savings_inr: float = 0.0
    total_verified_avoided_cost_inr: float


class DraftTrialPlanResponse(BaseModel):
    """Prefilled energy-saving trial plan draft."""
    is_suitable: bool
    unsuitable_reason: Optional[str] = None
    recommendation_type: str = "OPERATIONAL_TRIAL"  # OPERATIONAL_TRIAL or EVIDENCE_GATHERING
    audit_recommendation: Optional[str] = None
    plan_draft: Optional[CreateMeasurementPlanRequest] = None
    break_duration_minutes: Optional[float] = None
    restart_readiness_minutes: Optional[float] = None
    target_equipment: Optional[str] = None
    suggested_operating_change: Optional[str] = None
    operating_window: Optional[str] = None
    why_saves_electricity: Optional[str] = None
    production_dependencies: Optional[str] = None
    restart_requirements: Optional[str] = None
    stop_conditions: Optional[str] = None
    inference_source: str = "RULE_BASED_FALLBACK"  # DOMO_AI_MODEL or RULE_BASED_FALLBACK
    agent_execution_trace: Optional[Dict[str, Any]] = None


class AssessmentAIExplanationResponse(BaseModel):
    """AI Assistant explanation for outcome assessment."""
    assessment_id: str
    overall_verdict: str
    question_1_cost_intensity: Dict[str, Any]
    question_2_production_protection: Dict[str, Any]
    question_3_attribution: Dict[str, Any]
    dual_boundary_summary: Optional[Dict[str, Any]] = None
    ledger_eligibility: Dict[str, Any]
    narrative_explanation: str
    citations: List[Dict[str, str]] = Field(default_factory=list)
