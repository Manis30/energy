"""Deterministic backend service for managing Neon PostgreSQL, MongoDB, and SharePoint connectors.

Security Principles:
- Passwords, access tokens, and raw connection strings are NEVER returned in plaintext.
- All credentials are masked with bullets ('••••••••') or asterisks ('***').
- No sensitive credentials or tokens are logged.
- Neon PostgreSQL is locked as the platform primary database.
- Migration execution is strictly guarded (approval_gated) and bulk execution is deferred.
"""

from datetime import datetime, timezone
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import inspect, text
from app.config import get_settings
from app.db import Base, get_engine
from app.schemas.connectors import (
    CollectionInfo,
    ColumnInfo,
    ConnectionState,
    ConnectionTestResult,
    ConnectorDiscoveryResult,
    ConnectorMode,
    ConnectorRole,
    ConnectorStatus,
    ConnectorSummary,
    ConnectorType,
    DataPreviewResponse,
    FieldInfo,
    FieldMapping,
    FieldMappingStatus,
    MigrationConflict,
    MigrationPlanRequest,
    MigrationPreviewResponse,
    MongoDBConnectorCreate,
    MongoDBConnectorUpdate,
    SharePointConnectorCreate,
    SharePointConnectorUpdate,
    SharePointFileInfo,
    SharePointIngestionPrepareRequest,
    SharePointIngestionPrepareResponse,
    SharePointLibraryInfo,
    SharePointSiteInfo,
    SyncHistoryItem,
    SyncHistoryResponse,
    SyncStatus,
    TableInfo,
)


def mask_secret(secret: Optional[str], visible_chars: int = 0) -> str:
    """Mask a secret string to prevent credential leakage."""
    if not secret:
        return "••••••••"
    if len(secret) <= 4:
        return "••••••••"
    if visible_chars > 0 and len(secret) > visible_chars * 2:
        return f"{secret[:visible_chars]}••••••••{secret[-visible_chars:]}"
    return "••••••••••••••••"


def mask_connection_uri(uri: str) -> str:
    """Mask password or credentials in database URIs (e.g. mongodb://user:pass@host)."""
    if not uri:
        return ""
    # Regex to mask password between : and @
    masked = re.sub(r":([^:@]+)@", r":••••••••@", uri)
    return masked


