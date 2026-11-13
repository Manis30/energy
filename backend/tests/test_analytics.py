"""Automated verification tests for deterministic analytics services against Neon database."""

import unittest
from decimal import Decimal

from app.db import get_engine, get_session_factory
from app.services.energy_analytics import (
    get_energy_by_area,
    get_energy_by_meter,
    get_energy_daily_trend,
    get_energy_summary,
    get_power_factor_summary,
)
from app.services.energy_intensity import (
    get_factory_energy_analytics,
    get_process_energy_analytics,
    get_product_process_energy,
    get_zero_production_period_energy,
)
from app.services.production_analytics import (
    get_downtime_by_reason,
    get_production_by_line,
    get_production_by_product,
    get_production_by_shift,
    get_production_daily_trend,
    get_production_summary,
)


class TestAnalyticsServices(unittest.TestCase):
    """Test suite verifying mathematical and referential accuracy of analytics functions."""

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

    def test_energy_summary_aggregates(self):
        """Verify overall energy metrics against exact database totals."""
        summary = get_energy_summary(self.session)
        self.assertEqual(summary["total_consumption_kwh"], Decimal("1958088.3130"))
        self.assertEqual(summary["total_cost_inr"], Decimal("16154228.24"))
        self.assertEqual(summary["total_co2e_kg"], Decimal("1401991.1270"))
        self.assertEqual(summary["total_readings"], 22080)
        self.assertEqual(summary["distinct_hours"], 2208)
        self.assertIsNotNone(summary["peak_reading"])
        self.assertEqual(summary["peak_reading"]["consumption_kwh"], Decimal("159.1380"))

    def test_energy_reconciliation_by_meter_and_area(self):
        """Verify meter breakdown sums exactly reconcile to overall total consumption."""
        summary = get_energy_summary(self.session)
        by_meter = get_energy_by_meter(self.session)
        by_area = get_energy_by_area(self.session)

        meter_sum = sum(m["consumption_kwh"] for m in by_meter)
        area_sum = sum(a["consumption_kwh"] for a in by_area)

        self.assertEqual(meter_sum, summary["total_consumption_kwh"])
        self.assertEqual(area_sum, summary["total_consumption_kwh"])
        self.assertEqual(len(by_meter), 5)
        self.assertEqual(len(by_area), 5)

        # SMT should be the top consuming meter
        self.assertEqual(by_meter[0]["meter_id"], "MTR-SMT")
        self.assertEqual(by_meter[0]["consumption_kwh"], Decimal("507553.4990"))

    def test_production_summary_aggregates_and_balance(self):
        """Verify production volume totals and the identity: actual = good + reject."""
        summary = get_production_summary(self.session)
        self.assertEqual(summary["target_qty"], 2914560)
        self.assertEqual(summary["actual_qty"], 2424184)
        self.assertEqual(summary["good_qty"], 2378960)
        self.assertEqual(summary["reject_qty"], 45224)
        self.assertEqual(summary["rework_qty"], 24852)
        self.assertEqual(summary["downtime_min"], 60290)
        self.assertEqual(summary["event_count"], 8832)
        self.assertTrue(summary["quantity_balance_valid"])
        self.assertEqual(summary["actual_qty"], summary["good_qty"] + summary["reject_qty"])

    def test_production_line_breakdown(self):
        """Verify line metrics sum to total actual production across the 4 lines."""
        lines = get_production_by_line(self.session)
        self.assertEqual(len(lines), 4)

        total_line_actual = sum(l["actual_qty"] for l in lines)
        self.assertEqual(total_line_actual, 2424184)

        # Check line IDs
        line_ids = sorted([l["line_id"] for l in lines])
        self.assertEqual(line_ids, ["FAL-L1", "FAL-L2", "SMT-L1", "SMT-L2"])

    def test_production_product_breakdown(self):
        """Verify product SKU breakdown sums to total actual production."""
        products = get_production_by_product(self.session)
        self.assertEqual(len(products), 3)

        total_prod_actual = sum(p["actual_qty"] for p in products)
        self.assertEqual(total_prod_actual, 2424184)

    def test_process_energy_analytics_no_join_duplication(self):
        """Verify line process energy matches exactly MTR-SMT and MTR-FAL totals without cartesian duplication."""
        process = get_process_energy_analytics(self.session)
        lines = process["lines"]
        self.assertEqual(len(lines), 4)

        # MTR-SMT total in database is exactly 507,553.4990
        smt_kwh = process["smt_summary"]["total_process_kwh"]
        self.assertEqual(smt_kwh, Decimal("507553.4990"))

        # MTR-FAL total in database is exactly 362,678.4210
        fal_kwh = process["fal_summary"]["total_process_kwh"]
        self.assertEqual(fal_kwh, Decimal("362678.4210"))

        # SMT overall SEC = 507553.4990 / 1431132 = 0.3547 kWh/board
        self.assertEqual(process["smt_summary"]["overall_process_sec_kwh_per_board"], Decimal("0.3547"))

        # FAL overall SEC = 362678.4210 / 993052 = 0.3652 kWh/phone
        self.assertEqual(process["fal_summary"]["overall_process_sec_kwh_per_phone"], Decimal("0.3652"))

    def test_factory_energy_analytics_and_utility_isolation(self):
        """Verify factory SEC includes all 5 meters and facility utilities are segregated."""
        factory = get_factory_energy_analytics(self.session)
        self.assertEqual(factory["total_plant_energy_kwh"], Decimal("1958088.3130"))

        # Final Assembly Output = FAL-L1 + FAL-L2
        self.assertEqual(factory["final_assembly_actual_output"], 495577 + 497475)
        self.assertEqual(factory["final_assembly_actual_output"], 993052)

        # Factory SEC = 1958088.3130 / 993052 = 1.9718 kWh / finished unit
        self.assertEqual(factory["factory_sec_kwh_per_finished_unit"], Decimal("1.9718"))

        # Check utilities isolation (3 meters: HVAC, COMPRESSOR, CHILLER)
        utils = factory["facility_utilities"]
        self.assertEqual(len(utils["meters"]), 3)
        util_meters = sorted([m["meter_id"] for m in utils["meters"]])
        self.assertEqual(util_meters, ["MTR-CHILLER", "MTR-COMPRESSOR", "MTR-HVAC"])

        # Utility total + SMT + FAL = 100% of plant total
        process_total = Decimal("507553.4990") + Decimal("362678.4210")
        self.assertEqual(utils["total_utility_consumption_kwh"] + process_total, factory["total_plant_energy_kwh"])

    def test_product_process_energy_reconciliation(self):
        """Verify product-level direct process energy sums to the combined SMT + FAL total."""
        product_energy = get_product_process_energy(self.session)
        self.assertEqual(len(product_energy), 3)

        total_product_process_kwh = sum(p["total_direct_process_kwh"] for p in product_energy)
        expected_process_kwh = Decimal("507553.4990") + Decimal("362678.4210")
        self.assertEqual(total_product_process_kwh, expected_process_kwh)

        # Stage-specific SEC is valid: Aster Pro 256GB has higher SMT board SEC
        pro = [p for p in product_energy if p["product_id"] == "SPH-PRO-256"][0]
        a15_256 = [p for p in product_energy if p["product_id"] == "SPH-A15-256"][0]
        self.assertGreater(pro["smt_process_sec_kwh_per_board"], a15_256["smt_process_sec_kwh_per_board"])
        self.assertIsNotNone(pro["fal_process_sec_kwh_per_phone"])
        # Cross-stage finished-phone combined SEC is unavailable without WIP tracking
        self.assertIsNone(pro["finished_phone_process_sec_kwh_per_unit"])
        self.assertIn("UNAVAILABLE", pro["finished_phone_sec_status"])

    def test_zero_production_period_energy(self):
        """Verify 155 zero-production hours are isolated with their actual standby draw."""
        zero_prod = get_zero_production_period_energy(self.session)
        self.assertEqual(zero_prod["total_zero_production_hours"], 155)
        self.assertGreater(zero_prod["total_zero_production_energy_kwh"], Decimal("0"))

        # Check that reasons match downtime reasons
        reasons = [r["downtime_reason"] for r in zero_prod["by_downtime_reason"]]
        self.assertIn("CHANGEOVER", reasons)
        self.assertIn("MICRO_STOP", reasons)
        self.assertIn("EQUIPMENT_FAULT", reasons)
        self.assertIn("NO_MATERIAL", reasons)
        self.assertIn("FEEDER_JAM", reasons)


if __name__ == "__main__":
    unittest.main()
