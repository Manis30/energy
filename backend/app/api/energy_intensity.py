"""Energy Intensity and Specific Energy Consumption (SEC) API endpoints."""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.common import validate_date_range
from app.schemas.energy_intensity import (
    EnergyIntensityTrendsResponse,
    FactoryEnergyResponse,
    ProcessEnergySummaryResponse,
    ProductProcessEnergyItem,
    ZeroProductionEnergyResponse,
)
from app.services.energy_intensity import (
    get_energy_intensity_trends,
    get_factory_energy_analytics,
    get_process_energy_analytics,
    get_product_process_energy,
    get_zero_production_period_energy,
)

router = APIRouter()


@router.get(
    "/process",
    response_model=ProcessEnergySummaryResponse,
    summary="Get process-level energy and SEC by production line",
    description=(
        "Calculates direct process energy and Specific Energy Consumption (kWh/unit) "
        "using dedicated line-to-meter mappings (SMT -> MTR-SMT, FAL -> MTR-FAL). "
        "Strictly excludes facility utilities and avoids Cartesian join inflation."
    ),
)
def read_process_energy_analytics(
    plant_id: Optional[str] = Query(None, description="Plant ID filter, e.g. 'IN-TN-01' or 'IN-KA-01'"),
    start_date: Optional[date] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date filter (YYYY-MM-DD)"),
    db: Session = Depends(get_db_session),
) -> ProcessEnergySummaryResponse:
    validate_date_range(start_date, end_date)
    try:
        data = get_process_energy_analytics(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
        )
        return ProcessEnergySummaryResponse(**data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate process energy analytics: {str(e)}",
        )


@router.get(
    "/factory",
    response_model=FactoryEnergyResponse,
    summary="Get factory-level energy, complete coverage, and headline energy intelligence KPIs",
    description=(
        "Calculates factory-wide electricity intensity (kWh/good unit), cost intensity (₹/good unit), "
        "and emissions intensity (kg CO2e/good unit) per good finished unit. Reports telemetry coverage "
        "(expected vs complete matched plant-hours), production quality context, and utility segregation."
    ),
)
def read_factory_energy_analytics(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    line_id: Optional[str] = Query(None, description="Optional line filter"),
    product_id: Optional[str] = Query(None, description="Optional product SKU filter"),
    shift_id: Optional[str] = Query(None, description="Optional shift filter"),
    db: Session = Depends(get_db_session),
) -> FactoryEnergyResponse:
    validate_date_range(start_date, end_date)
    try:
        data = get_factory_energy_analytics(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
            line_id=line_id,
            product_id=product_id,
            shift_id=shift_id,
        )
        return FactoryEnergyResponse(**data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate factory energy analytics: {str(e)}",
        )


@router.get(
    "/trends",
    response_model=EnergyIntensityTrendsResponse,
    summary="Get energy, cost, and emissions intensity trends with coverage",
    description=(
        "Calculates time-series trends of electricity intensity (kWh/good unit), cost intensity (₹/good unit), "
        "and emissions intensity (kg CO2e/good unit) grouped by day or month. Strictly sums numerators and "
        "denominators across buckets (never averages daily ratios). Delivers coverage and production context."
    ),
)
def read_energy_intensity_trends(
    plant_id: Optional[str] = Query(None, description="Plant ID filter (all plants when omitted)"),
    start_date: Optional[date] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date filter (YYYY-MM-DD)"),
    grain: str = Query("daily", description="Time aggregation grain: 'daily' or 'monthly'"),
    group_by_plant: bool = Query(False, description="When true, breaks out each plant separately"),
    db: Session = Depends(get_db_session),
) -> EnergyIntensityTrendsResponse:
    validate_date_range(start_date, end_date)
    try:
        data = get_energy_intensity_trends(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
            grain=grain,
            group_by_plant=group_by_plant,
        )
        return EnergyIntensityTrendsResponse(**data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate energy intensity trends: {str(e)}",
        )


@router.get(
    "/product",
    response_model=List[ProductProcessEnergyItem],
    summary="Get product SKU direct process energy and stage SEC",
    description=(
        "Returns manufacturing energy observed while operating each SKU across SMT and Final Assembly stages. "
        "Facility utilities are excluded from product allocation."
    ),
)
def read_product_process_energy(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db_session),
) -> List[ProductProcessEnergyItem]:
    validate_date_range(start_date, end_date)
    try:
        data = get_product_process_energy(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
        )
        return [ProductProcessEnergyItem(**item) for item in data]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate product process energy: {str(e)}",
        )


@router.get(
    "/zero-production",
    response_model=ZeroProductionEnergyResponse,
    summary="Get standby/idle energy observed during zero-production hours",
    description=(
        "Analyzes hours where production output was zero during stoppage events (feeder jam, changeover, etc.). "
        "Reports actual measured standby power without labeling it avoidable waste without technical baseline."
    ),
)
def read_zero_production_period_energy(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db_session),
) -> ZeroProductionEnergyResponse:
    validate_date_range(start_date, end_date)
    try:
        data = get_zero_production_period_energy(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
        )
        return ZeroProductionEnergyResponse(**data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate zero-production period energy: {str(e)}",
        )
