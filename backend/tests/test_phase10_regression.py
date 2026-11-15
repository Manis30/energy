"""
Regression test suite for Phase 10.1 findings resolution and contract alignment.

Validates:
1. Omitted dates default evaluation window (latest 24-hour operational window).
2. Explicit latest-day evaluation scope.
3. Explicit historical evaluation scope.
4. Strict prior-only baseline boundaries (zero baseline leakage).
5. Empty evaluation windows handling.
6. Zero-energy vs missing data analytics distinction.
7. Anomaly API limit handling.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_engine, get_session_factory
from app.main import app
from app.models import FactEnergyMeterHourly
from app.services.anomaly_detection import (
    detect_all_anomalies,
    detect_energy_statistical_anomalies,
    detect_rolling_baseline_anomalies,
)
from app.services.energy_analytics import get_energy_summary


class TestPhase10Regression(unittest.TestCase):
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
        self.session.rollback()
        self.session.close()

    # =========================================================================
    # 1. Omitted dates vs explicit latest_day vs historical scope
    # =========================================================================

    def test_omitted_dates_defaults_to_latest_day_window(self):
        """Verify omitting start_time and end_time evaluates the latest 24h operational window."""
        res = detect_energy_statistical_anomalies(self.session)
        self.assertIn("evaluation_period", res)
        eval_p = res["evaluation_period"]
        self.assertEqual(eval_p["evaluation_scope"], "latest_day")

        eval_start = datetime.fromisoformat(eval_p["start_time"])
        eval_end = datetime.fromisoformat(eval_p["end_time"])
        self.assertEqual(eval_end - eval_start, timedelta(days=1))

        # Baseline period must be exactly lookback_days prior to eval_start
        base_p = res["baseline_period"]
        b_start = datetime.fromisoformat(base_p["start_time"])
        b_end = datetime.fromisoformat(base_p["end_time"])
        self.assertEqual(b_end, eval_start)
        self.assertEqual(b_end - b_start, timedelta(days=30))

    def test_explicit_latest_day_scope(self):
        """Verify explicit evaluation_scope='latest_day' matches omitted-dates window."""
        res_default = detect_energy_statistical_anomalies(self.session)
        res_explicit = detect_energy_statistical_anomalies(
            self.session, evaluation_scope="latest_day"
        )
        self.assertEqual(
            res_default["evaluation_period"]["start_time"],
            res_explicit["evaluation_period"]["start_time"],
        )
        self.assertEqual(
            res_default["evaluation_period"]["end_time"],
            res_explicit["evaluation_period"]["end_time"],
        )

    def test_explicit_historical_scope(self):
        """Verify explicit evaluation_scope='historical' evaluates the full historical window with prior baseline."""
        res = detect_energy_statistical_anomalies(
            self.session, evaluation_scope="historical", lookback_days=30
        )
        eval_p = res["evaluation_period"]
        base_p = res["baseline_period"]
        self.assertEqual(eval_p["evaluation_scope"], "historical")

        b_start = datetime.fromisoformat(base_p["start_time"])
        b_end = datetime.fromisoformat(base_p["end_time"])
        eval_start = datetime.fromisoformat(eval_p["start_time"])
        eval_end = datetime.fromisoformat(eval_p["end_time"])

        # Baseline is initial 30 days of the dataset
        self.assertEqual(b_end - b_start, timedelta(days=30))
        # Historical evaluation starts immediately after the initial baseline
        self.assertEqual(eval_start, b_end)
        self.assertGreater(eval_end, eval_start)
        # In historical scope, multiple extreme readings are identified
        self.assertGreater(res["total_anomalies_detected"], 0)

    # =========================================================================
    # 2. Strict Prior-Only Baseline Boundaries (No Data Leakage)
    # =========================================================================

    def test_strict_prior_only_baseline_boundaries(self):
        """Verify that all baseline timestamps are strictly prior to eval_start (no look-ahead leakage)."""
        res = detect_energy_statistical_anomalies(
            self.session, evaluation_scope="historical", lookback_days=30
        )
        eval_start = datetime.fromisoformat(res["evaluation_period"]["start_time"])
        b_end = datetime.fromisoformat(res["baseline_period"]["end_time"])

        self.assertLessEqual(b_end, eval_start)

        for anom in res["anomalies"]:
            anom_ts = datetime.fromisoformat(anom["timestamp"])
            # Every anomaly observation must occur at or after eval_start
            self.assertGreaterEqual(anom_ts, eval_start)

    def test_rolling_baseline_strict_preceding_history(self):
        """Verify rolling detector uses strictly preceding observations."""
        res = detect_rolling_baseline_anomalies(
            self.session,
            window_size=24,
            min_observations=12,
            evaluation_scope="historical",
        )
        for anom in res["anomalies"]:
            self.assertTrue(anom["context_flags"]["current_observation_excluded"])
            self.assertGreaterEqual(anom["context_flags"]["historical_observations_used"], 12)
            self.assertLessEqual(anom["context_flags"]["historical_observations_used"], 24)

    # =========================================================================
    # 3. Empty Windows and Edge Cases
    # =========================================================================

    def test_empty_evaluation_window_handling(self):
        """Verify querying a future out-of-range window returns 0 anomalies gracefully."""
        res = detect_energy_statistical_anomalies(
            self.session,
            start_time=datetime(2035, 1, 1),
            end_time=datetime(2035, 1, 2),
        )
        self.assertEqual(res["total_anomalies_detected"], 0)
        self.assertEqual(len(res["anomalies"]), 0)
        # All groups report insufficient history
        self.assertEqual(res["qualified_groups_count"], 0)

    def test_rolling_empty_window_handling(self):
        """Verify rolling baseline on out-of-range dates returns 0 anomalies gracefully."""
        res = detect_rolling_baseline_anomalies(
            self.session,
            start_time=datetime(2035, 1, 1),
            end_time=datetime(2035, 1, 2),
        )
        self.assertEqual(res["total_anomalies_detected"], 0)
        self.assertEqual(len(res["anomalies"]), 0)

    # =========================================================================
    # 4. Zero-Energy vs Missing Data Analytics Distinction
    # =========================================================================

    def test_missing_data_analytics_contract(self):
        """Verify that when no observations exist, total_consumption_kwh is None and data_available is False."""
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

    def test_actual_zero_energy_analytics_contract(self):
        """Verify that when actual zero consumption is observed, total_consumption_kwh is 0 and data_available is True."""
        test_ts = datetime(2035, 5, 1, 10, 0, 0)
        zero_row = FactEnergyMeterHourly(
            meter_reading_id="MTR-REG-ZERO-TEST",
            timestamp=test_ts,
            date=test_ts.date(),
            plant_id="IN-TN-01",
            meter_id="MTR-SMT",
            area="SMT",
            energy_source="GRID",
            consumption_kwh=Decimal("0.0000"),
            demand_kw=Decimal("0.0000"),
            power_factor=Decimal("0.9600"),
            tariff_inr_per_kwh=Decimal("7.5000"),
            cost_inr=Decimal("0.00"),
            co2e_kg=Decimal("0.00"),
            reading_quality="VALID",
        )
        self.session.add(zero_row)
        self.session.flush()

        summary = get_energy_summary(
            self.session,
            start_date=date(2035, 5, 1),
            end_date=date(2035, 5, 1),
        )
        self.assertTrue(summary["data_available"])
        self.assertTrue(summary["consumption_data_available"])
        self.assertEqual(summary["total_consumption_kwh"], Decimal("0.0000"))
        self.assertEqual(summary["total_readings"], 1)
        self.assertEqual(summary["avg_power_factor"], Decimal("0.9600"))

    # =========================================================================
    # 5. Anomaly API Limit Handling
    # =========================================================================

    def test_api_limit_parameter_capping(self):
        """Verify API limit parameter restricts returned array size while preserving total_anomalies_detected."""
        resp = self.client.get(
            "/api/anomalies/statistical",
            params={"threshold_z": 3.0, "limit": 3, "evaluation_scope": "historical"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["total_anomalies_detected"], 3)
        self.assertEqual(len(data["anomalies"]), 3)

    def test_api_invalid_evaluation_scope_rejected(self):
        """Verify passing an unrecognized evaluation scope returns HTTP 422 Unprocessable Entity."""
        resp = self.client.get(
            "/api/anomalies/statistical",
            params={"evaluation_scope": "invalid_scope"},
        )
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()

