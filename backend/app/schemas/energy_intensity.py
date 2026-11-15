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
    consumption_kwh: Optional[Decimal]
    cost_inr: Optional[Decimal]
    co2e_kg: Optional[Decimal]
    reading_count: int
    percentage_of_plant_total: Optional[Decimal]


class FacilityUtilitiesSummary(BaseModel):
    """Summary of non-process facility utility meters."""
    total_utility_consumption_kwh: Optional[Decimal]
    utility_share_percentage: Optional[Decimal]
    data_available: bool
    reading_count: int
    meters: List[FactoryUtilityItem]


class FactoryEnergyResponse(BaseModel):
    """Factory-level energy, total plant SEC, and utility segregation."""
    plant_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    data_available: bool = Field(..., description="Whether plant energy readings were returned for the requested scope")
    total_plant_energy_kwh: Optional[Decimal] = Field(None, description="Energy returned from all plant meters in the requested scope (kWh)")
    total_plant_cost_inr: Optional[Decimal] = Field(None, description="Dataset-calculated cost for the requested scope (INR)")
    total_plant_co2e_kg: Optional[Decimal] = Field(None, description="Estimated CO2e for the requested scope (kg)")
    final_assembly_data_available: bool
    final_assembly_actual_output: Optional[int] = Field(None, description="Finished phones output at Final Assembly gate")
    final_assembly_good_output: Optional[int] = None
    factory_sec_alignment_available: bool
    factory_sec_scope_complete: bool
    factory_sec_data_available: bool
    factory_sec_good_data_available: bool
    factory_sec_aligned_energy_kwh: Optional[Decimal] = None
    factory_sec_aligned_actual_output: Optional[int] = None
    factory_sec_aligned_good_output: Optional[int] = None
    factory_sec_aligned_plant_hours: int
    factory_sec_alignment_start_date: Optional[str] = None
    factory_sec_alignment_end_date: Optional[str] = None
    factory_sec_alignment_note: str
    factory_sec_kwh_per_finished_unit: Optional[Decimal] = Field(
        None,
        description="Aligned plant-hour energy divided by aligned Final Assembly actual output (kWh/unit)",
    )
    factory_sec_good_kwh_per_finished_unit: Optional[Decimal] = Field(
        None,
        description="Aligned plant-hour energy divided by aligned Final Assembly good output (kWh/unit)",
    )
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
