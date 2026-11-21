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

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.findings import (
    FindingAuditLog,
    FindingOccurrence,
    FindingOccurrenceSource,
    OperationalFinding,
)
from app.models.source_data import (
    FactEnergyMeterHourly,
    FactHourlyProduction,
    FactSourceRevision,
)
from app.models.upload_history import UploadHistory
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
    "PERSISTENT_BASELOAD": [
        "PERSISTENT_BASELOAD_INCREASE",
        "PERSISTENT_BASELOAD_DECREASE",
        "BASELOAD_DRIFT",
        "COMPARABLE_PERIOD_ELECTRICITY_CHANGE",
        "COMPARABLE_PERIOD_ELECTRICITY_INCREASE",
        "COMPARABLE_PERIOD_ELECTRICITY_DECREASE",
    ],
    "BASELOAD": [
        "PERSISTENT_BASELOAD_INCREASE",
        "PERSISTENT_BASELOAD_DECREASE",
        "BASELOAD_DRIFT",
        "COMPARABLE_PERIOD_ELECTRICITY_CHANGE",
        "COMPARABLE_PERIOD_ELECTRICITY_INCREASE",
        "COMPARABLE_PERIOD_ELECTRICITY_DECREASE",
    ],
    "COMPARABLE_PERIOD": [
        "COMPARABLE_PERIOD_ELECTRICITY_CHANGE",
        "COMPARABLE_PERIOD_ELECTRICITY_INCREASE",
        "COMPARABLE_PERIOD_ELECTRICITY_DECREASE",
    ],
    "ZERO_OUTPUT_RESTART": ["UNUSUALLY_LONG_STOPPAGE", "HIGH_STOPPAGE_ENERGY_RATE", "UNUSUAL_RESTART_BEHAVIOR"],
    "RESTART": ["UNUSUALLY_LONG_STOPPAGE", "HIGH_STOPPAGE_ENERGY_RATE", "UNUSUAL_RESTART_BEHAVIOR"],
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


def _serialize_record_for_revision(rec: Any, tbl: str) -> Dict[str, Any]:
    """Serialize physical fact record with exact string representation for numeric fields."""
    if tbl == "fact_energy_meter_hourly":
        return {
            "meter_reading_id": rec.meter_reading_id,
            "timestamp": rec.timestamp.isoformat() if rec.timestamp else None,
            "date": rec.date.isoformat() if rec.date else None,
            "plant_id": rec.plant_id,
            "meter_id": rec.meter_id,
            "area": rec.area,
            "energy_source": rec.energy_source,
            "consumption_kwh": str(rec.consumption_kwh) if rec.consumption_kwh is not None else None,
            "demand_kw": str(rec.demand_kw) if rec.demand_kw is not None else None,
            "power_factor": str(rec.power_factor) if rec.power_factor is not None else None,
            "tariff_inr_per_kwh": str(rec.tariff_inr_per_kwh) if rec.tariff_inr_per_kwh is not None else None,
            "cost_inr": str(rec.cost_inr) if rec.cost_inr is not None else None,
            "co2e_kg": str(rec.co2e_kg) if rec.co2e_kg is not None else None,
            "reading_quality": rec.reading_quality,
            "upload_id": rec.upload_id,
            "ingested_at": rec.ingested_at.isoformat() if rec.ingested_at else None,
        }
    elif tbl == "fact_hourly_production":
        return {
            "event_id": rec.event_id,
            "event_ts": rec.event_ts.isoformat() if rec.event_ts else None,
            "event_date": rec.event_date.isoformat() if rec.event_date else None,
            "year": rec.year,
            "month": rec.month,
            "week": rec.week,
            "day": rec.day,
            "hour": rec.hour,
            "plant_id": rec.plant_id,
            "line_id": rec.line_id,
            "shift_id": rec.shift_id,
            "product_id": rec.product_id,
            "production_order_id": rec.production_order_id,
            "target_qty": rec.target_qty,
            "actual_qty": rec.actual_qty,
            "good_qty": rec.good_qty,
            "reject_qty": rec.reject_qty,
            "rework_qty": rec.rework_qty,
            "downtime_min": rec.downtime_min,
            "downtime_reason": rec.downtime_reason,
            "operator_team": rec.operator_team,
            "source_system": rec.source_system,
            "data_quality": rec.data_quality,
            "upload_id": rec.upload_id,
            "ingested_at": rec.ingested_at.isoformat() if rec.ingested_at else None,
        }
    return {}


