"""
Regression tests for Backend Analytics Accuracy and Reliability Corrections (Phase 9 - Task 2).

Verifies:
1. Zero-production standby utility filtering (plant, date, and timestamp isolation).
2. Standardized power-factor thresholds (0.90 engineering monitoring threshold).
3. Product-level energy intensity (stage-specific valid SEC, decoupled cross-stage unavailable).
4. Anomaly API parameter validation bounds and safe failure responses.
5. Energy-weighted power-factor aggregation and zero-energy safe handling.
6. Process-meter join scalability and multi-line safe topology validation.
"""

from datetime import date, datetime
from decimal import Decimal
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import DEFAULT_POWER_FACTOR_THRESHOLD
from app.db import get_engine, get_session_factory
from app.main import app
from app.services.agent.tool_registry import get_all_tools
from app.services.anomaly_detection import (
    detect_all_anomalies,
    detect_energy_statistical_anomalies,
    detect_low_power_factor_anomalies,
    detect_rolling_baseline_anomalies,
    detect_zero_production_standby_anomalies,
)
from app.services.energy_analytics import (
    get_energy_by_area,
    get_energy_by_meter,
    get_energy_daily_trend,
    get_energy_summary,
    get_power_factor_summary,
)
from app.services.energy_intensity import (
    get_product_process_energy,
    validate_line_meter_topology,
)


