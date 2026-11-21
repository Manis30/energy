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
    actual_units: Optional[int] = None
    good_units: Optional[int] = None
    kwh_per_actual_unit: Optional[Decimal] = None
    kwh_per_good_unit: Optional[Decimal] = None
    denominator_unit: Optional[str] = None
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


class CoverageSummary(BaseModel):
    """Hourly observation coverage and boundary completeness."""
    expected_plant_hours: int = Field(..., description="Expected plant-hours for the requested reporting scope")
    complete_matched_hours: int = Field(..., description="Plant-hours with all 5 meters and FAL production present")
    incomplete_hours: int = Field(..., description="Plant-hours missing meters or production observations")
    coverage_percentage: Decimal = Field(..., description="Percentage of complete matched plant-hours")
    coverage_status: str = Field(..., description="FULL, PARTIAL, INSUFFICIENT, or NONE")
    coverage_reasons: List[str] = Field(default_factory=list, description="Explanations of coverage limitations")


class ProductionQualityContext(BaseModel):
    """Final Assembly operational volume, scrap, rework, and downtime context."""
    fal_target_qty: Optional[int] = Field(None, description="Final Assembly target production (units)")
    fal_actual_qty: Optional[int] = Field(None, description="Final Assembly actual production (units)")
    fal_good_qty: Optional[int] = Field(None, description="Final Assembly good production (units)")
    fal_reject_qty: Optional[int] = Field(None, description="Final Assembly rejected scrap units")
    fal_rework_qty: Optional[int] = Field(None, description="Final Assembly reworked units")
    fal_reject_rate_pct: Optional[Decimal] = Field(None, description="Final Assembly reject rate (%)")
    fal_yield_pct: Optional[Decimal] = Field(None, description="Final Assembly yield rate (%)")
    fal_downtime_line_minutes: Optional[int] = Field(None, description="Final Assembly line downtime duration (minutes)")
    target_qty: Optional[int] = None
    actual_qty: Optional[int] = None
    good_qty: Optional[int] = None
    reject_qty: Optional[int] = None
    rework_qty: Optional[int] = None
    reject_rate_percentage: Optional[Decimal] = None
    yield_percentage: Optional[Decimal] = None
    downtime_minutes: Optional[int] = None


class FactorLineage(BaseModel):
    """Lineage and approval classification for conversion factors."""
    tariff_rate_inr_per_kwh: Optional[Decimal] = Field(None, description="Applied electricity tariff (INR/kWh)")
    tariff_approval_status: str = Field("UNKNOWN", description="Approval status of tariff factor")
    tariff_classification: str = Field("dataset-derived", description="Tariff classification")
    emissions_factor_kg_co2e_per_kwh: Optional[Decimal] = Field(None, description="Applied grid emissions factor (kg CO2e/kWh)")
    emissions_approval_status: str = Field("UNKNOWN", description="Approval status of emissions factor")
    emissions_classification: str = Field("estimated", description="Emissions classification")
    source_dataset_version: Optional[str] = Field(None, description="Source dataset version identifier")


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

    # Phase 2 Complete Energy Intelligence KPIs per Good Finished Unit
    electricity_intensity_kwh_per_good_unit: Optional[Decimal] = Field(
        None,
        description="Sum of eligible plant energy divided by matched FAL good output (kWh/good finished unit)",
    )
    cost_intensity_inr_per_good_unit: Optional[Decimal] = Field(
        None,
        description="Sum of eligible plant cost divided by matched FAL good output (₹/good finished unit)",
    )
    emissions_intensity_co2e_per_good_unit: Optional[Decimal] = Field(
        None,
        description="Sum of eligible plant CO2e divided by matched FAL good output (kg CO2e/good finished unit)",
    )
    electricity_intensity_status: str = Field("AVAILABLE", description="AVAILABLE or UNAVAILABLE")
    electricity_intensity_reason: Optional[str] = Field(None, description="Reason if intensity is unavailable")
    cost_intensity_status: str = Field("AVAILABLE", description="AVAILABLE or UNAVAILABLE")
    cost_intensity_reason: Optional[str] = Field(None, description="Reason if cost intensity is unavailable")
    emissions_intensity_status: str = Field("AVAILABLE", description="AVAILABLE or UNAVAILABLE")
    emissions_intensity_reason: Optional[str] = Field(None, description="Reason if emissions intensity is unavailable")
    factory_sec_aligned_cost_inr: Optional[Decimal] = Field(None, description="Aligned plant-hour electricity cost (INR)")
    factory_sec_aligned_co2e_kg: Optional[Decimal] = Field(None, description="Aligned plant-hour estimated emissions (kg CO2e)")
    coverage: Optional[CoverageSummary] = None
    coverage_summary: Optional[CoverageSummary] = None
    production_context: Optional[ProductionQualityContext] = None
    production_quality_context: Optional[ProductionQualityContext] = None
    factor_lineage: Optional[FactorLineage] = None


class EnergyIntensityTrendBucket(BaseModel):
    """Energy intensity, cost intensity, emissions intensity and coverage for a single time bucket."""
    period_start: str = Field(..., description="Bucket start date (YYYY-MM-DD)")
    period_end: str = Field(..., description="Bucket end date (YYYY-MM-DD)")
    plant_id: str = Field(..., description="Plant scope ('ALL' or specific plant identifier)")
    grain: str = Field(..., description="Aggregation grain ('daily' or 'monthly')")
    eligible_energy_kwh: Optional[Decimal] = Field(None, description="Eligible plant electricity consumption (kWh)")
    eligible_cost_inr: Optional[Decimal] = Field(None, description="Eligible electricity cost (INR)")
    eligible_co2e_kg: Optional[Decimal] = Field(None, description="Eligible estimated emissions (kg CO2e)")
    matched_good_qty: Optional[int] = Field(None, description="Matched Final Assembly good finished units")
    matched_actual_qty: Optional[int] = Field(None, description="Matched Final Assembly actual finished units")
    electricity_intensity_kwh_per_good_unit: Optional[Decimal] = Field(
        None, description="Electricity intensity (kWh/good finished unit)"
    )
    cost_intensity_inr_per_good_unit: Optional[Decimal] = Field(
        None, description="Estimated electricity cost intensity (₹/good finished unit)"
    )
    emissions_intensity_co2e_per_good_unit: Optional[Decimal] = Field(
        None, description="Estimated emissions intensity (kg CO2e/good finished unit)"
    )
    factory_sec_actual_kwh_per_unit: Optional[Decimal] = Field(
        None, description="Engineering SEC based on actual output (kWh/finished unit)"
    )
    factory_sec_good_kwh_per_finished_unit: Optional[Decimal] = Field(
        None, description="SEC based on good output (kWh/good finished unit)"
    )
    coverage: CoverageSummary
    production_context: ProductionQualityContext
    status: str = Field("AVAILABLE", description="AVAILABLE or UNAVAILABLE")
    reason: Optional[str] = Field(None, description="Reason if intensity is UNAVAILABLE")


class EnergyIntensityTrendsResponse(BaseModel):
    """Time-series trend response of energy, cost, and emissions intensity."""
    plant_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    grain: str = Field(..., description="'daily' or 'monthly'")
    group_by_plant: bool = Field(False, description="Whether broken out by individual plant")
    total_buckets: int
    buckets: List[EnergyIntensityTrendBucket]
    factor_lineage: Optional[FactorLineage] = None


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