def _pin_occurrence_sources(
    session: Session,
    occ_id: str,
    anomaly: Dict[str, Any],
    default_upload_id: Optional[str],
    now: datetime,
) -> Optional[str]:
    """
    Pin each contributing source telemetry record to an immutable FactSourceRevision.
    Creates an initial revision on demand if one does not exist for the source record.
    Returns the primary revision_id if applicable.
    """
    sources_to_pin: List[Dict[str, Any]] = []
    if anomaly.get("source_records") and isinstance(anomaly["source_records"], list):
        for s in anomaly["source_records"]:
            sources_to_pin.append({
                "source_table": s.get("source_table"),
                "source_record_id": s.get("source_record_id"),
                "role": s.get("role") or "PRIMARY_OBSERVATION",
                "upload_id": s.get("upload_id") or default_upload_id,
                "revision_id": s.get("revision_id"),
            })
    elif anomaly.get("source_table") and anomaly.get("source_record_id"):
        sources_to_pin.append({
            "source_table": anomaly.get("source_table"),
            "source_record_id": anomaly.get("source_record_id"),
            "role": "PRIMARY_OBSERVATION",
            "upload_id": anomaly.get("upload_id") or default_upload_id,
            "revision_id": anomaly.get("revision_id"),
        })

    primary_rev_id: Optional[str] = None

    for item in sources_to_pin:
        tbl = item.get("source_table")
        rec_id = item.get("source_record_id")
        role = item.get("role") or "PRIMARY_OBSERVATION"
        up_id = item.get("upload_id")
        rev_id = item.get("revision_id")

        if not tbl or not rec_id:
            continue

        if not rev_id:
            # Query existing current revision
            rev_stmt = select(FactSourceRevision).where(
                FactSourceRevision.source_table == tbl,
                FactSourceRevision.source_record_id == str(rec_id),
                FactSourceRevision.is_current == True,
            )
            existing_rev = session.execute(rev_stmt).scalars().first()
            if existing_rev:
                rev_id = existing_rev.revision_id
            else:
                # Create initial baseline revision from actual table row
                raw_values = {}
                b_key = f"{tbl}:{rec_id}"
                plant_id = anomaly.get("plant_id", "UNKNOWN")

                if tbl == "fact_energy_meter_hourly":
                    e_row = session.execute(
                        select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.meter_reading_id == str(rec_id))
                    ).scalars().first()
                    if e_row:
                        plant_id = e_row.plant_id
                        b_key = f"{e_row.plant_id}:{e_row.meter_id}:{e_row.timestamp.isoformat()}"
                        raw_values = _serialize_record_for_revision(e_row, tbl)
                        up_id = up_id or e_row.upload_id
                elif tbl == "fact_hourly_production":
                    p_row = session.execute(
                        select(FactHourlyProduction).where(FactHourlyProduction.event_id == str(rec_id))
                    ).scalars().first()
                    if p_row:
                        plant_id = p_row.plant_id
                        b_key = f"{p_row.plant_id}:{p_row.line_id}:{p_row.event_ts.isoformat()}"
                        raw_values = _serialize_record_for_revision(p_row, tbl)
                        up_id = up_id or p_row.upload_id

                if raw_values:
                    rev_id = f"REV-{tbl[:4].upper()}-{str(rec_id)[:16]}-1"
                    new_rev = FactSourceRevision(
                        revision_id=rev_id,
                        source_table=tbl,
                        source_record_id=str(rec_id),
                        business_key=b_key,
                        plant_id=plant_id,
                        upload_id=up_id,
                        revision_timestamp=now,
                        source_values_json=json.dumps(raw_values, default=str),
                        is_current=True,
                    )
                    session.add(new_rev)
                    session.flush()

        if rev_id and primary_rev_id is None:
            primary_rev_id = rev_id

        # Insert FindingOccurrenceSource link
        occ_src = FindingOccurrenceSource(
            occurrence_id=occ_id,
            revision_id=rev_id,
            source_table=tbl,
            source_record_id=str(rec_id),
            role=role,
            upload_id=up_id,
        )
        session.add(occ_src)

    return primary_rev_id


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

    qual_status = anomaly.get("qualification_status")
    raw_trust = str(anomaly.get("evidence_classification") or anomaly.get("trust_level") or "").strip().upper()
    if raw_trust in ("TRUSTED", "HIGH", "QUALIFIED"):
        trust_lvl = "TRUSTED"
    elif raw_trust in ("TENTATIVE", "MEDIUM", "PARTIAL"):
        trust_lvl = "TENTATIVE"
    elif raw_trust in ("INCONCLUSIVE",):
        trust_lvl = "INCONCLUSIVE"
    elif raw_trust in ("DISQUALIFIED", "LOW", "UNQUALIFIED", "NOT_QUALIFIED"):
        trust_lvl = "DISQUALIFIED"
    elif raw_trust:
        trust_lvl = raw_trust
    else:
        trust_lvl = "TRUSTED"
    conf = anomaly.get("confidence")
    r_codes = json.dumps(anomaly.get("reason_codes"), default=str) if anomaly.get("reason_codes") else None
    comp_window = anomaly.get("comparison_window")

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
                    latest_qualification_status=qual_status,
                    latest_trust_level=trust_lvl,
                    latest_confidence=conf,
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
                    revision_id=None,
                    qualification_status=qual_status,
                    trust_level=trust_lvl,
                    confidence=conf,
                    reason_codes=r_codes,
                    comparison_window=comp_window,
                    recorded_at=now,
                )
                session.add(occurrence)
                session.flush()

                primary_rev_id = _pin_occurrence_sources(session, occ_id, anomaly, upload_id, now)
                if primary_rev_id:
                    occurrence.revision_id = primary_rev_id
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
        if qual_status:
            finding.latest_qualification_status = qual_status
        if trust_lvl:
            finding.latest_trust_level = trust_lvl
        if conf:
            finding.latest_confidence = conf
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
                revision_id=None,
                qualification_status=qual_status,
                trust_level=trust_lvl,
                confidence=conf,
                reason_codes=r_codes,
                comparison_window=comp_window,
                recorded_at=now,
            )
            session.add(occurrence)
            session.flush()

            primary_rev_id = _pin_occurrence_sources(session, occ_id, anomaly, upload_id, now)
            if primary_rev_id:
                occurrence.revision_id = primary_rev_id
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
        for detector_key in (
            "statistical_zscore",
            "rolling_baseline",
            "low_power_factor",
            "zero_production_standby",
            "persistent_baseload",
            "zero_output_restart",
        ):
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


