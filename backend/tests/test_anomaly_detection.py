"""
Integration and edge-case tests for Deterministic Anomaly Detection Services.

Verifies:
1. Energy Statistical Z-Score Anomaly Detection
2. Rolling Historical Baseline Anomaly Detection (Strict current-observation exclusion)
3. Low Power Factor Compliance Monitoring
4. Zero-Production Period Standby Energy Detection (Utility segregation, no fake waste claims)
5. Zero Variance and Insufficient Observation Safe Handling
6. Unified Anomaly Suite Execution
"""

from datetime import datetime
from decimal import Decimal
import unittest

from app.db import get_engine, get_session_factory
from app.services.anomaly_detection import (
    detect_all_anomalies,
    detect_energy_statistical_anomalies,
    detect_low_power_factor_anomalies,
    detect_rolling_baseline_anomalies,
    detect_zero_production_standby_anomalies,
)


class TestAnomalyDetectionServices(unittest.TestCase):
    """Test suite validating deterministic anomaly detection logic against live Neon data."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        if cls.engine is None:
            raise RuntimeError("Database engine not available for tests.")
        cls.session_factory = get_session_factory()

    def setUp(self):
        self.session = self.session_factory()

    def tearDown(self):
        self.session.close()

    def test_energy_statistical_anomalies_detection(self):
        """Verify Z-score anomaly detection meets output contract and thresholds."""
        res = detect_energy_statistical_anomalies(
            self.session,
            threshold_z=3.0,
            min_observations=10,
        )

        self.assertEqual(res["analysis_type"], "statistical_zscore")
        self.assertEqual(res["threshold_z"], 3.0)
        self.assertEqual(res["eligible_groups_count"], 10)  # 2 plants * 5 meters
        self.assertEqual(len(res["zero_variance_groups"]), 0)
        self.assertEqual(len(res["insufficient_observations_groups"]), 0)

        # There are statistically rare extreme hourly readings across 22,080 rows
        self.assertGreater(res["total_anomalies_detected"], 0)
        self.assertLessEqual(res["total_anomalies_detected"], 100)

        # Inspect contract fields on top anomaly
        top = res["anomalies"][0]
        self.assertIn(top["anomaly_type"], ["ENERGY_STATISTICAL_SPIKE", "ENERGY_STATISTICAL_DROP"])
        self.assertIn(top["plant_id"], ["IN-TN-01", "IN-KA-01"])
        self.assertIn(top["meter_id"], ["MTR-SMT", "MTR-FAL", "MTR-HVAC", "MTR-COMPRESSOR", "MTR-CHILLER"])
        self.assertIsInstance(top["actual_value"], Decimal)
        self.assertIsInstance(top["baseline_value"], Decimal)
        self.assertIsInstance(top["deviation_score"], float)
        self.assertGreaterEqual(abs(top["deviation_score"]), 3.0)
        self.assertIn(top["severity"], ["HIGH", "CRITICAL"])
        self.assertTrue(len(top["explanation"]) > 20)
        self.assertIn("sample_size", top["context_flags"])
        self.assertEqual(top["context_flags"]["sample_size"], 2208)

    def test_statistical_anomalies_safe_guards_and_edge_cases(self):
        """Verify edge cases: high min_observations causes safe bypass without errors."""
        # 1. Require more observations than exist
        res = detect_energy_statistical_anomalies(
            self.session,
            plant_id="IN-TN-01",
            meter_id="MTR-SMT",
            min_observations=5000,  # Only 2208 exist per meter-plant
        )
        self.assertEqual(res["total_anomalies_detected"], 0)
        self.assertEqual(res["eligible_groups_count"], 0)
        self.assertIn("IN-TN-01_MTR-SMT", res["insufficient_observations_groups"])

        # 2. Narrow date window resulting in zero observations
        res_empty = detect_energy_statistical_anomalies(
            self.session,
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 2),
        )
        self.assertEqual(res_empty["total_anomalies_detected"], 0)
        self.assertEqual(len(res_empty["anomalies"]), 0)

    def test_rolling_baseline_anomalies_and_historical_exclusion(self):
        """Verify rolling baseline window uses strictly historical rows and excludes current."""
        res = detect_rolling_baseline_anomalies(
            self.session,
            plant_id="IN-KA-01",
            meter_id="MTR-HVAC",
            window_size=24,
            min_observations=12,
            threshold_z=3.0,
        )

        self.assertEqual(res["analysis_type"], "rolling_baseline")
        self.assertEqual(res["window_size_hours"], 24)
        self.assertGreater(res["total_anomalies_detected"], 0)

        # Verify contract and strictly historical flag
        for anom in res["anomalies"]:
            self.assertEqual(anom["plant_id"], "IN-KA-01")
            self.assertEqual(anom["meter_id"], "MTR-HVAC")
            self.assertIn(anom["anomaly_type"], ["ROLLING_BASELINE_SPIKE", "ROLLING_BASELINE_DROP"])
            self.assertTrue(anom["context_flags"]["current_observation_excluded"])
            self.assertGreaterEqual(anom["context_flags"]["historical_observations_used"], 12)
            self.assertLessEqual(anom["context_flags"]["historical_observations_used"], 24)
            self.assertGreaterEqual(abs(anom["deviation_score"]), 3.0)

    def test_low_power_factor_monitoring(self):
        """Verify low power factor detection conforms to tariff rule constraints."""
        # 1. Standard regulatory threshold 0.90: Neon dataset has all readings >= 0.9100
        res_default = detect_low_power_factor_anomalies(
            self.session,
            threshold=Decimal("0.90"),
        )
        self.assertEqual(res_default["analysis_type"], "low_power_factor")
        self.assertEqual(res_default["threshold"], 0.90)
        self.assertEqual(res_default["total_anomalies_detected"], 0)

        # 2. Configurable threshold 0.93: Detects lower tier power factor readings safely
        res_93 = detect_low_power_factor_anomalies(
            self.session,
            threshold=Decimal("0.93"),
        )
        self.assertGreater(res_93["total_anomalies_detected"], 0)
        anom = res_93["anomalies"][0]
        self.assertEqual(anom["anomaly_type"], "LOW_POWER_FACTOR")
        self.assertLess(anom["actual_value"], Decimal("0.9300"))
        self.assertGreaterEqual(anom["actual_value"], Decimal("0.9100"))
        self.assertFalse(anom["context_flags"]["tariff_penalty_claimed"])
        self.assertIn("monetary penalty requires site-specific utility tariff", anom["context_flags"]["note"])

    def test_zero_production_standby_anomalies_and_utility_segregation(self):
        """Verify zero-production standby detection preserves meter mapping and utility isolation."""
        res = detect_zero_production_standby_anomalies(self.session)

        # Exactly 155 zero-production line hours across SMT and FAL
        self.assertEqual(res["total_events_detected"], 155)
        self.assertEqual(res["total_standby_energy_kwh"], Decimal("15553.9580"))
        self.assertEqual(res["total_stoppage_minutes"], 9300)
        self.assertEqual(res["smt_standby_energy_kwh"], Decimal("9178.7030"))
        self.assertEqual(res["fal_standby_energy_kwh"], Decimal("6375.2550"))

        # Check utility segregation
        util_status = res["facility_utilities_status"]
        self.assertTrue(util_status["segregated"])
        self.assertIn("MTR-HVAC", util_status["overall_utility_totals"])
        self.assertIn("MTR-COMPRESSOR", util_status["overall_utility_totals"])
        self.assertIn("MTR-CHILLER", util_status["overall_utility_totals"])

        # Check an event record
        event = res["anomalies"][0]
        self.assertEqual(event["anomaly_type"], "ZERO_PRODUCTION_STANDBY_ENERGY")
        self.assertIsNone(event["baseline_value"])
        self.assertFalse(event["context_flags"]["avoidable_waste_claimed"])
        self.assertEqual(event["context_flags"]["category"], "STANDBY_POWER")

    def test_detect_all_anomalies_unified(self):
        """Verify unified detector aggregates all categories into unified response."""
        res = detect_all_anomalies(
            self.session,
            plant_id="IN-TN-01",
            z_threshold=3.0,
            pf_threshold=Decimal("0.90"),
        )
        self.assertEqual(res["plant_id"], "IN-TN-01")
        self.assertIn("statistical_zscore", res)
        self.assertIn("rolling_baseline", res)
        self.assertIn("low_power_factor", res)
        self.assertIn("zero_production_standby", res)
        self.assertGreater(res["total_anomalies_detected"], 0)


if __name__ == "__main__":
    unittest.main()
