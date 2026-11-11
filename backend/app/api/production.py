"""Production Analytics API endpoints."""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.common import validate_date_range
from app.schemas.production import (
    DailyProductionItem,
    DowntimeReasonItem,
    ProductionLineItem,
    ProductionProductItem,
    ProductionShiftItem,
    ProductionSummaryResponse,
)
from app.services.production_analytics import (
    get_downtime_by_reason,
    get_production_by_line,
    get_production_by_product,
    get_production_by_shift,
    get_production_daily_trend,
    get_production_summary,
)

router = APIRouter()


@router.get(
    "/summary",
    response_model=ProductionSummaryResponse,
    summary="Get overall production output, scrap rates, and downtime totals",
    description="Calculates deterministic factory output volumes, target achievement, scrap/rework rates, downtime, and OEE evaluation.",
)
def read_production_summary(
    plant_id: Optional[str] = Query(None, description="Plant ID filter, e.g. 'IN-TN-01' or 'IN-KA-01'"),
    line_id: Optional[str] = Query(None, description="Production line ID filter, e.g. 'SMT-L1' or 'FAL-L1'"),
    product_id: Optional[str] = Query(None, description="Product SKU filter, e.g. 'SPH-A15-128'"),
    shift_id: Optional[str] = Query(None, description="Shift ID filter, e.g. 'Shift A'"),
    start_date: Optional[date] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date filter (YYYY-MM-DD)"),
    db: Session = Depends(get_db_session),
) -> ProductionSummaryResponse:
    validate_date_range(start_date, end_date)
    try:
        data = get_production_summary(
            session=db,
            plant_id=plant_id,
            line_id=line_id,
            product_id=product_id,
            shift_id=shift_id,
            start_date=start_date,
            end_date=end_date,
        )
        return ProductionSummaryResponse(**data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate production summary: {str(e)}",
        )


@router.get(
    "/by-line",
    response_model=List[ProductionLineItem],
    summary="Get production breakdown by manufacturing line",
    description="Returns production volumes, target achievement, good/reject rates, and downtime minutes per production line.",
)
def read_production_by_line(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db_session),
) -> List[ProductionLineItem]:
    validate_date_range(start_date, end_date)
    try:
        data = get_production_by_line(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
        )
        return [ProductionLineItem(**item) for item in data]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate production by line: {str(e)}",
        )


@router.get(
    "/by-product",
    response_model=List[ProductionProductItem],
    summary="Get production breakdown by product SKU",
    description="Aggregates target and actual production volumes, scrap, and rework across product models.",
)
def read_production_by_product(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    line_id: Optional[str] = Query(None, description="Line ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db_session),
) -> List[ProductionProductItem]:
    validate_date_range(start_date, end_date)
    try:
        data = get_production_by_product(
            session=db,
            plant_id=plant_id,
            line_id=line_id,
            start_date=start_date,
            end_date=end_date,
        )
        return [ProductionProductItem(**item) for item in data]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate production by product: {str(e)}",
        )


@router.get(
    "/by-shift",
    response_model=List[ProductionShiftItem],
    summary="Get production breakdown by manufacturing shift",
    description="Returns volume, achievement, yield, and scrap performance for Shift A, Shift B, and Shift C.",
)
def read_production_by_shift(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db_session),
) -> List[ProductionShiftItem]:
    validate_date_range(start_date, end_date)
    try:
        data = get_production_by_shift(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
        )
        return [ProductionShiftItem(**item) for item in data]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate production by shift: {str(e)}",
        )


@router.get(
    "/downtime-by-reason",
    response_model=List[DowntimeReasonItem],
    summary="Get downtime minutes and occurrence share by stoppage reason",
    description="Groups factory downtime by reason category with minutes, total events, and zero-output events.",
)
def read_downtime_by_reason(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    line_id: Optional[str] = Query(None, description="Line ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db_session),
) -> List[DowntimeReasonItem]:
    validate_date_range(start_date, end_date)
    try:
        data = get_downtime_by_reason(
            session=db,
            plant_id=plant_id,
            line_id=line_id,
            start_date=start_date,
            end_date=end_date,
        )
        return [DowntimeReasonItem(**item) for item in data]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate downtime by reason: {str(e)}",
        )


@router.get(
    "/daily-trend",
    response_model=List[DailyProductionItem],
    summary="Get daily production trend time-series",
    description="Returns daily aggregates of target, actual, good, reject, rework, and downtime.",
)
def read_production_daily_trend(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db_session),
) -> List[DailyProductionItem]:
    validate_date_range(start_date, end_date)
    try:
        data = get_production_daily_trend(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
        )
        return [DailyProductionItem(**item) for item in data]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate production daily trend: {str(e)}",
        )
