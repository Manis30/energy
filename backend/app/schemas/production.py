"""Pydantic schemas for Production Analytics API."""

from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class OeeAssessment(BaseModel):
    """Assessment of standard OEE computability."""
    status: str = Field(..., description="'available' or 'unavailable'")
    quality_rate: Optional[Decimal] = Field(None, description="Good count / actual count (%)")
    availability: Optional[Decimal] = Field(None, description="Availability rate (%)")
    performance: Optional[Decimal] = Field(None, description="Performance rate (%)")
    overall_oee: Optional[Decimal] = Field(None, description="Overall Equipment Effectiveness (%)")
    reason: Optional[str] = Field(None, description="Explanation of calculation assumptions or limitations")


class ProductionSummaryResponse(BaseModel):
    """Overall factory production summary response."""
    plant_id: Optional[str] = None
    line_id: Optional[str] = None
    product_id: Optional[str] = None
    shift_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    target_qty: int
    actual_qty: int
    good_qty: int
    reject_qty: int
    rework_qty: int
    downtime_min: int
    event_count: int
    quantity_balance_valid: bool
    achievement_rate: Decimal = Field(..., description="Actual / Target (%)")
    good_rate: Decimal = Field(..., description="Good / Actual (%)")
    reject_rate: Decimal = Field(..., description="Reject / Actual (%)")
    rework_rate: Decimal = Field(..., description="Rework / Actual (%)")
    oee: Optional[OeeAssessment] = None


class ProductionLineItem(BaseModel):
    """Production metrics aggregated by production line."""
    line_id: str
    plant_id: str
    line_type: str
    area: str
    target_qty: int
    actual_qty: int
    good_qty: int
    reject_qty: int
    rework_qty: int
    downtime_min: int
    operating_hours: int
    achievement_rate: Decimal
    good_rate: Decimal
    reject_rate: Decimal
    rework_rate: Decimal


class ProductionProductItem(BaseModel):
    """Production metrics aggregated by product SKU."""
    product_id: str
    product_name: str
    product_family: str
    target_qty: int
    actual_qty: int
    good_qty: int
    reject_qty: int
    rework_qty: int
    operating_hours: int
    achievement_rate: Decimal
    good_rate: Decimal
    reject_rate: Decimal
    rework_rate: Decimal


class ProductionShiftItem(BaseModel):
    """Production metrics aggregated by manufacturing shift."""
    shift_id: str
    target_qty: int
    actual_qty: int
    good_qty: int
    reject_qty: int
    downtime_min: int
    operating_hours: int
    achievement_rate: Decimal
    good_rate: Decimal
    reject_rate: Decimal
    rework_rate: Decimal


class DowntimeReasonItem(BaseModel):
    """Downtime minutes and occurrence share grouped by stoppage reason."""
    downtime_reason: str
    total_downtime_min: int
    event_count: int
    zero_output_events: int


class DailyProductionItem(BaseModel):
    """Daily production output and scrap time series."""
    date: str
    target_qty: int
    actual_qty: int
    good_qty: int
    reject_qty: int
    downtime_min: int
    achievement_rate: Decimal
    good_rate: Decimal
    reject_rate: Decimal
    rework_rate: Decimal
