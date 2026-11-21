"""Operational Recommendations, Corrective Actions, and Audit Trail API endpoints."""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.recommendations import (
    ActionAuditLog,
    CorrectiveAction,
    InterventionAssessment,
    OperationalRecommendation,
    RecommendationAuditLog,
)
from app.schemas.recommendations import (
    ActionAuditLogResponse,
    ActionListResponse,
    CorrectiveActionResponse,
    CreateActionRequest,
    CreateRecommendationRequest,
    GenerateRecommendationsResponse,
    RecommendationAuditLogResponse,
    RecommendationDetailResponse,
    RecommendationListResponse,
    RecommendationSummary,
    UpdateActionRequest,
    UpdateRecommendationStatusRequest,
)
from app.schemas.interventions import (
    AmendMeasurementPlanRequest,
    ApproveMeasurementPlanRequest,
    AssessmentAIExplanationResponse,
    AssessmentSignOffRequest,
    CreateMeasurementPlanRequest,
    DraftTrialPlanResponse,
    InterventionAssessmentResponse,
    InterventionComparisonResponse,
    MeasurementPlanResponse,
    RecordImplementationRequest,
    RequestAssessmentRequest,
    ReviewActionRequest,
    SavingsLedgerListResponse,
)
from app.services.recommendation_service import (
    create_corrective_action,
    create_recommendation,
    draft_trial_plan_from_recommendation,
    generate_recommendations_from_finding,
    get_action_audit_logs,
    get_corrective_action,
    get_recommendation_audit_logs,
    get_recommendation_detail,
    list_corrective_actions,
    list_recommendations,
    update_corrective_action,
    update_recommendation_status,
)
from app.services.finding_ai_investigation_service import explain_assessment_with_ai
from app.services.intervention_service import (
    amend_measurement_plan,
    approve_measurement_plan,
    create_measurement_plan,
    evaluate_and_record_assessment,
    get_measurement_plan_for_action,
    list_savings_ledger,
    plan_to_response,
    record_action_implementation,
    request_action_assessment,
    review_corrective_action,
    sign_off_assessment,
)

recommendations_router = APIRouter()
actions_router = APIRouter()


# -------------------------------------------------------------------------
# Serialization Helpers
# -------------------------------------------------------------------------

def _rec_audit_to_dict(log: RecommendationAuditLog) -> Dict[str, Any]:
    """Serialize RecommendationAuditLog model to dictionary."""
    changed = {}
    if log.changed_fields_json:
        try:
            changed = json.loads(log.changed_fields_json)
        except Exception:
            changed = {}

    meta = {}
    if log.audit_metadata_json:
        try:
            meta = json.loads(log.audit_metadata_json)
        except Exception:
            meta = {}

    return {
        "id": log.id,
        "audit_id": log.audit_id,
        "recommendation_id": log.recommendation_id,
        "entity_id": log.entity_id,
        "action": log.action,
        "from_status": log.from_status,
        "to_status": log.to_status,
        "performed_at": log.performed_at.isoformat() if log.performed_at else "",
        "comment": log.comment,
        "changed_fields": changed,
        "actor_attribution": meta.get("actor_attribution"),
        "actor_type": meta.get("actor_type", "UNVERIFIED_CALLER"),
        "source": meta.get("source", "SYSTEM_AUTOMATION"),
        "metadata": meta.get("details", {}),
    }


def _action_audit_to_dict(log: ActionAuditLog) -> Dict[str, Any]:
    """Serialize ActionAuditLog model to dictionary."""
    changed = {}
    if log.changed_fields_json:
        try:
            changed = json.loads(log.changed_fields_json)
        except Exception:
            changed = {}

    meta = {}
    if log.audit_metadata_json:
        try:
            meta = json.loads(log.audit_metadata_json)
        except Exception:
            meta = {}

    return {
        "id": log.id,
        "audit_id": log.audit_id,
        "action_id": log.action_id,
        "recommendation_id": log.recommendation_id,
        "entity_id": log.entity_id,
        "action": log.action,
        "from_status": log.from_status,
        "to_status": log.to_status,
        "performed_at": log.performed_at.isoformat() if log.performed_at else "",
        "comment": log.comment,
        "changed_fields": changed,
        "actor_attribution": meta.get("actor_attribution"),
        "actor_type": meta.get("actor_type", "UNVERIFIED_CALLER"),
        "source": meta.get("source", "SYSTEM_AUTOMATION"),
        "metadata": meta.get("details", {}),
    }


