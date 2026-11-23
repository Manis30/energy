"""API endpoints for daily report upload, validation, database ingestion, and audit history."""

import json
import logging
import os
import uuid
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.config import get_settings
from app.models.upload_history import UploadHistory
from app.schemas.common import validate_date_range
from app.schemas.daily_reports import (
    DailyReportCoverageResponse,
    IngestReportResponse,
    InspectResponse,
    UploadHistoryItem,
    ValidateReportResponse,
    VerifyIngestionResponse,
)
from app.services.daily_report_service import (
    clear_staged_report,
    generate_template_csv,
    get_daily_report_coverage,
    get_staged_report,
    ingest_validated_report,
    inspect_file,
    stage_validated_report,
    validate_report_file,
)

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE_MB = get_settings().MAX_UPLOAD_SIZE_MB
MAX_FILE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_COVERAGE_RANGE_DAYS = 366


async def read_uploaded_file_safely(file: UploadFile, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    """Read uploaded file in chunks, enforcing strict size limits to prevent memory exhaustion."""
    chunks = []
    total_size = 0
    chunk_size = 64 * 1024  # 64 KB
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Uploaded file exceeds maximum permitted size of {MAX_UPLOAD_SIZE_MB} MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/inspect",
    response_model=InspectResponse,
    summary="Inspect file metadata and worksheets",
    description="Validates file size, format (.csv, .xlsx, .xls), lists sheets if Excel, and identifies likely report type.",
)
async def inspect_uploaded_file(
    file: UploadFile = File(..., description="Daily report file in CSV, XLSX, or XLS format")
) -> InspectResponse:
    try:
        content = await read_uploaded_file_safely(file)
        safe_filename = os.path.basename(file.filename or "upload")
        return inspect_file(filename=safe_filename, file_bytes=content)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to inspect file due to an unexpected parsing error.",
        )


@router.post(
    "/validate",
    response_model=ValidateReportResponse,
    summary="Validate daily report rows, schema, and reference keys",
    description="Performs pre-ingestion validation: required columns, types, range checks, foreign keys, duplicate detection, and date consistency.",
)
async def validate_report(
    file: UploadFile = File(..., description="Report file to validate"),
    report_type: Optional[str] = Form(None, description="'ENERGY' or 'PRODUCTION' or None for auto-detect"),
    sheet_name: Optional[str] = Form(None, description="Worksheet name if multi-sheet Excel"),
    confirmed_date: Optional[date] = Form(None, description="Confirmed reporting date filter (YYYY-MM-DD)"),
    mode: Optional[str] = Form("INCREMENTAL", description="'INCREMENTAL' or 'OVERWRITE_CORRECTION'"),
    db: Session = Depends(get_db_session),
) -> ValidateReportResponse:
    try:
        content = await read_uploaded_file_safely(file)
        safe_filename = os.path.basename(file.filename or "upload")
        norm_mode = mode.upper() if mode else "INCREMENTAL"
        result = validate_report_file(
            session=db,
            filename=safe_filename,
            file_bytes=content,
            report_type=report_type,
            sheet_name=sheet_name,
            confirmed_date=confirmed_date,
            mode=norm_mode,
        )
        target_date = confirmed_date or (result["summary"].confirmed_date or result["summary"].detected_date)
        resolved_type = result["summary"].report_type
        if target_date and resolved_type:
            gen_upload_id = f"UPL-{target_date.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
            stage_validated_report(
                reporting_date=target_date,
                report_type=resolved_type,
                filename=safe_filename,
                file_bytes=content,
                upload_id=gen_upload_id,
                summary=result["summary"],
            )
            result["upload_id"] = gen_upload_id

        return ValidateReportResponse(**result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report validation failed: {str(e)}",
        )


