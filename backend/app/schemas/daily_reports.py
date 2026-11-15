"""Pydantic schemas for daily report validation, inspection, ingestion, and audit history."""

from datetime import date, datetime
from enum import Enum
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


class CompletenessInfo(BaseModel):
    """Assessment of reporting coverage against standard 24-hour factory structures."""
    is_complete: bool = True
    coverage_status: str = Field("COMPLETE", description="'COMPLETE' or 'PARTIAL'")
    hours_reported: int = 24
    missing_hours: List[int] = Field(default_factory=list)
    found_entities: List[str] = Field(default_factory=list)
    missing_entities: List[str] = Field(default_factory=list)
    plant_scopes: Dict[str, Any] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


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
    is_complete: bool = True
    coverage_status: str = "COMPLETE"
    missing_hours: List[int] = Field(default_factory=list)
    missing_entities: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    completeness: Optional[CompletenessInfo] = None


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
    replaced_rows: int = 0
    affected_scope: Optional[Dict[str, Any]] = None


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


class CoverageRecordStatus(str, Enum):
    """Whether any persisted records were observed for a plant and date."""

    NO_RECORDS = "NO_RECORDS"
    OBSERVED = "OBSERVED"


class EntityCoverageStatus(str, Enum):
    """Date-level entity observation status, not an hourly operating schedule."""

    NO_RECORDS = "NO_RECORDS"
    PARTIAL_OBSERVED = "PARTIAL_OBSERVED"
    ALL_REGISTERED_OBSERVED = "ALL_REGISTERED_OBSERVED"
    UNDETERMINED = "UNDETERMINED"


class DailyStreamCoverage(BaseModel):
    """Persisted data coverage for one stream, plant, and reporting date."""

    plant_id: str
    reporting_date: date
    record_status: CoverageRecordStatus = Field(
        ..., description="Whether persisted records exist for this plant and date"
    )
    coverage_status: EntityCoverageStatus = Field(
        ...,
        description=(
            "Entity presence across the date only; ALL_REGISTERED_OBSERVED means each "
            "known registered entity appeared at least once, not once per hour"
        ),
    )
    record_count: int = Field(..., ge=0, description="Number of persisted fact rows")
    observed_hours: int = Field(
        ...,
        ge=0,
        description="Distinct hourly fact timestamps containing records; not scheduled operating hours",
    )
    expected_entity_count: Optional[int] = Field(
        None, description="Registered entities applicable to this plant, when determinable"
    )
    expected_entities: Optional[List[str]] = Field(
        None, description="Registered entities applicable to this plant, when determinable"
    )
    observed_entity_count: int = Field(..., ge=0)
    observed_entities: List[str] = Field(default_factory=list)
    unobserved_registered_entities: Optional[List[str]] = Field(
        None,
        description="Registered entities with no record on this date; does not imply they were scheduled",
    )
    unregistered_observed_entities: List[str] = Field(
        default_factory=list,
        description="Observed entity identifiers absent from the available registry",
    )
    all_registered_entities_observed_for_date: Optional[bool] = Field(
        None,
        description="Whether all applicable registered entities appeared at least once on this date",
    )
    missing_hours: Optional[List[int]] = Field(
        None,
        description="Unavailable without an approved operating calendar or expected-hour schedule",
    )
    first_observed_timestamp: Optional[datetime] = None
    last_observed_timestamp: Optional[datetime] = None
    limitations: List[str] = Field(default_factory=list)


class DailyReportCoverageResponse(BaseModel):
    """Read-only energy and production coverage for an inclusive date range."""

    start_date: date
    end_date: date
    registered_energy_meters: List[str] = Field(
        default_factory=list,
        description="Globally configured meter catalog; no plant-to-meter registry is available",
    )
    energy_coverage: List[DailyStreamCoverage] = Field(default_factory=list)
    production_coverage: List[DailyStreamCoverage] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)

