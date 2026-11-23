"""
Intervention Management & Savings Ledger Service (Phase 5).

Provides deterministic lifecycle state machines, measurement plan governance,
and idempotent persistence for the Intervention and Savings Ledger.

Workflows:
1. Review Action Proposal: Approve or reject proposal with engineering justification.
2. Measurement Plan Governance: Create, amend, freeze, and version M&V plans.
3. Record Implementation: Enforces actual implementation timestamp before outcome evaluation.
4. Request & Evaluate Assessment: Deterministic before/after comparison with guardrails and savings separation.
5. Sign-Off & Savings Ledger: Reviewer governance, overlap detection, and idempotent audit trail.
"""

from datetime import datetime, timezone, timedelta
import json
import logging
import uuid
import zoneinfo
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.models.findings import FindingOccurrence, OperationalFinding
from app.models.recommendations import (
    ActionAuditLog,
    CorrectiveAction,
    InterventionAssessment,
    InterventionPlan,
    OperationalRecommendation,
)
from app.schemas.interventions import (
    AmendMeasurementPlanRequest,
    ApproveMeasurementPlanRequest,
    AssessmentSignOffRequest,
    CreateMeasurementPlanRequest,
    InterventionAssessmentResponse,
    InterventionComparisonResponse,
    MeasurementPlanResponse,
    RecordImplementationRequest,
    RequestAssessmentRequest,
    ReviewActionRequest,
    SavingsLedgerListResponse,
)
from app.services.intervention_comparison_service import (
    COMMON_RATE_FACTOR_VERSION,
    COMMON_RATE_TARIFF_INR_PER_KWH,
    execute_deterministic_comparison,
)
from app.services.recommendation_service import (
    build_audit_metadata,
    generate_audit_id,
    get_corrective_action,
)

logger = logging.getLogger(__name__)


def generate_plan_id(plant_id: str) -> str:
    """Generate a clean, stable measurement plan identifier."""
    clean_plant = plant_id.replace(" ", "-").replace("_", "-").upper()
    random_part = uuid.uuid4().hex[:10].upper()
    return f"PLAN-{clean_plant}-{random_part}"


def generate_assessment_id(action_id: str) -> str:
    """Generate a clean, stable assessment identifier."""
    random_part = uuid.uuid4().hex[:10].upper()
    return f"ASM-{action_id}-{random_part}"


# -------------------------------------------------------------------------
# 1. Action Proposal Review & Implementation Lifecycle
# -------------------------------------------------------------------------

def review_corrective_action(
    session: Session,
    action_id: str,
    req: ReviewActionRequest,
    caller_attribution: Optional[str] = None,
    auth_caller: Optional[Dict[str, Any]] = None,
) -> CorrectiveAction:
    """
    Review an operational action proposal (Approve or Reject).
    Records reviewer, timestamp, decision, and engineering reason in audit log.
    Derives operational identity from authenticated session; if unavailable,
    marks review as demo/unauthenticated.
    """
    action = get_corrective_action(session, action_id)
    if not action:
        raise ValueError(f"Corrective action '{action_id}' not found.")

    decision_norm = req.decision.strip().upper()
    if decision_norm not in ("APPROVE", "REJECT"):
        raise ValueError("Review decision must be 'APPROVE' or 'REJECT'.")

    # Enforce role and plant scope when trusted operational auth is configured
    if auth_caller and auth_caller.get("operational_auth_available"):
        user_role = auth_caller.get("role")
        user_plant = auth_caller.get("plant_scope")
        if user_role not in AUTHORIZED_REVIEW_ROLES:
            raise ValueError(
                f"Operational review denied: Role '{user_role}' is not in authorized operational review roles "
                f"({', '.join(sorted(AUTHORIZED_REVIEW_ROLES))})."
            )
        if not user_plant or (action.plant_id and user_plant != action.plant_id):
            raise ValueError(
                f"Operational review denied: Authenticated plant scope '{user_plant or 'NONE'}' does not match "
                f"action plant '{action.plant_id}'. Missing or mismatched plant scope denies operational transitions."
            )

    now = datetime.utcnow()
    old_review_status = action.review_status
    new_review_status = "APPROVED" if decision_norm == "APPROVE" else "REJECTED"
    new_action_status = "APPROVED" if decision_norm == "APPROVE" else "REJECTED"

    is_authenticated = bool(auth_caller and auth_caller.get("is_authenticated"))
    if is_authenticated and auth_caller.get("user_id"):
        reviewer_label = f"{auth_caller.get('user_id')} ({auth_caller.get('role', 'OPERATIONS')})"
    else:
        reviewer_label = f"{req.reviewer.strip()} [Demo / Unauthenticated]"

    action.review_status = new_review_status
    action.status = new_action_status
    action.reviewed_by = reviewer_label
    action.reviewed_at = now
    action.review_decision_reason = req.reason.strip()
    action.updated_at = now

    audit = ActionAuditLog(
        audit_id=generate_audit_id("ACT"),
        action_id=action.action_id,
        recommendation_id=action.recommendation_id,
        entity_id=action.action_id,
        action="REVIEWED",
        from_status=old_review_status,
        to_status=new_review_status,
        performed_at=now,
        comment=f"Action proposal {new_review_status.lower()} by {reviewer_label}. Reason: {req.reason.strip()}",
        changed_fields_json=json.dumps({
            "review_status": {"old": old_review_status, "new": new_review_status},
            "status": {"old": action.status, "new": new_action_status},
            "reviewed_by": {"old": None, "new": reviewer_label},
            "review_decision_reason": {"old": None, "new": req.reason.strip()},
        }, default=str),
        audit_metadata_json=build_audit_metadata(
            caller_attribution=caller_attribution or req.caller_attribution,
            source="OPERATOR_REVIEW",
            details={"decision": decision_norm, "action_id": action.action_id},
        ),
    )

    try:
        with session.begin_nested():
            session.add(action)
            session.add(audit)
            session.flush()
        session.commit()
        session.refresh(action)
        return action
    except Exception:
        session.rollback()
        raise


def record_action_implementation(
    session: Session,
    action_id: str,
    req: RecordImplementationRequest,
    caller_attribution: Optional[str] = None,
    auth_caller: Optional[Dict[str, Any]] = None,
) -> CorrectiveAction:
    """
    Record that an approved operational intervention has been physically implemented.
    Crucial Rule: Requires an actual implementation timestamp before evaluating an outcome.
    Approval alone cannot begin the post-intervention period.
    Derives operational identity from authenticated session; if unavailable,
    marks implementation as demo/unauthenticated.
    """
    action = get_corrective_action(session, action_id)
    if not action:
        raise ValueError(f"Corrective action '{action_id}' not found.")

    if action.review_status != "APPROVED":
        raise ValueError(
            f"Cannot record implementation for action '{action_id}' with review status '{action.review_status}'. "
            f"Action proposal must be APPROVED by Facilities/Production first."
        )

    if not req.implemented_at:
        raise ValueError("An explicit implementation timestamp is required before recording implementation.")

    # Enforce role and plant scope when trusted operational auth is configured
    if auth_caller and auth_caller.get("operational_auth_available"):
        user_role = auth_caller.get("role")
        user_plant = auth_caller.get("plant_scope")
        if user_role not in AUTHORIZED_REVIEW_ROLES:
            raise ValueError(
                f"Recording implementation denied: Role '{user_role}' is not in authorized operational roles "
                f"({', '.join(sorted(AUTHORIZED_REVIEW_ROLES))})."
            )
        if not user_plant or (action.plant_id and user_plant != action.plant_id):
            raise ValueError(
                f"Recording implementation denied: Authenticated plant scope '{user_plant or 'NONE'}' does not match "
                f"action plant '{action.plant_id}'. Missing or mismatched plant scope denies operational transitions."
            )

    now = datetime.utcnow()
    old_status = action.status
    action.status = "IMPLEMENTED"
    action.implemented_at = req.implemented_at

    is_authenticated = bool(auth_caller and auth_caller.get("is_authenticated"))
    if is_authenticated and auth_caller.get("user_id"):
        impl_label = f"{auth_caller.get('user_id')} ({auth_caller.get('role', 'OPERATIONS')})"
    else:
        impl_label = f"{req.implemented_by.strip()} [Demo / Unauthenticated]"

    action.implemented_by = impl_label
    action.implementation_notes = req.implementation_notes.strip()
    action.updated_at = now

    details = {"implemented_at": req.implemented_at.isoformat()}
    audit_notes = [f"Notes: {req.implementation_notes.strip()}"]

    # Link maintenance work order or downtime record if supplied
    if req.work_order_id:
        from app.models.source_data import FactMaintenanceWorkOrder
        stmt_wo = select(FactMaintenanceWorkOrder).where(FactMaintenanceWorkOrder.work_order_id == req.work_order_id.strip())
        wo = session.execute(stmt_wo).scalar_one_or_none()
        if wo:
            if action.plant_id and wo.plant_id != action.plant_id:
                raise ValueError(
                    f"Maintenance work order '{req.work_order_id}' belongs to plant '{wo.plant_id}', "
                    f"mismatched with action plant '{action.plant_id}'."
                )
            details["work_order_id"] = wo.work_order_id
            audit_notes.append(
                f"Linked Work Order: {wo.work_order_id} ({wo.maintenance_type} on {wo.machine_id}). "
                f"Note: Work order corroborates physical maintenance activity but does not certify an energy reduction."
            )
        else:
            raise ValueError(f"Maintenance work order '{req.work_order_id}' not found in CMMS master records.")

    if req.downtime_event_id:
        from app.models.source_data import FactDowntimeEvent
        stmt_dt = select(FactDowntimeEvent).where(FactDowntimeEvent.downtime_id == req.downtime_event_id.strip())
        dt = session.execute(stmt_dt).scalar_one_or_none()
        if dt:
            if action.plant_id and dt.plant_id != action.plant_id:
                raise ValueError(
                    f"Downtime event '{req.downtime_event_id}' belongs to plant '{dt.plant_id}', "
                    f"mismatched with action plant '{action.plant_id}'."
                )
            details["downtime_event_id"] = dt.downtime_id
            audit_notes.append(f"Linked Downtime Event: {dt.downtime_id} ({dt.reason_code}, {dt.duration_min} min).")
        else:
            raise ValueError(f"Downtime event '{req.downtime_event_id}' not found in production downtime logs.")

    comment_body = (
        f"Operational implementation recorded by {impl_label} at "
        f"{req.implemented_at.isoformat()}. " + " | ".join(audit_notes)
    )

    audit = ActionAuditLog(
        audit_id=generate_audit_id("ACT"),
        action_id=action.action_id,
        recommendation_id=action.recommendation_id,
        entity_id=action.action_id,
        action="IMPLEMENTED",
        from_status=old_status,
        to_status="IMPLEMENTED",
        performed_at=now,
        comment=comment_body,
        changed_fields_json=json.dumps({
            "status": {"old": old_status, "new": "IMPLEMENTED"},
            "implemented_at": {"old": None, "new": req.implemented_at.isoformat()},
            "implemented_by": {"old": None, "new": impl_label},
            "implementation_notes": {"old": None, "new": req.implementation_notes.strip()},
            "work_order_id": {"old": None, "new": details.get("work_order_id")},
            "downtime_event_id": {"old": None, "new": details.get("downtime_event_id")},
        }, default=str),
        audit_metadata_json=build_audit_metadata(
            caller_attribution=caller_attribution or req.caller_attribution,
            source="OPERATOR_IMPLEMENTATION",
            details=details,
        ),
    )

    try:
        with session.begin_nested():
            session.add(action)
            session.add(audit)
            session.flush()
        session.commit()
        session.refresh(action)
        return action
    except Exception:
        session.rollback()
        raise


