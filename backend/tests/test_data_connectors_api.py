"""
Automated API tests for Data Connectors FastAPI endpoints (/api/connectors).

Covers all 13 REST endpoints:
1. GET /api/connectors (List connectors, credentials masked)
2. GET /api/connectors/{id} (Get single connector, 404 handling)
3. POST /api/connectors/mongodb (Register MongoDB connector, validation)
4. PUT /api/connectors/mongodb/{id} (Update MongoDB connector)
5. POST /api/connectors/sharepoint (Register SharePoint connector, OAuth validation)
6. PUT /api/connectors/sharepoint/{id} (Update SharePoint connector)
7. DELETE /api/connectors/{id} (Protected Neon 403, custom 200, unknown 404)
8. POST /api/connectors/{id}/test (Active connectivity testing & latency diagnostics)
9. GET /api/connectors/{id}/discover (Schema, collection, and file discovery)
10. GET /api/connectors/{id}/preview (Table, collection, and file data preview)
11. POST /api/connectors/migration/preview (Gated migration preview & conflict analysis)
12. POST /api/connectors/sharepoint/prepare-ingestion (SharePoint staging preparation)
13. GET /api/connectors/sync-history/list (Audit synchronization history & query limits)

Uses Starlette TestClient with FastAPI dependency overrides.
No live external connections or database mutations.
"""

import unittest
from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient

from app.main import app
from app.services.connector_service import ConnectorService, get_connector_service


