"""
Automated API tests for Daily Reports FastAPI endpoints.

Tests inspect, validate, ingest, history, coverage, and template endpoints
using Starlette TestClient with disposable database session.
"""

from datetime import date
import io
import unittest

from starlette.testclient import TestClient

from app.db import get_session_factory
from app.main import app
from app.models.source_data import FactEnergyMeterHourly
from app.models.upload_history import UploadHistory

API_TEST_DATE = date(2026, 5, 20)


def _build_api_energy_csv() -> bytes:
    return (
        "timestamp,date,plant_id,meter_id,area,energy_source,consumption_kwh,demand_kw,"
        "power_factor,tariff_inr_per_kwh,cost_inr,co2e_kg,reading_quality\n"
        f"{API_TEST_DATE.isoformat()} 00:00:00,{API_TEST_DATE.isoformat()},IN-TN-01,MTR-SMT,SMT,ELECTRICITY,100,25,0.95,7.5,750,82,VALID\n"
    ).encode("utf-8")


class TestDailyReportsApi(unittest.TestCase):
    """Daily Reports HTTP endpoints contract and integration tests."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.session_factory = get_session_factory()

    def setUp(self):
        self.session = self.session_factory()
        self._cleanup()

    def tearDown(self):
        self._cleanup()
        self.session.close()

    def _cleanup(self):
        self.session.query(FactEnergyMeterHourly).filter(
            FactEnergyMeterHourly.date == API_TEST_DATE
        ).delete()
        self.session.query(UploadHistory).filter(
            UploadHistory.reporting_date == API_TEST_DATE
        ).delete()
        self.session.commit()

    # ---------------------------------------------------------
    # 1. Template Download Endpoints
    # ---------------------------------------------------------

    def test_download_energy_template_success(self):
        """GET /api/daily-reports/template/energy returns 200 with attached CSV."""
        resp = self.client.get("/api/daily-reports/template/energy")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=", resp.headers.get("content-disposition", ""))
        self.assertIn("consumption_kwh", resp.text)
        self.assertIn("meter_id", resp.text)

    def test_download_production_template_success(self):
        """GET /api/daily-reports/template/production returns 200 with attached CSV."""
        resp = self.client.get("/api/daily-reports/template/production")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("event_ts", resp.text)
        self.assertIn("actual_qty", resp.text)

    def test_download_template_invalid_type_raises_400(self):
        """GET /api/daily-reports/template/invalid returns 400 Bad Request."""
        resp = self.client.get("/api/daily-reports/template/invalid_type")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("must be 'energy' or 'production'", resp.json().get("detail", ""))

    # ---------------------------------------------------------
    # 2. Coverage Endpoints
    # ---------------------------------------------------------

    def test_coverage_valid_date_range(self):
        """GET /api/daily-reports/coverage returns 200 with coverage matrix."""
        resp = self.client.get("/api/daily-reports/coverage?start_date=2026-01-01&end_date=2026-01-07")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("energy_coverage", data)
        self.assertIn("production_coverage", data)
        self.assertIn("registered_energy_meters", data)

    def test_coverage_missing_params_raises_422(self):
        """GET /api/daily-reports/coverage without start_date and end_date raises 422."""
        resp = self.client.get("/api/daily-reports/coverage")
        self.assertEqual(resp.status_code, 422)

    def test_coverage_inverted_date_range_raises_400(self):
        """GET /api/daily-reports/coverage with start_date > end_date raises 400."""
        resp = self.client.get("/api/daily-reports/coverage?start_date=2026-01-10&end_date=2026-01-01")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("must be before or equal to", resp.json().get("detail", "").lower())

    def test_coverage_exceeding_max_days_raises_400(self):
        """GET /api/daily-reports/coverage exceeding 366 days raises 400."""
        resp = self.client.get("/api/daily-reports/coverage?start_date=2024-01-01&end_date=2026-01-01")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("must not exceed 366 inclusive days", resp.json().get("detail", ""))

    # ---------------------------------------------------------
    # 3. History Endpoints
    # ---------------------------------------------------------

    def test_get_upload_history_success(self):
        """GET /api/daily-reports/history returns 200 and list of history items."""
        resp = self.client.get("/api/daily-reports/history?limit=10")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_get_upload_history_limit_validation(self):
        """GET /api/daily-reports/history with invalid limit raises 422."""
        resp = self.client.get("/api/daily-reports/history?limit=0")
        self.assertEqual(resp.status_code, 422)

        resp2 = self.client.get("/api/daily-reports/history?limit=201")
        self.assertEqual(resp2.status_code, 422)

    # ---------------------------------------------------------
    # 4. File Inspect Endpoint
    # ---------------------------------------------------------

    def test_inspect_endpoint_valid_csv(self):
        """POST /api/daily-reports/inspect returns file format and sheet metadata."""
        csv_bytes = _build_api_energy_csv()
        files = {"file": ("energy_daily.csv", io.BytesIO(csv_bytes), "text/csv")}
        resp = self.client.post("/api/daily-reports/inspect", files=files)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["file_format"], "CSV")
        self.assertEqual(data["detected_report_type"], "ENERGY")

    def test_inspect_endpoint_unsupported_format_raises_400(self):
        """POST /api/daily-reports/inspect with unsupported file raises 400."""
        files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 dummy"), "application/pdf")}
        resp = self.client.post("/api/daily-reports/inspect", files=files)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported file format", resp.json().get("detail", ""))

    # ---------------------------------------------------------
    # 5. File Validate & Ingest Endpoints
    # ---------------------------------------------------------

    def test_validate_endpoint_valid_csv(self):
        """POST /api/daily-reports/validate validates schema and returns is_ready_for_ingest=True."""
        csv_bytes = _build_api_energy_csv()
        files = {"file": ("energy_daily.csv", io.BytesIO(csv_bytes), "text/csv")}
        data = {"report_type": "ENERGY", "mode": "INCREMENTAL"}
        resp = self.client.post("/api/daily-reports/validate", files=files, data=data)
        self.assertEqual(resp.status_code, 200)
        res_data = resp.json()
        self.assertTrue(res_data["summary"]["is_ready_for_ingest"])
        self.assertEqual(res_data["summary"]["valid_rows"], 1)

    def test_ingest_endpoint_valid_csv_success(self):
        """POST /api/daily-reports/ingest transactionally imports records into fact table."""
        csv_bytes = _build_api_energy_csv()
        files = {"file": ("energy_daily.csv", io.BytesIO(csv_bytes), "text/csv")}
        data = {
            "report_type": "ENERGY",
            "reporting_date": API_TEST_DATE.isoformat(),
            "mode": "INCREMENTAL",
        }
        resp = self.client.post("/api/daily-reports/ingest", files=files, data=data)
        self.assertEqual(resp.status_code, 200)
        res_data = resp.json()
        self.assertEqual(res_data["status"], "COMPLETED")
        self.assertEqual(res_data["imported_rows"], 1)
        self.assertTrue(res_data["upload_id"].startswith("UPL-"))


if __name__ == "__main__":
    unittest.main()
