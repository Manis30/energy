"""Pydantic schemas for Data Connectors, schema discovery, migration preparation, and sync history.

Strictly supports three connectors:
1. Neon PostgreSQL (Application Primary Database)
2. MongoDB (Document / Telemetry Store)
3. SharePoint (Microsoft Graph API / File Ingestion Source)
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ConnectorType(str, Enum):
    """Approved connector types."""
    NEON_POSTGRES = "neon_postgres"
    POSTGRESQL = "postgresql"
    FILE_UPLOAD = "file_upload"
    MONGODB = "mongodb"
    SHAREPOINT = "sharepoint"
    REST_API = "rest_api"
    SIEMENS_OPCENTER = "siemens_opcenter"
    SAP_ERP = "sap_erp"
    SAP_HANA = "sap_hana"
    ORACLE = "oracle"
    SNOWFLAKE = "snowflake"
    MS_TEAMS = "ms_teams"


class ConnectorMode(str, Enum):
    """Architectural connector execution mode."""
    LIVE_CAPABLE = "live_capable"
    FILE_BASED = "file_based"
    SIMULATED = "simulated"
    PLANNED = "planned"


class ConnectionState(str, Enum):
    """Active runtime connection state."""
    UNCONFIGURED = "unconfigured"
    CONFIGURED_UNVERIFIED = "configured_unverified"
    REACHABLE = "reachable"
    FAILED = "failed"


class ConnectorStatus(str, Enum):
    """Operational status of data connector."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    CONFIGURING = "configuring"
    SIMULATED = "simulated"


class ConnectorRole(str, Enum):
    """Role within platform architecture."""
    PRIMARY_SOURCE = "primary_source"
    SOURCE_DESTINATION = "source_destination"
    INGESTION_SOURCE = "ingestion_source"


class SyncStatus(str, Enum):
    """Status of synchronization or discovery jobs."""
    SUCCESS = "SUCCESS"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    WARNING = "WARNING"


# -------------------------------------------------------------------------
# Connector Configuration & Summary Schemas
# -------------------------------------------------------------------------

class ConnectorSummary(BaseModel):
    """Summary of a registered data connector with masked credentials."""
    id: str = Field(..., description="Unique connector identifier")
    name: str = Field(..., description="Human-readable connector name")
    type: ConnectorType = Field(..., description="Connector technology type")
    role: ConnectorRole = Field(..., description="Role in data architecture")
    description: str = Field(..., description="Connector purpose and details")
    status: ConnectorStatus = Field(..., description="Current connection status")
    mode: ConnectorMode = Field(ConnectorMode.PLANNED, description="Connector architectural mode: live_capable, file_based, simulated, planned")
    connection_state: ConnectionState = Field(ConnectionState.UNCONFIGURED, description="Runtime connection state: unconfigured, configured_unverified, reachable, failed")
    status_label: Optional[str] = Field(None, description="Truthful human-readable status badge")
    is_primary: bool = Field(False, description="True if this is the primary platform database")
    is_predefined: bool = Field(False, description="True if managed by platform configuration")
    is_simulation: bool = Field(False, description="True if mock fixture or sandbox simulation")
    is_operational_intake: bool = Field(False, description="True if actively used for platform operational intake")
    created_at: datetime = Field(..., description="Registration timestamp")
    last_tested_at: Optional[datetime] = Field(None, description="Last connectivity check timestamp")
    last_sync_at: Optional[datetime] = Field(None, description="Last sync or discovery timestamp")
    last_connectivity_check_at: Optional[datetime] = Field(None, description="Timestamp of most recent connectivity probe")
    last_successful_ingestion_at: Optional[datetime] = Field(None, description="Timestamp of most recent verified operational data ingestion")
    provider_details: Optional[Dict[str, Any]] = Field(None, description="Observed server provider, TLS, and version details")
    connection_info: Dict[str, Any] = Field(
        default_factory=dict,
        description="Public connection parameters with credentials strictly masked"
    )