def request_action_assessment(
    session: Session,
    action_id: str,
    req: RequestAssessmentRequest,
    caller_attribution: Optional[str] = None,
) -> CorrectiveAction:
    """
    Request an outcome assessment for an implemented action.
    Validates that implementation has occurred and an approved measurement plan exists.
    """
    action = get_corrective_action(session, action_id)
    if not action:
        raise ValueError(f"Corrective action '{action_id}' not found.")

    if not action.implemented_at:
        raise ValueError(
            f"Cannot request outcome assessment for action '{action_id}'. "
            f"Actual physical implementation has not been recorded."
        )

    # Check for linked measurement plan
    plan = get_measurement_plan_for_action(session, action_id)
    if not plan:
        raise ValueError(
            f"Cannot request outcome assessment for action '{action_id}'. "
            f"A measurement and verification plan must be captured and approved first."
        )

    now = datetime.utcnow()
    old_status = action.status
    action.status = "ASSESSMENT_REQUESTED"
    action.assessment_status = "REQUESTED"
    action.updated_at = now

    audit = ActionAuditLog(
        audit_id=generate_audit_id("ACT"),
        action_id=action.action_id,
        recommendation_id=action.recommendation_id,
        entity_id=action.action_id,
        action="ASSESSMENT_REQUESTED",
        from_status=old_status,
        to_status="ASSESSMENT_REQUESTED",
        performed_at=now,
        comment=f"Outcome assessment requested by {req.requested_by.strip()}. Notes: {req.notes or 'None'}",
        changed_fields_json=json.dumps({
            "status": {"old": old_status, "new": "ASSESSMENT_REQUESTED"},
            "assessment_status": {"old": "NONE", "new": "REQUESTED"},
        }, default=str),
        audit_metadata_json=build_audit_metadata(
            caller_attribution=caller_attribution or req.caller_attribution,
            source="OPERATOR_ASSESSMENT_REQUEST",
            details={"requested_by": req.requested_by.strip(), "plan_id": plan.plan_id},
        ),
    )

    try:
        with session.begin_nested():
            session.add(action)
            session.add(audit)
            session.flush()
        session.commit()
        session.refresh(action)
        return action
    except Exception:
        session.rollback()
        raise


# -------------------------------------------------------------------------
# 2. Measurement Plan Governance
# -------------------------------------------------------------------------