def _action_to_dict(a: CorrectiveAction) -> Dict[str, Any]:
    """Serialize CorrectiveAction model to dictionary including audit trail."""
    logs = getattr(a, "audit_logs", None) or []
    pinned_ev = []
    if getattr(a, "pinned_evidence_json", None):
        try:
            pinned_ev = json.loads(a.pinned_evidence_json)
        except Exception:
            pinned_ev = []

    return {
        "action_id": a.action_id,
        "recommendation_id": a.recommendation_id,
        "title": a.title,
        "description": a.description,
        "status": a.status,
        "owner": a.owner,
        "due_date": a.due_date.isoformat() if a.due_date else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "resolution_notes": a.resolution_notes,
        "plant_id": getattr(a, "plant_id", None),
        "finding_id": getattr(a, "finding_id", None),
        "occurrence_id": getattr(a, "occurrence_id", None),
        "pinned_evidence": pinned_ev,
        "affected_equipment": getattr(a, "affected_equipment", None),
        "measurement_meter_id": getattr(a, "measurement_meter_id", None),
        "shared_meter_limitation": getattr(a, "shared_meter_limitation", None),
        "responsible_team": getattr(a, "responsible_team", None),
        "review_status": getattr(a, "review_status", "PENDING_REVIEW"),
        "reviewed_by": getattr(a, "reviewed_by", None),
        "reviewed_at": a.reviewed_at.isoformat() if getattr(a, "reviewed_at", None) else None,
        "review_decision_reason": getattr(a, "review_decision_reason", None),
        "implemented_at": a.implemented_at.isoformat() if getattr(a, "implemented_at", None) else None,
        "implemented_by": getattr(a, "implemented_by", None),
        "implementation_notes": getattr(a, "implementation_notes", None),
        "measurement_plan_id": getattr(a, "measurement_plan_id", None),
        "assessment_status": getattr(a, "assessment_status", "NONE"),
        "created_at": a.created_at.isoformat() if a.created_at else "",
        "updated_at": a.updated_at.isoformat() if a.updated_at else "",
        "audit_trail": [_action_audit_to_dict(log) for log in logs],
    }


def _recommendation_to_summary_dict(r: OperationalRecommendation) -> Dict[str, Any]:
    """Serialize OperationalRecommendation model to summary dictionary."""
    actions = r.actions or []
    open_actions = sum(1 for a in actions if a.status in ("OPEN", "IN_PROGRESS"))
    return {
        "recommendation_id": r.recommendation_id,
        "finding_id": r.finding_id,
        "occurrence_id": r.occurrence_id,
        "plant_id": r.plant_id,
        "title": r.title,
        "description": r.description,
        "category": r.category,
        "priority": r.priority,
        "status": r.status,
        "action_count": len(actions),
        "open_action_count": open_actions,
        "implemented_at": r.implemented_at.isoformat() if r.implemented_at else None,
        "dismissed_at": r.dismissed_at.isoformat() if r.dismissed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "updated_at": r.updated_at.isoformat() if r.updated_at else "",
    }


def _recommendation_to_detail_dict(r: OperationalRecommendation) -> Dict[str, Any]:
    """Serialize OperationalRecommendation with actions, finding snapshot, evidence, and audit trail."""
    summary = _recommendation_to_summary_dict(r)
    evidence = {}
    if r.evidence_context_json:
        try:
            evidence = json.loads(r.evidence_context_json)
        except Exception:
            evidence = {}

    actions_data = [_action_to_dict(a) for a in (r.actions or [])]
    audit_trail_data = [_rec_audit_to_dict(log) for log in (getattr(r, "audit_logs", None) or [])]

    finding_summary = None
    if hasattr(r, "finding") and r.finding:
        f = r.finding
        finding_summary = {
            "finding_id": f.finding_id,
            "anomaly_type": f.anomaly_type,
            "plant_id": f.plant_id,
            "meter_id": f.meter_id,
            "line_id": f.line_id,
            "status": f.status,
            "severity": f.severity,
            "current_actual_value": f.current_actual_value,
            "current_baseline_value": f.current_baseline_value,
            "current_deviation_score": f.current_deviation_score,
            "occurrence_count": f.occurrence_count,
            "last_detected_at": f.last_detected_at.isoformat() if f.last_detected_at else None,
        }

    return {
        **summary,
        "evidence_context": evidence,
        "dismissed_reason": r.dismissed_reason,
        "actions": actions_data,
        "source_finding": finding_summary,
        "audit_trail": audit_trail_data,
    }