class MongoDBConnectorCreate(BaseModel):
    """Payload for registering a new MongoDB connection."""
    name: str = Field(..., min_length=2, max_length=100, description="Display name for connector")
    uri: str = Field(..., min_length=10, description="MongoDB connection URI (mongodb:// or mongodb+srv://)")
    database_name: str = Field(..., min_length=1, max_length=100, description="Target database name")
    auth_database: Optional[str] = Field("admin", description="Authentication database")
    replica_set: Optional[str] = Field(None, description="Replica set name if applicable")
    ssl: bool = Field(True, description="Enable TLS/SSL encryption")


class MongoDBConnectorUpdate(BaseModel):
    """Payload for updating a MongoDB connection."""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    uri: Optional[str] = Field(None, min_length=10)
    database_name: Optional[str] = Field(None, min_length=1)
    auth_database: Optional[str] = None
    replica_set: Optional[str] = None
    ssl: Optional[bool] = None


class SharePointConnectorCreate(BaseModel):
    """Payload for connecting SharePoint using Microsoft Graph API OAuth credentials."""
    name: str = Field(..., min_length=2, max_length=100, description="Connector display name")
    tenant_id: str = Field(..., min_length=8, description="Azure AD / Entra ID Tenant ID")
    client_id: str = Field(..., min_length=8, description="Application (client) ID")
    client_secret: str = Field(..., min_length=4, description="Client Secret (never exposed back to UI)")
    site_url: str = Field(..., min_length=10, description="SharePoint Site URL (https://company.sharepoint.com/sites/...)")
    default_library: Optional[str] = Field("Energy & Production Reports", description="Default document library")


class SharePointConnectorUpdate(BaseModel):
    """Payload for updating SharePoint connector."""
    name: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    site_url: Optional[str] = None
    default_library: Optional[str] = None


# -------------------------------------------------------------------------
# Connection Testing & Diagnostics
# -------------------------------------------------------------------------

class ConnectionTestResult(BaseModel):
    """Result of active connectivity testing."""
    connector_id: str
    connector_name: str
    connector_type: ConnectorType
    success: bool
    status: ConnectorStatus
    mode: Optional[ConnectorMode] = None
    connection_state: Optional[ConnectionState] = None
    is_simulation: bool = False
    is_operational_intake: bool = False
    latency_ms: float = Field(..., description="Round-trip handshake latency in milliseconds")
    message: str = Field(..., description="Summary status message")
    last_connectivity_check_at: Optional[datetime] = None
    last_successful_ingestion_at: Optional[datetime] = None
    provider_details: Optional[Dict[str, Any]] = None
    diagnostics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed diagnostic metrics (DNS, TLS, Ping, Auth, Version)"
    )
    tested_at: datetime = Field(default_factory=datetime.utcnow)


# -------------------------------------------------------------------------
# Discovery Schemas (Schema, Table, Collection, File)
# -------------------------------------------------------------------------

class ColumnInfo(BaseModel):
    """Column metadata for relational tables."""
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    sample_value: Optional[str] = None


class TableInfo(BaseModel):
    """Table metadata for relational databases."""
    table_name: str
    schema_name: str = "public"
    row_count: int = 0
    columns: List[ColumnInfo] = Field(default_factory=list)


class FieldInfo(BaseModel):
    """Document field metadata for NoSQL collections."""
    field_name: str
    field_type: str
    is_indexed: bool = False
    sample_value: Optional[str] = None


class CollectionInfo(BaseModel):
    """Collection metadata for MongoDB."""
    collection_name: str
    database_name: str
    document_count: int = 0
    estimated_size_kb: float = 0.0
    fields: List[FieldInfo] = Field(default_factory=list)


class SharePointFileInfo(BaseModel):
    """File metadata for SharePoint document libraries."""
    file_id: str
    file_name: str
    file_extension: str
    size_bytes: int
    size_formatted: str
    modified_at: datetime
    library_name: str
    path: str
    is_supported: bool
    report_type_hint: Optional[str] = None


class SharePointLibraryInfo(BaseModel):
    """Document library in SharePoint."""
    library_id: str
    name: str
    item_count: int = 0
    web_url: Optional[str] = None


class SharePointSiteInfo(BaseModel):
    """Site info in SharePoint."""
    site_id: str
    site_name: str
    web_url: str