class TestDataConnectorsApi(unittest.TestCase):
    """FastAPI Data Connectors API endpoint contracts and authorization guards."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # Create an isolated service instance per test
        self.service = ConnectorService()

        # Patch time.sleep to avoid synthetic network wait times in tests
        self.sleep_patcher = patch("app.services.connector_service.time.sleep")
        self.mock_sleep = self.sleep_patcher.start()

        # Patch get_engine to prevent any real DB connections during testing
        self.engine_patcher = patch("app.services.connector_service.get_engine")
        self.mock_get_engine = self.engine_patcher.start()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.scalar.return_value = 1
        mock_engine.connect.return_value = mock_conn
        mock_engine.pool.size.return_value = 10
        mock_engine.pool.checkedin.return_value = 5
        self.mock_get_engine.return_value = mock_engine

        # Dependency override to use isolated service instance
        app.dependency_overrides[get_connector_service] = lambda: self.service

    def tearDown(self):
        self.sleep_patcher.stop()
        self.engine_patcher.stop()
        app.dependency_overrides.clear()

    # -------------------------------------------------------------------------
    # 1. Listing & Individual Connector Retrieval
    # -------------------------------------------------------------------------

    def test_list_connectors_endpoint_masks_credentials(self):
        """GET /api/connectors returns all registered connectors with masked credentials."""
        response = self.client.get("/api/connectors")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 3)

        connector_ids = [c["id"] for c in data]
        self.assertIn("conn-neon-primary", connector_ids)
        self.assertIn("conn-mongo-analytics", connector_ids)
        self.assertIn("conn-sp-mfg", connector_ids)

        for conn in data:
            self.assertIn("id", conn)
            self.assertIn("name", conn)
            self.assertIn("type", conn)
            self.assertIn("role", conn)
            self.assertIn("status", conn)
            self.assertIn("connection_info", conn)

            info = conn["connection_info"]
            # Security assertion: No raw passwords or secrets returned
            self.assertNotIn("password", info)
            if "uri" in info:
                self.assertIn("••••••••", info["uri"])
            if "client_secret" in info:
                self.assertEqual(info["client_secret"], "••••••••••••••••")

    def test_get_connector_details_success(self):
        """GET /api/connectors/{id} returns details for existing connectors."""
        # Neon primary
        res_neon = self.client.get("/api/connectors/conn-neon-primary")
        self.assertEqual(res_neon.status_code, 200)
        data_neon = res_neon.json()
        self.assertEqual(data_neon["id"], "conn-neon-primary")
        self.assertTrue(data_neon["is_primary"])
        self.assertTrue(data_neon["is_predefined"])

        # MongoDB
        res_mongo = self.client.get("/api/connectors/conn-mongo-analytics")
        self.assertEqual(res_mongo.status_code, 200)
        data_mongo = res_mongo.json()
        self.assertEqual(data_mongo["type"], "mongodb")
        self.assertFalse(data_mongo["is_primary"])

        # SharePoint
        res_sp = self.client.get("/api/connectors/conn-sp-mfg")
        self.assertEqual(res_sp.status_code, 200)
        data_sp = res_sp.json()
        self.assertEqual(data_sp["type"], "sharepoint")

    def test_get_connector_details_not_found(self):
        """GET /api/connectors/{id} returns 404 for unknown connector ID."""
        response = self.client.get("/api/connectors/non-existent-connector-id")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    # -------------------------------------------------------------------------
    # 2. MongoDB Registration & Update
    # -------------------------------------------------------------------------

    def test_create_mongodb_connector_success(self):
        """POST /api/connectors/mongodb registers new connector and returns masked summary."""
        payload = {
            "name": "Line SMT Telemetry Cluster",
            "uri": "mongodb+srv://user_smt:SecretPassword123@cluster0.mongodb.net/smt_data",
            "database_name": "smt_data",
            "auth_database": "admin",
            "replica_set": "rs-smt-01",
            "ssl": True,
        }
        response = self.client.post("/api/connectors/mongodb", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()

        self.assertEqual(data["name"], "Line SMT Telemetry Cluster")
        self.assertEqual(data["type"], "mongodb")
        self.assertEqual(data["status"], "connected")
        self.assertIn("••••••••", data["connection_info"]["uri"])
        self.assertNotIn("SecretPassword123", data["connection_info"]["uri"])

    def test_create_mongodb_connector_validation_failure(self):
        """POST /api/connectors/mongodb rejects invalid payload with 422."""
        invalid_payload = {
            "name": "A",  # Min length is 2
            "uri": "short",  # Min length is 10
            "database_name": "",  # Min length is 1
        }
        response = self.client.post("/api/connectors/mongodb", json=invalid_payload)
        self.assertEqual(response.status_code, 422)

    def test_update_mongodb_connector_success(self):
        """PUT /api/connectors/mongodb/{id} updates parameters and re-tests connectivity."""
        update_payload = {
            "name": "Updated SMT Cluster Name",
            "database_name": "smt_data_v2",
            "ssl": False,
        }
        response = self.client.put("/api/connectors/mongodb/conn-mongo-analytics", json=update_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["name"], "Updated SMT Cluster Name")
        self.assertEqual(data["connection_info"]["database_name"], "smt_data_v2")
        self.assertFalse(data["connection_info"]["ssl"])

    def test_update_mongodb_connector_not_found(self):
        """PUT /api/connectors/mongodb/{id} returns 404 for unknown connector ID."""
        response = self.client.put("/api/connectors/mongodb/unknown-mongo-id", json={"name": "New Name"})
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------------------
    # 3. SharePoint Registration & Update
    # -------------------------------------------------------------------------

    def test_create_sharepoint_connector_success(self):
        """POST /api/connectors/sharepoint registers connection with Graph OAuth parameters."""
        payload = {
            "name": "Plant FAL Ingestion Library",
            "tenant_id": "8b14a512-3f71-4a9c-9c12-7489ab1092e4",
            "client_id": "4c28f910-d851-4012-b2d9-1234abcd5678",
            "client_secret": "LiveSecret_GraphApi_9876543210_Key",
            "site_url": "https://industrial-energy.sharepoint.com/sites/fal-plant",
            "default_library": "Shift Production Logs",
        }
        response = self.client.post("/api/connectors/sharepoint", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()

        self.assertEqual(data["name"], "Plant FAL Ingestion Library")
        self.assertEqual(data["type"], "sharepoint")
        self.assertEqual(data["status"], "connected")
        self.assertEqual(data["connection_info"]["client_secret"], "••••••••••••••••")
        self.assertNotIn("LiveSecret_GraphApi_9876543210_Key", str(data))

    def test_create_sharepoint_connector_validation_failure(self):
        """POST /api/connectors/sharepoint returns 422 on invalid OAuth credentials."""
        invalid_payload = {
            "name": "SP",
            "tenant_id": "short",  # Min length 8
            "client_id": "short",  # Min length 8
            "client_secret": "abc",  # Min length 4
            "site_url": "http",  # Min length 10
        }
        response = self.client.post("/api/connectors/sharepoint", json=invalid_payload)
        self.assertEqual(response.status_code, 422)

    def test_update_sharepoint_connector_success(self):
        """PUT /api/connectors/sharepoint/{id} updates parameters."""
        update_payload = {
            "name": "Renamed Operations SharePoint",
            "site_url": "https://industrial-energy.sharepoint.com/sites/renamed-ops",
        }
        response = self.client.put("/api/connectors/sharepoint/conn-sp-mfg", json=update_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["name"], "Renamed Operations SharePoint")
        self.assertEqual(data["connection_info"]["site_url"], "https://industrial-energy.sharepoint.com/sites/renamed-ops")

    def test_update_sharepoint_connector_not_found(self):
        """PUT /api/connectors/sharepoint/{id} returns 404 for unknown ID."""
        response = self.client.put("/api/connectors/sharepoint/unknown-sp-id", json={"name": "New Name"})
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------------------
    # 4. Protected Deletion Guards
    # -------------------------------------------------------------------------

    def test_delete_primary_neon_connector_forbidden(self):
        """DELETE /api/connectors/conn-neon-primary returns HTTP 403 Forbidden."""
        response = self.client.delete("/api/connectors/conn-neon-primary")
        self.assertEqual(response.status_code, 403)
        self.assertIn("cannot be removed", response.json()["detail"].lower())

    def test_update_primary_neon_connector_rejected(self):
        """Neon primary connector cannot be modified via PUT endpoints."""
        # Generic PUT on /api/connectors/{id} is not an allowed method (HTTP 405)
        res_direct = self.client.put("/api/connectors/conn-neon-primary", json={"name": "Hacked Neon"})
        self.assertEqual(res_direct.status_code, 405)

        # Attempting update via MongoDB endpoint rejects with 404
        res_mongo = self.client.put("/api/connectors/mongodb/conn-neon-primary", json={"name": "Hacked Neon"})
        self.assertEqual(res_mongo.status_code, 404)

        # Attempting update via SharePoint endpoint rejects with 404
        res_sp = self.client.put("/api/connectors/sharepoint/conn-neon-primary", json={"name": "Hacked Neon"})
        self.assertEqual(res_sp.status_code, 404)

    def test_delete_custom_connector_success(self):
        """DELETE /api/connectors/{id} successfully deletes custom connector."""
        # Create a disposable connector
        create_res = self.client.post(
            "/api/connectors/mongodb",
            json={
                "name": "Disposable Mongo",
                "uri": "mongodb://user:pass@host:27017/db",
                "database_name": "db",
            },
        )
        conn_id = create_res.json()["id"]

        del_res = self.client.delete(f"/api/connectors/{conn_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["status"], "success")

        # Verify it no longer exists
        get_res = self.client.get(f"/api/connectors/{conn_id}")
        self.assertEqual(get_res.status_code, 404)

    def test_delete_connector_not_found(self):
        """DELETE /api/connectors/{id} returns 404 for unknown ID."""
        response = self.client.delete("/api/connectors/unknown-connector-999")
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------------------
    # 5. Connectivity Testing & Diagnostics
    # -------------------------------------------------------------------------

    def test_connectivity_test_neon_endpoint(self):
        """POST /api/connectors/{id}/test tests Neon primary connectivity."""
        response = self.client.post("/api/connectors/conn-neon-primary/test")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["connector_id"], "conn-neon-primary")
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "connected")
        self.assertGreaterEqual(data["latency_ms"], 0.0)
        self.assertIn("diagnostics", data)
        self.assertEqual(data["diagnostics"]["ping_status"], "OK")

    def test_connectivity_test_mongodb_endpoint(self):
        """POST /api/connectors/{id}/test tests MongoDB connectivity."""
        response = self.client.post("/api/connectors/conn-mongo-analytics/test")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["connector_id"], "conn-mongo-analytics")
        self.assertTrue(data["success"])
        self.assertEqual(data["connector_type"], "mongodb")
        self.assertEqual(data["diagnostics"]["ping_status"], "OK")

    def test_connectivity_test_sharepoint_endpoint(self):
        """POST /api/connectors/{id}/test tests Microsoft Graph API OAuth connectivity."""
        response = self.client.post("/api/connectors/conn-sp-mfg/test")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["connector_id"], "conn-sp-mfg")
        self.assertTrue(data["success"])
        self.assertEqual(data["connector_type"], "sharepoint")
        self.assertIn("Files.Read.All", data["diagnostics"]["scopes_granted"])

    def test_connectivity_test_unknown_connector_returns_404(self):
        """POST /api/connectors/{id}/test returns 404 for non-existent connector."""
        response = self.client.post("/api/connectors/non-existent/test")
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------------------
    # 6. Schema, Collection, and File Discovery
    # -------------------------------------------------------------------------

    def test_discover_neon_tables_endpoint(self):
        """GET /api/connectors/{id}/discover returns table metadata for Neon."""
        response = self.client.get("/api/connectors/conn-neon-primary/discover")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["connector_id"], "conn-neon-primary")
        self.assertEqual(data["schemas"], ["public"])
        self.assertIsNotNone(data["tables"])
        self.assertGreaterEqual(len(data["tables"]), 6)

        table_names = [t["table_name"] for t in data["tables"]]
        self.assertIn("fact_energy_meter_hourly", table_names)
        self.assertIn("fact_hourly_production", table_names)

    def test_discover_mongodb_collections_endpoint(self):
        """GET /api/connectors/{id}/discover returns collection metadata for MongoDB."""
        response = self.client.get("/api/connectors/conn-mongo-analytics/discover")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["connector_id"], "conn-mongo-analytics")
        self.assertIsNotNone(data["collections"])
        self.assertGreaterEqual(len(data["collections"]), 3)

        coll_names = [c["collection_name"] for c in data["collections"]]
        self.assertIn("meter_raw_events", coll_names)

    def test_discover_sharepoint_resources_endpoint(self):
        """GET /api/connectors/{id}/discover returns sites, libraries, and files for SharePoint."""
        response = self.client.get("/api/connectors/conn-sp-mfg/discover")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["connector_id"], "conn-sp-mfg")
        self.assertIsNotNone(data["sites"])
        self.assertIsNotNone(data["libraries"])
        self.assertIsNotNone(data["files"])

        file_names = [f["file_name"] for f in data["files"]]
        self.assertIn("daily_energy_consumption_nov2026.xlsx", file_names)

    def test_discover_unknown_connector_returns_404(self):
        """GET /api/connectors/{id}/discover returns 404 for unknown connector."""
        response = self.client.get("/api/connectors/unknown-connector/discover")
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------------------
    # 7. Data Preview
    # -------------------------------------------------------------------------

    def test_preview_neon_table_data(self):
        """GET /api/connectors/{id}/preview returns sample records for Neon table."""
        response = self.client.get(
            "/api/connectors/conn-neon-primary/preview",
            params={"entity_name": "fact_energy_meter_hourly", "entity_type": "table"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["connector_id"], "conn-neon-primary")
        self.assertEqual(data["entity_name"], "fact_energy_meter_hourly")
        self.assertEqual(data["entity_type"], "table")
        self.assertGreater(len(data["columns"]), 0)
        self.assertGreater(len(data["rows"]), 0)

    def test_preview_mongodb_collection_data(self):
        """GET /api/connectors/{id}/preview returns BSON document sample for MongoDB collection."""
        response = self.client.get(
            "/api/connectors/conn-mongo-analytics/preview",
            params={"entity_name": "meter_raw_events", "entity_type": "collection"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["connector_id"], "conn-mongo-analytics")
        self.assertEqual(data["entity_type"], "collection")
        self.assertGreater(len(data["rows"]), 0)

    def test_preview_sharepoint_file_data(self):
        """GET /api/connectors/{id}/preview returns sample rows from SharePoint report file."""
        response = self.client.get(
            "/api/connectors/conn-sp-mfg/preview",
            params={"entity_name": "daily_energy_consumption_nov2026.xlsx", "entity_type": "file"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["connector_id"], "conn-sp-mfg")
        self.assertEqual(data["entity_type"], "file")
        self.assertEqual(data["total_records"], 24)

    def test_preview_unknown_connector_returns_404(self):
        """GET /api/connectors/{id}/preview returns 404 for unknown connector."""
        response = self.client.get(
            "/api/connectors/unknown-connector/preview",
            params={"entity_name": "some_table", "entity_type": "table"},
        )
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------------------
    # 8. Migration Preview & Conflict Analysis
    # -------------------------------------------------------------------------

    def test_migration_preview_endpoint_approval_gated(self):
        """POST /api/connectors/migration/preview returns gated plan with conflict analysis."""
        payload = {
            "source_connector_id": "conn-neon-primary",
            "destination_connector_id": "conn-mongo-analytics",
            "source_entity": "fact_energy_meter_hourly",
            "destination_entity": "meter_raw_events",
            "field_mappings": [
                {
                    "source_field": "timestamp",
                    "source_type": "timestamptz",
                    "destination_field": "timestamp",
                    "destination_type": "isodate",
                },
                {
                    "source_field": "consumption_kwh",
                    "source_type": "numeric",
                    "destination_field": "active_power_kw",
                    "destination_type": "double",
                },
                {
                    "source_field": "meter_reading_id",
                    "source_type": "bigint",
                    "destination_field": "_id",
                    "destination_type": "objectid",
                },
            ],
        }
        response = self.client.post("/api/connectors/migration/preview", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["approval_status"], "APPROVAL_GATED")
        self.assertTrue(data["execution_gated"])
        self.assertEqual(data["incompatible_types_count"], 1)
        self.assertGreaterEqual(len(data["conflicts"]), 2)
        self.assertIn("Bulk migration execution is strictly gated", data["execution_notice"])

    def test_migration_preview_unknown_connector_returns_404(self):
        """POST /api/connectors/migration/preview returns 404 if a connector ID is invalid."""
        payload = {
            "source_connector_id": "unknown-source",
            "destination_connector_id": "conn-mongo-analytics",
            "source_entity": "tbl",
            "destination_entity": "coll",
            "field_mappings": [],
        }
        response = self.client.post("/api/connectors/migration/preview", json=payload)
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------------------
    # 9. SharePoint Ingestion Staging
    # -------------------------------------------------------------------------

    def test_sharepoint_prepare_ingestion_endpoint(self):
        """POST /api/connectors/sharepoint/prepare-ingestion validates and stages file."""
        payload = {
            "connector_id": "conn-sp-mfg",
            "file_id": "sp-file-001",
            "target_pipeline": "daily_reports",
        }
        response = self.client.post("/api/connectors/sharepoint/prepare-ingestion", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["staging_id"].startswith("stg-"))
        self.assertEqual(data["status"], "STAGED_FOR_PIPELINE")
        self.assertEqual(data["detected_pipeline"], "daily_reports")
        self.assertEqual(data["validated_rows"], 24)
        self.assertGreater(len(data["columns_matched"]), 0)

    def test_sharepoint_prepare_ingestion_unknown_connector_returns_404(self):
        """POST /api/connectors/sharepoint/prepare-ingestion returns 404 for invalid connector."""
        payload = {
            "connector_id": "non-existent-connector",
            "file_id": "sp-file-001",
            "target_pipeline": "daily_reports",
        }
        response = self.client.post("/api/connectors/sharepoint/prepare-ingestion", json=payload)
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------------------
    # 10. Synchronization Audit History
    # -------------------------------------------------------------------------

    def test_get_sync_history_endpoint(self):
        """GET /api/connectors/sync-history/list returns audit history items."""
        response = self.client.get("/api/connectors/sync-history/list?limit=25")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertGreaterEqual(data["total"], 3)

        first_item = data["items"][0]
        self.assertIn("id", first_item)
        self.assertIn("connector_id", first_item)
        self.assertIn("sync_type", first_item)
        self.assertIn("status", first_item)
        self.assertIn("duration_ms", first_item)

    def test_sync_history_limit_validation(self):
        """GET /api/connectors/sync-history/list enforces limit bounds (1 <= limit <= 200)."""
        res_zero = self.client.get("/api/connectors/sync-history/list?limit=0")
        self.assertEqual(res_zero.status_code, 422)

        res_over = self.client.get("/api/connectors/sync-history/list?limit=201")
        self.assertEqual(res_over.status_code, 422)


if __name__ == "__main__":
    unittest.main()
