"""Pydantic schemas for Recommendations, Corrective Actions, and Audit Trail API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# -------------------------------------------------------------------------
# Audit Trail Schemas
# -------------------------------------------------------------------------

class RecommendationAuditLogResponse(BaseModel):
    """Audit log entry for operational recommendation changes."""
    id: int
    audit_id: str
    recommendation_id: Optional[str] = None
    entity_id: str
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    performed_at: str
    comment: Optional[str] = None
    changed_fields: Dict[str, Any] = Field(default_factory=dict)
    actor_attribution: Optional[str] = Field(
        None,
        description="Unverified caller-supplied attribution label (e.g. operator label).",
    )
    actor_type: str = Field(
        "UNVERIFIED_CALLER",
        description="Attribution classification: 'SYSTEM_AUTOMATION' or 'UNVERIFIED_CALLER'.",
    )
    source: str = Field("SYSTEM_AUTOMATION", description="Source or subsystem that initiated the audit event.")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ActionAuditLogResponse(BaseModel):
    """Audit log entry for corrective action changes."""
    id: int
    audit_id: str
    action_id: Optional[str] = None
    recommendation_id: Optional[str] = None
    entity_id: str
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    performed_at: str
    comment: Optional[str] = None
    changed_fields: Dict[str, Any] = Field(default_factory=dict)
    actor_attribution: Optional[str] = Field(
        None,
        description="Unverified caller-supplied attribution label (e.g. operator label).",
    )
    actor_type: str = Field(
        "UNVERIFIED_CALLER",
        description="Attribution classification: 'SYSTEM_AUTOMATION' or 'UNVERIFIED_CALLER'.",
    )
    source: str = Field("SYSTEM_AUTOMATION", description="Source or subsystem that initiated the audit event.")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# -------------------------------------------------------------------------
# Corrective Action Schemas
# -------------------------------------------------------------------------

class CorrectiveActionResponse(BaseModel):
    """Corrective action item details with historical audit trail."""
    action_id: str
    recommendation_id: str
    title: str
    description: str
    status: str = Field(description="OPEN, IN_PROGRESS, PROPOSED, APPROVED, REJECTED, IMPLEMENTED, ASSESSMENT_REQUESTED, COMPLETED, CANCELLED")
    owner: Optional[str] = Field(None, description="Assigned owner or team label. Nullable.")
    due_date: Optional[str] = Field(None, description="ISO format due date string")
    completed_at: Optional[str] = Field(None, description="ISO format completion timestamp")
    resolution_notes: Optional[str] = Field(None, description="Notes documenting resolution or progress")

    # Phase 5: Boundary, Lineage & Review Lifecycle
    plant_id: Optional[str] = None
    finding_id: Optional[str] = None
    occurrence_id: Optional[str] = None
    pinned_evidence: List[Any] = Field(default_factory=list)
    affected_equipment: Optional[str] = None
    measurement_meter_id: Optional[str] = None
    shared_meter_limitation: Optional[str] = None
    responsible_team: Optional[str] = None

    review_status: str = "PENDING_REVIEW"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_decision_reason: Optional[str] = None

    implemented_at: Optional[str] = None
    implemented_by: Optional[str] = None
    implementation_notes: Optional[str] = None

    measurement_plan_id: Optional[str] = None
    assessment_status: str = "NONE"

    created_at: str
    updated_at: str
    audit_trail: List[ActionAuditLogResponse] = Field(default_factory=list)


class ActionListResponse(BaseModel):
    """Paginated corrective actions response."""
    items: List[CorrectiveActionResponse]
    total: int
    limit: int
    offset: int


class CreateActionRequest(BaseModel):
    """Request payload to create a new corrective action under a recommendation."""
    title: str = Field(..., min_length=3, max_length=200, description="Short title of the corrective action")
    description: str = Field(..., min_length=3, description="Detailed actionable description of required tasks")
    owner: Optional[str] = Field(None, max_length=100, description="Optional assignee or team label. Nullable.")
    due_date: Optional[datetime] = Field(None, description="Optional planned completion date")
    caller_attribution: Optional[str] = Field(
        None,
        max_length=150,
        description="Optional unverified caller attribution label (e.g. operator label).",
    )


class UpdateActionRequest(BaseModel):
    """Request payload to update an existing corrective action."""
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, min_length=3)
    status: Optional[str] = Field(None, description="OPEN, IN_PROGRESS, COMPLETED, CANCELLED")
    owner: Optional[str] = Field(None, max_length=100, description="Assigned owner or team label")
    clear_owner: Optional[bool] = Field(False, description="Explicitly remove owner assignment")
    due_date: Optional[datetime] = Field(None, description="Planned due date")
    clear_due_date: Optional[bool] = Field(False, description="Explicitly remove due date")
    resolution_notes: Optional[str] = Field(None, description="Resolution or completion documentation")
    caller_attribution: Optional[str] = Field(
        None,
        max_length=150,
        description="Optional unverified caller attribution label (e.g. operator label).",
    )


# -------------------------------------------------------------------------
# Operational Recommendation Schemas
# -------------------------------------------------------------------------

class RecommendationSummary(BaseModel):
    """High-level summary of an operational recommendation."""
    recommendation_id: str
    finding_id: Optional[str] = Field(None, description="Linked operational finding ID")
    occurrence_id: Optional[str] = Field(None, description="Linked triggering occurrence ID")
    plant_id: str
    title: str
    description: str
    category: str
    priority: str = Field(description="CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL")
    status: str = Field(description="OPEN, IN_PROGRESS, IMPLEMENTED, DISMISSED")
    action_count: int = 0
    open_action_count: int = 0
    implemented_at: Optional[str] = None
    dismissed_at: Optional[str] = None
    created_at: str
    updated_at: str


class RecommendationDetailResponse(RecommendationSummary):
    """Full operational recommendation details including actions, evidence context, and audit trail."""
    evidence_context: Dict[str, Any] = Field(default_factory=dict)
    dismissed_reason: Optional[str] = None
    actions: List[CorrectiveActionResponse] = Field(default_factory=list)
    source_finding: Optional[Dict[str, Any]] = Field(None, description="Snapshot of source finding metadata if linked")
    audit_trail: List[RecommendationAuditLogResponse] = Field(default_factory=list)


class RecommendationListResponse(BaseModel):
    """Paginated recommendations response."""
    items: List[RecommendationSummary]
    total: int
    limit: int
    offset: int


class CreateRecommendationRequest(BaseModel):
    """Request payload to create a persistent operational recommendation."""
    plant_id: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=3)
    category: str = Field(..., min_length=1, max_length=50)
    priority: str = Field("MEDIUM", description="CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL")
    finding_id: Optional[str] = Field(None, max_length=60, description="Optional linked operational finding")
    occurrence_id: Optional[str] = Field(None, max_length=60, description="Optional linked occurrence")
    evidence_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured telemetry facts and lineage context. Never fabricated financial or savings values.",
    )
    caller_attribution: Optional[str] = Field(
        None,
        max_length=150,
        description="Optional unverified caller attribution label (e.g. operator label).",
    )


class UpdateRecommendationStatusRequest(BaseModel):
    """Request payload to transition recommendation lifecycle status."""
    status: str = Field(..., description="Target status: OPEN, IN_PROGRESS, IMPLEMENTED, DISMISSED")
    reason: Optional[str] = Field(None, max_length=1000, description="Reason if dismissed or reopened")
    caller_attribution: Optional[str] = Field(
        None,
        max_length=150,
        description="Optional unverified caller attribution label (e.g. operator label).",
    )


class GenerateRecommendationsResponse(BaseModel):
    """Response payload when generating recommendations from an operational finding."""
    generated_count: int = Field(..., description="Count of newly generated recommendations")
    created_count: int = Field(0, description="Count of newly created recommendations")
    reused_count: int = Field(0, description="Count of existing active recommendations reused")
    recommendations: List[RecommendationSummary]
    message: str
