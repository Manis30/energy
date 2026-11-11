"""Common schemas and validation helpers for Industrial Energy Intelligence API."""

from datetime import date, datetime
from typing import Optional
from fastapi import HTTPException, status
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standardized error response schema."""
    error: str = Field(..., description="Error category or code")
    message: str = Field(..., description="Human-readable explanation of error")
    detail: Optional[str] = Field(None, description="Additional context if available")


def validate_date_range(start_date: Optional[date], end_date: Optional[date]) -> None:
    """Validate that start_date is not after end_date."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date range: start_date ({start_date.isoformat()}) must be before or equal to end_date ({end_date.isoformat()}).",
        )


def validate_time_range(start_time: Optional[datetime], end_time: Optional[datetime]) -> None:
    """Validate that start_time is not after end_time."""
    if start_time and end_time and start_time > end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid time range: start_time ({start_time.isoformat()}) must be before or equal to end_time ({end_time.isoformat()}).",
        )
