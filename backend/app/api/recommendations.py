"""Operational Recommendations, Corrective Actions, and Audit Trail API endpoints."""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.recommendations import (
    ActionAuditLog,
    CorrectiveAction,
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
from app.services.recommendation_service import (
    create_corrective_action,
    create_recommendation,
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
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
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
        recs = generate_recommendations_from_finding(
            session=session,
            finding_id=finding_id,
            caller_attribution=caller_attribution,
        )
        summaries = [RecommendationSummary(**_recommendation_to_summary_dict(r)) for r in recs]
        return GenerateRecommendationsResponse(
            generated_count=len(recs),
            recommendations=summaries,
            message=f"Generated {len(recs)} recommendation(s) for finding '{finding_id}'.",
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
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
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
