"""Pydantic schemas for daily report validation, inspection, ingestion, and audit history."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InspectResponse(BaseModel):
    """File inspection metadata and worksheet enumeration."""
    filename: str
    file_format: str = Field(..., description="CSV, XLSX, or XLS")
    file_size_bytes: int
    sheet_names: List[str] = Field(default_factory=list)
    is_multi_sheet: bool = False
    detected_report_type: Optional[str] = None
    estimated_rows: int = 0


class RowValidationError(BaseModel):
    """Specific row-level validation issue."""
    row_number: int
    column: Optional[str] = None
    error_type: str = Field(..., description="Category of error, e.g. MISSING_FIELD, RANGE_VIOLATION, FK_ERROR")
    message: str
    value: Optional[str] = None


class PreviewRow(BaseModel):
    """Preview row with validity status and error details."""
    row_number: int
    status: str = Field(..., description="VALID, DUPLICATE, or REJECTED")
    data: Dict[str, Any]
    errors: List[str] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    """Aggregated validation statistics and operational metrics."""
    report_type: str
    total_rows: int
    valid_rows: int
    rejected_rows: int
    duplicate_rows: int
    detected_date: Optional[date] = None
    confirmed_date: Optional[date] = None
    plants_found: List[str] = Field(default_factory=list)
    meters_found: Optional[List[str]] = None
    lines_found: Optional[List[str]] = None
    is_ready_for_ingest: bool = False


class ValidateReportResponse(BaseModel):
    """Comprehensive validation result including summary, preview, and error list."""
    filename: str
    file_format: str
    sheet_name: Optional[str] = None
    sheet_names: List[str] = Field(default_factory=list)
    detected_dates: List[str] = Field(default_factory=list)
    summary: ValidationSummary
    errors: List[RowValidationError] = Field(default_factory=list)
    preview: List[PreviewRow] = Field(default_factory=list)


class IngestReportResponse(BaseModel):
    """Outcome of transactional database ingestion."""
    upload_id: str
    status: str = Field(..., description="COMPLETED, FAILED, or PARTIAL")
    report_type: str
    reporting_date: date
    total_rows: int
    imported_rows: int
    duplicate_rows: int
    rejected_rows: int
    mode: str = Field(..., description="INCREMENTAL or OVERWRITE_CORRECTION")
    message: str


class UploadHistoryItem(BaseModel):
    """Single historical report upload and ingestion record."""
    id: int
    upload_id: str
    uploaded_at: datetime
    report_type: str
    filename: str
    file_format: str
    sheet_name: Optional[str] = None
    reporting_date: date
    file_size_bytes: int
    total_rows: int
    valid_rows: int
    rejected_rows: int
    duplicate_rows: int
    status: str
    mode: str
    audit_details: Optional[str] = None

    class Config:
        from_attributes = True

