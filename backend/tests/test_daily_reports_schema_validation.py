"""
Automated unit tests for Daily Reports schema validation, units, numerics, and domain rules.

Tests column requirements, unknown columns, unit checking, range constraints,
non-finite numbers, timestamp consistency, foreign key validation, quantity balance,
and formula injection protection.
Completely isolated and database-free (mocking MasterDataCache where needed).
"""

from datetime import date, datetime
from decimal import Decimal
import unittest
from unittest.mock import MagicMock

from app.services.daily_report_service import (
    ENERGY_REQUIRED_COLUMNS,
    METER_AREA_MAPPING,
    PRODUCTION_REQUIRED_COLUMNS,
    VALID_ENERGY_SOURCES,
    VALID_METERS,
    check_cell_formula_injection,
    check_header_schema,
    is_numeric_column,
    parse_cell_date,
    parse_cell_datetime,
    parse_cell_decimal,
    parse_cell_int,
    sanitize_cell_value,
    validate_energy_rows,
    validate_production_rows,
)


def _make_mock_master_cache(
    plants=None,
    lines_by_plant=None,
    products=None,
):
    """Create a mock MasterDataCache for isolated domain validation tests."""
    cache = MagicMock()
    cache.plants = set(plants or ["PLANT-A", "PLANT-B", "IN-TN-01"])
    cache.lines_by_plant = set(
        lines_by_plant
        or [
            ("LINE-SMT-1", "PLANT-A"),
            ("LINE-FAL-1", "PLANT-A"),
            ("LINE-SMT-2", "PLANT-B"),
            ("SMT-01", "IN-TN-01"),
            ("FAL-01", "IN-TN-01"),
        ]
    )
    cache.products = set(products or ["PROD-SMART-METER-V1", "PROD-ENERGY-HUB-PRO", "PRODUCT-A"])
    cache.lines_for_plant = {
        "PLANT-A": ["LINE-SMT-1", "LINE-FAL-1"],
        "PLANT-B": ["LINE-SMT-2"],
        "IN-TN-01": ["SMT-01", "FAL-01"],
    }
    return cache


