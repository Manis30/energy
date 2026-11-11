"""Energy Intensity and Specific Energy Consumption (SEC) API endpoints."""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.common import validate_date_range
from app.schemas.energy_intensity import (
    FactoryEnergyResponse,
    ProcessEnergySummaryResponse,
    ProductProcessEnergyItem,
    ZeroProductionEnergyResponse,
)
from app.services.energy_intensity import (
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
    summary="Get factory-level energy, total SEC, and utility segregation",
    description=(
        "Calculates factory-wide SEC (Total plant energy across all 5 meters divided by finished phone output). "
        "Strictly segregates non-process facility utilities (HVAC, Compressor, Chiller) and reports their share."
    ),
)
def read_factory_energy_analytics(
    plant_id: Optional[str] = Query(None, description="Plant ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db_session),
) -> FactoryEnergyResponse:
    validate_date_range(start_date, end_date)
    try:
        data = get_factory_energy_analytics(
            session=db,
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
        )
        return FactoryEnergyResponse(**data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate factory energy analytics: {str(e)}",
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