# -------------------------------------------------------------------------
# Recommendations Endpoints
# -------------------------------------------------------------------------

@recommendations_router.get(
    "",
    response_model=RecommendationListResponse,
    summary="List operational recommendations",
    description="Retrieve paginated operational recommendations with optional filtering by plant, finding, status, priority, or category.",
)
def get_recommendations(
    plant_id: Optional[str] = Query(None, description="Filter by plant / facility ID"),
    finding_id: Optional[str] = Query(None, description="Filter by linked operational finding ID"),
    status: Optional[str] = Query(None, description="Filter by status: OPEN, IN_PROGRESS, IMPLEMENTED, DISMISSED"),
    priority: Optional[str] = Query(None, description="Filter by priority: CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL"),
    category: Optional[str] = Query(None, description="Filter by category (e.g. POWER_FACTOR_CORRECTION, STANDBY_SHUTDOWN)"),
    limit: int = Query(50, ge=1, le=500, description="Items per page (default 50, max 500)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: Session = Depends(get_db_session),
) -> RecommendationListResponse:
    items, total = list_recommendations(
        session=session,
        plant_id=plant_id,
        finding_id=finding_id,
        status=status,
        priority=priority,
        category=category,
        limit=limit,
        offset=offset,
    )
    return RecommendationListResponse(
        items=[RecommendationSummary(**_recommendation_to_summary_dict(r)) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# -------------------------------------------------------------------------
# Phase 5: Persistent Savings Ledger Endpoints
# (Registered before /{recommendation_id} and /{action_id} to prevent shadowing)
# -------------------------------------------------------------------------

@actions_router.get(
    "/savings-ledger",
    response_model=SavingsLedgerListResponse,
    summary="List savings ledger entries",
    description="Retrieve all persistent M&V intervention assessments from the savings ledger.",
)
@recommendations_router.get(
    "/savings-ledger",
    response_model=SavingsLedgerListResponse,
    summary="List savings ledger entries",
    description="Retrieve all persistent M&V intervention assessments from the savings ledger.",
)
def get_savings_ledger_endpoint(
    plant_id: Optional[str] = Query(None, description="Filter by plant ID"),
    status: Optional[str] = Query(None, description="Filter by claim status: VERIFIED, NOT_VERIFIED, INCONCLUSIVE, PENDING_REVIEW"),
    limit: int = Query(50, ge=1, le=500, description="Items per page (default 50, max 500)"),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db_session),
) -> SavingsLedgerListResponse:
    return list_savings_ledger(
        session=session,
        plant_id=plant_id,
        savings_claim_status=status,
        limit=limit,
        offset=offset,
    )


@recommendations_router.get(
    "/{recommendation_id}",
    response_model=RecommendationDetailResponse,
    summary="Get recommendation detail",
    description="Retrieve full details for an operational recommendation including associated corrective actions, source finding context, and append-only audit trail.",
)
def get_recommendation(
    recommendation_id: str,
    session: Session = Depends(get_db_session),
) -> RecommendationDetailResponse:
    rec = get_recommendation_detail(session, recommendation_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Operational recommendation '{recommendation_id}' not found.",
        )
    return RecommendationDetailResponse(**_recommendation_to_detail_dict(rec))


@recommendations_router.get(
    "/{recommendation_id}/audit",
    response_model=List[RecommendationAuditLogResponse],
    summary="Get recommendation audit trail",
    description="Retrieve the complete append-only historical audit trail for an operational recommendation.",
)
def get_recommendation_audit(
    recommendation_id: str,
    limit: int = Query(100, ge=1, le=500, description="Maximum audit entries to retrieve"),
    session: Session = Depends(get_db_session),
) -> List[RecommendationAuditLogResponse]:
    rec = get_recommendation_detail(session, recommendation_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Operational recommendation '{recommendation_id}' not found.",
        )
    logs = get_recommendation_audit_logs(session, recommendation_id, limit=limit)
    return [RecommendationAuditLogResponse(**_rec_audit_to_dict(log)) for log in logs]


@recommendations_router.post(
    "",
    response_model=RecommendationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create operational recommendation",
    description="Manually create an operational recommendation linked to evidence or findings with append-only audit tracking.",
)
def create_new_recommendation(
    payload: CreateRecommendationRequest,
    session: Session = Depends(get_db_session),
) -> RecommendationDetailResponse:
    try:
        rec = create_recommendation(
            session=session,
            data=payload,
            caller_attribution=payload.caller_attribution,
        )
        # Fetch with relationships for detail serialization
        detail = get_recommendation_detail(session, rec.recommendation_id) or rec
        return RecommendationDetailResponse(**_recommendation_to_detail_dict(detail))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@recommendations_router.post(
    "/generate/{finding_id}",
    response_model=GenerateRecommendationsResponse,
    summary="Generate recommendation from finding",
    description="Deterministically create actionable operational recommendations from an existing energy finding using domain rules.",
)
def generate_from_finding(
    finding_id: str,
    caller_attribution: Optional[str] = Query(None, description="Optional unverified caller label"),
    session: Session = Depends(get_db_session),
) -> GenerateRecommendationsResponse:
    try:
        recs, created_count, reused_count = generate_recommendations_from_finding(
            session=session,
            finding_id=finding_id,
            caller_attribution=caller_attribution,
        )
        summaries = [RecommendationSummary(**_recommendation_to_summary_dict(r)) for r in recs]
        if created_count > 0:
            msg = f"Created {created_count} new recommendation(s) for finding '{finding_id}'."
        else:
            msg = f"Reused {reused_count} existing active recommendation(s) for finding '{finding_id}'."
        return GenerateRecommendationsResponse(
            generated_count=created_count,
            created_count=created_count,
            reused_count=reused_count,
            recommendations=summaries,
            message=msg,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@recommendations_router.patch(
    "/{recommendation_id}/status",
    response_model=RecommendationDetailResponse,
    summary="Update recommendation status",
    description="Update lifecycle status of a recommendation (OPEN, IN_PROGRESS, IMPLEMENTED, DISMISSED) with audit trail.",
)
def update_status(
    recommendation_id: str,
    payload: UpdateRecommendationStatusRequest,
    session: Session = Depends(get_db_session),
) -> RecommendationDetailResponse:
    try:
        rec = update_recommendation_status(
            session=session,
            recommendation_id=recommendation_id,
            new_status=payload.status,
            reason=payload.reason,
            caller_attribution=payload.caller_attribution,
        )
        detail = get_recommendation_detail(session, rec.recommendation_id) or rec
        return RecommendationDetailResponse(**_recommendation_to_detail_dict(detail))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@recommendations_router.post(
    "/{recommendation_id}/actions",
    response_model=CorrectiveActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create corrective action under recommendation",
    description="Create a persistent corrective action task linked to the specified recommendation with audit tracking.",
)
def add_action_to_recommendation(
    recommendation_id: str,
    payload: CreateActionRequest,
    session: Session = Depends(get_db_session),
) -> CorrectiveActionResponse:
    try:
        action = create_corrective_action(
            session=session,
            recommendation_id=recommendation_id,
            data=payload,
            caller_attribution=payload.caller_attribution,
        )
        detail = get_corrective_action(session, action.action_id) or action
        return CorrectiveActionResponse(**_action_to_dict(detail))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@recommendations_router.post(
    "/{recommendation_id}/draft-trial-plan",
    response_model=DraftTrialPlanResponse,
    summary="Draft energy-saving trial plan",
    description="Prefill measurement plan with dual boundary, operating change, and production guardrails based on recommendation evidence.",
)
def draft_trial_plan_endpoint(
    recommendation_id: str,
    break_duration_minutes: Optional[float] = Query(None, description="Planned stoppage duration in minutes"),
    restart_readiness_minutes: Optional[float] = Query(None, description="Equipment restart readiness in minutes"),
    caller_attribution: Optional[str] = Query(None, description="Optional caller label"),
    session: Session = Depends(get_db_session),
) -> DraftTrialPlanResponse:
    try:
        draft_data = draft_trial_plan_from_recommendation(
            session=session,
            recommendation_id=recommendation_id,
            break_duration_minutes=break_duration_minutes,
            restart_readiness_minutes=restart_readiness_minutes,
            caller_attribution=caller_attribution,
        )
        return DraftTrialPlanResponse(**draft_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -------------------------------------------------------------------------
# Corrective Actions Endpoints
# -------------------------------------------------------------------------

@actions_router.get(
    "",
    response_model=ActionListResponse,
    summary="List corrective actions",
    description="Retrieve paginated corrective actions with optional filtering by recommendation, status, or owner.",
)
def get_actions(
    recommendation_id: Optional[str] = Query(None, description="Filter by parent recommendation ID"),
    status: Optional[str] = Query(None, description="Filter by status: OPEN, IN_PROGRESS, COMPLETED, CANCELLED"),
    owner: Optional[str] = Query(None, description="Filter by assigned owner substring"),
    limit: int = Query(50, ge=1, le=500, description="Items per page (default 50, max 500)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: Session = Depends(get_db_session),
) -> ActionListResponse:
    items, total = list_corrective_actions(
        session=session,
        recommendation_id=recommendation_id,
        status=status,
        owner=owner,
        limit=limit,
        offset=offset,
    )
    return ActionListResponse(
        items=[CorrectiveActionResponse(**_action_to_dict(a)) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@actions_router.get(
    "/{action_id}",
    response_model=CorrectiveActionResponse,
    summary="Get corrective action detail",
    description="Retrieve single corrective action by its unique identifier including historical audit trail.",
)
def get_action_detail(
    action_id: str,
    session: Session = Depends(get_db_session),
) -> CorrectiveActionResponse:
    action = get_corrective_action(session, action_id)
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Corrective action '{action_id}' not found.",
        )
    return CorrectiveActionResponse(**_action_to_dict(action))


@actions_router.get(
    "/{action_id}/audit",
    response_model=List[ActionAuditLogResponse],
    summary="Get corrective action audit trail",
    description="Retrieve the complete append-only historical audit trail for a corrective action.",
)
def get_action_audit(
    action_id: str,
    limit: int = Query(100, ge=1, le=500, description="Maximum audit entries to retrieve"),
    session: Session = Depends(get_db_session),
) -> List[ActionAuditLogResponse]:
    action = get_corrective_action(session, action_id)
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Corrective action '{action_id}' not found.",
        )
    logs = get_action_audit_logs(session, action_id, limit=limit)
    return [ActionAuditLogResponse(**_action_audit_to_dict(log)) for log in logs]


@actions_router.patch(
    "/{action_id}",
    response_model=CorrectiveActionResponse,
    summary="Update corrective action",
    description="Update status, assignee owner, due date, or resolution documentation of a corrective action with audit trail.",
)
def update_action(
    action_id: str,
    payload: UpdateActionRequest,
    session: Session = Depends(get_db_session),
) -> CorrectiveActionResponse:
    try:
        action = update_corrective_action(
            session=session,
            action_id=action_id,
            data=payload,
            caller_attribution=payload.caller_attribution,
        )
        detail = get_corrective_action(session, action.action_id) or action
        return CorrectiveActionResponse(**_action_to_dict(detail))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -------------------------------------------------------------------------
# Phase 5: Action Proposal Review, Implementation & Outcome Assessment
# -------------------------------------------------------------------------

@actions_router.post(
    "/{action_id}/review",
    response_model=CorrectiveActionResponse,
    summary="Review action proposal",
    description="Facilities or Production review of an action proposal (Approve or Reject with reason).",
)
def review_action_endpoint(
    action_id: str,
    payload: ReviewActionRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> CorrectiveActionResponse:
    auth_caller = extract_authenticated_caller(request)
    try:
        action = review_corrective_action(
            session,
            action_id,
            payload,
            caller_attribution=payload.caller_attribution,
            auth_caller=auth_caller,
        )
        detail = get_corrective_action(session, action.action_id) or action
        return CorrectiveActionResponse(**_action_to_dict(detail))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@actions_router.post(
    "/{action_id}/implement",
    response_model=CorrectiveActionResponse,
    summary="Record physical implementation",
    description="Record physical implementation of operational change. Enforces implementation timestamp before outcome evaluation.",
)
def implement_action_endpoint(
    action_id: str,
    payload: RecordImplementationRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> CorrectiveActionResponse:
    auth_caller = extract_authenticated_caller(request)
    try:
        action = record_action_implementation(
            session,
            action_id,
            payload,
            caller_attribution=payload.caller_attribution,
            auth_caller=auth_caller,
        )
        detail = get_corrective_action(session, action.action_id) or action
        return CorrectiveActionResponse(**_action_to_dict(detail))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@actions_router.post(
    "/{action_id}/request-assessment",
    response_model=CorrectiveActionResponse,
    summary="Request outcome assessment",
    description="Request outcome verification assessment for an implemented action with approved M&V plan.",
)
def request_assessment_endpoint(
    action_id: str,
    payload: RequestAssessmentRequest,
    session: Session = Depends(get_db_session),
) -> CorrectiveActionResponse:
    try:
        action = request_action_assessment(session, action_id, payload, caller_attribution=payload.caller_attribution)
        detail = get_corrective_action(session, action.action_id) or action
        return CorrectiveActionResponse(**_action_to_dict(detail))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -------------------------------------------------------------------------
# Phase 5: Measurement & Verification Plan Endpoints
# -------------------------------------------------------------------------

@actions_router.get(
    "/{action_id}/plan",
    response_model=MeasurementPlanResponse,
    summary="Get measurement plan",
    description="Retrieve the latest M&V measurement plan linked to a corrective action.",
)
def get_action_plan_endpoint(
    action_id: str,
    session: Session = Depends(get_db_session),
) -> MeasurementPlanResponse:
    action = get_corrective_action(session, action_id)
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Corrective action '{action_id}' not found.",
        )
    plan = get_measurement_plan_for_action(session, action_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No measurement plan found for action '{action_id}'.",
        )
    return plan_to_response(plan)


@actions_router.post(
    "/{action_id}/plan",
    response_model=MeasurementPlanResponse,
    summary="Create measurement plan",
    description="Capture M&V measurement plan before implementing change. Flags retrospective plans explicitly.",
)
def create_action_plan_endpoint(
    action_id: str,
    payload: CreateMeasurementPlanRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> MeasurementPlanResponse:
    auth_caller = extract_authenticated_caller(request)
    try:
        plan = create_measurement_plan(
            session,
            action_id,
            payload,
            caller_attribution=payload.created_by,
            auth_caller=auth_caller,
        )
        return plan_to_response(plan)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@actions_router.put(
    "/{action_id}/plan",
    response_model=MeasurementPlanResponse,
    summary="Amend measurement plan",
    description="Amend an existing M&V plan. Increments version and records author and justification reason.",
)
def amend_action_plan_endpoint(
    action_id: str,
    payload: AmendMeasurementPlanRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> MeasurementPlanResponse:
    auth_caller = extract_authenticated_caller(request)
    plan = get_measurement_plan_for_action(session, action_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existing measurement plan found for action '{action_id}' to amend.",
        )
    try:
        amended = amend_measurement_plan(
            session,
            plan.plan_id,
            payload,
            caller_attribution=payload.author,
            auth_caller=auth_caller,
        )
        return plan_to_response(amended)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@actions_router.post(
    "/{action_id}/plan/approve",
    response_model=MeasurementPlanResponse,
    summary="Approve and freeze measurement plan",
    description="Approve and freeze M&V plan prior to physical implementation. Freezing ensures retrospective tamper-resistance.",
)
def approve_action_plan_endpoint(
    action_id: str,
    payload: ApproveMeasurementPlanRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> MeasurementPlanResponse:
    auth_caller = extract_authenticated_caller(request)
    plan = get_measurement_plan_for_action(session, action_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No measurement plan found for action '{action_id}' to approve.",
        )
    try:
        approved = approve_measurement_plan(
            session,
            plan.plan_id,
            payload,
            caller_attribution=payload.reviewer,
            auth_caller=auth_caller,
        )
        return plan_to_response(approved)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -------------------------------------------------------------------------
# Phase 5: Deterministic Before/After Assessment & Reviewer Sign-Off
# -------------------------------------------------------------------------

@actions_router.get(
    "/{action_id}/assessment",
    response_model=InterventionComparisonResponse,
    summary="Evaluate outcome assessment",
    description="Calculate side-by-side deterministic metrics, guardrail outcomes, and separated savings quantities.",
)
def get_action_assessment_endpoint(
    action_id: str,
    session: Session = Depends(get_db_session),
) -> InterventionComparisonResponse:
    try:
        comp, _ = evaluate_and_record_assessment(session, action_id)
        return comp
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@actions_router.post(
    "/{action_id}/assessment/explain-ai",
    response_model=AssessmentAIExplanationResponse,
    summary="Explain action assessment with AI Assistant",
    description="Synthesize assessment outcome, dual-boundary net energy accounting, production protection status, and ledger eligibility.",
)
@recommendations_router.post(
    "/assessments/{assessment_id}/explain-ai",
    response_model=AssessmentAIExplanationResponse,
    summary="Explain assessment with AI Assistant",
    description="Synthesize assessment outcome, dual-boundary net energy accounting, production protection status, and ledger eligibility.",
)
def explain_assessment_endpoint(
    assessment_id: Optional[str] = None,
    action_id: Optional[str] = None,
    caller_attribution: Optional[str] = Query(None, description="Optional caller label"),
    session: Session = Depends(get_db_session),
) -> AssessmentAIExplanationResponse:
    target_asm_id = assessment_id
    if not target_asm_id and action_id:
        stmt = (
            select(InterventionAssessment.assessment_id)
            .where(InterventionAssessment.action_id == action_id)
            .order_by(desc(InterventionAssessment.assessment_revision))
            .limit(1)
        )
        target_asm_id = session.execute(stmt).scalar()
        if not target_asm_id:
            try:
                _, asm = evaluate_and_record_assessment(session, action_id, evaluated_by=caller_attribution)
                target_asm_id = asm.assessment_id
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No assessment found or evaluable for action '{action_id}': {e}")
    if not target_asm_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assessment ID or Action ID required.")
    try:
        res = explain_assessment_with_ai(session, target_asm_id, caller_attribution)
        return AssessmentAIExplanationResponse(**res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def extract_authenticated_caller(request: Request) -> Dict[str, Any]:
    """
    Extract authenticated operational caller identity, role, and plant scope
    from the application's trusted server-side authentication mechanism.

    Derives operational identity, roles and plant permissions from server-side state.
    A missing plant scope must not grant access to every plant.
    If the repository has no trusted operational authentication mechanism configured,
    operational identity is marked unavailable, making operational verification unavailable.
    Payload names and headers are treated strictly as unverified display labels.
    """
    # Check for server-side authenticated user session attached to request state
    session_user = getattr(request.state, "user", None)
    if session_user and getattr(session_user, "is_authenticated", False):
        user_id = getattr(session_user, "user_id", None) or getattr(session_user, "username", None)
        role = getattr(session_user, "role", None)
        plant_scope = getattr(session_user, "plant_scope", None)
        # Validate plant scope: missing or wildcard must NOT grant access to every plant
        if plant_scope in ("*", "ALL", "") or not plant_scope:
            clean_plant = None
        else:
            clean_plant = str(plant_scope).strip()

        return {
            "is_authenticated": True,
            "operational_auth_available": True,
            "user_id": str(user_id).strip() if user_id else None,
            "role": str(role).strip().upper() if role else None,
            "plant_scope": clean_plant,
            "auth_mechanism": "SERVER_SESSION",
        }

    # Repository has no configured trusted operational authentication mechanism
    return {
        "is_authenticated": False,
        "operational_auth_available": False,
        "user_id": None,
        "role": None,
        "plant_scope": None,
        "auth_mechanism": "NONE_CONFIGURED",
    }


@actions_router.post(
    "/{action_id}/assessment/sign-off",
    response_model=InterventionAssessmentResponse,
    summary="Sign off on verified assessment",
    description="Authorized reviewer governance decision on an assessment (APPROVED_VERIFIED, REJECTED, REQUEST_REANALYSIS). Derives reviewer from authenticated session; excludes unauthenticated/demo calls from verified totals.",
)
def sign_off_assessment_endpoint(
    action_id: str,
    payload: AssessmentSignOffRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> InterventionAssessmentResponse:
    auth_caller = extract_authenticated_caller(request)

    # Find latest assessment for action
    stmt = (
        select(InterventionAssessment)
        .where(InterventionAssessment.action_id == action_id)
        .order_by(desc(InterventionAssessment.assessment_revision))
        .limit(1)
    )
    asm = session.execute(stmt).scalar_one_or_none()
    if not asm:
        # Evaluate first if not yet created
        try:
            _, asm = evaluate_and_record_assessment(session, action_id, evaluated_by=payload.reviewer)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    try:
        signed_asm = sign_off_assessment(
            session=session,
            assessment_id=asm.assessment_id,
            req=payload,
            caller_attribution=payload.reviewer,
            auth_caller=auth_caller,
        )
        return InterventionAssessmentResponse(
            id=signed_asm.id,
            assessment_id=signed_asm.assessment_id,
            action_id=signed_asm.action_id,
            plan_id=signed_asm.plan_id,
            plan_version=signed_asm.plan_version,
            assessment_revision=signed_asm.assessment_revision,
            is_stale_flag=signed_asm.is_stale_flag,
            stale_reason=signed_asm.stale_reason,
            evaluated_at=signed_asm.evaluated_at.isoformat(),
            evaluated_by=signed_asm.evaluated_by,
            calculation_method=signed_asm.calculation_method,
            baseline_kwh=signed_asm.baseline_kwh,
            baseline_cost_inr=signed_asm.baseline_cost_inr,
            baseline_actual_units=signed_asm.baseline_actual_units,
            baseline_good_units=signed_asm.baseline_good_units,
            baseline_reject_units=signed_asm.baseline_reject_units,
            baseline_downtime_min=signed_asm.baseline_downtime_min,
            baseline_operating_hours=signed_asm.baseline_operating_hours,
            baseline_coverage_pct=signed_asm.baseline_coverage_pct,
            baseline_kwh_per_good_unit=signed_asm.baseline_kwh_per_good_unit,
            baseline_cost_per_good_unit=signed_asm.baseline_cost_per_good_unit,
            baseline_yield_pct=signed_asm.baseline_yield_pct,
            post_kwh=signed_asm.post_kwh,
            post_cost_inr=signed_asm.post_cost_inr,
            post_actual_units=signed_asm.post_actual_units,
            post_good_units=signed_asm.post_good_units,
            post_reject_units=signed_asm.post_reject_units,
            post_downtime_min=signed_asm.post_downtime_min,
            post_operating_hours=signed_asm.post_operating_hours,
            post_coverage_pct=signed_asm.post_coverage_pct,
            post_kwh_per_good_unit=signed_asm.post_kwh_per_good_unit,
            post_cost_per_good_unit=signed_asm.post_cost_per_good_unit,
            post_yield_pct=signed_asm.post_yield_pct,
            kwh_change_abs=signed_asm.kwh_change_abs,
            kwh_change_pct=signed_asm.kwh_change_pct,
            intensity_change_abs=signed_asm.intensity_change_abs,
            intensity_change_pct=signed_asm.intensity_change_pct,
            cost_intensity_change_abs=signed_asm.cost_intensity_change_abs,
            cost_intensity_change_pct=signed_asm.cost_intensity_change_pct,
            common_rate_cost_baseline_inr=signed_asm.common_rate_cost_baseline_inr,
            common_rate_cost_post_inr=signed_asm.common_rate_cost_post_inr,
            common_rate_factor_inr_per_kwh=signed_asm.common_rate_factor_inr_per_kwh,
            common_rate_factor_version=signed_asm.common_rate_factor_version,
            output_guardrail_met=signed_asm.output_guardrail_met,
            quality_guardrail_met=signed_asm.quality_guardrail_met,
            downtime_guardrail_met=signed_asm.downtime_guardrail_met,
            objective_outcome=signed_asm.objective_outcome,
            electricity_savings_kwh=signed_asm.electricity_savings_kwh,
            monetary_savings_basis=signed_asm.monetary_savings_basis,
            avoided_cost_inr=signed_asm.avoided_cost_inr,
            savings_claim_status=signed_asm.savings_claim_status,
            savings_claim_description=signed_asm.savings_claim_description,
            status_reason=signed_asm.status_reason,
            overlap_flag=signed_asm.overlap_flag,
            overlap_details=signed_asm.overlap_details,
            signed_off_by=signed_asm.signed_off_by,
            signed_off_at=signed_asm.signed_off_at.isoformat() if signed_asm.signed_off_at else None,
            review_decision=signed_asm.review_decision,
            review_notes=signed_asm.review_notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
