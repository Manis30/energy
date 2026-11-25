"""
Daily Operations End-to-End Intelligence Pipeline Service.

Orchestrates and tracks the complete 8-stage operational workflow for any given reporting date:
1. data_upload - File selection and upload metadata tracking.
2. validation - Schema, type, range, constraint, and date consistency checks.
3. database_ingestion - Transactional commit into fact_energy_meter_hourly and fact_hourly_production.
4. data_reconciliation - Deterministic cross-source reconciliation.
5. daily_analytics - Energy, production, and Specific Energy Consumption (SEC) calculations.
6. intelligence_report - Comprehensive daily operational intelligence synthesis.
7. anomaly_detection - Multi-algorithm surveillance (statistical, rolling, low PF, standby waste).
8. investigation_handoff - Mapping anomalies to persistent findings with priority suggestions.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import logging
import os
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session

from app.models.findings import FindingOccurrence, OperationalFinding
from app.models.pipeline_runs import DailyPipelineRun
from app.models.recommendations import (
    CorrectiveAction,
    InterventionAssessment,
    OperationalRecommendation,
)
from app.models.source_data import FactEnergyMeterHourly, FactHourlyProduction
from app.models.upload_history import UploadHistory
from app.services.anomaly_detection import detect_all_anomalies
from app.services.finding_lifecycle_service import sync_findings_from_anomalies
from app.services.energy_analytics import (
    get_energy_by_area,
    get_energy_by_meter,
    get_energy_summary,
    get_power_factor_summary,
)
from app.services.energy_intensity import (
    get_factory_energy_analytics,
    get_process_energy_analytics,
)
from app.services.production_analytics import (
    get_production_by_line,
    get_production_summary,
)
from app.services.reconciliation_service import run_cross_source_reconciliation
from app.services.intervention_service import (
    is_claim_eligible_for_verified_savings,
    is_claim_eligible_for_verified_monetary,
)

logger = logging.getLogger(__name__)

STATE_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "daily_pipeline_state.json",
)

STAGE_KEYS = [
    "data_upload",
    "validation",
    "database_ingestion",
    "data_reconciliation",
    "daily_analytics",
    "intelligence_report",
    "anomaly_detection",
    "investigation_handoff",
]

# Thread safety locks
_FILE_LOCK = threading.RLock()
_DATE_EXECUTION_LOCKS: Dict[str, threading.Lock] = {}
_DATE_LOCKS_GUARD = threading.Lock()


def _get_date_lock(date_str: str) -> threading.Lock:
    """Retrieve or create an execution lock for a specific reporting date."""
    with _DATE_LOCKS_GUARD:
        if date_str not in _DATE_EXECUTION_LOCKS:
            _DATE_EXECUTION_LOCKS[date_str] = threading.Lock()
        return _DATE_EXECUTION_LOCKS[date_str]


def is_date_locked(date_str: str) -> bool:
    """Check whether a downstream pipeline execution is actively running for the given date."""
    with _DATE_LOCKS_GUARD:
        lock = _DATE_EXECUTION_LOCKS.get(date_str)
        return lock.locked() if lock else False


def _json_serial(val: Any) -> Any:
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val) if val.is_finite() else str(val)
    if hasattr(val, "model_dump"):
        return val.model_dump()
    raise TypeError(f"Object of type {type(val).__name__} is not JSON serializable")


def _load_all_pipeline_states() -> Dict[str, Any]:
    """
    Load persistent pipeline states dictionary from local storage file.
    Recovers gracefully from missing or corrupted files.
    """
    with _FILE_LOCK:
        if not os.path.exists(STATE_FILE_PATH):
            return {}
        try:
            with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as jde:
            logger.error("Daily pipeline state file corrupted: %s. Backing up and resetting.", str(jde))
            try:
                corrupted_backup = f"{STATE_FILE_PATH}.corrupted.{int(time.time())}"
                os.rename(STATE_FILE_PATH, corrupted_backup)
            except Exception as e:
                logger.error("Failed to backup corrupted state file: %s", str(e))
            return {}
        except Exception as e:
            logger.warning("Failed to load daily pipeline state: %s", str(e))
            return {}


def _save_all_pipeline_states(states: Dict[str, Any]) -> None:
    """
    Save persistent pipeline states atomically with cross-platform lock.
    Uses tempfile + fsync + retry replace to guarantee crash-proof writes on Windows.
    """
    with _FILE_LOCK:
        try:
            target_dir = os.path.dirname(STATE_FILE_PATH)
            os.makedirs(target_dir, exist_ok=True)

            with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
                json.dump(states, tf, indent=2, default=_json_serial)
                tf.flush()
                os.fsync(tf.fileno())
                temp_name = tf.name

            # Windows-resilient atomic replace with exponential backoff
            replaced = False
            for attempt in range(5):
                try:
                    os.replace(temp_name, STATE_FILE_PATH)
                    replaced = True
                    break
                except PermissionError:
                    time.sleep(0.04 * (attempt + 1))

            if not replaced:
                logger.error("Failed to atomically replace %s after 5 attempts", STATE_FILE_PATH)
                if os.path.exists(temp_name):
                    try:
                        os.remove(temp_name)
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Failed to save daily pipeline state: %s", str(e))


def reset_daily_pipeline_state(reporting_date: date) -> None:
    """Remove persistent pipeline stage state for a given reporting date."""
    date_str = reporting_date.isoformat()
    with _FILE_LOCK:
        states = _load_all_pipeline_states()
        if date_str in states:
            del states[date_str]
            _save_all_pipeline_states(states)


def invalidate_downstream_stages(reporting_date: date, plant_id: str = "IN-TN-01") -> None:
    """Mark all downstream stages (4-8) as RERUN_REQUIRED when telemetry is updated."""
    date_str = reporting_date.isoformat()
    downstream_keys = [
        "data_reconciliation",
        "daily_analytics",
        "intelligence_report",
        "anomaly_detection",
        "investigation_handoff",
    ]
    with _FILE_LOCK:
        states = _load_all_pipeline_states()
        if date_str not in states:
            states[date_str] = {}
        for key in downstream_keys:
            states[date_str][key] = {
                "status": "RERUN_REQUIRED",
                "timestamp": datetime.utcnow().isoformat(),
                "summary": "Source telemetry updated. Downstream pipeline re-run required.",
                "details": {"rerun_required": True},
            }
        _save_all_pipeline_states(states)


def get_human_action_summary_for_date(
    session: Session,
    reporting_date: date,
    plant_id: str,
) -> Dict[str, Any]:
    """
    Summarize human operational action lifecycle for a reporting date and plant.
    Tracks recommendations, corrective actions, and M&V assessments linked to findings.
    Exposes explicit lifecycle states and required evidence before outcome verification.
    """
    day_start = datetime.combine(reporting_date, datetime.min.time())
    day_end = datetime.combine(reporting_date, datetime.max.time())

    # 1. Findings with occurrences on this reporting date
    occ_fids_stmt = select(FindingOccurrence.finding_id).join(
        OperationalFinding, FindingOccurrence.finding_id == OperationalFinding.finding_id
    ).where(
        OperationalFinding.plant_id == plant_id,
        FindingOccurrence.occurrence_ts >= day_start,
        FindingOccurrence.occurrence_ts <= day_end,
    ).distinct()
    date_finding_ids = set(session.execute(occ_fids_stmt).scalars().all())

    # 2. Findings whose active window covers this reporting date
    window_stmt = select(OperationalFinding.finding_id).where(
        OperationalFinding.plant_id == plant_id,
        OperationalFinding.first_detected_at <= day_end,
        OperationalFinding.last_detected_at >= day_start,
    )
    for fid in session.execute(window_stmt).scalars().all():
        date_finding_ids.add(fid)

    # 3. If no findings matched this single day, include plant findings that have ongoing recommendations/actions
    if not date_finding_ids:
        plant_fids_stmt = select(OperationalFinding.finding_id).where(
            OperationalFinding.plant_id == plant_id
        )
        date_finding_ids = set(session.execute(plant_fids_stmt).scalars().all())

    if not date_finding_ids:
        return {
            "total_findings": 0,
            "open_findings": 0,
            "total_recommendations": 0,
            "total_actions": 0,
            "actions_by_status": {},
            "actions_by_review_status": {},
            "total_assessments": 0,
            "verified_savings_count": 0,
            "total_verified_avoided_kwh": 0.0,
            "total_verified_avoided_cost_inr": 0.0,
            "lifecycle_state_summary": "Zero operational findings identified for this reporting date and plant.",
            "evidence_needed": [],
        }

    findings = session.execute(
        select(OperationalFinding).where(OperationalFinding.finding_id.in_(list(date_finding_ids)))
    ).scalars().all()
    finding_ids = [f.finding_id for f in findings]

    recs_stmt = select(OperationalRecommendation).where(
        OperationalRecommendation.finding_id.in_(finding_ids)
    )
    recs = session.execute(recs_stmt).scalars().all()
    rec_ids = [r.recommendation_id for r in recs]

    actions = []
    if rec_ids:
        acts_stmt = select(CorrectiveAction).where(
            CorrectiveAction.recommendation_id.in_(rec_ids)
        )
        actions = session.execute(acts_stmt).scalars().all()

    action_ids = [a.action_id for a in actions]
    assessments = []
    if action_ids:
        asms_stmt = select(InterventionAssessment).where(
            InterventionAssessment.action_id.in_(action_ids)
        )
        assessments = session.execute(asms_stmt).scalars().all()

    actions_by_status: Dict[str, int] = {}
    actions_by_review: Dict[str, int] = {}
    evidence_needed: List[Dict[str, Any]] = []

    for a in actions:
        actions_by_status[a.status] = actions_by_status.get(a.status, 0) + 1
        actions_by_review[a.review_status] = actions_by_review.get(a.review_status, 0) + 1

        if a.review_status == "PENDING_REVIEW":
            evidence_needed.append({
                "action_id": a.action_id,
                "title": a.title,
                "state": "PENDING_APPROVAL",
                "evidence_needed": "Requires Facilities or Production engineering proposal review and formal approval reason.",
            })
        elif not a.implemented_at:
            evidence_needed.append({
                "action_id": a.action_id,
                "title": a.title,
                "state": "PENDING_IMPLEMENTATION",
                "evidence_needed": "Requires physical implementation timestamp and execution notes before post-action window evaluation.",
            })
        elif a.assessment_status in ("NONE", "REQUESTED"):
            evidence_needed.append({
                "action_id": a.action_id,
                "title": a.title,
                "state": "PENDING_ASSESSMENT",
                "evidence_needed": "Requires post-intervention observation accumulation and deterministic comparison execution.",
            })
        elif a.assessment_status == "INCONCLUSIVE":
            evidence_needed.append({
                "action_id": a.action_id,
                "title": a.title,
                "state": "INCONCLUSIVE_DATA",
                "evidence_needed": "Post-intervention coverage below approved plan minimum or operational schedule non-comparable.",
            })

    verified_asms = [asm for asm in assessments if is_claim_eligible_for_verified_savings(asm)[0]]
    total_avoided_kwh = sum(v.electricity_savings_kwh or 0.0 for v in verified_asms)
    total_avoided_cost = sum(
        v.verified_monetary_savings_inr or 0.0
        for v in verified_asms
        if is_claim_eligible_for_verified_monetary(v)[0]
    )

    open_findings = sum(1 for f in findings if f.status in ("NEW", "ACKNOWLEDGED", "INVESTIGATING", "REOPENED"))

    state_desc = (
        f"{len(findings)} findings ({open_findings} active), {len(recs)} recommendations, {len(actions)} actions. "
        f"Verified savings: {total_avoided_kwh:.2f} kWh (₹{total_avoided_cost:.2f})."
        if verified_asms
        else f"{len(findings)} findings ({open_findings} active), {len(recs)} recommendations, {len(actions)} actions. No verified intervention savings."
    )

    return {
        "total_findings": len(findings),
        "open_findings": open_findings,
        "total_recommendations": len(recs),
        "total_actions": len(actions),
        "actions_by_status": actions_by_status,
        "actions_by_review_status": actions_by_review,
        "total_assessments": len(assessments),
        "verified_savings_count": len(verified_asms),
        "total_verified_avoided_kwh": round(total_avoided_kwh, 2) if verified_asms else None,
        "total_verified_avoided_cost_inr": round(total_avoided_cost, 2) if verified_asms else None,
        "lifecycle_state_summary": state_desc,
        "evidence_needed": evidence_needed,
    }


def get_daily_pipeline_status(
    session: Session,
    reporting_date: date,
    plant_id: str = "IN-TN-01",
) -> Dict[str, Any]:
    """
    Retrieve authoritative pipeline status for a reporting date.
    Strictly verifies fact tables and upload history, recovering interrupted states
    and detecting stale analytics when source telemetry is updated.
    """
    date_str = reporting_date.isoformat()
    db_run = session.execute(
        select(DailyPipelineRun)
        .where(
            DailyPipelineRun.reporting_date == reporting_date,
            DailyPipelineRun.plant_id == plant_id,
            DailyPipelineRun.is_current == True,
        )
        .order_by(DailyPipelineRun.id.desc())
    ).scalars().first()

    # Query superseded (historical lineage) runs for corrected uploads
    superseded_runs_stmt = (
        select(DailyPipelineRun)
        .where(
            DailyPipelineRun.reporting_date == reporting_date,
            DailyPipelineRun.plant_id == plant_id,
            DailyPipelineRun.is_current == False,
        )
        .order_by(DailyPipelineRun.id.desc())
    )
    superseded_runs = session.execute(superseded_runs_stmt).scalars().all()
    superseded_runs_info = [
        {
            "run_id": sr.run_id,
            "status": sr.status,
            "input_batch_id": sr.input_batch_id,
            "findings_synchronized_count": sr.findings_synchronized_count,
            "new_findings_count": sr.new_findings_count,
            "reused_findings_count": sr.reused_findings_count,
            "started_at": sr.started_at.isoformat() if sr.started_at else None,
            "completed_at": sr.completed_at.isoformat() if sr.completed_at else None,
        }
        for sr in superseded_runs
    ]

    saved = {}
    if db_run and db_run.stage_states_json:
        try:
            saved = json.loads(db_run.stage_states_json)
        except Exception:
            saved = {}
    all_states = _load_all_pipeline_states()
    file_saved = all_states.get(date_str, {})
    if file_saved:
        saved.update(file_saved)

    # 1. Authoritative verification against PostgreSQL fact tables
    energy_filters = [FactEnergyMeterHourly.date == reporting_date]
    if plant_id:
        energy_filters.append(FactEnergyMeterHourly.plant_id == plant_id)
    energy_rows_count = session.query(func.count(FactEnergyMeterHourly.meter_reading_id)).filter(*energy_filters).scalar() or 0

    prod_filters = [FactHourlyProduction.event_date == reporting_date]
    if plant_id:
        prod_filters.append(FactHourlyProduction.plant_id == plant_id)
    production_rows_count = session.query(func.count(FactHourlyProduction.event_id)).filter(*prod_filters).scalar() or 0

    uploads_stmt = select(UploadHistory).filter(
        UploadHistory.reporting_date == reporting_date
    ).order_by(UploadHistory.uploaded_at.desc())
    uploads: List[UploadHistory] = session.execute(uploads_stmt).scalars().all()

    # Distinguish Energy vs Production uploads
    energy_uploads = [u for u in uploads if u.report_type in ("ENERGY", "ENERGY_AND_PRODUCTION")]
    prod_uploads = [u for u in uploads if u.report_type in ("PRODUCTION", "ENERGY_AND_PRODUCTION")]

    completed_energy_uploads = [u for u in energy_uploads if u.status in ("COMPLETED", "PARTIAL")]
    completed_prod_uploads = [u for u in prod_uploads if u.status in ("COMPLETED", "PARTIAL")]

    # Verify upload linkage via upload_id in fact tables
    energy_uids = [u.upload_id for u in completed_energy_uploads]
    prod_uids = [u.upload_id for u in completed_prod_uploads]

    if energy_uids:
        linked_energy_count = session.query(func.count(FactEnergyMeterHourly.meter_reading_id)).filter(
            *energy_filters,
            FactEnergyMeterHourly.upload_id.in_(energy_uids),
        ).scalar() or 0
    else:
        linked_energy_count = 0

    if prod_uids:
        linked_production_count = session.query(func.count(FactHourlyProduction.event_id)).filter(
            *prod_filters,
            FactHourlyProduction.upload_id.in_(prod_uids),
        ).scalar() or 0
    else:
        linked_production_count = 0

    has_uploaded_energy = bool(completed_energy_uploads) and (
        linked_energy_count > 0 or (energy_rows_count > 0 and any(u.duplicate_rows > 0 for u in completed_energy_uploads))
    )
    has_uploaded_production = bool(completed_prod_uploads) and (
        linked_production_count > 0 or (production_rows_count > 0 and any(u.duplicate_rows > 0 for u in completed_prod_uploads))
    )
    has_uploaded_both = has_uploaded_energy and has_uploaded_production

    has_energy = energy_rows_count > 0
    has_production = production_rows_count > 0
    has_data = has_energy or has_production
    has_both = has_energy and has_production

    # Check for staged uploads waiting for confirmation
    from app.services.daily_report_service import list_staged_reports_for_date
    staged_reports = list_staged_reports_for_date(reporting_date)

    stages: Dict[str, Any] = {}

    # Stage 1: Data Upload
    if uploads:
        upload_files = [
            {
                "upload_id": u.upload_id,
                "filename": u.filename,
                "report_type": u.report_type,
                "size_bytes": u.file_size_bytes,
                "status": u.status,
                "uploaded_at": u.uploaded_at.isoformat() if u.uploaded_at else None,
            }
            for u in uploads
        ]
        energy_count_display = energy_rows_count if energy_rows_count > 0 else linked_energy_count
        prod_count_display = production_rows_count if production_rows_count > 0 else linked_production_count
        summary_text = (
            f"{energy_count_display} Energy entries · {prod_count_display} Production entries"
            if (energy_count_display > 0 or prod_count_display > 0)
            else f"{len(uploads)} file(s) recorded in upload history ({sum(u.file_size_bytes for u in uploads)} bytes total)"
        )
        stages["data_upload"] = {
            "status": "COMPLETED",
            "timestamp": uploads[0].uploaded_at.isoformat() if uploads[0].uploaded_at else None,
            "summary": summary_text,
            "details": {"files": upload_files, "has_linked_uploads": True},
        }
    elif staged_reports:
        stages["data_upload"] = {
            "status": "COMPLETED",
            "timestamp": staged_reports[0].get("staged_at"),
            "summary": f"{len(staged_reports)} file(s) staged and validated for ingestion.",
            "details": {"files": staged_reports, "has_staged_files": True},
        }
    elif has_data:
        # Historical seeded baseline telemetry without daily report uploads
        stages["data_upload"] = {
            "status": "COMPLETED",
            "timestamp": None,
            "summary": (
                f"{energy_rows_count} Energy entries · {production_rows_count} Production entries"
                if (energy_rows_count > 0 or production_rows_count > 0)
                else "No entries recorded for this plant and reporting date."
            ),
            "details": {"is_historical_baseline": True, "files": [], "energy_saved": energy_rows_count, "production_saved": production_rows_count},
        }
    elif saved.get("data_upload") and saved["data_upload"].get("status") in ("COMPLETED", "IN_PROGRESS"):
        stages["data_upload"] = saved["data_upload"]
    else:
        stages["data_upload"] = {
            "status": "NOT_STARTED",
            "timestamp": None,
            "summary": "Awaiting Energy Telemetry and Production Output file selection.",
            "details": None,
        }

    # Missing inputs and unavailable metrics tracking for partial/missing coverage
    missing_inputs: List[str] = []
    unavailable_metrics: List[str] = []
    if not has_energy and has_production:
        missing_inputs.append("Energy Telemetry")
        unavailable_metrics = [
            "Process SEC (kWh/good unit)",
            "Estimated Cost/Good Unit (₹/unit)",
            "Power Factor Deficit Analysis",
            "Avoided Energy (kWh)",
            "Savings Ledger Entries",
        ]
    elif has_energy and not has_production:
        missing_inputs.append("Production Output")
        unavailable_metrics = [
            "Process SEC (kWh/good unit)",
            "Estimated Cost/Good Unit (₹/unit)",
            "Good Unit Yield (%)",
            "Target Production Attainment (%)",
            "Avoided Cost / Good Unit",
        ]
    elif not has_energy and not has_production:
        missing_inputs = ["Energy Telemetry", "Production Output"]
        unavailable_metrics = [
            "All Energy Intensity KPIs",
            "All Production KPIs",
            "Operating Context Stoppages",
            "Anomaly Detection",
            "Savings Ledger Entries",
        ]

    # Stage 2: Validation
    if uploads:
        total_valid = sum(u.valid_rows for u in uploads)
        total_rejected = sum(u.rejected_rows for u in uploads)
        total_duplicates = sum(u.duplicate_rows for u in uploads)
        is_duplicate_no_change = total_duplicates > 0 and total_valid == 0
        has_warnings = total_rejected > 0 or any(u.status == "PARTIAL" for u in uploads) or is_duplicate_no_change

        val_summary = f"{total_valid} valid rows verified ({total_rejected} rejected, {total_duplicates} duplicate)"
        if is_duplicate_no_change:
            val_summary = f"Duplicate upload with no changes: {total_duplicates} rows matched existing records (0 new rows). Existing pipeline data reused."

        stages["validation"] = {
            "status": "COMPLETED_WITH_WARNINGS" if has_warnings else "COMPLETED",
            "timestamp": uploads[0].uploaded_at.isoformat() if uploads[0].uploaded_at else None,
            "summary": val_summary,
            "details": {
                "total_valid_rows": total_valid,
                "total_rejected_rows": total_rejected,
                "total_duplicate_rows": total_duplicates,
                "is_duplicate_no_change": is_duplicate_no_change,
                "files_validated": len(uploads),
            },
        }
    elif staged_reports:
        total_staged_valid = sum(s.get("valid_rows", 0) for s in staged_reports)
        total_staged_rejected = sum(s.get("rejected_rows", 0) for s in staged_reports)
        energy_staged = next((s for s in staged_reports if s.get("report_type") == "ENERGY"), None)
        prod_staged = next((s for s in staged_reports if s.get("report_type") == "PRODUCTION"), None)
        has_warnings = total_staged_rejected > 0
        stages["validation"] = {
            "status": "COMPLETED_WITH_WARNINGS" if has_warnings else "COMPLETED",
            "timestamp": staged_reports[0].get("staged_at"),
            "summary": f"{total_staged_valid} valid rows verified ({total_staged_rejected} rejected) across staged daily reports.",
            "details": {
                "total_valid_rows": total_staged_valid,
                "total_rejected_rows": total_staged_rejected,
                "files_validated": len(staged_reports),
                "has_staged_files": True,
                "has_staged_energy": bool(energy_staged),
                "has_staged_production": bool(prod_staged),
                "energy_upload_id": energy_staged.get("upload_id") if energy_staged else None,
                "production_upload_id": prod_staged.get("upload_id") if prod_staged else None,
                "staged_files": staged_reports,
            },
        }
    elif has_data:
        stages["validation"] = {
            "status": "NOT_STARTED",
            "timestamp": None,
            "summary": "Awaiting daily report file upload for validation.",
            "details": None,
        }
    elif saved.get("validation") and saved["validation"].get("status") in ("COMPLETED", "COMPLETED_WITH_WARNINGS", "IN_PROGRESS", "FAILED"):
        stages["validation"] = saved["validation"]
    else:
        stages["validation"] = {
            "status": "NOT_STARTED" if stages["data_upload"]["status"] == "COMPLETED" else "BLOCKED",
            "timestamp": None,
            "summary": "Pending file upload validation review.",
            "details": None,
        }

    # Stage 3: Database Ingestion (Strict ground-truth enforcement)
    if has_data:
        if uploads and (has_uploaded_energy or has_uploaded_production):
            # Ingestion derived from verified daily upload records
            completed_batches = completed_energy_uploads + completed_prod_uploads
            total_rejected_in_completed = sum(u.rejected_rows for u in completed_batches)
            total_dup_in_completed = sum(u.duplicate_rows for u in completed_batches)
            has_partial_uploads = any(u.status == "PARTIAL" or u.rejected_rows > 0 for u in completed_batches)
            is_dup_no_change = total_dup_in_completed > 0 and sum(u.valid_rows for u in completed_batches) == 0

            latest_energy_upload = None
            if completed_energy_uploads:
                eu = completed_energy_uploads[0]
                latest_energy_upload = {
                    "upload_id": eu.upload_id,
                    "filename": eu.filename,
                    "newly_inserted": eu.valid_rows,
                    "skipped_duplicates": eu.duplicate_rows,
                    "rejected_rows": eu.rejected_rows,
                    "total_rows": eu.total_rows,
                    "status": eu.status,
                    "is_duplicate_only": (eu.valid_rows == 0 and eu.duplicate_rows > 0),
                    "uploaded_at": eu.uploaded_at.isoformat() if eu.uploaded_at else None,
                }

            latest_production_upload = None
            if completed_prod_uploads:
                pu = completed_prod_uploads[0]
                latest_production_upload = {
                    "upload_id": pu.upload_id,
                    "filename": pu.filename,
                    "newly_inserted": pu.valid_rows,
                    "skipped_duplicates": pu.duplicate_rows,
                    "rejected_rows": pu.rejected_rows,
                    "total_rows": pu.total_rows,
                    "status": pu.status,
                    "is_duplicate_only": (pu.valid_rows == 0 and pu.duplicate_rows > 0),
                    "uploaded_at": pu.uploaded_at.isoformat() if pu.uploaded_at else None,
                }

            if is_dup_no_change:
                status_ingest = "COMPLETED"
                summary_msg = f"Already stored — 0 new rows: {total_dup_in_completed} duplicate rows skipped. Retained {energy_rows_count} energy rows and {production_rows_count} production rows in database."
            elif has_uploaded_both and not has_partial_uploads:
                status_ingest = "COMPLETED"
                summary_msg = f"Verified {linked_energy_count} energy rows and {linked_production_count} production rows linked to upload history."
            else:
                status_ingest = "COMPLETED_WITH_WARNINGS"
                if not has_uploaded_both:
                    missing_part = "Production Output" if not has_uploaded_production else "Energy Telemetry"
                    summary_msg = f"Verified {linked_energy_count} energy rows and {linked_production_count} production rows linked to upload history. Note: {missing_part} daily report upload is missing for this date."
                    if has_partial_uploads:
                        summary_msg += f" ({total_rejected_in_completed} rejected rows across uploaded batches)."
                else:
                    summary_msg = f"Verified {linked_energy_count} energy rows and {linked_production_count} production rows linked to upload history (Partial ingestion: {total_rejected_in_completed} rejected rows across uploaded batches)."

            latest_upload_ts = uploads[0].uploaded_at.isoformat() if uploads[0].uploaded_at else datetime.utcnow().isoformat()
            is_historical = False
        else:
            # Ingestion derived from verified historical baseline telemetry
            status_ingest = "COMPLETED" if has_both else "COMPLETED_WITH_WARNINGS"
            summary_msg = f"Historical baseline telemetry verified in PostgreSQL ({energy_rows_count} energy rows, {production_rows_count} production rows; seeded/baseline data, not from daily report upload)."
            if not has_both:
                missing_part = "Production Output" if not has_production else "Energy Telemetry"
                summary_msg += f" Note: {missing_part} records are missing for this date."
            latest_upload_ts = datetime.combine(reporting_date, datetime.min.time()).isoformat()
            is_historical = True
            has_partial_uploads = False
            total_rejected_in_completed = 0
            is_dup_no_change = False

        stages["database_ingestion"] = {
            "status": status_ingest,
            "timestamp": latest_upload_ts,
            "summary": summary_msg,
            "details": {
                "energy_records": energy_rows_count,
                "production_records": production_rows_count,
                "linked_energy_records": linked_energy_count,
                "linked_production_records": linked_production_count,
                "is_historical_baseline": is_historical,
                "has_energy": has_energy,
                "has_production": has_production,
                "has_partial_uploads": has_partial_uploads,
                "rejected_rows_count": total_rejected_in_completed,
                "superseded_runs_count": len(superseded_runs_info),
                "superseded_runs": superseded_runs_info,
                "is_duplicate_no_change": is_dup_no_change,
                "latest_energy_upload": latest_energy_upload if not is_historical else None,
                "latest_production_upload": latest_production_upload if not is_historical else None,
                "total_stored_energy": energy_rows_count,
                "total_stored_production": production_rows_count,
            },
        }
    else:
        # Strictly never mark ingestion COMPLETED when zero records exist in PostgreSQL
        can_ingest = stages["validation"]["status"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS")
        stages["database_ingestion"] = {
            "status": "NOT_STARTED" if can_ingest else "BLOCKED",
            "timestamp": None,
            "summary": "Requires operator confirmation to ingest validated records into fact tables." if can_ingest else "Blocked until files are validated.",
            "details": {
                "has_staged_files": bool(staged_reports),
                "staged_reports_count": len(staged_reports),
            } if staged_reports else None,
        }

    ingestion_ok = stages["database_ingestion"]["status"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS")

    # Detect stale downstream results if data was ingested after downstream execution
    last_ingest_time_str = stages["database_ingestion"].get("timestamp")
    last_ingest_dt: Optional[datetime] = None
    if last_ingest_time_str:
        try:
            last_ingest_dt = datetime.fromisoformat(last_ingest_time_str)
        except Exception:
            pass

    # Check whether the downstream pipeline is actively executing in this process
    is_actively_running = is_date_locked(date_str)

    downstream_keys = [
        "data_reconciliation",
        "daily_analytics",
        "intelligence_report",
        "anomaly_detection",
        "investigation_handoff",
    ]

    for key in downstream_keys:
        stage_record = saved.get(key)
        if stage_record and ingestion_ok:
            # Check for interrupted/crashed execution (ONLY when not actively executing)
            if stage_record.get("status") == "IN_PROGRESS":
                if not is_actively_running:
                    stage_record["status"] = "FAILED"
                    stage_record["summary"] = "Stage execution was interrupted by an application restart or crash. Click 'Retry Stage' to resume."
                    stage_record["details"] = {"error": "Execution interrupted before completion", "interrupted": True}

            # Check for staleness against latest ingestion
            stage_ts_str = stage_record.get("timestamp")
            if stage_ts_str and last_ingest_dt and not is_actively_running:
                try:
                    stage_dt = datetime.fromisoformat(stage_ts_str)
                    if stage_dt < last_ingest_dt:
                        stage_record = {
                            "status": "NOT_STARTED",
                            "timestamp": None,
                            "summary": "Source telemetry updated. Downstream pipeline re-run required.",
                            "details": None,
                        }
                except Exception:
                    pass

            stages[key] = stage_record
        else:
            stages[key] = {
                "status": "NOT_STARTED" if ingestion_ok else "BLOCKED",
                "timestamp": None,
                "summary": "Ready to execute downstream processing." if ingestion_ok else "Blocked until database ingestion completes.",
                "details": None,
            }

    if db_run and db_run.status == "STALE":
        for key in downstream_keys:
            stages[key] = {
                "status": "NOT_STARTED",
                "timestamp": None,
                "summary": "Source telemetry updated. Downstream pipeline re-run required.",
                "details": None,
            }

    # Determine current active stage index
    if stages.get("database_ingestion", {}).get("status") in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
        # Ingestion is established; active focus is on downstream intelligence processing
        current_stage_idx = 2  # database_ingestion
        for idx in range(3, len(STAGE_KEYS)):
            key = STAGE_KEYS[idx]
            st = stages[key]["status"]
            if st in ("NOT_STARTED", "IN_PROGRESS", "FAILED"):
                current_stage_idx = idx
                break
            elif st in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
                current_stage_idx = idx
    else:
        current_stage_idx = 0
        for idx in range(3):
            key = STAGE_KEYS[idx]
            st = stages[key]["status"]
            if st in ("NOT_STARTED", "IN_PROGRESS", "FAILED"):
                current_stage_idx = idx
                break
            elif st in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
                current_stage_idx = min(idx + 1, 2)

    interrupted_run_detected = False
    recovery_action = None
    if db_run and db_run.status in ("RUNNING", "IN_PROGRESS") and not is_actively_running:
        interrupted_run_detected = True
        recovery_action = {
            "recommended_action": "RESUME_OR_RETRY",
            "last_persisted_stage": db_run.current_stage or "database_ingestion",
            "message": "Previous pipeline run was interrupted before completion. Idempotent rerun will preserve deduplication and reuse existing fact records.",
        }

    human_action_summary = get_human_action_summary_for_date(session, reporting_date, plant_id)
    if "investigation_handoff" in stages and isinstance(stages["investigation_handoff"].get("details"), dict):
        stages["investigation_handoff"]["details"]["human_action_summary"] = human_action_summary

    pipeline_run_info = None
    if db_run:
        pipeline_run_info = {
            "run_id": db_run.run_id,
            "status": db_run.status,
            "input_batch_id": db_run.input_batch_id,
            "items_prepared_count": db_run.items_prepared_count,
            "findings_synchronized_count": db_run.findings_synchronized_count,
            "new_findings_count": db_run.new_findings_count,
            "reused_findings_count": db_run.reused_findings_count,
            "is_current": db_run.is_current,
            "started_at": db_run.started_at.isoformat() if db_run.started_at else None,
            "completed_at": db_run.completed_at.isoformat() if db_run.completed_at else None,
        }

    return {
        "reporting_date": date_str,
        "plant_id": plant_id,
        "current_stage": STAGE_KEYS[current_stage_idx],
        "current_stage_index": current_stage_idx,
        "stages": stages,
        "pipeline_run": pipeline_run_info,
        "superseded_runs": superseded_runs_info,
        "human_action_summary": human_action_summary,
        "interrupted_run": interrupted_run_detected,
        "recovery_action": recovery_action,
        "database_state": {
            "has_data": has_data,
            "has_energy": has_energy,
            "has_production": has_production,
            "energy_records": energy_rows_count,
            "production_records": production_rows_count,
            "upload_count": len(uploads),
            "missing_inputs": missing_inputs,
            "unavailable_metrics": unavailable_metrics,
        },
    }


def record_pipeline_stage_state(
    reporting_date: date,
    stage_id: str,
    status: str,
    summary: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist an individual stage state safely under global file lock."""
    date_str = reporting_date.isoformat()
    with _FILE_LOCK:
        all_states = _load_all_pipeline_states()
        if date_str not in all_states:
            all_states[date_str] = {}

        all_states[date_str][stage_id] = {
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": summary,
            "details": details,
        }
        _save_all_pipeline_states(all_states)
        return all_states[date_str][stage_id]


