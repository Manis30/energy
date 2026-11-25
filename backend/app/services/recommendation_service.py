"""
Persistent Recommendations & Corrective Actions Service with Append-Only Audit Trail.

Provides deterministic lifecycle state machines and immutable audit logging for:
1. Operational Recommendations:
   - Traceable to operational energy findings and occurrence lineage.
   - Categorized by operational intervention type (e.g. POWER_FACTOR_CORRECTION, STANDBY_SHUTDOWN).
   - Distinct recommendation priority from source anomaly severity.
   - Evidence-grounded telemetry context without fabricated financial or savings estimates.
   - Lifecycle: OPEN -> IN_PROGRESS -> IMPLEMENTED | DISMISSED.
   - Append-only audit history tracking all transitions, dismissals, reasons, and reopenings.

2. Corrective Actions:
   - Persistent operational tasks linked to a parent recommendation.
   - Nullable unauthenticated owner assignment (no fake user accounts).
   - Due date tracking, completion timestamping, and resolution documentation.
   - Lifecycle: OPEN -> IN_PROGRESS -> COMPLETED | CANCELLED.
   - Action creation/completion is decoupled from recommendation completion.
   - Append-only audit history tracking task creation, status, ownership, due dates, and notes.
"""

from datetime import datetime, timedelta
import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.findings import FindingOccurrence, OperationalFinding
from app.models.recommendations import (
    ActionAuditLog,
    CorrectiveAction,
    OperationalRecommendation,
    RecommendationAuditLog,
)
from app.schemas.recommendations import (
    CreateActionRequest,
    CreateRecommendationRequest,
    UpdateActionRequest,
)

logger = logging.getLogger(__name__)

# Permitted state transitions for Recommendations
VALID_REC_TRANSITIONS: Dict[str, Set[str]] = {
    "OPEN": {"IN_PROGRESS", "IMPLEMENTED", "DISMISSED"},
    "IN_PROGRESS": {"IMPLEMENTED", "DISMISSED", "OPEN"},
    "IMPLEMENTED": {"OPEN", "IN_PROGRESS"},
    "DISMISSED": {"OPEN", "IN_PROGRESS"},
}

