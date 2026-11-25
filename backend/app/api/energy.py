"""Energy Analytics API endpoints."""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.config import DEFAULT_POWER_FACTOR_THRESHOLD
from app.schemas.common import validate_date_range
from app.schemas.energy import (
    AreaEnergyItem,
    DailyEnergyItem,
    EnergySummaryResponse,
    MeterEnergyItem,
    PowerFactorSummaryResponse,
)
from app.services.energy_analytics import (
    get_energy_by_area,
    get_energy_by_meter,
    get_energy_daily_trend,
    get_energy_summary,
    get_power_factor_summary,
)

router = APIRouter()


@router.get(
    "/summary",
    response_model=EnergySummaryResponse,
    summary="Get overall energy consumption, cost, and emission totals",
    description="Calculates deterministic factory energy consumption (kWh), spend (INR), CO2e emissions (kg), average/peak load, and power factor.",
)
def read_energy_summary(
    plant_id: Optional[str] = Query(None, description="Plant ID filter, e.g. 'IN-TN-01' or 'IN-KA-01'"),
    start_date: Optional[date] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date filter (YYYY-MM-DD)"),
    shift_id: Optional[str] = Query(None, description="Shift ID filter, e.g. 'A', 'B', or 'C'"),
    db: Session = Depends(get_db_session),
) -> EnergySummaryResponse:
    validate_date_range(start_date, end_date)
    try:
        data = get_energy_summary(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
            shift_id=shift_id,
        )
        return EnergySummaryResponse(**data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate energy summary: {str(e)}",
        )


@router.get(
    "/by-meter",
    response_model=List[MeterEnergyItem],
    summary="Get energy breakdown by individual meter",
    description="Returns energy consumption, cost, emissions, and percentage share for each individual meter.",
)
def read_energy_by_meter(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    shift_id: Optional[str] = Query(None, description="Shift ID filter, e.g. 'A', 'B', or 'C'"),
    db: Session = Depends(get_db_session),
) -> List[MeterEnergyItem]:
    validate_date_range(start_date, end_date)
    try:
        data = get_energy_by_meter(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
            shift_id=shift_id,
        )
        return [MeterEnergyItem(**item) for item in data]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate energy by meter: {str(e)}",
        )


@router.get(
    "/by-area",
    response_model=List[AreaEnergyItem],
    summary="Get energy breakdown by factory area",
    description="Aggregates energy consumption and cost by physical manufacturing areas (SMT, Final Assembly, Utilities).",
)
def read_energy_by_area(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    shift_id: Optional[str] = Query(None, description="Shift ID filter, e.g. 'A', 'B', or 'C'"),
    db: Session = Depends(get_db_session),
) -> List[AreaEnergyItem]:
    validate_date_range(start_date, end_date)
    try:
        data = get_energy_by_area(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
            shift_id=shift_id,
        )
        return [AreaEnergyItem(**item) for item in data]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate energy by area: {str(e)}",
        )


@router.get(
    "/daily-trend",
    response_model=List[DailyEnergyItem],
    summary="Get daily energy consumption trend time-series",
    description="Returns daily aggregates of kWh, cost, emissions, and peak hourly loads.",
)
def read_energy_daily_trend(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date filter (YYYY-MM-DD)"),
    shift_id: Optional[str] = Query(None, description="Shift ID filter, e.g. 'A', 'B', or 'C'"),
    db: Session = Depends(get_db_session),
) -> List[DailyEnergyItem]:
    validate_date_range(start_date, end_date)
    try:
        data = get_energy_daily_trend(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
            shift_id=shift_id,
        )
        return [DailyEnergyItem(**item) for item in data]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate energy daily trend: {str(e)}",
        )


@router.get(
    "/power-factor",
    response_model=PowerFactorSummaryResponse,
    summary="Get power factor summary and application monitoring",
    description="Evaluates power factor distribution, energy-weighted mean, min, max, and occurrences below monitoring threshold.",
)
def read_power_factor_summary(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    threshold: Decimal = Query(DEFAULT_POWER_FACTOR_THRESHOLD, ge=Decimal("0.1"), le=Decimal("1.0"), description="Application power factor monitoring threshold (default 0.90)"),
    shift_id: Optional[str] = Query(None, description="Shift ID filter, e.g. 'A', 'B', or 'C'"),
    db: Session = Depends(get_db_session),
) -> PowerFactorSummaryResponse:
    validate_date_range(start_date, end_date)
    try:
        data = get_power_factor_summary(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
            low_pf_threshold=threshold,
            shift_id=shift_id,
        )
        return PowerFactorSummaryResponse(**data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate power factor summary: {str(e)}",
        )
