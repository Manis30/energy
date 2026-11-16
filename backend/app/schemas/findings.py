"""Pydantic schemas for Operational Findings Lifecycle API."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OccurrenceResponse(BaseModel):
    """Detection occurrence evidence record."""
    occurrence_id: str
    finding_id: str
    occurrence_ts: str
    actual_value: Decimal
    baseline_value: Optional[Decimal] = None
    deviation_score: float
    severity: str
    explanation: Optional[str] = None
    context_flags: Dict[str, Any] = Field(default_factory=dict)
    recorded_at: str
    source_table: Optional[str] = Field(None, description="Originating database table for the anomaly observation")
    source_record_id: Optional[str] = Field(None, description="Primary key identifier of the originating source record")
    upload_id: Optional[str] = Field(None, description="Upload batch identifier that introduced the originating record")
    detector_version: Optional[str] = Field(None, description="Deterministic detector algorithm version that identified the anomaly")
    lineage_status: str = Field(default="UNAVAILABLE", description="Source lineage resolution status: AVAILABLE, MULTI_SOURCE, or UNAVAILABLE")
    source_records: List[Dict[str, Any]] = Field(default_factory=list, description="Structured lineage references for multi-row or composite anomalies")


class AuditLogResponse(BaseModel):
    """Lifecycle audit trail entry with explicit caller attribution status."""
    id: int
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    performed_at: str
    comment: Optional[str] = None
    actor_attribution: Optional[str] = Field(
        None,
        description="Unverified caller-supplied attribution label (e.g. operator label, terminal identifier).",
    )
    actor_type: str = Field(
        "UNVERIFIED_CALLER",
        description="Attribution classification: 'SYSTEM_AUTOMATION' or 'UNVERIFIED_CALLER'. Never presented as verified authentication.",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FindingSummary(BaseModel):
    """Operational finding high-level summary item."""
    finding_id: str
    finding_key: str
    anomaly_type: str
    plant_id: str
    meter_id: Optional[str] = None
    line_id: Optional[str] = None
    status: str
    severity: str
    occurrence_count: int
    first_detected_at: str
    last_detected_at: str
    current_actual_value: Optional[Decimal] = None
    current_baseline_value: Optional[Decimal] = None
    current_deviation_score: Optional[float] = None
    current_explanation: Optional[str] = None
    acknowledged_at: Optional[str] = None
    investigated_at: Optional[str] = None
    resolved_at: Optional[str] = None
    reopened_at: Optional[str] = None
    created_at: str
    updated_at: str
    latest_source_table: Optional[str] = Field(None, description="Source table of the latest detection occurrence")
    latest_source_record_id: Optional[str] = Field(None, description="Source record ID of the latest detection occurrence")
    latest_upload_id: Optional[str] = Field(None, description="Upload batch ID of the latest detection occurrence")
    latest_detector_version: Optional[str] = Field(None, description="Detector algorithm version of the latest detection occurrence")
    latest_lineage_status: Optional[str] = Field(None, description="Lineage availability status of the latest detection occurrence")


class FindingDetailResponse(FindingSummary):
    """Full operational finding detail with occurrences and audit trail."""
    investigation_notes: Optional[str] = None
    resolution_notes: Optional[str] = None
    reopen_reason: Optional[str] = None
    occurrences: List[OccurrenceResponse] = Field(default_factory=list)
    audit_trail: List[AuditLogResponse] = Field(default_factory=list)


class FindingListResponse(BaseModel):
    """Paginated findings response."""
    items: List[FindingSummary]
    total: int
    limit: int
    offset: int


class AcknowledgeFindingRequest(BaseModel):
    """Request payload to acknowledge a finding."""
    comment: Optional[str] = Field(None, max_length=1000, description="Optional acknowledgment remarks")
    caller_attribution: Optional[str] = Field(
        None,
        max_length=150,
        description="Optional unverified caller-supplied attribution label (e.g. operator name or terminal ID). Not an authenticated identity.",
    )


class StartInvestigationRequest(BaseModel):
    """Request payload to transition finding to investigating state."""
    investigation_notes: Optional[str] = Field(None, max_length=5000, description="Initial investigation notes or hypothesis")
    caller_attribution: Optional[str] = Field(
        None,
        max_length=150,
        description="Optional unverified caller-supplied attribution label. Not an authenticated identity.",
    )


class AddNotesRequest(BaseModel):
    """Request payload to add ongoing investigation notes."""
    notes: str = Field(..., min_length=1, max_length=5000, description="Investigation progress or diagnostic findings")
    caller_attribution: Optional[str] = Field(
        None,
        max_length=150,
        description="Optional unverified caller-supplied attribution label. Not an authenticated identity.",
    )


class ResolveFindingRequest(BaseModel):
    """Request payload to resolve a finding."""
    resolution_notes: str = Field(..., min_length=1, max_length=5000, description="Root cause and corrective action resolution notes")
    caller_attribution: Optional[str] = Field(
        None,
        max_length=150,
        description="Optional unverified caller-supplied attribution label. Not an authenticated identity.",
    )


class ReopenFindingRequest(BaseModel):
    """Request payload to manually reopen a resolved finding."""
    reason: str = Field(..., min_length=1, max_length=2000, description="Justification for reopening previously resolved finding")
    caller_attribution: Optional[str] = Field(
        None,
        max_length=150,
        description="Optional unverified caller-supplied attribution label. Not an authenticated identity.",
    )


class SyncFindingsRequest(BaseModel):
    """Request payload to trigger findings synchronization from anomaly detection."""
    plant_id: Optional[str] = Field(None, description="Optional plant filter")
    meter_id: Optional[str] = Field(None, description="Optional meter filter")
    start_time: Optional[str] = Field(None, description="Optional ISO start time")
    end_time: Optional[str] = Field(None, description="Optional ISO end time")
    caller_attribution: Optional[str] = Field(
        None,
        max_length=150,
        description="Optional unverified caller-supplied attribution label. Not an authenticated identity.",
    )


class SyncFindingsResponse(BaseModel):
    """Result of anomaly detection findings synchronization."""
    total_anomalies_evaluated: int
    new_findings_created: int
    existing_findings_updated: int
    findings_reopened: int
    occurrences_recorded: int
    duplicates_ignored: int = 0
    conflicts_preserved: int = 0
    affected_finding_ids: List[str]


class UploadMetadataResponse(BaseModel):
    """Provenance upload batch audit metadata."""
    upload_id: str
    filename: str
    file_format: str
    sheet_name: Optional[str] = None
    report_type: str
    reporting_date: Optional[str] = None
    uploaded_at: Optional[str] = None
    file_size_bytes: int = 0
    total_rows: int = 0
    valid_rows: int = 0
    rejected_rows: int = 0
    duplicate_rows: int = 0
    status: str
    mode: str
    is_available: bool = True


class SourceRecordDrillDownResponse(BaseModel):
    """Detailed ground-truth source record resolution for an occurrence."""
    source_table: str = Field(..., description="PostgreSQL table name: fact_energy_meter_hourly or fact_hourly_production")
    source_record_id: Optional[str] = Field(None, description="Primary key identifier of source observation (meter_reading_id or event_id)")
    role: Optional[str] = Field(None, description="Domain semantic role (e.g. PRODUCTION_ZERO_OUTPUT_EVENT, PROCESS_ENERGY_MEASUREMENT)")
    reporting_timestamp: Optional[str] = Field(None, description="Timestamp of the physical sensor or production observation")
    plant_id: Optional[str] = Field(None, description="Plant identifier")
    entity_id: Optional[str] = Field(None, description="Meter ID or Line ID")
    entity_type: Optional[str] = Field(None, description="METER or LINE")
    record_status: str = Field("FOUND", description="FOUND, MISSING, or UNSUPPORTED_TABLE")
    raw_data: Optional[Dict[str, Any]] = Field(None, description="Full dictionary of source table columns and measured attributes")
    upload: Optional[UploadMetadataResponse] = Field(None, description="Upload batch details if linked to an upload batch")
    upload_status: str = Field("UNAVAILABLE", description="AVAILABLE, UNAVAILABLE_HISTORICAL, or UPLOAD_NOT_FOUND")
    lineage_state: str = Field(..., description="Stream-level lineage: AVAILABLE, UPLOAD_UNAVAILABLE, or SOURCE_MISSING")
    lineage_note: Optional[str] = Field(None, description="Auditable diagnostic note on this specific contributing stream")


class OccurrenceProvenanceResponse(BaseModel):
    """End-to-end provenance drill-down response for a specific finding occurrence."""
    finding_id: str
    occurrence_id: str
    occurrence_ts: str
    anomaly_type: str
    severity: str
    detector_name: Optional[str] = None
    detector_version: Optional[str] = None
    overall_lineage_state: str = Field(
        ...,
        description="Explicit lineage category: AVAILABLE, MULTI_SOURCE, LEGACY_UNLINKED, SOURCE_MISSING, or UPLOAD_UNAVAILABLE",
    )
    lineage_explanation: str = Field(..., description="Operational explanation of data lineage and traceability")
    is_multi_source: bool = Field(False, description="True if anomaly combines multiple distinct telemetry streams")
    source_records: List[SourceRecordDrillDownResponse] = Field(default_factory=list)
    retrieved_at: str

