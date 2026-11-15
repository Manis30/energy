"""
Automated API tests for Cross-Source Data Reconciliation FastAPI endpoints.

Tests report, summary, and checks catalog endpoints using Starlette TestClient
with disposable database session.
"""

from datetime import date
import unittest

from starlette.testclient import TestClient

from app.db import get_session_factory
from app.main import app
from app.schemas.reconciliation import ReconciliationCategory, ReconciliationStatus

SEEDED_START_DATE = date(2026, 8, 1)
SEEDED_END_DATE = date(2026, 8, 2)


class TestReconciliationApi(unittest.TestCase):
    """FastAPI reconciliation endpoints contract and integration tests."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.session_factory = get_session_factory()

    def setUp(self):
        self.session = self.session_factory()

    def tearDown(self):
        self.session.close()

    # ---------------------------------------------------------
    # 1. GET /api/reconciliation (Full Report Endpoint)
    # ---------------------------------------------------------

    def test_get_reconciliation_report_success(self):
        """GET /api/reconciliation returns 200 with full report schema on valid window."""
        response = self.client.get(
            "/api/reconciliation",
            params={
                "start_date": SEEDED_START_DATE.isoformat(),
                "end_date": SEEDED_END_DATE.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("status", data)
        self.assertEqual(data["status"], ReconciliationStatus.PASS.value)
        self.assertIn("counts", data)
        self.assertEqual(data["counts"]["total_checks"], 7)
        self.assertEqual(data["counts"]["pass_count"], 7)
        self.assertEqual(data["counts"]["fail_count"], 0)
        self.assertIn("evaluation_period", data)
        self.assertEqual(data["evaluation_period"]["start_date"], SEEDED_START_DATE.isoformat())
        self.assertEqual(data["evaluation_period"]["end_date"], SEEDED_END_DATE.isoformat())
        self.assertIn("checks", data)
        self.assertEqual(len(data["checks"]), 7)
        self.assertIn("limitations", data)
        self.assertTrue(len(data["limitations"]) >= 1)

    def test_get_reconciliation_report_plant_filter(self):
        """GET /api/reconciliation filters report by plant_id."""
        response = self.client.get(
            "/api/reconciliation",
            params={
                "start_date": SEEDED_START_DATE.isoformat(),
                "end_date": SEEDED_END_DATE.isoformat(),
                "plant_id": "IN-TN-01",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["plant_id"], "IN-TN-01")
        for chk in data["checks"]:
            self.assertEqual(chk["plant_id"], "IN-TN-01")

    def test_get_reconciliation_report_category_filter(self):
        """GET /api/reconciliation filters checks by category."""
        response = self.client.get(
            "/api/reconciliation",
            params={
                "start_date": SEEDED_START_DATE.isoformat(),
                "end_date": SEEDED_END_DATE.isoformat(),
                "category": "ENERGY_COVERAGE",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["checks"]), 1)
        self.assertEqual(data["checks"][0]["check_id"], "CHK_ENERGY_COVERAGE")
        self.assertEqual(data["checks"][0]["category"], ReconciliationCategory.ENERGY_COVERAGE.value)
        self.assertEqual(data["counts"]["total_checks"], 1)

    def test_get_reconciliation_report_finding_status_filter(self):
        """GET /api/reconciliation filters findings by finding_status."""
        response = self.client.get(
            "/api/reconciliation",
            params={
                "start_date": SEEDED_START_DATE.isoformat(),
                "end_date": SEEDED_END_DATE.isoformat(),
                "finding_status": "UNAVAILABLE",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for chk in data["checks"]:
            for f in chk["findings"]:
                self.assertEqual(f["status"], "UNAVAILABLE")

    def test_get_reconciliation_report_invalid_date_range_400(self):
        """GET /api/reconciliation returns 400 when start_date > end_date."""
        response = self.client.get(
            "/api/reconciliation",
            params={
                "start_date": "2026-08-10",
                "end_date": "2026-08-01",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("must be before or equal to", response.json()["detail"].lower())

    def test_get_reconciliation_report_exceeds_max_range_400(self):
        """GET /api/reconciliation returns 400 when date range exceeds 366 days."""
        response = self.client.get(
            "/api/reconciliation",
            params={
                "start_date": "2025-01-01",
                "end_date": "2026-02-01",  # 397 days
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("366", response.json()["detail"])

    def test_get_reconciliation_report_missing_parameters_422(self):
        """GET /api/reconciliation returns 422 when required query params are omitted."""
        response = self.client.get("/api/reconciliation")
        self.assertEqual(response.status_code, 422)

    def test_get_reconciliation_report_invalid_date_format_422(self):
        """GET /api/reconciliation returns 422 when dates are not ISO YYYY-MM-DD."""
        response = self.client.get(
            "/api/reconciliation",
            params={"start_date": "not-a-date", "end_date": "2026-08-01"},
        )
        self.assertEqual(response.status_code, 422)

    def test_get_reconciliation_report_invalid_category_422(self):
        """GET /api/reconciliation returns 422 when category is not a valid enum value."""
        response = self.client.get(
            "/api/reconciliation",
            params={
                "start_date": "2026-08-01",
                "end_date": "2026-08-02",
                "category": "NON_EXISTENT_CATEGORY",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_get_reconciliation_report_empty_dataset_handling(self):
        """GET /api/reconciliation on window with no telemetry returns 200 with WARNING status."""
        response = self.client.get(
            "/api/reconciliation",
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], ReconciliationStatus.WARNING.value)
        self.assertTrue(data["counts"]["warning_count"] > 0)

    # ---------------------------------------------------------
    # 2. GET /api/reconciliation/summary (Summary Endpoint)
    # ---------------------------------------------------------

    def test_get_summary_success(self):
        """GET /api/reconciliation/summary returns 200 with lightweight summary and category statuses."""
        response = self.client.get(
            "/api/reconciliation/summary",
            params={
                "start_date": SEEDED_START_DATE.isoformat(),
                "end_date": SEEDED_END_DATE.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("status", data)
        self.assertEqual(data["status"], ReconciliationStatus.PASS.value)
        self.assertIn("counts", data)
        self.assertEqual(data["counts"]["total_checks"], 7)
        self.assertIn("category_statuses", data)
        self.assertEqual(len(data["category_statuses"]), 7)
        for cat in ReconciliationCategory:
            self.assertIn(cat.value, data["category_statuses"])
            self.assertEqual(data["category_statuses"][cat.value], ReconciliationStatus.PASS.value)
        self.assertIn("limitations", data)

    def test_get_summary_plant_filter(self):
        """GET /api/reconciliation/summary filters summary by plant_id."""
        response = self.client.get(
            "/api/reconciliation/summary",
            params={
                "start_date": SEEDED_START_DATE.isoformat(),
                "end_date": SEEDED_END_DATE.isoformat(),
                "plant_id": "IN-KA-01",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["plant_id"], "IN-KA-01")
        self.assertEqual(data["status"], ReconciliationStatus.PASS.value)

    def test_get_summary_invalid_date_range_400(self):
        """GET /api/reconciliation/summary returns 400 when start_date > end_date."""
        response = self.client.get(
            "/api/reconciliation/summary",
            params={"start_date": "2026-08-10", "end_date": "2026-08-01"},
        )
        self.assertEqual(response.status_code, 400)

    def test_get_summary_exceeds_max_range_400(self):
        """GET /api/reconciliation/summary returns 400 when date range exceeds 366 days."""
        response = self.client.get(
            "/api/reconciliation/summary",
            params={"start_date": "2025-01-01", "end_date": "2026-02-01"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("366", response.json()["detail"])

    def test_get_summary_missing_parameters_422(self):
        """GET /api/reconciliation/summary returns 422 when required query params are omitted."""
        response = self.client.get("/api/reconciliation/summary")
        self.assertEqual(response.status_code, 422)

    # ---------------------------------------------------------
    # 3. GET /api/reconciliation/checks (Catalog Endpoint)
    # ---------------------------------------------------------

    def test_list_checks_success(self):
        """GET /api/reconciliation/checks returns 200 with list of all 7 check definitions."""
        response = self.client.get("/api/reconciliation/checks")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 7)

    def test_list_checks_contains_all_seven_categories(self):
        """GET /api/reconciliation/checks catalog includes all 7 ReconciliationCategory enums."""
        response = self.client.get("/api/reconciliation/checks")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        returned_categories = {item["category"] for item in data}
        expected_categories = {cat.value for cat in ReconciliationCategory}
        self.assertEqual(returned_categories, expected_categories)

    def test_list_checks_definition_fields(self):
        """GET /api/reconciliation/checks definitions include all required schema fields."""
        response = self.client.get("/api/reconciliation/checks")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        required_fields = {
            "check_id",
            "category",
            "name",
            "description",
            "supported_dimensions",
            "unsupported_dimensions",
            "source_tables",
        }
        for item in data:
            self.assertTrue(required_fields.issubset(item.keys()))
            self.assertTrue(item["check_id"].startswith("CHK_"))
            self.assertTrue(len(item["name"]) > 0)
            self.assertTrue(len(item["description"]) > 0)
            self.assertTrue(len(item["source_tables"]) >= 1)


if __name__ == "__main__":
    unittest.main()

