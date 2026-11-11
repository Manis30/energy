"""
Automated API tests for Industrial Energy Intelligence Platform.

Tests all 21 FastAPI analytical endpoints using native ASGI request execution:
1. Energy Analytics Endpoints (summary, by-meter, by-area, daily-trend, power-factor)
2. Production Analytics Endpoints (summary, by-line, by-product, by-shift, downtime-by-reason, daily-trend)
3. Energy Intensity Endpoints (process, factory, product, zero-production)
4. Deterministic Anomaly Endpoints (statistical, rolling, low-power-factor, zero-production, all)
5. Input Validation (invalid time/date ranges return 400 Bad Request)
6. OpenAPI Schema Documentation Verification
"""

import asyncio
from datetime import date, datetime
from decimal import Decimal
import json
from typing import Any, Dict, Optional, Tuple
import unittest
from urllib.parse import urlencode

from app.db import get_engine
from app.main import app


class AsgiClient:
    """Lightweight ASGI test client using pure Python asyncio without external dependencies."""

    def __init__(self, asgi_app):
        self.app = asgi_app

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
        query_string = ""
        if params:
            clean_params = {}
            for k, v in params.items():
                if v is not None:
                    if isinstance(v, (datetime, date)):
                        clean_params[k] = v.isoformat()
                    else:
                        clean_params[k] = str(v)
            query_string = urlencode(clean_params)

        return asyncio.run(self._dispatch("GET", path, query_string))

    async def _dispatch(self, method: str, path: str, query_string: str) -> Tuple[int, Dict[str, Any]]:
        response_body = []
        status_code = 500

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            nonlocal status_code, response_body
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                response_body.append(message.get("body", b""))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query_string.encode("utf-8"),
            "headers": [(b"host", b"127.0.0.1:8000")],
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 50000),
        }

        await self.app(scope, receive, send)
        raw_content = b"".join(response_body).decode("utf-8")
        try:
            parsed = json.loads(raw_content) if raw_content else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw_content}

        return status_code, parsed