def _serialize_energy_record(rec: FactEnergyMeterHourly) -> Dict[str, Any]:
    """Serialize physical fact_energy_meter_hourly record for provenance inspection."""
    return {
        "meter_reading_id": rec.meter_reading_id,
        "timestamp": rec.timestamp.isoformat() if rec.timestamp else None,
        "date": rec.date.isoformat() if rec.date else None,
        "plant_id": rec.plant_id,
        "meter_id": rec.meter_id,
        "area": rec.area,
        "energy_source": rec.energy_source,
        "consumption_kwh": float(rec.consumption_kwh) if rec.consumption_kwh is not None else None,
        "demand_kw": float(rec.demand_kw) if rec.demand_kw is not None else None,
        "power_factor": float(rec.power_factor) if rec.power_factor is not None else None,
        "tariff_inr_per_kwh": float(rec.tariff_inr_per_kwh) if rec.tariff_inr_per_kwh is not None else None,
        "cost_inr": float(rec.cost_inr) if rec.cost_inr is not None else None,
        "co2e_kg": float(rec.co2e_kg) if rec.co2e_kg is not None else None,
        "reading_quality": rec.reading_quality,
        "upload_id": rec.upload_id,
        "ingested_at": rec.ingested_at.isoformat() if rec.ingested_at else None,
    }