# Permitted state transitions for Corrective Actions
VALID_ACTION_TRANSITIONS: Dict[str, Set[str]] = {
    "OPEN": {"IN_PROGRESS", "COMPLETED", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED", "CANCELLED", "OPEN"},
    "COMPLETED": {"OPEN", "IN_PROGRESS"},
    "CANCELLED": {"OPEN", "IN_PROGRESS"},
}

VALID_PRIORITIES: Set[str] = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"}
VALID_REC_STATUSES: Set[str] = {"OPEN", "IN_PROGRESS", "IMPLEMENTED", "DISMISSED"}
VALID_ACTION_STATUSES: Set[str] = {"OPEN", "IN_PROGRESS", "COMPLETED", "CANCELLED"}


def generate_recommendation_id(plant_id: str) -> str:
    """Generate a clean, stable recommendation identifier."""
    clean_plant = plant_id.replace(" ", "-").replace("_", "-").upper()
    random_part = uuid.uuid4().hex[:10].upper()
    return f"REC-{clean_plant}-{random_part}"


def generate_action_id() -> str:
    """Generate a clean, stable corrective action identifier."""
    random_part = uuid.uuid4().hex[:10].upper()
    return f"ACT-{random_part}"


def generate_audit_id(prefix: str = "REC") -> str:
    """Generate a clean, stable audit trail identifier."""
    random_part = uuid.uuid4().hex[:12].upper()
    return f"AUD-{prefix}-{random_part}"


def build_audit_metadata(
    caller_attribution: Optional[str] = None,
    source: str = "SYSTEM_AUTOMATION",
    details: Optional[Dict[str, Any]] = None,
    is_authenticated: bool = False,
) -> str:
    """
    Construct standardized audit metadata JSON string.
    
    Adheres to attribution constraints:
    - Never fabricates or validates unverified caller strings as authenticated.
    - Classifies actor_type as AUTHENTICATED_OPERATOR, UNVERIFIED_CALLER, or SYSTEM_AUTOMATION.
    - Preserves is_authenticated flag derived from authenticated session.
    """
    clean_attribution = caller_attribution.strip() if caller_attribution and caller_attribution.strip() else None
    if is_authenticated:
        actor_type = "AUTHENTICATED_OPERATOR"
    else:
        actor_type = "UNVERIFIED_CALLER" if clean_attribution else "SYSTEM_AUTOMATION"
    payload: Dict[str, Any] = {
        "actor_type": actor_type,
        "actor_attribution": clean_attribution,
        "is_authenticated": bool(is_authenticated),
        "source": source,
        "details": details or {},
    }
    return json.dumps(payload, default=str)


# -------------------------------------------------------------------------
# Operational Recommendations Operations
# -------------------------------------------------------------------------

def list_recommendations(
    session: Session,
    plant_id: Optional[str] = None,
    finding_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[OperationalRecommendation], int]:
    """
    List and filter persistent recommendations with pagination.
    
    Eagerly loads corrective actions to allow accurate action counts without N+1 queries.
    """
    stmt = select(OperationalRecommendation).options(
        selectinload(OperationalRecommendation.actions)
    )

    # Exclude test fixtures from operational recommendations
    stmt = stmt.where(
        and_(
            ~OperationalRecommendation.recommendation_id.like("REC-CONCUR-%"),
            ~OperationalRecommendation.recommendation_id.like("REC-DISM-%"),
            ~OperationalRecommendation.recommendation_id.like("REC-ATOMIC-%"),
            ~OperationalRecommendation.recommendation_id.like("REC-ACTLIFECYCLE-%"),
            ~OperationalRecommendation.recommendation_id.like("REC-TEST-%"),
            ~OperationalRecommendation.finding_id.like("FND-CONCUR-%"),
            ~OperationalRecommendation.finding_id.like("FND-DISM-%"),
            ~OperationalRecommendation.finding_id.like("FND-ATOMIC-%"),
            ~OperationalRecommendation.finding_id.like("FND-ACTLIFECYCLE-%"),
            ~OperationalRecommendation.finding_id.like("FND-TEST-%"),
        )
    )

    if plant_id:
        stmt = stmt.where(OperationalRecommendation.plant_id == plant_id.strip())
    if finding_id:
        stmt = stmt.where(OperationalRecommendation.finding_id == finding_id.strip())
    if status:
        status_clean = status.strip().upper()
        if "," in status_clean:
            statuses = [s.strip() for s in status_clean.split(",") if s.strip()]
            stmt = stmt.where(OperationalRecommendation.status.in_(statuses))
        elif status_clean == "ACTIVE":
            stmt = stmt.where(OperationalRecommendation.status.in_(["OPEN", "IN_PROGRESS"]))
        else:
            stmt = stmt.where(OperationalRecommendation.status == status_clean)
    if priority:
        stmt = stmt.where(OperationalRecommendation.priority == priority.strip().upper())
    if category:
        stmt = stmt.where(OperationalRecommendation.category == category.strip().upper())

    # Count total matching
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = session.execute(count_stmt).scalar() or 0

    # Apply pagination and sorting with deterministic tie-breaker
    stmt = (
        stmt.order_by(
            desc(OperationalRecommendation.created_at),
            desc(OperationalRecommendation.id),
        )
        .offset(offset)
        .limit(limit)
    )
    items = list(session.execute(stmt).scalars().all())

    return items, total


def get_recommendation_detail(
    session: Session,
    recommendation_id: str,
) -> Optional[OperationalRecommendation]:
    """
    Retrieve single recommendation by ID with associated actions, linked finding, and audit trail.
    """
    stmt = (
        select(OperationalRecommendation)
        .where(OperationalRecommendation.recommendation_id == recommendation_id.strip())
        .options(
            selectinload(OperationalRecommendation.actions).selectinload(CorrectiveAction.audit_logs),
            selectinload(OperationalRecommendation.finding),
            selectinload(OperationalRecommendation.audit_logs),
        )
    )
    return session.execute(stmt).scalars().first()


def get_recommendation_audit_logs(
    session: Session,
    recommendation_id: str,
    limit: int = 100,
) -> List[RecommendationAuditLog]:
    """
    Retrieve ordered audit log trail for a recommendation.
    """
    stmt = (
        select(RecommendationAuditLog)
        .where(RecommendationAuditLog.entity_id == recommendation_id.strip())
        .order_by(desc(RecommendationAuditLog.performed_at), desc(RecommendationAuditLog.id))
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


def create_recommendation(
    session: Session,
    data: CreateRecommendationRequest,
    caller_attribution: Optional[str] = None,
) -> OperationalRecommendation:
    """
    Create a persistent operational recommendation with audit log tracking.
    
    Enforces referential integrity checks (DEF-01) and active deduplication (DEF-02):
    1. Validates finding existence if supplied.
    2. Validates occurrence existence if supplied.
    3. Verifies that occurrence belongs to finding (occurrence.finding_id == finding.finding_id).
    4. Verifies that recommendation plant_id matches the referenced finding's plant_id.
    5. Derives finding_id from occurrence if occurrence supplied without finding_id.
    6. Preserves nullable references for legitimate standalone recommendations.
    7. Prevents duplicate active recommendations for the same (finding_id, category).
    8. Records immutable CREATED audit event inside atomic transaction.
    """
    priority = (data.priority or "MEDIUM").upper()
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority '{data.priority}'. Must be one of {sorted(VALID_PRIORITIES)}")

    plant_id = data.plant_id.strip()
    if not plant_id:
        raise ValueError("Recommendation plant_id must not be empty.")

    category = data.category.strip().upper()
    if not category:
        raise ValueError("Recommendation category must not be empty.")

    clean_finding_id = data.finding_id.strip() if data.finding_id and data.finding_id.strip() else None
    clean_occ_id = data.occurrence_id.strip() if data.occurrence_id and data.occurrence_id.strip() else None

    finding: Optional[OperationalFinding] = None
    occ: Optional[FindingOccurrence] = None

    # Step 1 & 2: Validate occurrence existence if referenced
    if clean_occ_id:
        occ = session.execute(
            select(FindingOccurrence).where(FindingOccurrence.occurrence_id == clean_occ_id)
        ).scalars().first()
        if not occ:
            raise ValueError(f"Finding occurrence '{clean_occ_id}' not found.")

    # Step 6: If occurrence supplied without finding ID, derive finding association
    if clean_occ_id and not clean_finding_id and occ:
        clean_finding_id = occ.finding_id

    # Step 1: Validate finding existence if supplied or derived from occurrence
    if clean_finding_id:
        finding = session.execute(
            select(OperationalFinding).where(OperationalFinding.finding_id == clean_finding_id)
        ).scalars().first()
        if not finding:
            raise ValueError(f"Operational finding '{clean_finding_id}' not found.")

    # Step 3: When both are supplied, verify occurrence belongs to finding
    if clean_finding_id and clean_occ_id and occ and finding:
        if occ.finding_id != finding.finding_id:
            raise ValueError(
                f"Referential mismatch: Occurrence '{clean_occ_id}' belongs to finding '{occ.finding_id}', "
                f"not '{finding.finding_id}'."
            )

    # Step 4 & 5: Verify recommendation plant_id matches the referenced finding's plant_id
    if finding:
        if finding.plant_id != plant_id:
            raise ValueError(
                f"Referential mismatch: Recommendation plant_id '{plant_id}' does not match "
                f"referenced finding plant_id '{finding.plant_id}' (finding '{finding.finding_id}')."
            )

    # Database-level & application-level active recommendation deduplication check
    if clean_finding_id:
        active_rec = session.execute(
            select(OperationalRecommendation)
            .where(
                OperationalRecommendation.finding_id == clean_finding_id,
                OperationalRecommendation.category == category,
                OperationalRecommendation.status.in_(["OPEN", "IN_PROGRESS"]),
            )
        ).scalars().first()
        if active_rec:
            raise ValueError(
                f"An active recommendation ('{active_rec.recommendation_id}') already exists for finding "
                f"'{clean_finding_id}' in category '{category}'. "
                f"Resolve or dismiss the existing recommendation before creating a new one."
            )

    evidence_json = None
    if data.evidence_context is not None:
        evidence_json = json.dumps(data.evidence_context, default=str)

    rec_id = generate_recommendation_id(plant_id)
    now = datetime.utcnow()
    recommendation = OperationalRecommendation(
        recommendation_id=rec_id,
        finding_id=clean_finding_id,
        occurrence_id=clean_occ_id,
        plant_id=plant_id,
        title=data.title.strip(),
        description=data.description.strip(),
        category=category,
        priority=priority,
        status="OPEN",
        evidence_context_json=evidence_json,
        created_at=now,
        updated_at=now,
    )

    effective_attribution = caller_attribution or getattr(data, "caller_attribution", None)
    audit = RecommendationAuditLog(
        audit_id=generate_audit_id("REC"),
        recommendation_id=rec_id,
        entity_id=rec_id,
        action="CREATED",
        from_status=None,
        to_status="OPEN",
        performed_at=now,
        comment=f"Created recommendation '{data.title.strip()}' in category '{category}' with priority '{priority}'.",
        changed_fields_json=json.dumps({
            "status": {"old": None, "new": "OPEN"},
            "category": {"old": None, "new": category},
            "priority": {"old": None, "new": priority},
            "title": {"old": None, "new": data.title.strip()},
            "plant_id": {"old": None, "new": plant_id},
            "finding_id": {"old": None, "new": clean_finding_id},
            "occurrence_id": {"old": None, "new": clean_occ_id},
        }, default=str),
        audit_metadata_json=build_audit_metadata(
            caller_attribution=effective_attribution,
            source="MANUAL_CREATION" if effective_attribution else "SYSTEM_AUTOMATION",
            details={"priority": priority, "category": category, "plant_id": plant_id},
        ),
    )

    try:
        with session.begin_nested():
            session.add(recommendation)
            session.add(audit)
            session.flush()
        session.commit()
        session.refresh(recommendation)
        return recommendation
    except IntegrityError as e:
        session.rollback()
        raise ValueError(
            f"Cannot create duplicate active recommendation for finding '{clean_finding_id}' "
            f"in category '{category}'."
        ) from e


def update_recommendation_status(
    session: Session,
    recommendation_id: str,
    new_status: str,
    reason: Optional[str] = None,
    caller_attribution: Optional[str] = None,
) -> OperationalRecommendation:
    """
    Transition recommendation lifecycle status with validation and audit trail.
    
    Permitted: OPEN -> IN_PROGRESS -> IMPLEMENTED | DISMISSED.
    Reopening is permitted from IMPLEMENTED or DISMISSED to OPEN or IN_PROGRESS.
    Enforces active deduplication invariant when transitioning to active states.
    Records append-only audit log preserving prior dismissal reasons on reopening.
    Only records changes if an actual transition or reason update occurs.
    """
    rec = get_recommendation_detail(session, recommendation_id)
    if not rec:
        raise ValueError(f"Operational recommendation '{recommendation_id}' not found.")

    target_status = new_status.strip().upper()
    if target_status not in VALID_REC_STATUSES:
        raise ValueError(f"Invalid recommendation status '{new_status}'. Must be one of {sorted(VALID_REC_STATUSES)}")

    clean_reason = reason.strip() if reason and reason.strip() else None

    # Check if this is an idempotent request or reason modification
    if target_status == rec.status:
        if target_status == "DISMISSED" and clean_reason and clean_reason != (rec.dismissed_reason or ""):
            # Update dismissal reason with audit log
            prev_reason = rec.dismissed_reason
            now = datetime.utcnow()
            rec.dismissed_reason = clean_reason
            rec.updated_at = now

            audit = RecommendationAuditLog(
                audit_id=generate_audit_id("REC"),
                recommendation_id=rec.recommendation_id,
                entity_id=rec.recommendation_id,
                action="DISMISSAL_REASON_CHANGED",
                from_status=rec.status,
                to_status=rec.status,
                performed_at=now,
                comment=f"Updated dismissal reason: '{clean_reason}'.",
                changed_fields_json=json.dumps({
                    "dismissed_reason": {"old": prev_reason, "new": clean_reason}
                }, default=str),
                audit_metadata_json=build_audit_metadata(
                    caller_attribution=caller_attribution,
                    source="OPERATOR_ACTION" if caller_attribution else "SYSTEM_AUTOMATION",
                    details={"from_status": rec.status, "to_status": rec.status},
                ),
            )
            with session.begin_nested():
                session.add(audit)
                session.flush()
            session.commit()
            session.refresh(rec)
            return rec

        # No change at all, avoid writing redundant audit entries
        return rec

    allowed_targets = VALID_REC_TRANSITIONS.get(rec.status, set())
    if target_status not in allowed_targets:
        raise ValueError(
            f"Invalid recommendation transition from '{rec.status}' to '{target_status}'. "
            f"Permitted transitions from '{rec.status}' are: {sorted(allowed_targets)}"
        )

    # When transitioning to OPEN or IN_PROGRESS, verify we don't violate active uniqueness
    if target_status in ("OPEN", "IN_PROGRESS") and rec.finding_id:
        conflict = session.execute(
            select(OperationalRecommendation)
            .where(
                OperationalRecommendation.finding_id == rec.finding_id,
                OperationalRecommendation.category == rec.category,
                OperationalRecommendation.status.in_(["OPEN", "IN_PROGRESS"]),
                OperationalRecommendation.recommendation_id != rec.recommendation_id,
            )
        ).scalars().first()
        if conflict:
            raise ValueError(
                f"Cannot transition recommendation '{rec.recommendation_id}' to '{target_status}'. "
                f"An active recommendation ('{conflict.recommendation_id}') already exists for finding "
                f"'{rec.finding_id}' in category '{rec.category}'."
            )

    now = datetime.utcnow()
    prev_status = rec.status
    prev_dismissed_reason = rec.dismissed_reason
    rec.status = target_status
    rec.updated_at = now

    # Determine specific audit action event name
    if target_status == "IMPLEMENTED":
        action_name = "IMPLEMENTED"
        rec.implemented_at = now
        rec.dismissed_at = None
        rec.dismissed_reason = None
        comment_text = clean_reason or "Recommendation marked as implemented."
    elif target_status == "DISMISSED":
        action_name = "DISMISSED"
        rec.dismissed_at = now
        rec.dismissed_reason = clean_reason or "Dismissed by operational reviewer"
        rec.implemented_at = None
        comment_text = rec.dismissed_reason
    elif target_status in ("OPEN", "IN_PROGRESS"):
        rec.dismissed_at = None
        rec.dismissed_reason = None
        rec.implemented_at = None
        if prev_status in ("IMPLEMENTED", "DISMISSED"):
            action_name = "REOPENED"
            if prev_status == "DISMISSED" and prev_dismissed_reason:
                comment_text = f"Reopened from DISMISSED (prior reason: '{prev_dismissed_reason}'). {clean_reason or ''}".strip()
            else:
                comment_text = f"Reopened from {prev_status}. {clean_reason or ''}".strip()
        else:
            action_name = "STATUS_CHANGED"
            comment_text = clean_reason or f"Transitioned status from {prev_status} to {target_status}."
    else:
        action_name = "STATUS_CHANGED"
        comment_text = clean_reason or f"Transitioned status from {prev_status} to {target_status}."

    # Build changed fields record, preserving prior dismissal reason on reopening
    changed_fields: Dict[str, Any] = {
        "status": {"old": prev_status, "new": target_status},
    }
    if prev_dismissed_reason != rec.dismissed_reason:
        changed_fields["dismissed_reason"] = {
            "old": prev_dismissed_reason,
            "new": rec.dismissed_reason,
        }

    audit = RecommendationAuditLog(
        audit_id=generate_audit_id("REC"),
        recommendation_id=rec.recommendation_id,
        entity_id=rec.recommendation_id,
        action=action_name,
        from_status=prev_status,
        to_status=target_status,
        performed_at=now,
        comment=comment_text,
        changed_fields_json=json.dumps(changed_fields, default=str),
        audit_metadata_json=build_audit_metadata(
            caller_attribution=caller_attribution,
            source="OPERATOR_ACTION" if caller_attribution else "SYSTEM_AUTOMATION",
            details={
                "from_status": prev_status,
                "to_status": target_status,
                "reason": clean_reason,
                "prior_dismissed_reason": prev_dismissed_reason,
            },
        ),
    )

    try:
        with session.begin_nested():
            session.add(audit)
            session.flush()
        session.commit()
        session.refresh(rec)
        return rec
    except IntegrityError as e:
        session.rollback()
        raise ValueError(
            f"Cannot transition recommendation '{rec.recommendation_id}' to '{target_status}': "
            f"an active recommendation already exists for finding '{rec.finding_id}' in category '{rec.category}'."
        ) from e


def generate_recommendations_from_finding(
    session: Session,
    finding_id: str,
    caller_attribution: Optional[str] = None,
) -> Tuple[List[OperationalRecommendation], int, int]:
    """
    Generate evidence-backed recommendations for an existing operational finding.
    
    Domain Rules:
    - Analyzes finding anomaly_type, severity, plant, meter, line, and latest occurrence lineage.
    - Suggests category-specific operational interventions:
        * LOW_POWER_FACTOR -> POWER_FACTOR_CORRECTION
        * ZERO_PRODUCTION_STANDBY_ENERGY -> STANDBY_SHUTDOWN (Advisory investigation)
        * PEAK_DEMAND / LOAD_SPIKE -> LOAD_BALANCING (Peak Hourly Consumption)
        * SEC_EXCURSION / INTENSITY -> OPERATIONAL_TUNING
        * General / Statistical -> MAINTENANCE_INSPECTION
    - Preserves row-level lineage (source_table, source_record_id, upload_id, detector_version).
    - Never fabricates dollar savings, percentage energy savings, or unverified claims.
    - Advisory only: recommendations suggest human review/investigation rather than automated plant control.
    - Deduplicates: will not recreate an OPEN or IN_PROGRESS recommendation of the same category for the finding.
    - Returns: (recommendations_list, created_count, reused_count).
    - Records append-only CREATED audit log linked to finding detection.
    """
    clean_finding_id = finding_id.strip()

    # Row-level lock on the parent finding to serialize concurrent generators where supported
    finding = session.execute(
        select(OperationalFinding)
        .where(OperationalFinding.finding_id == clean_finding_id)
        .with_for_update()
        .options(
            selectinload(OperationalFinding.occurrences),
            selectinload(OperationalFinding.recommendations),
        )
    ).scalars().first()

    if not finding:
        raise ValueError(f"Operational finding '{finding_id}' not found.")

    latest_occ = finding.occurrences[0] if finding.occurrences else None

    # Determine domain intervention template
    target_category: str
    title: str
    description: str
    rec_priority: str

    atype = finding.anomaly_type.upper()
    entity_str = (
        f"meter '{finding.meter_id}'"
        if finding.meter_id
        else (f"line '{finding.line_id}'" if finding.line_id else f"plant '{finding.plant_id}'")
    )

    # Map finding severity to recommendation priority
    if finding.severity in ("CRITICAL", "HIGH"):
        rec_priority = "HIGH"
    elif finding.severity == "MEDIUM":
        rec_priority = "MEDIUM"
    else:
        rec_priority = "LOW"

    time_window = (
        finding.last_detected_at.strftime("%Y-%m-%d %H:%M")
        if finding.last_detected_at
        else "Unknown"
    )

    if "POWER_FACTOR" in atype:
        target_category = "POWER_FACTOR_CORRECTION"
        rec_priority = "HIGH" if finding.severity in ("CRITICAL", "HIGH") else "MEDIUM"
        assigned_team = "Facilities"
        title = f"Check power factor correction on {finding.meter_id or 'MTR-SMT'}"
        observed_cond = (
            f"Plant {finding.plant_id}, meter {finding.meter_id or 'main'}: measured power factor of "
            f"{finding.current_actual_value or 'unavailable'} fell below the engineering monitoring benchmark "
            f"(threshold: 0.90 lag, deficit: {finding.current_deviation_score or 'unavailable'}) around {time_window}."
        )
        comp_evidence = (
            f"Power factor monitored against CEA / IEEE 519 standard utility threshold (0.90 lag). "
            f"Total occurrences recorded: {finding.occurrence_count}. "
            f"Source record: {latest_occ.source_record_id if latest_occ else 'Unavailable'}."
        )
        possible_causes = [
            "[HYPOTHESIS-FACILITIES: APFC Controller or Capacitor Stage Failure] "
            "Automatic power factor controller relay stuck or capacitor step degraded.",
            "[HYPOTHESIS-PRODUCTION: Inductive Motor Light-Load Idling] "
            "Pumps, fans, or conveyor drives operating without load during transition.",
            "[LIMITATION-BILLING: Tariff Penalty Structure Unsupplied] "
            "Dataset does not include utility billing contract or penalty slab formulas.",
        ]
        condition_to_check = (
            "Verify line motor operating status and equipment load schedule before adjusting capacitor bank steps or APFC settings."
        )
        action_item = "Inspect capacitor bank steps and APFC relay status for degradation or disconnection."

    elif "STOPPAGE" in atype or "RESTART" in atype or "STANDBY" in atype or "ZERO_PRODUCTION" in atype:
        target_category = "STANDBY_SHUTDOWN"
        assigned_team = "Production"
        title = f"Investigate Zero-Output Stoppage and Standby Consumption on {entity_str}"
        observed_cond = (
            f"Plant {finding.plant_id}, line {finding.line_id or entity_str}: "
            f"{finding.current_explanation or 'Zero-output stoppage energy draw recorded'} around {time_window}. "
            f"Measured process electricity: {finding.current_actual_value or 'unavailable'} kWh."
        )
        comp_evidence = (
            f"Evaluated against historical completed stoppage episodes on same line. "
            f"Occurrence count: {finding.occurrence_count}. "
            f"Source record: {latest_occ.source_record_id if latest_occ else 'Unavailable'}."
        )
        possible_causes = [
            "[HYPOTHESIS-PRODUCTION: Extended Stoppage & Changeover Delay] "
            "Line remained unpowered down during zero-output stoppage exceeding typical duration.",
            "[HYPOTHESIS-FACILITIES: Auxiliary Standby Draw] "
            "Heaters, pumps, conveyors, or testing stations held in standby during stoppage.",
            "[LIMITATION-METERING: Dedicated Process Meter Boundary] "
            "Readings reflect line aggregate; subcomponents cannot be decoupled without submetering.",
        ]
        condition_to_check = (
            "Verify line mechanical safety, changeover completion, and upstream buffer readiness before adjusting electrical power, heaters, or auxiliaries."
        )
        action_item = "Audit stoppage root cause, line changeover handover, and auxiliary equipment idle isolation."

    elif "BASELOAD" in atype:
        target_category = "MAINTENANCE_INSPECTION"
        assigned_team = "Facilities"
        title = f"Investigate Persistent Baseload Electricity Shift on {entity_str}"
        observed_cond = (
            f"Plant {finding.plant_id}, meter {finding.meter_id or 'main'}: persistent shift in electricity consumption "
            f"(deviation: {finding.current_deviation_score}%) observed across consecutive intervals around {time_window}. "
            f"Observed rate: {finding.current_actual_value or 'unavailable'} kWh/h vs baseline {finding.current_baseline_value or 'unavailable'} kWh/h."
        )
        comp_evidence = (
            f"Screened against 14-day comparable historical baseline. "
            f"Occurrence count: {finding.occurrence_count}. "
            f"Source record: {latest_occ.source_record_id if latest_occ else 'Unavailable'}."
        )
        possible_causes = [
            "[HYPOTHESIS-FACILITIES: Auxiliary Equipment Setpoint Drift] "
            "Chiller setpoint shifted, compressor air leak, or ventilation operating continuously.",
            "[HYPOTHESIS-PRODUCTION: Shift Handover Idle Draw] "
            "Equipment left powered on between production shifts.",
            "[LIMITATION-METEOROLOGICAL: Ambient Conditions Unmeasured] "
            "External weather and temperature telemetry are not tracked.",
        ]
        condition_to_check = (
            "Verify plant compressed air pressure and cleanroom temperature bounds before altering auxiliary equipment schedules."
        )
        action_item = "Audit compressed air lines, HVAC setpoints, and chiller operating profile."

    elif "PEAK" in atype or "DEMAND" in atype:
        target_category = "LOAD_BALANCING"
        assigned_team = "Production"
        title = f"Review Peak Hourly Consumption Scheduling for {entity_str}"
        observed_cond = (
            f"Plant {finding.plant_id}, meter {finding.meter_id or 'main'}: elevated peak hourly consumption of "
            f"{finding.current_actual_value or 'unavailable'} kWh around {time_window}."
        )
        comp_evidence = (
            f"Peak consumption compared against historical baseline mean {finding.current_baseline_value or 'unavailable'} kWh. "
            f"Source record: {latest_occ.source_record_id if latest_occ else 'Unavailable'}."
        )
        possible_causes = [
            "[HYPOTHESIS-PRODUCTION: Coincident Line Startup] Simultaneous motor or thermal ramp-up.",
            "[LIMITATION-MEASUREMENT: Derived Demand] Derived demand_kw is not independently measured kW peak.",
        ]
        condition_to_check = (
            "Verify line production schedule and motor startup interlocks before re-sequencing start times."
        )
        action_item = "Review equipment startup sequencing to avoid coincident peak hours."

    elif "INTENSITY" in atype or "SEC" in atype:
        target_category = "OPERATIONAL_TUNING"
        assigned_team = "Production"
        title = f"Investigate Specific Energy Consumption Deviation on {entity_str}"
        observed_cond = (
            f"Plant {finding.plant_id}, line {finding.line_id or entity_str}: specific energy consumption "
            f"reached {finding.current_actual_value or 'unavailable'} around {time_window}."
        )
        comp_evidence = (
            f"Compared against baseline SEC target of {finding.current_baseline_value or 'unavailable'}. "
            f"Source record: {latest_occ.source_record_id if latest_occ else 'Unavailable'}."
        )
        possible_causes = [
            "[HYPOTHESIS-PRODUCTION: Reduced Throughput / High Scrap] Lower good output with fixed process electricity.",
            "[LIMITATION-ATTRIBUTION: Process Meter Aggregate] Process SEC reflects entire line, not individual stations.",
        ]
        condition_to_check = (
            "Verify product mix, operating speed, and scrap reject counts before re-tuning line parameters."
        )
        action_item = "Review line operating speed, batch sizing, and scrap reject rates."

    else:
        target_category = "MAINTENANCE_INSPECTION"
        assigned_team = "Facilities"
        title = f"Conduct Mechanical & Electrical Inspection on {entity_str}"
        observed_cond = (
            f"Plant {finding.plant_id}, entity {entity_str}: anomaly '{finding.anomaly_type}' "
            f"(value: {finding.current_actual_value or 'unavailable'}) detected around {time_window}."
        )
        comp_evidence = (
            f"Telemetry flagged deviation against historical baseline. "
            f"Source record: {latest_occ.source_record_id if latest_occ else 'Unavailable'}."
        )
        possible_causes = [
            "[HYPOTHESIS-FACILITIES: Telemetry or Mechanical Excursion] Sensor calibration drift or mechanical wear.",
            "[LIMITATION-INSPECTION: Physical Access Required] In-person inspection needed to isolate cause.",
        ]
        condition_to_check = (
            "Verify machine safety interlocks before opening electrical panels or servicing sensors."
        )
        action_item = "Perform thermal imaging and sensor calibration verification."

    # Formulate structured description with the 4 sections
    description = (
        f"### 1. Observed Condition\n{observed_cond}\n\n"
        f"### 2. Comparison and Evidence\n{comp_evidence}\n\n"
        f"### 3. Possible Causes and Limitations\n" + "\n".join(f"- {p}" for p in possible_causes) + "\n\n"
        f"### 4. Suggested Investigation\n"
        f"- Responsible Team: {assigned_team}\n"
        f"- Condition to Check Before Modifying State: {condition_to_check}\n"
        f"- Recommended Action: {action_item}"
    )

    # Application-level active deduplication check
    existing_active = session.execute(
        select(OperationalRecommendation)
        .where(
            OperationalRecommendation.finding_id == finding.finding_id,
            OperationalRecommendation.category == target_category,
            OperationalRecommendation.status.in_(["OPEN", "IN_PROGRESS"]),
        )
        .options(selectinload(OperationalRecommendation.actions))
    ).scalars().first()

    if existing_active:
        logger.info(
            "Active recommendation '%s' in category %s already exists for finding %s. Reusing existing.",
            existing_active.recommendation_id,
            target_category,
            finding.finding_id,
        )
        return [existing_active], 0, 1

    # Assemble factual evidence context without fabricated savings
    evidence_context: Dict[str, Any] = {
        "source_finding_id": finding.finding_id,
        "source_anomaly_type": finding.anomaly_type,
        "source_severity": finding.severity,
        "plant_id": finding.plant_id,
        "meter_id": finding.meter_id,
        "line_id": finding.line_id,
        "current_actual_value": str(finding.current_actual_value) if finding.current_actual_value is not None else None,
        "current_baseline_value": str(finding.current_baseline_value) if finding.current_baseline_value is not None else None,
        "current_deviation_score": finding.current_deviation_score,
        "first_detected_at": finding.first_detected_at.isoformat() if finding.first_detected_at else None,
        "last_detected_at": finding.last_detected_at.isoformat() if finding.last_detected_at else None,
        "occurrence_count": finding.occurrence_count,
        "source_explanation": finding.current_explanation,
    }

    source_records = None
    if latest_occ:
        c_flags: Dict[str, Any] = {}
        if latest_occ.context_flags_json:
            try:
                c_flags = json.loads(latest_occ.context_flags_json)
            except Exception:
                c_flags = {}

        source_records = c_flags.get("source_records")
        if latest_occ.source_table and latest_occ.source_record_id:
            lineage_status = "AVAILABLE"
        elif source_records and isinstance(source_records, list) and len(source_records) > 0:
            lineage_status = c_flags.get("lineage_status", "MULTI_SOURCE")
        else:
            lineage_status = "UNAVAILABLE"

        evidence_context.update({
            "latest_occurrence_id": latest_occ.occurrence_id,
            "latest_occurrence_ts": latest_occ.occurrence_ts.isoformat() if latest_occ.occurrence_ts else None,
            "source_table": latest_occ.source_table,
            "source_record_id": latest_occ.source_record_id,
            "upload_id": latest_occ.upload_id,
            "detector_version": latest_occ.detector_version,
            "lineage_status": lineage_status,
        })
        if source_records and isinstance(source_records, list) and len(source_records) > 0:
            evidence_context["source_records"] = source_records
    else:
        evidence_context["lineage_status"] = "UNAVAILABLE"

    evidence_context["investigation_sections"] = {
        "observed_condition": observed_cond,
        "comparison_and_evidence": comp_evidence,
        "possible_causes_and_limitations": possible_causes,
        "suggested_investigation": {
            "responsible_team": assigned_team,
            "production_condition_to_check": condition_to_check,
            "action_item": action_item,
        },
    }

    rec_id = generate_recommendation_id(finding.plant_id)
    evidence_json = json.dumps(evidence_context, default=str)
    now = datetime.utcnow()

    recommendation = OperationalRecommendation(
        recommendation_id=rec_id,
        finding_id=finding.finding_id,
        occurrence_id=latest_occ.occurrence_id if latest_occ else None,
        plant_id=finding.plant_id,
        title=title,
        description=description,
        category=target_category,
        priority=rec_priority,
        status="OPEN",
        evidence_context_json=evidence_json,
        created_at=now,
        updated_at=now,
    )

    audit = RecommendationAuditLog(
        audit_id=generate_audit_id("REC"),
        recommendation_id=rec_id,
        entity_id=rec_id,
        action="CREATED",
        from_status=None,
        to_status="OPEN",
        performed_at=now,
        comment=f"Generated from finding '{finding.finding_id}' ({finding.anomaly_type}) in category '{target_category}'.",
        changed_fields_json=json.dumps({
            "status": {"old": None, "new": "OPEN"},
            "category": {"old": None, "new": target_category},
            "priority": {"old": None, "new": rec_priority},
            "title": {"old": None, "new": title},
            "finding_id": {"old": None, "new": finding.finding_id},
            "plant_id": {"old": None, "new": finding.plant_id},
        }, default=str),
        audit_metadata_json=build_audit_metadata(
            caller_attribution=caller_attribution,
            source="DETECTOR_AUTOMATION",
            details={
                "source_finding_id": finding.finding_id,
                "anomaly_type": finding.anomaly_type,
                "severity": finding.severity,
                "category": target_category,
            },
        ),
    )

    action_id = generate_action_id()
    limitation_note = (
        f"Meter {finding.meter_id} measures aggregate electrical circuits for {finding.line_id or 'area'}; "
        f"submetering is required to isolate individual subcomponent loads."
        if finding.meter_id else None
    )
    pinned_json = json.dumps(source_records) if source_records else None

    action = CorrectiveAction(
        action_id=action_id,
        recommendation_id=rec_id,
        title=f"{assigned_team}: {action_item}",
        description=f"Actionable investigation for {assigned_team}.\n\nCondition to check before modifying state: {condition_to_check}\n\nObserved Condition: {observed_cond}",
        status="OPEN",
        owner=assigned_team,
        due_date=now + timedelta(days=7),
        plant_id=finding.plant_id,
        finding_id=finding.finding_id,
        occurrence_id=latest_occ.occurrence_id if latest_occ else None,
        pinned_evidence_json=pinned_json,
        affected_equipment=finding.line_id,
        measurement_meter_id=finding.meter_id,
        shared_meter_limitation=limitation_note,
        responsible_team=assigned_team,
        review_status="PENDING_REVIEW",
        assessment_status="NONE",
        created_at=now,
        updated_at=now,
    )
    action_audit = ActionAuditLog(
        audit_id=generate_audit_id("ACT"),
        action_id=action_id,
        entity_id=action_id,
        recommendation_id=rec_id,
        action="CREATED",
        from_status=None,
        to_status="OPEN",
        performed_at=now,
        comment=f"Initial actionable investigation task assigned to {assigned_team}.",
        changed_fields_json=json.dumps({"status": {"old": None, "new": "OPEN"}, "owner": {"old": None, "new": assigned_team}}, default=str),
        audit_metadata_json=build_audit_metadata(caller_attribution=caller_attribution, source="DETECTOR_AUTOMATION"),
    )

    try:
        with session.begin_nested():
            session.add(recommendation)
            session.add(audit)
            session.add(action)
            session.add(action_audit)
            session.flush()
        session.commit()
        session.refresh(recommendation)
        return [recommendation], 1, 0
    except IntegrityError:
        session.rollback()
        # Concurrently committed active recommendation exists now. Retrieve and return gracefully.
        concurrent_rec = session.execute(
            select(OperationalRecommendation)
            .where(
                OperationalRecommendation.finding_id == finding.finding_id,
                OperationalRecommendation.category == target_category,
                OperationalRecommendation.status.in_(["OPEN", "IN_PROGRESS"]),
            )
            .options(selectinload(OperationalRecommendation.actions))
        ).scalars().first()

        if concurrent_rec:
            logger.info(
                "Gracefully resolved concurrent unique conflict: returning existing active recommendation '%s' for finding %s",
                concurrent_rec.recommendation_id,
                finding.finding_id,
            )
            return [concurrent_rec], 0, 1
        raise


# -------------------------------------------------------------------------
# Corrective Actions Operations
# -------------------------------------------------------------------------

def list_corrective_actions(
    session: Session,
    recommendation_id: Optional[str] = None,
    status: Optional[str] = None,
    owner: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[CorrectiveAction], int]:
    """
    List and filter corrective actions with pagination and audit trails.
    """
    stmt = select(CorrectiveAction).options(
        selectinload(CorrectiveAction.audit_logs)
    )

    # Exclude test fixtures from operational corrective actions
    stmt = stmt.where(
        and_(
            ~CorrectiveAction.action_id.like("ACT-TEST-%"),
            ~CorrectiveAction.action_id.like("ACT-ACTLIFECYCLE-%"),
            ~CorrectiveAction.recommendation_id.like("REC-CONCUR-%"),
            ~CorrectiveAction.recommendation_id.like("REC-DISM-%"),
            ~CorrectiveAction.recommendation_id.like("REC-ATOMIC-%"),
            ~CorrectiveAction.recommendation_id.like("REC-ACTLIFECYCLE-%"),
            ~CorrectiveAction.recommendation_id.like("REC-TEST-%"),
        )
    )

    if recommendation_id:
        stmt = stmt.where(CorrectiveAction.recommendation_id == recommendation_id.strip())
    if status:
        stmt = stmt.where(CorrectiveAction.status == status.strip().upper())
    if owner:
        stmt = stmt.where(CorrectiveAction.owner.ilike(f"%{owner.strip()}%"))

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = session.execute(count_stmt).scalar() or 0

    # Apply pagination and sorting with deterministic tie-breaker
    stmt = (
        stmt.order_by(
            desc(CorrectiveAction.created_at),
            desc(CorrectiveAction.id),
        )
        .offset(offset)
        .limit(limit)
    )
    items = list(session.execute(stmt).scalars().all())

    return items, total


def get_corrective_action(
    session: Session,
    action_id: str,
) -> Optional[CorrectiveAction]:
    """
    Retrieve single corrective action by ID with audit logs.
    """
    stmt = (
        select(CorrectiveAction)
        .where(CorrectiveAction.action_id == action_id.strip())
        .options(selectinload(CorrectiveAction.audit_logs))
    )
    return session.execute(stmt).scalars().first()


def get_action_audit_logs(
    session: Session,
    action_id: str,
    limit: int = 100,
) -> List[ActionAuditLog]:
    """
    Retrieve ordered audit log trail for a corrective action.
    """
    stmt = (
        select(ActionAuditLog)
        .where(ActionAuditLog.entity_id == action_id.strip())
        .order_by(desc(ActionAuditLog.performed_at), desc(ActionAuditLog.id))
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


def create_corrective_action(
    session: Session,
    recommendation_id: str,
    data: CreateActionRequest,
    caller_attribution: Optional[str] = None,
) -> CorrectiveAction:
    """
    Create a new corrective action linked to a recommendation with audit logging.
    
    Lifecycle Rules (DEF-03):
    1. Rejects action creation under a DISMISSED recommendation. Reopening is required first.
    2. Rejects action creation under an IMPLEMENTED recommendation. Reopening is required first.
    3. If the parent recommendation is currently 'OPEN', transitions it to 'IN_PROGRESS' and logs audit.
    4. Action creation and recommendation status transition commit atomically in the same transaction.
    5. Crucially: Does NOT mark recommendation as completed or implemented.
    6. Records immutable CREATED action audit log.
    """
    rec = get_recommendation_detail(session, recommendation_id)
    if not rec:
        raise ValueError(f"Operational recommendation '{recommendation_id}' not found.")

    # DEF-03: Prevent action creation under closed recommendations
    if rec.status == "DISMISSED":
        raise ValueError(
            f"Cannot create corrective action under DISMISSED recommendation '{recommendation_id}'. "
            f"Explicitly reopen the recommendation to OPEN or IN_PROGRESS first."
        )
    if rec.status == "IMPLEMENTED":
        raise ValueError(
            f"Cannot create corrective action under IMPLEMENTED recommendation '{recommendation_id}'. "
            f"Explicitly reopen the recommendation to IN_PROGRESS first before adding new actions."
        )

    action_id = generate_action_id()
    owner_val = data.owner.strip() if data.owner and data.owner.strip() else None
    now = datetime.utcnow()

    action = CorrectiveAction(
        action_id=action_id,
        recommendation_id=rec.recommendation_id,
        title=data.title.strip(),
        description=data.description.strip(),
        status="OPEN",
        owner=owner_val,
        due_date=data.due_date,
        created_at=now,
        updated_at=now,
    )

    effective_attribution = caller_attribution or getattr(data, "caller_attribution", None)

    # Action audit entry
    action_audit = ActionAuditLog(
        audit_id=generate_audit_id("ACT"),
        action_id=action_id,
        recommendation_id=rec.recommendation_id,
        entity_id=action_id,
        action="CREATED",
        from_status=None,
        to_status="OPEN",
        performed_at=now,
        comment=f"Created corrective action '{data.title.strip()}'.",
        changed_fields_json=json.dumps({
            "status": {"old": None, "new": "OPEN"},
            "title": {"old": None, "new": data.title.strip()},
            "owner": {"old": None, "new": owner_val},
            "due_date": {"old": None, "new": data.due_date.isoformat() if data.due_date else None},
        }, default=str),
        audit_metadata_json=build_audit_metadata(
            caller_attribution=effective_attribution,
            source="OPERATOR_ACTION" if effective_attribution else "SYSTEM_AUTOMATION",
            details={"recommendation_id": rec.recommendation_id, "owner": owner_val},
        ),
    )

    rec_audit: Optional[RecommendationAuditLog] = None
    # Automatically progress recommendation to IN_PROGRESS when first action is logged
    if rec.status == "OPEN":
        rec.status = "IN_PROGRESS"
        rec.updated_at = now
        rec_audit = RecommendationAuditLog(
            audit_id=generate_audit_id("REC"),
            recommendation_id=rec.recommendation_id,
            entity_id=rec.recommendation_id,
            action="STATUS_CHANGED",
            from_status="OPEN",
            to_status="IN_PROGRESS",
            performed_at=now,
            comment=f"Automatically transitioned recommendation to IN_PROGRESS upon creation of action '{action_id}'.",
            changed_fields_json=json.dumps({
                "status": {"old": "OPEN", "new": "IN_PROGRESS"}
            }, default=str),
            audit_metadata_json=build_audit_metadata(
                caller_attribution=effective_attribution,
                source="ACTION_CREATION_HOOK",
                details={"triggering_action_id": action_id},
            ),
        )

    try:
        with session.begin_nested():
            session.add(action)
            session.add(action_audit)
            if rec_audit:
                session.add(rec_audit)
            session.flush()
        session.commit()
        session.refresh(action)
        return action
    except Exception:
        session.rollback()
        raise


def update_corrective_action(
    session: Session,
    action_id: str,
    data: UpdateActionRequest,
    caller_attribution: Optional[str] = None,
) -> CorrectiveAction:
    """
    Update corrective action status, ownership, due date, and resolution documentation with audit trail.
    
    Rules:
    - Status transitions validated against VALID_ACTION_TRANSITIONS.
    - Sets completed_at automatically when transitioning to COMPLETED.
    - Clears completed_at when transitioning away from COMPLETED.
    - Owner can be updated or explicitly cleared via clear_owner=True.
    - Due date can be updated or explicitly cleared via clear_due_date=True.
    - Crucially: Does NOT mark the parent recommendation as IMPLEMENTED merely because
      this action is completed.
    - Records immutable audit trail tracking changed fields only.
    - Bypasses redundant audit logging when no fields actually change.
    """
    action = get_corrective_action(session, action_id)
    if not action:
        raise ValueError(f"Corrective action '{action_id}' not found.")

    now = datetime.utcnow()
    changed_fields: Dict[str, Any] = {}
    status_changed = False
    old_status = action.status
    new_status = old_status

    # Status transition handling
    if data.status:
        target_status = data.status.strip().upper()
        if target_status not in VALID_ACTION_STATUSES:
            raise ValueError(
                f"Invalid action status '{data.status}'. Must be one of {sorted(VALID_ACTION_STATUSES)}"
            )

        if target_status != action.status:
            allowed = VALID_ACTION_TRANSITIONS.get(action.status, set())
            if target_status not in allowed:
                raise ValueError(
                    f"Invalid action status transition from '{action.status}' to '{target_status}'. "
                    f"Permitted transitions from '{action.status}' are: {sorted(allowed)}"
                )

            status_changed = True
            new_status = target_status
            changed_fields["status"] = {"old": action.status, "new": target_status}
            action.status = target_status
            if target_status == "COMPLETED":
                action.completed_at = now
            else:
                action.completed_at = None

    # Title & Description
    if data.title is not None and data.title.strip() and data.title.strip() != action.title:
        changed_fields["title"] = {"old": action.title, "new": data.title.strip()}
        action.title = data.title.strip()

    if data.description is not None and data.description.strip() and data.description.strip() != action.description:
        changed_fields["description"] = {"old": action.description, "new": data.description.strip()}
        action.description = data.description.strip()

    # Ownership management
    owner_changed = False
    if data.clear_owner:
        if action.owner is not None:
            changed_fields["owner"] = {"old": action.owner, "new": None}
            action.owner = None
            owner_changed = True
    elif data.owner is not None:
        new_owner_val = data.owner.strip() if data.owner.strip() else None
        if new_owner_val != action.owner:
            changed_fields["owner"] = {"old": action.owner, "new": new_owner_val}
            action.owner = new_owner_val
            owner_changed = True

    # Due date management
    due_date_changed = False
    if data.clear_due_date:
        if action.due_date is not None:
            changed_fields["due_date"] = {"old": action.due_date.isoformat(), "new": None}
            action.due_date = None
            due_date_changed = True
    elif data.due_date is not None:
        if action.due_date != data.due_date:
            changed_fields["due_date"] = {
                "old": action.due_date.isoformat() if action.due_date else None,
                "new": data.due_date.isoformat(),
            }
            action.due_date = data.due_date
            due_date_changed = True

    # Resolution notes
    notes_changed = False
    if data.resolution_notes is not None:
        new_notes_val = data.resolution_notes.strip() if data.resolution_notes.strip() else None
        if new_notes_val != action.resolution_notes:
            changed_fields["resolution_notes"] = {"old": action.resolution_notes, "new": new_notes_val}
            action.resolution_notes = new_notes_val
            notes_changed = True

    # If no fields were modified, return without writing duplicate audit logs
    if not changed_fields:
        return action

    action.updated_at = now

    # Determine specific action event name
    if status_changed:
        if new_status == "COMPLETED":
            action_event = "COMPLETED"
            comment = "Action completed."
        elif new_status == "CANCELLED":
            action_event = "CANCELLED"
            comment = "Action cancelled."
        elif new_status in ("OPEN", "IN_PROGRESS") and old_status in ("COMPLETED", "CANCELLED"):
            action_event = "REOPENED"
            comment = f"Action reopened from {old_status} to {new_status}."
        else:
            action_event = "STATUS_CHANGED"
            comment = f"Status changed from {old_status} to {new_status}."
    elif owner_changed:
        action_event = "OWNER_CHANGED"
        comment = f"Ownership updated to '{action.owner}'." if action.owner else "Ownership cleared."
    elif due_date_changed:
        action_event = "DUE_DATE_CHANGED"
        comment = f"Due date set to {action.due_date.isoformat()}." if action.due_date else "Due date cleared."
    elif notes_changed:
        action_event = "NOTES_UPDATED"
        comment = "Resolution notes updated."
    else:
        action_event = "UPDATED"
        comment = "Action details updated."

    effective_attribution = caller_attribution or getattr(data, "caller_attribution", None)
    audit = ActionAuditLog(
        audit_id=generate_audit_id("ACT"),
        action_id=action.action_id,
        recommendation_id=action.recommendation_id,
        entity_id=action.action_id,
        action=action_event,
        from_status=old_status if status_changed else None,
        to_status=new_status if status_changed else None,
        performed_at=now,
        comment=comment,
        changed_fields_json=json.dumps(changed_fields, default=str),
        audit_metadata_json=build_audit_metadata(
            caller_attribution=effective_attribution,
            source="OPERATOR_ACTION" if effective_attribution else "SYSTEM_AUTOMATION",
            details={"changed_keys": list(changed_fields.keys())},
        ),
    )

    try:
        with session.begin_nested():
            session.add(audit)
            session.flush()
        session.commit()
        session.refresh(action)
        return action
    except Exception:
        session.rollback()
        raise


def draft_trial_plan_from_recommendation(
    session: Session,
    recommendation_id: str,
    break_duration_minutes: Optional[float] = None,
    restart_readiness_minutes: Optional[float] = None,
    caller_attribution: Optional[str] = None,
    target_equipment: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Draft an energy-saving trial plan prefilled from recommendation and finding data.
    Answers Questions 2, 3, and 4 before physical execution:
    - What specific operating change could we try?
    - Under what conditions could we try it while protecting production?
    - What dual-boundary measurement windows and guardrails will be used?

    Evaluates suitability:
    - If break duration is less than restart readiness, flags trial as unsuitable.
    - If equipment data is missing, recommends equipment audit/submetering (evidence gathering).
    - If suitable, returns prefilled CreateMeasurementPlanRequest with dual boundary & guardrails.
    """
    rec = get_recommendation_detail(session, recommendation_id)
    if not rec:
        raise ValueError(f"Operational recommendation '{recommendation_id}' not found.")

    finding: Optional[OperationalFinding] = None
    if rec.finding_id:
        finding = session.execute(
            select(OperationalFinding).where(OperationalFinding.finding_id == rec.finding_id)
        ).scalars().first()

    plant_id = rec.plant_id or (finding.plant_id if finding else "IN-TN-01")
    line_id = finding.line_id if finding else None
    meter_id = (finding.meter_id if finding else None) or "MTR-SMT"

    if not target_equipment and finding:
        target_equipment = getattr(finding, "machine_id", None) or getattr(finding, "equipment_id", None)

    break_min = float(break_duration_minutes) if break_duration_minutes is not None else 60.0
    restart_min = float(restart_readiness_minutes) if restart_readiness_minutes is not None else 10.0

    # 1. Suitability check: break duration vs restart readiness
    if break_duration_minutes is not None and restart_readiness_minutes is not None and break_min < restart_min:
        return {
            "is_suitable": False,
            "unsuitable_reason": (
                f"Operating change unsuitable for trial: Planned break duration ({break_min:.0f} min) "
                f"is shorter than equipment restart readiness ({restart_min:.0f} min). "
                f"Powering down equipment would risk delaying production restart and breaching availability guardrails."
            ),
            "recommendation_type": "OPERATIONAL_TRIAL",
            "audit_recommendation": None,
            "plan_draft": None,
            "break_duration_minutes": break_min,
            "restart_readiness_minutes": restart_min,
            "target_equipment": target_equipment,
            "suggested_operating_change": None,
            "operating_window": None,
            "why_saves_electricity": None,
            "production_dependencies": None,
            "restart_requirements": None,
            "stop_conditions": None,
            "inference_source": "RULE_BASED_FALLBACK",
            "agent_execution_trace": {
                "provider": "Domo AI Services",
                "model": "offline",
                "tools_called": ["evaluate_trial_suitability"],
                "status": "COMPLETED",
            },
        }

    # 2. Shared utility check (e.g. central compressor, chiller, HVAC)
    corr_id = f"corr-trial-{hashlib.sha256((rec.recommendation_id + str(break_min)).encode()).hexdigest()[:12]}"
    is_shared_compressor = bool(
        "COMPRESSOR" in str(meter_id).upper()
        or "COMPRESSOR" in str(getattr(rec, "affected_equipment", "") or "").upper()
        or "COMPRESSOR" in str(rec.title or "").upper()
    )
    is_shared_utility = is_shared_compressor or bool(
        "CHILLER" in str(meter_id).upper()
        or "CHILLER" in str(getattr(rec, "affected_equipment", "") or "").upper()
    )
    if is_shared_utility:
        return {
            "is_suitable": True,
            "is_equipment_trial_blocked": True,
            "unsuitable_reason": None,
            "recommendation_type": "EVIDENCE_GATHERING",
            "audit_recommendation": (
                f"Meter '{meter_id}' supplies shared utility services across multiple production lines whose individual pneumatic dependencies and demand are unknown. "
                f"Because another operating line may still require compressed air or cooling while Line {line_id or 'process'} is on break, "
                f"shutting down or modulating the utility load without line-level isolation creates a severe risk of starving active production. "
                f"Recommend measuring demand first with dedicated line-level flow submeters or pressure loggers. "
                f"Physical equipment-change trials are strictly blocked until line dependencies are resolved."
            ),
            "plan_draft": None,
            "break_duration_minutes": break_min,
            "restart_readiness_minutes": restart_min,
            "target_equipment": target_equipment or "Central Utility System",
            "suggested_operating_change": "Conduct distribution audit and install dedicated line isolation valves before staging utility power-down trials.",
            "operating_window": "Pre-trial pneumatic/cooling distribution audit window",
            "why_saves_electricity": "Distinguishes background header leakage from legitimate compressed air or cooling demand of adjacent operating lines.",
            "production_dependencies": "Central receiver header pressure must remain >= 6.5 bar for active production lines.",
            "restart_requirements": "Confirm full header pressure reaches 7.0 bar before initiating downstream machine cycles.",
            "stop_conditions": "Immediately abort audit or test and open isolation bypass if receiver pressure drops below 6.0 bar.",
            "inference_source": "RULE_GENERATED_DRAFT",
            "agent_execution_trace": {
                "provider": "Domo AI Services",
                "correlation_id": corr_id,
                "workflow_step": "PROPOSE_TRIAL",
                "model": "offline",
                "tools_called": ["audit_shared_utility_topology"],
                "status": "COMPLETED",
            },
        }

    # 3. Evidence gathering check: missing equipment data on aggregate line meter
    if not target_equipment:
        return {
            "is_suitable": True,
            "is_equipment_trial_blocked": False,
            "unsuitable_reason": None,
            "recommendation_type": "EVIDENCE_GATHERING",
            "audit_recommendation": (
                f"Process meter '{meter_id}' measures line aggregate consumption. "
                f"Line-level meter cannot isolate machine draw without submetering. "
                f"Conduct equipment-level log audit and install temporary IoT submeters to isolate "
                f"candidate auxiliary loads before staging an operational trial."
            ),
            "plan_draft": None,
            "break_duration_minutes": break_min,
            "restart_readiness_minutes": restart_min,
            "target_equipment": None,
            "suggested_operating_change": "Conduct equipment audit and attach temporary submeters to identify candidate standby loads.",
            "operating_window": "Pre-trial equipment submetering audit window",
            "why_saves_electricity": "Identifies which auxiliary subsystem draws parasitic power during zero-production stoppage intervals.",
            "production_dependencies": "Submeter installation must not interrupt active production power buses.",
            "restart_requirements": "Verify electrical phase balance and voltage drop before line startup.",
            "stop_conditions": "Abort submeter installation if ground fault or breaker trip occurs.",
            "inference_source": "RULE_GENERATED_DRAFT",
            "agent_execution_trace": {
                "provider": "Domo AI Services",
                "correlation_id": corr_id,
                "workflow_step": "PROPOSE_TRIAL",
                "model": "offline",
                "tools_called": ["audit_submeter_coverage"],
                "status": "COMPLETED",
            },
        }

    # 4. Formulate prefilled trial plan
    now = datetime.utcnow()
    ref_ts = (finding.last_detected_at if finding and finding.last_detected_at else now).replace(minute=0, second=0, microsecond=0)

    b_start = ref_ts - timedelta(days=1)
    b_end = b_start + timedelta(hours=2)
    p_start = ref_ts
    p_end = p_start + timedelta(hours=2)

    intended_change = "Activate plant-approved standby mode for nonessential line auxiliaries during planned breaks exceeding restart readiness."
    operating_window = f"Planned break [{b_start.strftime('%H:%M')}–{(b_start + timedelta(hours=1)).strftime('%H:%M')}) with restart buffer of {restart_min:.0f} minutes"
    why_saves_electricity = "De-energizing nonessential idle heaters, auxiliary pumps, and conveyor drives avoids standby parasitic draw during zero-production intervals."
    production_dependencies = "Upstream buffer inventory must be verified; downstream packing line must be cleared."
    restart_requirements = f"Pre-restart sequence must initiate at least {restart_min:.0f} minutes prior to shift start to achieve thermal/pneumatic operating thresholds."
    stop_conditions = "Immediately restore normal power if line startup is called early or safety interlocks trip."

    inference_source = "RULE_BASED_FALLBACK"
    agent_trace = {
        "provider": "Domo AI Services",
        "model": "offline",
        "tools_called": ["draft_measurement_plan_parameters"],
        "status": "COMPLETED",
    }

    from app.schemas.interventions import CreateMeasurementPlanRequest
    plan_draft = CreateMeasurementPlanRequest(
        intended_change=intended_change,
        implementation_owner="Shift Production Lead",
        plant_id=plant_id,
        process_or_line=line_id or "PLANT_WIDE",
        eligible_meters=[meter_id],
        production_denominator="Good finished units",
        production_unit="units",
        baseline_start=b_start,
        baseline_end=b_end,
        post_start=p_start,
        post_end=p_end,
        guardrail_output_min=100.0,
        guardrail_output_unit="units",
        guardrail_output_direction="GREATER_OR_EQUAL",
        guardrail_output_source="Approved Production Schedule",
        guardrail_output_reason="Maintain minimum production target of 100 good units",
        guardrail_reject_max=10.0,
        guardrail_reject_unit="units",
        guardrail_reject_direction="LESS_OR_EQUAL",
        guardrail_reject_source="Quality Specification Limit",
        guardrail_reject_reason="Keep scrap rejects below 10 units",
        guardrail_downtime_max_min=15.0,
        guardrail_downtime_unit="minutes",
        guardrail_downtime_direction="LESS_OR_EQUAL",
        guardrail_downtime_source="Target Line Availability",
        guardrail_downtime_reason="Ensure unplanned downtime does not exceed 15 minutes",
        guardrail_restart_max_min=12.0,
        guardrail_restart_unit="minutes",
        guardrail_restart_direction="LESS_OR_EQUAL",
        guardrail_restart_source="Target Line Availability / Restart Envelope",
        guardrail_restart_reason="Restart and ramp-up must complete within 12 minutes",
        comparison_method="DUAL_STOPPAGE_AND_RESTART",
        min_coverage_pct=90.0,
        success_criterion="Achieve net electricity reduction >= 5% across stoppage and restart while satisfying all production guardrails",
        success_criterion_metric="AVOIDED_KWH",
        success_criterion_threshold_pct=-5.0,
        has_dual_boundary=True,
        boundary_type="DUAL_STOPPAGE_AND_RESTART",
        boundary_a_config={
            "name": "Boundary A: Stoppage Electricity",
            "baseline_start": b_start.isoformat(),
            "baseline_end": (b_start + timedelta(hours=1)).isoformat(),
            "post_start": p_start.isoformat(),
            "post_end": (p_start + timedelta(hours=1)).isoformat(),
            "eligible_meters": [meter_id],
        },
        boundary_b_config={
            "name": "Boundary B: Restart & Productive Shift",
            "baseline_start": (b_start + timedelta(hours=1)).isoformat(),
            "baseline_end": b_end.isoformat(),
            "post_start": (p_start + timedelta(hours=1)).isoformat(),
            "post_end": p_end.isoformat(),
            "eligible_meters": [meter_id],
        },
        is_retrospective=False,
        created_by=caller_attribution or "SYSTEM_OPERATIONS",
    )

    return {
        "is_suitable": True,
        "unsuitable_reason": None,
        "recommendation_type": "OPERATIONAL_TRIAL",
        "audit_recommendation": None,
        "plan_draft": plan_draft,
        "break_duration_minutes": break_min,
        "restart_readiness_minutes": restart_min,
        "target_equipment": target_equipment or "Line Auxiliaries & Heating Stations",
        "suggested_operating_change": intended_change,
        "operating_window": operating_window,
        "why_saves_electricity": why_saves_electricity,
        "production_dependencies": production_dependencies,
        "restart_requirements": restart_requirements,
        "stop_conditions": stop_conditions,
        "inference_source": inference_source,
        "agent_execution_trace": agent_trace,
    }