def run_downstream_pipeline(
    session: Session,
    reporting_date: date,
    plant_id: str = "IN-TN-01",
) -> Dict[str, Any]:
    """
    Executes stages 4 through 8 sequentially with per-date execution locking:
    4. Data Reconciliation
    5. Daily Analytics
    6. Daily Intelligence Report
    7. Anomaly Detection
    8. Investigation Handoff

    Preserves successful prior stage outputs if a later stage fails, and enforces
    strict accuracy constraints (distinguishing missing data from zero, validating SEC alignment).
    """
    date_str = reporting_date.isoformat()
    date_lock = _get_date_lock(date_str)

    # Prevent concurrent downstream runs on the same date
    if not date_lock.acquire(blocking=False):
        logger.warning("Downstream pipeline already in progress for date: %s", date_str)
        return get_daily_pipeline_status(session, reporting_date, plant_id)

    try:
        logger.info("Executing downstream operations pipeline for date: %s, plant: %s", date_str, plant_id)

        # Check for existing current run to resume
        existing_run = session.execute(
            select(DailyPipelineRun)
            .where(
                DailyPipelineRun.reporting_date == reporting_date,
                DailyPipelineRun.plant_id == plant_id,
                DailyPipelineRun.is_current == True,
            )
            .order_by(DailyPipelineRun.id.desc())
        ).scalars().first()

        if existing_run:
            current_db_run = existing_run
            current_db_run.status = "RUNNING"
            logger.info(
                "Resuming existing pipeline run %s (batch %s) for %s / %s",
                current_db_run.run_id,
                current_db_run.input_batch_id,
                date_str,
                plant_id,
            )
        else:
            # Invalidate prior current runs for this date and plant if any
            session.execute(
                update(DailyPipelineRun)
                .where(
                    DailyPipelineRun.reporting_date == reporting_date,
                    DailyPipelineRun.plant_id == plant_id,
                    DailyPipelineRun.is_current == True,
                )
                .values(is_current=False)
            )
            session.flush()

            upload_stmt = select(UploadHistory.upload_id).where(
                UploadHistory.reporting_date == reporting_date
            )
            ups = session.execute(upload_stmt).scalars().all()
            batch_id = ",".join(ups) if ups else f"BATCH-{reporting_date.strftime('%Y%m%d')}-{plant_id}"

            run_id = f"RUN-{plant_id}-{reporting_date.strftime('%Y%m%d')}-{int(time.time())}"
            current_db_run = DailyPipelineRun(
                run_id=run_id,
                reporting_date=reporting_date,
                plant_id=plant_id,
                input_batch_id=batch_id,
                status="RUNNING",
                current_stage="data_reconciliation",
                stage_states_json="{}",
                items_prepared_count=0,
                findings_synchronized_count=0,
                new_findings_count=0,
                reused_findings_count=0,
                is_current=True,
                started_at=datetime.utcnow(),
            )
            session.add(current_db_run)
        session.commit()

        saved = {}
        if current_db_run.stage_states_json:
            try:
                saved = json.loads(current_db_run.stage_states_json)
            except Exception:
                saved = {}
        all_states = _load_all_pipeline_states()
        file_saved = all_states.get(date_str, {})
        if file_saved:
            saved.update(file_saved)

        # Retrieve latest ingestion timestamp to check for stale downstream results.
        # A completed stage from a prior run must NOT be reused if its timestamp precedes
        # the latest database ingestion revision.
        initial_status = get_daily_pipeline_status(session, reporting_date, plant_id)
        last_ingest_time_str = initial_status.get("stages", {}).get("database_ingestion", {}).get("timestamp")
        last_ingest_dt: Optional[datetime] = None
        if last_ingest_time_str:
            try:
                last_ingest_dt = datetime.fromisoformat(last_ingest_time_str)
            except Exception:
                pass

        def _is_stage_fresh(stage_key: str) -> bool:
            record = saved.get(stage_key)
            if not record or record.get("status") not in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
                return False
            ts_str = record.get("timestamp")
            if not ts_str:
                return False
            if last_ingest_dt:
                try:
                    stage_dt = datetime.fromisoformat(ts_str)
                    if stage_dt < last_ingest_dt:
                        return False
                except Exception:
                    return False
            return True

        has_prior_recon = _is_stage_fresh("data_reconciliation")
        has_prior_analytics = has_prior_recon and _is_stage_fresh("daily_analytics")
        has_prior_intel = has_prior_analytics and _is_stage_fresh("intelligence_report")

        # -------------------------------------------------------------------------
        # STAGE 4: Data Reconciliation
        # -------------------------------------------------------------------------
        if has_prior_recon:
            recon_status = saved["data_reconciliation"]["status"]
            recon_summary = saved["data_reconciliation"].get("summary", "Reconciliation completed.")
            recon_details = saved["data_reconciliation"].get("details", {})
        else:
            current_db_run.current_stage = "data_reconciliation"
            session.commit()
            record_pipeline_stage_state(
                reporting_date=reporting_date,
                stage_id="data_reconciliation",
                status="IN_PROGRESS",
                summary="Evaluating cross-source reconciliation rules...",
            )

            try:
                recon_report = run_cross_source_reconciliation(
                    session=session,
                    start_date=reporting_date,
                    end_date=reporting_date,
                    plant_id=plant_id,
                )
                recon_counts = recon_report.counts
                recon_status = "COMPLETED"
                if recon_counts.fail_count > 0:
                    recon_status = "COMPLETED_WITH_WARNINGS"
                elif recon_counts.warning_count > 0:
                    recon_status = "COMPLETED_WITH_WARNINGS"

                recon_summary = (
                    f"Reconciliation evaluated {recon_counts.total_checks} checks: "
                    f"{recon_counts.pass_count} Passed, {recon_counts.warning_count} Warnings, {recon_counts.fail_count} Failed."
                )
                recon_details = {
                    "status": str(recon_report.status),
                    "counts": recon_counts.model_dump(),
                    "checks": [c.model_dump() for c in recon_report.checks],
                    "limitations": recon_report.limitations,
                }
            except Exception as e:
                logger.exception("Reconciliation stage failed: %s", str(e))
                session.rollback()
                raw_err = str(e).split("\n")[0].strip()
                concise_err = raw_err.split("] ")[-1] if "] " in raw_err else raw_err
                if len(concise_err) > 160:
                    concise_err = concise_err[:157] + "..."
                recon_status = "FAILED"
                recon_summary = f"Reconciliation execution failed: {concise_err}"
                recon_details = {"error": concise_err}
                record_pipeline_stage_state(
                    reporting_date=reporting_date,
                    stage_id="data_reconciliation",
                    status="FAILED",
                    summary=recon_summary,
                    details=recon_details,
                )
                for b_stage in ("daily_analytics", "intelligence_report", "anomaly_detection", "investigation_handoff"):
                    record_pipeline_stage_state(
                        reporting_date=reporting_date,
                        stage_id=b_stage,
                        status="BLOCKED",
                        summary="Blocked: Requires successful data_reconciliation.",
                        details={"error": "Upstream stage data_reconciliation failed"},
                    )
                current_db_run.status = "FAILED"
                current_db_run.current_stage = "data_reconciliation"
                current_db_run.completed_at = datetime.utcnow()
                current_status = get_daily_pipeline_status(session, reporting_date, plant_id)
                current_db_run.stage_states_json = json.dumps(current_status.get("stages", {}), default=_json_serial)
                session.commit()
                return current_status

            record_pipeline_stage_state(
                reporting_date=reporting_date,
                stage_id="data_reconciliation",
                status=recon_status,
                summary=recon_summary,
                details=recon_details,
            )

        # -------------------------------------------------------------------------
        # STAGE 5: Daily Analytics
        # -------------------------------------------------------------------------
        if has_prior_analytics:
            analytics_status = saved["daily_analytics"]["status"]
            analytics_summary = saved["daily_analytics"].get("summary", "Daily analytics computed.")
            analytics_details = saved["daily_analytics"].get("details", {})
        else:
            current_db_run.current_stage = "daily_analytics"
            session.commit()
            record_pipeline_stage_state(
                reporting_date=reporting_date,
                stage_id="daily_analytics",
                status="IN_PROGRESS",
                summary="Computing energy, production, and Specific Energy Consumption metrics...",
            )

            try:
                energy_sum = get_energy_summary(session, plant_id=plant_id, start_date=reporting_date, end_date=reporting_date)
                meter_sum = get_energy_by_meter(session, plant_id=plant_id, start_date=reporting_date, end_date=reporting_date)
                area_sum = get_energy_by_area(session, plant_id=plant_id, start_date=reporting_date, end_date=reporting_date)
                pf_sum = get_power_factor_summary(session, plant_id=plant_id, start_date=reporting_date, end_date=reporting_date)
                prod_sum = get_production_summary(session, plant_id=plant_id, start_date=reporting_date, end_date=reporting_date)
                line_sum = get_production_by_line(session, plant_id=plant_id, start_date=reporting_date, end_date=reporting_date)
                proc_sec = get_process_energy_analytics(session, plant_id=plant_id, start_date=reporting_date, end_date=reporting_date)
                factory_sec = get_factory_energy_analytics(session, plant_id=plant_id, start_date=reporting_date, end_date=reporting_date)

                total_kwh = energy_sum.get("total_consumption_kwh")
                total_inr = energy_sum.get("total_cost_inr")
                actual_qty = prod_sum.get("actual_qty")
                avg_pf = pf_sum.get("avg_power_factor")

                analytics_status = "COMPLETED"
                summary_parts = []
                if total_kwh is not None:
                    summary_parts.append(f"{total_kwh:,.2f} kWh (INR {total_inr:,.2f})" if total_inr is not None else f"{total_kwh:,.2f} kWh")
                else:
                    summary_parts.append("Energy: Unavailable")

                if actual_qty is not None:
                    summary_parts.append(f"{actual_qty:,} devices produced")
                else:
                    summary_parts.append("Production: Unavailable")

                if avg_pf is not None:
                    summary_parts.append(f"Avg PF: {avg_pf:.3f}")
                else:
                    summary_parts.append("PF: Unavailable")

                analytics_summary = f"Calculated: {', '.join(summary_parts)}."

                analytics_details = {
                    "energy_summary": energy_sum,
                    "meters": meter_sum,
                    "areas": area_sum,
                    "power_factor": pf_sum,
                    "production_summary": prod_sum,
                    "lines": line_sum,
                    "process_sec": proc_sec,
                    "factory_sec": factory_sec,
                }
            except Exception as e:
                logger.exception("Daily analytics stage failed: %s", str(e))
                session.rollback()
                raw_err = str(e).split("\n")[0].strip()
                concise_err = raw_err.split("] ")[-1] if "] " in raw_err else raw_err
                if len(concise_err) > 160:
                    concise_err = concise_err[:157] + "..."
                analytics_status = "FAILED"
                analytics_summary = f"Analytics calculation failed: {concise_err}"
                analytics_details = {"error": concise_err}
                record_pipeline_stage_state(
                    reporting_date=reporting_date,
                    stage_id="daily_analytics",
                    status="FAILED",
                    summary=analytics_summary,
                    details=analytics_details,
                )
                for b_stage in ("intelligence_report", "anomaly_detection", "investigation_handoff"):
                    record_pipeline_stage_state(
                        reporting_date=reporting_date,
                        stage_id=b_stage,
                        status="BLOCKED",
                        summary="Blocked: Requires successful daily_analytics.",
                        details={"error": "Upstream stage daily_analytics failed"},
                    )
                current_db_run.status = "FAILED"
                current_db_run.current_stage = "daily_analytics"
                current_db_run.completed_at = datetime.utcnow()
                current_status = get_daily_pipeline_status(session, reporting_date, plant_id)
                current_db_run.stage_states_json = json.dumps(current_status.get("stages", {}), default=_json_serial)
                session.commit()
                return current_status

            record_pipeline_stage_state(
                reporting_date=reporting_date,
                stage_id="daily_analytics",
                status=analytics_status,
                summary=analytics_summary,
                details=analytics_details,
            )

        # -------------------------------------------------------------------------
        # STAGE 6: Daily Intelligence Report
        # -------------------------------------------------------------------------
        if has_prior_intel:
            intel_status = saved["intelligence_report"]["status"]
            intel_summary = saved["intelligence_report"].get("summary", "Daily intelligence report compiled.")
            intel_details = saved["intelligence_report"].get("details", {})
        else:
            current_db_run.current_stage = "intelligence_report"
            session.commit()
            record_pipeline_stage_state(
                reporting_date=reporting_date,
                stage_id="intelligence_report",
                status="IN_PROGRESS",
                summary="Synthesizing daily operations intelligence briefing...",
            )

            try:
                report_sections = []
                analytics_data = analytics_details if not has_prior_analytics else (saved.get("daily_analytics", {}).get("details") or {})
                if analytics_status in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
                    tot_kwh = analytics_data.get("energy_summary", {}).get("total_consumption_kwh")
                    tot_inr = analytics_data.get("energy_summary", {}).get("total_cost_inr")
                    tot_emissions = analytics_data.get("energy_summary", {}).get("total_co2e_kg")
                    tot_qty = analytics_data.get("production_summary", {}).get("actual_qty")
                    good_qty = analytics_data.get("production_summary", {}).get("good_qty")
                    reject_qty = analytics_data.get("production_summary", {}).get("reject_qty")

                    # Energy performance narrative
                    if tot_kwh is not None:
                        cost_text = f"for an electricity cost of INR {tot_inr:,.2f}" if tot_inr is not None else "with cost unavailable"
                        emiss_text = f"and carbon footprint of {tot_emissions:,.2f} kg CO2e" if tot_emissions is not None else "with carbon emissions unavailable"
                        report_sections.append(f"Plant {plant_id} consumed {tot_kwh:,.2f} kWh {cost_text} {emiss_text}.")
                    else:
                        report_sections.append(f"Plant {plant_id} electrical energy consumption was unavailable for {date_str}.")

                    # Production output narrative
                    if tot_qty is not None and tot_qty > 0:
                        scrap_rate = (reject_qty / tot_qty * 100) if (reject_qty is not None and tot_qty > 0) else 0.0
                        good_yield = (good_qty / tot_qty * 100) if (good_qty is not None and tot_qty > 0) else 0.0
                        report_sections.append(
                            f"Output totaled {tot_qty:,} units ({good_qty or 0:,} good, {reject_qty or 0:,} scrap; reject rate {scrap_rate:.2f}%, good-output yield {good_yield:.2f}%)."
                        )
                    elif tot_qty == 0:
                        report_sections.append(f"Output recorded was 0 units across all production lines for {date_str}.")
                    else:
                        report_sections.append(f"Production output records were unavailable for {date_str}.")

                    # Specific Energy Consumption (SEC) - verified alignment
                    smt_summary = analytics_data.get("process_sec", {}).get("smt_summary", {})
                    smt_sec = smt_summary.get("kwh_per_good_unit") or smt_summary.get("overall_process_sec_good_kwh_per_board") or smt_summary.get("overall_process_sec_kwh_per_board")
                    smt_sec_actual = smt_summary.get("kwh_per_actual_unit") or smt_summary.get("overall_process_sec_kwh_per_board")
                    if smt_sec is not None:
                        actual_clause = f" (Actual SEC: {float(smt_sec_actual):.4f} kWh/actual board)" if smt_sec_actual is not None else ""
                        report_sections.append(f"SMT Process SEC: {float(smt_sec):.4f} kWh/good board{actual_clause}.")
                    else:
                        report_sections.append("SMT Process SEC: Unavailable (requires matched SMT meter and board production).")

                    fal_summary = analytics_data.get("process_sec", {}).get("fal_summary", {})
                    fal_sec = fal_summary.get("kwh_per_good_unit") or fal_summary.get("overall_process_sec_good_kwh_per_assembly_unit") or fal_summary.get("overall_process_sec_kwh_per_phone")
                    fal_sec_actual = fal_summary.get("kwh_per_actual_unit") or fal_summary.get("overall_process_sec_kwh_per_assembly_unit") or fal_summary.get("overall_process_sec_kwh_per_phone")
                    if fal_sec is not None:
                        actual_clause = f" (Actual SEC: {float(fal_sec_actual):.4f} kWh/actual assembly unit)" if fal_sec_actual is not None else ""
                        report_sections.append(f"FAL Process SEC: {float(fal_sec):.4f} kWh/good assembly unit{actual_clause}.")
                    else:
                        report_sections.append("FAL Process SEC: Unavailable (requires matched FAL meter and assembly production).")

                    fac_sec_data = analytics_data.get("factory_sec", {})
                    elec_int = fac_sec_data.get("electricity_intensity_kwh_per_good_unit")
                    cost_int = fac_sec_data.get("cost_intensity_inr_per_good_unit")
                    emiss_int = fac_sec_data.get("emissions_intensity_co2e_per_good_unit")
                    cov_sum = fac_sec_data.get("coverage_summary", {})
                    cov_status = cov_sum.get("coverage_status", "UNKNOWN")
                    cov_pct = cov_sum.get("coverage_percentage", 0)

                    if elec_int is not None:
                        cost_str = f", Cost: INR {float(cost_int):.2f}/unit" if cost_int is not None else ""
                        emiss_str = f", Emissions: {float(emiss_int):.4f} kg CO2e/unit" if emiss_int is not None else ""
                        report_sections.append(
                            f"Factory Energy Intensity: {float(elec_int):.4f} kWh/good finished unit{cost_str}{emiss_str} "
                            f"[Coverage: {cov_status} ({cov_pct}%)]."
                        )
                    elif fac_sec_data.get("factory_sec_data_available"):
                        fac_val = fac_sec_data.get("factory_sec_kwh_per_finished_unit")
                        report_sections.append(f"Factory SEC: {float(fac_val):.4f} kWh/good finished unit (aligned plant-wide energy / finished goods).")
                    else:
                        note = fac_sec_data.get("electricity_status_reason") or fac_sec_data.get("factory_sec_alignment_note", "incomplete timestamp alignment")
                        report_sections.append(f"Factory Energy Intensity: Unavailable ({note}).")

                intel_status = "COMPLETED"
                intel_summary = "Daily Intelligence Report successfully compiled."
                intel_details = {
                    "title": f"Daily Operations Intelligence Briefing — {date_str}",
                    "key_takeaways": report_sections,
                    "reconciliation_notes": recon_summary,
                    "generated_at": datetime.utcnow().isoformat(),
                }
            except Exception as e:
                logger.exception("Intelligence report stage failed: %s", str(e))
                session.rollback()
                raw_err = str(e).split("\n")[0].strip()
                concise_err = raw_err.split("] ")[-1] if "] " in raw_err else raw_err
                if len(concise_err) > 160:
                    concise_err = concise_err[:157] + "..."
                intel_status = "FAILED"
                intel_summary = f"Intelligence report synthesis failed: {concise_err}"
                intel_details = {"error": concise_err}
                record_pipeline_stage_state(
                    reporting_date=reporting_date,
                    stage_id="intelligence_report",
                    status="FAILED",
                    summary=intel_summary,
                    details=intel_details,
                )
                for b_stage in ("anomaly_detection", "investigation_handoff"):
                    record_pipeline_stage_state(
                        reporting_date=reporting_date,
                        stage_id=b_stage,
                        status="BLOCKED",
                        summary="Blocked: Requires successful intelligence_report.",
                        details={"error": "Upstream stage intelligence_report failed"},
                    )
                current_db_run.status = "FAILED"
                current_db_run.current_stage = "intelligence_report"
                current_db_run.completed_at = datetime.utcnow()
                current_status = get_daily_pipeline_status(session, reporting_date, plant_id)
                current_db_run.stage_states_json = json.dumps(current_status.get("stages", {}), default=_json_serial)
                session.commit()
                return current_status

            record_pipeline_stage_state(
                reporting_date=reporting_date,
                stage_id="intelligence_report",
                status=intel_status,
                summary=intel_summary,
                details=intel_details,
            )

        # -------------------------------------------------------------------------
        # STAGE 7: Anomaly Detection
        # -------------------------------------------------------------------------
        current_db_run.current_stage = "anomaly_detection"
        session.commit()

        record_pipeline_stage_state(
            reporting_date=reporting_date,
            stage_id="anomaly_detection",
            status="IN_PROGRESS",
            summary="Executing statistical, rolling baseline, low power factor, and standby waste detectors...",
        )

        try:
            start_dt = datetime.combine(reporting_date, datetime.min.time())
            end_dt = datetime.combine(reporting_date + timedelta(days=1), datetime.min.time())
            anomalies_res = detect_all_anomalies(
                session=session,
                plant_id=plant_id,
                meter_id=None,
                start_time=start_dt,
                end_time=end_dt,
            )

            total_anom = anomalies_res.get("total_anomalies_detected", 0)
            stat_list = anomalies_res.get("statistical_zscore", {}).get("anomalies", [])
            roll_list = anomalies_res.get("rolling_baseline", {}).get("anomalies", [])
            low_pf_list = anomalies_res.get("low_power_factor", {}).get("anomalies", [])
            standby_list = anomalies_res.get("zero_production_standby", {}).get("anomalies", [])
            baseload_list = anomalies_res.get("persistent_baseload", {}).get("anomalies", [])
            restart_list = anomalies_res.get("zero_output_restart", {}).get("anomalies", [])

            all_detected_events = []
            for a in stat_list:
                all_detected_events.append({**a, "detector": "Statistical Z-Score", "type": "CONSUMPTION_SPIKE"})
            for a in roll_list:
                all_detected_events.append({**a, "detector": "Rolling Baseline", "type": "BASELINE_DEVIATION"})
            for a in low_pf_list:
                all_detected_events.append({**a, "detector": "Low Power Factor", "type": "POWER_FACTOR_DEFICIT"})
            for a in standby_list:
                all_detected_events.append({**a, "detector": "Zero-Production Standby", "type": "STANDBY_WASTE"})
            for a in baseload_list:
                load_cls = a.get("context_flags", {}).get("load_classification", "Baseload drift")
                is_baseload = "Baseload" in load_cls
                detector_label = "Baseload Drift" if is_baseload else "Comparable-Period Shift"
                event_type = a.get("anomaly_type") or ("BASELOAD_DRIFT" if is_baseload else "COMPARABLE_PERIOD_ELECTRICITY_CHANGE")
                all_detected_events.append({**a, "detector": detector_label, "type": event_type})
            for a in restart_list:
                all_detected_events.append({**a, "detector": "Zero-Output & Restart", "type": "STOPPAGE_RESTART_ANOMALY"})

            anom_status = "COMPLETED_WITH_WARNINGS" if total_anom > 0 else "COMPLETED"
            anom_summary = (
                f"Detected {total_anom} anomalies across deterministic surveillance algorithm families."
                if total_anom > 0
                else "Surveillance completed: 0 anomalies detected across all monitoring boundaries."
            )

            anom_details = {
                "total_anomalies": total_anom,
                "counts_by_detector": {
                    "statistical_zscore": len(stat_list),
                    "rolling_baseline": len(roll_list),
                    "low_power_factor": len(low_pf_list),
                    "zero_production_standby": len(standby_list),
                    "persistent_baseload": len(baseload_list),
                    "zero_output_restart": len(restart_list),
                },
                "events": all_detected_events[:60],
            }

            record_pipeline_stage_state(
                reporting_date=reporting_date,
                stage_id="anomaly_detection",
                status=anom_status,
                summary=anom_summary,
                details=anom_details,
            )
        except Exception as e:
            logger.exception("Anomaly detection stage failed: %s", str(e))
            session.rollback()
            raw_err = str(e).split("\n")[0].strip()
            concise_err = raw_err.split("] ")[-1] if "] " in raw_err else raw_err
            if len(concise_err) > 160:
                concise_err = concise_err[:157] + "..."

            anom_status = "FAILED"
            anom_summary = f"Anomaly detection failed: {concise_err}"
            anom_details = {"error": concise_err, "events": []}

            record_pipeline_stage_state(
                reporting_date=reporting_date,
                stage_id="anomaly_detection",
                status=anom_status,
                summary=anom_summary,
                details=anom_details,
            )

            record_pipeline_stage_state(
                reporting_date=reporting_date,
                stage_id="investigation_handoff",
                status="BLOCKED",
                summary="Blocked: Requires successful anomaly detection.",
                details={"error": "Dependent stage anomaly_detection failed", "items": []},
            )

            current_db_run.status = "FAILED"
            current_db_run.current_stage = "anomaly_detection"
            current_db_run.completed_at = datetime.utcnow()
            current_status = get_daily_pipeline_status(session, reporting_date, plant_id)
            current_db_run.stage_states_json = json.dumps(current_status.get("stages", {}), default=_json_serial)
            session.commit()
            return current_status

        # -------------------------------------------------------------------------
        # STAGE 8: Investigation Handoff
        # -------------------------------------------------------------------------
        current_db_run.current_stage = "investigation_handoff"
        session.commit()

        record_pipeline_stage_state(
            reporting_date=reporting_date,
            stage_id="investigation_handoff",
            status="IN_PROGRESS",
            summary="Correlating anomaly events with persistent operational findings...",
        )

        try:
            events = anom_details.get("events", [])
            handoff_items = []

            findings_stmt = select(OperationalFinding).filter(
                OperationalFinding.plant_id == plant_id
            ).order_by(OperationalFinding.last_detected_at.desc()).limit(100)
            existing_findings: List[OperationalFinding] = session.execute(findings_stmt).scalars().all()

            findings_map = {}
            for f in existing_findings:
                key = f"{f.anomaly_type}_{f.meter_id or ''}_{f.line_id or ''}"
                findings_map[key] = f

            for ev in events:
                ev_type = str(ev.get("type") or "").upper()
                ev_meter = ev.get("meter_id")
                ev_line = ev.get("line_id")
                match_key = f"{ev_type}_{ev_meter or ''}_{ev_line or ''}"
                matched_finding = findings_map.get(match_key)

                sev = str(ev.get("severity", "MEDIUM")).upper()
                if ev_type in ("LOW_POWER_FACTOR", "POWER_FACTOR_DEFICIT"):
                    suggested_priority = "HIGH" if sev in ("CRITICAL", "HIGH") else "MEDIUM"
                    priority_reason = "Power factor reading below monitored engineering threshold; requires electrical system review."
                elif ev_type in ("ZERO_PRODUCTION_STANDBY_ENERGY", "STANDBY_POWER", "ZERO_PRODUCTION_STANDBY"):
                    suggested_priority = "MEDIUM"
                    priority_reason = "Process energy observed during zero-output production interval; investigate operating conditions and restart requirements."
                elif "BASELOAD" in ev_type:
                    suggested_priority = "HIGH" if sev in ("CRITICAL", "HIGH") else "MEDIUM"
                    priority_reason = "Persistent multi-interval shift in demonstrated low-load baseload; requires Facilities inspection."
                elif "COMPARABLE" in ev_type:
                    suggested_priority = "MEDIUM"
                    priority_reason = "Persistent multi-interval change in comparable-period electricity use; investigate operating schedule and equipment idle draw."
                elif "STOPPAGE" in ev_type or "RESTART" in ev_type:
                    suggested_priority = "HIGH" if sev in ("CRITICAL", "HIGH") else "MEDIUM"
                    priority_reason = "Unusually long stoppage or abnormal restart behavior; requires Production and Facilities review."
                elif "SPIKE" in ev_type:
                    suggested_priority = sev
                    priority_reason = f"Statistical consumption deviation ({sev}) above historical baseline mean."
                elif "DROP" in ev_type:
                    suggested_priority = sev
                    priority_reason = f"Statistical consumption drop ({sev}) below historical baseline mean."
                else:
                    suggested_priority = sev
                    priority_reason = f"Telemetry observation evaluated by {ev.get('detector') or 'detector'}."

                handoff_items.append({
                    "anomaly_type": ev_type,
                    "detector": ev.get("detector"),
                    "timestamp": ev.get("timestamp"),
                    "meter_id": ev_meter,
                    "line_id": ev_line,
                    "severity": sev,
                    "evidence_classification": ev.get("evidence_classification") or ev.get("trust_level"),
                    "actual_value": ev.get("actual_kwh") or ev.get("actual_value") or ev.get("power_factor"),
                    "baseline_value": ev.get("baseline_kwh") or ev.get("baseline_value"),
                    "suggested_priority": suggested_priority,
                    "priority_reason": priority_reason,
                    "finding_id": matched_finding.finding_id if matched_finding else None,
                    "finding_status": matched_finding.status if matched_finding else None,
                })

            day_start = datetime.combine(reporting_date, datetime.min.time())
            day_end = datetime.combine(reporting_date, datetime.max.time())
            sync_result = sync_findings_from_anomalies(
                session=session,
                plant_id=plant_id,
                start_time=day_start,
                end_time=day_end,
                caller_attribution="DOWNSTREAM_PIPELINE",
            )
            # Correlate handoff items with downstream recommendations, actions, and assessments
            finding_ids = [h["finding_id"] for h in handoff_items if h.get("finding_id")]
            rec_by_fid: Dict[str, Any] = {}
            act_by_recid: Dict[str, Any] = {}
            asm_by_actid: Dict[str, Any] = {}
            if finding_ids:
                recs = session.execute(
                    select(OperationalRecommendation).where(OperationalRecommendation.finding_id.in_(finding_ids))
                ).scalars().all()
                for r in recs:
                    rec_by_fid[r.finding_id] = r
                rec_ids = [r.recommendation_id for r in recs]
                if rec_ids:
                    acts = session.execute(
                        select(CorrectiveAction).where(CorrectiveAction.recommendation_id.in_(rec_ids))
                    ).scalars().all()
                    for a in acts:
                        act_by_recid[a.recommendation_id] = a
                    act_ids = [a.action_id for a in acts]
                    if act_ids:
                        asms = session.execute(
                            select(InterventionAssessment).where(
                                InterventionAssessment.action_id.in_(act_ids),
                                InterventionAssessment.is_stale_flag == False,
                            ).order_by(desc(InterventionAssessment.assessment_revision))
                        ).scalars().all()
                        for asm in asms:
                            if asm.action_id not in asm_by_actid:
                                asm_by_actid[asm.action_id] = asm

            for h in handoff_items:
                fid = h.get("finding_id")
                rec = rec_by_fid.get(fid)
                act = act_by_recid.get(rec.recommendation_id) if rec else None
                asm = asm_by_actid.get(act.action_id) if act else None

                h["recommendation_id"] = rec.recommendation_id if rec else None
                h["action_id"] = act.action_id if act else None
                h["action_title"] = act.title if act else None
                h["action_status"] = act.status if act else None
                h["action_review_status"] = act.review_status if act else None
                h["assessment_status"] = act.assessment_status if act else None
                h["assessment_id"] = asm.assessment_id if asm else None
                h["savings_claim_status"] = asm.savings_claim_status if asm else None
                h["verified_savings_kwh"] = (asm.electricity_savings_kwh or 0.0) if (asm and is_claim_eligible_for_verified_savings(asm)[0]) else None
                h["verified_avoided_cost_inr"] = (asm.verified_monetary_savings_inr or 0.0) if (asm and is_claim_eligible_for_verified_monetary(asm)[0]) else None
                h["estimated_avoided_cost_inr"] = (asm.avoided_cost_inr or 0.0) if (asm and is_claim_eligible_for_verified_savings(asm)[0]) else None

            human_action_summary = get_human_action_summary_for_date(session, reporting_date, plant_id)
            items_prep = len(handoff_items)
            findings_sync = sync_result.get("occurrences_recorded", 0) + sync_result.get("duplicates_ignored", 0)
            new_findings = sync_result.get("new_findings_created", 0)
            reused_findings = sync_result.get("existing_findings_updated", 0) + sync_result.get("duplicates_ignored", 0)

            handoff_status = "COMPLETED"
            linked_count = sum(1 for h in handoff_items if h["finding_id"])
            handoff_summary = (
                f"Prepared {items_prep} anomaly investigation items ({new_findings} newly created findings, "
                f"{reused_findings} existing/reused findings synchronized in database)."
                if items_prep > 0
                else "Zero anomalies detected; no investigation handoff needed."
            )

            handoff_details = {
                "total_items": items_prep,
                "items_prepared_count": items_prep,
                "findings_synchronized_count": findings_sync,
                "new_findings_count": new_findings,
                "reused_findings_count": reused_findings,
                "linked_findings_count": linked_count,
                "items": handoff_items,
                "human_action_summary": human_action_summary,
            }
        except Exception as e:
            logger.exception("Investigation handoff stage failed: %s", str(e))
            session.rollback()
            raw_err = str(e).split("\n")[0].strip()
            concise_err = raw_err.split("] ")[-1] if "] " in raw_err else raw_err
            if len(concise_err) > 160:
                concise_err = concise_err[:157] + "..."

            handoff_status = "FAILED"
            handoff_summary = f"Investigation handoff preparation failed: {concise_err}"
            handoff_details = {"error": concise_err, "items": []}
            items_prep = 0
            findings_sync = 0
            new_findings = 0
            reused_findings = 0

        record_pipeline_stage_state(
            reporting_date=reporting_date,
            stage_id="investigation_handoff",
            status=handoff_status,
            summary=handoff_summary,
            details=handoff_details,
        )

        current_status = get_daily_pipeline_status(session, reporting_date, plant_id)
        current_db_run.status = "COMPLETED" if handoff_status != "FAILED" else "FAILED"
        current_db_run.current_stage = "investigation_handoff"
        current_db_run.items_prepared_count = items_prep
        current_db_run.findings_synchronized_count = findings_sync
        current_db_run.new_findings_count = new_findings
        current_db_run.reused_findings_count = reused_findings
        current_db_run.completed_at = datetime.utcnow()
        current_db_run.stage_states_json = json.dumps(current_status.get("stages", {}), default=_json_serial)
        session.commit()

        return current_status
    finally:
        date_lock.release()