def _serialize_production_record(rec: FactHourlyProduction) -> Dict[str, Any]:
    """Serialize physical fact_hourly_production record for provenance inspection."""
    return {
        "event_id": rec.event_id,
        "event_ts": rec.event_ts.isoformat() if rec.event_ts else None,
        "event_date": rec.event_date.isoformat() if rec.event_date else None,
        "year": rec.year,
        "month": rec.month,
        "week": rec.week,
        "day": rec.day,
        "hour": rec.hour,
        "plant_id": rec.plant_id,
        "line_id": rec.line_id,
        "shift_id": rec.shift_id,
        "product_id": rec.product_id,
        "production_order_id": rec.production_order_id,
        "target_qty": rec.target_qty,
        "actual_qty": rec.actual_qty,
        "good_qty": rec.good_qty,
        "reject_qty": rec.reject_qty,
        "rework_qty": rec.rework_qty,
        "downtime_min": rec.downtime_min,
        "downtime_reason": rec.downtime_reason,
        "operator_team": rec.operator_team,
        "source_system": rec.source_system,
        "data_quality": rec.data_quality,
        "upload_id": rec.upload_id,
        "ingested_at": rec.ingested_at.isoformat() if rec.ingested_at else None,
    }


def _serialize_upload_history(u: UploadHistory) -> Dict[str, Any]:
    """Serialize upload batch audit trail record for provenance inspection."""
    return {
        "upload_id": u.upload_id,
        "filename": u.filename,
        "file_format": u.file_format,
        "sheet_name": u.sheet_name,
        "report_type": u.report_type,
        "reporting_date": u.reporting_date.isoformat() if u.reporting_date else None,
        "uploaded_at": u.uploaded_at.isoformat() if u.uploaded_at else None,
        "file_size_bytes": u.file_size_bytes,
        "total_rows": u.total_rows,
        "valid_rows": u.valid_rows,
        "rejected_rows": u.rejected_rows,
        "duplicate_rows": u.duplicate_rows,
        "status": u.status,
        "mode": u.mode,
        "is_available": True,
    }