class TestDailyReportsSchemaValidation(unittest.TestCase):
    """Schema validation, units, data types, and business logic constraints."""

    # ---------------------------------------------------------
    # 1. Header & Column Schema Checks
    # ---------------------------------------------------------

    def test_energy_required_columns_all_present(self):
        """Energy report header with all 13 approved columns passes validation."""
        missing, unknown, unsupp = check_header_schema(ENERGY_REQUIRED_COLUMNS, "ENERGY")
        self.assertEqual(missing, [])
        self.assertEqual(unknown, [])
        self.assertEqual(unsupp, [])

    def test_production_required_columns_all_present(self):
        """Production report header with all 17 approved columns passes validation."""
        missing, unknown, unsupp = check_header_schema(PRODUCTION_REQUIRED_COLUMNS, "PRODUCTION")
        self.assertEqual(missing, [])
        self.assertEqual(unknown, [])
        self.assertEqual(unsupp, [])

    def test_missing_required_columns_flagged(self):
        """Headers omitting required columns are explicitly reported."""
        incomplete = ["timestamp", "date", "plant_id", "meter_id"]
        missing, _, _ = check_header_schema(incomplete, "ENERGY")
        self.assertIn("consumption_kwh", missing)
        self.assertIn("demand_kw", missing)
        self.assertIn("power_factor", missing)
        self.assertIn("cost_inr", missing)

    def test_unknown_columns_flagged_without_auto_mapping(self):
        """Headers containing unrecognized columns are flagged as unknown columns."""
        headers = ENERGY_REQUIRED_COLUMNS + ["unexpected_column", "custom_sensor_raw"]
        missing, unknown, unsupp = check_header_schema(headers, "ENERGY")
        self.assertEqual(missing, [])
        self.assertEqual(unknown, ["unexpected_column", "custom_sensor_raw"])
        self.assertEqual(unsupp, [])

    def test_unsupported_unit_patterns_detected(self):
        """Headers with incompatible engineering units are explicitly flagged."""
        test_cases = [
            ("consumption_mwh", "consumption_kwh"),
            ("consumption_wh", "consumption_kwh"),
            ("demand_mw", "demand_kw"),
            ("tariff_usd_per_kwh", "tariff_inr_per_kwh"),
            ("cost_usd", "cost_inr"),
            ("co2e_tons", "co2e_kg"),
            ("downtime_hours", "downtime_min"),
        ]
        for col, expected_unit in test_cases:
            with self.subTest(col=col):
                headers = [col]
                _, unknown, unsupp = check_header_schema(headers, "ENERGY")
                self.assertEqual(len(unsupp), 1)
                self.assertIn(expected_unit, unsupp[0])
                self.assertEqual(unknown, [])

    # ---------------------------------------------------------
    # 2. Numeric Parsing & Non-Finite Numbers
    # ---------------------------------------------------------

    def test_parse_cell_decimal_valid(self):
        """Valid integer, float, and decimal string representations parse to Decimal."""
        self.assertEqual(parse_cell_decimal(100), Decimal("100"))
        self.assertEqual(parse_cell_decimal(100.5), Decimal("100.5"))
        self.assertEqual(parse_cell_decimal("1,250.75"), Decimal("1250.75"))
        self.assertEqual(parse_cell_decimal("-45.2"), Decimal("-45.2"))
        self.assertEqual(parse_cell_decimal("+10.0"), Decimal("10.0"))

    def test_parse_cell_decimal_rejects_non_finite_and_nan(self):
        """NaN, Inf, -Inf, infinity, null, and none are safely rejected as None."""
        for non_finite in ["nan", "NaN", "INF", "infinity", "-Infinity", "-inf", "null", "none", None, ""]:
            with self.subTest(val=non_finite):
                self.assertIsNone(parse_cell_decimal(non_finite))

    def test_parse_cell_int_valid_and_rejections(self):
        """Integers parse cleanly; fractions and non-finite values are rejected."""
        self.assertEqual(parse_cell_int(50), 50)
        self.assertEqual(parse_cell_int("1,000"), 1000)
        self.assertEqual(parse_cell_int(45.0), 45)

        # Fractions rejected for integer fields
        self.assertIsNone(parse_cell_int(45.6))
        self.assertIsNone(parse_cell_int("45.6"))
        self.assertIsNone(parse_cell_int("nan"))
        self.assertIsNone(parse_cell_int("inf"))
        self.assertIsNone(parse_cell_int(None))

    # ---------------------------------------------------------
    # 3. Timestamp & Date Parsing
    # ---------------------------------------------------------

    def test_parse_cell_datetime_formats(self):
        """Parses ISO, standard SQL, and common localized date-time strings."""
        dt1 = parse_cell_datetime("2026-04-01T14:30:00")
        self.assertEqual(dt1, datetime(2026, 4, 1, 14, 30, 0))

        dt2 = parse_cell_datetime("2026-04-01 14:30:00")
        self.assertEqual(dt2, datetime(2026, 4, 1, 14, 30, 0))

        dt3 = parse_cell_datetime("01/04/2026 14:30:00")
        self.assertEqual(dt3, datetime(2026, 4, 1, 14, 30, 0))

        self.assertIsNone(parse_cell_datetime("invalid-timestamp-string"))
        self.assertIsNone(parse_cell_datetime("nan"))

    def test_parse_cell_date_formats(self):
        """Parses ISO and common date formats."""
        self.assertEqual(parse_cell_date("2026-04-01"), date(2026, 4, 1))
        self.assertEqual(parse_cell_date("01-04-2026"), date(2026, 4, 1))
        self.assertEqual(parse_cell_date(datetime(2026, 4, 1, 10, 0)), date(2026, 4, 1))
        self.assertIsNone(parse_cell_date("not-a-date"))

    # ---------------------------------------------------------
    # 4. Energy Row Validation & Domain Rules
    # ---------------------------------------------------------

    def test_validate_energy_rows_valid(self):
        """A valid energy row with registered meter, matching area, and clean numerics passes."""
        cache = _make_mock_master_cache()
        row = {
            "timestamp": "2026-04-01 00:00:00",
            "date": "2026-04-01",
            "plant_id": "PLANT-A",
            "meter_id": "MTR-SMT",
            "area": "SMT",
            "energy_source": "ELECTRICITY",
            "consumption_kwh": "120.5",
            "demand_kw": "45.0",
            "power_factor": "0.95",
            "tariff_inr_per_kwh": "7.5",
            "cost_inr": "903.75",
            "co2e_kg": "98.81",
            "reading_quality": "VALID",
        }
        valid, errors, preview, summary = validate_energy_rows(
            rows=[row],
            confirmed_date=date(2026, 4, 1),
            master_cache=cache,
            existing_db_keys=set(),
            mode="INCREMENTAL",
        )
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(errors), 0)
        self.assertEqual(summary.valid_rows, 1)
        self.assertEqual(summary.rejected_rows, 0)
        self.assertEqual(preview[0].status, "VALID")

    def test_validate_energy_rows_power_factor_out_of_bounds(self):
        """Power factor outside [0.0, 1.0] is rejected with RANGE_VIOLATION."""
        cache = _make_mock_master_cache()
        base_row = {
            "timestamp": "2026-04-01 00:00:00",
            "date": "2026-04-01",
            "plant_id": "PLANT-A",
            "meter_id": "MTR-SMT",
            "area": "SMT",
            "energy_source": "ELECTRICITY",
            "consumption_kwh": "100",
            "demand_kw": "25",
            "power_factor": "1.25",  # Invalid: > 1.0
            "tariff_inr_per_kwh": "7.5",
            "cost_inr": "750",
            "co2e_kg": "82",
            "reading_quality": "VALID",
        }
        valid, errors, preview, summary = validate_energy_rows(
            rows=[base_row],
            confirmed_date=date(2026, 4, 1),
            master_cache=cache,
            existing_db_keys=set(),
        )
        self.assertEqual(len(valid), 0)
        self.assertTrue(any(e.column == "power_factor" and e.error_type == "RANGE_VIOLATION" for e in errors))

    def test_validate_energy_rows_negative_consumption_rejected(self):
        """Negative energy consumption is strictly rejected with RANGE_VIOLATION."""
        cache = _make_mock_master_cache()
        row = {
            "timestamp": "2026-04-01 00:00:00",
            "date": "2026-04-01",
            "plant_id": "PLANT-A",
            "meter_id": "MTR-SMT",
            "area": "SMT",
            "energy_source": "ELECTRICITY",
            "consumption_kwh": "-50.0",  # Negative
            "demand_kw": "25",
            "power_factor": "0.92",
            "tariff_inr_per_kwh": "7.5",
            "cost_inr": "750",
            "co2e_kg": "82",
            "reading_quality": "VALID",
        }
        valid, errors, preview, summary = validate_energy_rows(
            rows=[row],
            confirmed_date=date(2026, 4, 1),
            master_cache=cache,
            existing_db_keys=set(),
        )
        self.assertEqual(len(valid), 0)
        self.assertTrue(any(e.column == "consumption_kwh" and e.error_type == "RANGE_VIOLATION" for e in errors))

    def test_validate_energy_rows_unapproved_meter_and_area_mismatch(self):
        """Unregistered submeter ID or area mismatch is rejected."""
        cache = _make_mock_master_cache()
        # 1. Unapproved meter
        row1 = {
            "timestamp": "2026-04-01 00:00:00",
            "date": "2026-04-01",
            "plant_id": "PLANT-A",
            "meter_id": "MTR-UNKNOWN-99",
            "area": "SMT",
            "energy_source": "ELECTRICITY",
            "consumption_kwh": "100",
            "demand_kw": "25",
            "power_factor": "0.95",
            "tariff_inr_per_kwh": "7.5",
            "cost_inr": "750",
            "co2e_kg": "82",
            "reading_quality": "VALID",
        }
        valid, errors, _, _ = validate_energy_rows(
            rows=[row1], confirmed_date=date(2026, 4, 1), master_cache=cache, existing_db_keys=set()
        )
        self.assertEqual(len(valid), 0)
        self.assertTrue(any(e.error_type == "INVALID_METER" for e in errors))

        # 2. Area mismatch: MTR-SMT must belong to area SMT
        row2 = dict(row1, meter_id="MTR-SMT", area="FAL")
        valid2, errors2, _, _ = validate_energy_rows(
            rows=[row2], confirmed_date=date(2026, 4, 1), master_cache=cache, existing_db_keys=set()
        )
        self.assertEqual(len(valid2), 0)
        self.assertTrue(any(e.error_type == "AREA_MISMATCH" for e in errors2))

    def test_validate_energy_rows_date_and_reporting_mismatch(self):
        """Date column contradicting timestamp date or confirmed reporting date is rejected."""
        cache = _make_mock_master_cache()
        row = {
            "timestamp": "2026-04-01 05:00:00",
            "date": "2026-04-02",  # Contradicts timestamp date 2026-04-01
            "plant_id": "PLANT-A",
            "meter_id": "MTR-SMT",
            "area": "SMT",
            "energy_source": "ELECTRICITY",
            "consumption_kwh": "100",
            "demand_kw": "25",
            "power_factor": "0.95",
            "tariff_inr_per_kwh": "7.5",
            "cost_inr": "750",
            "co2e_kg": "82",
            "reading_quality": "VALID",
        }
        valid, errors, _, _ = validate_energy_rows(
            rows=[row], confirmed_date=date(2026, 4, 1), master_cache=cache, existing_db_keys=set()
        )
        self.assertEqual(len(valid), 0)
        self.assertTrue(any(e.error_type == "DATE_MISMATCH" for e in errors))

    # ---------------------------------------------------------
    # 5. Production Row Validation & Quantity Balance
    # ---------------------------------------------------------

    def test_validate_production_rows_valid(self):
        """A valid production row with exact quantity balance passes."""
        cache = _make_mock_master_cache()
        row = {
            "event_ts": "2026-04-01 08:00:00",
            "event_date": "2026-04-01",
            "plant_id": "PLANT-A",
            "line_id": "LINE-SMT-1",
            "shift_id": "SHIFT-A",
            "product_id": "PROD-SMART-METER-V1",
            "production_order_id": "PO-2026-001",
            "target_qty": "500",
            "actual_qty": "480",
            "good_qty": "470",
            "reject_qty": "10",  # 470 + 10 = 480
            "rework_qty": "5",
            "downtime_min": "15",
            "downtime_reason": "No Downtime",
            "operator_team": "Team Alpha",
            "source_system": "MES-MANUAL",
            "data_quality": "VALID",
            "hour": "8",
        }
        valid, errors, preview, summary = validate_production_rows(
            rows=[row],
            confirmed_date=date(2026, 4, 1),
            master_cache=cache,
            existing_db_keys=set(),
        )
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(errors), 0)
        self.assertEqual(summary.valid_rows, 1)

    def test_validate_production_quantity_balance_violation(self):
        """Violation of actual_qty == good_qty + reject_qty is rejected."""
        cache = _make_mock_master_cache()
        row = {
            "event_ts": "2026-04-01 08:00:00",
            "event_date": "2026-04-01",
            "plant_id": "PLANT-A",
            "line_id": "LINE-SMT-1",
            "shift_id": "SHIFT-A",
            "product_id": "PROD-SMART-METER-V1",
            "production_order_id": "PO-2026-001",
            "target_qty": "500",
            "actual_qty": "500",
            "good_qty": "450",
            "reject_qty": "20",  # 450 + 20 = 470 != 500
            "rework_qty": "0",
            "downtime_min": "0",
            "downtime_reason": "No Downtime",
            "operator_team": "Team Alpha",
            "source_system": "MES",
            "data_quality": "VALID",
        }
        valid, errors, _, _ = validate_production_rows(
            rows=[row], confirmed_date=date(2026, 4, 1), master_cache=cache, existing_db_keys=set()
        )
        self.assertEqual(len(valid), 0)
        self.assertTrue(any("Quantity balance violation" in e.message for e in errors))

    def test_validate_production_foreign_key_violations(self):
        """Unregistered product or line-plant mismatch is rejected with FOREIGN_KEY_VIOLATION."""
        cache = _make_mock_master_cache()

        # 1. Invalid line for plant (LINE-SMT-2 belongs to PLANT-B, not PLANT-A)
        row1 = {
            "event_ts": "2026-04-01 08:00:00",
            "event_date": "2026-04-01",
            "plant_id": "PLANT-A",
            "line_id": "LINE-SMT-2",  # Mismatch
            "shift_id": "SHIFT-A",
            "product_id": "PROD-SMART-METER-V1",
            "production_order_id": "PO-2026-001",
            "target_qty": "100",
            "actual_qty": "100",
            "good_qty": "100",
            "reject_qty": "0",
            "rework_qty": "0",
            "downtime_min": "0",
            "downtime_reason": "None",
            "operator_team": "Team Alpha",
            "source_system": "MES",
            "data_quality": "VALID",
        }
        valid1, errors1, _, _ = validate_production_rows(
            rows=[row1], confirmed_date=date(2026, 4, 1), master_cache=cache, existing_db_keys=set()
        )
        self.assertEqual(len(valid1), 0)
        self.assertTrue(any(e.error_type == "FOREIGN_KEY_VIOLATION" and e.column == "line_id" for e in errors1))

        # 2. Unknown product ID
        row2 = dict(row1, line_id="LINE-SMT-1", product_id="PROD-NON-EXISTENT-XYZ")
        valid2, errors2, _, _ = validate_production_rows(
            rows=[row2], confirmed_date=date(2026, 4, 1), master_cache=cache, existing_db_keys=set()
        )
        self.assertEqual(len(valid2), 0)
        self.assertTrue(any(e.error_type == "FOREIGN_KEY_VIOLATION" and e.column == "product_id" for e in errors2))

    def test_validate_production_hour_mismatch(self):
        """Explicit hour column differing from event_ts hour is rejected."""
        cache = _make_mock_master_cache()
        row = {
            "event_ts": "2026-04-01 14:00:00",  # hour 14
            "event_date": "2026-04-01",
            "plant_id": "PLANT-A",
            "line_id": "LINE-SMT-1",
            "shift_id": "SHIFT-B",
            "product_id": "PROD-SMART-METER-V1",
            "production_order_id": "PO-2026-001",
            "target_qty": "100",
            "actual_qty": "100",
            "good_qty": "100",
            "reject_qty": "0",
            "rework_qty": "0",
            "downtime_min": "0",
            "downtime_reason": "None",
            "operator_team": "Team Alpha",
            "source_system": "MES",
            "data_quality": "VALID",
            "hour": "8",  # Contradicts 14
        }
        valid, errors, _, _ = validate_production_rows(
            rows=[row], confirmed_date=date(2026, 4, 1), master_cache=cache, existing_db_keys=set()
        )
        self.assertEqual(len(valid), 0)
        self.assertTrue(any(e.error_type == "HOUR_MISMATCH" for e in errors))

    # ---------------------------------------------------------
    # 6. Formula Injection Protection
    # ---------------------------------------------------------

    def test_formula_injection_sanitization_and_detection(self):
        """Dangerous spreadsheet formula prefixes are safely neutralized and detected."""
        # Detect dangerous prefixes
        self.assertTrue(check_cell_formula_injection("=cmd|'/C calc'!A0"))
        self.assertTrue(check_cell_formula_injection("@SUM(A1:A10)"))
        self.assertFalse(check_cell_formula_injection("Normal Text"))
        self.assertFalse(check_cell_formula_injection("-50.5"))
        self.assertFalse(check_cell_formula_injection("+100"))

        # Column-aware sanitization
        # Numeric column: legitimate negative/positive preserved
        self.assertEqual(sanitize_cell_value("-50.0", "consumption_kwh"), "-50.0")
        self.assertEqual(sanitize_cell_value("+25.5", "demand_kw"), "+25.5")
        # Numeric column: formula neutralized
        self.assertEqual(sanitize_cell_value("=1+1", "consumption_kwh"), "'=1+1")
        # Text column: formula neutralized
        self.assertEqual(sanitize_cell_value("=HYPERLINK(\"http://evil.com\")", "downtime_reason"), "'=HYPERLINK(\"http://evil.com\")")
        # Text column: ordinary text preserved
        self.assertEqual(sanitize_cell_value("Line 1 - Shift A + Maintenance", "downtime_reason"), "Line 1 - Shift A + Maintenance")


if __name__ == "__main__":
    unittest.main()