class TestAccuracyCorrections(unittest.TestCase):
    """Test suite covering accuracy and reliability defect corrections."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        if cls.engine is None:
            raise RuntimeError("Database engine not available for tests.")
        cls.session_factory = get_session_factory()
        cls.client = TestClient(app)

    def setUp(self):
        self.session = self.session_factory()

    def tearDown(self):
        self.session.close()

    # =========================================================================
    # Step 2: Zero-Production Standby Utility Filtering
    # =========================================================================

    def test_zero_production_utility_all_plants(self):
        """Verify utility totals are strictly computed during zero-production timestamps across all plants."""
        res = detect_zero_production_standby_anomalies(self.session)
        self.assertEqual(res["total_events_detected"], 155)

        util_totals = res["facility_utilities_status"]["overall_utility_totals"]
        # Exactly 153 distinct timestamps exist with actual_qty = 0 across lines
        self.assertEqual(util_totals["MTR-CHILLER"]["readings"], 153)
        self.assertEqual(util_totals["MTR-COMPRESSOR"]["readings"], 153)
        self.assertEqual(util_totals["MTR-HVAC"]["readings"], 153)

        self.assertEqual(util_totals["MTR-CHILLER"]["consumption_kwh"], Decimal("12397.3510"))
        self.assertEqual(util_totals["MTR-COMPRESSOR"]["consumption_kwh"], Decimal("12776.4400"))
        self.assertEqual(util_totals["MTR-HVAC"]["consumption_kwh"], Decimal("12401.6530"))

    def test_zero_production_utility_individual_plants(self):
        """Verify utility totals respect plant filter and match each plant's zero-production timestamps."""
        # 1. Plant IN-TN-01
        res_tn = detect_zero_production_standby_anomalies(self.session, plant_id="IN-TN-01")
        util_tn = res_tn["facility_utilities_status"]["overall_utility_totals"]
        self.assertGreater(res_tn["total_events_detected"], 0)
        # Distinct zero-production timestamps for TN is 92
        tn_count = util_tn["MTR-HVAC"]["readings"]
        self.assertEqual(tn_count, 92)
        self.assertEqual(util_tn["MTR-COMPRESSOR"]["readings"], 92)
        self.assertEqual(util_tn["MTR-CHILLER"]["readings"], 92)

        # 2. Plant IN-KA-01
        res_ka = detect_zero_production_standby_anomalies(self.session, plant_id="IN-KA-01")
        util_ka = res_ka["facility_utilities_status"]["overall_utility_totals"]
        self.assertGreater(res_ka["total_events_detected"], 0)
        # Distinct zero-production timestamps for KA is 61
        ka_count = util_ka["MTR-HVAC"]["readings"]
        self.assertEqual(ka_count, 61)
        self.assertEqual(util_ka["MTR-COMPRESSOR"]["readings"], 61)
        self.assertEqual(util_ka["MTR-CHILLER"]["readings"], 61)

        # Reconciliation: 92 + 61 = 153 distinct plant-timestamps
        self.assertEqual(tn_count + ka_count, 153)

    def test_zero_production_utility_restricted_date_range(self):
        """Verify utility totals strictly respect start_time and end_time range."""
        start = datetime(2026, 8, 1, 0, 0, 0)
        end = datetime(2026, 8, 10, 23, 59, 59)
        res = detect_zero_production_standby_anomalies(
            self.session,
            start_time=start,
            end_time=end,
        )
        util_totals = res["facility_utilities_status"]["overall_utility_totals"]
        for m in ("MTR-HVAC", "MTR-COMPRESSOR", "MTR-CHILLER"):
            self.assertLess(util_totals[m]["readings"], 153)
            self.assertGreater(util_totals[m]["readings"], 0)

    def test_zero_production_utility_no_zero_production_period(self):
        """Verify that when no zero-production events exist, utility totals safely return 0 readings and 0 kWh."""
        # Future date range with 0 production events
        start = datetime(2030, 1, 1, 0, 0, 0)
        end = datetime(2030, 1, 2, 0, 0, 0)
        res = detect_zero_production_standby_anomalies(
            self.session,
            start_time=start,
            end_time=end,
        )
        self.assertEqual(res["total_events_detected"], 0)
        util_totals = res["facility_utilities_status"]["overall_utility_totals"]
        for m in ("MTR-HVAC", "MTR-COMPRESSOR", "MTR-CHILLER"):
            self.assertEqual(util_totals[m]["readings"], 0)
            self.assertEqual(util_totals[m]["consumption_kwh"], Decimal("0.0000"))

    def test_zero_production_utility_exact_reconciliation(self):
        """Cross-check utility query against raw DB records for IN-TN-01."""
        res = detect_zero_production_standby_anomalies(self.session, plant_id="IN-TN-01")
        hvac_reported = res["facility_utilities_status"]["overall_utility_totals"]["MTR-HVAC"]["consumption_kwh"]

        # Directly query Neon for HVAC energy during IN-TN-01 zero-production timestamps
        raw_sql = """
            SELECT SUM(consumption_kwh)
            FROM fact_energy_meter_hourly
            WHERE plant_id = 'IN-TN-01'
              AND meter_id = 'MTR-HVAC'
              AND timestamp IN (
                  SELECT DISTINCT event_ts
                  FROM fact_hourly_production
                  WHERE plant_id = 'IN-TN-01' AND actual_qty = 0
              )
        """
        raw_hvac = self.session.execute(text(raw_sql)).scalar()
        self.assertEqual(hvac_reported, round(Decimal(str(raw_hvac)), 4))

    # =========================================================================
    # Step 3: Standardize Power-Factor Thresholds
    # =========================================================================

    def test_power_factor_threshold_standardization(self):
        """Verify 0.90 is consistently configured as the application monitoring threshold across all services."""
        self.assertEqual(DEFAULT_POWER_FACTOR_THRESHOLD, Decimal("0.90"))

        # Energy analytics power factor summary default
        pf_summary = get_power_factor_summary(self.session)
        self.assertEqual(pf_summary["threshold"], Decimal("0.90"))

        # Anomaly detection low power factor default
        lpf_anom = detect_low_power_factor_anomalies(self.session)
        self.assertEqual(lpf_anom["threshold"], 0.90)

        # Unified anomaly suite default
        all_anom = detect_all_anomalies(self.session)
        self.assertEqual(all_anom["low_power_factor"]["threshold"], 0.90)

        # Agent tools registry threshold check
        tools = get_all_tools()
        pf_tool = tools["power_factor_summary"]
        schema = pf_tool.args_schema.model_fields
        self.assertEqual(schema["low_pf_threshold"].default, Decimal("0.90"))

    # =========================================================================
    # Step 4: Product-Level Energy Intensity Corrections
    # =========================================================================

    def test_product_sec_stage_specific_and_finished_phone_unavailable(self):
        """Verify stage SEC is computed accurately while cross-stage finished-phone SEC is unavailable."""
        products = get_product_process_energy(self.session)
        self.assertEqual(len(products), 3)

        for p in products:
            # Stage-specific SMT SEC (kWh / board)
            self.assertIsNotNone(p["smt_process_sec_kwh_per_board"])
            expected_smt_sec = round(p["smt_process_kwh"] / p["smt_actual_units"], 4)
            self.assertEqual(p["smt_process_sec_kwh_per_board"], expected_smt_sec)

            # Stage-specific FAL SEC (kWh / phone)
            self.assertIsNotNone(p["fal_process_sec_kwh_per_phone"])
            expected_fal_sec = round(p["fal_process_kwh"] / p["fal_actual_units"], 4)
            self.assertEqual(p["fal_process_sec_kwh_per_phone"], expected_fal_sec)

            # Cross-stage finished-phone SEC must be None with explicit explanation
            self.assertIsNone(p["finished_phone_process_sec_kwh_per_unit"])
            self.assertIn("UNAVAILABLE", p["finished_phone_sec_status"])
            self.assertIn("decoupled stages", p["scope_note"])

    # =========================================================================
    # Step 5: Validate Anomaly API Parameters
    # =========================================================================

    def test_anomaly_api_parameter_validation_bounds(self):
        """Verify API endpoints return HTTP 422 or 400 for out-of-bound anomaly parameters."""
        # 1. Statistical anomalies: threshold_z <= 0
        resp = self.client.get("/api/anomalies/statistical", params={"threshold_z": 0})
        self.assertEqual(resp.status_code, 422)

        # 2. Statistical anomalies: min_observations < 2
        resp = self.client.get("/api/anomalies/statistical", params={"min_observations": 1})
        self.assertEqual(resp.status_code, 422)

        # 3. Rolling anomalies: min_observations > window_size
        resp = self.client.get("/api/anomalies/rolling", params={"window_size": 10, "min_observations": 15})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("cannot exceed window_size", resp.json()["detail"])

        # 4. Low power factor: threshold > 1.0 or <= 0
        resp = self.client.get("/api/anomalies/low-power-factor", params={"threshold": "1.5"})
        self.assertEqual(resp.status_code, 422)

        # 5. Invalid time range: start_time > end_time
        resp = self.client.get(
            "/api/anomalies/statistical",
            params={
                "start_time": "2025-02-01T00:00:00",
                "end_time": "2025-01-01T00:00:00",
            },
        )
        self.assertEqual(resp.status_code, 400)

    def test_anomaly_api_limit_parameter(self):
        """Verify optional limit parameter caps returned records while preserving total_anomalies_detected."""
        # Query with explicit historical evaluation scope to verify capping over a multi-anomaly window
        resp = self.client.get(
            "/api/anomalies/statistical",
            params={"threshold_z": 3.0, "limit": 5, "evaluation_scope": "historical"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["total_anomalies_detected"], 5)
        self.assertEqual(len(data["anomalies"]), 5)

        # Also verify default latest_day evaluation scope responds safely
        resp_latest = self.client.get(
            "/api/anomalies/statistical",
            params={"threshold_z": 3.0, "limit": 5},
        )
        self.assertEqual(resp_latest.status_code, 200)
        data_latest = resp_latest.json()
        self.assertEqual(data_latest["evaluation_period"]["evaluation_scope"], "latest_day")
        self.assertLessEqual(len(data_latest["anomalies"]), 5)

    # =========================================================================
    # Step 6: Power-Factor Aggregation (Energy-Weighted)
    # =========================================================================

    def test_energy_weighted_power_factor_aggregation(self):
        """Verify power factor is aggregated using energy weighting: sum(pf * kwh) / sum(kwh)."""
        summary = get_energy_summary(self.session)

        # Verify against exact DB computation
        raw_sql = """
            SELECT
                SUM(power_factor * consumption_kwh) / SUM(consumption_kwh) as weighted_pf,
                AVG(power_factor) as arithmetic_pf
            FROM fact_energy_meter_hourly
        """
        row = self.session.execute(text(raw_sql)).fetchone()
        expected_weighted = round(Decimal(str(row[0])), 4)
        expected_arithmetic = round(Decimal(str(row[1])), 4)

        self.assertEqual(summary["avg_power_factor"], expected_weighted)
        self.assertEqual(summary["arithmetic_avg_power_factor"], expected_arithmetic)

        # Verify meter and area breakdowns also provide energy-weighted average
        by_meter = get_energy_by_meter(self.session)
        for m in by_meter:
            self.assertIsNotNone(m["avg_power_factor"])
            self.assertIsNotNone(m["arithmetic_avg_power_factor"])

        by_area = get_energy_by_area(self.session)
        for a in by_area:
            self.assertIsNotNone(a["avg_power_factor"])
            self.assertIsNotNone(a["arithmetic_avg_power_factor"])

        daily = get_energy_daily_trend(self.session)
        for d in daily:
            self.assertIsNotNone(d["avg_power_factor"])
            self.assertIsNotNone(d["arithmetic_avg_power_factor"])

    def test_power_factor_zero_energy_safe_handling(self):
        """Verify that periods with no observations preserve honest provenance: data_available=False, values None."""
        summary = get_energy_summary(
            self.session,
            start_date=date(2035, 1, 1),
            end_date=date(2035, 1, 2),
        )
        self.assertFalse(summary["data_available"])
        self.assertFalse(summary["consumption_data_available"])
        self.assertIsNone(summary["total_consumption_kwh"])
        self.assertIsNone(summary["avg_power_factor"])
        self.assertIsNone(summary["arithmetic_avg_power_factor"])
        self.assertEqual(summary["total_readings"], 0)
        self.assertEqual(summary["distinct_hours"], 0)

    def test_actual_zero_energy_observation_handling(self):
        """Verify actual zero-energy observations return total_consumption_kwh = 0 with data_available = True and safe PF fallback."""
        from app.models import FactEnergyMeterHourly
        test_ts = datetime(2035, 6, 1, 12, 0, 0)
        zero_reading = FactEnergyMeterHourly(
            meter_reading_id="MTR-TEST-ZERO-PF",
            timestamp=test_ts,
            date=test_ts.date(),
            plant_id="IN-TN-01",
            meter_id="MTR-SMT",
            area="SMT",
            energy_source="GRID",
            consumption_kwh=Decimal("0.0000"),
            demand_kw=Decimal("0.0000"),
            power_factor=Decimal("0.9500"),
            tariff_inr_per_kwh=Decimal("7.5000"),
            cost_inr=Decimal("0.00"),
            co2e_kg=Decimal("0.00"),
            reading_quality="VALID",
        )
        try:
            self.session.add(zero_reading)
            self.session.flush()

            summary = get_energy_summary(
                self.session,
                start_date=date(2035, 6, 1),
                end_date=date(2035, 6, 1),
            )
            self.assertTrue(summary["data_available"])
            self.assertTrue(summary["consumption_data_available"])
            self.assertEqual(summary["total_consumption_kwh"], Decimal("0.0000"))
            self.assertEqual(summary["total_readings"], 1)
            # Power factor falls back to arithmetic mean via COALESCE, safely avoiding ZeroDivisionError
            self.assertEqual(summary["avg_power_factor"], Decimal("0.9500"))
            self.assertEqual(summary["arithmetic_avg_power_factor"], Decimal("0.9500"))
        finally:
            self.session.rollback()

    # =========================================================================
    # Step 7: Process-Meter Join Scalability
    # =========================================================================

    def test_current_topology_passes_verification(self):
        """Verify current 1 SMT + 1 FAL line per plant topology passes without error."""
        validate_line_meter_topology(self.session)
        validate_line_meter_topology(self.session, plant_id="IN-TN-01")
        validate_line_meter_topology(self.session, plant_id="IN-KA-01")

    def test_simulated_multi_line_fails_safely(self):
        """Verify that if multiple lines of the same type exist in a single plant, it fails safely with ValueError."""
        # Mock session returning a violation (2 SMT lines in IN-TN-01)
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchall.return_value = [
            ("IN-TN-01", "SMT", 2)
        ]

        with self.assertRaises(ValueError) as ctx:
            validate_line_meter_topology(mock_session, plant_id="IN-TN-01")
        self.assertIn("Multi-line topology limitation", str(ctx.exception))
        self.assertIn("Plant 'IN-TN-01' has 2 lines configured for 'SMT'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