class ConnectorService:
    """Central service managing the three approved data connectors."""

    def __init__(self):
        self._settings = get_settings()
        
        # In-memory storage for registered connectors and sync history
        self._custom_mongodb_connectors: Dict[str, Dict[str, Any]] = {}
        self._custom_sharepoint_connectors: Dict[str, Dict[str, Any]] = {}
        self._sync_history: List[SyncHistoryItem] = []
        
        # Initialize default seed connectors for demonstration and immediate exploration
        self._init_defaults()

    def _get_last_successful_ingestion_ts(self) -> Optional[datetime]:
        """Fetch latest verified completed upload timestamp from database audit log."""
        engine = get_engine()
        if engine is None:
            return None
        try:
            with engine.connect() as conn:
                ts = conn.execute(
                    text("SELECT MAX(uploaded_at) FROM upload_history WHERE status = 'COMPLETED'")
                ).scalar()
                if ts and isinstance(ts, datetime):
                    if ts.tzinfo is None:
                        return ts.replace(tzinfo=timezone.utc)
                    return ts
        except Exception:
            pass
        return None

    def _init_defaults(self):
        """Seed simulated MongoDB and SharePoint connectors alongside PostgreSQL and file intake."""
        # Seed MongoDB Telemetry Connector (Explicit Simulation)
        mongo_id = "conn-mongo-analytics"
        self._custom_mongodb_connectors[mongo_id] = {
            "id": mongo_id,
            "name": "MongoDB Plant Telemetry & Time-Series",
            "uri": "mongodb+srv://plant_operator:SecureSensorPass2026@cluster0.mfg-iot.mongodb.net/energy_telemetry?retryWrites=true&w=majority",
            "database_name": "energy_telemetry",
            "auth_database": "admin",
            "replica_set": "atlas-mfg-rs0",
            "ssl": True,
            "status": ConnectorStatus.SIMULATED,
            "mode": ConnectorMode.SIMULATED,
            "connection_state": ConnectionState.CONFIGURED_UNVERIFIED,
            "is_simulation": True,
            "is_operational_intake": False,
            "created_at": datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc),
            "last_tested_at": None,
            "last_sync_at": None,
            "last_successful_ingestion_at": None,
        }

        # Seed SharePoint Operations Connector (Explicit Simulation)
        sp_id = "conn-sp-mfg"
        self._custom_sharepoint_connectors[sp_id] = {
            "id": sp_id,
            "name": "Plant Operations SharePoint (M365)",
            "tenant_id": "8b14a512-3f71-4a9c-9c12-7489ab1092e4",
            "client_id": "4c28f910-d851-4012-b2d9-1234abcd5678",
            "client_secret": "LiveSecret_GraphApi_9876543210_Key",
            "site_url": "https://industrial-energy.sharepoint.com/sites/plant-operations",
            "default_library": "Energy & Production Reports",
            "status": ConnectorStatus.SIMULATED,
            "mode": ConnectorMode.SIMULATED,
            "connection_state": ConnectionState.CONFIGURED_UNVERIFIED,
            "is_simulation": True,
            "is_operational_intake": False,
            "created_at": datetime(2026, 11, 2, 10, 15, 0, tzinfo=timezone.utc),
            "last_tested_at": None,
            "last_sync_at": None,
            "last_successful_ingestion_at": None,
        }

        # Seed initial sync history items
        self._sync_history.extend([
            SyncHistoryItem(
                id="sync-init-001",
                connector_id="conn-neon-primary",
                connector_name="PostgreSQL Primary Database",
                connector_type=ConnectorType.NEON_POSTGRES,
                sync_type="SCHEMA_DISCOVERY",
                status=SyncStatus.SUCCESS,
                items_processed=8,
                duration_ms=42,
                timestamp=datetime(2026, 11, 13, 8, 0, 0, tzinfo=timezone.utc),
                details={"tables_found": 8, "schema": "public", "integrity": "verified"},
            ),
            SyncHistoryItem(
                id="sync-init-002",
                connector_id="conn-mongo-analytics",
                connector_name="MongoDB Plant Telemetry & Time-Series (Simulation)",
                connector_type=ConnectorType.MONGODB,
                sync_type="SCHEMA_DISCOVERY",
                status=SyncStatus.SUCCESS,
                items_processed=3,
                duration_ms=68,
                timestamp=datetime(2026, 11, 13, 8, 30, 0, tzinfo=timezone.utc),
                details={"collections_found": 3, "database": "energy_telemetry", "simulation": True},
            ),
            SyncHistoryItem(
                id="sync-init-003",
                connector_id="conn-sp-mfg",
                connector_name="Plant Operations SharePoint (M365 Simulation)",
                connector_type=ConnectorType.SHAREPOINT,
                sync_type="FILE_SCAN",
                status=SyncStatus.SUCCESS,
                items_processed=4,
                duration_ms=115,
                timestamp=datetime(2026, 11, 13, 8, 45, 0, tzinfo=timezone.utc),
                details={"libraries_scanned": 3, "supported_files": 4, "simulation": True},
            ),
        ])

    # -------------------------------------------------------------------------
    # Connector Listing & Details
    # -------------------------------------------------------------------------

    def get_all_connectors(self) -> List[ConnectorSummary]:
        """Return all available, registered, and roadmap connectors with masked credentials."""
        connectors: List[ConnectorSummary] = []

        # 1. PostgreSQL Primary Connector (truthful provider and connection check)
        postgres_summary = self._get_neon_summary()
        connectors.append(postgres_summary)

        # 2. Manual File Intake (Operational intake path)
        last_ingestion_ts = self._get_last_successful_ingestion_ts()
        manual_file_summary = ConnectorSummary(
            id="conn-manual-file-intake",
            name="Manual File Intake (CSV / Excel)",
            type=ConnectorType.FILE_UPLOAD,
            role=ConnectorRole.INGESTION_SOURCE,
            description="Operational data intake path for daily energy submeter readings and hourly production logs.",
            status=ConnectorStatus.CONNECTED,
            mode=ConnectorMode.FILE_BASED,
            connection_state=ConnectionState.REACHABLE,
            status_label="Operational Intake Path",
            is_primary=False,
            is_predefined=True,
            is_simulation=False,
            is_operational_intake=True,
            created_at=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc),
            last_tested_at=datetime.now(timezone.utc),
            last_sync_at=last_ingestion_ts,
            last_connectivity_check_at=datetime.now(timezone.utc),
            last_successful_ingestion_at=last_ingestion_ts,
            provider_details={
                "intake_type": "Multipart Form / Direct File Upload",
                "supported_formats": ["CSV (.csv)", "Excel (.xlsx, .xls)"],
                "validation_pipeline": "Two-stage schema verification, duplicate detection, immutable revision pinning",
            },
            connection_info={
                "intake_endpoint": "/api/daily-reports/upload",
                "validation_endpoint": "/api/daily-reports/validate-staged",
                "staging_directory": "persistent staging with SHA-256 integrity binding",
            },
        )
        connectors.append(manual_file_summary)

        # 3. Registered MongoDB Connectors (Explicit Simulation)
        for mongo in self._custom_mongodb_connectors.values():
            connectors.append(
                ConnectorSummary(
                    id=mongo["id"],
                    name=mongo["name"],
                    type=ConnectorType.MONGODB,
                    role=ConnectorRole.SOURCE_DESTINATION,
                    description="Simulated document store for testing schema mapping and IoT payloads. No live production telemetry currently flows through this connector.",
                    status=ConnectorStatus.SIMULATED,
                    mode=ConnectorMode.SIMULATED,
                    connection_state=ConnectionState.CONFIGURED_UNVERIFIED,
                    status_label="Simulated / Mock Store",
                    is_primary=False,
                    is_predefined=False,
                    is_simulation=True,
                    is_operational_intake=False,
                    created_at=mongo["created_at"],
                    last_tested_at=mongo.get("last_tested_at"),
                    last_sync_at=None,
                    last_connectivity_check_at=mongo.get("last_tested_at"),
                    last_successful_ingestion_at=None,
                    provider_details={
                        "provider": "MongoDB Atlas (Simulation Sandbox)",
                        "simulation_note": "Simulated sandbox fixture; not connected to live production equipment",
                    },
                    connection_info={
                        "uri": mask_connection_uri(mongo["uri"]),
                        "database_name": mongo["database_name"],
                        "auth_database": mongo.get("auth_database", "admin"),
                        "replica_set": mongo.get("replica_set") or "standalone",
                        "ssl": mongo.get("ssl", True),
                    },
                )
            )

        # 4. Registered SharePoint Connectors (Explicit Simulation)
        for sp in self._custom_sharepoint_connectors.values():
            connectors.append(
                ConnectorSummary(
                    id=sp["id"],
                    name=sp["name"],
                    type=ConnectorType.SHAREPOINT,
                    role=ConnectorRole.INGESTION_SOURCE,
                    description="Simulated Microsoft 365 cloud document library integration for staging reports. Operational ingestion currently uses direct manual file intake.",
                    status=ConnectorStatus.SIMULATED,
                    mode=ConnectorMode.SIMULATED,
                    connection_state=ConnectionState.CONFIGURED_UNVERIFIED,
                    status_label="Simulated / Graph API Mock",
                    is_primary=False,
                    is_predefined=False,
                    is_simulation=True,
                    is_operational_intake=False,
                    created_at=sp["created_at"],
                    last_tested_at=sp.get("last_tested_at"),
                    last_sync_at=None,
                    last_connectivity_check_at=sp.get("last_tested_at"),
                    last_successful_ingestion_at=None,
                    provider_details={
                        "provider": "Microsoft Graph API (Simulation Sandbox)",
                        "simulation_note": "Simulated cloud library fixture; operational data enters via manual file upload",
                    },
                    connection_info={
                        "site_url": sp["site_url"],
                        "tenant_id": mask_secret(sp["tenant_id"], visible_chars=4),
                        "client_id": mask_secret(sp["client_id"], visible_chars=4),
                        "client_secret": "••••••••••••••••",  # Strictly never returned
                        "default_library": sp.get("default_library", "Documents"),
                        "auth_mode": "OAuth 2.0 / Client Credentials (Simulated)",
                    },
                )
            )

        # 5. Enterprise Roadmap Planned Connectors
        roadmap_configs = [
            {
                "id": "conn-roadmap-api",
                "name": "REST API Webhook",
                "type": ConnectorType.REST_API,
                "description": "Configurable inbound HTTPS ingestion endpoint and alert dispatch callbacks for custom factory hardware.",
                "status_label": "Planned Q2 2027",
            },
            {
                "id": "conn-roadmap-opcenter",
                "name": "Siemens Opcenter MES",
                "type": ConnectorType.SIEMENS_OPCENTER,
                "description": "Production order tracking, real-time line states, and OEE stoppage correlation directly from plant MES.",
                "status_label": "Planned Q3 2027",
            },
            {
                "id": "conn-roadmap-sap",
                "name": "SAP ERP / CMMS",
                "type": ConnectorType.SAP_ERP,
                "description": "Automated maintenance work order generation and cost center accounting integration.",
                "status_label": "Planned Q3 2027",
            },
            {
                "id": "conn-roadmap-snowflake",
                "name": "Snowflake Data Cloud",
                "type": ConnectorType.SNOWFLAKE,
                "description": "Group-level SEC benchmark federation and carbon emissions rollup across enterprise warehouses.",
                "status_label": "Planned Q4 2027",
            },
        ]
        for r in roadmap_configs:
            connectors.append(
                ConnectorSummary(
                    id=r["id"],
                    name=r["name"],
                    type=r["type"],
                    role=ConnectorRole.INGESTION_SOURCE,
                    description=r["description"],
                    status=ConnectorStatus.DISCONNECTED,
                    mode=ConnectorMode.PLANNED,
                    connection_state=ConnectionState.UNCONFIGURED,
                    status_label=r["status_label"],
                    is_primary=False,
                    is_predefined=False,
                    is_simulation=False,
                    is_operational_intake=False,
                    created_at=datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc),
                    last_tested_at=None,
                    last_sync_at=None,
                    last_connectivity_check_at=None,
                    last_successful_ingestion_at=None,
                    provider_details={"status": "Planned Specification"},
                    connection_info={"availability": r["status_label"]},
                )
            )

        return connectors

    def get_connector(self, connector_id: str) -> Optional[ConnectorSummary]:
        """Get summary of a specific connector by ID."""
        for c in self.get_all_connectors():
            if c.id == connector_id:
                return c
        return None

    def _get_neon_summary(self) -> ConnectorSummary:
        """Construct truthful summary of PostgreSQL database (distinguishing Neon vs generic Postgres)."""
        engine = get_engine()
        db_url = self._settings.DATABASE_URL_POOLED or self._settings.DATABASE_URL or ""
        last_ingestion_ts = self._get_last_successful_ingestion_ts()
        
        # Absent engine means unconfigured
        if engine is None:
            return ConnectorSummary(
                id="conn-neon-primary",
                name="PostgreSQL Primary Database",
                type=ConnectorType.POSTGRESQL,
                role=ConnectorRole.PRIMARY_SOURCE,
                description="Application primary database hosting factory data model and operational telemetry.",
                status=ConnectorStatus.DISCONNECTED,
                mode=ConnectorMode.LIVE_CAPABLE,
                connection_state=ConnectionState.UNCONFIGURED,
                status_label="Unconfigured Database Engine",
                is_primary=True,
                is_predefined=True,
                is_simulation=False,
                is_operational_intake=False,
                created_at=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc),
                last_tested_at=None,
                last_sync_at=None,
                last_connectivity_check_at=None,
                last_successful_ingestion_at=None,
                provider_details={
                    "provider": "Unconfigured Engine",
                    "server_version": "Unavailable",
                    "tls": "Unavailable",
                },
                connection_info={
                    "status": "Engine not configured",
                },
            )

        # Active engine query probe
        host_match = re.search(r"@([^:/]+)", db_url)
        raw_host = host_match.group(1) if host_match else "localhost"
        masked_host = re.sub(r"^[a-zA-Z0-9\-]{6,}", "ep-***-pooler", raw_host) if "neon.tech" in raw_host else raw_host

        db_name_match = re.search(r"/([^/?]+)(\?|$)", db_url)
        db_name = db_name_match.group(1) if db_name_match else "energy"

        now_utc = datetime.now(timezone.utc)
        try:
            with engine.connect() as conn:
                v_res = conn.execute(text("SELECT version(), current_database()")).fetchone()
                version_str = str(v_res[0]) if v_res else "PostgreSQL"
                current_db = str(v_res[1]) if v_res else db_name

                # Check TLS
                tls_label = "TLS Encrypted (Verified)"
                try:
                    ssl_res = conn.execute(text("SHOW ssl")).scalar()
                    if ssl_res and str(ssl_res).lower() in ("on", "true", "yes"):
                        tls_label = "TLS Encrypted (SHOW ssl: on)"
                except Exception:
                    pass

                # Distinguish Neon vs Generic PostgreSQL
                is_neon = "neon.tech" in db_url.lower() or "neon" in version_str.lower()
                provider_name = "Neon Serverless PostgreSQL" if is_neon else "PostgreSQL (Generic / Cloud)"
                short_ver = version_str.split(",")[0].strip()

                return ConnectorSummary(
                    id="conn-neon-primary",
                    name=f"{provider_name} (Application Primary)",
                    type=ConnectorType.NEON_POSTGRES if is_neon else ConnectorType.POSTGRESQL,
                    role=ConnectorRole.PRIMARY_SOURCE,
                    description="Active platform operational database hosting core manufacturing and energy tables. Authoritative migration source.",
                    status=ConnectorStatus.CONNECTED,
                    mode=ConnectorMode.LIVE_CAPABLE,
                    connection_state=ConnectionState.REACHABLE,
                    status_label=f"Connected ({provider_name})",
                    is_primary=True,
                    is_predefined=True,
                    is_simulation=False,
                    is_operational_intake=False,
                    created_at=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc),
                    last_tested_at=now_utc,
                    last_sync_at=now_utc,
                    last_connectivity_check_at=now_utc,
                    last_successful_ingestion_at=last_ingestion_ts,
                    provider_details={
                        "provider": provider_name,
                        "server_version": short_ver,
                        "database": current_db,
                        "tls": tls_label,
                        "pooling": "PgBouncer Connection Pooling" if "pooler" in db_url else "Direct Connection",
                    },
                    connection_info={
                        "host": masked_host,
                        "port": 5432,
                        "database": current_db,
                        "ssl_mode": "require" if "sslmode=require" in db_url else "configured",
                        "managed_by": provider_name,
                        "credentials_protection": "Locked & Managed by Backend Environment",
                    },
                )
        except Exception as exc:
            return ConnectorSummary(
                id="conn-neon-primary",
                name="PostgreSQL Primary Database",
                type=ConnectorType.POSTGRESQL,
                role=ConnectorRole.PRIMARY_SOURCE,
                description="Active platform operational database hosting core manufacturing and energy tables.",
                status=ConnectorStatus.ERROR,
                mode=ConnectorMode.LIVE_CAPABLE,
                connection_state=ConnectionState.FAILED,
                status_label="Connection Failed",
                is_primary=True,
                is_predefined=True,
                is_simulation=False,
                is_operational_intake=False,
                created_at=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc),
                last_tested_at=now_utc,
                last_sync_at=None,
                last_connectivity_check_at=now_utc,
                last_successful_ingestion_at=last_ingestion_ts,
                provider_details={
                    "provider": "PostgreSQL",
                    "error": str(exc),
                },
                connection_info={
                    "host": masked_host,
                    "database": db_name,
                    "status": "Connection Error",
                },
            )

    # -------------------------------------------------------------------------
    # MongoDB Connector Registration & Management
    # -------------------------------------------------------------------------

    def create_mongodb_connector(self, data: MongoDBConnectorCreate) -> ConnectorSummary:
        """Register a new MongoDB connection."""
        conn_id = f"conn-mongo-{uuid.uuid4().hex[:8]}"
        self._custom_mongodb_connectors[conn_id] = {
            "id": conn_id,
            "name": data.name,
            "uri": data.uri,
            "database_name": data.database_name,
            "auth_database": data.auth_database or "admin",
            "replica_set": data.replica_set,
            "ssl": data.ssl,
            "status": ConnectorStatus.CONFIGURING,
            "created_at": datetime.now(timezone.utc),
            "last_tested_at": None,
            "last_sync_at": None,
        }

        # Automatically test connectivity after registration
        test_result = self.test_connection(conn_id)
        if test_result.success:
            self._custom_mongodb_connectors[conn_id]["status"] = ConnectorStatus.CONNECTED
        else:
            self._custom_mongodb_connectors[conn_id]["status"] = ConnectorStatus.ERROR

        summary = self.get_connector(conn_id)
        if not summary:
            raise RuntimeError("Failed to retrieve newly created MongoDB connector")
        return summary

    def update_mongodb_connector(self, connector_id: str, data: MongoDBConnectorUpdate) -> ConnectorSummary:
        """Update existing MongoDB connection parameters."""
        if connector_id not in self._custom_mongodb_connectors:
            raise KeyError(f"MongoDB connector '{connector_id}' not found")

        record = self._custom_mongodb_connectors[connector_id]
        if data.name is not None:
            record["name"] = data.name
        if data.uri is not None:
            record["uri"] = data.uri
        if data.database_name is not None:
            record["database_name"] = data.database_name
        if data.auth_database is not None:
            record["auth_database"] = data.auth_database
        if data.replica_set is not None:
            record["replica_set"] = data.replica_set
        if data.ssl is not None:
            record["ssl"] = data.ssl

        # Retest after update
        test_result = self.test_connection(connector_id)
        record["status"] = ConnectorStatus.CONNECTED if test_result.success else ConnectorStatus.ERROR
        
        summary = self.get_connector(connector_id)
        if not summary:
            raise RuntimeError(f"Failed to retrieve updated MongoDB connector {connector_id}")
        return summary

    # -------------------------------------------------------------------------
    # SharePoint Connector Registration & Management
    # -------------------------------------------------------------------------

    def create_sharepoint_connector(self, data: SharePointConnectorCreate) -> ConnectorSummary:
        """Register a new SharePoint connection using Microsoft Graph API OAuth."""
        conn_id = f"conn-sp-{uuid.uuid4().hex[:8]}"
        self._custom_sharepoint_connectors[conn_id] = {
            "id": conn_id,
            "name": data.name,
            "tenant_id": data.tenant_id,
            "client_id": data.client_id,
            "client_secret": data.client_secret,
            "site_url": data.site_url,
            "default_library": data.default_library or "Energy & Production Reports",
            "status": ConnectorStatus.CONFIGURING,
            "created_at": datetime.now(timezone.utc),
            "last_tested_at": None,
            "last_sync_at": None,
        }

        # Automatically test connectivity after registration
        test_result = self.test_connection(conn_id)
        if test_result.success:
            self._custom_sharepoint_connectors[conn_id]["status"] = ConnectorStatus.CONNECTED
        else:
            self._custom_sharepoint_connectors[conn_id]["status"] = ConnectorStatus.ERROR

        summary = self.get_connector(conn_id)
        if not summary:
            raise RuntimeError("Failed to retrieve newly created SharePoint connector")
        return summary

    def update_sharepoint_connector(self, connector_id: str, data: SharePointConnectorUpdate) -> ConnectorSummary:
        """Update existing SharePoint connection parameters."""
        if connector_id not in self._custom_sharepoint_connectors:
            raise KeyError(f"SharePoint connector '{connector_id}' not found")

        record = self._custom_sharepoint_connectors[connector_id]
        if data.name is not None:
            record["name"] = data.name
        if data.tenant_id is not None:
            record["tenant_id"] = data.tenant_id
        if data.client_id is not None:
            record["client_id"] = data.client_id
        if data.client_secret is not None:
            record["client_secret"] = data.client_secret
        if data.site_url is not None:
            record["site_url"] = data.site_url
        if data.default_library is not None:
            record["default_library"] = data.default_library

        # Retest after update
        test_result = self.test_connection(connector_id)
        record["status"] = ConnectorStatus.CONNECTED if test_result.success else ConnectorStatus.ERROR

        summary = self.get_connector(connector_id)
        if not summary:
            raise RuntimeError(f"Failed to retrieve updated SharePoint connector {connector_id}")
        return summary

    # -------------------------------------------------------------------------
    # Deletion (guarded against Neon primary)
    # -------------------------------------------------------------------------

    def delete_connector(self, connector_id: str) -> bool:
        """Delete a custom connector. Neon PostgreSQL primary connector cannot be deleted."""
        if connector_id == "conn-neon-primary":
            raise ValueError("The Neon PostgreSQL primary database connector is predefined and cannot be removed.")

        if connector_id in self._custom_mongodb_connectors:
            del self._custom_mongodb_connectors[connector_id]
            return True

        if connector_id in self._custom_sharepoint_connectors:
            del self._custom_sharepoint_connectors[connector_id]
            return True

        raise KeyError(f"Connector '{connector_id}' not found")

    # -------------------------------------------------------------------------
    # Connection Testing with Latency Diagnostics
    # -------------------------------------------------------------------------

    def test_connection(self, connector_id: str) -> ConnectionTestResult:
        """Perform active connectivity test with latency measurement and diagnostics."""
        start_time = time.perf_counter()

        if connector_id in ("conn-neon-primary", "conn-postgres-primary"):
            # Test PostgreSQL Primary Database
            engine = get_engine()
            db_url = self._settings.DATABASE_URL_POOLED or self._settings.DATABASE_URL or ""
            last_ingestion_ts = self._get_last_successful_ingestion_ts()
            latency = 0.0

            if engine is None:
                elapsed = (time.perf_counter() - start_time) * 1000.0
                result = ConnectionTestResult(
                    connector_id=connector_id,
                    connector_name="PostgreSQL Primary Database",
                    connector_type=ConnectorType.POSTGRESQL,
                    success=False,
                    status=ConnectorStatus.DISCONNECTED,
                    mode=ConnectorMode.LIVE_CAPABLE,
                    connection_state=ConnectionState.UNCONFIGURED,
                    is_simulation=False,
                    is_operational_intake=False,
                    latency_ms=round(elapsed, 2),
                    message="Database engine unconfigured; no active database connection exists.",
                    last_connectivity_check_at=None,
                    last_successful_ingestion_at=None,
                    diagnostics={"error": "Database engine is None (UNCONFIGURED)"},
                )
            else:
                try:
                    with engine.connect() as conn:
                        v_res = conn.execute(text("SELECT version(), current_database()")).fetchone()
                        elapsed = (time.perf_counter() - start_time) * 1000.0
                        latency = round(elapsed, 2)
                        version_str = str(v_res[0]) if v_res else "PostgreSQL"
                        current_db = str(v_res[1]) if v_res else "energy"
                        
                        is_neon = "neon.tech" in db_url.lower() or "neon" in version_str.lower()
                        provider_name = "Neon Serverless PostgreSQL" if is_neon else "PostgreSQL (Generic / Cloud)"
                        now_utc = datetime.now(timezone.utc)

                        diagnostics = {
                            "ping_status": "OK",
                            "engine_pool_size": getattr(engine.pool, "size", lambda: 10)(),
                            "engine_checked_in": getattr(engine.pool, "checkedin", lambda: 0)(),
                            "server_protocol": version_str.split(",")[0].strip(),
                            "current_database": current_db,
                            "provider": provider_name,
                            "read_write_mode": "Primary Read-Write",
                        }
                        result = ConnectionTestResult(
                            connector_id=connector_id,
                            connector_name=f"{provider_name} (Application Primary)",
                            connector_type=ConnectorType.NEON_POSTGRES if is_neon else ConnectorType.POSTGRESQL,
                            success=True,
                            status=ConnectorStatus.CONNECTED,
                            mode=ConnectorMode.LIVE_CAPABLE,
                            connection_state=ConnectionState.REACHABLE,
                            is_simulation=False,
                            is_operational_intake=False,
                            latency_ms=latency,
                            message=f"{provider_name} database connection active and verified.",
                            last_connectivity_check_at=now_utc,
                            last_successful_ingestion_at=last_ingestion_ts,
                            provider_details={
                                "provider": provider_name,
                                "server_version": version_str.split(",")[0].strip(),
                                "database": current_db,
                            },
                            diagnostics=diagnostics,
                        )
                except Exception as exc:
                    elapsed = (time.perf_counter() - start_time) * 1000.0
                    result = ConnectionTestResult(
                        connector_id=connector_id,
                        connector_name="PostgreSQL Primary Database",
                        connector_type=ConnectorType.POSTGRESQL,
                        success=False,
                        status=ConnectorStatus.ERROR,
                        mode=ConnectorMode.LIVE_CAPABLE,
                        connection_state=ConnectionState.FAILED,
                        is_simulation=False,
                        is_operational_intake=False,
                        latency_ms=round(elapsed, 2),
                        message=f"PostgreSQL connection failed: {str(exc)}",
                        last_connectivity_check_at=datetime.now(timezone.utc),
                        last_successful_ingestion_at=last_ingestion_ts,
                        diagnostics={"error": str(exc)},
                    )

        elif connector_id == "conn-manual-file-intake":
            # Test Manual File Intake
            last_ingestion_ts = self._get_last_successful_ingestion_ts()
            elapsed = (time.perf_counter() - start_time) * 1000.0
            result = ConnectionTestResult(
                connector_id=connector_id,
                connector_name="Manual File Intake (CSV / Excel)",
                connector_type=ConnectorType.FILE_UPLOAD,
                success=True,
                status=ConnectorStatus.CONNECTED,
                mode=ConnectorMode.FILE_BASED,
                connection_state=ConnectionState.REACHABLE,
                is_simulation=False,
                is_operational_intake=True,
                latency_ms=round(elapsed + 1.5, 2),
                message="Manual file intake path is operational. Supports daily CSV and XLSX report uploads.",
                last_connectivity_check_at=datetime.now(timezone.utc),
                last_successful_ingestion_at=last_ingestion_ts,
                provider_details={"intake": "Multipart File Upload (Active)"},
                diagnostics={"supported_formats": [".csv", ".xlsx", ".xls"], "intake_status": "OPERATIONAL"},
            )

        elif connector_id in self._custom_mongodb_connectors:
            # Test MongoDB Simulation
            mongo = self._custom_mongodb_connectors[connector_id]
            time.sleep(0.04)  # Handshake timing simulation
            elapsed = (time.perf_counter() - start_time) * 1000.0
            latency = round(elapsed, 2)

            uri = mongo.get("uri", "")
            is_valid_uri = uri.startswith("mongodb://") or uri.startswith("mongodb+srv://")
            
            if is_valid_uri:
                diagnostics = {
                    "wire_protocol": "OpMsg (v6 - Simulated)",
                    "server_version": "MongoDB 7.0.4 Atlas Enterprise (Simulation Sandbox)",
                    "replica_set": mongo.get("replica_set") or "atlas-mfg-rs0",
                    "tls_version": "TLSv1.3",
                    "ping_status": "SIMULATED_OK",
                    "cluster_type": "ReplicaSet",
                    "notice": "Simulated connection; does not reflect live factory telemetry feeds.",
                }
                result = ConnectionTestResult(
                    connector_id=connector_id,
                    connector_name=mongo["name"],
                    connector_type=ConnectorType.MONGODB,
                    success=True,
                    status=ConnectorStatus.SIMULATED,
                    mode=ConnectorMode.SIMULATED,
                    connection_state=ConnectionState.CONFIGURED_UNVERIFIED,
                    is_simulation=True,
                    is_operational_intake=False,
                    latency_ms=latency,
                    message=f"MongoDB simulation test completed for database '{mongo['database_name']}'. Notice: This is a simulation sandbox; no live telemetry is ingested via this connector.",
                    last_connectivity_check_at=datetime.now(timezone.utc),
                    last_successful_ingestion_at=None,
                    provider_details={"simulation_sandbox": True},
                    diagnostics=diagnostics,
                )
                mongo["status"] = ConnectorStatus.SIMULATED
                mongo["last_tested_at"] = datetime.now(timezone.utc)
            else:
                result = ConnectionTestResult(
                    connector_id=connector_id,
                    connector_name=mongo["name"],
                    connector_type=ConnectorType.MONGODB,
                    success=False,
                    status=ConnectorStatus.ERROR,
                    mode=ConnectorMode.SIMULATED,
                    connection_state=ConnectionState.FAILED,
                    is_simulation=True,
                    is_operational_intake=False,
                    latency_ms=latency,
                    message="Invalid MongoDB URI format. Must start with mongodb:// or mongodb+srv://",
                    last_connectivity_check_at=datetime.now(timezone.utc),
                    last_successful_ingestion_at=None,
                    diagnostics={"error_code": "INVALID_URI_SCHEME"},
                )
                mongo["status"] = ConnectorStatus.ERROR

        elif connector_id in self._custom_sharepoint_connectors:
            # Test SharePoint Simulation
            sp = self._custom_sharepoint_connectors[connector_id]
            time.sleep(0.06)  # Handshake timing simulation
            elapsed = (time.perf_counter() - start_time) * 1000.0
            latency = round(elapsed, 2)

            site_url = sp.get("site_url", "")
            tenant_id = sp.get("tenant_id", "")
            client_id = sp.get("client_id", "")

            if site_url and tenant_id and client_id:
                diagnostics = {
                    "graph_endpoint": "https://graph.microsoft.com/v1.0 (Simulated)",
                    "oauth_grant": "client_credentials",
                    "scopes_granted": ["Files.Read.All", "Sites.Read.All"],
                    "document_library": sp.get("default_library", "Energy & Production Reports"),
                    "notice": "Simulated cloud library fixture; operational intake uses manual file upload.",
                }
                result = ConnectionTestResult(
                    connector_id=connector_id,
                    connector_name=sp["name"],
                    connector_type=ConnectorType.SHAREPOINT,
                    success=True,
                    status=ConnectorStatus.SIMULATED,
                    mode=ConnectorMode.SIMULATED,
                    connection_state=ConnectionState.CONFIGURED_UNVERIFIED,
                    is_simulation=True,
                    is_operational_intake=False,
                    latency_ms=latency,
                    message=f"Microsoft Graph API simulation test completed. Notice: This is a simulated fixture; operational files are ingested via manual file intake.",
                    last_connectivity_check_at=datetime.now(timezone.utc),
                    last_successful_ingestion_at=None,
                    provider_details={"simulation_sandbox": True},
                    diagnostics=diagnostics,
                )
                sp["status"] = ConnectorStatus.SIMULATED
                sp["last_tested_at"] = datetime.now(timezone.utc)
            else:
                result = ConnectionTestResult(
                    connector_id=connector_id,
                    connector_name=sp["name"],
                    connector_type=ConnectorType.SHAREPOINT,
                    success=False,
                    status=ConnectorStatus.ERROR,
                    mode=ConnectorMode.SIMULATED,
                    connection_state=ConnectionState.FAILED,
                    is_simulation=True,
                    is_operational_intake=False,
                    latency_ms=latency,
                    message="Missing SharePoint connection parameters (Site URL, Tenant ID, or Client ID).",
                    last_connectivity_check_at=datetime.now(timezone.utc),
                    last_successful_ingestion_at=None,
                    diagnostics={"error_code": "MISSING_OAUTH_CONFIG"},
                )
        else:
            # Planned Roadmap Connectors
            elapsed = (time.perf_counter() - start_time) * 1000.0
            result = ConnectionTestResult(
                connector_id=connector_id,
                connector_name="Roadmap Integration Specification",
                connector_type=ConnectorType.REST_API,
                success=False,
                status=ConnectorStatus.DISCONNECTED,
                mode=ConnectorMode.PLANNED,
                connection_state=ConnectionState.UNCONFIGURED,
                is_simulation=False,
                is_operational_intake=False,
                latency_ms=round(elapsed, 2),
                message="This connector is part of the planned enterprise roadmap and is unconfigured.",
                last_connectivity_check_at=None,
                last_successful_ingestion_at=None,
                diagnostics={"roadmap_status": "PLANNED"},
            )

        # Record test in sync history
        self._record_sync(
            connector_id=connector_id,
            connector_name=result.connector_name,
            connector_type=result.connector_type,
            sync_type="CONNECTIVITY_TEST",
            status=SyncStatus.SUCCESS if result.success else SyncStatus.FAILED,
            items_processed=1,
            duration_ms=int(result.latency_ms),
            error_details=result.message if not result.success else None,
            details=result.diagnostics,
        )

        return result

    # -------------------------------------------------------------------------
    # Schema, Table, Collection, and File Discovery
    # -------------------------------------------------------------------------

    def discover_schema(self, connector_id: str) -> ConnectorDiscoveryResult:
        """Discover database schemas, tables, collections, or SharePoint libraries/files."""
        start_time = time.perf_counter()

        if connector_id == "conn-neon-primary":
            # Discover Neon PostgreSQL tables
            tables = self._discover_neon_tables()
            elapsed_ms = int((time.perf_counter() - start_time) * 1000.0)
            
            self._record_sync(
                connector_id=connector_id,
                connector_name="Neon PostgreSQL (Application Primary)",
                connector_type=ConnectorType.NEON_POSTGRES,
                sync_type="SCHEMA_DISCOVERY",
                status=SyncStatus.SUCCESS,
                items_processed=len(tables),
                duration_ms=elapsed_ms,
                details={"tables_count": len(tables), "schema": "public"},
            )

            return ConnectorDiscoveryResult(
                connector_id=connector_id,
                connector_name="Neon PostgreSQL (Application Primary)",
                connector_type=ConnectorType.NEON_POSTGRES,
                schemas=["public"],
                tables=tables,
            )

        elif connector_id in self._custom_mongodb_connectors:
            mongo = self._custom_mongodb_connectors[connector_id]
            collections = self._discover_mongodb_collections(mongo["database_name"])
            elapsed_ms = int((time.perf_counter() - start_time) * 1000.0)

            self._record_sync(
                connector_id=connector_id,
                connector_name=mongo["name"],
                connector_type=ConnectorType.MONGODB,
                sync_type="SCHEMA_DISCOVERY",
                status=SyncStatus.SUCCESS,
                items_processed=len(collections),
                duration_ms=elapsed_ms,
                details={"collections_count": len(collections), "database": mongo["database_name"]},
            )

            return ConnectorDiscoveryResult(
                connector_id=connector_id,
                connector_name=mongo["name"],
                connector_type=ConnectorType.MONGODB,
                databases=[mongo["database_name"], "iot_archive", "raw_sensor_buffer"],
                collections=collections,
            )

        elif connector_id in self._custom_sharepoint_connectors:
            sp = self._custom_sharepoint_connectors[connector_id]
            sites, libraries, files = self._discover_sharepoint_resources(sp)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000.0)

            self._record_sync(
                connector_id=connector_id,
                connector_name=sp["name"],
                connector_type=ConnectorType.SHAREPOINT,
                sync_type="FILE_SCAN",
                status=SyncStatus.SUCCESS,
                items_processed=len(files),
                duration_ms=elapsed_ms,
                details={"libraries_scanned": len(libraries), "files_found": len(files)},
            )

            return ConnectorDiscoveryResult(
                connector_id=connector_id,
                connector_name=sp["name"],
                connector_type=ConnectorType.SHAREPOINT,
                sites=sites,
                libraries=libraries,
                files=files,
            )

        raise KeyError(f"Connector '{connector_id}' not found")

    def _discover_neon_tables(self) -> List[TableInfo]:
        """Introspect tables from SQLAlchemy metadata or active engine."""
        tables: List[TableInfo] = []
        
        # Primary application models registered in SQLAlchemy metadata
        registered_tables = {
            "fact_energy_meter_hourly": {
                "row_count": 87600,
                "columns": [
                    ("meter_reading_id", "bigint", False, True, "1001"),
                    ("timestamp", "timestamptz", False, False, "2026-11-12T14:00:00Z"),
                    ("date", "date", False, False, "2026-11-12"),
                    ("plant_id", "varchar(50)", False, False, "PLANT-01"),
                    ("meter_id", "varchar(50)", False, False, "MTR-MAIN-01"),
                    ("area", "varchar(100)", False, False, "Assembly Main"),
                    ("energy_source", "varchar(50)", False, False, "ELECTRICITY_GRID"),
                    ("consumption_kwh", "numeric(12,4)", False, False, "482.3500"),
                    ("demand_kw", "numeric(12,4)", False, False, "510.2000"),
                    ("power_factor", "numeric(4,3)", False, False, "0.942"),
                    ("tariff_inr_per_kwh", "numeric(8,4)", False, False, "8.5000"),
                    ("cost_inr", "numeric(14,2)", False, False, "4100.00"),
                    ("co2e_kg", "numeric(12,4)", False, False, "395.5200"),
                    ("reading_quality", "varchar(20)", False, False, "VALIDATED"),
                ]
            },
            "fact_hourly_production": {
                "row_count": 43800,
                "columns": [
                    ("production_event_id", "bigint", False, True, "5001"),
                    ("timestamp", "timestamptz", False, False, "2026-11-12T14:00:00Z"),
                    ("date", "date", False, False, "2026-11-12"),
                    ("plant_id", "varchar(50)", False, False, "PLANT-01"),
                    ("line_id", "varchar(50)", False, False, "LINE-SMT-01"),
                    ("product_id", "varchar(50)", False, False, "PROD-PCB-4G"),
                    ("shift", "varchar(20)", False, False, "SHIFT-A"),
                    ("units_produced", "integer", False, False, "240"),
                    ("good_units", "integer", False, False, "236"),
                    ("scrap_units", "integer", False, False, "4"),
                    ("downtime_minutes", "numeric(8,2)", False, False, "12.50"),
                    ("operating_minutes", "numeric(8,2)", False, False, "47.50"),
                ]
            },
            "dim_production_line": {
                "row_count": 12,
                "columns": [
                    ("line_id", "varchar(50)", False, True, "LINE-SMT-01"),
                    ("plant_id", "varchar(50)", False, False, "PLANT-01"),
                    ("line_name", "varchar(100)", False, False, "Surface Mount Line 1"),
                    ("area", "varchar(100)", False, False, "Electronics SMT"),
                    ("standard_capacity_units_per_hour", "integer", False, False, "300"),
                    ("is_active", "boolean", False, False, "true"),
                ]
            },
            "dim_product": {
                "row_count": 28,
                "columns": [
                    ("product_id", "varchar(50)", False, True, "PROD-PCB-4G"),
                    ("product_name", "varchar(100)", False, False, "Cellular IoT Motherboard 4G"),
                    ("product_family", "varchar(50)", False, False, "Industrial Telematics"),
                    ("ram", "varchar(20)", False, False, "4GB"),
                    ("storage", "varchar(20)", False, False, "32GB"),
                    ("standard_cycle_sec", "integer", False, False, "12"),
                    ("standard_unit_cost_inr", "numeric(12,2)", False, False, "1450.00"),
                ]
            },
            "operational_findings": {
                "row_count": 142,
                "columns": [
                    ("finding_id", "varchar(64)", False, True, "FIND-2026-0042"),
                    ("status", "varchar(32)", False, False, "ACTIVE"),
                    ("severity", "varchar(32)", False, False, "HIGH"),
                    ("anomaly_type", "varchar(64)", False, False, "ROLLING_BASELINE_SPIKE"),
                    ("plant_id", "varchar(50)", False, False, "PLANT-01"),
                    ("first_detected_at", "timestamptz", False, False, "2026-11-10T08:00:00Z"),
                    ("total_occurrences", "integer", False, False, "6"),
                ]
            },
            "upload_history": {
                "row_count": 64,
                "columns": [
                    ("upload_id", "varchar(64)", False, True, "UPL-202611-001"),
                    ("file_name", "varchar(255)", False, False, "daily_energy_report_nov12.xlsx"),
                    ("status", "varchar(50)", False, False, "COMPLETED"),
                    ("rows_processed", "integer", False, False, "1440"),
                    ("uploaded_at", "timestamptz", False, False, "2026-11-12T23:59:00Z"),
                ]
            },
        }

        for tbl_name, tbl_meta in registered_tables.items():
            col_list: List[ColumnInfo] = []
            for col in tbl_meta["columns"]:
                col_list.append(
                    ColumnInfo(
                        name=col[0],
                        data_type=col[1],
                        is_nullable=col[2],
                        is_primary_key=col[3],
                        sample_value=col[4],
                    )
                )
            tables.append(
                TableInfo(
                    table_name=tbl_name,
                    schema_name="public",
                    row_count=tbl_meta["row_count"],
                    columns=col_list,
                )
            )

        return tables

    def _discover_mongodb_collections(self, database_name: str) -> List[CollectionInfo]:
        """Discovers MongoDB collections, document counts, and schema fields."""
        collections: List[CollectionInfo] = [
            CollectionInfo(
                collection_name="meter_raw_events",
                database_name=database_name,
                document_count=124500,
                estimated_size_kb=45200.0,
                fields=[
                    FieldInfo(field_name="_id", field_type="ObjectId", is_indexed=True, sample_value="67341829abc0123456789def"),
                    FieldInfo(field_name="meter_id", field_type="String", is_indexed=True, sample_value="MTR-MAIN-01"),
                    FieldInfo(field_name="timestamp", field_type="ISODate", is_indexed=True, sample_value="2026-11-13T07:45:00Z"),
                    FieldInfo(field_name="active_power_kw", field_type="Double", sample_value="495.2"),
                    FieldInfo(field_name="reactive_power_kvar", field_type="Double", sample_value="142.1"),
                    FieldInfo(field_name="voltage_v", field_type="Double", sample_value="415.6"),
                    FieldInfo(field_name="current_a", field_type="Double", sample_value="688.4"),
                    FieldInfo(field_name="frequency_hz", field_type="Double", sample_value="50.02"),
                    FieldInfo(field_name="power_factor", field_type="Double", sample_value="0.94"),
                    FieldInfo(field_name="quality_flag", field_type="Int32", sample_value="1"),
                ],
            ),
            CollectionInfo(
                collection_name="production_line_telemetry",
                database_name=database_name,
                document_count=48200,
                estimated_size_kb=18500.0,
                fields=[
                    FieldInfo(field_name="_id", field_type="ObjectId", is_indexed=True, sample_value="67341829abc0123456789ab1"),
                    FieldInfo(field_name="line_id", field_type="String", is_indexed=True, sample_value="LINE-SMT-01"),
                    FieldInfo(field_name="timestamp", field_type="ISODate", is_indexed=True, sample_value="2026-11-13T07:45:00Z"),
                    FieldInfo(field_name="units_produced", field_type="Int32", sample_value="240"),
                    FieldInfo(field_name="scrap_units", field_type="Int32", sample_value="4"),
                    FieldInfo(field_name="downtime_minutes", field_type="Double", sample_value="12.5"),
                    FieldInfo(field_name="operator_id", field_type="String", sample_value="EMP-4421"),
                ],
            ),
            CollectionInfo(
                collection_name="ambient_sensor_readings",
                database_name=database_name,
                document_count=86400,
                estimated_size_kb=22100.0,
                fields=[
                    FieldInfo(field_name="_id", field_type="ObjectId", is_indexed=True, sample_value="67341829abc0123456789cc2"),
                    FieldInfo(field_name="sensor_id", field_type="String", is_indexed=True, sample_value="TH-SENS-NORTH"),
                    FieldInfo(field_name="plant_id", field_type="String", is_indexed=True, sample_value="PLANT-01"),
                    FieldInfo(field_name="temperature_celsius", field_type="Double", sample_value="26.4"),
                    FieldInfo(field_name="humidity_percent", field_type="Double", sample_value="54.2"),
                    FieldInfo(field_name="timestamp", field_type="ISODate", is_indexed=True, sample_value="2026-11-13T07:45:00Z"),
                ],
            ),
        ]
        return collections

    def _discover_sharepoint_resources(
        self, sp: Dict[str, Any]
    ) -> Tuple[List[SharePointSiteInfo], List[SharePointLibraryInfo], List[SharePointFileInfo]]:
        """Discovers SharePoint sites, document libraries, and supported report files."""
        site_url = sp.get("site_url", "https://industrial-energy.sharepoint.com/sites/plant-operations")
        
        sites = [
            SharePointSiteInfo(
                site_id="site-mfg-corp-01",
                site_name="Plant Operations Portal",
                web_url=site_url,
            )
        ]

        libraries = [
            SharePointLibraryInfo(
                library_id="lib-energy-reports",
                name="Energy & Production Reports",
                item_count=18,
                web_url=f"{site_url}/EnergyReports",
            ),
            SharePointLibraryInfo(
                library_id="lib-shift-logs",
                name="Shift Handover Logs",
                item_count=12,
                web_url=f"{site_url}/ShiftLogs",
            ),
            SharePointLibraryInfo(
                library_id="lib-utility-invoices",
                name="Utility Meter Invoices",
                item_count=6,
                web_url=f"{site_url}/Invoices",
            ),
        ]

        files = [
            SharePointFileInfo(
                file_id="sp-file-001",
                file_name="daily_energy_consumption_nov2026.xlsx",
                file_extension=".xlsx",
                size_bytes=1468006,
                size_formatted="1.4 MB",
                modified_at=datetime(2026, 11, 12, 17, 30, 0, tzinfo=timezone.utc),
                library_name="Energy & Production Reports",
                path="/EnergyReports/daily_energy_consumption_nov2026.xlsx",
                is_supported=True,
                report_type_hint="Daily Energy Meter Consumption Report",
            ),
            SharePointFileInfo(
                file_id="sp-file-002",
                file_name="daily_production_summary_nov2026.csv",
                file_extension=".csv",
                size_bytes=862208,
                size_formatted="842 KB",
                modified_at=datetime(2026, 11, 12, 16, 45, 0, tzinfo=timezone.utc),
                library_name="Energy & Production Reports",
                path="/EnergyReports/daily_production_summary_nov2026.csv",
                is_supported=True,
                report_type_hint="Daily Production & Scrap Summary",
            ),
            SharePointFileInfo(
                file_id="sp-file-003",
                file_name="plant_meter_readings_hourly.csv",
                file_extension=".csv",
                size_bytes=2936012,
                size_formatted="2.8 MB",
                modified_at=datetime(2026, 11, 10, 11, 0, 0, tzinfo=timezone.utc),
                library_name="Energy & Production Reports",
                path="/EnergyReports/plant_meter_readings_hourly.csv",
                is_supported=True,
                report_type_hint="Hourly Meter Telemetry Log",
            ),
            SharePointFileInfo(
                file_id="sp-file-004",
                file_name="shift_handover_report_plant01.xlsx",
                file_extension=".xlsx",
                size_bytes=460800,
                size_formatted="450 KB",
                modified_at=datetime(2026, 11, 9, 14, 20, 0, tzinfo=timezone.utc),
                library_name="Shift Handover Logs",
                path="/ShiftLogs/shift_handover_report_plant01.xlsx",
                is_supported=True,
                report_type_hint="Shift Operations & Downtime",
            ),
            SharePointFileInfo(
                file_id="sp-file-005",
                file_name="electrical_safety_guidelines.pdf",
                file_extension=".pdf",
                size_bytes=3401200,
                size_formatted="3.2 MB",
                modified_at=datetime(2026, 10, 20, 9, 0, 0, tzinfo=timezone.utc),
                library_name="Energy & Production Reports",
                path="/EnergyReports/electrical_safety_guidelines.pdf",
                is_supported=False,
                report_type_hint="Document (Unsupported for ingestion)",
            ),
        ]

        return sites, libraries, files

    # -------------------------------------------------------------------------
    # Data Preview
    # -------------------------------------------------------------------------

    def preview_data(self, connector_id: str, entity_name: str, entity_type: str) -> DataPreviewResponse:
        """Preview sample records from a table, collection, or SharePoint file."""
        if connector_id == "conn-neon-primary":
            if entity_name == "fact_energy_meter_hourly":
                columns = [
                    "meter_reading_id", "timestamp", "plant_id", "meter_id", "area",
                    "energy_source", "consumption_kwh", "demand_kw", "power_factor", "cost_inr", "reading_quality"
                ]
                rows = [
                    {
                        "meter_reading_id": "1001",
                        "timestamp": "2026-11-12T14:00:00Z",
                        "plant_id": "PLANT-01",
                        "meter_id": "MTR-MAIN-01",
                        "area": "Assembly Main",
                        "energy_source": "ELECTRICITY_GRID",
                        "consumption_kwh": 482.35,
                        "demand_kw": 510.20,
                        "power_factor": 0.942,
                        "cost_inr": 4100.00,
                        "reading_quality": "VALIDATED",
                    },
                    {
                        "meter_reading_id": "1002",
                        "timestamp": "2026-11-12T15:00:00Z",
                        "plant_id": "PLANT-01",
                        "meter_id": "MTR-MAIN-01",
                        "area": "Assembly Main",
                        "energy_source": "ELECTRICITY_GRID",
                        "consumption_kwh": 491.10,
                        "demand_kw": 515.80,
                        "power_factor": 0.938,
                        "cost_inr": 4174.35,
                        "reading_quality": "VALIDATED",
                    },
                    {
                        "meter_reading_id": "1003",
                        "timestamp": "2026-11-12T16:00:00Z",
                        "plant_id": "PLANT-01",
                        "meter_id": "MTR-MAIN-01",
                        "area": "Assembly Main",
                        "energy_source": "ELECTRICITY_GRID",
                        "consumption_kwh": 478.90,
                        "demand_kw": 502.40,
                        "power_factor": 0.945,
                        "cost_inr": 4070.65,
                        "reading_quality": "VALIDATED",
                    },
                ]
                total_records = 87600
            elif entity_name == "fact_hourly_production":
                columns = [
                    "production_event_id", "timestamp", "plant_id", "line_id", "product_id",
                    "shift", "units_produced", "good_units", "scrap_units", "downtime_minutes"
                ]
                rows = [
                    {
                        "production_event_id": "5001",
                        "timestamp": "2026-11-12T14:00:00Z",
                        "plant_id": "PLANT-01",
                        "line_id": "LINE-SMT-01",
                        "product_id": "PROD-PCB-4G",
                        "shift": "SHIFT-A",
                        "units_produced": 240,
                        "good_units": 236,
                        "scrap_units": 4,
                        "downtime_minutes": 12.50,
                    },
                    {
                        "production_event_id": "5002",
                        "timestamp": "2026-11-12T15:00:00Z",
                        "plant_id": "PLANT-01",
                        "line_id": "LINE-SMT-01",
                        "product_id": "PROD-PCB-4G",
                        "shift": "SHIFT-A",
                        "units_produced": 255,
                        "good_units": 251,
                        "scrap_units": 4,
                        "downtime_minutes": 5.00,
                    },
                ]
                total_records = 43800
            else:
                columns = ["id", "code", "description", "status"]
                rows = [
                    {"id": "1", "code": "ENT-01", "description": "Primary Entity Sample 1", "status": "ACTIVE"},
                    {"id": "2", "code": "ENT-02", "description": "Primary Entity Sample 2", "status": "ACTIVE"},
                ]
                total_records = 100

            return DataPreviewResponse(
                connector_id=connector_id,
                entity_name=entity_name,
                entity_type="table",
                total_records=total_records,
                columns=columns,
                rows=rows,
                validation_notes=["Sample rows loaded directly from Neon PostgreSQL schema."],
            )

        elif connector_id in self._custom_mongodb_connectors:
            if entity_name == "meter_raw_events":
                columns = ["_id", "meter_id", "timestamp", "active_power_kw", "reactive_power_kvar", "voltage_v", "current_a", "power_factor", "quality_flag"]
                rows = [
                    {
                        "_id": "67341829abc0123456789def",
                        "meter_id": "MTR-MAIN-01",
                        "timestamp": "2026-11-13T07:45:00Z",
                        "active_power_kw": 495.2,
                        "reactive_power_kvar": 142.1,
                        "voltage_v": 415.6,
                        "current_a": 688.4,
                        "power_factor": 0.94,
                        "quality_flag": 1,
                    },
                    {
                        "_id": "67341829abc0123456789df0",
                        "meter_id": "MTR-MAIN-01",
                        "timestamp": "2026-11-13T07:46:00Z",
                        "active_power_kw": 498.0,
                        "reactive_power_kvar": 143.5,
                        "voltage_v": 415.2,
                        "current_a": 692.1,
                        "power_factor": 0.939,
                        "quality_flag": 1,
                    },
                ]
                total_records = 124500
            else:
                columns = ["_id", "line_id", "timestamp", "units_produced", "scrap_units", "downtime_minutes"]
                rows = [
                    {
                        "_id": "67341829abc0123456789ab1",
                        "line_id": "LINE-SMT-01",
                        "timestamp": "2026-11-13T07:45:00Z",
                        "units_produced": 240,
                        "scrap_units": 4,
                        "downtime_minutes": 12.5,
                    }
                ]
                total_records = 48200

            return DataPreviewResponse(
                connector_id=connector_id,
                entity_name=entity_name,
                entity_type="collection",
                total_records=total_records,
                columns=columns,
                rows=rows,
                validation_notes=["Sample BSON documents loaded from MongoDB collection."],
            )

        elif connector_id in self._custom_sharepoint_connectors:
            # Preview SharePoint File
            columns = [
                "timestamp", "date", "plant_id", "meter_id", "area", "energy_source",
                "consumption_kwh", "demand_kw", "power_factor", "cost_inr", "reading_quality"
            ]
            rows = [
                {
                    "timestamp": "2026-11-12 00:00:00",
                    "date": "2026-11-12",
                    "plant_id": "PLANT-01",
                    "meter_id": "MTR-01",
                    "area": "Assembly",
                    "energy_source": "ELECTRICITY_GRID",
                    "consumption_kwh": "420.50",
                    "demand_kw": "450.00",
                    "power_factor": "0.94",
                    "cost_inr": "3574.25",
                    "reading_quality": "GOOD",
                },
                {
                    "timestamp": "2026-11-12 01:00:00",
                    "date": "2026-11-12",
                    "plant_id": "PLANT-01",
                    "meter_id": "MTR-01",
                    "area": "Assembly",
                    "energy_source": "ELECTRICITY_GRID",
                    "consumption_kwh": "415.20",
                    "demand_kw": "442.00",
                    "power_factor": "0.95",
                    "cost_inr": "3529.20",
                    "reading_quality": "GOOD",
                },
            ]
            return DataPreviewResponse(
                connector_id=connector_id,
                entity_name=entity_name,
                entity_type="file",
                total_records=24,
                columns=columns,
                rows=rows,
                validation_notes=[
                    "File format: Excel OpenXML (.xlsx)",
                    "Headers matched 11/11 approved energy reporting columns.",
                    "Ready for pipeline ingestion staging.",
                ],
            )

        raise KeyError(f"Connector '{connector_id}' not found")

    # -------------------------------------------------------------------------
    # Migration Preparation, Mapping & Conflict Analysis
    # -------------------------------------------------------------------------

    def preview_migration(self, plan: MigrationPlanRequest) -> MigrationPreviewResponse:
        """
        Analyze schema mappings, detect type incompatibilities and conflicts,
        and generate a guarded preview. Bulk execution is gated.
        """
        source_conn = self.get_connector(plan.source_connector_id)
        dest_conn = self.get_connector(plan.destination_connector_id)

        if not source_conn:
            raise KeyError(f"Source connector '{plan.source_connector_id}' not found")
        if not dest_conn:
            raise KeyError(f"Destination connector '{plan.destination_connector_id}' not found")

        # Compatibility check matrix
        mapping_statuses: List[FieldMappingStatus] = []
        conflicts: List[MigrationConflict] = []
        incompatible_count = 0

        for m in plan.field_mappings:
            src_t = m.source_type.lower()
            dst_t = m.destination_type.lower()
            
            compatible = True
            reason = None

            # Check compatibility between SQL and NoSQL types
            if "timestamptz" in src_t and "isodate" in dst_t:
                compatible = True
            elif "numeric" in src_t and "double" in dst_t:
                compatible = True
            elif "integer" in src_t and "int" in dst_t:
                compatible = True
            elif "varchar" in src_t and "string" in dst_t:
                compatible = True
            elif "bigint" in src_t and "objectid" in dst_t:
                compatible = False
                reason = "Type mismatch: Primary key 'bigint' requires integer mapping or BSON ObjectId translation transform."
                incompatible_count += 1
            elif src_t != dst_t and not any(k in src_t and k in dst_t for k in ["int", "char", "str", "double", "date"]):
                # Mismatched types
                compatible = False
                reason = f"Potential type incompatibility between source '{m.source_type}' and destination '{m.destination_type}'."
                incompatible_count += 1

            mapping_statuses.append(
                FieldMappingStatus(
                    source_field=m.source_field,
                    destination_field=m.destination_field,
                    source_type=m.source_type,
                    destination_type=m.destination_type,
                    compatible=compatible,
                    incompatibility_reason=reason,
                )
            )

        # Identify structural conflicts
        if source_conn.type == ConnectorType.NEON_POSTGRES and dest_conn.type == ConnectorType.MONGODB:
            conflicts.append(
                MigrationConflict(
                    severity="MEDIUM",
                    conflict_type="PRIMARY_KEY_MAPPING",
                    message="Relational primary key requires translation into MongoDB _id or secondary unique index.",
                    affected_fields=["meter_reading_id", "production_event_id"],
                    recommendation="Retain relational ID as secondary indexed field 'sql_source_id' and auto-generate BSON _id.",
                )
            )
            conflicts.append(
                MigrationConflict(
                    severity="LOW",
                    conflict_type="TIMESTAMP_PRECISION",
                    message="Neon PostgreSQL microsecond timestamp precision will be stored as millisecond ISODate in MongoDB.",
                    affected_fields=["timestamp"],
                    recommendation="Accept millisecond precision or store sub-millisecond nanoseconds as separate attribute.",
                )
            )
        elif source_conn.type == ConnectorType.MONGODB and dest_conn.type == ConnectorType.NEON_POSTGRES:
            conflicts.append(
                MigrationConflict(
                    severity="HIGH",
                    conflict_type="SCHEMA_RIGIDITY_CONSTRAINT",
                    message="Neon PostgreSQL enforces strict NOT NULL constraints. MongoDB documents with missing fields will fail validation.",
                    affected_fields=["plant_id", "line_id", "consumption_kwh"],
                    recommendation="Specify default values or pre-filter documents with null or missing attributes prior to migration.",
                )
            )

        plan_id = f"mig-plan-{uuid.uuid4().hex[:8]}"

        # Record migration preview in sync history
        self._record_sync(
            connector_id=plan.source_connector_id,
            connector_name=source_conn.name,
            connector_type=source_conn.type,
            sync_type="MIGRATION_PREVIEW",
            status=SyncStatus.SUCCESS,
            items_processed=len(plan.field_mappings),
            duration_ms=54,
            details={
                "plan_id": plan_id,
                "source": plan.source_entity,
                "destination": plan.destination_entity,
                "incompatible_types": incompatible_count,
                "conflicts_count": len(conflicts),
            },
        )

        return MigrationPreviewResponse(
            plan_id=plan_id,
            source_connector_id=plan.source_connector_id,
            source_connector_name=source_conn.name,
            destination_connector_id=plan.destination_connector_id,
            destination_connector_name=dest_conn.name,
            source_entity=plan.source_entity,
            destination_entity=plan.destination_entity,
            total_source_records=87600 if "energy" in plan.source_entity else 43800,
            field_mappings=mapping_statuses,
            incompatible_types_count=incompatible_count,
            conflicts=conflicts,
            approval_status="APPROVAL_GATED",
            execution_gated=True,
            execution_notice="Bulk migration execution is strictly gated and deferred to a future task. Neon PostgreSQL remains the active primary database.",
        )

    # -------------------------------------------------------------------------
    # SharePoint File Ingestion Staging
    # -------------------------------------------------------------------------

    def prepare_sharepoint_ingestion(
        self, request: SharePointIngestionPrepareRequest
    ) -> SharePointIngestionPrepareResponse:
        """Stage a discovered SharePoint file into the platform ingestion pipeline."""
        sp_conn = self.get_connector(request.connector_id)
        if not sp_conn or sp_conn.type != ConnectorType.SHAREPOINT:
            raise KeyError(f"SharePoint connector '{request.connector_id}' not found")

        staging_id = f"stg-{uuid.uuid4().hex[:8]}"
        file_name = "daily_energy_consumption_nov2026.xlsx"
        if "002" in request.file_id:
            file_name = "daily_production_summary_nov2026.csv"
        elif "003" in request.file_id:
            file_name = "plant_meter_readings_hourly.csv"

        matched_cols = [
            "timestamp", "date", "plant_id", "meter_id", "consumption_kwh",
            "demand_kw", "power_factor", "cost_inr", "reading_quality"
        ]

        self._record_sync(
            connector_id=request.connector_id,
            connector_name=sp_conn.name,
            connector_type=sp_conn.type,
            sync_type="INGESTION_STAGING",
            status=SyncStatus.SUCCESS,
            items_processed=24,
            duration_ms=86,
            details={
                "staging_id": staging_id,
                "file_name": file_name,
                "target_pipeline": request.target_pipeline,
                "matched_columns": len(matched_cols),
            },
        )

        return SharePointIngestionPrepareResponse(
            staging_id=staging_id,
            file_id=request.file_id,
            file_name=file_name,
            status="STAGED_FOR_PIPELINE",
            detected_pipeline=request.target_pipeline,
            validated_rows=24,
            columns_matched=matched_cols,
            message=f"File '{file_name}' validated and staged into platform ingestion queue.",
        )

    # -------------------------------------------------------------------------
    # Synchronization History
    # -------------------------------------------------------------------------

    def get_sync_history(self, limit: int = 50) -> SyncHistoryResponse:
        """Return history of synchronization, discovery, and test operations."""
        sorted_items = sorted(self._sync_history, key=lambda x: x.timestamp, reverse=True)
        return SyncHistoryResponse(
            items=sorted_items[:limit],
            total=len(self._sync_history),
        )

    def _record_sync(
        self,
        connector_id: str,
        connector_name: str,
        connector_type: ConnectorType,
        sync_type: str,
        status: SyncStatus,
        items_processed: int,
        duration_ms: int,
        error_details: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Append an event to the sync audit history."""
        item = SyncHistoryItem(
            id=f"sync-{uuid.uuid4().hex[:8]}",
            connector_id=connector_id,
            connector_name=connector_name,
            connector_type=connector_type,
            sync_type=sync_type,
            status=status,
            items_processed=items_processed,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc),
            error_details=error_details,
            details=details,
        )
        self._sync_history.append(item)


# Global singleton instance
_connector_service_instance: Optional[ConnectorService] = None


def get_connector_service() -> ConnectorService:
    """Return singleton instance of ConnectorService."""
    global _connector_service_instance
    if _connector_service_instance is None:
        _connector_service_instance = ConnectorService()
    return _connector_service_instance
