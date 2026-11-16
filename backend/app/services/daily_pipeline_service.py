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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.findings import OperationalFinding
from app.models.source_data import FactEnergyMeterHourly, FactHourlyProduction
from app.models.upload_history import UploadHistory
from app.services.anomaly_detection import detect_all_anomalies
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
    all_states = _load_all_pipeline_states()
    saved = all_states.get(date_str, {})

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

    has_uploaded_energy = bool(completed_energy_uploads) and linked_energy_count > 0
    has_uploaded_production = bool(completed_prod_uploads) and linked_production_count > 0
    has_uploaded_both = has_uploaded_energy and has_uploaded_production

    has_energy = energy_rows_count > 0
    has_production = production_rows_count > 0
    has_data = has_energy or has_production
    has_both = has_energy and has_production

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
        stages["data_upload"] = {
            "status": "COMPLETED",
            "timestamp": uploads[0].uploaded_at.isoformat() if uploads[0].uploaded_at else None,
            "summary": f"{len(uploads)} file(s) recorded in upload history ({sum(u.file_size_bytes for u in uploads)} bytes total)",
            "details": {"files": upload_files, "has_linked_uploads": True},
        }
    elif has_data:
        # Historical seeded baseline telemetry without daily report uploads
        stages["data_upload"] = {
            "status": "NOT_STARTED",
            "timestamp": None,
            "summary": "No daily report files uploaded for this date. (Baseline historical telemetry is present in database).",
            "details": {"is_historical_baseline": True, "files": []},
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

    # Stage 2: Validation
    if uploads:
        total_valid = sum(u.valid_rows for u in uploads)
        total_rejected = sum(u.rejected_rows for u in uploads)
        has_warnings = total_rejected > 0 or any(u.status == "PARTIAL" for u in uploads)
        stages["validation"] = {
            "status": "COMPLETED_WITH_WARNINGS" if has_warnings else "COMPLETED",
            "timestamp": uploads[0].uploaded_at.isoformat() if uploads[0].uploaded_at else None,
            "summary": f"{total_valid} valid rows verified ({total_rejected} rejected)",
            "details": {
                "total_valid_rows": total_valid,
                "total_rejected_rows": total_rejected,
                "files_validated": len(uploads),
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
            has_partial_uploads = any(u.status == "PARTIAL" or u.rejected_rows > 0 for u in completed_batches)

            if has_uploaded_both and not has_partial_uploads:
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
            },
        }
    else:
        # Strictly never mark ingestion COMPLETED when zero records exist in PostgreSQL
        stages["database_ingestion"] = {
            "status": "NOT_STARTED" if stages["validation"]["status"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS") else "BLOCKED",
            "timestamp": None,
            "summary": "Requires operator confirmation to ingest validated records into fact tables.",
            "details": None,
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

    return {
        "reporting_date": date_str,
        "plant_id": plant_id,
        "current_stage": STAGE_KEYS[current_stage_idx],
        "current_stage_index": current_stage_idx,
        "stages": stages,
        "database_state": {
            "has_data": has_data,
            "has_energy": has_energy,
            "has_production": has_production,
            "energy_records": energy_rows_count,
            "production_records": production_rows_count,
            "upload_count": len(uploads),
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

        # -------------------------------------------------------------------------
        # STAGE 4: Data Reconciliation
        # -------------------------------------------------------------------------
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
            logger.error("Reconciliation stage failed: %s", str(e))
            recon_status = "FAILED"
            recon_summary = f"Reconciliation execution failed: {str(e)}"
            recon_details = {"error": str(e)}

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
            logger.error("Daily analytics stage failed: %s", str(e))
            analytics_status = "FAILED"
            analytics_summary = f"Analytics calculation failed: {str(e)}"
            analytics_details = {"error": str(e)}

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
        record_pipeline_stage_state(
            reporting_date=reporting_date,
            stage_id="intelligence_report",
            status="IN_PROGRESS",
            summary="Synthesizing daily operations intelligence briefing...",
        )

        try:
            report_sections = []
            if analytics_status == "COMPLETED":
                tot_kwh = analytics_details["energy_summary"].get("total_consumption_kwh")
                tot_inr = analytics_details["energy_summary"].get("total_cost_inr")
                tot_emissions = analytics_details["energy_summary"].get("total_co2e_kg")
                tot_qty = analytics_details["production_summary"].get("actual_qty")
                good_qty = analytics_details["production_summary"].get("good_qty")
                reject_qty = analytics_details["production_summary"].get("reject_qty")

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
                    report_sections.append(
                        f"Output totaled {tot_qty:,} units ({good_qty or 0:,} good, {reject_qty or 0:,} scrap; scrap rate {scrap_rate:.2f}%)."
                    )
                elif tot_qty == 0:
                    report_sections.append(f"Output recorded was 0 units across all production lines for {date_str}.")
                else:
                    report_sections.append(f"Production output records were unavailable for {date_str}.")

                # Specific Energy Consumption (SEC) - verified alignment
                smt_summary = analytics_details["process_sec"].get("smt_summary", {})
                smt_sec = smt_summary.get("overall_process_sec_kwh_per_board")
                if smt_sec is not None:
                    report_sections.append(f"SMT Process SEC: {float(smt_sec):.4f} kWh/board.")
                else:
                    report_sections.append("SMT Process SEC: Unavailable (requires matched SMT meter and board production).")

                fal_summary = analytics_details["process_sec"].get("fal_summary", {})
                fal_sec = fal_summary.get("overall_process_sec_kwh_per_phone")
                if fal_sec is not None:
                    report_sections.append(f"FAL Process SEC: {float(fal_sec):.4f} kWh/phone.")
                else:
                    report_sections.append("FAL Process SEC: Unavailable (requires matched FAL meter and phone production).")

                fac_sec_data = analytics_details["factory_sec"]
                if fac_sec_data.get("factory_sec_data_available"):
                    fac_val = fac_sec_data.get("factory_sec_kwh_per_finished_unit")
                    report_sections.append(f"Factory SEC: {float(fac_val):.4f} kWh/phone (aligned plant-wide energy / finished phones).")
                else:
                    note = fac_sec_data.get("factory_sec_alignment_note", "incomplete timestamp alignment")
                    report_sections.append(f"Factory SEC: Unavailable ({note}).")

            intel_status = "COMPLETED"
            intel_summary = "Daily Intelligence Report successfully compiled."
            intel_details = {
                "title": f"Daily Operations Intelligence Briefing — {date_str}",
                "key_takeaways": report_sections,
                "reconciliation_notes": recon_summary,
                "generated_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error("Intelligence report stage failed: %s", str(e))
            intel_status = "FAILED"
            intel_summary = f"Intelligence report synthesis failed: {str(e)}"
            intel_details = {"error": str(e)}

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

            all_detected_events = []
            for a in stat_list:
                all_detected_events.append({**a, "detector": "Statistical Z-Score", "type": "CONSUMPTION_SPIKE"})
            for a in roll_list:
                all_detected_events.append({**a, "detector": "Rolling Baseline", "type": "BASELINE_DEVIATION"})
            for a in low_pf_list:
                all_detected_events.append({**a, "detector": "Low Power Factor", "type": "POWER_FACTOR_DEFICIT"})
            for a in standby_list:
                all_detected_events.append({**a, "detector": "Zero-Production Standby", "type": "STANDBY_WASTE"})

            anom_status = "COMPLETED_WITH_WARNINGS" if total_anom > 0 else "COMPLETED"
            anom_summary = f"Detected {total_anom} anomalies across 4 mathematical surveillance algorithms."

            anom_details = {
                "total_anomalies": total_anom,
                "counts_by_detector": {
                    "statistical_zscore": len(stat_list),
                    "rolling_baseline": len(roll_list),
                    "low_power_factor": len(low_pf_list),
                    "zero_production_standby": len(standby_list),
                },
                "events": all_detected_events[:50],
            }
        except Exception as e:
            logger.error("Anomaly detection stage failed: %s", str(e))
            anom_status = "FAILED"
            anom_summary = f"Anomaly detection failed: {str(e)}"
            anom_details = {"error": str(e), "events": []}

        record_pipeline_stage_state(
            reporting_date=reporting_date,
            stage_id="anomaly_detection",
            status=anom_status,
            summary=anom_summary,
            details=anom_details,
        )

        # -------------------------------------------------------------------------
        # STAGE 8: Investigation Handoff
        # -------------------------------------------------------------------------
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
                ev_type = ev.get("type")
                ev_meter = ev.get("meter_id")
                ev_line = ev.get("line_id")
                match_key = f"{ev_type}_{ev_meter or ''}_{ev_line or ''}"
                matched_finding = findings_map.get(match_key)

                sev = str(ev.get("severity", "MEDIUM")).upper()
                if ev_type == "STANDBY_WASTE" or sev == "CRITICAL":
                    suggested_priority = "CRITICAL"
                    priority_reason = "Substantial standby power drawing while production line is idle."
                elif ev_type == "POWER_FACTOR_DEFICIT" or sev == "HIGH":
                    suggested_priority = "HIGH"
                    priority_reason = "PF breach below threshold risks active utility charges and penalties."
                else:
                    suggested_priority = "MEDIUM"
                    priority_reason = "Statistical deviation from established baseline."

                handoff_items.append({
                    "anomaly_type": ev_type,
                    "detector": ev.get("detector"),
                    "timestamp": ev.get("timestamp"),
                    "meter_id": ev_meter,
                    "line_id": ev_line,
                    "severity": sev,
                    "actual_value": ev.get("actual_kwh") or ev.get("actual_value") or ev.get("power_factor"),
                    "baseline_value": ev.get("baseline_kwh") or ev.get("baseline_value"),
                    "suggested_priority": suggested_priority,
                    "priority_reason": priority_reason,
                    "finding_id": matched_finding.finding_id if matched_finding else None,
                    "finding_status": matched_finding.status if matched_finding else None,
                })

            handoff_status = "COMPLETED"
            linked_count = sum(1 for h in handoff_items if h["finding_id"])
            handoff_summary = (
                f"Prepared {len(handoff_items)} anomaly investigation items ({linked_count} linked to existing findings)."
                if handoff_items
                else "Zero anomalies detected; no investigation handoff needed."
            )

            handoff_details = {
                "total_items": len(handoff_items),
                "linked_findings_count": linked_count,
                "items": handoff_items,
            }
        except Exception as e:
            logger.error("Investigation handoff stage failed: %s", str(e))
            handoff_status = "FAILED"
            handoff_summary = f"Investigation handoff preparation failed: {str(e)}"
            handoff_details = {"error": str(e), "items": []}

        record_pipeline_stage_state(
            reporting_date=reporting_date,
            stage_id="investigation_handoff",
            status=handoff_status,
            summary=handoff_summary,
            details=handoff_details,
        )

        return get_daily_pipeline_status(session, reporting_date, plant_id)
    finally:
        date_lock.release()