@router.post(
    "/ingest",
    response_model=IngestReportResponse,
    summary="Confirm and ingest valid records into Neon PostgreSQL",
    description="Transactionally ingests validated records into fact tables. Supports INCREMENTAL (skip duplicates) and OVERWRITE_CORRECTION (replace existing date records).",
)
async def ingest_report(
    file: Optional[UploadFile] = File(None, description="Validated report file to ingest"),
    report_type: str = Form(..., description="'ENERGY' or 'PRODUCTION'"),
    reporting_date: date = Form(..., description="Confirmed reporting date (YYYY-MM-DD)"),
    plant_id: Optional[str] = Form(None, description="Plant identifier"),
    upload_id: Optional[str] = Form(None, description="Staged or client upload ID"),
    mode: str = Form("INCREMENTAL", description="'INCREMENTAL' or 'OVERWRITE_CORRECTION'"),
    sheet_name: Optional[str] = Form(None, description="Worksheet name if multi-sheet Excel"),
    db: Session = Depends(get_db_session),
) -> IngestReportResponse:
    try:
        content = None
        safe_filename = None
        if file and file.filename:
            content = await read_uploaded_file_safely(file)
            safe_filename = os.path.basename(file.filename)

        if not content:
            staged = get_staged_report(reporting_date, report_type.upper(), upload_id=upload_id)
            if staged:
                content, staged_meta = staged
                safe_filename = staged_meta.get("filename", f"{report_type.lower()}_{reporting_date.isoformat()}.csv")
                if not upload_id:
                    upload_id = staged_meta.get("upload_id")
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No upload file provided and no staged file found for {reporting_date} ({report_type}). Please validate the report file first.",
                )

        result = ingest_validated_report(
            session=db,
            filename=safe_filename,
            file_bytes=content,
            report_type=report_type.upper(),
            reporting_date=reporting_date,
            mode=mode.upper(),
            sheet_name=sheet_name,
            upload_id=upload_id,
            plant_id=plant_id,
        )
        clear_staged_report(reporting_date, report_type.upper(), upload_id=upload_id)
        return IngestReportResponse(**result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database ingestion failed: {str(e)}",
        )


@router.post(
    "/upload",
    summary="Direct upload endpoint for telemetry files (including utility CSV)",
    description="Ingests daily telemetry files directly into fact tables, creating upload audit history and source revisions.",
)
async def upload_telemetry_file(
    file: UploadFile = File(..., description="Telemetry file to upload (Utility CSV, Energy CSV/XLSX, or Production CSV/XLSX)"),
    report_type: Optional[str] = Form(None, description="'UTILITY', 'ENERGY', or 'PRODUCTION' (auto-detected if omitted)"),
    plant_id: Optional[str] = Form("IN-TN-01", description="Plant identifier"),
    mode: str = Form("INCREMENTAL", description="'INCREMENTAL' or 'OVERWRITE_CORRECTION'"),
    db: Session = Depends(get_db_session),
):
    try:
        content = await read_uploaded_file_safely(file)
        safe_filename = os.path.basename(file.filename or "upload.csv")

        # Detect if utility CSV
        is_utility = False
        if report_type and report_type.upper() == "UTILITY":
            is_utility = True
        else:
            first_line = content[:1024].decode("utf-8-sig", errors="replace").lower()
            if "utility_reading_id" in first_line or "flow_rate" in first_line or "pressure_bar" in first_line:
                is_utility = True

        if is_utility:
            from app.services.upload_service import ingest_utility_telemetry_file
            result = ingest_utility_telemetry_file(
                session=db,
                filename=safe_filename,
                file_bytes=content,
                plant_id=plant_id,
                mode=mode,
            )
            return result

        # Fallback to standard validation & ingestion for ENERGY or PRODUCTION
        norm_type = report_type.upper() if report_type else None
        v_res = validate_report_file(
            session=db,
            filename=safe_filename,
            file_bytes=content,
            report_type=norm_type,
            mode=mode.upper(),
        )
        resolved_type = v_res["summary"].report_type
        target_date = v_res["summary"].confirmed_date or v_res["summary"].detected_date or date.today()
        gen_upload_id = f"UPL-{target_date.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        ingest_res = ingest_validated_report(
            session=db,
            filename=safe_filename,
            file_bytes=content,
            report_type=resolved_type,
            reporting_date=target_date,
            mode=mode.upper(),
            upload_id=gen_upload_id,
            plant_id=plant_id,
        )
        return ingest_res
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Telemetry upload failed: {str(e)}",
        )


@router.get(
    "/history",
    response_model=List[UploadHistoryItem],
    summary="List past daily report uploads and audit history",
    description="Returns chronological upload audit log with row metrics, ingestion mode, and status.",
)
def get_upload_history(
    limit: int = Query(50, ge=1, le=200, description="Max history records to return"),
    report_type: Optional[str] = Query(None, description="Filter by 'ENERGY' or 'PRODUCTION'"),
    reporting_date: Optional[date] = Query(None, description="Filter by reporting date"),
    db: Session = Depends(get_db_session),
) -> List[UploadHistoryItem]:
    stmt = select(UploadHistory)
    if report_type:
        stmt = stmt.where(UploadHistory.report_type == report_type.upper())
    if reporting_date:
        stmt = stmt.where(UploadHistory.reporting_date == reporting_date)

    stmt = stmt.order_by(UploadHistory.uploaded_at.desc()).limit(limit)
    records = db.execute(stmt).scalars().all()
    return [UploadHistoryItem.model_validate(r) for r in records]


