"""API endpoints for daily report upload, validation, database ingestion, and audit history."""

import os
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
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
)
from app.services.daily_report_service import (
    generate_template_csv,
    get_daily_report_coverage,
    ingest_validated_report,
    inspect_file,
    validate_report_file,
)

router = APIRouter()

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
    file: UploadFile = File(..., description="Validated report file to ingest"),
    report_type: str = Form(..., description="'ENERGY' or 'PRODUCTION'"),
    reporting_date: date = Form(..., description="Confirmed reporting date (YYYY-MM-DD)"),
    mode: str = Form("INCREMENTAL", description="'INCREMENTAL' or 'OVERWRITE_CORRECTION'"),
    sheet_name: Optional[str] = Form(None, description="Worksheet name if multi-sheet Excel"),
    db: Session = Depends(get_db_session),
) -> IngestReportResponse:
    try:
        content = await read_uploaded_file_safely(file)
        safe_filename = os.path.basename(file.filename or "upload")
        result = ingest_validated_report(
            session=db,
            filename=safe_filename,
            file_bytes=content,
            report_type=report_type.upper(),
            reporting_date=reporting_date,
            mode=mode.upper(),
            sheet_name=sheet_name,
        )
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

    record_pipeline_stage_state(
        reporting_date=reporting_date,
        stage_id=stage_id,
        status=status.upper(),
        summary=summary,
    )
    return get_daily_pipeline_status(session=db, reporting_date=reporting_date)