def get_measurement_plan_for_action(session: Session, action_id: str) -> Optional[InterventionPlan]:
    """Retrieve the latest active measurement plan for an action."""
    stmt = (
        select(InterventionPlan)
        .where(InterventionPlan.action_id == action_id)
        .order_by(desc(InterventionPlan.version))
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


PLANT_TIMEZONES: Dict[str, str] = {
    "IN-TN-01": "Asia/Kolkata",
    "IN-KA-01": "Asia/Kolkata",
}


def get_plant_tz(plant_id: str):
    tz_name = PLANT_TIMEZONES.get(plant_id, "Asia/Kolkata")
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return timezone(timedelta(hours=5, minutes=30))


def parse_and_normalize_plant_datetime(
    val: Any,
    plant_id: str,
    field_name: str,
) -> Tuple[datetime, datetime]:
    """
    Parses a datetime input (str or datetime) and normalizes it to:
    (naive_plant_dt, aware_utc_instant)
    - naive_plant_dt: Naive datetime preserving the intended local plant hour for database storage & hourly queries.
    - aware_utc_instant: Timezone-aware UTC instant for consistent temporal comparisons.
    """
    if val is None:
        raise ValueError(f"Missing required date field '{field_name}'.")

    if isinstance(val, str):
        clean_str = val.strip()
        if not clean_str:
            raise ValueError(f"Missing required date field '{field_name}'.")
        try:
            dt = datetime.fromisoformat(clean_str.replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"Invalid date format for '{field_name}': {str(e)}")
    elif isinstance(val, datetime):
        dt = val
    else:
        raise ValueError(f"Invalid date type for '{field_name}'.")

    plant_tz = get_plant_tz(plant_id)
    if dt.tzinfo is None:
        # Naive input: represents local plant time
        aware_plant = dt.replace(tzinfo=plant_tz)
        aware_utc = aware_plant.astimezone(timezone.utc)
        naive_plant = dt
    else:
        # Aware input: convert to configured plant timezone and UTC
        aware_plant = dt.astimezone(plant_tz)
        aware_utc = dt.astimezone(timezone.utc)
        naive_plant = aware_plant.replace(tzinfo=None)

    return naive_plant, aware_utc


def create_measurement_plan(
    session: Session,
    action_id: str,
    req: CreateMeasurementPlanRequest,
    caller_attribution: Optional[str] = None,
    auth_caller: Optional[Dict[str, Any]] = None,
) -> InterventionPlan:
    """
    Create a new M&V measurement plan before implementation.
    Validates boundary, windows, and explicit retrospective tagging.
    """
    action = get_corrective_action(session, action_id)
    if not action:
        raise ValueError(f"Corrective action '{action_id}' not found.")

    # Enforce role and plant scope when trusted operational auth is configured
    if auth_caller and auth_caller.get("operational_auth_available"):
        user_role = auth_caller.get("role")
        user_plant = auth_caller.get("plant_scope")
        if user_role not in AUTHORIZED_REVIEW_ROLES:
            raise ValueError(
                f"Measurement plan creation denied: Role '{user_role}' is not in authorized operational roles "
                f"({', '.join(sorted(AUTHORIZED_REVIEW_ROLES))})."
            )
        if not user_plant or (req.plant_id and user_plant != req.plant_id):
            raise ValueError(
                f"Measurement plan creation denied: Authenticated plant scope '{user_plant or 'NONE'}' does not match "
                f"plan plant '{req.plant_id}'. Missing or mismatched plant scope denies operational transitions."
            )

    existing_plan = get_measurement_plan_for_action(session, action_id)
    if existing_plan:
        raise ValueError(
            f"Measurement plan already exists for action '{action_id}' (Plan: {existing_plan.plan_id} v{existing_plan.version}). "
            f"Use amend_measurement_plan to create a versioned amendment."
        )

    plant_id = req.plant_id.strip()

    # Parse and normalize inputs in the configured plant timezone
    naive_b_start, _ = parse_and_normalize_plant_datetime(req.baseline_start, plant_id, "baseline_start")
    naive_b_end, _ = parse_and_normalize_plant_datetime(req.baseline_end, plant_id, "baseline_end")
    naive_p_start, _ = parse_and_normalize_plant_datetime(req.post_start, plant_id, "post_start")
    naive_p_end, post_end_utc = parse_and_normalize_plant_datetime(req.post_end, plant_id, "post_end")

    naive_stab_start = None
    if req.stabilization_start:
        naive_stab_start, _ = parse_and_normalize_plant_datetime(req.stabilization_start, plant_id, "stabilization_start")
    naive_stab_end = None
    if req.stabilization_end:
        naive_stab_end, _ = parse_and_normalize_plant_datetime(req.stabilization_end, plant_id, "stabilization_end")

    # Date sanity checks on normalized plant hours
    if naive_b_end <= naive_b_start:
        raise ValueError("Baseline end date must be after baseline start date.")
    if naive_p_end <= naive_p_start:
        raise ValueError("Post-intervention end date must be after post-intervention start date.")

    # Compare instants consistently using timezone-aware UTC
    now_utc = datetime.now(timezone.utc)
    # Retrospective detection: If action was already implemented, or post window has passed, enforce retrospective
    action_already_implemented = bool(action and action.implemented_at)
    if action_already_implemented:
        is_retrospective = True
    elif req.is_retrospective is not None:
        is_retrospective = bool(req.is_retrospective)
    else:
        is_retrospective = (post_end_utc <= now_utc)

    merged_operating_conditions = dict(req.operating_conditions or {})
    if req.guardrail_output_reason:
        merged_operating_conditions["guardrail_output_reason"] = req.guardrail_output_reason.strip()
    if req.guardrail_reject_reason:
        merged_operating_conditions["guardrail_reject_reason"] = req.guardrail_reject_reason.strip()
    if req.guardrail_downtime_reason:
        merged_operating_conditions["guardrail_downtime_reason"] = req.guardrail_downtime_reason.strip()
    if req.guardrail_restart_max_min is not None:
        merged_operating_conditions["guardrail_restart_max_min"] = req.guardrail_restart_max_min
        merged_operating_conditions["guardrail_restart_unit"] = req.guardrail_restart_unit or "minutes"
        merged_operating_conditions["guardrail_restart_direction"] = req.guardrail_restart_direction or "LESS_OR_EQUAL"
        merged_operating_conditions["guardrail_restart_source"] = req.guardrail_restart_source or "Target Line Availability / Restart Envelope"
        if req.guardrail_restart_reason:
            merged_operating_conditions["guardrail_restart_reason"] = req.guardrail_restart_reason.strip()
    if req.comparison_method:
        merged_operating_conditions["comparison_method"] = req.comparison_method.strip()

    # Dual Boundary Architecture (Requirement Item 1)
    if req.has_dual_boundary or req.comparison_method in ("DUAL_STOPPAGE_AND_RESTART", "DUAL_BOUNDARY"):
        merged_operating_conditions["has_dual_boundary"] = True
        merged_operating_conditions["boundary_type"] = req.boundary_type or "DUAL_STOPPAGE_AND_RESTART"
        if req.boundary_a_config:
            merged_operating_conditions["boundary_a"] = req.boundary_a_config
        if req.boundary_b_config:
            merged_operating_conditions["boundary_b"] = req.boundary_b_config

    plan_id = generate_plan_id(req.plant_id)
    plan = InterventionPlan(
        plan_id=plan_id,
        action_id=action.action_id,
        version=1,
        is_frozen=False,
        is_retrospective=is_retrospective,
        intended_change=req.intended_change.strip(),
        implementation_owner=req.implementation_owner.strip(),
        plant_id=req.plant_id.strip(),
        process_or_line=req.process_or_line.strip(),
        eligible_meters_json=json.dumps(req.eligible_meters),
        production_denominator=req.production_denominator.strip(),
        production_unit=req.production_unit.strip(),
        baseline_start=naive_b_start,
        baseline_end=naive_b_end,
        post_start=naive_p_start,
        post_end=naive_p_end,
        stabilization_start=naive_stab_start,
        stabilization_end=naive_stab_end,
        stabilization_exclusion_reason=req.stabilization_exclusion_reason.strip() if req.stabilization_exclusion_reason else None,
        restart_exclusion_reason=req.restart_exclusion_reason.strip() if req.restart_exclusion_reason else None,
        guardrail_output_min=req.guardrail_output_min,
        guardrail_output_unit=req.guardrail_output_unit,
        guardrail_output_direction=req.guardrail_output_direction,
        guardrail_output_source=req.guardrail_output_source,
        guardrail_reject_max=req.guardrail_reject_max,
        guardrail_reject_unit=req.guardrail_reject_unit,
        guardrail_reject_direction=req.guardrail_reject_direction,
        guardrail_reject_source=req.guardrail_reject_source,
        guardrail_downtime_max_min=req.guardrail_downtime_max_min,
        guardrail_downtime_unit=req.guardrail_downtime_unit,
        guardrail_downtime_direction=req.guardrail_downtime_direction,
        guardrail_downtime_source=req.guardrail_downtime_source,
        min_coverage_pct=req.min_coverage_pct,
        comparability_rules_json=json.dumps(req.comparability_rules) if req.comparability_rules else None,
        success_criterion=req.success_criterion.strip(),
        success_criterion_metric=req.success_criterion_metric,
        success_criterion_threshold_pct=req.success_criterion_threshold_pct,
        operating_conditions_json=json.dumps(merged_operating_conditions) if merged_operating_conditions else None,
        created_by=req.created_by or caller_attribution,
        created_at=now_utc,
    )

    action.measurement_plan_id = plan_id
    action.updated_at = now_utc

    try:
        with session.begin_nested():
            session.add(plan)
            session.add(action)
            session.flush()
        session.commit()
        session.refresh(plan)
        return plan
    except Exception:
        session.rollback()
        raise


def approve_measurement_plan(
    session: Session,
    plan_id: str,
    req: ApproveMeasurementPlanRequest,
    caller_attribution: Optional[str] = None,
    auth_caller: Optional[Dict[str, Any]] = None,
) -> InterventionPlan:
    """
    Approve and freeze a measurement plan before physical implementation.
    A frozen plan cannot be modified in place; subsequent changes require an amendment.
    Derives operational identity from authenticated session; if unavailable,
    marks approval as demo/unauthenticated.
    """
    stmt = select(InterventionPlan).where(InterventionPlan.plan_id == plan_id)
    plan = session.execute(stmt).scalar_one_or_none()
    if not plan:
        raise ValueError(f"Measurement plan '{plan_id}' not found.")

    # Enforce role and plant scope when trusted operational auth is configured
    if auth_caller and auth_caller.get("operational_auth_available"):
        user_role = auth_caller.get("role")
        user_plant = auth_caller.get("plant_scope")
        if user_role not in AUTHORIZED_REVIEW_ROLES:
            raise ValueError(
                f"Measurement plan approval denied: Role '{user_role}' is not in authorized operational roles "
                f"({', '.join(sorted(AUTHORIZED_REVIEW_ROLES))})."
            )
        if not user_plant or (plan.plant_id and user_plant != plan.plant_id):
            raise ValueError(
                f"Measurement plan approval denied: Authenticated plant scope '{user_plant or 'NONE'}' does not match "
                f"plan plant '{plan.plant_id}'. Missing or mismatched plant scope denies operational transitions."
            )

    if plan.is_frozen:
        return plan  # Already frozen and approved

    now = datetime.utcnow()
    plan.is_frozen = True

    action = get_corrective_action(session, plan.action_id)
    if action and action.implemented_at:
        # Implementation was already recorded before plan was approved: enforce retrospective
        plan.is_retrospective = True

    is_authenticated = bool(auth_caller and auth_caller.get("is_authenticated"))
    if is_authenticated and auth_caller.get("user_id"):
        approver_label = f"{auth_caller.get('user_id')} ({auth_caller.get('role', 'OPERATIONS')})"
    else:
        approver_label = f"{req.reviewer.strip()} [Demo / Unauthenticated]"

    plan.approved_by = approver_label
    plan.approved_at = now

    audit = None
    if action:
        audit = ActionAuditLog(
            audit_id=generate_audit_id("ACT"),
            action_id=action.action_id,
            recommendation_id=action.recommendation_id,
            entity_id=plan.plan_id,
            action="PLAN_APPROVED_FROZEN",
            from_status=action.status,
            to_status=action.status,
            performed_at=now,
            comment=f"Measurement plan v{plan.version} approved and frozen by {approver_label}.",
            changed_fields_json=json.dumps({
                "plan_id": plan.plan_id,
                "version": plan.version,
                "is_frozen": True,
                "approved_at": now.isoformat(),
                "approved_by": approver_label,
            }, default=str),
            audit_metadata_json=build_audit_metadata(
                caller_attribution=caller_attribution or (approver_label if is_authenticated else None),
                source="PLAN_APPROVAL",
                details={"plan_id": plan.plan_id, "version": plan.version, "is_authenticated": is_authenticated},
                is_authenticated=is_authenticated,
            ),
        )

    try:
        with session.begin_nested():
            session.add(plan)
            if audit:
                session.add(audit)
            session.flush()
        session.commit()
        session.refresh(plan)
        return plan
    except Exception:
        session.rollback()
        raise


def amend_measurement_plan(
    session: Session,
    plan_id: str,
    req: AmendMeasurementPlanRequest,
    caller_attribution: Optional[str] = None,
    auth_caller: Optional[Dict[str, Any]] = None,
) -> InterventionPlan:
    """
    Amend an existing measurement plan.
    Increments version number, preserves previous plan version, and records author and reason.
    """
    stmt = (
        select(InterventionPlan)
        .where(InterventionPlan.plan_id == plan_id)
        .order_by(desc(InterventionPlan.version))
        .limit(1)
    )
    current_plan = session.execute(stmt).scalar_one_or_none()
    if not current_plan:
        raise ValueError(f"Measurement plan '{plan_id}' not found.")

    # Enforce role and plant scope when trusted operational auth is configured
    if auth_caller and auth_caller.get("operational_auth_available"):
        user_role = auth_caller.get("role")
        user_plant = auth_caller.get("plant_scope")
        if user_role not in AUTHORIZED_REVIEW_ROLES:
            raise ValueError(
                f"Measurement plan amendment denied: Role '{user_role}' is not in authorized operational roles "
                f"({', '.join(sorted(AUTHORIZED_REVIEW_ROLES))})."
            )
        if not user_plant or (current_plan.plant_id and user_plant != current_plan.plant_id):
            raise ValueError(
                f"Measurement plan amendment denied: Authenticated plant scope '{user_plant or 'NONE'}' does not match "
                f"plan plant '{current_plan.plant_id}'. Missing or mismatched plant scope denies operational transitions."
            )

    d = req.plan_data
    plant_id = d.plant_id.strip()

    # Parse and normalize inputs in the configured plant timezone
    naive_b_start, _ = parse_and_normalize_plant_datetime(d.baseline_start, plant_id, "baseline_start")
    naive_b_end, _ = parse_and_normalize_plant_datetime(d.baseline_end, plant_id, "baseline_end")
    naive_p_start, _ = parse_and_normalize_plant_datetime(d.post_start, plant_id, "post_start")
    naive_p_end, post_end_utc = parse_and_normalize_plant_datetime(d.post_end, plant_id, "post_end")

    naive_stab_start = None
    if d.stabilization_start:
        naive_stab_start, _ = parse_and_normalize_plant_datetime(d.stabilization_start, plant_id, "stabilization_start")
    naive_stab_end = None
    if d.stabilization_end:
        naive_stab_end, _ = parse_and_normalize_plant_datetime(d.stabilization_end, plant_id, "stabilization_end")

    if naive_b_end <= naive_b_start:
        raise ValueError("Baseline end date must be after baseline start date.")
    if naive_p_end <= naive_p_start:
        raise ValueError("Post-intervention end date must be after post-intervention start date.")

    # Compare instants consistently using timezone-aware UTC
    now_utc = datetime.now(timezone.utc)
    action = get_corrective_action(session, current_plan.action_id)
    if action and action.implemented_at:
        # Action is already physically implemented: amending plan afterwards is retrospective by definition
        is_retrospective = True
    elif d.is_retrospective is not None:
        is_retrospective = bool(d.is_retrospective)
    else:
        is_retrospective = (post_end_utc <= now_utc)
    new_version = current_plan.version + 1

    merged_operating_conditions = dict(d.operating_conditions or {})
    if d.guardrail_output_reason:
        merged_operating_conditions["guardrail_output_reason"] = d.guardrail_output_reason.strip()
    if d.guardrail_reject_reason:
        merged_operating_conditions["guardrail_reject_reason"] = d.guardrail_reject_reason.strip()
    if d.guardrail_downtime_reason:
        merged_operating_conditions["guardrail_downtime_reason"] = d.guardrail_downtime_reason.strip()
    if d.guardrail_restart_max_min is not None:
        merged_operating_conditions["guardrail_restart_max_min"] = d.guardrail_restart_max_min
        merged_operating_conditions["guardrail_restart_unit"] = d.guardrail_restart_unit or "minutes"
        merged_operating_conditions["guardrail_restart_direction"] = d.guardrail_restart_direction or "LESS_OR_EQUAL"
        merged_operating_conditions["guardrail_restart_source"] = d.guardrail_restart_source or "Target Line Availability / Restart Envelope"
        if d.guardrail_restart_reason:
            merged_operating_conditions["guardrail_restart_reason"] = d.guardrail_restart_reason.strip()
    if d.comparison_method:
        merged_operating_conditions["comparison_method"] = d.comparison_method.strip()

    # Dual Boundary Architecture (Requirement Item 1)
    if d.has_dual_boundary:
        merged_operating_conditions["has_dual_boundary"] = True
        merged_operating_conditions["boundary_type"] = d.boundary_type or "DUAL_STOPPAGE_AND_RESTART"
        if d.boundary_a_config:
            merged_operating_conditions["boundary_a"] = d.boundary_a_config
        if d.boundary_b_config:
            merged_operating_conditions["boundary_b"] = d.boundary_b_config

    amended_plan = InterventionPlan(
        plan_id=current_plan.plan_id,
        action_id=current_plan.action_id,
        version=new_version,
        is_frozen=False,
        is_retrospective=is_retrospective,
        intended_change=d.intended_change.strip(),
        implementation_owner=d.implementation_owner.strip(),
        plant_id=d.plant_id.strip(),
        process_or_line=d.process_or_line.strip(),
        eligible_meters_json=json.dumps(d.eligible_meters),
        production_denominator=d.production_denominator.strip(),
        production_unit=d.production_unit.strip(),
        baseline_start=naive_b_start,
        baseline_end=naive_b_end,
        post_start=naive_p_start,
        post_end=naive_p_end,
        stabilization_start=naive_stab_start,
        stabilization_end=naive_stab_end,
        stabilization_exclusion_reason=d.stabilization_exclusion_reason.strip() if d.stabilization_exclusion_reason else None,
        restart_exclusion_reason=d.restart_exclusion_reason.strip() if d.restart_exclusion_reason else None,
        guardrail_output_min=d.guardrail_output_min,
        guardrail_output_unit=d.guardrail_output_unit,
        guardrail_output_direction=d.guardrail_output_direction,
        guardrail_output_source=d.guardrail_output_source,
        guardrail_reject_max=d.guardrail_reject_max,
        guardrail_reject_unit=d.guardrail_reject_unit,
        guardrail_reject_direction=d.guardrail_reject_direction,
        guardrail_reject_source=d.guardrail_reject_source,
        guardrail_downtime_max_min=d.guardrail_downtime_max_min,
        guardrail_downtime_unit=d.guardrail_downtime_unit,
        guardrail_downtime_direction=d.guardrail_downtime_direction,
        guardrail_downtime_source=d.guardrail_downtime_source,
        min_coverage_pct=d.min_coverage_pct,
        comparability_rules_json=json.dumps(d.comparability_rules) if d.comparability_rules else None,
        success_criterion=d.success_criterion.strip(),
        success_criterion_metric=d.success_criterion_metric,
        success_criterion_threshold_pct=d.success_criterion_threshold_pct,
        operating_conditions_json=json.dumps(merged_operating_conditions) if merged_operating_conditions else None,
        amendment_reason=req.amendment_reason.strip(),
        created_by=req.author.strip(),
        created_at=now_utc,
    )

    try:
        with session.begin_nested():
            session.add(amended_plan)
            session.flush()
        session.commit()
        session.refresh(amended_plan)
        return amended_plan
    except Exception:
        session.rollback()
        raise


# -------------------------------------------------------------------------
# 3. Assessment & Savings Ledger Persistence (Idempotent)
# -------------------------------------------------------------------------

def evaluate_and_record_assessment(
    session: Session,
    action_id: str,
    evaluated_by: Optional[str] = None,
) -> Tuple[InterventionComparisonResponse, InterventionAssessment]:
    """
    Execute deterministic before/after comparison and persist assessment to the savings ledger.
    Idempotent: If assessment for this plan version already exists and source data hasn't changed,
    returns existing ledger assessment.
    If source data revisions have updated, creates a new assessment revision and flags prior as stale.
    """
    action = get_corrective_action(session, action_id)
    if not action:
        raise ValueError(f"Corrective action '{action_id}' not found.")

    plan = get_measurement_plan_for_action(session, action_id)
    if not plan:
        raise ValueError(f"No measurement plan found for action '{action_id}'.")

    # Execute deterministic comparison
    comp = execute_deterministic_comparison(session, plan, action)

    # Check for existing assessment
    stmt = (
        select(InterventionAssessment)
        .where(
            and_(
                InterventionAssessment.action_id == action_id,
                InterventionAssessment.plan_id == plan.plan_id,
                InterventionAssessment.plan_version == plan.version,
            )
        )
        .order_by(desc(InterventionAssessment.assessment_revision))
        .limit(1)
    )
    existing_asm = session.execute(stmt).scalar_one_or_none()

    now = datetime.utcnow()
    evaluator = evaluated_by or "SYSTEM_ANALYTICS"

    if existing_asm:
        # Deterministic reuse check across 5 inputs:
        # 1. plan.version
        # 2. source revisions (baseline and post)
        # 3. exclusions (stabilization and restart excluded hours)
        # 4. factor versions (tariff/emissions factor versions and rates)
        # 5. calculation method version
        baseline_revs = json.dumps(comp.baseline.source_revisions, sort_keys=True)
        post_revs = json.dumps(comp.post.source_revisions, sort_keys=True)
        factors_match = (
            existing_asm.common_rate_factor_version == comp.common_rate_factor_version
            and abs((existing_asm.common_rate_factor_inr_per_kwh or 0.0) - (comp.common_rate_factor_inr_per_kwh or 0.0)) < 0.001
        )
        plan_matches = existing_asm.plan_version == plan.version
        method_matches = existing_asm.calculation_method == getattr(comp, "calculation_method", "DETERMINISTIC_COMPARISON_V1")
        kwh_matches = (
            abs(existing_asm.baseline_kwh - comp.baseline.kwh) < 0.01
            and abs(existing_asm.post_kwh - comp.post.kwh) < 0.01
        )

        if (
            not existing_asm.is_stale_flag
            and existing_asm.baseline_source_revisions_json == baseline_revs
            and existing_asm.post_source_revisions_json == post_revs
            and factors_match
            and plan_matches
            and method_matches
            and kwh_matches
        ):
            # Idempotent match: all 5 analytical inputs unchanged, deterministic reuse
            return comp, existing_asm

        # Data or inputs changed: Flag existing assessment as stale and create new revision
        existing_asm.is_stale_flag = True
        existing_asm.stale_reason = (
            "Underlying inputs updated: source revisions, plan version, exclusions, or factor assumptions changed."
        )
        new_revision = existing_asm.assessment_revision + 1
    else:
        new_revision = 1

    asm_id = generate_assessment_id(action_id)
    new_asm = InterventionAssessment(
        assessment_id=asm_id,
        action_id=action_id,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        assessment_revision=new_revision,
        is_stale_flag=False,
        stale_reason=None,
        evaluated_at=now,
        evaluated_by=evaluator,
        calculation_method="DETERMINISTIC_COMPARISON_V1",
        baseline_kwh=comp.baseline.kwh,
        baseline_cost_inr=comp.baseline.cost_inr,
        baseline_actual_units=comp.baseline.actual_units,
        baseline_good_units=comp.baseline.good_units,
        baseline_reject_units=comp.baseline.reject_units,
        baseline_downtime_min=comp.baseline.downtime_minutes,
        baseline_operating_hours=comp.baseline.operating_hours,
        baseline_coverage_pct=comp.baseline.coverage_pct,
        baseline_kwh_per_good_unit=comp.baseline.kwh_per_good_unit,
        baseline_cost_per_good_unit=comp.baseline.cost_per_good_unit,
        baseline_yield_pct=comp.baseline.yield_pct,
        post_kwh=comp.post.kwh,
        post_cost_inr=comp.post.cost_inr,
        post_actual_units=comp.post.actual_units,
        post_good_units=comp.post.good_units,
        post_reject_units=comp.post.reject_units,
        post_downtime_min=comp.post.downtime_minutes,
        post_operating_hours=comp.post.operating_hours,
        post_coverage_pct=comp.post.coverage_pct,
        post_kwh_per_good_unit=comp.post.kwh_per_good_unit,
        post_cost_per_good_unit=comp.post.cost_per_good_unit,
        post_yield_pct=comp.post.yield_pct,
        kwh_change_abs=comp.kwh_change_abs,
        kwh_change_pct=comp.kwh_change_pct,
        intensity_change_abs=comp.intensity_change_abs,
        intensity_change_pct=comp.intensity_change_pct,
        cost_intensity_change_abs=comp.cost_intensity_change_abs,
        cost_intensity_change_pct=comp.cost_intensity_change_pct,
        common_rate_cost_baseline_inr=comp.common_rate_baseline_cost_inr,
        common_rate_cost_post_inr=comp.common_rate_post_cost_inr,
        common_rate_factor_inr_per_kwh=comp.common_rate_factor_inr_per_kwh,
        common_rate_factor_version=comp.common_rate_factor_version,
        output_guardrail_met=all(g.passed for g in comp.guardrails if g.guardrail_type == "OUTPUT") if any(g.guardrail_type == "OUTPUT" for g in comp.guardrails) else None,
        quality_guardrail_met=all(g.passed for g in comp.guardrails if g.guardrail_type == "QUALITY_YIELD") if any(g.guardrail_type == "QUALITY_YIELD" for g in comp.guardrails) else None,
        downtime_guardrail_met=all(g.passed for g in comp.guardrails if g.guardrail_type == "DOWNTIME") if any(g.guardrail_type == "DOWNTIME" for g in comp.guardrails) else None,
        guardrails_summary_json=json.dumps([g.dict() for g in comp.guardrails]),
        objective_outcome=comp.objective_outcome,
        electricity_savings_kwh=comp.electricity_savings_kwh,
        monetary_savings_basis=comp.monetary_savings_basis,
        avoided_cost_inr=comp.avoided_cost_inr,
        verified_monetary_savings_inr=comp.verified_monetary_savings_inr,
        attribution_details_json=json.dumps(comp.attribution_details) if comp.attribution_details else None,
        savings_claim_status=comp.savings_claim_status,
        savings_claim_description=comp.savings_claim_description,
        status_reason=comp.status_reason,
        overlap_flag=comp.overlap_flag,
        overlap_details=comp.overlap_details,
        baseline_source_revisions_json=json.dumps(comp.baseline.source_revisions, sort_keys=True),
        post_source_revisions_json=json.dumps(comp.post.source_revisions, sort_keys=True),
    )

    action.assessment_status = comp.savings_claim_status
    action.updated_at = now

    try:
        with session.begin_nested():
            if existing_asm:
                session.add(existing_asm)
            session.add(new_asm)
            session.add(action)
            session.flush()
        session.commit()
        session.refresh(new_asm)
        return comp, new_asm
    except Exception:
        session.rollback()
        raise


AUTHORIZED_REVIEW_ROLES = {
    "PLANT_MANAGER",
    "ENERGY_ENGINEER",
    "FACILITIES_LEAD",
    "CONTINUOUS_IMPROVEMENT_DIRECTOR",
    "OPERATIONS_DIRECTOR",
    "ADMIN",
}


def sign_off_assessment(
    session: Session,
    assessment_id: str,
    req: AssessmentSignOffRequest,
    caller_attribution: Optional[str] = None,
    auth_caller: Optional[Dict[str, Any]] = None,
) -> InterventionAssessment:
    """
    Reviewer decision and formal sign-off on an outcome assessment.
    Transitions verified outcomes to VERIFIED and completes the action.
    
    Security & Governance Controls:
    - Derives operational reviewer from authenticated session.
    - Validates authorized engineering/operations role and plant scope.
    - Excludes demo or unauthenticated records from verified totals;
      if operational identity is unavailable, preserves demo workflow
      while keeping savings_claim_status as NOT_VERIFIED.
    """
    stmt = select(InterventionAssessment).where(InterventionAssessment.assessment_id == assessment_id)
    asm = session.execute(stmt).scalar_one_or_none()
    if not asm:
        raise ValueError(f"Intervention assessment '{assessment_id}' not found.")

    decision_norm = req.decision.strip().upper()
    if decision_norm not in ("APPROVED_VERIFIED", "REJECTED", "REQUEST_REANALYSIS"):
        raise ValueError("Sign-off decision must be 'APPROVED_VERIFIED', 'REJECTED', or 'REQUEST_REANALYSIS'.")

    action = get_corrective_action(session, asm.action_id)
    plan = session.execute(select(InterventionPlan).where(InterventionPlan.plan_id == asm.plan_id)).scalar_one_or_none()
    now = datetime.utcnow()

    # Identity and operational role validation
    is_authenticated = bool(auth_caller and auth_caller.get("is_authenticated"))
    operational_auth_available = bool(auth_caller and auth_caller.get("operational_auth_available"))
    auth_user = auth_caller.get("user_id") if auth_caller else None
    auth_role = auth_caller.get("role") if auth_caller else None
    auth_plant = auth_caller.get("plant_scope") if auth_caller else None

    # Derive reviewer from authenticated session if present; otherwise fallback to payload label
    if is_authenticated and auth_user and auth_role:
        reviewer_label = f"{auth_user} ({auth_role})"
    else:
        reviewer_label = req.reviewer.strip()

    # Check authorized role and plant scope: a missing plant scope must not grant access to every plant
    target_plant = plan.plant_id if plan else (action.plant_id if action else None)
    plant_matches = bool(auth_plant and target_plant and target_plant == auth_plant)
    role_authorized = bool(auth_role in AUTHORIZED_REVIEW_ROLES)
    is_authorized_verifier = is_authenticated and role_authorized and plant_matches

    # If trusted operational authentication is configured, strictly enforce role and plant scope
    if operational_auth_available:
        if not role_authorized:
            raise ValueError(
                f"Assessment sign-off denied: Caller '{auth_user}' (role: '{auth_role}') is not authorized. "
                f"Requires an authorized engineering/operations role ({', '.join(sorted(AUTHORIZED_REVIEW_ROLES))})."
            )
        if not plant_matches:
            raise ValueError(
                f"Assessment sign-off denied: Caller plant scope '{auth_plant or 'NONE'}' does not match "
                f"plant '{target_plant or 'Unknown'}'. Missing or mismatched plant scope denies operational transitions."
            )

    # Check if this intervention originated in demo / unauthenticated mode
    is_demo_origin = False
    if action:
        if action.reviewed_by and ("[Demo" in action.reviewed_by or "Unauthenticated" in action.reviewed_by):
            is_demo_origin = True
        if action.implemented_by and ("[Demo" in action.implemented_by or "Unauthenticated" in action.implemented_by):
            is_demo_origin = True
    if plan:
        if plan.approved_by and ("[Demo" in plan.approved_by or "Unauthenticated" in plan.approved_by):
            is_demo_origin = True
        if plan.is_retrospective:
            is_demo_origin = True

    asm.signed_off_by = reviewer_label if is_authenticated else f"{reviewer_label} [Demo / Unauthenticated]"
    asm.signed_off_at = now
    asm.review_decision = decision_norm
    asm.review_notes = req.notes.strip() if req.notes else None

    # Check factor assumption approval status for plant tariff
    from app.services.intervention_comparison_service import resolve_factor_assumption
    plant_scope = plan.plant_id if plan else "DEFAULT"
    target_date = plan.post_start if plan else None
    tariff_factor = resolve_factor_assumption(session, "ELECTRICITY_TARIFF", plant_scope, target_date=target_date)
    factor_approved = bool(tariff_factor.get("is_approved", False) and tariff_factor.get("factor_id") is not None)
    factor_status = tariff_factor.get("approval_status", "UNKNOWN")

    if decision_norm == "APPROVED_VERIFIED":
        if not is_authenticated:
            # Operational identity unavailable: preserve demo workflow, but exclude from verified totals
            asm.savings_claim_status = "NOT_VERIFIED"
            asm.verified_electricity_savings_kwh = None
            asm.verified_monetary_savings_inr = None
            asm.status_reason = (
                f"Operational verification unavailable: Sign-off was recorded in demo mode without an authenticated session. "
                f"Operational verification strictly requires an authenticated session with an authorized operational role "
                f"and matching plant scope. Excluded from verified factory totals in the ledger, pipeline, and assistant."
            )
            if action:
                action.status = "COMPLETED"
                action.completed_at = now
                action.assessment_status = "NOT_VERIFIED"
                action.resolution_notes = (
                    f"Sign-off recorded in demo mode by unverified caller '{req.reviewer.strip()}'. "
                    f"Savings claim status remains NOT_VERIFIED (operational identity unavailable)."
                )
        elif not is_authorized_verifier:
            # Authenticated session exists, but role or plant scope is unauthorized
            asm.savings_claim_status = "NOT_VERIFIED"
            asm.verified_electricity_savings_kwh = None
            asm.verified_monetary_savings_inr = None
            asm.status_reason = (
                f"Operational verification rejected: Caller '{auth_user}' (role: {auth_role}) "
                f"is not authorized to verify savings for plant '{plan.plant_id if plan else 'Unknown'}'. "
                f"Requires an authorized engineering/operations role with matching plant scope."
            )
            if action:
                action.assessment_status = "NOT_VERIFIED"
        elif is_demo_origin:
            # A later authenticated sign-off must NEVER promote a scripted / demo intervention into verified factory totals
            asm.savings_claim_status = "NOT_VERIFIED"
            asm.verified_electricity_savings_kwh = None
            asm.verified_monetary_savings_inr = None
            asm.status_reason = (
                f"Operational sign-off recorded by authenticated reviewer {reviewer_label}, but savings cannot be verified: "
                f"the intervention originated from a demo or scripted workflow. A later authenticated sign-off cannot "
                f"promote a scripted intervention into verified factory totals."
            )
            if action:
                action.status = "COMPLETED"
                action.completed_at = now
                action.assessment_status = "NOT_VERIFIED"
                action.resolution_notes = (
                    f"Operational sign-off completed by {reviewer_label}. "
                    f"Savings claim status remains NOT_VERIFIED: intervention originated in demo/scripted mode."
                )
        else:
            # Check guardrails summary for production protection (including restart, unassessable, output, quality, downtime)
            guardrails_summary = []
            if asm.guardrails_summary_json:
                try:
                    guardrails_summary = json.loads(asm.guardrails_summary_json)
                except Exception:
                    guardrails_summary = []
            has_guardrail_breach = any(g.get("status") == "BREACHED" or g.get("passed") is False for g in guardrails_summary)
            has_guardrail_unassessable = any(g.get("status") == "UNASSESSABLE" for g in guardrails_summary)
            production_limits_met = (
                not has_guardrail_breach
                and not has_guardrail_unassessable
                and not (asm.output_guardrail_met is False or asm.quality_guardrail_met is False or asm.downtime_guardrail_met is False)
            )

            # Requirement 1: Recorded approval/freeze timestamp MUST strictly precede action implementation timestamp
            plan_app_ts = plan.approved_at.replace(tzinfo=None) if (plan and plan.approved_at) else None
            act_impl_ts = action.implemented_at.replace(tzinfo=None) if (action and action.implemented_at) else None

            approval_precedes_implementation = False
            timing_denial_reason = None

            if plan_app_ts and act_impl_ts:
                if plan_app_ts < act_impl_ts:
                    approval_precedes_implementation = True
                elif plan_app_ts == act_impl_ts:
                    # Timestamps are equal: require independent ActionAuditLog evidence establishing prior plan freeze
                    # for the EXACT same plan revision (an older revision freeze cannot authorize a newer plan revision).
                    freeze_audit = None
                    impl_audit = None
                    if action and plan:
                        stmt_freeze = (
                            select(ActionAuditLog)
                            .where(
                                and_(
                                    ActionAuditLog.action_id == action.action_id,
                                    ActionAuditLog.entity_id == plan.plan_id,
                                    ActionAuditLog.action.in_(("PLAN_APPROVED_FROZEN", "PLAN_APPROVED", "PLAN_FROZEN")),
                                )
                            )
                            .order_by(ActionAuditLog.performed_at.asc())
                        )
                        candidate_freezes = session.execute(stmt_freeze).scalars().all()
                        for fa in candidate_freezes:
                            fa_ver = None
                            if fa.changed_fields_json:
                                try:
                                    cf = json.loads(fa.changed_fields_json)
                                    fa_ver = cf.get("version")
                                except Exception:
                                    pass
                            if fa_ver is None and fa.audit_metadata_json:
                                try:
                                    am = json.loads(fa.audit_metadata_json)
                                    fa_ver = (am.get("details") or {}).get("version")
                                except Exception:
                                    pass
                            if fa_ver is None and fa.comment and f"v{plan.version}" in fa.comment:
                                fa_ver = plan.version

                            # Verify exact plan revision match
                            if fa_ver is not None:
                                if fa_ver == plan.version:
                                    freeze_audit = fa
                                    break
                            elif plan.version == 1:
                                # Default to v1 only if plan itself is version 1
                                freeze_audit = fa
                                break

                        stmt_impl = (
                            select(ActionAuditLog)
                            .where(
                                and_(
                                    ActionAuditLog.action_id == action.action_id,
                                    ActionAuditLog.action == "IMPLEMENTED",
                                )
                            )
                            .order_by(ActionAuditLog.performed_at.asc())
                        )
                        impl_audit = session.execute(stmt_impl).scalars().first()

                    if freeze_audit and impl_audit and freeze_audit.performed_at < impl_audit.performed_at:
                        approval_precedes_implementation = True
                    else:
                        approval_precedes_implementation = False
                        if not freeze_audit:
                            timing_denial_reason = (
                                f"Non-prospective timing: Plan approval timestamp ({plan_app_ts.isoformat()}) "
                                f"equals implementation timestamp ({act_impl_ts.isoformat()}) without independent audit trail "
                                f"evidence establishing prior plan freeze for the exact plan revision v{plan.version if plan else '?'}. "
                                f"An older revision freeze cannot authorize a newer revision. Unverified sequence denies verified savings."
                            )
                        else:
                            timing_denial_reason = (
                                f"Non-prospective timing: Plan approval timestamp ({plan_app_ts.isoformat()}) "
                                f"equals implementation timestamp ({act_impl_ts.isoformat()}) without independent audit trail "
                                f"evidence establishing prior plan freeze before action implementation. Unverified sequence denies verified savings."
                            )
                else:
                    approval_precedes_implementation = False
                    timing_denial_reason = (
                        f"Non-prospective timing: Plan approval timestamp ({plan_app_ts.isoformat()}) "
                        f"did not precede action implementation timestamp ({act_impl_ts.isoformat()}). "
                        f"Approval after implementation denies verified savings."
                    )
            else:
                approval_precedes_implementation = False
                timing_denial_reason = (
                    f"Non-prospective timing: Missing plan approval timestamp "
                    f"({plan_app_ts.isoformat() if plan_app_ts else 'MISSING'}) or implementation timestamp "
                    f"({act_impl_ts.isoformat() if act_impl_ts else 'MISSING'}); savings cannot be verified. Verification denied."
                )

            prospective_implementation = bool(
                plan
                and plan.is_frozen
                and not plan.is_retrospective
                and action
                and action.implemented_at
                and approval_precedes_implementation
            )

            if (
                (asm.objective_outcome == "IMPROVED" or (asm.objective_outcome == "INCONCLUSIVE" and asm.monetary_savings_basis in ("APPROVED_CONTRACT_TARIFF", "ESTIMATED_AVOIDED_COST_VERSIONED_TARIFF")))
                and asm.electricity_savings_kwh is not None
                and asm.electricity_savings_kwh > 0
                and asm.monetary_savings_basis not in ("DISQUALIFIED_COMPARISON", "ATTRIBUTION_UNSUPPORTED", "INCONCLUSIVE_HIGH_UNCERTAINTY")
                and production_limits_met
                and prospective_implementation
                and not is_demo_origin
            ):
                # Physical electricity savings is verified! Missing tariff approval does not suppress qualified physical kWh.
                asm.savings_claim_status = "VERIFIED"
                asm.verified_electricity_savings_kwh = asm.electricity_savings_kwh
                if factor_approved:
                    asm.verified_monetary_savings_inr = asm.avoided_cost_inr
                    asm.status_reason = (
                        f"Verified by authenticated reviewer {reviewer_label} on {now.strftime('%Y-%m-%d')}. "
                        f"Electricity savings verified at {asm.electricity_savings_kwh:.4f} kWh and monetary savings "
                        f"verified at ₹{asm.verified_monetary_savings_inr:.2f} under approved contract tariff."
                    )
                else:
                    asm.verified_monetary_savings_inr = None
                    asm.status_reason = (
                        f"Physical electricity savings verified at {asm.electricity_savings_kwh:.4f} kWh by authenticated "
                        f"reviewer {reviewer_label} on {now.strftime('%Y-%m-%d')}. Monetary savings unverified "
                        f"(tariff assumption status: '{factor_status}', not an approved contract)."
                    )
                if action:
                    action.status = "COMPLETED"
                    action.completed_at = now
                    action.assessment_status = "VERIFIED"
                    action.resolution_notes = (
                        f"Verified savings outcome approved by {reviewer_label}. "
                        f"Objective: {asm.objective_outcome}. Notes: {req.notes or 'None'}"
                    )
            else:
                asm.savings_claim_status = "NOT_VERIFIED"
                asm.verified_electricity_savings_kwh = None
                asm.verified_monetary_savings_inr = None
                if not prospective_implementation:
                    if not approval_precedes_implementation:
                        asm.status_reason = timing_denial_reason or (
                            f"Non-prospective timing: Plan approval timestamp did not precede action implementation timestamp."
                        )
                    elif not plan or not plan.is_frozen:
                        asm.status_reason = "Measurement plan is not frozen on server; un-frozen plan denies verified savings."
                    elif plan and plan.is_retrospective:
                        asm.status_reason = "Measurement plan is retrospective; retrospective plans are ineligible for verified savings."
                    elif not action or not action.implemented_at:
                        asm.status_reason = "Corrective action implementation timestamp is missing; verification requires recorded implementation."
                elif not production_limits_met:
                    if has_guardrail_breach:
                        asm.status_reason = "Production limit breached during observation window; verified savings disqualified (null / ₹0)."
                    else:
                        asm.status_reason = "Production limits unassessable during observation window; verified savings disqualified (null / ₹0)."
                elif is_demo_origin:
                    asm.status_reason = "Intervention originated from scripted or demo workflow; cannot promote to verified factory totals."
                elif asm.electricity_savings_kwh is None or asm.electricity_savings_kwh <= 0:
                    asm.status_reason = "No positive attributable electricity savings observed during trial."
                else:
                    asm.status_reason = (
                        f"Sign-off recorded as {decision_norm} by authenticated reviewer {reviewer_label}, but savings cannot be verified: "
                        f"objective outcome is '{asm.objective_outcome}', basis is '{asm.monetary_savings_basis}', "
                        f"and avoided electricity is null. Human sign-off cannot override an undefined metric or disqualified comparison."
                    )

                if action:
                    action.status = "COMPLETED"
                    action.completed_at = now
                    action.assessment_status = "NOT_VERIFIED"
                    action.resolution_notes = asm.status_reason

    elif decision_norm == "REJECTED":
        asm.savings_claim_status = "NOT_VERIFIED"
        asm.status_reason = f"Verification rejected by reviewer {reviewer_label}. Reason: {req.notes or 'Unspecified'}"
        if action:
            action.assessment_status = "NOT_VERIFIED"

    elif decision_norm == "REQUEST_REANALYSIS":
        asm.savings_claim_status = "INCONCLUSIVE"
        asm.status_reason = f"Reviewer requested re-analysis: {req.notes or 'Pending updated baseline data'}"
        if action:
            action.assessment_status = "INCONCLUSIVE"

    # Append-only action audit trail
    audit = None
    if action:
        old_status = action.status
        audit = ActionAuditLog(
            audit_id=generate_audit_id("ACT"),
            action_id=action.action_id,
            recommendation_id=action.recommendation_id,
            entity_id=action.action_id,
            action=f"ASSESSMENT_SIGN_OFF_{decision_norm}",
            from_status=old_status,
            to_status=action.status,
            performed_at=now,
            comment=f"Assessment sign-off {decision_norm} by {reviewer_label}. Notes: {req.notes or 'None'}",
            changed_fields_json=json.dumps({
                "assessment_id": asm.assessment_id,
                "review_decision": decision_norm,
                "savings_claim_status": asm.savings_claim_status,
                "assessment_status": action.assessment_status,
                "is_authenticated": is_authenticated,
            }, default=str),
            audit_metadata_json=build_audit_metadata(
                caller_attribution=reviewer_label,
                source="OPERATIONAL_SIGN_OFF" if is_authenticated else "DEMO_UNAUTHENTICATED_SIGNOFF",
                details={
                    "is_authenticated": is_authenticated,
                    "reviewer": reviewer_label,
                    "role": auth_role,
                    "plant_scope": auth_plant,
                    "decision": decision_norm,
                    "savings_claim_status": asm.savings_claim_status,
                },
                is_authenticated=is_authenticated,
            ),
        )

    try:
        with session.begin_nested():
            session.add(asm)
            if action:
                session.add(action)
                if audit:
                    session.add(audit)
            session.flush()
        session.commit()
        session.refresh(asm)
        return asm
    except Exception:
        session.rollback()
        raise


def is_claim_eligible_for_verified_savings(asm: Any) -> Tuple[bool, str]:
    """
    Single canonical backend eligibility rule for verified intervention savings.
    Used consistently across ledger totals, daily pipeline summaries, and assistant responses.

    Excludes:
    - Stale or superseded revisions (is_stale_flag == True)
    - Overlapping claims on the same measurement boundary (overlap_flag == True)
    - Scripted, demo, or unauthenticated sign-offs (signed_off_by contains "[Demo" or "Unauthenticated")
    - Claims where savings_claim_status != "VERIFIED"
    - Claims lacking formal operational sign-off timestamp
    - Claims with zero or null avoided electricity
    - Claims with disqualified comparisons
    Missing tariff contract approval does not suppress qualified physical kWh savings.
    """
    if getattr(asm, "is_stale_flag", False):
        return False, "Assessment revision is stale or superseded"
    if getattr(asm, "overlap_flag", False):
        return False, "Assessment has an overlapping measurement window on the same boundary"
    if getattr(asm, "savings_claim_status", "") != "VERIFIED":
        return False, f"Savings claim status is {getattr(asm, 'savings_claim_status', 'UNKNOWN')}, not VERIFIED"
    if not getattr(asm, "signed_off_at", None):
        return False, "Assessment has not received formal operational sign-off"

    signed_by = getattr(asm, "signed_off_by", "") or ""
    if "[Demo" in signed_by or "Unauthenticated" in signed_by:
        return False, "Recorded in demo mode without trusted operational authentication"

    status_reason = getattr(asm, "status_reason", "") or ""
    if "demo" in status_reason.lower() or "scripted" in status_reason.lower():
        return False, "Intervention originated from scripted or demo workflow"

    kwh_savings = getattr(asm, "electricity_savings_kwh", None)
    if kwh_savings is None or kwh_savings <= 0:
        return False, "No positive attributable electricity savings"

    basis = getattr(asm, "monetary_savings_basis", "")
    if basis == "DISQUALIFIED_COMPARISON":
        return False, "Comparison is disqualified"

    guardrails_summary = []
    if getattr(asm, "guardrails_summary_json", None):
        try:
            guardrails_summary = json.loads(asm.guardrails_summary_json)
        except Exception:
            guardrails_summary = []
    if any(g.get("status") == "BREACHED" or g.get("passed") is False for g in guardrails_summary):
        return False, "Production limits were breached during observation window"
    if any(g.get("status") == "UNASSESSABLE" for g in guardrails_summary):
        return False, "Production limits were unassessable during observation window"
    if (
        getattr(asm, "output_guardrail_met", None) is False
        or getattr(asm, "quality_guardrail_met", None) is False
        or getattr(asm, "downtime_guardrail_met", None) is False
    ):
        return False, "Production output, quality, or downtime limits were breached"

    return True, "Eligible for verified factory rollup"


def is_claim_eligible_for_verified_monetary(asm: Any) -> Tuple[bool, str]:
    """
    Check if an assessment's monetary savings are formally verified.
    Requires qualified physical kWh AND an approved contract tariff.
    """
    eligible_kwh, reason = is_claim_eligible_for_verified_savings(asm)
    if not eligible_kwh:
        return False, reason

    verified_money = getattr(asm, "verified_monetary_savings_inr", None)
    if verified_money is None or verified_money <= 0:
        return False, "Monetary savings pending contract tariff approval"

    basis = getattr(asm, "monetary_savings_basis", "")
    if basis in ("UNAVAILABLE", "DISQUALIFIED_COMPARISON"):
        return False, f"Monetary basis {basis} is not an approved contract tariff"

    return True, "Eligible for verified monetary savings rollup"


def list_savings_ledger(
    session: Session,
    plant_id: Optional[str] = None,
    savings_claim_status: Optional[str] = None,
    include_stale: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> SavingsLedgerListResponse:
    """
    List persistent interventions and savings ledger entries.
    Distinguishes verified savings from estimates and inconclusive cases.
    Superseded historical assessments (is_stale_flag == True) are excluded from active verified totals.
    Uses canonical backend eligibility rule for verified rollups.
    """
    query = select(InterventionAssessment).order_by(desc(InterventionAssessment.evaluated_at))

    filters = []
    if not include_stale:
        filters.append(InterventionAssessment.is_stale_flag == False)
    if savings_claim_status:
        filters.append(InterventionAssessment.savings_claim_status == savings_claim_status.strip().upper())
    if plant_id:
        query = query.join(
            InterventionPlan,
            InterventionAssessment.plan_id == InterventionPlan.plan_id,
        )
        filters.append(InterventionPlan.plant_id == plant_id.strip())

    if filters:
        query = query.where(and_(*filters))

    # Aggregates across all ledger items using the canonical eligibility rule
    all_items = session.execute(query).scalars().all()
    total_count = len(all_items)

    # Deduplicate eligible items by action_id to ensure repeated sign-offs count once.
    # Exclude stale or superseded revisions (only the highest non-stale revision can qualify).
    raw_eligible_items = [
        it for it in all_items
        if not getattr(it, "is_stale_flag", False) and is_claim_eligible_for_verified_savings(it)[0]
    ]
    seen_action_ids = set()
    eligible_items = []
    for it in sorted(raw_eligible_items, key=lambda x: getattr(x, "assessment_revision", 1), reverse=True):
        act_id = it.action_id or it.assessment_id
        if act_id not in seen_action_ids:
            seen_action_ids.add(act_id)
            eligible_items.append(it)
    verified_count = len(eligible_items)
    not_verified_count = sum(1 for it in all_items if it.savings_claim_status == "NOT_VERIFIED" and not it.is_stale_flag)
    inconclusive_count = sum(1 for it in all_items if it.savings_claim_status in ("INCONCLUSIVE", "PENDING_REVIEW") and not it.is_stale_flag)

    # Sum verified avoided physical kWh
    total_verified_kwh = sum(it.electricity_savings_kwh or 0.0 for it in eligible_items) if eligible_items else 0.0
    # Sum estimated avoided cost (using dataset factor assumption)
    total_estimated_cost = sum(it.avoided_cost_inr or 0.0 for it in eligible_items) if eligible_items else 0.0
    # Sum verified monetary savings (only when contract tariff is approved)
    total_verified_monetary = sum(
        it.verified_monetary_savings_inr or 0.0
        for it in eligible_items
        if is_claim_eligible_for_verified_monetary(it)[0]
    ) if eligible_items else 0.0
    total_verified_cost = total_verified_monetary

    paginated_items = all_items[offset : offset + limit]

    response_items = []
    for it in paginated_items:
        # Determine plain-language management outcome for ledger row
        if it.quality_guardrail_met is False or it.downtime_guardrail_met is False:
            mg_outcome = "Production limit breached"
            mg_detail = "One or more production or quality guardrails failed during observation."
            mg_next = "Review root cause of guardrail breach with Production and Maintenance."
        elif it.objective_outcome == "NOT_IMPROVED":
            mg_outcome = "Cost objective not met"
            mg_detail = "Electricity cost per good finished unit showed no reduction. Zero change is not an improvement."
            mg_next = "Evaluate process setpoints to determine why cost intensity failed to improve."
        elif it.objective_outcome == "INCONCLUSIVE":
            if it.savings_claim_status == "VERIFIED":
                mg_outcome = "Verified stoppage standby reduction"
                mg_detail = (
                    "Standby electricity reduction verified during non-operating stoppage under approved contract tariff. "
                    "Cost per good unit is inconclusive and production protection is unassessable due to zero baseline output."
                )
                mg_next = "Intervention verified for stoppage standby. Monitor persistence in Savings Ledger."
            else:
                mg_outcome = "Inconclusive"
                mg_detail = it.status_reason or "Comparison inconclusive due to operating state or data coverage."
                mg_next = "Define an active production baseline window with positive good output or verify complete interval telemetry."
        elif it.objective_outcome == "IMPROVED":
            if it.savings_claim_status == "VERIFIED":
                mg_outcome = "Verified intervention improvement"
                mg_detail = "Intervention achieved certified cost-per-unit reduction with protected production and authorized sign-off."
                mg_next = "Intervention verified. Monitor ongoing persistence in Savings Ledger."
            elif it.savings_claim_status == "PENDING_REVIEW" or "eligible" in (it.status_reason or "").lower():
                mg_outcome = "Eligible for verification — awaiting reviewer"
                mg_detail = "Cost per good unit improved, production guardrails held, and attribution qualifies under approved criteria. Awaiting authorized reviewer sign-off."
                mg_next = "Submit formal sign-off by an authenticated, plant-authorized reviewer for this assessment revision to verify savings in the ledger."
            else:
                mg_outcome = "Observed improvement; attribution unverified"
                mg_detail = "Cost per good unit improved and guardrails held, but counterfactual attribution is unverified."
                mg_next = "Establish an approved engineering counterfactual reference model to verify attributable avoided energy."
        else:
            mg_outcome = "Inconclusive"
            mg_detail = it.status_reason or "Inconclusive"
            mg_next = "Review telemetry records."

        is_kwh_eligible, _ = is_claim_eligible_for_verified_savings(it)
        is_monetary_eligible, _ = is_claim_eligible_for_verified_monetary(it)

        # Three independent quantities:
        v_kwh = it.electricity_savings_kwh if is_kwh_eligible else None
        est_cost = it.avoided_cost_inr
        est_cost_assumption = (
            f"Dataset tariff assumption: INR {it.common_rate_factor_inr_per_kwh:.2f}/kWh ({it.common_rate_factor_version or 'DEFAULT'})"
            if it.common_rate_factor_inr_per_kwh
            else ("Dataset tariff assumption: INR 8.25/kWh" if it.avoided_cost_inr is not None else None)
        )
        v_monetary = it.verified_monetary_savings_inr if is_monetary_eligible else None
        attr_data = json.loads(it.attribution_details_json) if getattr(it, "attribution_details_json", None) else None

        response_items.append(
            InterventionAssessmentResponse(
                id=it.id,
                assessment_id=it.assessment_id,
                action_id=it.action_id,
                plan_id=it.plan_id,
                plan_version=it.plan_version,
                assessment_revision=it.assessment_revision,
                is_stale_flag=it.is_stale_flag,
                stale_reason=it.stale_reason,
                evaluated_at=it.evaluated_at.isoformat(),
                evaluated_by=it.evaluated_by,
                calculation_method=it.calculation_method,
                baseline_kwh=it.baseline_kwh,
                baseline_cost_inr=it.baseline_cost_inr,
                baseline_actual_units=it.baseline_actual_units,
                baseline_good_units=it.baseline_good_units,
                baseline_reject_units=it.baseline_reject_units,
                baseline_downtime_min=it.baseline_downtime_min,
                baseline_operating_hours=it.baseline_operating_hours,
                baseline_coverage_pct=it.baseline_coverage_pct,
                baseline_kwh_per_good_unit=it.baseline_kwh_per_good_unit,
                baseline_cost_per_good_unit=it.baseline_cost_per_good_unit,
                baseline_yield_pct=it.baseline_yield_pct,
                post_kwh=it.post_kwh,
                post_cost_inr=it.post_cost_inr,
                post_actual_units=it.post_actual_units,
                post_good_units=it.post_good_units,
                post_reject_units=it.post_reject_units,
                post_downtime_min=it.post_downtime_min,
                post_operating_hours=it.post_operating_hours,
                post_coverage_pct=it.post_coverage_pct,
                post_kwh_per_good_unit=it.post_kwh_per_good_unit,
                post_cost_per_good_unit=it.post_cost_per_good_unit,
                post_yield_pct=it.post_yield_pct,
                kwh_change_abs=it.kwh_change_abs,
                kwh_change_pct=it.kwh_change_pct,
                intensity_change_abs=it.intensity_change_abs,
                intensity_change_pct=it.intensity_change_pct,
                cost_intensity_change_abs=it.cost_intensity_change_abs,
                cost_intensity_change_pct=it.cost_intensity_change_pct,
                common_rate_cost_baseline_inr=it.common_rate_cost_baseline_inr,
                common_rate_cost_post_inr=it.common_rate_cost_post_inr,
                common_rate_factor_inr_per_kwh=it.common_rate_factor_inr_per_kwh,
                common_rate_factor_version=it.common_rate_factor_version,
                output_guardrail_met=it.output_guardrail_met,
                quality_guardrail_met=it.quality_guardrail_met,
                downtime_guardrail_met=it.downtime_guardrail_met,
                objective_outcome=it.objective_outcome,
                management_outcome=mg_outcome,
                management_outcome_detail=mg_detail,
                next_step=mg_next,
                electricity_savings_kwh=it.electricity_savings_kwh,
                monetary_savings_basis=it.monetary_savings_basis,
                avoided_cost_inr=it.avoided_cost_inr,
                verified_electricity_savings_kwh=v_kwh,
                estimated_avoided_cost_inr=est_cost,
                estimated_avoided_cost_assumption=est_cost_assumption,
                verified_monetary_savings_inr=v_monetary,
                attribution_details=attr_data,
                savings_claim_status=it.savings_claim_status,
                savings_claim_description=it.savings_claim_description,
                status_reason=it.status_reason,
                overlap_flag=it.overlap_flag,
                overlap_details=it.overlap_details,
                signed_off_by=it.signed_off_by,
                signed_off_at=it.signed_off_at.isoformat() if it.signed_off_at else None,
                review_decision=it.review_decision,
                review_notes=it.review_notes,
            )
        )

    return SavingsLedgerListResponse(
        items=response_items,
        total_count=total_count,
        verified_count=verified_count,
        not_verified_count=not_verified_count,
        inconclusive_count=inconclusive_count,
        total_verified_avoided_kwh=round(total_verified_kwh, 2),
        total_verified_avoided_cost_inr=round(total_verified_cost, 2),
        total_estimated_avoided_cost_inr=round(total_estimated_cost, 2),
        estimated_avoided_cost_assumption="Dataset tariff assumption: INR 8.25/kWh (unapproved contract)",
        total_verified_monetary_savings_inr=round(total_verified_monetary, 2),
    )


def plan_to_response(plan: InterventionPlan) -> MeasurementPlanResponse:
    """Format an InterventionPlan SQLAlchemy model into a Pydantic response."""
    eligible_meters = json.loads(plan.eligible_meters_json) if plan.eligible_meters_json else []
    comparability = json.loads(plan.comparability_rules_json) if plan.comparability_rules_json else {}
    operating_cond = json.loads(plan.operating_conditions_json) if plan.operating_conditions_json else {}

    return MeasurementPlanResponse(
        id=plan.id,
        plan_id=plan.plan_id,
        action_id=plan.action_id,
        version=plan.version,
        is_frozen=plan.is_frozen,
        is_retrospective=plan.is_retrospective,
        intended_change=plan.intended_change,
        implementation_owner=plan.implementation_owner,
        plant_id=plan.plant_id,
        process_or_line=plan.process_or_line,
        eligible_meters=eligible_meters,
        production_denominator=plan.production_denominator,
        production_unit=plan.production_unit,
        baseline_start=plan.baseline_start.isoformat(),
        baseline_end=plan.baseline_end.isoformat(),
        post_start=plan.post_start.isoformat(),
        post_end=plan.post_end.isoformat(),
        stabilization_start=plan.stabilization_start.isoformat() if plan.stabilization_start else None,
        stabilization_end=plan.stabilization_end.isoformat() if plan.stabilization_end else None,
        stabilization_exclusion_reason=plan.stabilization_exclusion_reason,
        restart_exclusion_reason=plan.restart_exclusion_reason,
        guardrail_output_min=plan.guardrail_output_min,
        guardrail_output_unit=plan.guardrail_output_unit,
        guardrail_output_direction=plan.guardrail_output_direction,
        guardrail_output_source=plan.guardrail_output_source,
        guardrail_output_reason=operating_cond.get("guardrail_output_reason"),
        guardrail_reject_max=plan.guardrail_reject_max,
        guardrail_reject_unit=plan.guardrail_reject_unit,
        guardrail_reject_direction=plan.guardrail_reject_direction,
        guardrail_reject_source=plan.guardrail_reject_source,
        guardrail_reject_reason=operating_cond.get("guardrail_reject_reason"),
        guardrail_downtime_max_min=plan.guardrail_downtime_max_min,
        guardrail_downtime_unit=plan.guardrail_downtime_unit,
        guardrail_downtime_direction=plan.guardrail_downtime_direction,
        guardrail_downtime_source=plan.guardrail_downtime_source,
        guardrail_downtime_reason=operating_cond.get("guardrail_downtime_reason"),
        guardrail_restart_max_min=operating_cond.get("guardrail_restart_max_min"),
        guardrail_restart_unit=operating_cond.get("guardrail_restart_unit", "minutes"),
        guardrail_restart_direction=operating_cond.get("guardrail_restart_direction", "LESS_OR_EQUAL"),
        guardrail_restart_source=operating_cond.get("guardrail_restart_source", "Target Line Availability / Restart Envelope"),
        guardrail_restart_reason=operating_cond.get("guardrail_restart_reason"),
        comparison_method=operating_cond.get("comparison_method", "MATCHED_SCHEDULE"),
        min_coverage_pct=plan.min_coverage_pct,
        comparability_rules=comparability,
        success_criterion=plan.success_criterion,
        success_criterion_metric=plan.success_criterion_metric,
        success_criterion_threshold_pct=plan.success_criterion_threshold_pct,
        operating_conditions=operating_cond,
        has_dual_boundary=bool(operating_cond.get("has_dual_boundary", False)),
        boundary_type=operating_cond.get("boundary_type", "SINGLE"),
        boundary_a_config=operating_cond.get("boundary_a"),
        boundary_b_config=operating_cond.get("boundary_b"),
        timing_status="PROSPECTIVE_CONFIRMED" if (plan.approved_at and not plan.is_retrospective) else ("RETROSPECTIVE_ENFORCED" if plan.is_retrospective else "UNESTABLISHED"),
        timing_reason=f"Plan approved at {plan.approved_at.isoformat()}." if plan.approved_at else "Plan has not been approved and frozen on server.",
        approved_by=plan.approved_by,
        approved_at=plan.approved_at.isoformat() if plan.approved_at else None,
        amendment_reason=plan.amendment_reason,
        created_by=plan.created_by,
        created_at=plan.created_at.isoformat(),
    )