class ConnectorDiscoveryResult(BaseModel):
    """Unified schema/file discovery payload."""
    connector_id: str
    connector_name: str
    connector_type: ConnectorType
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Neon PostgreSQL specifics
    schemas: Optional[List[str]] = None
    tables: Optional[List[TableInfo]] = None
    
    # MongoDB specifics
    databases: Optional[List[str]] = None
    collections: Optional[List[CollectionInfo]] = None
    
    # SharePoint specifics
    sites: Optional[List[SharePointSiteInfo]] = None
    libraries: Optional[List[SharePointLibraryInfo]] = None
    files: Optional[List[SharePointFileInfo]] = None


# -------------------------------------------------------------------------
# Data Preview Schemas
# -------------------------------------------------------------------------

class DataPreviewResponse(BaseModel):
    """Preview sample records from a table, collection, or SharePoint file."""
    connector_id: str
    entity_name: str
    entity_type: str = Field(..., description="'table', 'collection', or 'file'")
    total_records: int
    columns: List[str]
    rows: List[Dict[str, Any]]
    validation_notes: Optional[List[str]] = None


# -------------------------------------------------------------------------
# Migration Preparation & Mapping Schemas
# -------------------------------------------------------------------------

class FieldMapping(BaseModel):
    """Single column/field mapping specification."""
    source_field: str
    source_type: str
    destination_field: str
    destination_type: str
    transformation: Optional[str] = "direct"


class FieldMappingStatus(BaseModel):
    """Compatibility evaluation of a field mapping."""
    source_field: str
    destination_field: str
    source_type: str
    destination_type: str
    compatible: bool
    incompatibility_reason: Optional[str] = None


class MigrationConflict(BaseModel):
    """Identified schema, type, or constraint conflict."""
    severity: str = Field(..., description="'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'")
    conflict_type: str
    message: str
    affected_fields: List[str] = Field(default_factory=list)
    recommendation: str


class MigrationPlanRequest(BaseModel):
    """Request to generate and preview a migration plan."""
    source_connector_id: str
    destination_connector_id: str
    source_entity: str
    destination_entity: str
    field_mappings: List[FieldMapping]


class MigrationPreviewResponse(BaseModel):
    """Preview of migration plan with conflict analysis and strict execution gate."""
    plan_id: str
    source_connector_id: str
    source_connector_name: str
    destination_connector_id: str
    destination_connector_name: str
    source_entity: str
    destination_entity: str
    total_source_records: int
    field_mappings: List[FieldMappingStatus]
    incompatible_types_count: int
    conflicts: List[MigrationConflict]
    approval_status: str = Field("APPROVAL_GATED", description="Guarded status requiring explicit administrative release")
    execution_gated: bool = Field(True, description="Always True; prevents automatic or destructive data transfers")
    execution_notice: str = Field(
        "Bulk migration execution is strictly gated and deferred to a future task. Neon PostgreSQL remains the active primary database.",
        description="Safety boundary notice"
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# -------------------------------------------------------------------------
# SharePoint Ingestion Staging
# -------------------------------------------------------------------------

class SharePointIngestionPrepareRequest(BaseModel):
    """Request to prepare a SharePoint file for platform ingestion."""
    connector_id: str
    file_id: str
    target_pipeline: str = Field("daily_reports", description="Target platform pipeline: daily_reports, hourly_energy, hourly_production")


class SharePointIngestionPrepareResponse(BaseModel):
    """Result of staging SharePoint file for pipeline ingestion."""
    staging_id: str
    file_id: str
    file_name: str
    status: str = Field("STAGED_FOR_PIPELINE", description="Staging status")
    detected_pipeline: str
    validated_rows: int
    columns_matched: List[str]
    message: str
    staged_at: datetime = Field(default_factory=datetime.utcnow)


# -------------------------------------------------------------------------
# Synchronization History Schemas
# -------------------------------------------------------------------------

class SyncHistoryItem(BaseModel):
    """Historical record of connector synchronization, discovery, or test operation."""
    id: str
    connector_id: str
    connector_name: str
    connector_type: ConnectorType
    sync_type: str = Field(..., description="SCHEMA_DISCOVERY, FILE_SCAN, CONNECTIVITY_TEST, INGESTION_STAGING, MIGRATION_PREVIEW")
    status: SyncStatus
    items_processed: int = 0
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    error_details: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class SyncHistoryResponse(BaseModel):
    """List of sync history events."""
    items: List[SyncHistoryItem]
    total: int

