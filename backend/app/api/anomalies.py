"""Deterministic Anomaly Detection API endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.config import DEFAULT_POWER_FACTOR_THRESHOLD
from app.schemas.anomalies import (
    LowPowerFactorResponse,
    RollingAnomaliesResponse,
    StatisticalAnomaliesResponse,
    UnifiedAnomaliesResponse,
    ZeroProductionStandbyResponse,
)
from app.schemas.common import validate_time_range
from app.services.anomaly_detection import (
    detect_all_anomalies,
    detect_energy_statistical_anomalies,
    detect_low_power_factor_anomalies,
    detect_rolling_baseline_anomalies,
    detect_zero_production_standby_anomalies,
)

router = APIRouter()


@router.get(
    "/statistical",
    response_model=StatisticalAnomaliesResponse,
    summary="Detect energy statistical anomalies via Z-score",
    description=(
        "Identifies extreme hourly energy consumption readings using sample Z-score per (plant_id, meter_id). "
        "Safely handles zero variance and small samples."
    ),
)
def read_statistical_anomalies(
    plant_id: Optional[str] = Query(None, description="Plant ID filter, e.g. 'IN-TN-01' or 'IN-KA-01'"),
    meter_id: Optional[str] = Query(None, description="Meter ID filter, e.g. 'MTR-SMT'"),
    start_time: Optional[datetime] = Query(None, description="Start timestamp filter (ISO 8601)"),
    end_time: Optional[datetime] = Query(None, description="End timestamp filter (ISO 8601)"),
    threshold_z: float = Query(3.0, ge=0.1, le=15.0, description="Absolute Z-score threshold for anomaly flag (default 3.0, range 0.1-15.0)"),
    min_observations: int = Query(10, ge=2, le=50000, description="Minimum observations required before computing Z-score (min 2)"),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Optional maximum number of anomaly records to return"),
    db: Session = Depends(get_db_session),
) -> StatisticalAnomaliesResponse:
    validate_time_range(start_time, end_time)
    try:
        data = detect_energy_statistical_anomalies(
            session=db,
            plant_id=plant_id,
            meter_id=meter_id,
            start_time=start_time,
            end_time=end_time,
            threshold_z=threshold_z,
            min_observations=min_observations,
            limit=limit,
        )
        return StatisticalAnomaliesResponse(**data)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect statistical anomalies: {str(e)}",
        )


@router.get(
    "/rolling",
    response_model=RollingAnomaliesResponse,
    summary="Detect energy deviations against historical rolling baseline",
    description=(
        "Computes a rolling baseline from observations in the preceding timestamp duration. "
        "The current observation is excluded; intervals with too few available observations are not evaluated."
    ),
)
def read_rolling_anomalies(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    meter_id: Optional[str] = Query(None, description="Meter ID filter"),
    start_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    end_time: Optional[datetime] = Query(None, description="End timestamp filter"),
    window_size: int = Query(24, ge=2, le=720, description="Rolling window size in hours (default 24, range 2-720)"),
    min_observations: int = Query(12, ge=2, le=720, description="Minimum historical observations in window (default 12, range 2-720)"),
    threshold_z: float = Query(3.0, ge=0.1, le=15.0, description="Z-score threshold for rolling deviation (default 3.0, range 0.1-15.0)"),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Optional maximum number of anomaly records to return"),
    db: Session = Depends(get_db_session),
) -> RollingAnomaliesResponse:
    validate_time_range(start_time, end_time)
    if min_observations > window_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"min_observations ({min_observations}) cannot exceed window_size ({window_size}).",
        )
    try:
        data = detect_rolling_baseline_anomalies(
            session=db,
            plant_id=plant_id,
            meter_id=meter_id,
            start_time=start_time,
            end_time=end_time,
            window_size=window_size,
            min_observations=min_observations,
            threshold_z=threshold_z,
            limit=limit,
        )
        return RollingAnomaliesResponse(**data)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect rolling baseline anomalies: {str(e)}",
        )


@router.get(
    "/low-power-factor",
    response_model=LowPowerFactorResponse,
    summary="Detect power factor readings below application monitoring threshold",
    description=(
        "Identifies meter readings falling below the application monitoring threshold (default 0.90). "
        "Does not claim penalty savings without verified utility rate structures."
    ),
)
def read_low_power_factor_anomalies(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    meter_id: Optional[str] = Query(None, description="Meter ID filter"),
    start_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    end_time: Optional[datetime] = Query(None, description="End timestamp filter"),
    threshold: Decimal = Query(DEFAULT_POWER_FACTOR_THRESHOLD, ge=Decimal("0.1"), le=Decimal("1.0"), description="Power factor application monitoring threshold (default 0.90, range 0.1-1.0)"),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Optional maximum number of anomaly records to return"),
    db: Session = Depends(get_db_session),
) -> LowPowerFactorResponse:
    validate_time_range(start_time, end_time)
    try:
        data = detect_low_power_factor_anomalies(
            session=db,
            plant_id=plant_id,
            meter_id=meter_id,
            start_time=start_time,
            end_time=end_time,
            threshold=threshold,
            limit=limit,
        )
        return LowPowerFactorResponse(**data)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect low power factor anomalies: {str(e)}",
        )


@router.get(
    "/zero-production",
    response_model=ZeroProductionStandbyResponse,
    summary="Detect process energy during zero-output line intervals",
    description=(
        "Reports positive energy measurements from dedicated process meters during zero-output intervals (actual_qty = 0). "
        "Keeps SMT, FAL, and facility utilities segregated. Avoids false waste assumptions."
    ),
)
def read_zero_production_standby_anomalies(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    line_id: Optional[str] = Query(None, description="Line ID filter"),
    start_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    end_time: Optional[datetime] = Query(None, description="End timestamp filter"),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Optional maximum number of anomaly records to return"),
    db: Session = Depends(get_db_session),
) -> ZeroProductionStandbyResponse:
    validate_time_range(start_time, end_time)
    try:
        data = detect_zero_production_standby_anomalies(
            session=db,
            plant_id=plant_id,
            line_id=line_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        return ZeroProductionStandbyResponse(**data)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect zero-production standby anomalies: {str(e)}",
        )


@router.get(
    "/all",
    response_model=UnifiedAnomaliesResponse,
    summary="Get unified anomaly results across all detection capabilities",
    description="Runs statistical Z-score, rolling baseline, low power factor, and zero-production standby detectors in a single unified payload.",
)
def read_all_anomalies(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_time: Optional[datetime] = Query(None, description="Start timestamp filter"),
    end_time: Optional[datetime] = Query(None, description="End timestamp filter"),
    z_threshold: float = Query(3.0, ge=0.1, le=15.0, description="Z-score threshold for statistical anomalies (range 0.1-15.0)"),
    rolling_window_hours: int = Query(24, ge=2, le=720, description="Window size in hours for rolling baseline (range 2-720)"),
    pf_threshold: Decimal = Query(DEFAULT_POWER_FACTOR_THRESHOLD, ge=Decimal("0.1"), le=Decimal("1.0"), description="Application threshold for low power factor detection (range 0.1-1.0)"),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Optional maximum number of anomaly records to return per detector"),
    db: Session = Depends(get_db_session),
) -> UnifiedAnomaliesResponse:
    validate_time_range(start_time, end_time)
    try:
        data = detect_all_anomalies(
            session=db,
            plant_id=plant_id,
            start_time=start_time,
            end_time=end_time,
            z_threshold=z_threshold,
            rolling_window_hours=rolling_window_hours,
            pf_threshold=pf_threshold,
            limit=limit,
        )
        return UnifiedAnomaliesResponse(**data)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect unified anomalies: {str(e)}",
        )