@router.get(
    "/coverage",
    response_model=DailyReportCoverageResponse,
    summary="Report persisted daily energy and production coverage",
    description=(
        "Groups observed energy and production records by plant and reporting date. "
        "Does not assume a 24-hour schedule or per-hour entity expectations."
    ),
)
def get_report_coverage(
    start_date: date = Query(..., description="Inclusive start reporting date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Inclusive end reporting date (YYYY-MM-DD)"),
    db: Session = Depends(get_db_session),
) -> DailyReportCoverageResponse:
    validate_date_range(start_date, end_date)
    requested_days = (end_date - start_date).days + 1
    if requested_days > MAX_COVERAGE_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Date range must not exceed {MAX_COVERAGE_RANGE_DAYS} inclusive days.",
        )

    data = get_daily_report_coverage(
        session=db,
        start_date=start_date,
        end_date=end_date,
    )
    return DailyReportCoverageResponse(**data)


@router.get(
    "/template/{report_type}",
    summary="Download sample CSV template for daily report",
    description="Provides an approved CSV template for operators to fill out daily energy or production records.",
)
def download_template(
    report_type: str,
) -> Response:
    norm_type = report_type.upper()
    if norm_type not in {"ENERGY", "PRODUCTION"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template report_type must be 'energy' or 'production'.",
        )

    csv_data = generate_template_csv(norm_type)
    filename = f"{norm_type.lower()}_daily_report_template.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


# ---------------------------------------------------------------------------
# Daily Operations End-to-End Intelligence Pipeline Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/pipeline-status",
    summary="Get authoritative Daily Operations pipeline status",
    description="Returns current execution state, status, timestamps, and summaries across all 8 pipeline stages for a reporting date.",
)
def get_pipeline_status_endpoint(
    reporting_date: date = Query(..., description="Confirmed reporting date (YYYY-MM-DD)"),
    plant_id: str = Query("IN-TN-01", description="Plant identifier"),
    db: Session = Depends(get_db_session),
):
    from app.services.daily_pipeline_service import get_daily_pipeline_status
    return get_daily_pipeline_status(session=db, reporting_date=reporting_date, plant_id=plant_id)


@router.post(
    "/pipeline/run-downstream",
    summary="Execute downstream stages of Daily Operations pipeline",
    description="Sequentially executes Reconciliation, Analytics, Intelligence Report, Anomaly Detection, and Investigation Handoff, persisting results.",
)
def run_downstream_pipeline_endpoint(
    reporting_date: date = Query(..., description="Confirmed reporting date (YYYY-MM-DD)"),
    plant_id: str = Query("IN-TN-01", description="Plant identifier"),
    db: Session = Depends(get_db_session),
):
    from app.services.daily_pipeline_service import run_downstream_pipeline
    return run_downstream_pipeline(session=db, reporting_date=reporting_date, plant_id=plant_id)


@router.post(
    "/pipeline-status",
    summary="Persist or update Daily Operations pipeline stage status",
    description="Records stage transition, status, and summary in persistent pipeline state with validation integrity checks.",
)
def update_pipeline_status_endpoint(
    reporting_date: date = Form(..., description="Confirmed reporting date (YYYY-MM-DD)"),
    stage_id: str = Form(..., description="Pipeline stage identifier"),
    status: str = Form(..., description="'NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED', 'BLOCKED'"),
    summary: str = Form(..., description="Human-readable stage execution summary"),
    details: Optional[str] = Form(None, description="Optional JSON serialized stage details"),
    db: Session = Depends(get_db_session),
):
    from app.services.daily_pipeline_service import record_pipeline_stage_state, get_daily_pipeline_status, STAGE_KEYS

    if stage_id not in STAGE_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage_id '{stage_id}'. Supported stages: {STAGE_KEYS}",
        )

    valid_statuses = {"NOT_STARTED", "IN_PROGRESS", "COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "BLOCKED"}
    if status.upper() not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. Must be one of {valid_statuses}",
        )

    # Ingestion stage status must strictly reflect actual database records, not arbitrary client claims
    if stage_id == "database_ingestion" and status.upper() in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
        from app.models.source_data import FactEnergyMeterHourly, FactHourlyProduction
        from sqlalchemy import func
        energy_count = db.query(func.count(FactEnergyMeterHourly.meter_reading_id)).filter(
            FactEnergyMeterHourly.date == reporting_date
        ).scalar() or 0
        prod_count = db.query(func.count(FactHourlyProduction.event_id)).filter(
            FactHourlyProduction.event_date == reporting_date
        ).scalar() or 0
        if energy_count == 0 and prod_count == 0:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot mark database_ingestion as COMPLETED: zero records exist in PostgreSQL for {reporting_date}.",
            )

    parsed_details = None
    if details:
        try:
            parsed_details = json.loads(details)
        except Exception:
            parsed_details = {"raw": details}

    record_pipeline_stage_state(
        reporting_date=reporting_date,
        stage_id=stage_id,
        status=status.upper(),
        summary=summary,
        details=parsed_details,
    )
    return get_daily_pipeline_status(session=db, reporting_date=reporting_date)


