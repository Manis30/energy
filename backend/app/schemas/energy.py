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
    total_consumption_kwh: Decimal = Field(..., description="Total energy consumption across filtered scope (kWh)")
    total_cost_inr: Decimal = Field(..., description="Total energy spend in INR")
    total_co2e_kg: Decimal = Field(..., description="Total CO2e greenhouse gas emissions (kg)")
    avg_power_factor: Optional[Decimal] = Field(None, description="Average power factor across readings")
    total_readings: int = Field(..., description="Number of hourly meter readings included")
    distinct_hours: int = Field(..., description="Number of distinct operating hours")
    avg_hourly_consumption_kwh: Decimal = Field(..., description="Average consumption per active meter-hour")
    peak_reading: Optional[EnergyPeakReading] = None


class MeterEnergyItem(BaseModel):
    """Energy consumption and cost breakdown per individual meter."""
    meter_id: str
    area: str
    consumption_kwh: Decimal
    cost_inr: Decimal
    co2e_kg: Decimal
    avg_power_factor: Optional[Decimal] = None
    peak_kwh: Decimal
    reading_count: int
    percentage_of_total: Decimal = Field(..., description="Share of total analyzed consumption (%)")


class AreaEnergyItem(BaseModel):
    """Energy consumption and spend aggregated by factory area."""
    area: str
    consumption_kwh: Decimal
    cost_inr: Decimal
    co2e_kg: Decimal
    avg_power_factor: Optional[Decimal] = None
    percentage_of_total: Decimal


class DailyEnergyItem(BaseModel):
    """Daily energy time-series observation."""
    date: str
    consumption_kwh: Decimal
    cost_inr: Decimal
    co2e_kg: Decimal
    avg_power_factor: Optional[Decimal] = None
    peak_hourly_kwh: Decimal
    reading_count: int


class PowerFactorSummaryResponse(BaseModel):
    """Power factor distribution and compliance summary."""
    threshold: Decimal
    avg_power_factor: Decimal
    min_power_factor: Decimal
    max_power_factor: Decimal
    total_readings: int
    low_pf_events_count: int
    low_pf_percentage: Decimal
    low_pf_by_meter: List[Dict[str, Any]]
