"""SQLAlchemy models for persistent recommendations and corrective actions."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.findings import FindingOccurrence, OperationalFinding


class OperationalRecommendation(Base):
    """
    Persistent operational recommendation derived from energy/production findings.
    
    Provides actionable guidance, category classification, and operational prioritization
    without fabricated financial or energy savings claims.
    """

    __tablename__ = "operational_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    
    # Linked source finding and triggering occurrence
    finding_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        ForeignKey("operational_findings.finding_id", name="fk_op_rec_finding_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    occurrence_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        ForeignKey("finding_occurrences.occurrence_id", name="fk_op_rec_occurrence_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    plant_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MEDIUM",
        index=True,
    )  # CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OPEN",
        index=True,
    )  # OPEN, IN_PROGRESS, IMPLEMENTED, DISMISSED

    # Evidence and contextual data reference (JSON string)
    evidence_context_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Lifecycle timestamps
    implemented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    dismissed_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("recommendation_id", name="uq_op_recommendations_rec_id"),
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'IMPLEMENTED', 'DISMISSED')",
            name="chk_recommendation_status",
        ),
        CheckConstraint(
            "priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL')",
            name="chk_recommendation_priority",
        ),
        Index(
            "uq_active_rec_finding_category",
            "finding_id",
            "category",
            unique=True,
            postgresql_where=text("status IN ('OPEN', 'IN_PROGRESS')"),
            sqlite_where=text("status IN ('OPEN', 'IN_PROGRESS')"),
        ),
        Index("idx_rec_plant_status", "plant_id", "status"),
        Index("idx_rec_finding_id", "finding_id"),
        Index("idx_rec_occurrence_id", "occurrence_id"),
        Index("idx_rec_priority", "priority"),
        Index("idx_rec_category", "category"),
        Index("idx_rec_created_at", "created_at"),
    )

    finding: Mapped[Optional["OperationalFinding"]] = relationship(
        "OperationalFinding",
        back_populates="recommendations",
        foreign_keys=[finding_id],
    )
    occurrence: Mapped[Optional["FindingOccurrence"]] = relationship(
        "FindingOccurrence",
        foreign_keys=[occurrence_id],
    )
    actions: Mapped[List["CorrectiveAction"]] = relationship(
        "CorrectiveAction",
        back_populates="recommendation",
        cascade="all, delete-orphan",
        order_by="asc(CorrectiveAction.created_at)",
    )
    audit_logs: Mapped[List["RecommendationAuditLog"]] = relationship(
        "RecommendationAuditLog",
        back_populates="recommendation",
        cascade="save-update, merge",
        order_by="desc(RecommendationAuditLog.performed_at)",
    )


class CorrectiveAction(Base):
    """
    Persistent corrective action item tracked under an operational recommendation.
    
    Supports task tracking, assignment, due date management, and verified completion notes.
    """

    __tablename__ = "corrective_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    
    recommendation_id: Mapped[str] = mapped_column(
        String(60),
        ForeignKey("operational_recommendations.recommendation_id", name="fk_action_recommendation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OPEN",
        index=True,
    )  # OPEN, IN_PROGRESS, PROPOSED, APPROVED, REJECTED, IMPLEMENTED, ASSESSMENT_REQUESTED, COMPLETED, CANCELLED

    owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Phase 5: Lineage, Operational Boundary & Review Lifecycle
    plant_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    finding_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    occurrence_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    pinned_evidence_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    affected_equipment: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    measurement_meter_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    shared_meter_limitation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    responsible_team: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Facilities vs Production

    # Review Lifecycle (proposal approval/rejection)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING_REVIEW")  # PENDING_REVIEW, APPROVED, REJECTED
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    review_decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Implementation Lifecycle (requires concrete implementation timestamp before evaluating outcome)
    implemented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    implemented_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    implementation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Measurement Plan & Assessment Linking
    measurement_plan_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    assessment_status: Mapped[str] = mapped_column(String(30), nullable=False, default="NONE")  # NONE, REQUESTED, EVALUATED, VERIFIED, NOT_VERIFIED, INCONCLUSIVE

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("action_id", name="uq_corrective_actions_action_id"),
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'PROPOSED', 'APPROVED', 'REJECTED', 'IMPLEMENTED', 'ASSESSMENT_REQUESTED', 'COMPLETED', 'CANCELLED')",
            name="chk_action_status",
        ),
        Index("idx_action_recommendation_id", "recommendation_id"),
        Index("idx_action_status", "status"),
        Index("idx_action_owner", "owner"),
        Index("idx_action_due_date", "due_date"),
        Index("idx_action_created_at", "created_at"),
        Index("idx_action_plant_id", "plant_id"),
        Index("idx_action_review_status", "review_status"),
        Index("idx_action_assessment_status", "assessment_status"),
    )

    recommendation: Mapped["OperationalRecommendation"] = relationship(
        "OperationalRecommendation",
        back_populates="actions",
        foreign_keys=[recommendation_id],
    )
    audit_logs: Mapped[List["ActionAuditLog"]] = relationship(
        "ActionAuditLog",
        back_populates="corrective_action",
        cascade="save-update, merge",
        order_by="desc(ActionAuditLog.performed_at)",
    )
    plans: Mapped[List["InterventionPlan"]] = relationship(
        "InterventionPlan",
        back_populates="corrective_action",
        cascade="all, delete-orphan",
        order_by="desc(InterventionPlan.version)",
    )
    assessments: Mapped[List["InterventionAssessment"]] = relationship(
        "InterventionAssessment",
        back_populates="corrective_action",
        cascade="all, delete-orphan",
        order_by="desc(InterventionAssessment.assessment_revision)",
    )


class RecommendationAuditLog(Base):
    """
    Append-only audit trail tracking operational recommendation lifecycle transitions and modifications.
    """

    __tablename__ = "recommendation_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)

    recommendation_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        ForeignKey("operational_recommendations.recommendation_id", name="fk_rec_audit_rec_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_fields_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audit_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("audit_id", name="uq_rec_audit_id"),
        Index("idx_rec_audit_entity_perf", "entity_id", "performed_at"),
        Index("idx_rec_audit_rec_perf", "recommendation_id", "performed_at"),
    )

    recommendation: Mapped[Optional["OperationalRecommendation"]] = relationship(
        "OperationalRecommendation",
        back_populates="audit_logs",
        foreign_keys=[recommendation_id],
    )


class ActionAuditLog(Base):
    """
    Append-only audit trail tracking corrective action lifecycle transitions, ownership changes, and due dates.
    """

    __tablename__ = "action_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)

    action_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        ForeignKey("corrective_actions.action_id", name="fk_act_audit_act_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recommendation_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        ForeignKey("operational_recommendations.recommendation_id", name="fk_act_audit_rec_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_fields_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audit_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("audit_id", name="uq_act_audit_id"),
        Index("idx_act_audit_entity_perf", "entity_id", "performed_at"),
        Index("idx_act_audit_act_perf", "action_id", "performed_at"),
        Index("idx_act_audit_rec_perf", "recommendation_id", "performed_at"),
    )

    corrective_action: Mapped[Optional["CorrectiveAction"]] = relationship(
        "CorrectiveAction",
        back_populates="audit_logs",
        foreign_keys=[action_id],
    )
    recommendation: Mapped[Optional["OperationalRecommendation"]] = relationship(
        "OperationalRecommendation",
        foreign_keys=[recommendation_id],
    )


class InterventionPlan(Base):
    """
    Measurement and Verification (M&V) Plan captured before an operational intervention is executed.
    
    Includes operational boundary, baseline/post windows, stabilization exclusions,
    quality/output/downtime guardrails, and frozen approval versioning.
    """
    __tablename__ = "intervention_plans"
    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_plan_id_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(
        String(60),
        ForeignKey("corrective_actions.action_id", name="fk_plan_action_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_retrospective: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    intended_change: Mapped[str] = mapped_column(Text, nullable=False)
    implementation_owner: Mapped[str] = mapped_column(String(100), nullable=False)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    process_or_line: Mapped[str] = mapped_column(String(100), nullable=False)
    eligible_meters_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list of meter IDs
    production_denominator: Mapped[str] = mapped_column(String(100), nullable=False)
    production_unit: Mapped[str] = mapped_column(String(50), nullable=False)

    baseline_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    baseline_end: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    post_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    post_end: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    stabilization_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    stabilization_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    stabilization_exclusion_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    restart_exclusion_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Guardrails: output, quality/yield, downtime limits
    guardrail_output_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    guardrail_output_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    guardrail_output_direction: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="GREATER_OR_EQUAL")
    guardrail_output_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    guardrail_reject_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    guardrail_reject_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    guardrail_reject_direction: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="LESS_OR_EQUAL")
    guardrail_reject_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    guardrail_downtime_max_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    guardrail_downtime_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    guardrail_downtime_direction: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="LESS_OR_EQUAL")
    guardrail_downtime_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    min_coverage_pct: Mapped[float] = mapped_column(Float, nullable=False, default=90.0)
    comparability_rules_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    success_criterion: Mapped[str] = mapped_column(Text, nullable=False)
    success_criterion_metric: Mapped[str] = mapped_column(String(50), nullable=False, default="COST_INTENSITY")
    success_criterion_threshold_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    operating_conditions_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    amendment_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("plan_id", name="uq_intervention_plans_plan_id"),
        Index("idx_intervention_plan_action", "action_id"),
        Index("idx_intervention_plan_plant", "plant_id"),
    )

    corrective_action: Mapped["CorrectiveAction"] = relationship(
        "CorrectiveAction",
        back_populates="plans",
        foreign_keys=[action_id],
    )


class InterventionAssessment(Base):
    """
    Persistent ledger of deterministic savings verification assessments.
    
    Tracks before/after analytics, guardrail outcomes, objective business outcomes,
    avoided electricity quantities, monetary basis, reviewer decisions, and overlap flags.
    """
    __tablename__ = "intervention_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(
        String(60),
        ForeignKey("corrective_actions.action_id", name="fk_assessment_action_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    assessment_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    is_stale_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stale_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    evaluated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    calculation_method: Mapped[str] = mapped_column(String(60), nullable=False, default="DETERMINISTIC_COMPARISON_V1")

    # Baseline observations
    baseline_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_cost_inr: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_actual_units: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_good_units: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_reject_units: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_downtime_min: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_operating_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_coverage_pct: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_kwh_per_good_unit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    baseline_cost_per_good_unit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    baseline_yield_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Post-intervention observations
    post_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    post_cost_inr: Mapped[float] = mapped_column(Float, nullable=False)
    post_actual_units: Mapped[int] = mapped_column(Integer, nullable=False)
    post_good_units: Mapped[int] = mapped_column(Integer, nullable=False)
    post_reject_units: Mapped[int] = mapped_column(Integer, nullable=False)
    post_downtime_min: Mapped[int] = mapped_column(Integer, nullable=False)
    post_operating_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    post_coverage_pct: Mapped[float] = mapped_column(Float, nullable=False)
    post_kwh_per_good_unit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    post_cost_per_good_unit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    post_yield_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Changes & Deltas (explicit signs defined in schemas/services)
    kwh_change_abs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kwh_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    intensity_change_abs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    intensity_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_intensity_change_abs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_intensity_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Common-rate comparison using traceable tariff
    common_rate_cost_baseline_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    common_rate_cost_post_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    common_rate_factor_inr_per_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    common_rate_factor_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Guardrails outcomes
    output_guardrail_met: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    quality_guardrail_met: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    downtime_guardrail_met: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    guardrails_summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Business decision vs Savings quantity separation (Requirements Item 4)
    objective_outcome: Mapped[str] = mapped_column(String(50), nullable=False)  # IMPROVED, NOT_IMPROVED, GUARDRAILS_BREACHED, INCONCLUSIVE
    electricity_savings_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Null if no defensible comparison
    monetary_savings_basis: Mapped[str] = mapped_column(String(60), nullable=False)  # SOURCE_COST_DIFF, ESTIMATED_AVOIDED_COST_VERSIONED_TARIFF, UNAVAILABLE
    avoided_cost_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verified_monetary_savings_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    attribution_details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    savings_claim_status: Mapped[str] = mapped_column(String(30), nullable=False)  # VERIFIED, NOT_VERIFIED, INCONCLUSIVE, PENDING_REVIEW
    savings_claim_description: Mapped[str] = mapped_column(Text, nullable=False)
    status_reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Overlap detection
    overlap_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    overlap_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Revisions & Provenance
    baseline_source_revisions_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    post_source_revisions_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Human sign-off & governance
    signed_off_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    signed_off_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    review_decision: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # APPROVED_VERIFIED, REJECTED, REQUEST_REANALYSIS
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("assessment_id", name="uq_intervention_assessments_id"),
        Index("idx_intervention_assessment_action", "action_id"),
        Index("idx_intervention_assessment_plan", "plan_id"),
        Index("idx_intervention_assessment_status", "savings_claim_status"),
    )

    corrective_action: Mapped["CorrectiveAction"] = relationship(
        "CorrectiveAction",
        back_populates="assessments",
        foreign_keys=[action_id],
    )

