"""
Pydantic schemas for Cross-Source Data Reconciliation Engine.

Defines contracts for deterministic data reconciliation findings, check results,
summary metrics, and API payloads across energy, production, and upload history sources.
"""

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReconciliationStatus(str, Enum):
    """Deterministic reconciliation outcome statuses."""

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class ReconciliationCategory(str, Enum):
    """Categories of cross-source reconciliation checks."""

    ENERGY_COVERAGE = "ENERGY_COVERAGE"
    PRODUCTION_COVERAGE = "PRODUCTION_COVERAGE"
    TIMESTAMP_ALIGNMENT = "TIMESTAMP_ALIGNMENT"
    DUPLICATE_RECORDS = "DUPLICATE_RECORDS"
    SOURCE_CONSISTENCY = "SOURCE_CONSISTENCY"
    REFERENCE_INTEGRITY = "REFERENCE_INTEGRITY"
    DATA_QUALITY = "DATA_QUALITY"


class ReconciliationFinding(BaseModel):
    """Discrete discrepancy or validation signal discovered during reconciliation."""

    check_id: str = Field(..., description="Unique check identifier, e.g. 'CHK_ENERGY_COVERAGE'")
    category: ReconciliationCategory = Field(..., description="Reconciliation check family")
    status: ReconciliationStatus = Field(..., description="'PASS', 'WARNING', 'FAIL', or 'UNAVAILABLE'")
    plant_id: Optional[str] = Field(None, description="Plant ID where known, e.g. 'IN-TN-01'")
    affected_entity: Optional[str] = Field(None, description="Specific meter, line, product, table, or file")
    evaluation_period: Dict[str, Any] = Field(..., description="Date or timestamp range evaluated")
    observed_value: Optional[Any] = Field(None, description="Observed measurement, count, or state")
    expected_value: Optional[Any] = Field(None, description="Expected value, threshold, or benchmark")
    difference: Optional[Any] = Field(None, description="Calculated variance or numerical delta where applicable")
    difference_unit: Optional[str] = Field(None, description="Unit of measurement, e.g. 'records', 'hours', 'kWh'")
    source_references: List[str] = Field(default_factory=list, description="Underlying tables or models inspected")
    explanation: str = Field(..., description="Deterministic human-readable explanation")
    reason_code: str = Field(..., description="Machine-readable diagnostic code")


class ReconciliationCheckResult(BaseModel):
    """Aggregated result for a single reconciliation check."""

    check_id: str
    category: ReconciliationCategory
    name: str
    description: str
    status: ReconciliationStatus
    plant_id: Optional[str] = None
    findings_count: int
    findings: List[ReconciliationFinding]
    summary: str


class ReconciliationSummaryCounts(BaseModel):
    """Aggregate check counts partitioned by reconciliation status."""

    pass_count: int = Field(default=0, description="Count of checks passing with zero discrepancies")
    warning_count: int = Field(default=0, description="Count of checks with non-fatal discrepancies")
    fail_count: int = Field(default=0, description="Count of checks with confirmed data integrity violations")
    unavailable_count: int = Field(default=0, description="Count of checks where evidence/mapping was unavailable")
    total_checks: int = Field(default=0, description="Total number of evaluated checks")


class ReconciliationReportResponse(BaseModel):
    """Full cross-source reconciliation report response."""

    status: ReconciliationStatus = Field(..., description="Overall status: FAIL > WARNING > UNAVAILABLE > PASS")
    counts: ReconciliationSummaryCounts
    evaluation_period: Dict[str, str] = Field(..., description="Inclusive start_date and end_date (YYYY-MM-DD)")
    plant_id: Optional[str] = Field(None, description="Plant filter if applied")
    checks: List[ReconciliationCheckResult]
    limitations: List[str] = Field(default_factory=list, description="Known architectural boundaries and schema limits")


class ReconciliationSummaryResponse(BaseModel):
    """Lightweight reconciliation status summary response."""

    status: ReconciliationStatus
    counts: ReconciliationSummaryCounts
    evaluation_period: Dict[str, str]
    plant_id: Optional[str] = None
    category_statuses: Dict[str, ReconciliationStatus] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


class ReconciliationCheckDefinition(BaseModel):
    """Metadata describing a supported reconciliation check."""

    check_id: str
    category: ReconciliationCategory
    name: str
    description: str
    supported_dimensions: List[str]
    unsupported_dimensions: List[str]
    source_tables: List[str]

