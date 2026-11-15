"""
Operational Findings Lifecycle, Deduplication & Recurrence Hardened Service.

Deterministic operational finding lifecycle state machine:
1. Finding Identity & Deduplication: Stable key partitioned by (plant_id, entity, anomaly_type).
2. Occurrence Idempotency: Duplicate timestamps do not increment occurrence counts. Conflicting
   duplicate timestamps preserve original evidence and record a diagnostic audit entry.
3. Concurrency Safety: Row-level locking (with_for_update) and nested savepoint transactions prevent
   duplicate finding/occurrence creation under high concurrency.
4. Transactional Audit Integrity: Every state transition and corresponding audit log commits or rolls back
   as an atomic unit. Notes are appended with timestamp preservation.
5. Actor Attribution: Clearly distinguishes unverified caller-supplied attribution from authenticated identity.
"""

from datetime import datetime
from decimal import Decimal
import hashlib
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.findings import FindingAuditLog, FindingOccurrence, OperationalFinding
from app.services.anomaly_detection import detect_all_anomalies

logger = logging.getLogger(__name__)

# Severity order hierarchy for deterministic escalation
SEVERITY_RANK: Dict[str, int] = {
    "INFORMATIONAL": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}

# Permitted state transitions according to lifecycle rules
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "NEW": {"ACKNOWLEDGED", "INVESTIGATING"},
    "ACKNOWLEDGED": {"INVESTIGATING", "RESOLVED"},
    "INVESTIGATING": {"RESOLVED"},
    "RESOLVED": {"REOPENED"},
    "REOPENED": {"ACKNOWLEDGED", "INVESTIGATING", "RESOLVED"},
}

# Detector family mapping to associated stored anomaly types
DETECTOR_FAMILY_MAP: Dict[str, List[str]] = {
    "STATISTICAL_ZSCORE": ["ENERGY_STATISTICAL_SPIKE", "ENERGY_STATISTICAL_DROP"],
    "STATISTICAL": ["ENERGY_STATISTICAL_SPIKE", "ENERGY_STATISTICAL_DROP"],
    "ROLLING_BASELINE": ["ROLLING_BASELINE_SPIKE", "ROLLING_BASELINE_DROP"],
    "ROLLING": ["ROLLING_BASELINE_SPIKE", "ROLLING_BASELINE_DROP"],
    "LOW_POWER_FACTOR": ["LOW_POWER_FACTOR"],
    "POWER_FACTOR": ["LOW_POWER_FACTOR"],
    "ZERO_PRODUCTION_STANDBY": ["ZERO_PRODUCTION_STANDBY_ENERGY"],
    "ZERO_PRODUCTION": ["ZERO_PRODUCTION_STANDBY_ENERGY"],
}

# In-process lock guarding anomaly telemetry synchronization against duplicate concurrent runs
_sync_lock = threading.Lock()


def _max_severity(sev_a: str, sev_b: str) -> str:
    """Return the higher severity rank between two severity ratings."""
    rank_a = SEVERITY_RANK.get(sev_a.upper(), 1)
    rank_b = SEVERITY_RANK.get(sev_b.upper(), 1)
    return sev_a.upper() if rank_a >= rank_b else sev_b.upper()