class TestAnalyticsApiEndpoints(unittest.TestCase):
    """Test suite verifying FastAPI endpoints against live Neon analytical data."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        if cls.engine is None:
            raise RuntimeError("Database engine not available for API tests.")
        cls.client = AsgiClient(app)

    def test_health_check(self):
        """Verify system health check endpoint."""
        status_code, body = self.client.get("/api/health")
        self.assertEqual(status_code, 200)
        self.assertEqual(body["status"], "ok")

    # ==========================================
    # Energy Analytics Endpoints
    # ==========================================

    def test_energy_summary_endpoint(self):
        """Verify /api/energy/summary returns correct overall factory totals."""
        status_code, body = self.client.get("/api/energy/summary")
        self.assertEqual(status_code, 200)
        self.assertEqual(body["total_consumption_kwh"], "1958088.3130")
        self.assertEqual(body["total_cost_inr"], "16154228.24")
        self.assertEqual(body["total_co2e_kg"], "1401991.1270")
        self.assertEqual(body["total_readings"], 22080)
        self.assertEqual(body["distinct_hours"], 2208)

    def test_energy_summary_with_plant_filter(self):
        """Verify /api/energy/summary with plant filter isolates specific plant."""
        status_code, body = self.client.get("/api/energy/summary", {"plant_id": "IN-TN-01"})
        self.assertEqual(status_code, 200)
        self.assertEqual(body["plant_id"], "IN-TN-01")
        self.assertEqual(body["total_readings"], 11040)

    def test_energy_by_meter_endpoint(self):
        """Verify /api/energy/by-meter returns all 5 meters with correct shares."""
        status_code, body = self.client.get("/api/energy/by-meter")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(body), 5)
        # SMT should be top consumer
        self.assertEqual(body[0]["meter_id"], "MTR-SMT")
        self.assertEqual(body[0]["consumption_kwh"], "507553.4990")

    def test_energy_by_area_endpoint(self):
        """Verify /api/energy/by-area aggregates factory areas correctly."""
        status_code, body = self.client.get("/api/energy/by-area")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(body), 5)

    def test_energy_daily_trend_endpoint(self):
        """Verify /api/energy/daily-trend returns daily time-series."""
        status_code, body = self.client.get("/api/energy/daily-trend")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(body), 92)  # 92 operating days

    def test_power_factor_endpoint(self):
        """Verify /api/energy/power-factor evaluates compliance threshold."""
        status_code, body = self.client.get("/api/energy/power-factor", {"threshold": "0.90"})
        self.assertEqual(status_code, 200)
        self.assertEqual(body["total_readings"], 22080)
        self.assertEqual(body["low_pf_events_count"], 0)  # All readings >= 0.9100

    # ==========================================
    # Production Analytics Endpoints
    # ==========================================

    def test_production_summary_endpoint(self):
        """Verify /api/production/summary returns output, rework, and OEE assessments."""
        status_code, body = self.client.get("/api/production/summary")
        self.assertEqual(status_code, 200)
        self.assertEqual(body["target_qty"], 2914560)
        self.assertEqual(body["actual_qty"], 2424184)
        self.assertEqual(body["good_qty"], 2378960)
        self.assertEqual(body["reject_qty"], 45224)
        self.assertEqual(body["rework_qty"], 24852)
        self.assertEqual(body["downtime_min"], 60290)
        self.assertTrue(body["quantity_balance_valid"])
        # Check OEE status block
        self.assertEqual(body["oee"]["status"], "unavailable")
        self.assertEqual(body["oee"]["quality_rate"], "98.13")
        self.assertIsNone(body["oee"]["availability"])

    def test_production_by_line_endpoint(self):
        """Verify /api/production/by-line returns 4 lines."""
        status_code, body = self.client.get("/api/production/by-line")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(body), 4)
        lines = [item["line_id"] for item in body]
        self.assertIn("SMT-L1", lines)
        self.assertIn("FAL-L1", lines)

    def test_production_by_product_endpoint(self):
        """Verify /api/production/by-product returns 3 product models."""
        status_code, body = self.client.get("/api/production/by-product")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(body), 3)

    def test_production_by_shift_endpoint(self):
        """Verify /api/production/by-shift returns 3 shifts."""
        status_code, body = self.client.get("/api/production/by-shift")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(body), 3)

    def test_downtime_by_reason_endpoint(self):
        """Verify /api/production/downtime-by-reason returns downtime breakdown."""
        status_code, body = self.client.get("/api/production/downtime-by-reason")
        self.assertEqual(status_code, 200)
        self.assertGreater(len(body), 0)

    def test_production_daily_trend_endpoint(self):
        """Verify /api/production/daily-trend returns daily time-series."""
        status_code, body = self.client.get("/api/production/daily-trend")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(body), 92)

    # ==========================================
    # Energy Intensity & SEC Endpoints
    # ==========================================

    def test_process_energy_intensity_endpoint(self):
        """Verify /api/energy-intensity/process returns line SEC without Cartesian inflation."""
        status_code, body = self.client.get("/api/energy-intensity/process")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(body["lines"]), 4)
        # SMT Area combined SEC is 0.3547 kWh/board
        self.assertEqual(body["smt_summary"]["overall_process_sec_kwh_per_board"], "0.3547")
        # SMT-L1 line SEC is 0.3567 kWh/board
        smt_l1 = [l for l in body["lines"] if l["line_id"] == "SMT-L1"][0]
        self.assertEqual(smt_l1["process_sec_actual_kwh_per_unit"], "0.3567")

    def test_factory_energy_intensity_endpoint(self):
        """Verify /api/energy-intensity/factory aggregates 5 meters and segregates utilities."""
        status_code, body = self.client.get("/api/energy-intensity/factory")
        self.assertEqual(status_code, 200)
        self.assertEqual(body["total_plant_energy_kwh"], "1958088.3130")
        self.assertEqual(body["final_assembly_actual_output"], 993052)
        self.assertEqual(body["factory_sec_kwh_per_finished_unit"], "1.9718")
        self.assertEqual(len(body["facility_utilities"]["meters"]), 3)

    def test_product_process_energy_endpoint(self):
        """Verify /api/energy-intensity/product returns product process allocation."""
        status_code, body = self.client.get("/api/energy-intensity/product")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(body), 3)

    def test_zero_production_energy_endpoint(self):
        """Verify /api/energy-intensity/zero-production returns standby totals."""
        status_code, body = self.client.get("/api/energy-intensity/zero-production")
        self.assertEqual(status_code, 200)
        self.assertEqual(body["total_zero_production_hours"], 155)
        self.assertEqual(body["total_zero_production_energy_kwh"], "15553.9580")

    # ==========================================
    # Anomaly Detection Endpoints
    # ==========================================

    def test_anomalies_statistical_endpoint(self):
        """Verify /api/anomalies/statistical detects Z-score anomalies."""
        status_code, body = self.client.get("/api/anomalies/statistical", {"threshold_z": 3.0})
        self.assertEqual(status_code, 200)
        self.assertGreater(body["total_anomalies_detected"], 0)
        top = body["anomalies"][0]
        self.assertIn("anomaly_type", top)
        self.assertIn("severity", top)

    def test_anomalies_rolling_endpoint(self):
        """Verify /api/anomalies/rolling detects rolling deviations."""
        status_code, body = self.client.get("/api/anomalies/rolling", {"threshold_z": 3.0, "window_size": 24})
        self.assertEqual(status_code, 200)
        self.assertEqual(body["window_size_hours"], 24)
        self.assertGreater(body["total_anomalies_detected"], 0)

    def test_anomalies_low_power_factor_endpoint(self):
        """Verify /api/anomalies/low-power-factor evaluates compliance."""
        status_code, body = self.client.get("/api/anomalies/low-power-factor", {"threshold": "0.90"})
        self.assertEqual(status_code, 200)
        self.assertEqual(body["total_anomalies_detected"], 0)

    def test_anomalies_zero_production_endpoint(self):
        """Verify /api/anomalies/zero-production detects standby line stoppage events."""
        status_code, body = self.client.get("/api/anomalies/zero-production")
        self.assertEqual(status_code, 200)
        self.assertEqual(body["total_events_detected"], 155)
        self.assertEqual(body["total_standby_energy_kwh"], "15553.9580")

    def test_anomalies_all_unified_endpoint(self):
        """Verify /api/anomalies/all aggregates all detectors."""
        status_code, body = self.client.get("/api/anomalies/all", {"plant_id": "IN-TN-01"})
        self.assertEqual(status_code, 200)
        self.assertEqual(body["plant_id"], "IN-TN-01")
        self.assertIn("statistical_zscore", body)
        self.assertIn("rolling_baseline", body)
        self.assertIn("low_power_factor", body)
        self.assertIn("zero_production_standby", body)

    # ==========================================
    # Validation and Error Handling
    # ==========================================

    def test_invalid_time_range_returns_400(self):
        """Verify start_time > end_time returns HTTP 400 Bad Request."""
        status_code, body = self.client.get(
            "/api/anomalies/statistical",
            {"start_time": "2026-10-02T00:00:00", "end_time": "2026-10-01T00:00:00"},
        )
        self.assertEqual(status_code, 400)
        self.assertIn("Invalid time range", body["detail"])

    def test_invalid_date_range_returns_400(self):
        """Verify start_date > end_date returns HTTP 400 Bad Request."""
        status_code, body = self.client.get(
            "/api/production/summary",
            {"start_date": "2026-10-02", "end_date": "2026-10-01"},
        )
        self.assertEqual(status_code, 400)
        self.assertIn("Invalid date range", body["detail"])

    def test_openapi_schema_contains_all_21_endpoints(self):
        """Verify FastAPI OpenAPI documentation lists all 21 endpoints."""
        openapi = app.openapi()
        paths = openapi["paths"]
        expected_endpoints = [
            "/api/health",
            "/api/energy/summary",
            "/api/energy/by-meter",
            "/api/energy/by-area",
            "/api/energy/daily-trend",
            "/api/energy/power-factor",
            "/api/production/summary",
            "/api/production/by-line",
            "/api/production/by-product",
            "/api/production/by-shift",
            "/api/production/downtime-by-reason",
            "/api/production/daily-trend",
            "/api/energy-intensity/process",
            "/api/energy-intensity/factory",
            "/api/energy-intensity/product",
            "/api/energy-intensity/zero-production",
            "/api/anomalies/statistical",
            "/api/anomalies/rolling",
            "/api/anomalies/low-power-factor",
            "/api/anomalies/zero-production",
            "/api/anomalies/all",
        ]
        for ep in expected_endpoints:
            self.assertIn(ep, paths, f"Endpoint {ep} missing from OpenAPI schema")


if __name__ == "__main__":
    unittest.main()
