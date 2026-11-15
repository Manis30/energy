"""Pydantic schemas for Energy Analytics API."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EnergyPeakReading(BaseModel):
    """Peak hourly energy consumption details."""
    timestamp: Optional[str] = Field(None, description="ISO timestamp of the peak reading")
    meter_id: Optional[str] = Field(None, description="Meter recording peak consumption")
    plant_id: Optional[str] = Field(None, description="Plant location of peak reading")
    consumption_kwh: Decimal = Field(..., description="Peak hourly consumption in kWh")


class EnergySummaryResponse(BaseModel):
    """Overall energy analytics summary response."""
    plant_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    data_available: bool = Field(..., description="Whether energy meter readings were returned for the requested scope")
    consumption_data_available: bool
    cost_data_available: bool
    emissions_data_available: bool
    power_factor_data_available: bool
    total_consumption_kwh: Optional[Decimal] = Field(None, description="Total energy consumption across filtered scope (kWh)")
    total_cost_inr: Optional[Decimal] = Field(None, description="Dataset-calculated energy cost in INR")
    total_co2e_kg: Optional[Decimal] = Field(None, description="Estimated CO2e using the dataset emission factor (kg)")
    avg_power_factor: Optional[Decimal] = Field(None, description="Energy-weighted average power factor across readings")
    arithmetic_avg_power_factor: Optional[Decimal] = Field(None, description="Simple arithmetic mean power factor")
    total_readings: int = Field(..., description="Number of hourly meter readings included")
    distinct_hours: int = Field(..., description="Number of distinct operating hours")
    avg_hourly_consumption_kwh: Optional[Decimal] = Field(None, description="Average consumption per active meter-hour")
    peak_reading: Optional[EnergyPeakReading] = None


class MeterEnergyItem(BaseModel):
    """Energy consumption and cost breakdown per individual meter."""
    meter_id: str
    area: str
    consumption_kwh: Optional[Decimal]
    cost_inr: Optional[Decimal]
    co2e_kg: Optional[Decimal]
    avg_power_factor: Optional[Decimal] = Field(None, description="Energy-weighted average power factor")
    arithmetic_avg_power_factor: Optional[Decimal] = Field(None, description="Arithmetic mean power factor")
    power_factor_data_available: bool
    peak_kwh: Optional[Decimal]
    reading_count: int
    percentage_of_total: Optional[Decimal] = Field(None, description="Share of total analyzed consumption (%)")


class AreaEnergyItem(BaseModel):
    """Energy consumption and spend aggregated by factory area."""
    area: str
    consumption_kwh: Optional[Decimal]
    cost_inr: Optional[Decimal]
    co2e_kg: Optional[Decimal]
    avg_power_factor: Optional[Decimal] = Field(None, description="Energy-weighted average power factor")
    arithmetic_avg_power_factor: Optional[Decimal] = Field(None, description="Arithmetic mean power factor")
    power_factor_data_available: bool
    percentage_of_total: Optional[Decimal]


class DailyEnergyItem(BaseModel):
    """Daily energy time-series observation."""
    date: str
    consumption_kwh: Optional[Decimal]
    cost_inr: Optional[Decimal]
    co2e_kg: Optional[Decimal]
    avg_power_factor: Optional[Decimal] = Field(None, description="Energy-weighted average power factor")
    arithmetic_avg_power_factor: Optional[Decimal] = Field(None, description="Arithmetic mean power factor")
    power_factor_data_available: bool
    peak_hourly_kwh: Optional[Decimal]
    reading_count: int


class PowerFactorSummaryResponse(BaseModel):
    """Power factor distribution and application monitoring summary."""
    threshold: Decimal
    power_factor_data_available: bool
    power_factor_readings_count: int
    avg_power_factor: Optional[Decimal] = Field(
        None,
        description="Energy-weighted average when energy is positive, arithmetic fallback for zero-energy readings, unavailable when no readings exist",
    )
    arithmetic_avg_power_factor: Optional[Decimal] = Field(None, description="Arithmetic mean power factor")
    min_power_factor: Optional[Decimal] = None
    max_power_factor: Optional[Decimal] = None
    total_readings: int
    low_pf_events_count: int
    low_pf_percentage: Optional[Decimal] = None
    low_pf_by_meter: List[Dict[str, Any]]