def build_audit_metadata(
    caller_attribution: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Construct standardized audit metadata JSON string.
    
    Adheres to actor handling constraints:
    - Never presents caller-supplied strings as authenticated identities.
    - Clearly classifies caller attribution as 'UNVERIFIED_CALLER' vs 'SYSTEM_AUTOMATION'.
    """
    clean_attribution = caller_attribution.strip() if caller_attribution and caller_attribution.strip() else None
    payload: Dict[str, Any] = {
        "actor_type": "UNVERIFIED_CALLER" if clean_attribution else "SYSTEM_AUTOMATION",
        "actor_attribution": clean_attribution,
        "is_authenticated": False,
        "details": details or {},
    }
    return json.dumps(payload, default=str)


def compute_finding_key(
    plant_id: str,
    anomaly_type: str,
    meter_id: Optional[str] = None,
    line_id: Optional[str] = None,
) -> str:
    """
    Derive a deterministic, stable grouping identity for an operational finding.
    
    Guarantees isolation:
    - Never merges different meters, plants, or anomaly categories.
    - If meter_id is provided, scoped to meter.
    - If line_id is provided, scoped to line.
    - Otherwise scoped to plant.
    """
    clean_plant = plant_id.strip()
    clean_type = anomaly_type.strip()
    if meter_id:
        scope = f"meter:{meter_id.strip()}"
    elif line_id:
        scope = f"line:{line_id.strip()}"
    else:
        scope = "plant_wide"
    return f"{clean_plant}:{scope}:{clean_type}"


def generate_finding_id(finding_key: str, plant_id: str) -> str:
    """Generate a clean, deterministic stable ID for a finding."""
    key_hash = hashlib.sha256(finding_key.encode("utf-8")).hexdigest()[:10].upper()
    clean_plant = plant_id.replace(" ", "-").replace("_", "-").upper()
    return f"FND-{clean_plant}-{key_hash}"


def generate_occurrence_id(finding_id: str, occurrence_ts: datetime) -> str:
    """Generate a unique occurrence ID."""
    raw = f"{finding_id}:{occurrence_ts.isoformat()}"
    occ_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"OCC-{occ_hash}"


def _parse_datetime(dt_val: Any) -> datetime:
    """Parse date-time from string or datetime object."""
    if isinstance(dt_val, datetime):
        return dt_val
    if isinstance(dt_val, str):
        clean = dt_val.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(clean)
        except Exception:
            return datetime.strptime(dt_val[:19], "%Y-%m-%dT%H:%M:%S")
    raise ValueError(f"Cannot parse datetime from: {dt_val}")


def record_anomaly_occurrence(
    session: Session,
    anomaly: Dict[str, Any],
    caller_attribution: Optional[str] = None,
) -> Tuple[OperationalFinding, str]:
    """
    Ingest a single deterministic anomaly detection record into the finding lifecycle.
    
    Hardened for concurrency safety and idempotency:
    - Uses row-level lock (with_for_update) to serialize concurrent operations on the same finding.
    - Uses nested savepoints (begin_nested) to safely resolve simultaneous insert collisions.
    - Strictly checks occurrence idempotency:
        * Identical timestamp & value -> DUPLICATE_IGNORED (no counter increment, no modification).
        * Identical timestamp & different value -> DUPLICATE_CONFLICT_PRESERVED (immutable evidence
          is kept unchanged, occurrence count not incremented, conflict audit record written).
        * Genuinely new timestamp -> occurrence count incremented by 1, evidence appended.
    """
    plant_id = str(anomaly["plant_id"]).strip()
    anomaly_type = str(anomaly["anomaly_type"]).strip()
    meter_id = str(anomaly["meter_id"]).strip() if anomaly.get("meter_id") else None
    line_id = str(anomaly["line_id"]).strip() if anomaly.get("line_id") else None
    occ_ts = _parse_datetime(anomaly["timestamp"])
    
    actual_val = Decimal(str(anomaly["actual_value"]))
    base_val = Decimal(str(anomaly["baseline_value"])) if anomaly.get("baseline_value") is not None else None
    dev_score = float(anomaly.get("deviation_score", 0.0))
    severity = str(anomaly.get("severity", "MEDIUM")).upper()
    explanation = str(anomaly.get("explanation", ""))
    context_flags = anomaly.get("context_flags") or {}
    context_json = json.dumps(context_flags, default=str)

    source_table = str(anomaly["source_table"]).strip() if anomaly.get("source_table") else None
    source_record_id = str(anomaly["source_record_id"]).strip() if anomaly.get("source_record_id") else None
    upload_id = str(anomaly["upload_id"]).strip() if anomaly.get("upload_id") else None
    detector_version = str(anomaly["detector_version"]).strip() if anomaly.get("detector_version") else None

    finding_key = compute_finding_key(plant_id, anomaly_type, meter_id, line_id)
    finding_id = generate_finding_id(finding_key, plant_id)
    occ_id = generate_occurrence_id(finding_id, occ_ts)

    now = datetime.utcnow()

    # 1. Acquire row lock on existing finding if present
    stmt = (
        select(OperationalFinding)
        .where(OperationalFinding.finding_key == finding_key)
        .with_for_update()
    )
    finding = session.execute(stmt).scalar_one_or_none()

    if finding is None:
        # Attempt to insert brand new finding inside a savepoint to protect against concurrent inserts
        try:
            with session.begin_nested():
                finding = OperationalFinding(
                    finding_id=finding_id,
                    finding_key=finding_key,
                    anomaly_type=anomaly_type,
                    plant_id=plant_id,
                    meter_id=meter_id,
                    line_id=line_id,
                    status="NEW",
                    severity=severity,
                    first_detected_at=occ_ts,
                    last_detected_at=occ_ts,
                    occurrence_count=1,
                    current_actual_value=actual_val,
                    current_baseline_value=base_val,
                    current_deviation_score=dev_score,
                    current_explanation=explanation,
                    created_at=now,
                    updated_at=now,
                )
                session.add(finding)
                session.flush()

                audit = FindingAuditLog(
                    finding_id=finding_id,
                    action="CREATED",
                    from_status=None,
                    to_status="NEW",
                    performed_at=now,
                    comment=f"Initial detection recorded ({actual_val} vs baseline {base_val}).",
                    audit_metadata_json=build_audit_metadata(
                        caller_attribution=caller_attribution,
                        details={"actual_value": str(actual_val), "baseline_value": str(base_val) if base_val else None},
                    ),
                )
                session.add(audit)

                occurrence = FindingOccurrence(
                    occurrence_id=occ_id,
                    finding_id=finding_id,
                    occurrence_ts=occ_ts,
                    actual_value=actual_val,
                    baseline_value=base_val,
                    deviation_score=dev_score,
                    severity=severity,
                    explanation=explanation,
                    context_flags_json=context_json,
                    source_table=source_table,
                    source_record_id=source_record_id,
                    upload_id=upload_id,
                    detector_version=detector_version,
                    recorded_at=now,
                )
                session.add(occurrence)
                session.flush()

                return finding, "CREATED"

        except IntegrityError:
            # Concurrent worker inserted this finding_key simultaneously.
            # Re-fetch the newly committed finding with row lock.
            finding = session.execute(
                select(OperationalFinding)
                .where(OperationalFinding.finding_key == finding_key)
                .with_for_update()
            ).scalar_one()

    # 2. Finding exists and is locked. Check for existing occurrence at this exact timestamp.
    occ_check_stmt = (
        select(FindingOccurrence)
        .where(
            FindingOccurrence.finding_id == finding.finding_id,
            FindingOccurrence.occurrence_ts == occ_ts,
        )
    )
    existing_occ = session.execute(occ_check_stmt).scalar_one_or_none()

    if existing_occ is not None:
        # Check if measured value matches
        if existing_occ.actual_value == actual_val:
            # Exact duplicate replay: completely idempotent, do not increment count
            return finding, "DUPLICATE_IGNORED"
        else:
            # Conflicting duplicate timestamp: preserve original evidence without overwrite
            conflict_comment = (
                f"Duplicate occurrence timestamp {occ_ts.isoformat()} received with differing "
                f"measured value (incoming: {actual_val}, preserved: {existing_occ.actual_value}). "
                f"Existing immutable evidence retained."
            )
            audit = FindingAuditLog(
                finding_id=finding.finding_id,
                action="OCCURRENCE_CONFLICT_RECORDED",
                from_status=finding.status,
                to_status=finding.status,
                performed_at=now,
                comment=conflict_comment,
                audit_metadata_json=build_audit_metadata(
                    caller_attribution=caller_attribution,
                    details={
                        "timestamp": occ_ts.isoformat(),
                        "incoming_actual_value": str(actual_val),
                        "preserved_actual_value": str(existing_occ.actual_value),
                        "incoming_baseline_value": str(base_val) if base_val else None,
                        "incoming_deviation_score": dev_score,
                    },
                ),
            )
            session.add(audit)
            session.flush()
            return finding, "DUPLICATE_CONFLICT_PRESERVED"

    # 3. Genuinely new occurrence: check recurrence / state policy
    action_type = "UPDATED"

    if finding.status == "RESOLVED":
        if finding.resolved_at and occ_ts > finding.resolved_at:
            # Recurrence after resolution: Reopen finding
            reopen_reason = (
                f"Recurrence detected at {occ_ts.isoformat()} with measured value {actual_val} "
                f"after previous resolution at {finding.resolved_at.isoformat()}."
            )
            finding.status = "REOPENED"
            finding.reopened_at = now
            finding.reopen_reason = reopen_reason
            finding.occurrence_count += 1
            if occ_ts > finding.last_detected_at:
                finding.last_detected_at = occ_ts
            finding.current_actual_value = actual_val
            finding.current_baseline_value = base_val
            finding.current_deviation_score = dev_score
            finding.current_explanation = explanation
            finding.severity = _max_severity(finding.severity, severity)
            finding.updated_at = now

            audit = FindingAuditLog(
                finding_id=finding.finding_id,
                action="REOPENED",
                from_status="RESOLVED",
                to_status="REOPENED",
                performed_at=now,
                comment=reopen_reason,
                audit_metadata_json=build_audit_metadata(
                    caller_attribution=caller_attribution,
                    details={"reopen_trigger_ts": occ_ts.isoformat(), "actual_value": str(actual_val)},
                ),
            )
            session.add(audit)
            action_type = "REOPENED"
        else:
            # Late-arriving historical detection dated prior to resolution: record evidence without reopening
            finding.occurrence_count += 1
            finding.updated_at = now
            audit = FindingAuditLog(
                finding_id=finding.finding_id,
                action="HISTORICAL_OCCURRENCE_RECORDED",
                from_status="RESOLVED",
                to_status="RESOLVED",
                performed_at=now,
                comment=f"Historical occurrence at {occ_ts.isoformat()} attached to evidence without reopening.",
                audit_metadata_json=build_audit_metadata(
                    caller_attribution=caller_attribution,
                    details={"occurrence_ts": occ_ts.isoformat(), "actual_value": str(actual_val)},
                ),
            )
            session.add(audit)
            action_type = "EVIDENCE_ATTACHED"

    else:
        # Active finding: Deduplicate and update
        finding.occurrence_count += 1
        if occ_ts > finding.last_detected_at:
            finding.last_detected_at = occ_ts
        if occ_ts < finding.first_detected_at:
            finding.first_detected_at = occ_ts

        finding.current_actual_value = actual_val
        finding.current_baseline_value = base_val
        finding.current_deviation_score = dev_score
        finding.current_explanation = explanation
        finding.severity = _max_severity(finding.severity, severity)
        finding.updated_at = now

        audit = FindingAuditLog(
            finding_id=finding.finding_id,
            action="OCCURRENCE_RECORDED",
            from_status=finding.status,
            to_status=finding.status,
            performed_at=now,
            comment=f"Occurrence #{finding.occurrence_count} recorded at {occ_ts.isoformat()}.",
            audit_metadata_json=build_audit_metadata(
                caller_attribution=caller_attribution,
                details={"occurrence_ts": occ_ts.isoformat(), "actual_value": str(actual_val)},
            ),
        )
        session.add(audit)
        action_type = "UPDATED"

    # Save immutable detection evidence inside savepoint
    try:
        with session.begin_nested():
            occurrence = FindingOccurrence(
                occurrence_id=occ_id,
                finding_id=finding.finding_id,
                occurrence_ts=occ_ts,
                actual_value=actual_val,
                baseline_value=base_val,
                deviation_score=dev_score,
                severity=severity,
                explanation=explanation,
                context_flags_json=context_json,
                source_table=source_table,
                source_record_id=source_record_id,
                upload_id=upload_id,
                detector_version=detector_version,
                recorded_at=now,
            )
            session.add(occurrence)
            session.flush()
    except IntegrityError:
        # In the unlikely event of concurrent occurrence collision, savepoint safely absorbs it
        pass

    return finding, action_type


def sync_findings_from_anomalies(
    session: Session,
    plant_id: Optional[str] = None,
    meter_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    caller_attribution: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run deterministic anomaly detection suite and synchronize all findings and evidence.
    
    Guarded by an in-process execution lock (_sync_lock) to prevent duplicate concurrent runs.
    Ensures transactional integrity: entire sync executes atomically and commits together.
    Rolls back cleanly on unexpected error.
    """
    if not _sync_lock.acquire(blocking=False):
        raise RuntimeError(
            "A telemetry findings synchronization is already in progress. Please wait for the active run to finish."
        )

    try:
        detection_payload = detect_all_anomalies(
            session=session,
            plant_id=plant_id,
            meter_id=meter_id,
            start_time=start_time,
            end_time=end_time,
        )

        all_anomalies: List[Dict[str, Any]] = []
        for detector_key in ("statistical_zscore", "rolling_baseline", "low_power_factor", "zero_production_standby"):
            detector_result = detection_payload.get(detector_key) or {}
            anomalies_list = detector_result.get("anomalies") or []
            all_anomalies.extend(anomalies_list)

        new_count = 0
        updated_count = 0
        reopened_count = 0
        occ_count = 0
        ignored_count = 0
        conflict_count = 0
        affected_ids: Set[str] = set()

        try:
            for item in all_anomalies:
                finding, action = record_anomaly_occurrence(
                    session=session,
                    anomaly=item,
                    caller_attribution=caller_attribution,
                )
                if action == "CREATED":
                    new_count += 1
                    occ_count += 1
                    affected_ids.add(finding.finding_id)
                elif action == "UPDATED":
                    updated_count += 1
                    occ_count += 1
                    affected_ids.add(finding.finding_id)
                elif action == "REOPENED":
                    reopened_count += 1
                    occ_count += 1
                    affected_ids.add(finding.finding_id)
                elif action == "EVIDENCE_ATTACHED":
                    occ_count += 1
                    affected_ids.add(finding.finding_id)
                elif action == "DUPLICATE_IGNORED":
                    ignored_count += 1
                elif action == "DUPLICATE_CONFLICT_PRESERVED":
                    conflict_count += 1
                    affected_ids.add(finding.finding_id)

            session.commit()

            return {
                "total_anomalies_evaluated": len(all_anomalies),
                "new_findings_created": new_count,
                "existing_findings_updated": updated_count,
                "findings_reopened": reopened_count,
                "occurrences_recorded": occ_count,
                "duplicates_ignored": ignored_count,
                "conflicts_preserved": conflict_count,
                "affected_finding_ids": sorted(list(affected_ids)),
            }
        except Exception:
            session.rollback()
            raise
    finally:
        _sync_lock.release()


def validate_transition(current_status: str, target_status: str) -> None:
    """Validate that state transition is permitted by lifecycle rules."""
    allowed = VALID_TRANSITIONS.get(current_status.upper(), set())
    if target_status.upper() not in allowed:
        raise ValueError(
            f"Invalid finding status transition from '{current_status}' to '{target_status}'. "
            f"Allowed next states from '{current_status}': {sorted(list(allowed))}."
        )


def acknowledge_finding(
    session: Session,
    finding_id: str,
    comment: Optional[str] = None,
    caller_attribution: Optional[str] = None,
) -> OperationalFinding:
    """
    Transition finding to ACKNOWLEDGED with concurrency locking and atomic audit log commit.
    """
    try:
        finding = session.execute(
            select(OperationalFinding)
            .where(OperationalFinding.finding_id == finding_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not finding:
            raise KeyError(f"Finding '{finding_id}' not found.")

        validate_transition(finding.status, "ACKNOWLEDGED")

        now = datetime.utcnow()
        prev_status = finding.status
        finding.status = "ACKNOWLEDGED"
        finding.acknowledged_at = now
        finding.updated_at = now

        audit = FindingAuditLog(
            finding_id=finding.finding_id,
            action="ACKNOWLEDGED",
            from_status=prev_status,
            to_status="ACKNOWLEDGED",
            performed_at=now,
            comment=comment or "Finding acknowledged by operational engineering review.",
            audit_metadata_json=build_audit_metadata(
                caller_attribution=caller_attribution,
                details={"transition": f"{prev_status} -> ACKNOWLEDGED"},
            ),
        )
        session.add(audit)
        session.commit()
        session.refresh(finding)
        return finding
    except Exception:
        session.rollback()
        raise


def start_investigation(
    session: Session,
    finding_id: str,
    investigation_notes: Optional[str] = None,
    caller_attribution: Optional[str] = None,
) -> OperationalFinding:
    """
    Transition finding to INVESTIGATING with concurrency locking and note append preservation.
    """
    try:
        finding = session.execute(
            select(OperationalFinding)
            .where(OperationalFinding.finding_id == finding_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not finding:
            raise KeyError(f"Finding '{finding_id}' not found.")

        validate_transition(finding.status, "INVESTIGATING")

        now = datetime.utcnow()
        prev_status = finding.status
        finding.status = "INVESTIGATING"
        finding.investigated_at = now
        if investigation_notes and investigation_notes.strip():
            existing = f"{finding.investigation_notes}\n\n" if finding.investigation_notes else ""
            finding.investigation_notes = f"{existing}[{now.strftime('%Y-%m-%d %H:%M:%S')}] {investigation_notes.strip()}"
        finding.updated_at = now

        audit = FindingAuditLog(
            finding_id=finding.finding_id,
            action="INVESTIGATION_STARTED",
            from_status=prev_status,
            to_status="INVESTIGATING",
            performed_at=now,
            comment=investigation_notes or "Investigation initiated for finding.",
            audit_metadata_json=build_audit_metadata(
                caller_attribution=caller_attribution,
                details={"transition": f"{prev_status} -> INVESTIGATING"},
            ),
        )
        session.add(audit)
        session.commit()
        session.refresh(finding)
        return finding
    except Exception:
        session.rollback()
        raise


def add_investigation_notes(
    session: Session,
    finding_id: str,
    notes: str,
    caller_attribution: Optional[str] = None,
) -> OperationalFinding:
    """
    Append investigation progress notes with timestamp preservation without altering status.
    """
    try:
        finding = session.execute(
            select(OperationalFinding)
            .where(OperationalFinding.finding_id == finding_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not finding:
            raise KeyError(f"Finding '{finding_id}' not found.")

        if not notes or not notes.strip():
            raise ValueError("Investigation notes cannot be empty.")

        now = datetime.utcnow()
        clean_notes = notes.strip()
        timestamped = f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {clean_notes}"
        existing = f"{finding.investigation_notes}\n\n" if finding.investigation_notes else ""
        finding.investigation_notes = f"{existing}{timestamped}"
        finding.updated_at = now

        audit = FindingAuditLog(
            finding_id=finding.finding_id,
            action="NOTES_UPDATED",
            from_status=finding.status,
            to_status=finding.status,
            performed_at=now,
            comment=clean_notes,
            audit_metadata_json=build_audit_metadata(
                caller_attribution=caller_attribution,
                details={"note_appended": True},
            ),
        )
        session.add(audit)
        session.commit()
        session.refresh(finding)
        return finding
    except Exception:
        session.rollback()
        raise


def resolve_finding(
    session: Session,
    finding_id: str,
    resolution_notes: str,
    caller_attribution: Optional[str] = None,
) -> OperationalFinding:
    """
    Transition finding to RESOLVED with required resolution notes and concurrency lock.
    Leaves investigation_notes intact in their separate column.
    """
    try:
        finding = session.execute(
            select(OperationalFinding)
            .where(OperationalFinding.finding_id == finding_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not finding:
            raise KeyError(f"Finding '{finding_id}' not found.")

        if not resolution_notes or not resolution_notes.strip():
            raise ValueError("Resolution notes are required to resolve a finding.")

        validate_transition(finding.status, "RESOLVED")

        now = datetime.utcnow()
        prev_status = finding.status
        finding.status = "RESOLVED"
        finding.resolved_at = now
        finding.resolution_notes = resolution_notes.strip()
        finding.updated_at = now

        audit = FindingAuditLog(
            finding_id=finding.finding_id,
            action="RESOLVED",
            from_status=prev_status,
            to_status="RESOLVED",
            performed_at=now,
            comment=resolution_notes.strip(),
            audit_metadata_json=build_audit_metadata(
                caller_attribution=caller_attribution,
                details={"transition": f"{prev_status} -> RESOLVED"},
            ),
        )
        session.add(audit)
        session.commit()
        session.refresh(finding)
        return finding
    except Exception:
        session.rollback()
        raise


def reopen_finding(
    session: Session,
    finding_id: str,
    reason: str,
    caller_attribution: Optional[str] = None,
) -> OperationalFinding:
    """
    Manually reopen a previously resolved finding with documented engineering justification.
    Leaves investigation_notes and resolution_notes intact.
    """
    try:
        finding = session.execute(
            select(OperationalFinding)
            .where(OperationalFinding.finding_id == finding_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not finding:
            raise KeyError(f"Finding '{finding_id}' not found.")

        if not reason or not reason.strip():
            raise ValueError("Reopen reason is required to reopen a resolved finding.")

        validate_transition(finding.status, "REOPENED")

        now = datetime.utcnow()
        prev_status = finding.status
        clean_reason = reason.strip()
        finding.status = "REOPENED"
        finding.reopened_at = now
        finding.reopen_reason = clean_reason
        finding.updated_at = now

        audit = FindingAuditLog(
            finding_id=finding.finding_id,
            action="REOPENED",
            from_status=prev_status,
            to_status="REOPENED",
            performed_at=now,
            comment=clean_reason,
            audit_metadata_json=build_audit_metadata(
                caller_attribution=caller_attribution,
                details={"transition": f"{prev_status} -> REOPENED"},
            ),
        )
        session.add(audit)
        session.commit()
        session.refresh(finding)
        return finding
    except Exception:
        session.rollback()
        raise


def list_findings(
    session: Session,
    plant_id: Optional[str] = None,
    meter_id: Optional[str] = None,
    line_id: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    anomaly_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[OperationalFinding], int]:
    """
    Retrieve filtered, paginated operational findings ordered by last detected time.
    
    Supports:
    - Detector family and exact category matching via DETECTOR_FAMILY_MAP.
    - Database-wide partial text search across finding_id, plant_id, meter_id, line_id, and anomaly_type.
    - Status filtering (including ACTIVE scope excluding RESOLVED).
    - Severity and plant isolation.
    """
    stmt = select(OperationalFinding)

    if plant_id:
        stmt = stmt.where(OperationalFinding.plant_id == plant_id.strip())
    if meter_id:
        stmt = stmt.where(OperationalFinding.meter_id == meter_id.strip())
    if line_id:
        stmt = stmt.where(OperationalFinding.line_id == line_id.strip())
    if severity:
        stmt = stmt.where(OperationalFinding.severity == severity.strip().upper())
    if anomaly_type and anomaly_type.strip():
        clean_type = anomaly_type.strip().upper()
        if clean_type in DETECTOR_FAMILY_MAP:
            stmt = stmt.where(OperationalFinding.anomaly_type.in_(DETECTOR_FAMILY_MAP[clean_type]))
        else:
            stmt = stmt.where(func.upper(OperationalFinding.anomaly_type) == clean_type)
    if status:
        clean_status = status.strip().upper()
        if clean_status == "ACTIVE":
            stmt = stmt.where(OperationalFinding.status != "RESOLVED")
        else:
            stmt = stmt.where(OperationalFinding.status == clean_status)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(OperationalFinding.finding_id).like(term),
                func.lower(OperationalFinding.plant_id).like(term),
                func.lower(func.coalesce(OperationalFinding.meter_id, "")).like(term),
                func.lower(func.coalesce(OperationalFinding.line_id, "")).like(term),
                func.lower(OperationalFinding.anomaly_type).like(term),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = session.execute(count_stmt).scalar() or 0

    stmt = stmt.order_by(desc(OperationalFinding.last_detected_at), desc(OperationalFinding.id))
    stmt = stmt.limit(max(1, min(limit, 500))).offset(max(0, offset))

    items = session.execute(stmt).scalars().all()
    return list(items), total_count


def get_finding_detail(
    session: Session,
    finding_id: str,
) -> Optional[OperationalFinding]:
    """Retrieve full finding detail with occurrences and audit log."""
    stmt = (
        select(OperationalFinding)
        .where(OperationalFinding.finding_id == finding_id)
        .options(
            selectinload(OperationalFinding.occurrences),
            selectinload(OperationalFinding.audit_logs),
        )
    )
    return session.execute(stmt).scalar_one_or_none()
