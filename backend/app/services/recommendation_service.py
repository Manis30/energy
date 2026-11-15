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

from datetime import datetime
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import desc, func, select
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
) -> str:
    """
    Construct standardized audit metadata JSON string.
    
    Adheres to attribution constraints:
    - Never fabricates or validates authentications.
    - Classifies actor_type as UNVERIFIED_CALLER vs SYSTEM_AUTOMATION.
    - Sets is_authenticated=False unconditionally.
    """
    clean_attribution = caller_attribution.strip() if caller_attribution and caller_attribution.strip() else None
    actor_type = "UNVERIFIED_CALLER" if clean_attribution else "SYSTEM_AUTOMATION"
    payload: Dict[str, Any] = {
        "actor_type": actor_type,
        "actor_attribution": clean_attribution,
        "is_authenticated": False,
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

    if plant_id:
        stmt = stmt.where(OperationalRecommendation.plant_id == plant_id.strip())
    if finding_id:
        stmt = stmt.where(OperationalRecommendation.finding_id == finding_id.strip())
    if status:
        stmt = stmt.where(OperationalRecommendation.status == status.strip().upper())
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
) -> List[OperationalRecommendation]:
    """
    Generate evidence-backed recommendations for an existing operational finding.
    
    Domain Rules:
    - Analyzes finding anomaly_type, severity, plant, meter, line, and latest occurrence lineage.
    - Suggests category-specific operational interventions:
        * LOW_POWER_FACTOR -> POWER_FACTOR_CORRECTION
        * ZERO_PRODUCTION_STANDBY_ENERGY -> STANDBY_SHUTDOWN
        * PEAK_DEMAND / LOAD_SPIKE -> LOAD_BALANCING
        * SEC_EXCURSION / INTENSITY -> OPERATIONAL_TUNING
        * General / Statistical -> MAINTENANCE_INSPECTION
    - Preserves row-level lineage (source_table, source_record_id, upload_id, detector_version).
    - Never fabricates dollar savings, percentage energy savings, or unverified claims.
    - Deduplicates: will not recreate an OPEN or IN_PROGRESS recommendation of the same category for the finding.
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

    if "POWER_FACTOR" in atype:
        target_category = "POWER_FACTOR_CORRECTION"
        rec_priority = "HIGH" if finding.severity in ("CRITICAL", "HIGH") else "MEDIUM"
        title = f"Inspect Capacitor Bank and Power Factor Correction on {entity_str}"
        description = (
            f"Power factor deficit detected on {entity_str}. "
            f"Inspect capacitor bank stages, automatic power factor controller (APFC) switching relays, "
            f"and check for excessive inductive motor idling."
        )
    elif "STANDBY" in atype or "ZERO_PRODUCTION" in atype:
        target_category = "STANDBY_SHUTDOWN"
        title = f"Enforce Non-Operational Standby Shutdown Protocols on {entity_str}"
        description = (
            f"Active energy consumption was recorded during scheduled zero-production intervals on {entity_str}. "
            f"Verify shift handover isolation procedures, auxiliary equipment interlocks, and master breaker disconnects."
        )
    elif "PEAK" in atype or "DEMAND" in atype:
        target_category = "LOAD_BALANCING"
        title = f"Review Peak Demand Load Scheduling for {entity_str}"
        description = (
            f"Significant demand peak observed on {entity_str}. "
            f"Coordinate high-load equipment startup sequences and consider staggering motor starts to balance demand."
        )
    elif "INTENSITY" in atype or "SEC" in atype:
        target_category = "OPERATIONAL_TUNING"
        title = f"Tune Specific Energy Consumption Operating Parameters on {entity_str}"
        description = (
            f"Energy consumption per production unit deviated from baseline on {entity_str}. "
            f"Audit operating speed, batch sizing, thermal losses, and mechanical friction on the line."
        )
    else:
        target_category = "MAINTENANCE_INSPECTION"
        title = f"Conduct Mechanical & Electrical Inspection on {entity_str}"
        description = (
            f"Operational energy anomaly '{finding.anomaly_type}' flagged on {entity_str}. "
            f"Perform thermal imaging, check connection tightness, and verify sensor calibration."
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
            "Active recommendation '%s' in category %s already exists for finding %s. Returning existing.",
            existing_active.recommendation_id,
            target_category,
            finding.finding_id,
        )
        return [existing_active]

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

    try:
        with session.begin_nested():
            session.add(recommendation)
            session.add(audit)
            session.flush()
        session.commit()
        session.refresh(recommendation)
        return [recommendation]
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
            return [concurrent_rec]
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
