"""
Automated unit tests for Data Connectors Service contracts and security boundaries.

Covers:
1. Neon PostgreSQL — primary database, protected status, credential masking, schema discovery.
2. MongoDB — multiple registrations, URI masking, TLS, diagnostics, collection/schema discovery.
3. Microsoft SharePoint — OAuth configuration, credential masking, library/file discovery, ingestion staging.
4. Migration & Security — non-mutating preview, approval gating, credential masking, secret redaction, audit history.

Fail-Closed Security:
- All external connections (Neon, MongoDB, SharePoint, Graph OAuth) are strictly mocked.
- Zero live external connections, zero production .env access, zero database mutations.
"""

from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from app.schemas.connectors import (
    ConnectorRole,
    ConnectorStatus,
    ConnectorType,
    FieldMapping,
    MigrationPlanRequest,
    MongoDBConnectorCreate,
    MongoDBConnectorUpdate,
    SharePointConnectorCreate,
    SharePointConnectorUpdate,
    SharePointIngestionPrepareRequest,
    SyncStatus,
)
from app.services.connector_service import (
    ConnectorService,
    mask_connection_uri,
    mask_secret,
)


class TestNeonPostgresConnectorContract(unittest.TestCase):
    """Section 2: Neon PostgreSQL primary database connector contracts and boundaries."""

    def setUp(self):
        self.sleep_patcher = patch("app.services.connector_service.time.sleep")
        self.mock_sleep = self.sleep_patcher.start()
        self.service = ConnectorService()

    def tearDown(self):
        self.sleep_patcher.stop()

    def test_primary_connector_discovery(self):
        """Neon connector is discovered as the platform primary database."""
        neon = self.service.get_connector("conn-neon-primary")
        self.assertIsNotNone(neon)
        self.assertEqual(neon.id, "conn-neon-primary")
        self.assertEqual(neon.type, ConnectorType.NEON_POSTGRES)
        self.assertEqual(neon.role, ConnectorRole.PRIMARY_SOURCE)
        self.assertTrue(neon.is_primary)
        self.assertTrue(neon.is_predefined)
        self.assertEqual(neon.status, ConnectorStatus.CONNECTED)

    def test_primary_connector_credentials_masked(self):
        """Neon connection info contains strictly masked host and no credentials."""
        neon = self.service.get_connector("conn-neon-primary")
        info = neon.connection_info

        self.assertIn("host", info)
        # Supports local disposable test host (127.0.0.1 / localhost) or masked remote Neon endpoint
        self.assertTrue(
            info["host"] in ("127.0.0.1", "localhost") or "ep-***-pooler" in info["host"],
            f"Host '{info['host']}' is neither a known local test host nor a masked remote Neon endpoint.",
        )
        self.assertNotIn("password", info)
        self.assertNotIn("user", info)
        self.assertEqual(info["port"], 5432)
        self.assertEqual(info["ssl_mode"], "require")
        self.assertIn("PgBouncer", info["pooling"])
        self.assertIn("Locked", info["credentials_protection"])

        # Separate assertion ensuring remote Neon hostname masking remains explicitly covered
        with patch.object(
            self.service._settings,
            "DATABASE_URL_POOLED",
            "postgresql+psycopg://user:pass@ep-sample-a1arlm2b.ap-southeast-1.aws.neon.tech/neondb",
        ):
            remote_summary = self.service._get_neon_summary()
            self.assertEqual(remote_summary.connection_info["host"], "ep-***-pooler.ap-southeast-1.aws.neon.tech")
            self.assertNotIn("pass", str(remote_summary.connection_info))
            self.assertNotIn("user", str(remote_summary.connection_info))

    @patch("app.services.connector_service.get_engine")
    def test_connectivity_test_success_with_mock_engine(self, mock_get_engine):
        """Active connectivity test executes SELECT 1 against mock engine and reports diagnostics."""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.scalar.return_value = 1
        mock_engine.connect.return_value = mock_conn
        mock_engine.pool.size.return_value = 10
        mock_engine.pool.checkedin.return_value = 5
        mock_get_engine.return_value = mock_engine

        result = self.service.test_connection("conn-neon-primary")

        self.assertTrue(result.success)
        self.assertEqual(result.status, ConnectorStatus.CONNECTED)
        self.assertGreaterEqual(result.latency_ms, 0.0)
        self.assertIn("active and verified", result.message)
        self.assertEqual(result.diagnostics["ping_status"], "OK")
        self.assertEqual(result.diagnostics["server_protocol"], "PostgreSQL 16.x / Neon serverless")

    @patch("app.services.connector_service.get_engine")
    def test_connectivity_test_engine_standby(self, mock_get_engine):
        """When SQLAlchemy engine is None, reports standby configured status."""
        mock_get_engine.return_value = None

        result = self.service.test_connection("conn-neon-primary")

        self.assertTrue(result.success)
        self.assertEqual(result.status, ConnectorStatus.CONNECTED)
        self.assertIn("Engine standby", result.message)
        self.assertEqual(result.diagnostics["status"], "Configured")

    @patch("app.services.connector_service.get_engine")
    def test_connectivity_test_failure_sanitizes_errors(self, mock_get_engine):
        """Database connection exception is captured with status ERROR and no credential leakage."""
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("connection to server at '127.0.0.1', port 5432 failed: timeout")
        mock_get_engine.return_value = mock_engine

        result = self.service.test_connection("conn-neon-primary")

        self.assertFalse(result.success)
        self.assertEqual(result.status, ConnectorStatus.ERROR)
        self.assertIn("Neon connection failed", result.message)
        self.assertIn("timeout", result.diagnostics["error"])

    def test_schema_discovery_tables_and_columns(self):
        """Schema discovery introspects relational tables and column metadata."""
        disc = self.service.discover_schema("conn-neon-primary")

        self.assertEqual(disc.connector_id, "conn-neon-primary")
        self.assertEqual(disc.schemas, ["public"])
        self.assertGreaterEqual(len(disc.tables), 6)

        table_names = [t.table_name for t in disc.tables]
        self.assertIn("fact_energy_meter_hourly", table_names)
        self.assertIn("fact_hourly_production", table_names)
        self.assertIn("dim_production_line", table_names)
        self.assertIn("dim_product", table_names)

        # Inspect fact_energy_meter_hourly columns
        energy_tbl = [t for t in disc.tables if t.table_name == "fact_energy_meter_hourly"][0]
        col_names = [c.name for c in energy_tbl.columns]
        self.assertIn("meter_reading_id", col_names)
        self.assertIn("consumption_kwh", col_names)
        self.assertIn("power_factor", col_names)

        pk_col = [c for c in energy_tbl.columns if c.is_primary_key][0]
        self.assertEqual(pk_col.name, "meter_reading_id")

    def test_data_preview_fact_tables(self):
        """Data preview returns sample records and columns for relational tables."""
        preview = self.service.preview_data("conn-neon-primary", "fact_energy_meter_hourly", "table")

        self.assertEqual(preview.connector_id, "conn-neon-primary")
        self.assertEqual(preview.entity_name, "fact_energy_meter_hourly")
        self.assertEqual(preview.entity_type, "table")
        self.assertGreater(len(preview.columns), 0)
        self.assertGreater(len(preview.rows), 0)
        self.assertIn("consumption_kwh", preview.columns)
        self.assertIn("Sample rows loaded directly from Neon PostgreSQL schema.", preview.validation_notes[0])

    def test_protected_primary_connector_cannot_be_deleted(self):
        """Attempting to delete the predefined Neon primary connector raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.service.delete_connector("conn-neon-primary")
        self.assertIn("Neon PostgreSQL primary database connector is predefined and cannot be removed", str(ctx.exception))


class TestMongoDBConnectorContract(unittest.TestCase):
    """Section 3: MongoDB connector registration, URI masking, discovery, and lifecycle."""

    def setUp(self):
        self.sleep_patcher = patch("app.services.connector_service.time.sleep")
        self.mock_sleep = self.sleep_patcher.start()
        self.service = ConnectorService()

    def tearDown(self):
        self.sleep_patcher.stop()

    def test_default_seeded_mongodb_connector(self):
        """Initial default MongoDB telemetry connector is present with masked URI."""
        mongo = self.service.get_connector("conn-mongo-analytics")
        self.assertIsNotNone(mongo)
        self.assertEqual(mongo.type, ConnectorType.MONGODB)
        self.assertEqual(mongo.role, ConnectorRole.SOURCE_DESTINATION)
        self.assertFalse(mongo.is_primary)
        self.assertIn("••••••••", mongo.connection_info["uri"])
        self.assertNotIn("SecureSensorPass2026", mongo.connection_info["uri"])

    def test_multiple_independent_connector_registrations(self):
        """Platform supports multiple independent MongoDB connector registrations."""
        conn1_payload = MongoDBConnectorCreate(
            name="Plant SMT Buffer Mongo",
            uri="mongodb://operator_smt:SecretSMT@cluster-smt.iot.net:27017/smt_buffer",
            database_name="smt_buffer",
            ssl=True,
        )
        conn2_payload = MongoDBConnectorCreate(
            name="Plant FAL Telemetry Mongo",
            uri="mongodb+srv://operator_fal:SecretFAL@cluster-fal.iot.net/fal_telemetry",
            database_name="fal_telemetry",
            ssl=False,
        )

        c1 = self.service.create_mongodb_connector(conn1_payload)
        c2 = self.service.create_mongodb_connector(conn2_payload)

        self.assertNotEqual(c1.id, c2.id)
        self.assertEqual(c1.name, "Plant SMT Buffer Mongo")
        self.assertEqual(c2.name, "Plant FAL Telemetry Mongo")

        # Verify password masking for both
        self.assertIn("••••••••", c1.connection_info["uri"])
        self.assertNotIn("SecretSMT", c1.connection_info["uri"])
        self.assertIn("••••••••", c2.connection_info["uri"])
        self.assertNotIn("SecretFAL", c2.connection_info["uri"])

        # Both exist independently in the connector listing
        all_conns = self.service.get_all_connectors()
        conn_ids = [c.id for c in all_conns]
        self.assertIn(c1.id, conn_ids)
        self.assertIn(c2.id, conn_ids)

    def test_tls_ssl_configuration_persistence(self):
        """TLS/SSL flag is accurately recorded and toggled."""
        c_ssl = self.service.create_mongodb_connector(
            MongoDBConnectorCreate(
                name="Encrypted Mongo",
                uri="mongodb://user:pass@host:27017/secure_db",
                database_name="secure_db",
                ssl=True,
            )
        )
        self.assertTrue(c_ssl.connection_info["ssl"])

        c_plain = self.service.create_mongodb_connector(
            MongoDBConnectorCreate(
                name="Plain Mongo",
                uri="mongodb://user:pass@host:27017/plain_db",
                database_name="plain_db",
                ssl=False,
            )
        )
        self.assertFalse(c_plain.connection_info["ssl"])

    def test_connectivity_test_success_valid_uri(self):
        """Valid MongoDB URI returns connected status with detailed diagnostics."""
        result = self.service.test_connection("conn-mongo-analytics")

        self.assertTrue(result.success)
        self.assertEqual(result.status, ConnectorStatus.CONNECTED)
        self.assertEqual(result.connector_type, ConnectorType.MONGODB)
        self.assertGreaterEqual(result.latency_ms, 0.0)
        self.assertEqual(result.diagnostics["ping_status"], "OK")
        self.assertEqual(result.diagnostics["wire_protocol"], "OpMsg (v6)")
        self.assertEqual(result.diagnostics["tls_version"], "TLSv1.3")

    def test_connectivity_test_failure_invalid_uri_scheme(self):
        """Invalid URI scheme triggers connection failure with INVALID_URI_SCHEME diagnostic."""
        c_bad = self.service.create_mongodb_connector(
            MongoDBConnectorCreate(
                name="Bad Scheme Mongo",
                uri="invalid-scheme://user:pass@host:27017/db",
                database_name="db",
            )
        )
        # Automatic connection test during creation flags ERROR
        self.assertEqual(c_bad.status, ConnectorStatus.ERROR)

        test_res = self.service.test_connection(c_bad.id)
        self.assertFalse(test_res.success)
        self.assertEqual(test_res.status, ConnectorStatus.ERROR)
        self.assertIn("Invalid MongoDB URI format", test_res.message)
        self.assertEqual(test_res.diagnostics["error_code"], "INVALID_URI_SCHEME")

    def test_connector_update_parameters_and_retesting(self):
        """Updating MongoDB parameters triggers re-testing and persists changes."""
        update_data = MongoDBConnectorUpdate(
            name="Renamed Mongo Cluster",
            database_name="updated_telemetry_db",
            replica_set="new-rs-01",
            ssl=False,
        )
        updated = self.service.update_mongodb_connector("conn-mongo-analytics", update_data)

        self.assertEqual(updated.name, "Renamed Mongo Cluster")
        self.assertEqual(updated.connection_info["database_name"], "updated_telemetry_db")
        self.assertEqual(updated.connection_info["replica_set"], "new-rs-01")
        self.assertFalse(updated.connection_info["ssl"])

    def test_collection_and_schema_discovery(self):
        """MongoDB discovery reports collections, document counts, sizes, and schema fields."""
        disc = self.service.discover_schema("conn-mongo-analytics")

        self.assertEqual(disc.connector_type, ConnectorType.MONGODB)
        self.assertGreaterEqual(len(disc.collections), 3)

        coll_names = [c.collection_name for c in disc.collections]
        self.assertIn("meter_raw_events", coll_names)
        self.assertIn("production_line_telemetry", coll_names)
        self.assertIn("ambient_sensor_readings", coll_names)

        meter_coll = [c for c in disc.collections if c.collection_name == "meter_raw_events"][0]
        self.assertEqual(meter_coll.document_count, 124500)
        self.assertEqual(meter_coll.estimated_size_kb, 45200.0)

        # Check field definitions
        field_names = [f.field_name for f in meter_coll.fields]
        self.assertIn("_id", field_names)
        self.assertIn("meter_id", field_names)
        self.assertIn("active_power_kw", field_names)

        id_field = [f for f in meter_coll.fields if f.field_name == "_id"][0]
        self.assertEqual(id_field.field_type, "ObjectId")
        self.assertTrue(id_field.is_indexed)

    def test_data_preview_collection(self):
        """Data preview returns BSON documents and validation notes."""
        preview = self.service.preview_data("conn-mongo-analytics", "meter_raw_events", "collection")

        self.assertEqual(preview.connector_id, "conn-mongo-analytics")
        self.assertEqual(preview.entity_type, "collection")
        self.assertEqual(preview.total_records, 124500)
        self.assertIn("_id", preview.columns)
        self.assertIn("active_power_kw", preview.columns)
        self.assertGreater(len(preview.rows), 0)
        self.assertIn("Sample BSON documents", preview.validation_notes[0])

    def test_custom_connector_deletion(self):
        """Custom MongoDB connector is successfully removed from state."""
        c = self.service.create_mongodb_connector(
            MongoDBConnectorCreate(
                name="Temporary Mongo",
                uri="mongodb://user:pass@host:27017/temp_db",
                database_name="temp_db",
            )
        )
        self.assertIsNotNone(self.service.get_connector(c.id))

        deleted = self.service.delete_connector(c.id)
        self.assertTrue(deleted)
        self.assertIsNone(self.service.get_connector(c.id))

        # Second deletion raises KeyError
        with self.assertRaises(KeyError):
            self.service.delete_connector(c.id)


class TestSharePointConnectorContract(unittest.TestCase):
    """Section 4: Microsoft SharePoint Graph API OAuth connector, discovery, and ingestion staging."""

    def setUp(self):
        self.sleep_patcher = patch("app.services.connector_service.time.sleep")
        self.mock_sleep = self.sleep_patcher.start()
        self.service = ConnectorService()

    def tearDown(self):
        self.sleep_patcher.stop()

    def test_default_seeded_sharepoint_connector(self):
        """Initial SharePoint connector is registered with masked credentials."""
        sp = self.service.get_connector("conn-sp-mfg")
        self.assertIsNotNone(sp)
        self.assertEqual(sp.type, ConnectorType.SHAREPOINT)
        self.assertEqual(sp.role, ConnectorRole.INGESTION_SOURCE)
        self.assertFalse(sp.is_primary)

        info = sp.connection_info
        self.assertIn("••••••••", info["tenant_id"])
        self.assertIn("••••••••", info["client_id"])
        self.assertEqual(info["client_secret"], "••••••••••••••••")
        self.assertNotIn("LiveSecret_GraphApi_9876543210_Key", str(info))

    def test_registration_oauth_configuration_validation(self):
        """New SharePoint connector registration enforces OAuth parameters and masks secret."""
        payload = SharePointConnectorCreate(
            name="Plant SMT Site Library",
            tenant_id="11112222-3333-4444-5555-666677778888",
            client_id="aaaabbbb-cccc-dddd-eeee-ffff00001111",
            client_secret="SuperSecretClientPassword123!",
            site_url="https://contoso.sharepoint.com/sites/smt-plant",
            default_library="Daily Logs",
        )
        c = self.service.create_sharepoint_connector(payload)

        self.assertIsNotNone(c)
        self.assertEqual(c.name, "Plant SMT Site Library")
        self.assertEqual(c.connection_info["client_secret"], "••••••••••••••••")
        self.assertNotIn("SuperSecretClientPassword123!", str(c.connection_info))

    def test_connectivity_test_success_mock_graph(self):
        """Connectivity test verifies Microsoft Graph endpoint resolution and OAuth scopes."""
        result = self.service.test_connection("conn-sp-mfg")

        self.assertTrue(result.success)
        self.assertEqual(result.status, ConnectorStatus.CONNECTED)
        self.assertEqual(result.connector_type, ConnectorType.SHAREPOINT)
        self.assertGreaterEqual(result.latency_ms, 0.0)

        diag = result.diagnostics
        self.assertEqual(diag["graph_endpoint"], "https://graph.microsoft.com/v1.0")
        self.assertEqual(diag["oauth_grant"], "client_credentials")
        self.assertIn("Files.Read.All", diag["scopes_granted"])
        self.assertIn("Sites.Read.All", diag["scopes_granted"])
        self.assertEqual(diag["site_resolution"], "Resolved (200 OK)")

    def test_connectivity_test_failure_missing_oauth_params(self):
        """Missing OAuth parameters produce status ERROR with MISSING_OAUTH_CONFIG diagnostic."""
        c = self.service.create_sharepoint_connector(
            SharePointConnectorCreate(
                name="Incomplete SharePoint",
                tenant_id="12345678",
                client_id="12345678",
                client_secret="secret",
                site_url="https://valid-url.sharepoint.com",
            )
        )
        # Simulate missing client_id in configuration
        self.service._custom_sharepoint_connectors[c.id]["client_id"] = ""
        test_res = self.service.test_connection(c.id)

        self.assertFalse(test_res.success)
        self.assertEqual(test_res.status, ConnectorStatus.ERROR)
        self.assertIn("Missing SharePoint connection parameters", test_res.message)
        self.assertEqual(test_res.diagnostics["error_code"], "MISSING_OAUTH_CONFIG")

    def test_connector_update_parameters(self):
        """Updating SharePoint parameters persists correctly."""
        update_data = SharePointConnectorUpdate(
            name="Updated SharePoint Portal",
            site_url="https://industrial-energy.sharepoint.com/sites/updated-ops",
            default_library="Monthly Energy Summary",
        )
        updated = self.service.update_sharepoint_connector("conn-sp-mfg", update_data)

        self.assertEqual(updated.name, "Updated SharePoint Portal")
        self.assertEqual(updated.connection_info["site_url"], "https://industrial-energy.sharepoint.com/sites/updated-ops")
        self.assertEqual(updated.connection_info["default_library"], "Monthly Energy Summary")

    def test_site_and_library_discovery(self):
        """Discovery lists sites and document libraries available for ingestion."""
        disc = self.service.discover_schema("conn-sp-mfg")

        self.assertEqual(disc.connector_type, ConnectorType.SHAREPOINT)
        self.assertIsNotNone(disc.sites)
        self.assertEqual(len(disc.sites), 1)
        self.assertEqual(disc.sites[0].site_name, "Plant Operations Portal")

        self.assertIsNotNone(disc.libraries)
        lib_names = [lib.name for lib in disc.libraries]
        self.assertIn("Energy & Production Reports", lib_names)
        self.assertIn("Shift Handover Logs", lib_names)
        self.assertIn("Utility Meter Invoices", lib_names)

    def test_supported_and_unsupported_files_discovery(self):
        """Discovery classifies supported (xlsx, csv) vs unsupported (pdf) files."""
        disc = self.service.discover_schema("conn-sp-mfg")
        self.assertIsNotNone(disc.files)

        supported_files = [f for f in disc.files if f.is_supported]
        unsupported_files = [f for f in disc.files if not f.is_supported]

        self.assertGreaterEqual(len(supported_files), 4)
        self.assertEqual(len(unsupported_files), 1)

        # Check supported formats
        supported_exts = {f.file_extension for f in supported_files}
        self.assertIn(".xlsx", supported_exts)
        self.assertIn(".csv", supported_exts)

        # Check unsupported format
        self.assertEqual(unsupported_files[0].file_extension, ".pdf")
        self.assertIn("Unsupported", unsupported_files[0].report_type_hint)

    def test_sharepoint_file_data_preview(self):
        """Previewing a SharePoint file returns structured rows and validation notes."""
        preview = self.service.preview_data("conn-sp-mfg", "daily_energy_consumption_nov2026.xlsx", "file")

        self.assertEqual(preview.connector_id, "conn-sp-mfg")
        self.assertEqual(preview.entity_type, "file")
        self.assertEqual(preview.total_records, 24)
        self.assertIn("consumption_kwh", preview.columns)
        self.assertIn("power_factor", preview.columns)
        self.assertGreater(len(preview.rows), 0)
        self.assertIn("Ready for pipeline ingestion staging", preview.validation_notes[2])

    def test_sharepoint_ingestion_preparation_staging_only(self):
        """Preparing SharePoint file creates a non-mutating staging entry without fact table mutation."""
        req = SharePointIngestionPrepareRequest(
            connector_id="conn-sp-mfg",
            file_id="sp-file-001",
            target_pipeline="daily_reports",
        )
        res = self.service.prepare_sharepoint_ingestion(req)

        self.assertIsNotNone(res.staging_id)
        self.assertTrue(res.staging_id.startswith("stg-"))
        self.assertEqual(res.status, "STAGED_FOR_PIPELINE")
        self.assertEqual(res.detected_pipeline, "daily_reports")
        self.assertEqual(res.validated_rows, 24)
        self.assertIn("consumption_kwh", res.columns_matched)
        self.assertIn("validated and staged", res.message)

        # Verify operation was recorded in sync audit history
        sync_items = self.service.get_sync_history().items
        stg_events = [s for s in sync_items if s.sync_type == "INGESTION_STAGING"]
        self.assertGreaterEqual(len(stg_events), 1)
        self.assertEqual(stg_events[0].status, SyncStatus.SUCCESS)

    def test_custom_sharepoint_connector_deletion(self):
        """Custom SharePoint connector can be cleanly deleted."""
        c = self.service.create_sharepoint_connector(
            SharePointConnectorCreate(
                name="Temporary SP",
                tenant_id="12345678",
                client_id="12345678",
                client_secret="secret",
                site_url="https://temp.sharepoint.com",
            )
        )
        self.assertTrue(self.service.delete_connector(c.id))
        self.assertIsNone(self.service.get_connector(c.id))


class TestMigrationAndSecurityBoundaries(unittest.TestCase):
    """Section 5: Migration preview safeguards, credential masking, error redaction, and sync history."""

    def setUp(self):
        self.sleep_patcher = patch("app.services.connector_service.time.sleep")
        self.mock_sleep = self.sleep_patcher.start()
        self.service = ConnectorService()

    def tearDown(self):
        self.sleep_patcher.stop()

    def test_migration_preview_is_approval_gated_and_non_mutating(self):
        """Migration preview is strictly gated and executes zero data modifications."""
        plan = MigrationPlanRequest(
            source_connector_id="conn-neon-primary",
            destination_connector_id="conn-mongo-analytics",
            source_entity="fact_energy_meter_hourly",
            destination_entity="meter_raw_events",
            field_mappings=[
                FieldMapping(source_field="timestamp", source_type="timestamptz", destination_field="timestamp", destination_type="isodate"),
                FieldMapping(source_field="consumption_kwh", source_type="numeric", destination_field="active_power_kw", destination_type="double"),
                FieldMapping(source_field="meter_reading_id", source_type="bigint", destination_field="_id", destination_type="objectid"),
            ],
        )
        preview = self.service.preview_migration(plan)

        self.assertIsNotNone(preview.plan_id)
        self.assertEqual(preview.approval_status, "APPROVAL_GATED")
        self.assertTrue(preview.execution_gated)
        self.assertIn("Bulk migration execution is strictly gated", preview.execution_notice)
        self.assertIn("Neon PostgreSQL remains the active primary database", preview.execution_notice)

        # Check field compatibility evaluations
        self.assertEqual(len(preview.field_mappings), 3)
        self.assertTrue(preview.field_mappings[0].compatible)  # timestamptz -> isodate
        self.assertTrue(preview.field_mappings[1].compatible)  # numeric -> double
        self.assertFalse(preview.field_mappings[2].compatible)  # bigint -> objectid
        self.assertEqual(preview.incompatible_types_count, 1)

        # Structural conflicts identified
        self.assertGreaterEqual(len(preview.conflicts), 2)
        conflict_types = [c.conflict_type for c in preview.conflicts]
        self.assertIn("PRIMARY_KEY_MAPPING", conflict_types)
        self.assertIn("TIMESTAMP_PRECISION", conflict_types)

    def test_migration_preview_unknown_connector_raises_key_error(self):
        """Previewing migration with non-existent connector ID raises KeyError."""
        plan = MigrationPlanRequest(
            source_connector_id="non-existent-source",
            destination_connector_id="conn-mongo-analytics",
            source_entity="source_tbl",
            destination_entity="dest_coll",
            field_mappings=[],
        )
        with self.assertRaises(KeyError):
            self.service.preview_migration(plan)

    def test_mask_secret_helper_scenarios(self):
        """mask_secret function correctly masks secrets under various inputs."""
        self.assertEqual(mask_secret(None), "••••••••")
        self.assertEqual(mask_secret(""), "••••••••")
        self.assertEqual(mask_secret("abc"), "••••••••")
        self.assertEqual(mask_secret("1234"), "••••••••")
        # Default full mask
        self.assertEqual(mask_secret("supersecretkey12345"), "••••••••••••••••")
        # Visible edge chars
        masked_partial = mask_secret("8b14a512-3f71-4a9c-9c12-7489ab1092e4", visible_chars=4)
        self.assertTrue(masked_partial.startswith("8b14"))
        self.assertTrue(masked_partial.endswith("92e4"))
        self.assertIn("••••••••", masked_partial)

    def test_mask_connection_uri_helper_scenarios(self):
        """mask_connection_uri strictly sanitizes passwords in database URIs."""
        self.assertEqual(mask_connection_uri(""), "")

        # MongoDB URI
        mongo_uri = "mongodb+srv://admin_user:SuperSecretPass!@cluster0.net/test?retryWrites=true"
        masked_mongo = mask_connection_uri(mongo_uri)
        self.assertNotIn("SuperSecretPass!", masked_mongo)
        self.assertIn("admin_user:••••••••@cluster0.net", masked_mongo)

        # PostgreSQL URI
        pg_uri = "postgresql://db_owner:SecretDbPass2026@ep-pooler.aws.neon.tech:5432/neondb"
        masked_pg = mask_connection_uri(pg_uri)
        self.assertNotIn("SecretDbPass2026", masked_pg)
        self.assertIn("db_owner:••••••••@ep-pooler", masked_pg)

        # URI with no credentials remains unchanged
        no_auth = "mongodb://localhost:27017/local_db"
        self.assertEqual(mask_connection_uri(no_auth), no_auth)

    def test_sync_audit_history_recording(self):
        """Service records audit entries for all discovery, testing, staging, and migration actions."""
        hist = self.service.get_sync_history(limit=50)
        self.assertGreaterEqual(hist.total, 3)

        # Trigger new operations
        self.service.test_connection("conn-mongo-analytics")
        self.service.discover_schema("conn-neon-primary")

        new_hist = self.service.get_sync_history(limit=50)
        self.assertGreater(new_hist.total, hist.total)

        sync_types = {item.sync_type for item in new_hist.items}
        self.assertIn("CONNECTIVITY_TEST", sync_types)
        self.assertIn("SCHEMA_DISCOVERY", sync_types)

    def test_non_existent_connector_raises_key_error(self):
        """Operations against non-existent connector IDs raise KeyError."""
        with self.assertRaises(KeyError):
            self.service.test_connection("unknown-connector-999")
        with self.assertRaises(KeyError):
            self.service.discover_schema("unknown-connector-999")
        with self.assertRaises(KeyError):
            self.service.preview_data("unknown-connector-999", "tbl", "table")
        with self.assertRaises(KeyError):
            self.service.delete_connector("unknown-connector-999")


if __name__ == "__main__":
    unittest.main()
