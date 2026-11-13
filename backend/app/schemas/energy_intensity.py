"""Pydantic schemas for Energy Intensity and Specific Energy Consumption (SEC) API."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProcessEnergyLineItem(BaseModel):
    """Line-level process energy, production volume, and calculated Process SEC."""
    line_id: str
    plant_id: str
    line_type: str
    meter_id: str
    actual_qty: int
    good_qty: int
    process_kwh: Decimal
    process_cost_inr: Decimal
    process_co2e_kg: Decimal
    process_sec_actual_kwh_per_unit: Optional[Decimal] = Field(None, description="Direct process SEC (kWh/unit)")
    process_sec_good_kwh_per_unit: Optional[Decimal] = Field(None, description="Good units process SEC (kWh/unit)")
    operating_hours: int
    zero_output_hours: int


class ProcessEnergySummaryResponse(BaseModel):
    """Process-level energy and SEC summary response across SMT and FAL lines."""
    plant_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    lines: List[ProcessEnergyLineItem]
    smt_summary: Dict[str, Any]
    fal_summary: Dict[str, Any]


class FactoryUtilityItem(BaseModel):
    """Utility meter consumption and share of total plant energy."""
    meter_id: str
    area: str
    consumption_kwh: Decimal
    cost_inr: Decimal
    co2e_kg: Decimal
    percentage_of_plant_total: Decimal


class FacilityUtilitiesSummary(BaseModel):
    """Summary of non-process facility utility meters."""
    total_utility_consumption_kwh: Decimal
    utility_share_percentage: Decimal
    meters: List[FactoryUtilityItem]


class FactoryEnergyResponse(BaseModel):
    """Factory-level energy, total plant SEC, and utility segregation."""
    plant_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total_plant_energy_kwh: Decimal = Field(..., description="Sum of all 5 plant meters (kWh)")
    total_plant_cost_inr: Decimal
    total_plant_co2e_kg: Decimal
    final_assembly_actual_output: int = Field(..., description="Finished phones output at Final Assembly gate")
    final_assembly_good_output: int
    factory_sec_kwh_per_finished_unit: Optional[Decimal] = Field(..., description="Total Plant kWh / Finished Phones")
    factory_sec_good_kwh_per_finished_unit: Optional[Decimal]
    facility_utilities: FacilityUtilitiesSummary


class ProductProcessEnergyItem(BaseModel):
    """Direct process manufacturing energy observed while producing each SKU."""
    product_id: str
    product_name: str
    product_family: str
    smt_actual_units: int
    fal_actual_units: int
    smt_process_kwh: Decimal
    fal_process_kwh: Decimal
    total_direct_process_kwh: Decimal
    total_process_cost_inr: Decimal
    smt_process_sec_kwh_per_board: Optional[Decimal]
    fal_process_sec_kwh_per_phone: Optional[Decimal]
    finished_phone_process_sec_kwh_per_unit: Optional[Decimal] = Field(
        None,
        description="Finished-phone combined SEC (kWh/phone). Unavailable across decoupled SMT/FAL stages without WIP lot tracking.",
    )
    finished_phone_sec_status: Optional[str] = Field(
        None,
        description="Status explaining availability of finished-phone SEC calculation.",
    )
    scope_note: str


class ZeroProductionLineItem(BaseModel):
    """Standby energy draw during zero-output hours for a specific line."""
    line_id: str
    plant_id: str
    meter_id: str
    zero_production_hours: int
    standby_consumption_kwh: Decimal
    standby_cost_inr: Decimal
    avg_standby_kwh_per_hr: Decimal


class ZeroProductionReasonItem(BaseModel):
    """Standby energy draw grouped by stoppage cause."""
    downtime_reason: str
    hours: int
    consumption_kwh: Decimal
    cost_inr: Decimal


class ZeroProductionEnergyResponse(BaseModel):
    """Process standby energy observed during zero-production hours."""
    plant_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total_zero_production_hours: int
    total_zero_production_energy_kwh: Decimal
    total_zero_production_cost_inr: Decimal
    overall_avg_standby_kwh_per_hr: Decimal
    by_line: List[ZeroProductionLineItem]
    by_downtime_reason: List[ZeroProductionReasonItem]
    classification_note: str