@router.get(
    "/verify-ingestion",
    response_model=VerifyIngestionResponse,
    summary="Verify fact table records and upload ID linkage in PostgreSQL",
    description="Confirms that fact records exist for the date and are linked to upload history batches.",
)
def verify_ingested_records(
    reporting_date: date = Query(..., description="Confirmed reporting date (YYYY-MM-DD)"),
    plant_id: Optional[str] = Query(None, description="Optional plant filter"),
    upload_id: Optional[str] = Query(None, description="Specific upload ID to verify"),
    db: Session = Depends(get_db_session),
) -> VerifyIngestionResponse:
    from app.models.source_data import FactEnergyMeterHourly, FactHourlyProduction
    from app.models.upload_history import UploadHistory

    energy_filters = [FactEnergyMeterHourly.date == reporting_date]
    prod_filters = [FactHourlyProduction.event_date == reporting_date]
    if plant_id:
        energy_filters.append(FactEnergyMeterHourly.plant_id == plant_id)
        prod_filters.append(FactHourlyProduction.plant_id == plant_id)

    energy_count = db.query(func.count(FactEnergyMeterHourly.meter_reading_id)).filter(*energy_filters).scalar() or 0
    prod_count = db.query(func.count(FactHourlyProduction.event_id)).filter(*prod_filters).scalar() or 0

    uploads_stmt = select(UploadHistory).filter(UploadHistory.reporting_date == reporting_date)
    if upload_id:
        uploads_stmt = uploads_stmt.filter(UploadHistory.upload_id == upload_id)
    uploads = db.execute(uploads_stmt).scalars().all()
    upload_ids = [u.upload_id for u in uploads]

    if upload_ids:
        linked_energy = db.query(func.count(FactEnergyMeterHourly.meter_reading_id)).filter(
            *energy_filters, FactEnergyMeterHourly.upload_id.in_(upload_ids)
        ).scalar() or 0
        linked_prod = db.query(func.count(FactHourlyProduction.event_id)).filter(
            *prod_filters, FactHourlyProduction.upload_id.in_(upload_ids)
        ).scalar() or 0
    else:
        linked_energy = 0
        linked_prod = 0

    verified = (energy_count > 0 or prod_count > 0)
    if upload_id:
        verified = (linked_energy > 0 or linked_prod > 0)

    msg = f"PostgreSQL verification: {energy_count} energy rows ({linked_energy} linked), {prod_count} production rows ({linked_prod} linked) for {reporting_date}."
    return VerifyIngestionResponse(
        reporting_date=reporting_date,
        plant_id=plant_id,
        upload_id=upload_id,
        verified=verified,
        energy_records=energy_count,
        production_records=prod_count,
        linked_energy_records=linked_energy,
        linked_production_records=linked_prod,
        upload_ids=upload_ids,
        message=msg,
    )


@router.get(
    "/opportunities",
    summary="List prioritized energy-saving opportunities for reporting date",
    description="Surfaces and ranks energy-saving trial candidates and evidence-gathering opportunities following daily operations pipeline execution.",
)
def get_daily_opportunities_endpoint(
    reporting_date: date = Query(..., description="Reporting date (YYYY-MM-DD)"),
    plant_id: str = Query("IN-TN-01", description="Plant identifier"),
    db: Session = Depends(get_db_session),
):
    from app.services.opportunity_service import get_energy_saving_opportunities
    try:
        return get_energy_saving_opportunities(session=db, reporting_date=reporting_date, plant_id=plant_id)
    except Exception as e:
        logger.exception("Failed to retrieve opportunities: %s", str(e))
        return []




