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
    data_available: bool
    target_qty: Optional[int]
    actual_qty: Optional[int]
    good_qty: Optional[int]
    reject_qty: Optional[int]
    rework_qty: Optional[int]
    downtime_min: Optional[int]
    event_count: int
    quantity_balance_valid: Optional[bool]
    achievement_rate: Optional[Decimal] = Field(None, description="Actual / Target (%)")
    good_rate: Optional[Decimal] = Field(None, description="Good / Actual (%)")
    reject_rate: Optional[Decimal] = Field(None, description="Reject / Actual (%)")
    rework_rate: Optional[Decimal] = Field(None, description="Rework / Actual (%)")
    oee: Optional[OeeAssessment] = None


class ProductionLineItem(BaseModel):
    """Production metrics aggregated by production line."""
    line_id: str
    plant_id: str
    line_type: str
    area: str
    target_qty: Optional[int]
    actual_qty: Optional[int]
    good_qty: Optional[int]
    reject_qty: Optional[int]
    rework_qty: Optional[int]
    downtime_min: Optional[int]
    operating_hours: int
    achievement_rate: Optional[Decimal]
    good_rate: Optional[Decimal]
    reject_rate: Optional[Decimal]
    rework_rate: Optional[Decimal]


class ProductionProductItem(BaseModel):
    """Production metrics aggregated by product SKU."""
    product_id: str
    product_name: str
    product_family: str
    target_qty: Optional[int]
    actual_qty: Optional[int]
    good_qty: Optional[int]
    reject_qty: Optional[int]
    rework_qty: Optional[int]
    operating_hours: int
    achievement_rate: Optional[Decimal]
    good_rate: Optional[Decimal]
    reject_rate: Optional[Decimal]
    rework_rate: Optional[Decimal]


class ProductionShiftItem(BaseModel):
    """Production metrics aggregated by manufacturing shift."""
    shift_id: str
    target_qty: Optional[int]
    actual_qty: Optional[int]
    good_qty: Optional[int]
    reject_qty: Optional[int]
    rework_qty: Optional[int] = None
    downtime_min: Optional[int]
    operating_hours: int
    achievement_rate: Optional[Decimal]
    good_rate: Optional[Decimal]
    reject_rate: Optional[Decimal]
    rework_rate: Optional[Decimal]


class DowntimeReasonItem(BaseModel):
    """Downtime minutes and occurrence share grouped by stoppage reason."""
    downtime_reason: str
    total_downtime_min: Optional[int]
    event_count: int
    zero_output_events: int


class DailyProductionItem(BaseModel):
    """Daily production output and scrap time series."""
    date: str
    target_qty: Optional[int]
    actual_qty: Optional[int]
    good_qty: Optional[int]
    reject_qty: Optional[int]
    rework_qty: Optional[int] = None
    downtime_min: Optional[int]
    achievement_rate: Optional[Decimal]
    good_rate: Optional[Decimal]
    reject_rate: Optional[Decimal]
    rework_rate: Optional[Decimal]