def get_occurrence_provenance(
    session: Session,
    finding_id: str,
    occurrence_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve end-to-end read-only provenance drill-down for a finding occurrence.

    Trace path:
    Finding -> Occurrence -> Source Record(s) -> Upload History

    Adheres strictly to constraints:
    - Never accepts arbitrary table names or SQL; strictly allowlists fact_energy_meter_hourly and fact_hourly_production.
    - Resolves source records using actual primary key identifiers (meter_reading_id, event_id).
    - Batch queries database tables to avoid N+1 queries.
    - Explicitly categorizes lineage states: AVAILABLE, MULTI_SOURCE, LEGACY_UNLINKED, SOURCE_MISSING, UPLOAD_UNAVAILABLE.
    - Preserves and exposes semantic roles for composite multi-source occurrences.
    """
    stmt = (
        select(OperationalFinding)
        .where(OperationalFinding.finding_id == finding_id)
        .options(selectinload(OperationalFinding.occurrences))
    )
    finding = session.execute(stmt).scalar_one_or_none()
    if not finding:
        raise KeyError(f"Finding '{finding_id}' not found.")

    target_occ: Optional[FindingOccurrence] = None
    if occurrence_id:
        for occ in (finding.occurrences or []):
            if occ.occurrence_id == occurrence_id:
                target_occ = occ
                break
        if not target_occ:
            other_occ = session.execute(
                select(FindingOccurrence).where(FindingOccurrence.occurrence_id == occurrence_id)
            ).scalar_one_or_none()
            if other_occ:
                raise ValueError(
                    f"Occurrence '{occurrence_id}' belongs to finding '{other_occ.finding_id}', not '{finding_id}'."
                )
            raise ValueError(f"Occurrence '{occurrence_id}' not found for finding '{finding_id}'.")
    else:
        if finding.occurrences:
            sorted_occs = sorted(
                finding.occurrences,
                key=lambda o: o.occurrence_ts or datetime.min,
                reverse=True,
            )
            target_occ = sorted_occs[0]
        else:
            now_iso = datetime.now(timezone.utc).isoformat()
            return {
                "finding_id": finding.finding_id,
                "occurrence_id": "NONE",
                "occurrence_ts": finding.first_detected_at.isoformat() if finding.first_detected_at else now_iso,
                "anomaly_type": finding.anomaly_type,
                "severity": finding.severity,
                "detector_name": finding.anomaly_type,
                "detector_version": "1.0.0",
                "overall_lineage_state": "LEGACY_UNLINKED",
                "lineage_explanation": "Historical finding has no recorded occurrences or source telemetry links.",
                "is_multi_source": False,
                "source_records": [],
                "retrieved_at": now_iso,
            }

    c_flags: Dict[str, Any] = {}
    if target_occ.context_flags_json:
        try:
            c_flags = json.loads(target_occ.context_flags_json)
        except Exception:
            c_flags = {}

    needs_energy_lookup = False
    needs_prod_lookup = False

    # 1. First check pinned database sources in finding_occurrence_sources
    db_sources = session.execute(
        select(FindingOccurrenceSource)
        .where(FindingOccurrenceSource.occurrence_id == target_occ.occurrence_id)
        .order_by(FindingOccurrenceSource.id.asc())
    ).scalars().all()

    specs: List[Dict[str, Any]] = []
    if db_sources:
        for ds in db_sources:
            specs.append({
                "source_table": ds.source_table,
                "source_record_id": ds.source_record_id,
                "upload_id": ds.upload_id or target_occ.upload_id,
                "role": ds.role,
                "revision_id": ds.revision_id,
            })
    elif target_occ.revision_id:
        specs.append({
            "source_table": target_occ.source_table or "fact_energy_meter_hourly",
            "source_record_id": target_occ.source_record_id,
            "upload_id": target_occ.upload_id,
            "role": "PRIMARY_OBSERVATION",
            "revision_id": target_occ.revision_id,
        })
    elif c_flags.get("source_records") and isinstance(c_flags["source_records"], list):
        specs = list(c_flags["source_records"])
    elif target_occ.source_table and target_occ.source_record_id:
        specs = [
            {
                "source_table": target_occ.source_table,
                "source_record_id": target_occ.source_record_id,
                "upload_id": target_occ.upload_id,
                "role": "PRIMARY_OBSERVATION",
                "revision_id": None,
            }
        ]
    else:
        # Fallback to direct keys in context_flags if present
        if c_flags.get("meter_reading_id"):
            specs.append({
                "source_table": "fact_energy_meter_hourly",
                "source_record_id": str(c_flags["meter_reading_id"]),
                "upload_id": c_flags.get("upload_id") or target_occ.upload_id,
                "role": "PROCESS_ENERGY_MEASUREMENT",
                "revision_id": None,
            })
        if c_flags.get("event_id"):
            specs.append({
                "source_table": "fact_hourly_production",
                "source_record_id": str(c_flags["event_id"]),
                "upload_id": c_flags.get("upload_id") or target_occ.upload_id,
                "role": "PRODUCTION_ZERO_OUTPUT_EVENT",
                "revision_id": None,
            })

        has_energy = any(s.get("source_table") == "fact_energy_meter_hourly" for s in specs)
        has_prod = any(s.get("source_table") == "fact_hourly_production" for s in specs)
        if not has_energy and finding.meter_id and target_occ.occurrence_ts:
            needs_energy_lookup = True
        if not has_prod and finding.line_id and target_occ.occurrence_ts and finding.anomaly_type == "ZERO_PRODUCTION_STANDBY_ENERGY":
            needs_prod_lookup = True

    ALLOWLISTED_TABLES = {"fact_energy_meter_hourly", "fact_hourly_production"}

    # Extract distinct IDs for batch queries to prevent N+1 overhead
    energy_ids = list({
        str(s["source_record_id"]).strip()
        for s in specs
        if s.get("source_table") == "fact_energy_meter_hourly"
        and s.get("source_record_id")
        and str(s.get("source_record_id")).strip()
    })
    prod_ids = list({
        str(s["source_record_id"]).strip()
        for s in specs
        if s.get("source_table") == "fact_hourly_production"
        and s.get("source_record_id")
        and str(s.get("source_record_id")).strip()
    })

    energy_map: Dict[str, FactEnergyMeterHourly] = {}
    fallback_energy_rec: Optional[FactEnergyMeterHourly] = None
    if energy_ids:
        e_stmt = select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.meter_reading_id.in_(energy_ids))
        for r in session.execute(e_stmt).scalars().all():
            energy_map[r.meter_reading_id] = r
    elif needs_energy_lookup and finding.meter_id and target_occ.occurrence_ts:
        e_sub = select(FactEnergyMeterHourly.meter_reading_id).where(
            FactEnergyMeterHourly.meter_id == finding.meter_id,
            FactEnergyMeterHourly.timestamp == target_occ.occurrence_ts,
        )
        e_stmt = select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.meter_reading_id.in_(e_sub))
        for r in session.execute(e_stmt).scalars().all():
            energy_map[r.meter_reading_id] = r
            fallback_energy_rec = r

    if fallback_energy_rec and not any(s.get("source_table") == "fact_energy_meter_hourly" for s in specs):
        specs.append({
            "source_table": "fact_energy_meter_hourly",
            "source_record_id": fallback_energy_rec.meter_reading_id,
            "upload_id": fallback_energy_rec.upload_id or target_occ.upload_id,
            "role": "PROCESS_ENERGY_MEASUREMENT" if finding.anomaly_type == "ZERO_PRODUCTION_STANDBY_ENERGY" else "PRIMARY_OBSERVATION",
        })

    prod_map: Dict[str, FactHourlyProduction] = {}
    fallback_prod_rec: Optional[FactHourlyProduction] = None
    if prod_ids:
        p_stmt = select(FactHourlyProduction).where(FactHourlyProduction.event_id.in_(prod_ids))
        for r in session.execute(p_stmt).scalars().all():
            prod_map[r.event_id] = r
    elif needs_prod_lookup and finding.line_id and target_occ.occurrence_ts:
        p_sub = select(FactHourlyProduction.event_id).where(
            FactHourlyProduction.line_id == finding.line_id,
            FactHourlyProduction.event_ts == target_occ.occurrence_ts,
        )
        p_stmt = select(FactHourlyProduction).where(FactHourlyProduction.event_id.in_(p_sub))
        for r in session.execute(p_stmt).scalars().all():
            prod_map[r.event_id] = r
            fallback_prod_rec = r

    if fallback_prod_rec and not any(s.get("source_table") == "fact_hourly_production" for s in specs):
        specs.append({
            "source_table": "fact_hourly_production",
            "source_record_id": fallback_prod_rec.event_id,
            "upload_id": fallback_prod_rec.upload_id or target_occ.upload_id,
            "role": "PRODUCTION_ZERO_OUTPUT_EVENT",
        })

    # Collect upload IDs for batch lookup in upload_history
    upload_ids: Set[str] = set()
    for s in specs:
        up = s.get("upload_id")
        if up and str(up).strip():
            upload_ids.add(str(up).strip())
    if target_occ.upload_id and str(target_occ.upload_id).strip():
        upload_ids.add(str(target_occ.upload_id).strip())
    for r in energy_map.values():
        if r.upload_id and str(r.upload_id).strip():
            upload_ids.add(str(r.upload_id).strip())
    for r in prod_map.values():
        if r.upload_id and str(r.upload_id).strip():
            upload_ids.add(str(r.upload_id).strip())

    upload_map: Dict[str, UploadHistory] = {}
    if upload_ids:
        u_stmt = select(UploadHistory).where(UploadHistory.upload_id.in_(list(upload_ids)))
        for u in session.execute(u_stmt).scalars().all():
            upload_map[u.upload_id] = u

    resolved_records: List[Dict[str, Any]] = []

    for spec in specs:
        table_name = str(spec.get("source_table", "")).strip()
        rec_id = str(spec.get("source_record_id", "")).strip() if spec.get("source_record_id") else None
        role = spec.get("role")

        if table_name not in ALLOWLISTED_TABLES:
            resolved_records.append({
                "source_table": table_name or "UNKNOWN",
                "source_record_id": rec_id,
                "upload_id": spec.get("upload_id") or target_occ.upload_id,
                "role": role,
                "reporting_timestamp": None,
                "plant_id": finding.plant_id,
                "entity_id": finding.meter_id or finding.line_id,
                "entity_type": "METER" if finding.meter_id else ("LINE" if finding.line_id else None),
                "record_status": "UNSUPPORTED_TABLE",
                "raw_data": None,
                "upload": None,
                "upload_status": "UNAVAILABLE",
                "lineage_state": "SOURCE_MISSING",
                "lineage_note": f"Source table '{table_name}' is not in the allowlisted schema tables.",
            })
            continue

        raw_obj: Optional[Dict[str, Any]] = None
        reporting_ts: Optional[str] = None
        plant_id = finding.plant_id
        entity_id: Optional[str] = None
        entity_type: Optional[str] = None
        found_upload_id = spec.get("upload_id") or target_occ.upload_id

        if table_name == "fact_energy_meter_hourly":
            entity_type = "METER"
            e_rec = energy_map.get(rec_id) if rec_id else None
            if e_rec:
                raw_obj = _serialize_energy_record(e_rec)
                reporting_ts = e_rec.timestamp.isoformat() if e_rec.timestamp else None
                plant_id = e_rec.plant_id
                entity_id = e_rec.meter_id
                if e_rec.upload_id:
                    found_upload_id = e_rec.upload_id
        elif table_name == "fact_hourly_production":
            entity_type = "LINE"
            p_rec = prod_map.get(rec_id) if rec_id else None
            if p_rec:
                raw_obj = _serialize_production_record(p_rec)
                reporting_ts = p_rec.event_ts.isoformat() if p_rec.event_ts else None
                plant_id = p_rec.plant_id
                entity_id = p_rec.line_id
                if p_rec.upload_id:
                    found_upload_id = p_rec.upload_id

        rev = None
        rev_id = spec.get("revision_id")
        if rev_id:
            rev = session.execute(
                select(FactSourceRevision).where(FactSourceRevision.revision_id == str(rev_id))
            ).scalars().first()

        has_newer_rev = False
        current_corrected = None
        rev_timestamp = None

        if rev:
            try:
                raw_obj = json.loads(rev.source_values_json)
            except Exception:
                raw_obj = {}
            rev_timestamp = rev.revision_timestamp.isoformat() if rev.revision_timestamp else None
            found_upload_id = rev.upload_id or spec.get("upload_id") or target_occ.upload_id
            reporting_ts = raw_obj.get("timestamp") or raw_obj.get("event_ts")
            record_status = "FOUND"
            lineage_state = "AVAILABLE"
            lineage_note = "Original source revision pinned at detection verified in database."

            # Check if newer corrected revision exists
            newer_rev = session.execute(
                select(FactSourceRevision).where(
                    FactSourceRevision.source_table == rev.source_table,
                    FactSourceRevision.business_key == rev.business_key,
                    FactSourceRevision.id > rev.id,
                    FactSourceRevision.is_current == True,
                )
            ).scalars().first()
            if newer_rev:
                has_newer_rev = True
                try:
                    current_corrected = json.loads(newer_rev.source_values_json)
                except Exception:
                    current_corrected = {}
                current_corrected["_revision_id"] = newer_rev.revision_id
                current_corrected["_upload_id"] = newer_rev.upload_id
                current_corrected["_revision_timestamp"] = (
                    newer_rev.revision_timestamp.isoformat() if newer_rev.revision_timestamp else None
                )

            if found_upload_id and found_upload_id in upload_map:
                up_info = _serialize_upload_history(upload_map[found_upload_id])
                up_status = "AVAILABLE"
            else:
                up_info = None
                up_status = "UNAVAILABLE_HISTORICAL" if not found_upload_id else "UPLOAD_NOT_FOUND"

        else:
            # Legacy occurrence: no pinned revision
            # Handle legacy occurrences honestly
            rev_id = None
            rev_timestamp = None
            has_newer_rev = False
            current_corrected = None

            if raw_obj is not None:
                record_status = "FOUND"
                lineage_state = "ORIGINAL_REVISION_UNAVAILABLE"
                lineage_note = "Original revision unavailable; current row with matching ID is insufficient proof of historical identity."
                if found_upload_id and found_upload_id in upload_map:
                    up_info = _serialize_upload_history(upload_map[found_upload_id])
                    up_status = "AVAILABLE"
                else:
                    up_info = None
                    up_status = "UNAVAILABLE_HISTORICAL" if not found_upload_id else "UPLOAD_NOT_FOUND"
            else:
                record_status = "MISSING"
                up_info = None
                up_status = "UNAVAILABLE"
                lineage_state = "SOURCE_MISSING"
                lineage_note = f"Source record ID '{rec_id}' was not found in database table '{table_name}'."

        resolved_records.append({
            "source_table": table_name,
            "source_record_id": rec_id,
            "upload_id": found_upload_id,
            "role": role,
            "reporting_timestamp": reporting_ts,
            "plant_id": plant_id,
            "entity_id": entity_id or (finding.meter_id if entity_type == "METER" else finding.line_id),
            "entity_type": entity_type,
            "record_status": record_status,
            "raw_data": raw_obj,
            "upload": up_info,
            "upload_status": up_status,
            "lineage_state": lineage_state,
            "lineage_note": lineage_note,
            "revision_id": rev_id,
            "revision_timestamp": rev_timestamp,
            "has_newer_revision": has_newer_rev,
            "current_corrected_reading": current_corrected,
        })

    is_multi = len(resolved_records) > 1
    if len(resolved_records) == 0:
        overall_lineage = "LEGACY_UNLINKED"
        lineage_explanation = "Historical finding has no stored source record identity. Ingested prior to telemetry tracking."
    elif any(r.get("lineage_state") == "ORIGINAL_REVISION_UNAVAILABLE" for r in resolved_records) and not is_multi:
        overall_lineage = "ORIGINAL_REVISION_UNAVAILABLE"
        lineage_explanation = "Original revision unavailable; current row with matching ID is insufficient proof of historical identity."
    elif is_multi:
        overall_lineage = "MULTI_SOURCE"
        lineage_explanation = (
            f"Composite anomaly cross-correlating {len(resolved_records)} discrete source telemetry records "
            "across production and energy streams."
        )
    else:
        single = resolved_records[0]
        overall_lineage = single["lineage_state"]
        lineage_explanation = single["lineage_note"] or "Single-source observation verified in database."

    det_ver = target_occ.detector_version or c_flags.get("detector_version") or "1.0.0"
    det_name = c_flags.get("detector_name") or finding.anomaly_type

    r_codes_list: List[str] = []
    if target_occ.reason_codes:
        try:
            parsed = json.loads(target_occ.reason_codes)
            if isinstance(parsed, list):
                r_codes_list = [str(x) for x in parsed]
            else:
                r_codes_list = [str(parsed)]
        except Exception:
            r_codes_list = [target_occ.reason_codes]

    return {
        "finding_id": finding.finding_id,
        "occurrence_id": target_occ.occurrence_id,
        "occurrence_ts": target_occ.occurrence_ts.isoformat() if target_occ.occurrence_ts else "",
        "anomaly_type": finding.anomaly_type,
        "severity": target_occ.severity or finding.severity,
        "detector_name": det_name,
        "detector_version": det_ver,
        "overall_lineage_state": overall_lineage,
        "lineage_explanation": lineage_explanation,
        "is_multi_source": is_multi,
        "qualification_status": target_occ.qualification_status,
        "trust_level": target_occ.trust_level,
        "confidence": target_occ.confidence,
        "reason_codes": r_codes_list,
        "comparison_window": target_occ.comparison_window,
        "has_newer_revision": any(r.get("has_newer_revision") for r in resolved_records),
        "source_records": resolved_records,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }

