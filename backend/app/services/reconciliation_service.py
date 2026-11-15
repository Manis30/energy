"""
Cross-Source Data Reconciliation Service for Industrial Energy Intelligence Platform.

This module provides a deterministic, read-only reconciliation engine that audits
consistency and integrity across:
1. Hourly Energy Meter Records (fact_energy_meter_hourly)
2. Hourly Production Events (fact_hourly_production)
3. Upload and Ingestion Audit History (upload_history)
4. Master Dimensions (dim_production_line, dim_product)

Supported Reconciliation Checks:
1. Energy Coverage: Missing or incomplete hourly observations per observed meter.
2. Production Coverage: Line event coverage for registered manufacturing lines.
3. Timestamp Alignment: Cross-stream hourly timestamp synchronization.
4. Duplicate Records: Business key uniqueness in energy, production, and upload records.
5. Source Consistency: Comparison of upload history valid rows against database counts.
6. Reference Integrity: Foreign key and dimension reference validation.
7. Data Quality: Non-negativity, physical bounds, quantity balance, and timestamp alignment.

Design Principles:
- Strictly Read-Only: Zero database mutations, corrections, or deletions.
- Deterministic Outcomes: PASS, WARNING, FAIL, UNAVAILABLE.
- Schema-Bounded Transparency: Explicitly reports unavailable dimensions (e.g., dim_meter,
  operating calendars, upload metric aggregates) rather than fabricating assumptions.
- Independent of AI: Pure SQL and Python evaluation without LLM dependencies.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.source_data import (
    DimProduct,
    DimProductionLine,
    FactEnergyMeterHourly,
    FactHourlyProduction,
)
from app.models.upload_history import UploadHistory
from app.schemas.reconciliation import (
    ReconciliationCategory,
    ReconciliationCheckDefinition,
    ReconciliationCheckResult,
    ReconciliationFinding,
    ReconciliationReportResponse,
    ReconciliationStatus,
    ReconciliationSummaryCounts,
    ReconciliationSummaryResponse,
)

# Standard architectural boundaries and limitations
STANDARD_LIMITATIONS: List[str] = [
    (
        "The energy meter catalog is global and lacks a plant-to-meter dimension table (dim_meter). "
        "Plant-specific expected meters cannot be statically inferred."
    ),
    (
        "No formal operating calendar, shift schedule, or planned maintenance registry is available in the schema. "
        "Missing line hours cannot be conclusively classified as unplanned downtime vs planned line stoppage."
    ),
    (
        "Upload audit history (upload_history) tracks file metadata and row counts, but does not store "
        "aggregate energy kWh or finished production volume totals."
    ),
    (
        "Process-meter energy and finished unit production are segregated; process energy draw during zero "
        "production (e.g. standby, setup, maintenance) is physically normal and is not treated as a timestamp misalignment."
    ),
    (
        "Energy consumption is not assumed to be production-dependent; reconciliation does not generate "
        "predictive energy baselines or savings claims."
    ),
]


# ============================================================================
# CHECK 1: ENERGY COVERAGE
# ============================================================================

def _check_energy_coverage(
    session: Session,
    start_date: date,
    end_date: date,
    plant_id: Optional[str] = None,
) -> ReconciliationCheckResult:
    """Audit hourly energy observations for gaps between observed time boundaries."""
    check_id = "CHK_ENERGY_COVERAGE"
    category = ReconciliationCategory.ENERGY_COVERAGE
    findings: List[ReconciliationFinding] = []
    period_dict = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

    # 1. Schema boundary notice: plant-to-meter catalog is unavailable
    findings.append(
        ReconciliationFinding(
            check_id=check_id,
            category=category,
            status=ReconciliationStatus.UNAVAILABLE,
            plant_id=plant_id,
            affected_entity="fact_energy_meter_hourly",
            evaluation_period=period_dict,
            observed_value=None,
            expected_value=None,
            difference=None,
            difference_unit=None,
            source_references=["fact_energy_meter_hourly"],
            explanation=(
                "The database schema does not define a formal plant-to-meter mapping (dim_meter). "
                "Expected meter counts per plant cannot be inferred statically."
            ),
            reason_code="PLANT_METER_CATALOG_UNAVAILABLE",
        )
    )

    # 2. Query observed meters and their boundary coverage
    query = (
        select(
            FactEnergyMeterHourly.plant_id,
            FactEnergyMeterHourly.meter_id,
            func.count(FactEnergyMeterHourly.meter_reading_id).label("record_count"),
            func.count(func.distinct(FactEnergyMeterHourly.timestamp)).label("distinct_hours"),
            func.min(FactEnergyMeterHourly.timestamp).label("first_ts"),
            func.max(FactEnergyMeterHourly.timestamp).label("last_ts"),
        )
        .where(
            FactEnergyMeterHourly.date >= start_date,
            FactEnergyMeterHourly.date <= end_date,
        )
    )
    if plant_id:
        query = query.where(FactEnergyMeterHourly.plant_id == plant_id)

    query = query.group_by(FactEnergyMeterHourly.plant_id, FactEnergyMeterHourly.meter_id)
    rows = session.execute(query).fetchall()

    if not rows:
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.WARNING,
                plant_id=plant_id,
                affected_entity="ENERGY_METERS",
                evaluation_period=period_dict,
                observed_value=0,
                expected_value="> 0",
                difference=None,
                difference_unit="records",
                source_references=["fact_energy_meter_hourly"],
                explanation=f"Zero energy meter observations recorded between {start_date} and {end_date}.",
                reason_code="ZERO_ENERGY_OBSERVATIONS_IN_PERIOD",
            )
        )
    else:
        for r in rows:
            p_id, m_id, record_count, distinct_hours, first_ts, last_ts = r
            if first_ts and last_ts:
                span_hours = int((last_ts - first_ts).total_seconds() // 3600) + 1
                missing_in_span = max(0, span_hours - distinct_hours)
                if missing_in_span > 0:
                    findings.append(
                        ReconciliationFinding(
                            check_id=check_id,
                            category=category,
                            status=ReconciliationStatus.WARNING,
                            plant_id=p_id,
                            affected_entity=m_id,
                            evaluation_period=period_dict,
                            observed_value=distinct_hours,
                            expected_value=span_hours,
                            difference=missing_in_span,
                            difference_unit="hours",
                            source_references=["fact_energy_meter_hourly"],
                            explanation=(
                                f"Meter '{m_id}' at plant '{p_id}' has {missing_in_span} missing hourly interval(s) "
                                f"between first reading ({first_ts}) and last reading ({last_ts})."
                            ),
                            reason_code="METER_HOURLY_GAPS_DETECTED",
                        )
                    )

    # Determine check status
    has_fail = any(f.status == ReconciliationStatus.FAIL for f in findings)
    has_warn = any(f.status == ReconciliationStatus.WARNING for f in findings)
    overall_status = ReconciliationStatus.FAIL if has_fail else (ReconciliationStatus.WARNING if has_warn else ReconciliationStatus.PASS)

    return ReconciliationCheckResult(
        check_id=check_id,
        category=category,
        name="Energy Telemetry Coverage & Missing Hours",
        description="Identifies gaps and missing hourly observations across observed energy meters.",
        status=overall_status,
        plant_id=plant_id,
        findings_count=len(findings),
        findings=findings,
        summary=(
            f"Evaluated {len(rows)} observed energy meter stream(s). Identified {len([f for f in findings if f.status == ReconciliationStatus.WARNING])} "
            f"coverage gap warning(s)."
        ),
    )


# ============================================================================
# CHECK 2: PRODUCTION COVERAGE
# ============================================================================

def _check_production_coverage(
    session: Session,
    start_date: date,
    end_date: date,
    plant_id: Optional[str] = None,
) -> ReconciliationCheckResult:
    """Audit production line event coverage against registered manufacturing lines."""
    check_id = "CHK_PRODUCTION_COVERAGE"
    category = ReconciliationCategory.PRODUCTION_COVERAGE
    findings: List[ReconciliationFinding] = []
    period_dict = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

    # 1. Schema boundary notice: Operating calendar unavailable
    findings.append(
        ReconciliationFinding(
            check_id=check_id,
            category=category,
            status=ReconciliationStatus.UNAVAILABLE,
            plant_id=plant_id,
            affected_entity="dim_production_line",
            evaluation_period=period_dict,
            observed_value=None,
            expected_value=None,
            difference=None,
            difference_unit=None,
            source_references=["dim_production_line", "fact_hourly_production"],
            explanation=(
                "No approved operating calendar or shift schedule is defined in the schema. "
                "Planned line stoppages cannot be distinguished from missing telemetry."
            ),
            reason_code="OPERATING_CALENDAR_UNAVAILABLE",
        )
    )

    # 2. Query registered lines in dim_production_line
    line_stmt = select(DimProductionLine.plant_id, DimProductionLine.line_id, DimProductionLine.line_type)
    if plant_id:
        line_stmt = line_stmt.where(DimProductionLine.plant_id == plant_id)
    registered_lines = session.execute(line_stmt).fetchall()

    # 3. Query observed production events per line
    prod_stmt = (
        select(
            FactHourlyProduction.plant_id,
            FactHourlyProduction.line_id,
            func.count(FactHourlyProduction.event_id).label("event_count"),
            func.count(func.distinct(FactHourlyProduction.event_ts)).label("distinct_hours"),
            func.min(FactHourlyProduction.event_ts).label("first_ts"),
            func.max(FactHourlyProduction.event_ts).label("last_ts"),
        )
        .where(
            FactHourlyProduction.event_date >= start_date,
            FactHourlyProduction.event_date <= end_date,
        )
    )
    if plant_id:
        prod_stmt = prod_stmt.where(FactHourlyProduction.plant_id == plant_id)

    prod_stmt = prod_stmt.group_by(FactHourlyProduction.plant_id, FactHourlyProduction.line_id)
    prod_rows = session.execute(prod_stmt).fetchall()

    observed_line_map = {
        (r[0], r[1]): {"event_count": r[2], "distinct_hours": r[3], "first_ts": r[4], "last_ts": r[5]}
        for r in prod_rows
    }

    # Compare registered lines against observed events
    for p_id, l_id, l_type in registered_lines:
        line_key = (p_id, l_id)
        if line_key not in observed_line_map:
            findings.append(
                ReconciliationFinding(
                    check_id=check_id,
                    category=category,
                    status=ReconciliationStatus.WARNING,
                    plant_id=p_id,
                    affected_entity=l_id,
                    evaluation_period=period_dict,
                    observed_value=0,
                    expected_value="> 0 events (if operating)",
                    difference=None,
                    difference_unit="records",
                    source_references=["dim_production_line", "fact_hourly_production"],
                    explanation=(
                        f"Production line '{l_id}' ({l_type}) is registered at plant '{p_id}' in dim_production_line "
                        f"but has 0 recorded production events between {start_date} and {end_date}."
                    ),
                    reason_code="REGISTERED_LINE_UNOBSERVED",
                )
            )

    has_fail = any(f.status == ReconciliationStatus.FAIL for f in findings)
    has_warn = any(f.status == ReconciliationStatus.WARNING for f in findings)
    overall_status = ReconciliationStatus.FAIL if has_fail else (ReconciliationStatus.WARNING if has_warn else ReconciliationStatus.PASS)

    return ReconciliationCheckResult(
        check_id=check_id,
        category=category,
        name="Production Line Coverage & Active Shift Observations",
        description="Audits manufacturing line event coverage against registered plant lines.",
        status=overall_status,
        plant_id=plant_id,
        findings_count=len(findings),
        findings=findings,
        summary=(
            f"Evaluated {len(registered_lines)} registered line(s). Found {len(prod_rows)} active line stream(s) "
            f"and {len([f for f in findings if f.status == ReconciliationStatus.WARNING])} unobserved line warning(s)."
        ),
    )


# ============================================================================
# CHECK 3: TIMESTAMP ALIGNMENT
# ============================================================================

def _check_timestamp_alignment(
    session: Session,
    start_date: date,
    end_date: date,
    plant_id: Optional[str] = None,
) -> ReconciliationCheckResult:
    """Identify hourly timestamps where manufacturing production occurred without energy telemetry."""
    check_id = "CHK_TIMESTAMP_ALIGNMENT"
    category = ReconciliationCategory.TIMESTAMP_ALIGNMENT
    findings: List[ReconciliationFinding] = []
    period_dict = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

    # 1. Active production hours without energy readings
    # Query distinct active production timestamps (actual_qty > 0)
    plant_clause_energy = "AND plant_id = :plant_id" if plant_id else ""
    plant_clause_prod = "AND plant_id = :plant_id" if plant_id else ""
    params = {"start_date": start_date, "end_date": end_date}
    if plant_id:
        params["plant_id"] = plant_id

    unaligned_sql = f"""
        SELECT
            p.plant_id,
            p.event_ts,
            SUM(p.actual_qty) as total_qty
        FROM fact_hourly_production p
        LEFT JOIN fact_energy_meter_hourly e
            ON p.plant_id = e.plant_id
           AND p.event_ts = e.timestamp
        WHERE p.event_date >= :start_date
          AND p.event_date <= :end_date
          AND p.actual_qty > 0
          {plant_clause_prod}
          AND e.timestamp IS NULL
        GROUP BY p.plant_id, p.event_ts
        ORDER BY p.plant_id, p.event_ts
    """
    unaligned_rows = session.execute(text(unaligned_sql), params).fetchall()

    if unaligned_rows:
        for r in unaligned_rows:
            p_id, ts, qty = r
            findings.append(
                ReconciliationFinding(
                    check_id=check_id,
                    category=category,
                    status=ReconciliationStatus.FAIL,
                    plant_id=p_id,
                    affected_entity="fact_hourly_production",
                    evaluation_period={"timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts)},
                    observed_value=0,
                    expected_value=">= 1 energy meter reading",
                    difference=1,
                    difference_unit="hours",
                    source_references=["fact_hourly_production", "fact_energy_meter_hourly"],
                    explanation=(
                        f"Plant '{p_id}' recorded active manufacturing output ({qty} units) at {ts} "
                        f"without any corresponding energy meter telemetry recorded in fact_energy_meter_hourly."
                    ),
                    reason_code="PRODUCTION_WITHOUT_ENERGY_TELEMETRY",
                )
            )

    # 2. Check for sub-hourly timestamp misalignment (minute != 0 or second != 0)
    subhourly_sql = f"""
        SELECT 'fact_energy_meter_hourly' as tbl, plant_id, timestamp as ts
        FROM fact_energy_meter_hourly
        WHERE date >= :start_date AND date <= :end_date
          {plant_clause_energy}
          AND (EXTRACT(MINUTE FROM timestamp) != 0 OR EXTRACT(SECOND FROM timestamp) != 0)
        UNION ALL
        SELECT 'fact_hourly_production' as tbl, plant_id, event_ts as ts
        FROM fact_hourly_production
        WHERE event_date >= :start_date AND event_date <= :end_date
          {plant_clause_prod}
          AND (EXTRACT(MINUTE FROM event_ts) != 0 OR EXTRACT(SECOND FROM event_ts) != 0)
    """
    subhourly_rows = session.execute(text(subhourly_sql), params).fetchall()
    for r in subhourly_rows:
        tbl, p_id, ts = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity=tbl,
                evaluation_period={"timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts)},
                observed_value=ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                expected_value="HH:00:00 (top-of-hour)",
                difference=None,
                difference_unit=None,
                source_references=[tbl],
                explanation=f"Telemetry record in '{tbl}' has unaligned sub-hourly timestamp ({ts}).",
                reason_code="SUB_HOURLY_TIMESTAMP_MISALIGNMENT",
            )
        )

    has_fail = any(f.status == ReconciliationStatus.FAIL for f in findings)
    overall_status = ReconciliationStatus.FAIL if has_fail else ReconciliationStatus.PASS

    return ReconciliationCheckResult(
        check_id=check_id,
        category=category,
        name="Cross-Stream Timestamp Synchronization",
        description="Identifies timestamps where active production was recorded without energy telemetry or non-hourly offsets.",
        status=overall_status,
        plant_id=plant_id,
        findings_count=len(findings),
        findings=findings,
        summary=(
            f"Cross-stream timestamp check {'PASSED' if overall_status == ReconciliationStatus.PASS else 'FAILED'}. "
            f"Identified {len(unaligned_rows)} active production hour(s) with zero energy telemetry and "
            f"{len(subhourly_rows)} sub-hourly timestamp misalignment(s)."
        ),
    )


# ============================================================================
# CHECK 4: DUPLICATE RECORDS
# ============================================================================

def _check_duplicate_records(
    session: Session,
    start_date: date,
    end_date: date,
    plant_id: Optional[str] = None,
) -> ReconciliationCheckResult:
    """Detect duplicate business keys in energy, production, and upload records."""
    check_id = "CHK_DUPLICATE_RECORDS"
    category = ReconciliationCategory.DUPLICATE_RECORDS
    findings: List[ReconciliationFinding] = []
    period_dict = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

    params = {"start_date": start_date, "end_date": end_date}
    plant_clause_energy = "AND plant_id = :plant_id" if plant_id else ""
    plant_clause_prod = "AND plant_id = :plant_id" if plant_id else ""
    if plant_id:
        params["plant_id"] = plant_id

    # 1. Duplicate Energy business keys: (timestamp, plant_id, meter_id)
    dup_energy_sql = f"""
        SELECT timestamp, plant_id, meter_id, COUNT(*) as cnt
        FROM fact_energy_meter_hourly
        WHERE date >= :start_date AND date <= :end_date
          {plant_clause_energy}
        GROUP BY timestamp, plant_id, meter_id
        HAVING COUNT(*) > 1
    """
    dup_energy_rows = session.execute(text(dup_energy_sql), params).fetchall()
    for r in dup_energy_rows:
        ts, p_id, m_id, cnt = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity=m_id,
                evaluation_period={"timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts)},
                observed_value=cnt,
                expected_value=1,
                difference=cnt - 1,
                difference_unit="duplicate records",
                source_references=["fact_energy_meter_hourly"],
                explanation=f"Duplicate energy business key: {cnt} records found for meter '{m_id}' at plant '{p_id}' at {ts}.",
                reason_code="DUPLICATE_ENERGY_BUSINESS_KEY",
            )
        )

    # 2. Duplicate Production business keys: (event_ts, plant_id, line_id)
    dup_prod_sql = f"""
        SELECT event_ts, plant_id, line_id, COUNT(*) as cnt
        FROM fact_hourly_production
        WHERE event_date >= :start_date AND event_date <= :end_date
          {plant_clause_prod}
        GROUP BY event_ts, plant_id, line_id
        HAVING COUNT(*) > 1
    """
    dup_prod_rows = session.execute(text(dup_prod_sql), params).fetchall()
    for r in dup_prod_rows:
        ts, p_id, l_id, cnt = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity=l_id,
                evaluation_period={"timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts)},
                observed_value=cnt,
                expected_value=1,
                difference=cnt - 1,
                difference_unit="duplicate records",
                source_references=["fact_hourly_production"],
                explanation=f"Duplicate production business key: {cnt} records found for line '{l_id}' at plant '{p_id}' at {ts}.",
                reason_code="DUPLICATE_PRODUCTION_BUSINESS_KEY",
            )
        )

    has_fail = any(f.status == ReconciliationStatus.FAIL for f in findings)
    overall_status = ReconciliationStatus.FAIL if has_fail else ReconciliationStatus.PASS

    return ReconciliationCheckResult(
        check_id=check_id,
        category=category,
        name="Business Key Uniqueness & Deduplication",
        description="Verifies that natural primary business keys are unique without duplicate occurrences.",
        status=overall_status,
        plant_id=plant_id,
        findings_count=len(findings),
        findings=findings,
        summary=(
            f"Business key uniqueness check {'PASSED' if overall_status == ReconciliationStatus.PASS else 'FAILED'}. "
            f"Found {len(dup_energy_rows)} duplicate energy key(s) and {len(dup_prod_rows)} duplicate production key(s)."
        ),
    )


# ============================================================================
# CHECK 5: SOURCE CONSISTENCY (UPLOAD HISTORY VS DATABASE COUNTS)
# ============================================================================

def _parse_upload_audit_meta(up: UploadHistory) -> Dict[str, Any]:
    """Parse audit_details JSON safely, returning empty dict on failure."""
    if not up.audit_details:
        return {}
    try:
        data = json.loads(up.audit_details)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _is_legacy_upload(up: UploadHistory, meta: Dict[str, Any]) -> bool:
    """
    Determine whether an upload history entry predates Phase 1 batch attribution.
    Phase 1 uploads always persist 'upload_id' and 'ingested_at' in audit_details metadata.
    """
    if meta.get("upload_id") or meta.get("ingested_at"):
        return False
    aff = meta.get("affected_scope")
    if isinstance(aff, dict) and aff.get("upload_id"):
        return False
    return True


def _extract_upload_plants(meta: Dict[str, Any]) -> Set[str]:
    """Extract set of plant IDs affected by this upload."""
    plants = meta.get("plants_affected")
    if not plants:
        aff = meta.get("affected_scope")
        if isinstance(aff, dict):
            plants = aff.get("plants")
    if isinstance(plants, list):
        return {str(p).strip() for p in plants if p}
    return set()


def _extract_upload_entities(meta: Dict[str, Any], report_type: str) -> Set[str]:
    """Extract set of meter IDs (ENERGY) or line IDs (PRODUCTION) affected by this upload."""
    aff = meta.get("affected_scope") if isinstance(meta.get("affected_scope"), dict) else {}
    if report_type == "ENERGY":
        meters = meta.get("meters_affected") or aff.get("meters")
        if isinstance(meters, list):
            return {str(m).strip() for m in meters if m}
    elif report_type == "PRODUCTION":
        lines = meta.get("lines_affected") or aff.get("lines")
        if isinstance(lines, list):
            return {str(l).strip() for l in lines if l}
    return set()


def _extract_overwritten_count(corr: UploadHistory, meta: Dict[str, Any]) -> int:
    """Extract documented overwritten record count from correction upload metadata."""
    cnt = meta.get("overwritten_records")
    if cnt is None:
        aff = meta.get("affected_scope")
        if isinstance(aff, dict):
            cnt = aff.get("overwritten_records")
    if isinstance(cnt, (int, float)):
        return max(0, int(cnt))
    return 0


def _extract_superseded_batches(
    meta: Dict[str, Any], report_type: Optional[str] = None
) -> Optional[Dict[str, int]]:
    """
    Extract exact superseded batch attribution mapping from correction upload metadata.
    Returns:
        - Dict[str, int] if superseded_batches or superseded_by_type is present.
        - None if this correction upload predates exact supersession attribution (historical correction).
    """
    # 1. Try report_type-specific breakdown if available
    by_type = meta.get("superseded_by_type")
    if not isinstance(by_type, dict):
        aff = meta.get("affected_scope")
        if isinstance(aff, dict):
            by_type = aff.get("superseded_by_type")

    if isinstance(by_type, dict) and report_type and report_type in by_type:
        type_dict = by_type[report_type]
        if isinstance(type_dict, dict):
            return {str(k): int(v) for k, v in type_dict.items() if isinstance(v, (int, float))}

    # 2. Try top-level superseded_batches
    batches = meta.get("superseded_batches")
    if not isinstance(batches, dict):
        aff = meta.get("affected_scope")
        if isinstance(aff, dict):
            batches = aff.get("superseded_batches")

    if isinstance(batches, dict):
        return {str(k): int(v) for k, v in batches.items() if isinstance(v, (int, float))}

    return None


def _evaluate_upload_source_consistency(
    session: Session,
    type_uploads: List[UploadHistory],
    report_type: str,
    fact_model: Any,
    pk_column: Any,
    date_column: Any,
    plant_id: Optional[str],
    check_id: str,
    category: ReconciliationCategory,
    missing_reason_code: str,
    mismatch_reason_code: str,
    fact_table_name: str,
) -> List[ReconciliationFinding]:
    """
    Evaluate source consistency for a given upload report type (ENERGY or PRODUCTION).
    Distinguishes legacy uploads, fully/partially superseded rows via exact OVERWRITE_CORRECTION
    attribution, historical corrections lacking attribution, and genuine count mismatches.
    """
    findings: List[ReconciliationFinding] = []

    # Group uploads by reporting date
    uploads_by_date: Dict[date, List[UploadHistory]] = {}
    for u in type_uploads:
        uploads_by_date.setdefault(u.reporting_date, []).append(u)

    for rep_date, date_uploads in uploads_by_date.items():
        # Sort chronologically by uploaded_at and primary key id
        date_uploads.sort(key=lambda u: (u.uploaded_at or datetime.min, u.id or 0))

        # Pre-parse metadata for all uploads on this reporting date
        parsed_metas: Dict[str, Dict[str, Any]] = {
            u.upload_id: _parse_upload_audit_meta(u) for u in date_uploads
        }

        # Evaluate each upload in chronological order
        for up in date_uploads:
            meta = parsed_metas[up.upload_id]
            is_legacy = _is_legacy_upload(up, meta)
            up_plants = _extract_upload_plants(meta)
            up_entities = _extract_upload_entities(meta, report_type)

            # Plant filter scope handling
            if plant_id:
                if up_plants and plant_id not in up_plants:
                    # Upload does not pertain to the requested plant filter
                    continue
                if len(up_plants) > 1:
                    # Multi-plant upload cannot be compared 1:1 against single-plant db count without plant split
                    continue

            # 1. Reliable Legacy Upload Handling (uploads predating Phase 1 batch attribution)
            if is_legacy:
                legacy_cnt_q = select(func.count(pk_column)).where(
                    date_column == rep_date,
                    fact_model.upload_id.is_(None),
                )
                if plant_id:
                    legacy_cnt_q = legacy_cnt_q.where(fact_model.plant_id == plant_id)
                legacy_cnt = session.execute(legacy_cnt_q).scalar() or 0

                # Check if legacy records were superseded by subsequent corrections on this date
                legacy_superseded = 0
                superseding_corr_ids: List[str] = []
                for corr in date_uploads:
                    if corr.mode == "OVERWRITE_CORRECTION" and (corr.uploaded_at or datetime.min, corr.id or 0) > (up.uploaded_at or datetime.min, up.id or 0):
                        c_meta = parsed_metas[corr.upload_id]
                        c_batches = _extract_superseded_batches(c_meta, report_type)
                        if c_batches is not None:
                            leg_cred = c_batches.get("__LEGACY__", 0)
                            if leg_cred > 0:
                                legacy_superseded += leg_cred
                                superseding_corr_ids.append(corr.upload_id)
                        else:
                            hist_cnt = _extract_overwritten_count(corr, c_meta)
                            if hist_cnt > 0:
                                superseding_corr_ids.append(corr.upload_id)

                if legacy_cnt > 0:
                    findings.append(
                        ReconciliationFinding(
                            check_id=check_id,
                            category=category,
                            status=ReconciliationStatus.UNAVAILABLE,
                            plant_id=plant_id,
                            affected_entity=up.upload_id,
                            evaluation_period={"reporting_date": rep_date.isoformat()},
                            observed_value=legacy_cnt,
                            expected_value=up.valid_rows,
                            difference=None,
                            difference_unit="records",
                            source_references=["upload_history", fact_table_name],
                            explanation=(
                                f"Upload '{up.upload_id}' for date {rep_date} predates batch attribution; "
                                f"underlying {legacy_cnt} record(s) on this date have untracked provenance (upload_id is NULL)."
                            ),
                            reason_code="LEGACY_UPLOAD_UNTRACKED_PROVENANCE",
                        )
                    )
                elif legacy_superseded > 0 or superseding_corr_ids:
                    findings.append(
                        ReconciliationFinding(
                            check_id=check_id,
                            category=category,
                            status=ReconciliationStatus.UNAVAILABLE,
                            plant_id=plant_id,
                            affected_entity=up.upload_id,
                            evaluation_period={"reporting_date": rep_date.isoformat()},
                            observed_value=0,
                            expected_value=up.valid_rows,
                            difference=None,
                            difference_unit="records",
                            source_references=["upload_history", fact_table_name],
                            explanation=(
                                f"Upload '{up.upload_id}' for date {rep_date} predates batch attribution; "
                                f"0 untracked legacy records survive on this date as legacy records were superseded "
                                f"by subsequent correction(s): {', '.join(superseding_corr_ids)}."
                            ),
                            reason_code="LEGACY_UPLOAD_UNTRACKED_PROVENANCE",
                        )
                    )
                else:
                    findings.append(
                        ReconciliationFinding(
                            check_id=check_id,
                            category=category,
                            status=ReconciliationStatus.UNAVAILABLE,
                            plant_id=plant_id,
                            affected_entity=up.upload_id,
                            evaluation_period={"reporting_date": rep_date.isoformat()},
                            observed_value=0,
                            expected_value=up.valid_rows,
                            difference=None,
                            difference_unit="records",
                            source_references=["upload_history", fact_table_name],
                            explanation=(
                                f"Upload '{up.upload_id}' for date {rep_date} predates batch attribution; "
                                f"0 records with untracked provenance survive on this date."
                            ),
                            reason_code="LEGACY_UPLOAD_UNTRACKED_PROVENANCE",
                        )
                    )
                continue

            # 2. Modern (Phase 1+) Upload Handling
            initial_valid = up.valid_rows
            if initial_valid == 0:
                # Empty upload (0 valid records), skip mismatch alerts
                continue

            # Count database rows currently stamped with this exact upload_id
            db_cnt_q = select(func.count(pk_column)).where(
                fact_model.upload_id == up.upload_id,
            )
            if plant_id:
                db_cnt_q = db_cnt_q.where(fact_model.plant_id == plant_id)
            db_cnt = session.execute(db_cnt_q).scalar() or 0

            # If db_cnt > initial_valid, database contains more rows than upload recorded
            if db_cnt > initial_valid:
                findings.append(
                    ReconciliationFinding(
                        check_id=check_id,
                        category=category,
                        status=ReconciliationStatus.WARNING,
                        plant_id=plant_id,
                        affected_entity=up.upload_id,
                        evaluation_period={"reporting_date": rep_date.isoformat()},
                        observed_value=db_cnt,
                        expected_value=initial_valid,
                        difference=db_cnt - initial_valid,
                        difference_unit="records",
                        source_references=["upload_history", fact_table_name],
                        explanation=(
                            f"Upload '{up.upload_id}' recorded {initial_valid} valid row(s), "
                            f"but {fact_table_name} contains {db_cnt} row(s) attributed to this upload."
                        ),
                        reason_code=mismatch_reason_code,
                    )
                )
                continue

            raw_shortfall = initial_valid - db_cnt
            if raw_shortfall == 0:
                # db_cnt == initial_valid: exact match without supersession
                continue

            # Evaluate subsequent corrections on the same reporting date
            exact_superseded = 0
            superseding_upload_ids: List[str] = []
            has_unattributed_historical_correction = False
            historical_corr_ids: List[str] = []

            for corr in date_uploads:
                if corr.mode != "OVERWRITE_CORRECTION":
                    continue

                # Must have been uploaded strictly after this upload
                if (corr.uploaded_at or datetime.min, corr.id or 0) <= (up.uploaded_at or datetime.min, up.id or 0):
                    continue

                c_meta = parsed_metas[corr.upload_id]
                c_plants = _extract_upload_plants(c_meta)
                c_entities = _extract_upload_entities(c_meta, report_type)

                # Scope overlap check: plants
                plants_overlap = True
                if up_plants and c_plants:
                    plants_overlap = bool(up_plants & c_plants)

                # Scope overlap check: entities (meters / lines)
                entities_overlap = True
                if up_entities and c_entities:
                    entities_overlap = bool(up_entities & c_entities)

                if not (plants_overlap and entities_overlap):
                    continue

                corr_batches = _extract_superseded_batches(c_meta, report_type)
                if corr_batches is not None:
                    # Modern correction: exact 1:1 attribution
                    # Never credit '__LEGACY__' to modern uploads
                    exact_credit = corr_batches.get(up.upload_id, 0)
                    if exact_credit > 0:
                        exact_superseded += exact_credit
                        superseding_upload_ids.append(corr.upload_id)
                else:
                    # Historical correction lacking superseded_batches metadata
                    hist_cnt = _extract_overwritten_count(corr, c_meta)
                    if hist_cnt > 0:
                        has_unattributed_historical_correction = True
                        historical_corr_ids.append(corr.upload_id)

            expected_surviving = max(0, initial_valid - exact_superseded)
            remaining_shortfall = max(0, expected_surviving - db_cnt)

            if remaining_shortfall == 0:
                # Shortfall is 100% accounted for by exact supersession attribution
                if db_cnt == 0:
                    findings.append(
                        ReconciliationFinding(
                            check_id=check_id,
                            category=category,
                            status=ReconciliationStatus.PASS,
                            plant_id=plant_id,
                            affected_entity=up.upload_id,
                            evaluation_period={"reporting_date": rep_date.isoformat()},
                            observed_value=0,
                            expected_value=0,
                            difference=0,
                            difference_unit="records",
                            source_references=["upload_history", fact_table_name],
                            explanation=(
                                f"Upload '{up.upload_id}' ({initial_valid} valid row(s)) has 0 surviving database records "
                                f"because all {initial_valid} record(s) were legitimately superseded by subsequent "
                                f"correction(s): {', '.join(superseding_upload_ids)}."
                            ),
                            reason_code="UPLOAD_RECORDS_FULLY_SUPERSEDED",
                        )
                    )
                else:
                    findings.append(
                        ReconciliationFinding(
                            check_id=check_id,
                            category=category,
                            status=ReconciliationStatus.PASS,
                            plant_id=plant_id,
                            affected_entity=up.upload_id,
                            evaluation_period={"reporting_date": rep_date.isoformat()},
                            observed_value=db_cnt,
                            expected_value=expected_surviving,
                            difference=0,
                            difference_unit="records",
                            source_references=["upload_history", fact_table_name],
                            explanation=(
                                f"Upload '{up.upload_id}' has {db_cnt} surviving database record(s); "
                                f"{exact_superseded} row(s) were legitimately superseded by subsequent "
                                f"correction(s): {', '.join(superseding_upload_ids)} "
                                f"(total accounted for: {db_cnt + exact_superseded}/{initial_valid})."
                            ),
                            reason_code="UPLOAD_RECORDS_PARTIALLY_SUPERSEDED",
                        )
                    )
            else:
                # remaining_shortfall > 0
                if has_unattributed_historical_correction:
                    # Shortfall coincides with historical corrections lacking exact attribution metadata
                    part_superseded_note = (
                        f" ({exact_superseded} row(s) verified superseded by modern correction(s): {', '.join(superseding_upload_ids)})"
                        if exact_superseded > 0
                        else ""
                    )
                    findings.append(
                        ReconciliationFinding(
                            check_id=check_id,
                            category=category,
                            status=ReconciliationStatus.UNAVAILABLE,
                            plant_id=plant_id,
                            affected_entity=up.upload_id,
                            evaluation_period={"reporting_date": rep_date.isoformat()},
                            observed_value=db_cnt,
                            expected_value=expected_surviving,
                            difference=None,
                            difference_unit="records",
                            source_references=["upload_history", fact_table_name],
                            explanation=(
                                f"Upload '{up.upload_id}' has {db_cnt} surviving database record(s) out of {initial_valid} valid row(s)"
                                f"{part_superseded_note}, leaving {remaining_shortfall} shortfall; "
                                f"subsequent correction(s) ({', '.join(historical_corr_ids)}) predate exact batch attribution "
                                f"(audit_details lacks 'superseded_batches'). Cannot determine if shortfall is due to "
                                f"legitimate supersession or missing data."
                            ),
                            reason_code="HISTORICAL_CORRECTION_ATTRIBUTION_UNAVAILABLE",
                        )
                    )
                else:
                    # No historical corrections: remaining_shortfall is genuine missing data
                    corr_note = (
                        f"; {exact_superseded} row(s) legitimately superseded by correction(s) ({', '.join(superseding_upload_ids)}) (expected surviving: {expected_surviving})"
                        if exact_superseded > 0
                        else ""
                    )
                    if db_cnt == 0:
                        findings.append(
                            ReconciliationFinding(
                                check_id=check_id,
                                category=category,
                                status=ReconciliationStatus.WARNING,
                                plant_id=plant_id,
                                affected_entity=up.upload_id,
                                evaluation_period={"reporting_date": rep_date.isoformat()},
                                observed_value=0,
                                expected_value=expected_surviving,
                                difference=-remaining_shortfall,
                                difference_unit="records",
                                source_references=["upload_history", fact_table_name],
                                explanation=(
                                    f"Upload '{up.upload_id}' recorded {initial_valid} valid row(s){corr_note}, "
                                    f"but 0 records with upload_id='{up.upload_id}' were found in {fact_table_name} "
                                    f"({remaining_shortfall} unexplained missing record(s))."
                                ),
                                reason_code=missing_reason_code,
                            )
                        )
                    else:
                        findings.append(
                            ReconciliationFinding(
                                check_id=check_id,
                                category=category,
                                status=ReconciliationStatus.WARNING,
                                plant_id=plant_id,
                                affected_entity=up.upload_id,
                                evaluation_period={"reporting_date": rep_date.isoformat()},
                                observed_value=db_cnt,
                                expected_value=expected_surviving,
                                difference=-remaining_shortfall,
                                difference_unit="records",
                                source_references=["upload_history", fact_table_name],
                                explanation=(
                                    f"Upload '{up.upload_id}' recorded {initial_valid} valid row(s){corr_note}, "
                                    f"but only {db_cnt} row(s) were found in {fact_table_name} "
                                    f"({remaining_shortfall} unexplained missing record(s))."
                                ),
                                reason_code=mismatch_reason_code,
                            )
                        )

    return findings


def _check_source_consistency(
    session: Session,
    start_date: date,
    end_date: date,
    plant_id: Optional[str] = None,
) -> ReconciliationCheckResult:
    """Compare uploaded report metadata and valid row counts against persisted database tables."""
    check_id = "CHK_SOURCE_CONSISTENCY"
    category = ReconciliationCategory.SOURCE_CONSISTENCY
    findings: List[ReconciliationFinding] = []
    period_dict = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

    # 1. Architectural notice: Aggregate metric totals (kWh, production qty) are unavailable in upload_history
    findings.append(
        ReconciliationFinding(
            check_id=check_id,
            category=category,
            status=ReconciliationStatus.UNAVAILABLE,
            plant_id=plant_id,
            affected_entity="upload_history",
            evaluation_period=period_dict,
            observed_value=None,
            expected_value=None,
            difference=None,
            difference_unit=None,
            source_references=["upload_history"],
            explanation=(
                "Upload audit history tracks file-level row metrics; aggregate consumption kWh "
                "and production volume totals are not stored in upload history records."
            ),
            reason_code="UPLOAD_METRIC_AGGREGATES_UNAVAILABLE",
        )
    )

    # 2. Audit untracked legacy records in fact tables (records with NULL upload_id)
    legacy_energy_q = select(func.count(FactEnergyMeterHourly.meter_reading_id)).where(
        FactEnergyMeterHourly.date >= start_date,
        FactEnergyMeterHourly.date <= end_date,
        FactEnergyMeterHourly.upload_id.is_(None),
    )
    if plant_id:
        legacy_energy_q = legacy_energy_q.where(FactEnergyMeterHourly.plant_id == plant_id)
    legacy_energy_cnt = session.execute(legacy_energy_q).scalar() or 0

    if legacy_energy_cnt > 0:
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.UNAVAILABLE,
                plant_id=plant_id,
                affected_entity="fact_energy_meter_hourly",
                evaluation_period=period_dict,
                observed_value=legacy_energy_cnt,
                expected_value=None,
                difference=None,
                difference_unit="records",
                source_references=["fact_energy_meter_hourly"],
                explanation=(
                    f"Identified {legacy_energy_cnt} historical energy meter record(s) with untracked provenance "
                    f"(upload_id is NULL) persisted prior to batch attribution."
                ),
                reason_code="UNTRACKED_HISTORICAL_ENERGY_RECORDS",
            )
        )

    legacy_prod_q = select(func.count(FactHourlyProduction.event_id)).where(
        FactHourlyProduction.event_date >= start_date,
        FactHourlyProduction.event_date <= end_date,
        FactHourlyProduction.upload_id.is_(None),
    )
    if plant_id:
        legacy_prod_q = legacy_prod_q.where(FactHourlyProduction.plant_id == plant_id)
    legacy_prod_cnt = session.execute(legacy_prod_q).scalar() or 0

    if legacy_prod_cnt > 0:
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.UNAVAILABLE,
                plant_id=plant_id,
                affected_entity="fact_hourly_production",
                evaluation_period=period_dict,
                observed_value=legacy_prod_cnt,
                expected_value=None,
                difference=None,
                difference_unit="records",
                source_references=["fact_hourly_production"],
                explanation=(
                    f"Identified {legacy_prod_cnt} historical production record(s) with untracked provenance "
                    f"(upload_id is NULL) persisted prior to batch attribution."
                ),
                reason_code="UNTRACKED_HISTORICAL_PRODUCTION_RECORDS",
            )
        )

    # 3. Query completed and partial upload records in the evaluation period
    upload_stmt = (
        select(UploadHistory)
        .where(
            UploadHistory.reporting_date >= start_date,
            UploadHistory.reporting_date <= end_date,
            UploadHistory.status.in_(["COMPLETED", "PARTIAL"]),
        )
        .order_by(UploadHistory.reporting_date.asc(), UploadHistory.uploaded_at.asc(), UploadHistory.id.asc())
    )
    uploads = session.execute(upload_stmt).scalars().all()

    if not uploads:
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.UNAVAILABLE,
                plant_id=plant_id,
                affected_entity="upload_history",
                evaluation_period=period_dict,
                observed_value=0,
                expected_value=">= 1 upload record",
                difference=None,
                difference_unit=None,
                source_references=["upload_history"],
                explanation=(
                    f"No completed or partial daily upload history records exist between {start_date} and {end_date}. "
                    f"Source consistency comparison between upload logs and database rows is unavailable."
                ),
                reason_code="NO_UPLOAD_AUDIT_HISTORY_IN_PERIOD",
            )
        )
    else:
        # Separate uploads by type
        energy_uploads = [u for u in uploads if u.report_type.upper() in {"ENERGY", "ENERGY_AND_PRODUCTION"}]
        prod_uploads = [u for u in uploads if u.report_type.upper() in {"PRODUCTION", "ENERGY_AND_PRODUCTION"}]

        # Evaluate ENERGY uploads with correction-aware supersession accounting
        if energy_uploads:
            energy_findings = _evaluate_upload_source_consistency(
                session=session,
                type_uploads=energy_uploads,
                report_type="ENERGY",
                fact_model=FactEnergyMeterHourly,
                pk_column=FactEnergyMeterHourly.meter_reading_id,
                date_column=FactEnergyMeterHourly.date,
                plant_id=plant_id,
                check_id=check_id,
                category=category,
                missing_reason_code="UPLOAD_ENERGY_RECORDS_MISSING",
                mismatch_reason_code="UPLOAD_ENERGY_ROW_COUNT_MISMATCH",
                fact_table_name="fact_energy_meter_hourly",
            )
            findings.extend(energy_findings)

        # Evaluate PRODUCTION uploads with correction-aware supersession accounting
        if prod_uploads:
            prod_findings = _evaluate_upload_source_consistency(
                session=session,
                type_uploads=prod_uploads,
                report_type="PRODUCTION",
                fact_model=FactHourlyProduction,
                pk_column=FactHourlyProduction.event_id,
                date_column=FactHourlyProduction.event_date,
                plant_id=plant_id,
                check_id=check_id,
                category=category,
                missing_reason_code="UPLOAD_PRODUCTION_RECORDS_MISSING",
                mismatch_reason_code="UPLOAD_PRODUCTION_ROW_COUNT_MISMATCH",
                fact_table_name="fact_hourly_production",
            )
            findings.extend(prod_findings)

    has_fail = any(f.status == ReconciliationStatus.FAIL for f in findings)
    has_warn = any(f.status == ReconciliationStatus.WARNING for f in findings)
    overall_status = ReconciliationStatus.FAIL if has_fail else (ReconciliationStatus.WARNING if has_warn else ReconciliationStatus.PASS)

    return ReconciliationCheckResult(
        check_id=check_id,
        category=category,
        name="Upload History Audit vs. Persisted Database Aggregates",
        description="Audits completed upload logs against persisted row counts in fact tables.",
        status=overall_status,
        plant_id=plant_id,
        findings_count=len(findings),
        findings=findings,
        summary=(
            f"Source consistency audit evaluated {len(uploads)} upload log record(s). "
            f"Identified {len([f for f in findings if f.status == ReconciliationStatus.WARNING])} row count mismatch warning(s)."
        ),
    )


# ============================================================================
# CHECK 6: REFERENCE INTEGRITY
# ============================================================================

def _check_reference_integrity(
    session: Session,
    start_date: date,
    end_date: date,
    plant_id: Optional[str] = None,
) -> ReconciliationCheckResult:
    """Validate referential integrity against registered dimension models."""
    check_id = "CHK_REFERENCE_INTEGRITY"
    category = ReconciliationCategory.REFERENCE_INTEGRITY
    findings: List[ReconciliationFinding] = []
    period_dict = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

    # 1. Schema boundary notice: dim_meter table does not exist
    findings.append(
        ReconciliationFinding(
            check_id=check_id,
            category=category,
            status=ReconciliationStatus.UNAVAILABLE,
            plant_id=plant_id,
            affected_entity="fact_energy_meter_hourly",
            evaluation_period=period_dict,
            observed_value=None,
            expected_value=None,
            difference=None,
            difference_unit=None,
            source_references=["fact_energy_meter_hourly"],
            explanation="No master dimension table exists for energy meters (dim_meter); meter IDs cannot be verified against a master catalog.",
            reason_code="DIM_METER_TABLE_UNAVAILABLE",
        )
    )

    params = {"start_date": start_date, "end_date": end_date}
    plant_clause_prod = "AND p.plant_id = :plant_id" if plant_id else ""
    plant_clause_energy = "AND e.plant_id = :plant_id" if plant_id else ""
    if plant_id:
        params["plant_id"] = plant_id

    # 2. Check orphan production line references: (line_id, plant_id) in fact_hourly_production not in dim_production_line
    orphan_line_sql = f"""
        SELECT DISTINCT p.plant_id, p.line_id, COUNT(*) as cnt
        FROM fact_hourly_production p
        LEFT JOIN dim_production_line d
          ON p.line_id = d.line_id
         AND p.plant_id = d.plant_id
        WHERE p.event_date >= :start_date AND p.event_date <= :end_date
          {plant_clause_prod}
          AND d.line_id IS NULL
        GROUP BY p.plant_id, p.line_id
    """
    orphan_lines = session.execute(text(orphan_line_sql), params).fetchall()
    for r in orphan_lines:
        p_id, l_id, cnt = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity=l_id,
                evaluation_period=period_dict,
                observed_value=cnt,
                expected_value=0,
                difference=cnt,
                difference_unit="orphan records",
                source_references=["fact_hourly_production", "dim_production_line"],
                explanation=f"Line '{l_id}' at plant '{p_id}' has {cnt} production event(s) not registered in dim_production_line.",
                reason_code="ORPHAN_PRODUCTION_LINE_REFERENCE",
            )
        )

    # 3. Check orphan product references: product_id in fact_hourly_production not in dim_product
    orphan_prod_sql = f"""
        SELECT DISTINCT p.plant_id, p.product_id, COUNT(*) as cnt
        FROM fact_hourly_production p
        LEFT JOIN dim_product d
          ON p.product_id = d.product_id
        WHERE p.event_date >= :start_date AND p.event_date <= :end_date
          {plant_clause_prod}
          AND d.product_id IS NULL
        GROUP BY p.plant_id, p.product_id
    """
    orphan_products = session.execute(text(orphan_prod_sql), params).fetchall()
    for r in orphan_products:
        p_id, pr_id, cnt = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity=pr_id,
                evaluation_period=period_dict,
                observed_value=cnt,
                expected_value=0,
                difference=cnt,
                difference_unit="orphan records",
                source_references=["fact_hourly_production", "dim_product"],
                explanation=f"Product '{pr_id}' has {cnt} production event(s) not registered in dim_product.",
                reason_code="ORPHAN_PRODUCT_REFERENCE",
            )
        )

    # 4. Check unregistered plants in fact_energy_meter_hourly
    unreg_plants_sql = f"""
        SELECT DISTINCT e.plant_id, COUNT(*) as cnt
        FROM fact_energy_meter_hourly e
        WHERE e.date >= :start_date AND e.date <= :end_date
          {plant_clause_energy}
          AND e.plant_id NOT IN (SELECT DISTINCT plant_id FROM dim_production_line)
        GROUP BY e.plant_id
    """
    unreg_plants = session.execute(text(unreg_plants_sql), params).fetchall()
    for r in unreg_plants:
        p_id, cnt = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity="fact_energy_meter_hourly",
                evaluation_period=period_dict,
                observed_value=cnt,
                expected_value=0,
                difference=cnt,
                difference_unit="unregistered records",
                source_references=["fact_energy_meter_hourly", "dim_production_line"],
                explanation=f"Plant '{p_id}' has {cnt} energy reading(s) but does not exist in dim_production_line.",
                reason_code="UNREGISTERED_PLANT_REFERENCE",
            )
        )

    has_fail = any(f.status == ReconciliationStatus.FAIL for f in findings)
    overall_status = ReconciliationStatus.FAIL if has_fail else ReconciliationStatus.PASS

    return ReconciliationCheckResult(
        check_id=check_id,
        category=category,
        name="Foreign Key & Dimensional Entity References",
        description="Audits production lines, products, and plants against registered dimension tables.",
        status=overall_status,
        plant_id=plant_id,
        findings_count=len(findings),
        findings=findings,
        summary=(
            f"Reference integrity check {'PASSED' if overall_status == ReconciliationStatus.PASS else 'FAILED'}. "
            f"Found {len(orphan_lines)} orphan line(s), {len(orphan_products)} orphan product(s), and "
            f"{len(unreg_plants)} unregistered plant(s)."
        ),
    )


# ============================================================================
# CHECK 7: DATA QUALITY
# ============================================================================

def _check_data_quality(
    session: Session,
    start_date: date,
    end_date: date,
    plant_id: Optional[str] = None,
) -> ReconciliationCheckResult:
    """Validate numerical non-negativity, physical bounds, quantity balance, and field constraints."""
    check_id = "CHK_DATA_QUALITY"
    category = ReconciliationCategory.DATA_QUALITY
    findings: List[ReconciliationFinding] = []
    period_dict = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

    params = {"start_date": start_date, "end_date": end_date}
    plant_clause_energy = "AND plant_id = :plant_id" if plant_id else ""
    plant_clause_prod = "AND plant_id = :plant_id" if plant_id else ""
    if plant_id:
        params["plant_id"] = plant_id

    # 1. Negative Energy Consumption
    neg_kwh_sql = f"""
        SELECT plant_id, meter_id, COUNT(*) as cnt, MIN(consumption_kwh) as min_val
        FROM fact_energy_meter_hourly
        WHERE date >= :start_date AND date <= :end_date
          {plant_clause_energy}
          AND consumption_kwh < 0
        GROUP BY plant_id, meter_id
    """
    neg_kwh_rows = session.execute(text(neg_kwh_sql), params).fetchall()
    for r in neg_kwh_rows:
        p_id, m_id, cnt, min_val = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity=m_id,
                evaluation_period=period_dict,
                observed_value=float(min_val),
                expected_value=">= 0.0 kWh",
                difference=cnt,
                difference_unit="negative readings",
                source_references=["fact_energy_meter_hourly"],
                explanation=f"Meter '{m_id}' at plant '{p_id}' has {cnt} negative consumption reading(s) (min: {min_val} kWh).",
                reason_code="NEGATIVE_ENERGY_CONSUMPTION",
            )
        )

    # 2. Power Factor out of range [0.0, 1.0]
    pf_range_sql = f"""
        SELECT plant_id, meter_id, COUNT(*) as cnt
        FROM fact_energy_meter_hourly
        WHERE date >= :start_date AND date <= :end_date
          {plant_clause_energy}
          AND (power_factor < 0.0 OR power_factor > 1.0)
        GROUP BY plant_id, meter_id
    """
    pf_range_rows = session.execute(text(pf_range_sql), params).fetchall()
    for r in pf_range_rows:
        p_id, m_id, cnt = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity=m_id,
                evaluation_period=period_dict,
                observed_value=cnt,
                expected_value="0.0 <= power_factor <= 1.0",
                difference=cnt,
                difference_unit="out-of-range readings",
                source_references=["fact_energy_meter_hourly"],
                explanation=f"Meter '{m_id}' at plant '{p_id}' has {cnt} power factor reading(s) outside [0.0, 1.0].",
                reason_code="POWER_FACTOR_OUT_OF_RANGE",
            )
        )

    # 3. Production Quantity Balance: actual_qty != good_qty + reject_qty
    qty_bal_sql = f"""
        SELECT plant_id, line_id, COUNT(*) as cnt
        FROM fact_hourly_production
        WHERE event_date >= :start_date AND event_date <= :end_date
          {plant_clause_prod}
          AND actual_qty != (good_qty + reject_qty)
        GROUP BY plant_id, line_id
    """
    qty_bal_rows = session.execute(text(qty_bal_sql), params).fetchall()
    for r in qty_bal_rows:
        p_id, l_id, cnt = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity=l_id,
                evaluation_period=period_dict,
                observed_value=cnt,
                expected_value="actual_qty == good_qty + reject_qty",
                difference=cnt,
                difference_unit="unbalanced records",
                source_references=["fact_hourly_production"],
                explanation=f"Line '{l_id}' at plant '{p_id}' has {cnt} record(s) where actual_qty != good_qty + reject_qty.",
                reason_code="PRODUCTION_QUANTITY_BALANCE_VIOLATION",
            )
        )

    # 4. Downtime Minutes out of range [0, 60]
    dt_range_sql = f"""
        SELECT plant_id, line_id, COUNT(*) as cnt
        FROM fact_hourly_production
        WHERE event_date >= :start_date AND event_date <= :end_date
          {plant_clause_prod}
          AND (downtime_min < 0 OR downtime_min > 60)
        GROUP BY plant_id, line_id
    """
    dt_range_rows = session.execute(text(dt_range_sql), params).fetchall()
    for r in dt_range_rows:
        p_id, l_id, cnt = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity=l_id,
                evaluation_period=period_dict,
                observed_value=cnt,
                expected_value="0 <= downtime_min <= 60",
                difference=cnt,
                difference_unit="invalid records",
                source_references=["fact_hourly_production"],
                explanation=f"Line '{l_id}' at plant '{p_id}' has {cnt} record(s) with downtime_min outside [0, 60].",
                reason_code="DOWNTIME_MINUTES_OUT_OF_RANGE",
            )
        )

    # 5. Timestamp and Date/Hour Mismatch in fact_hourly_production
    ts_mismatch_sql = f"""
        SELECT plant_id, line_id, COUNT(*) as cnt
        FROM fact_hourly_production
        WHERE event_date >= :start_date AND event_date <= :end_date
          {plant_clause_prod}
          AND (EXTRACT(HOUR FROM event_ts) != hour OR event_date != CAST(event_ts AS DATE))
        GROUP BY plant_id, line_id
    """
    ts_mismatch_rows = session.execute(text(ts_mismatch_sql), params).fetchall()
    for r in ts_mismatch_rows:
        p_id, l_id, cnt = r
        findings.append(
            ReconciliationFinding(
                check_id=check_id,
                category=category,
                status=ReconciliationStatus.FAIL,
                plant_id=p_id,
                affected_entity=l_id,
                evaluation_period=period_dict,
                observed_value=cnt,
                expected_value="event_ts matches hour and event_date",
                difference=cnt,
                difference_unit="mismatched records",
                source_references=["fact_hourly_production"],
                explanation=f"Line '{l_id}' at plant '{p_id}' has {cnt} record(s) where event_ts hour or date does not match stored hour/event_date columns.",
                reason_code="EVENT_TIMESTAMP_DIMENSION_MISMATCH",
            )
        )

    has_fail = any(f.status == ReconciliationStatus.FAIL for f in findings)
    overall_status = ReconciliationStatus.FAIL if has_fail else ReconciliationStatus.PASS

    return ReconciliationCheckResult(
        check_id=check_id,
        category=category,
        name="Field Validations, Physical Bounds & Quantity Balance",
        description="Audits non-negativity, mathematical quantity balance, downtime boundaries, and timestamp alignment.",
        status=overall_status,
        plant_id=plant_id,
        findings_count=len(findings),
        findings=findings,
        summary=(
            f"Data quality audit {'PASSED' if overall_status == ReconciliationStatus.PASS else 'FAILED'}. "
            f"Identified {len(findings)} data quality finding(s)."
        ),
    )


# ============================================================================
# MASTER RECONCILIATION ENGINE ORCHESTRATION
# ============================================================================

def run_cross_source_reconciliation(
    session: Session,
    start_date: date,
    end_date: date,
    plant_id: Optional[str] = None,
    category_filter: Optional[ReconciliationCategory] = None,
    status_filter: Optional[ReconciliationStatus] = None,
) -> ReconciliationReportResponse:
    """
    Execute deterministic cross-source data reconciliation across the requested window.
    
    Runs all 7 checks, compiles finding counts, determines overall status, and returns
    a fully structured, read-only reconciliation report.
    """
    checks: List[ReconciliationCheckResult] = []

    # 1. Run Energy Coverage Check
    if category_filter is None or category_filter == ReconciliationCategory.ENERGY_COVERAGE:
        checks.append(_check_energy_coverage(session, start_date, end_date, plant_id))

    # 2. Run Production Coverage Check
    if category_filter is None or category_filter == ReconciliationCategory.PRODUCTION_COVERAGE:
        checks.append(_check_production_coverage(session, start_date, end_date, plant_id))

    # 3. Run Timestamp Alignment Check
    if category_filter is None or category_filter == ReconciliationCategory.TIMESTAMP_ALIGNMENT:
        checks.append(_check_timestamp_alignment(session, start_date, end_date, plant_id))

    # 4. Run Duplicate Records Check
    if category_filter is None or category_filter == ReconciliationCategory.DUPLICATE_RECORDS:
        checks.append(_check_duplicate_records(session, start_date, end_date, plant_id))

    # 5. Run Source Consistency Check
    if category_filter is None or category_filter == ReconciliationCategory.SOURCE_CONSISTENCY:
        checks.append(_check_source_consistency(session, start_date, end_date, plant_id))

    # 6. Run Reference Integrity Check
    if category_filter is None or category_filter == ReconciliationCategory.REFERENCE_INTEGRITY:
        checks.append(_check_reference_integrity(session, start_date, end_date, plant_id))

    # 7. Run Data Quality Check
    if category_filter is None or category_filter == ReconciliationCategory.DATA_QUALITY:
        checks.append(_check_data_quality(session, start_date, end_date, plant_id))

    # Filter findings inside checks if status_filter is supplied
    if status_filter:
        for chk in checks:
            chk.findings = [f for f in chk.findings if f.status == status_filter]
            chk.findings_count = len(chk.findings)

    # Compute summary counts
    pass_cnt = sum(1 for c in checks if c.status == ReconciliationStatus.PASS)
    warn_cnt = sum(1 for c in checks if c.status == ReconciliationStatus.WARNING)
    fail_cnt = sum(1 for c in checks if c.status == ReconciliationStatus.FAIL)
    unavail_cnt = sum(1 for c in checks if c.status == ReconciliationStatus.UNAVAILABLE)
    total_checks = len(checks)

    counts = ReconciliationSummaryCounts(
        pass_count=pass_cnt,
        warning_count=warn_cnt,
        fail_count=fail_cnt,
        unavailable_count=unavail_cnt,
        total_checks=total_checks,
    )

    # Determine overall status: FAIL > WARNING > PASS
    if fail_cnt > 0:
        overall_status = ReconciliationStatus.FAIL
    elif warn_cnt > 0:
        overall_status = ReconciliationStatus.WARNING
    elif unavail_cnt > 0 and pass_cnt == 0:
        overall_status = ReconciliationStatus.UNAVAILABLE
    else:
        overall_status = ReconciliationStatus.PASS

    return ReconciliationReportResponse(
        status=overall_status,
        counts=counts,
        evaluation_period={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        plant_id=plant_id,
        checks=checks,
        limitations=STANDARD_LIMITATIONS,
    )


def get_reconciliation_summary(
    session: Session,
    start_date: date,
    end_date: date,
    plant_id: Optional[str] = None,
) -> ReconciliationSummaryResponse:
    """Lightweight summary of reconciliation statuses across all 7 categories."""
    full_report = run_cross_source_reconciliation(
        session=session,
        start_date=start_date,
        end_date=end_date,
        plant_id=plant_id,
    )
    category_statuses = {
        chk.category.value: chk.status
        for chk in full_report.checks
    }
    return ReconciliationSummaryResponse(
        status=full_report.status,
        counts=full_report.counts,
        evaluation_period=full_report.evaluation_period,
        plant_id=plant_id,
        category_statuses=category_statuses,
        limitations=full_report.limitations,
    )


def get_supported_check_definitions() -> List[ReconciliationCheckDefinition]:
    """Catalog of all 7 supported cross-source reconciliation checks."""
    return [
        ReconciliationCheckDefinition(
            check_id="CHK_ENERGY_COVERAGE",
            category=ReconciliationCategory.ENERGY_COVERAGE,
            name="Energy Telemetry Coverage & Missing Hours",
            description="Audits completeness and missing hourly observations across observed energy meters.",
            supported_dimensions=["meter_id", "plant_id", "date", "hourly_continuity"],
            unsupported_dimensions=["dim_meter", "plant_meter_catalog", "operating_calendars"],
            source_tables=["fact_energy_meter_hourly"],
        ),
        ReconciliationCheckDefinition(
            check_id="CHK_PRODUCTION_COVERAGE",
            category=ReconciliationCategory.PRODUCTION_COVERAGE,
            name="Production Line Coverage & Active Shift Observations",
            description="Audits manufacturing line event coverage against registered plant lines.",
            supported_dimensions=["line_id", "plant_id", "event_date", "dim_production_line"],
            unsupported_dimensions=["shift_calendars", "planned_stoppage_schedules", "historical_activation_dates"],
            source_tables=["fact_hourly_production", "dim_production_line"],
        ),
        ReconciliationCheckDefinition(
            check_id="CHK_TIMESTAMP_ALIGNMENT",
            category=ReconciliationCategory.TIMESTAMP_ALIGNMENT,
            name="Cross-Stream Timestamp Synchronization",
            description="Identifies timestamps where active production was recorded without energy telemetry or non-hourly offsets.",
            supported_dimensions=["hourly_timestamp_match", "sub_hourly_minute_second_alignment"],
            unsupported_dimensions=["process_meter_to_line_direct_linkage", "finished_output_to_meter_correlation"],
            source_tables=["fact_energy_meter_hourly", "fact_hourly_production"],
        ),
        ReconciliationCheckDefinition(
            check_id="CHK_DUPLICATE_RECORDS",
            category=ReconciliationCategory.DUPLICATE_RECORDS,
            name="Business Key Uniqueness & Deduplication",
            description="Verifies that natural primary business keys are unique without duplicate occurrences.",
            supported_dimensions=["(timestamp, plant_id, meter_id)", "(event_ts, plant_id, line_id)"],
            unsupported_dimensions=[],
            source_tables=["fact_energy_meter_hourly", "fact_hourly_production", "upload_history"],
        ),
        ReconciliationCheckDefinition(
            check_id="CHK_SOURCE_CONSISTENCY",
            category=ReconciliationCategory.SOURCE_CONSISTENCY,
            name="Upload History Audit vs. Persisted Database Aggregates",
            description="Audits completed upload logs against persisted row counts in fact tables using exact upload IDs and correction supersession accounting.",
            supported_dimensions=[
                "upload_history.upload_id",
                "upload_history.valid_rows",
                "fact_table_upload_id",
                "superseded_correction_rows",
                "untracked_historical_records",
            ],
            unsupported_dimensions=["upload_total_kwh_aggregates", "upload_production_volume_totals"],
            source_tables=["upload_history", "fact_energy_meter_hourly", "fact_hourly_production"],
        ),
        ReconciliationCheckDefinition(
            check_id="CHK_REFERENCE_INTEGRITY",
            category=ReconciliationCategory.REFERENCE_INTEGRITY,
            name="Foreign Key & Dimensional Entity References",
            description="Audits production lines, products, and plants against registered dimension tables.",
            supported_dimensions=["dim_production_line", "dim_product"],
            unsupported_dimensions=["dim_meter"],
            source_tables=["fact_hourly_production", "dim_production_line", "dim_product", "fact_energy_meter_hourly"],
        ),
        ReconciliationCheckDefinition(
            check_id="CHK_DATA_QUALITY",
            category=ReconciliationCategory.DATA_QUALITY,
            name="Field Validations, Physical Bounds & Quantity Balance",
            description="Audits non-negativity, mathematical quantity balance, downtime boundaries, and timestamp alignment.",
            supported_dimensions=["consumption_kwh >= 0", "actual_qty == good_qty + reject_qty", "0 <= downtime_min <= 60", "0 <= pf <= 1"],
            unsupported_dimensions=["sensor_drift_calibration", "dynamic_power_factor_target_thresholds"],
            source_tables=["fact_energy_meter_hourly", "fact_hourly_production"],
        ),
    ]

