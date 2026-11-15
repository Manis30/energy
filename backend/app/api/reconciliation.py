"""API endpoints for Cross-Source Data Reconciliation."""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.common import validate_date_range
from app.schemas.reconciliation import (
    ReconciliationCategory,
    ReconciliationCheckDefinition,
    ReconciliationReportResponse,
    ReconciliationStatus,
    ReconciliationSummaryResponse,
)
from app.services.reconciliation_service import (
    get_reconciliation_summary,
    get_supported_check_definitions,
    run_cross_source_reconciliation,
)

router = APIRouter()

MAX_RECONCILIATION_RANGE_DAYS = 366


@router.get(
    "",
    response_model=ReconciliationReportResponse,
    summary="Run cross-source data reconciliation",
    description=(
        "Executes deterministic cross-source data reconciliation across energy records, "
        "production records, and upload history. Identifies coverage gaps, unaligned timestamps, "
        "duplicate keys, reference integrity defects, and data quality violations."
    ),
)
def get_reconciliation_report(
    start_date: date = Query(..., description="Inclusive start reporting date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Inclusive end reporting date (YYYY-MM-DD)"),
    plant_id: Optional[str] = Query(None, description="Optional plant ID filter, e.g. 'IN-TN-01' or 'IN-KA-01'"),
    category: Optional[ReconciliationCategory] = Query(None, description="Filter by check category"),
    finding_status: Optional[ReconciliationStatus] = Query(None, description="Filter findings by status ('PASS', 'WARNING', 'FAIL', 'UNAVAILABLE')"),
    db: Session = Depends(get_db_session),
) -> ReconciliationReportResponse:
    validate_date_range(start_date, end_date)
    requested_days = (end_date - start_date).days + 1
    if requested_days > MAX_RECONCILIATION_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Date range must not exceed {MAX_RECONCILIATION_RANGE_DAYS} inclusive days.",
        )

    try:
        return run_cross_source_reconciliation(
            session=db,
            start_date=start_date,
            end_date=end_date,
            plant_id=plant_id,
            category_filter=category,
            status_filter=finding_status,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reconciliation engine failed: {str(e)}",
        )


@router.get(
    "/summary",
    response_model=ReconciliationSummaryResponse,
    summary="Get cross-source reconciliation summary counts",
    description="Returns aggregate PASS, WARNING, FAIL, and UNAVAILABLE check counts for the requested date range.",
)
def get_summary(
    start_date: date = Query(..., description="Inclusive start reporting date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Inclusive end reporting date (YYYY-MM-DD)"),
    plant_id: Optional[str] = Query(None, description="Optional plant ID filter"),
    db: Session = Depends(get_db_session),
) -> ReconciliationSummaryResponse:
    validate_date_range(start_date, end_date)
    requested_days = (end_date - start_date).days + 1
    if requested_days > MAX_RECONCILIATION_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Date range must not exceed {MAX_RECONCILIATION_RANGE_DAYS} inclusive days.",
        )

    try:
        return get_reconciliation_summary(
            session=db,
            start_date=start_date,
            end_date=end_date,
            plant_id=plant_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute reconciliation summary: {str(e)}",
        )


@router.get(
    "/checks",
    response_model=List[ReconciliationCheckDefinition],
    summary="List supported reconciliation check definitions",
    description="Returns metadata catalog of all 7 supported cross-source reconciliation checks.",
)
def list_checks() -> List[ReconciliationCheckDefinition]:
    return get_supported_check_definitions()

