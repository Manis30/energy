"""
Automated tests for Cross-Source Data Reconciliation Engine.

Covers all 7 reconciliation check suites, domain safeguards, boundary conditions,
status hierarchy, and service orchestration functions.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from typing import Any, List
import unittest
from unittest.mock import MagicMock

from sqlalchemy import delete, text

from app.db import get_session_factory
from app.models.source_data import DimProduct, DimProductionLine, FactEnergyMeterHourly, FactHourlyProduction
from app.models.upload_history import UploadHistory
from app.schemas.reconciliation import (
    ReconciliationCategory,
    ReconciliationCheckResult,
    ReconciliationFinding,
    ReconciliationReportResponse,
    ReconciliationStatus,
    ReconciliationSummaryResponse,
)
from app.services.reconciliation_service import (
    STANDARD_LIMITATIONS,
    _check_data_quality,
    _check_duplicate_records,
    _check_energy_coverage,
    _check_production_coverage,
    _check_reference_integrity,
    _check_source_consistency,
    _check_timestamp_alignment,
    get_reconciliation_summary,
    get_supported_check_definitions,
    run_cross_source_reconciliation,
)

# Baseline dates in seeded database
SEEDED_START_DATE = date(2026, 8, 1)
SEEDED_END_DATE = date(2026, 8, 2)

# Isolated test fixture date outside seeded range
FIXTURE_DATE = date(2026, 11, 20)
FIXTURE_END_DATE = date(2026, 11, 21)


class BaseReconciliationTestCase(unittest.TestCase):
    """Base test class providing disposable database session and safe fixture cleanup."""

    @classmethod
    def setUpClass(cls):
        cls.session_factory = get_session_factory()

    def setUp(self):
        self.session = self.session_factory()
        self._cleanup_fixtures()

    def tearDown(self):
        self._cleanup_fixtures()
        self.session.close()

    def _cleanup_fixtures(self):
        """Purge any test records created on or after 2026-11-01."""
        try:
            self.session.query(FactEnergyMeterHourly).filter(
                FactEnergyMeterHourly.date >= date(2026, 11, 1)
            ).delete()
            self.session.query(FactHourlyProduction).filter(
                FactHourlyProduction.event_date >= date(2026, 11, 1)
            ).delete()
            self.session.query(UploadHistory).filter(
                UploadHistory.reporting_date >= date(2026, 11, 1)
            ).delete()
            self.session.commit()
        except Exception:
            self.session.rollback()


class TestReconciliationEnergyCoverage(BaseReconciliationTestCase):
    """Check 1: CHK_ENERGY_COVERAGE tests."""

    def test_energy_coverage_pass_on_complete_telemetry(self):
        """Complete continuous telemetry produces PASS status."""
        result = _check_energy_coverage(self.session, SEEDED_START_DATE, SEEDED_END_DATE)
        self.assertEqual(result.check_id, "CHK_ENERGY_COVERAGE")
        self.assertEqual(result.category, ReconciliationCategory.ENERGY_COVERAGE)
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        # Verify schema boundary notice is present
        catalog_unavail = [f for f in result.findings if f.reason_code == "PLANT_METER_CATALOG_UNAVAILABLE"]
        self.assertEqual(len(catalog_unavail), 1)
        self.assertEqual(catalog_unavail[0].status, ReconciliationStatus.UNAVAILABLE)

    def test_energy_coverage_emits_catalog_unavailable_boundary_notice(self):
        """Schema boundary notice PLANT_METER_CATALOG_UNAVAILABLE is always emitted."""
        result = _check_energy_coverage(self.session, SEEDED_START_DATE, SEEDED_START_DATE)
        unavail_findings = [f for f in result.findings if f.reason_code == "PLANT_METER_CATALOG_UNAVAILABLE"]
        self.assertEqual(len(unavail_findings), 1)
        self.assertIn("dim_meter", unavail_findings[0].explanation)
        self.assertEqual(unavail_findings[0].source_references, ["fact_energy_meter_hourly"])

    def test_energy_coverage_detects_hourly_gaps(self):
        """Middle missing hours in observed meter span produce WARNING with METER_HOURLY_GAPS_DETECTED."""
        # Insert readings at 00:00 and 03:00 (omitting 01:00 and 02:00 -> 2 hours missing)
        readings = [
            FactEnergyMeterHourly(
                meter_reading_id="MTR_GAP_00",
                timestamp=datetime(2026, 11, 20, 0, 0, 0),
                date=FIXTURE_DATE,
                plant_id="IN-TN-01",
                meter_id="MTR-SMT",
                area="SMT",
                energy_source="ELECTRICITY",
                consumption_kwh=Decimal("100.0"),
                demand_kw=Decimal("25.0"),
                power_factor=Decimal("0.95"),
                tariff_inr_per_kwh=Decimal("7.5"),
                cost_inr=Decimal("750.0"),
                co2e_kg=Decimal("82.0"),
                reading_quality="VALID",
            ),
            FactEnergyMeterHourly(
                meter_reading_id="MTR_GAP_03",
                timestamp=datetime(2026, 11, 20, 3, 0, 0),
                date=FIXTURE_DATE,
                plant_id="IN-TN-01",
                meter_id="MTR-SMT",
                area="SMT",
                energy_source="ELECTRICITY",
                consumption_kwh=Decimal("110.0"),
                demand_kw=Decimal("28.0"),
                power_factor=Decimal("0.96"),
                tariff_inr_per_kwh=Decimal("7.5"),
                cost_inr=Decimal("825.0"),
                co2e_kg=Decimal("90.0"),
                reading_quality="VALID",
            ),
        ]
        self.session.add_all(readings)
        self.session.commit()

        result = _check_energy_coverage(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.WARNING)
        gap_findings = [f for f in result.findings if f.reason_code == "METER_HOURLY_GAPS_DETECTED"]
        self.assertEqual(len(gap_findings), 1)
        self.assertEqual(gap_findings[0].affected_entity, "MTR-SMT")
        self.assertEqual(gap_findings[0].observed_value, 2)  # 2 distinct hours
        self.assertEqual(gap_findings[0].expected_value, 4)  # 4 hour span (00 to 03)
        self.assertEqual(gap_findings[0].difference, 2)  # 2 missing hours
        self.assertEqual(gap_findings[0].difference_unit, "hours")
        self.assertIn("2 missing hourly interval(s)", gap_findings[0].explanation)

    def test_energy_coverage_zero_consumption_is_valid_telemetry_not_gap(self):
        """Domain Safeguard: Zero consumption (0.0 kWh) is valid recorded telemetry, not a missing hour."""
        # Insert 3 consecutive readings where hour 01:00 has consumption_kwh = 0.0
        readings = [
            FactEnergyMeterHourly(
                meter_reading_id="MTR_ZERO_00",
                timestamp=datetime(2026, 11, 20, 0, 0, 0),
                date=FIXTURE_DATE,
                plant_id="IN-TN-01",
                meter_id="MTR-SMT",
                area="SMT",
                energy_source="ELECTRICITY",
                consumption_kwh=Decimal("100.0"),
                demand_kw=Decimal("25.0"),
                power_factor=Decimal("0.95"),
                tariff_inr_per_kwh=Decimal("7.5"),
                cost_inr=Decimal("750.0"),
                co2e_kg=Decimal("82.0"),
                reading_quality="VALID",
            ),
            FactEnergyMeterHourly(
                meter_reading_id="MTR_ZERO_01",
                timestamp=datetime(2026, 11, 20, 1, 0, 0),
                date=FIXTURE_DATE,
                plant_id="IN-TN-01",
                meter_id="MTR-SMT",
                area="SMT",
                energy_source="ELECTRICITY",
                consumption_kwh=Decimal("0.0"),  # Zero consumption (standby/idle)
                demand_kw=Decimal("0.0"),
                power_factor=Decimal("0.90"),
                tariff_inr_per_kwh=Decimal("7.5"),
                cost_inr=Decimal("0.0"),
                co2e_kg=Decimal("0.0"),
                reading_quality="VALID",
            ),
            FactEnergyMeterHourly(
                meter_reading_id="MTR_ZERO_02",
                timestamp=datetime(2026, 11, 20, 2, 0, 0),
                date=FIXTURE_DATE,
                plant_id="IN-TN-01",
                meter_id="MTR-SMT",
                area="SMT",
                energy_source="ELECTRICITY",
                consumption_kwh=Decimal("105.0"),
                demand_kw=Decimal("26.0"),
                power_factor=Decimal("0.95"),
                tariff_inr_per_kwh=Decimal("7.5"),
                cost_inr=Decimal("787.5"),
                co2e_kg=Decimal("86.0"),
                reading_quality="VALID",
            ),
        ]
        self.session.add_all(readings)
        self.session.commit()

        result = _check_energy_coverage(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        # 3 hours in span, 3 distinct hours -> 0 missing hours -> PASS
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        gap_findings = [f for f in result.findings if f.reason_code == "METER_HOURLY_GAPS_DETECTED"]
        self.assertEqual(len(gap_findings), 0)

    def test_energy_coverage_warns_on_zero_observations(self):
        """Zero observations in evaluation window produce WARNING with ZERO_ENERGY_OBSERVATIONS_IN_PERIOD."""
        empty_date = date(2026, 1, 1)
        result = _check_energy_coverage(self.session, empty_date, empty_date)
        self.assertEqual(result.status, ReconciliationStatus.WARNING)
        zero_findings = [f for f in result.findings if f.reason_code == "ZERO_ENERGY_OBSERVATIONS_IN_PERIOD"]
        self.assertEqual(len(zero_findings), 1)
        self.assertEqual(zero_findings[0].observed_value, 0)
        self.assertIn("Zero energy meter observations", zero_findings[0].explanation)

    def test_energy_coverage_plant_filter_isolation(self):
        """Filtering by plant_id evaluates only meters belonging to the specified plant."""
        result_tn = _check_energy_coverage(self.session, SEEDED_START_DATE, SEEDED_START_DATE, plant_id="IN-TN-01")
        self.assertEqual(result_tn.plant_id, "IN-TN-01")
        self.assertEqual(result_tn.status, ReconciliationStatus.PASS)


class TestReconciliationProductionCoverage(BaseReconciliationTestCase):
    """Check 2: CHK_PRODUCTION_COVERAGE tests."""

    def test_production_coverage_pass_on_active_lines(self):
        """Active manufacturing lines with events produce PASS status."""
        result = _check_production_coverage(self.session, SEEDED_START_DATE, SEEDED_END_DATE)
        self.assertEqual(result.check_id, "CHK_PRODUCTION_COVERAGE")
        self.assertEqual(result.category, ReconciliationCategory.PRODUCTION_COVERAGE)
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        # Verify schema boundary notice is present
        cal_unavail = [f for f in result.findings if f.reason_code == "OPERATING_CALENDAR_UNAVAILABLE"]
        self.assertEqual(len(cal_unavail), 1)
        self.assertEqual(cal_unavail[0].status, ReconciliationStatus.UNAVAILABLE)

    def test_production_coverage_emits_operating_calendar_unavailable(self):
        """Domain Safeguard: Schema boundary notice OPERATING_CALENDAR_UNAVAILABLE is always emitted."""
        result = _check_production_coverage(self.session, SEEDED_START_DATE, SEEDED_START_DATE)
        findings = [f for f in result.findings if f.reason_code == "OPERATING_CALENDAR_UNAVAILABLE"]
        self.assertEqual(len(findings), 1)
        self.assertIn("operating calendar", findings[0].explanation.lower())

    def test_production_coverage_detects_unobserved_line(self):
        """Registered production line with zero recorded events produces WARNING with REGISTERED_LINE_UNOBSERVED."""
        # Query on date with no production records
        empty_date = date(2026, 1, 1)
        result = _check_production_coverage(self.session, empty_date, empty_date, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.WARNING)
        unobs_findings = [f for f in result.findings if f.reason_code == "REGISTERED_LINE_UNOBSERVED"]
        self.assertTrue(len(unobs_findings) > 0)
        # All findings must reference registered lines at IN-TN-01
        for f in unobs_findings:
            self.assertEqual(f.plant_id, "IN-TN-01")
            self.assertEqual(f.observed_value, 0)
            self.assertIn("0 recorded production events", f.explanation)

    def test_production_coverage_plant_filter(self):
        """Plant filter restricts line evaluation to registered lines of that plant."""
        result = _check_production_coverage(self.session, SEEDED_START_DATE, SEEDED_START_DATE, plant_id="IN-KA-01")
        self.assertEqual(result.plant_id, "IN-KA-01")
        self.assertEqual(result.status, ReconciliationStatus.PASS)


class TestReconciliationTimestampAlignment(BaseReconciliationTestCase):
    """Check 3: CHK_TIMESTAMP_ALIGNMENT tests."""

    def test_timestamp_alignment_pass_on_aligned_streams(self):
        """Aligned streams in seeded database pass synchronization audit."""
        result = _check_timestamp_alignment(self.session, SEEDED_START_DATE, SEEDED_END_DATE)
        self.assertEqual(result.check_id, "CHK_TIMESTAMP_ALIGNMENT")
        self.assertEqual(result.category, ReconciliationCategory.TIMESTAMP_ALIGNMENT)
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        self.assertEqual(len(result.findings), 0)

    def test_timestamp_alignment_fails_on_production_without_energy(self):
        """Domain Safeguard: Active manufacturing output (actual_qty > 0) without energy telemetry triggers FAIL."""
        # Insert an active production event with actual_qty = 100 without any energy record at 2026-11-20 10:00:00
        prod_event = FactHourlyProduction(
            event_id="PROD_NO_ENERGY_01",
            event_ts=datetime(2026, 11, 20, 10, 0, 0),
            event_date=FIXTURE_DATE,
            year=2026,
            month=11,
            week=47,
            day=20,
            hour=10,
            plant_id="IN-TN-01",
            line_id="SMT-L1",
            shift_id="S1",
            product_id="SPH-A15-128",
            production_order_id="ORD-ALIGN-01",
            target_qty=100,
            actual_qty=100,
            good_qty=95,
            reject_qty=5,
            rework_qty=0,
            downtime_min=0,
            downtime_reason="NONE",
            operator_team="TEAM-A",
            source_system="MES",
            data_quality="VALID",
        )
        self.session.add(prod_event)
        self.session.commit()

        result = _check_timestamp_alignment(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        no_energy_findings = [f for f in result.findings if f.reason_code == "PRODUCTION_WITHOUT_ENERGY_TELEMETRY"]
        self.assertEqual(len(no_energy_findings), 1)
        self.assertEqual(no_energy_findings[0].plant_id, "IN-TN-01")
        self.assertEqual(no_energy_findings[0].status, ReconciliationStatus.FAIL)
        self.assertEqual(no_energy_findings[0].difference_unit, "hours")
        self.assertIn("without any corresponding energy meter telemetry", no_energy_findings[0].explanation)

    def test_timestamp_alignment_allows_standby_energy_with_zero_production(self):
        """Domain Safeguard: Standby energy during zero production or idle hours is NOT penalized."""
        # Insert an energy meter reading with consumption, but NO production event
        energy_record = FactEnergyMeterHourly(
            meter_reading_id="MTR_STANDBY_01",
            timestamp=datetime(2026, 11, 20, 10, 0, 0),
            date=FIXTURE_DATE,
            plant_id="IN-TN-01",
            meter_id="MTR-SMT",
            area="SMT",
            energy_source="ELECTRICITY",
            consumption_kwh=Decimal("35.0"),
            demand_kw=Decimal("10.0"),
            power_factor=Decimal("0.92"),
            tariff_inr_per_kwh=Decimal("7.5"),
            cost_inr=Decimal("262.5"),
            co2e_kg=Decimal("28.7"),
            reading_quality="VALID",
        )
        self.session.add(energy_record)
        self.session.commit()

        # Alignment check evaluates whether active production had energy; standby energy does not trigger failure
        result = _check_timestamp_alignment(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        self.assertEqual(len(result.findings), 0)

    def test_timestamp_alignment_fails_on_subhourly_energy_timestamp(self):
        """Domain Safeguard: Energy telemetry with sub-hourly minute offset triggers FAIL with SUB_HOURLY_TIMESTAMP_MISALIGNMENT."""
        # Non-hourly timestamp: 10:30:00 (minute = 30)
        subhourly_record = FactEnergyMeterHourly(
            meter_reading_id="MTR_SUBHOURLY_01",
            timestamp=datetime(2026, 11, 20, 10, 30, 0),
            date=FIXTURE_DATE,
            plant_id="IN-TN-01",
            meter_id="MTR-SMT",
            area="SMT",
            energy_source="ELECTRICITY",
            consumption_kwh=Decimal("50.0"),
            demand_kw=Decimal("20.0"),
            power_factor=Decimal("0.95"),
            tariff_inr_per_kwh=Decimal("7.5"),
            cost_inr=Decimal("375.0"),
            co2e_kg=Decimal("41.0"),
            reading_quality="VALID",
        )
        self.session.add(subhourly_record)
        self.session.commit()

        result = _check_timestamp_alignment(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        subhourly_findings = [f for f in result.findings if f.reason_code == "SUB_HOURLY_TIMESTAMP_MISALIGNMENT"]
        self.assertEqual(len(subhourly_findings), 1)
        self.assertEqual(subhourly_findings[0].affected_entity, "fact_energy_meter_hourly")
        self.assertEqual(subhourly_findings[0].expected_value, "HH:00:00 (top-of-hour)")
        self.assertIn("10:30:00", subhourly_findings[0].explanation)

    def test_timestamp_alignment_fails_on_subhourly_production_timestamp(self):
        """Domain Safeguard: Production event with sub-hourly second offset triggers FAIL."""
        subhourly_prod = FactHourlyProduction(
            event_id="PROD_SUBHOURLY_01",
            event_ts=datetime(2026, 11, 20, 10, 0, 15),  # second = 15
            event_date=FIXTURE_DATE,
            year=2026,
            month=11,
            week=47,
            day=20,
            hour=10,
            plant_id="IN-TN-01",
            line_id="SMT-L1",
            shift_id="S1",
            product_id="SPH-A15-128",
            production_order_id="ORD-SUBH-01",
            target_qty=100,
            actual_qty=100,
            good_qty=100,
            reject_qty=0,
            rework_qty=0,
            downtime_min=0,
            downtime_reason="NONE",
            operator_team="TEAM-A",
            source_system="MES",
            data_quality="VALID",
        )
        self.session.add(subhourly_prod)
        self.session.commit()

        result = _check_timestamp_alignment(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        subhourly_findings = [f for f in result.findings if f.reason_code == "SUB_HOURLY_TIMESTAMP_MISALIGNMENT"]
        self.assertTrue(len(subhourly_findings) >= 1)
        prod_sub = [f for f in subhourly_findings if f.affected_entity == "fact_hourly_production"]
        self.assertEqual(len(prod_sub), 1)

    def test_timestamp_alignment_plant_filter_isolation(self):
        """Plant filter restricts timestamp alignment check to specified plant without query ambiguity."""
        result_tn = _check_timestamp_alignment(self.session, SEEDED_START_DATE, SEEDED_END_DATE, plant_id="IN-TN-01")
        self.assertEqual(result_tn.plant_id, "IN-TN-01")
        self.assertEqual(result_tn.status, ReconciliationStatus.PASS)

        result_ka = _check_timestamp_alignment(self.session, SEEDED_START_DATE, SEEDED_END_DATE, plant_id="IN-KA-01")
        self.assertEqual(result_ka.plant_id, "IN-KA-01")
        self.assertEqual(result_ka.status, ReconciliationStatus.PASS)


class TestReconciliationDuplicateRecords(BaseReconciliationTestCase):
    """Check 4: CHK_DUPLICATE_RECORDS tests."""

    def test_duplicate_records_pass_on_unique_data(self):
        """Natural business keys in seeded dataset pass deduplication check."""
        result = _check_duplicate_records(self.session, SEEDED_START_DATE, SEEDED_END_DATE)
        self.assertEqual(result.check_id, "CHK_DUPLICATE_RECORDS")
        self.assertEqual(result.category, ReconciliationCategory.DUPLICATE_RECORDS)
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        self.assertEqual(len(result.findings), 0)

    def test_duplicate_records_detects_duplicate_energy_keys(self):
        """Duplicate energy natural keys trigger FAIL with DUPLICATE_ENERGY_BUSINESS_KEY."""
        # Use a mock session executing duplicate query returning rows
        mock_session = MagicMock()
        mock_result_energy = MagicMock()
        ts = datetime(2026, 11, 20, 10, 0, 0)
        mock_result_energy.fetchall.return_value = [(ts, "IN-TN-01", "MTR-SMT", 2)]
        mock_result_prod = MagicMock()
        mock_result_prod.fetchall.return_value = []
        mock_session.execute.side_effect = [mock_result_energy, mock_result_prod]

        result = _check_duplicate_records(mock_session, FIXTURE_DATE, FIXTURE_DATE)
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        self.assertEqual(len(result.findings), 1)
        f = result.findings[0]
        self.assertEqual(f.reason_code, "DUPLICATE_ENERGY_BUSINESS_KEY")
        self.assertEqual(f.affected_entity, "MTR-SMT")
        self.assertEqual(f.observed_value, 2)
        self.assertEqual(f.expected_value, 1)
        self.assertEqual(f.difference, 1)
        self.assertEqual(f.difference_unit, "duplicate records")
        self.assertEqual(f.source_references, ["fact_energy_meter_hourly"])

    def test_duplicate_records_detects_duplicate_production_keys(self):
        """Duplicate production natural keys trigger FAIL with DUPLICATE_PRODUCTION_BUSINESS_KEY."""
        mock_session = MagicMock()
        mock_result_energy = MagicMock()
        mock_result_energy.fetchall.return_value = []
        mock_result_prod = MagicMock()
        ts = datetime(2026, 11, 20, 10, 0, 0)
        mock_result_prod.fetchall.return_value = [(ts, "IN-TN-01", "SMT-L1", 3)]
        mock_session.execute.side_effect = [mock_result_energy, mock_result_prod]

        result = _check_duplicate_records(mock_session, FIXTURE_DATE, FIXTURE_DATE)
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        self.assertEqual(len(result.findings), 1)
        f = result.findings[0]
        self.assertEqual(f.reason_code, "DUPLICATE_PRODUCTION_BUSINESS_KEY")
        self.assertEqual(f.affected_entity, "SMT-L1")
        self.assertEqual(f.observed_value, 3)
        self.assertEqual(f.expected_value, 1)
        self.assertEqual(f.difference, 2)
        self.assertEqual(f.difference_unit, "duplicate records")
        self.assertEqual(f.source_references, ["fact_hourly_production"])


class TestReconciliationSourceConsistency(BaseReconciliationTestCase):
    """Check 5: CHK_SOURCE_CONSISTENCY tests."""

    def test_source_consistency_emits_metric_aggregates_unavailable(self):
        """Schema boundary notice UPLOAD_METRIC_AGGREGATES_UNAVAILABLE is always emitted."""
        result = _check_source_consistency(self.session, SEEDED_START_DATE, SEEDED_START_DATE)
        findings = [f for f in result.findings if f.reason_code == "UPLOAD_METRIC_AGGREGATES_UNAVAILABLE"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].status, ReconciliationStatus.UNAVAILABLE)
        self.assertIn("file-level row metrics", findings[0].explanation)

    def test_source_consistency_detects_untracked_historical_records(self):
        """Records with NULL upload_id produce UNAVAILABLE findings for untracked provenance."""
        result = _check_source_consistency(self.session, SEEDED_START_DATE, SEEDED_START_DATE)
        untracked_energy = [f for f in result.findings if f.reason_code == "UNTRACKED_HISTORICAL_ENERGY_RECORDS"]
        untracked_prod = [f for f in result.findings if f.reason_code == "UNTRACKED_HISTORICAL_PRODUCTION_RECORDS"]
        self.assertTrue(len(untracked_energy) >= 1)
        self.assertTrue(len(untracked_prod) >= 1)
        self.assertEqual(untracked_energy[0].status, ReconciliationStatus.UNAVAILABLE)
        self.assertIn("untracked provenance", untracked_energy[0].explanation)

    def test_source_consistency_emits_unavailable_when_no_uploads_in_period(self):
        """When no upload history records exist in the period, NO_UPLOAD_AUDIT_HISTORY_IN_PERIOD is emitted."""
        result = _check_source_consistency(self.session, FIXTURE_DATE, FIXTURE_DATE)
        no_upload = [f for f in result.findings if f.reason_code == "NO_UPLOAD_AUDIT_HISTORY_IN_PERIOD"]
        self.assertEqual(len(no_upload), 1)
        self.assertEqual(no_upload[0].status, ReconciliationStatus.UNAVAILABLE)
        self.assertIn("No completed or partial daily upload history records", no_upload[0].explanation)

    def test_source_consistency_legacy_upload_untracked_provenance(self):
        """Uploads predating Phase 1 batch attribution produce LEGACY_UPLOAD_UNTRACKED_PROVENANCE."""
        legacy_up = UploadHistory(
            upload_id="LEGACY_UP_01",
            filename="legacy_energy_20261120.csv",
            file_format="CSV",
            file_size_bytes=1024,
            report_type="ENERGY",
            reporting_date=FIXTURE_DATE,
            total_rows=10,
            valid_rows=10,
            mode="INCREMENTAL",
            status="COMPLETED",
            audit_details=json.dumps({"plants_affected": ["IN-TN-01"]}),  # Lacks upload_id/ingested_at
        )
        self.session.add(legacy_up)
        self.session.commit()

        result = _check_source_consistency(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        legacy_findings = [f for f in result.findings if f.reason_code == "LEGACY_UPLOAD_UNTRACKED_PROVENANCE"]
        self.assertEqual(len(legacy_findings), 1)
        self.assertEqual(legacy_findings[0].affected_entity, "LEGACY_UP_01")
        self.assertEqual(legacy_findings[0].status, ReconciliationStatus.UNAVAILABLE)

    def test_source_consistency_modern_upload_exact_match_pass(self):
        """Modern upload whose valid_rows exactly matches attributed fact table records passes."""
        upload_id = "MOD_UP_PASS_01"
        upload = UploadHistory(
            upload_id=upload_id,
            filename="energy_20261120.csv",
            file_format="CSV",
            file_size_bytes=1024,
            report_type="ENERGY",
            reporting_date=FIXTURE_DATE,
            total_rows=2,
            valid_rows=2,
            mode="INCREMENTAL",
            status="COMPLETED",
            audit_details=json.dumps({"upload_id": upload_id, "ingested_at": "2026-11-20T08:00:00", "plants_affected": ["IN-TN-01"]}),
        )
        self.session.add(upload)

        # Add 2 matching records in fact_energy_meter_hourly
        for i in range(2):
            self.session.add(
                FactEnergyMeterHourly(
                    meter_reading_id=f"MTR_MATCH_{i}",
                    timestamp=datetime(2026, 11, 20, i, 0, 0),
                    date=FIXTURE_DATE,
                    plant_id="IN-TN-01",
                    meter_id="MTR-SMT",
                    area="SMT",
                    energy_source="ELECTRICITY",
                    consumption_kwh=Decimal("100.0"),
                    demand_kw=Decimal("25.0"),
                    power_factor=Decimal("0.95"),
                    tariff_inr_per_kwh=Decimal("7.5"),
                    cost_inr=Decimal("750.0"),
                    co2e_kg=Decimal("82.0"),
                    reading_quality="VALID",
                    upload_id=upload_id,
                    ingested_at=datetime(2026, 11, 20, 8, 0, 0),
                )
            )
        self.session.commit()

        result = _check_source_consistency(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        # Should have NO mismatch or missing warnings
        mismatches = [f for f in result.findings if f.status == ReconciliationStatus.WARNING]
        self.assertEqual(len(mismatches), 0)

    def test_source_consistency_modern_upload_missing_records_warning(self):
        """Modern upload with valid_rows > 0 but 0 database records triggers UPLOAD_ENERGY_RECORDS_MISSING."""
        upload_id = "MOD_UP_MISSING_01"
        upload = UploadHistory(
            upload_id=upload_id,
            filename="energy_20261120.csv",
            file_format="CSV",
            file_size_bytes=1024,
            report_type="ENERGY",
            reporting_date=FIXTURE_DATE,
            total_rows=5,
            valid_rows=5,
            mode="INCREMENTAL",
            status="COMPLETED",
            audit_details=json.dumps({"upload_id": upload_id, "ingested_at": "2026-11-20T08:00:00", "plants_affected": ["IN-TN-01"]}),
        )
        self.session.add(upload)
        self.session.commit()

        result = _check_source_consistency(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.WARNING)
        missing_findings = [f for f in result.findings if f.reason_code == "UPLOAD_ENERGY_RECORDS_MISSING"]
        self.assertEqual(len(missing_findings), 1)
        self.assertEqual(missing_findings[0].affected_entity, upload_id)
        self.assertEqual(missing_findings[0].observed_value, 0)
        self.assertEqual(missing_findings[0].expected_value, 5)
        self.assertEqual(missing_findings[0].difference, -5)

    def test_source_consistency_modern_upload_count_mismatch_warning(self):
        """Modern upload where db count > initial valid rows triggers UPLOAD_ENERGY_ROW_COUNT_MISMATCH."""
        upload_id = "MOD_UP_EXCESS_01"
        upload = UploadHistory(
            upload_id=upload_id,
            filename="energy_20261120.csv",
            file_format="CSV",
            file_size_bytes=1024,
            report_type="ENERGY",
            reporting_date=FIXTURE_DATE,
            total_rows=1,
            valid_rows=1,  # Only 1 valid row recorded in upload log
            mode="INCREMENTAL",
            status="COMPLETED",
            audit_details=json.dumps({"upload_id": upload_id, "ingested_at": "2026-11-20T08:00:00", "plants_affected": ["IN-TN-01"]}),
        )
        self.session.add(upload)

        # But 2 rows exist in db with this upload_id
        for i in range(2):
            self.session.add(
                FactEnergyMeterHourly(
                    meter_reading_id=f"MTR_EXCESS_{i}",
                    timestamp=datetime(2026, 11, 20, i, 0, 0),
                    date=FIXTURE_DATE,
                    plant_id="IN-TN-01",
                    meter_id="MTR-SMT",
                    area="SMT",
                    energy_source="ELECTRICITY",
                    consumption_kwh=Decimal("100.0"),
                    demand_kw=Decimal("25.0"),
                    power_factor=Decimal("0.95"),
                    tariff_inr_per_kwh=Decimal("7.5"),
                    cost_inr=Decimal("750.0"),
                    co2e_kg=Decimal("82.0"),
                    reading_quality="VALID",
                    upload_id=upload_id,
                    ingested_at=datetime(2026, 11, 20, 8, 0, 0),
                )
            )
        self.session.commit()

        result = _check_source_consistency(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.WARNING)
        mismatch_findings = [f for f in result.findings if f.reason_code == "UPLOAD_ENERGY_ROW_COUNT_MISMATCH"]
        self.assertEqual(len(mismatch_findings), 1)
        self.assertEqual(mismatch_findings[0].observed_value, 2)
        self.assertEqual(mismatch_findings[0].expected_value, 1)
        self.assertEqual(mismatch_findings[0].difference, 1)

    def test_source_consistency_fully_superseded_by_correction(self):
        """When subsequent OVERWRITE_CORRECTION supersedes all rows, check reports PASS with UPLOAD_RECORDS_FULLY_SUPERSEDED."""
        orig_upload_id = "MOD_UP_ORIG_01"
        corr_upload_id = "MOD_UP_CORR_01"

        orig_upload = UploadHistory(
            upload_id=orig_upload_id,
            filename="energy_orig.csv",
            file_format="CSV",
            file_size_bytes=1024,
            report_type="ENERGY",
            reporting_date=FIXTURE_DATE,
            total_rows=3,
            valid_rows=3,
            mode="INCREMENTAL",
            status="COMPLETED",
            uploaded_at=datetime(2026, 11, 20, 8, 0, 0),
            audit_details=json.dumps({"upload_id": orig_upload_id, "ingested_at": "2026-11-20T08:00:00", "plants_affected": ["IN-TN-01"]}),
        )
        corr_upload = UploadHistory(
            upload_id=corr_upload_id,
            filename="energy_corr.csv",
            file_format="CSV",
            file_size_bytes=1024,
            report_type="ENERGY",
            reporting_date=FIXTURE_DATE,
            total_rows=3,
            valid_rows=3,
            mode="OVERWRITE_CORRECTION",
            status="COMPLETED",
            uploaded_at=datetime(2026, 11, 20, 9, 0, 0),
            audit_details=json.dumps({
                "upload_id": corr_upload_id,
                "ingested_at": "2026-11-20T09:00:00",
                "plants_affected": ["IN-TN-01"],
                "superseded_batches": {orig_upload_id: 3},
            }),
        )
        self.session.add_all([orig_upload, corr_upload])

        # 3 surviving rows attributed to corr_upload_id, 0 attributed to orig_upload_id
        for i in range(3):
            self.session.add(
                FactEnergyMeterHourly(
                    meter_reading_id=f"MTR_CORR_{i}",
                    timestamp=datetime(2026, 11, 20, i, 0, 0),
                    date=FIXTURE_DATE,
                    plant_id="IN-TN-01",
                    meter_id="MTR-SMT",
                    area="SMT",
                    energy_source="ELECTRICITY",
                    consumption_kwh=Decimal("100.0"),
                    demand_kw=Decimal("25.0"),
                    power_factor=Decimal("0.95"),
                    tariff_inr_per_kwh=Decimal("7.5"),
                    cost_inr=Decimal("750.0"),
                    co2e_kg=Decimal("82.0"),
                    reading_quality="VALID",
                    upload_id=corr_upload_id,
                    ingested_at=datetime(2026, 11, 20, 9, 0, 0),
                )
            )
        self.session.commit()

        result = _check_source_consistency(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        superseded = [f for f in result.findings if f.reason_code == "UPLOAD_RECORDS_FULLY_SUPERSEDED"]
        self.assertEqual(len(superseded), 1)
        self.assertEqual(superseded[0].affected_entity, orig_upload_id)
        self.assertEqual(superseded[0].status, ReconciliationStatus.PASS)

    def test_source_consistency_partially_superseded_by_correction(self):
        """When subsequent OVERWRITE_CORRECTION supersedes partial rows and remainder survives, check reports PASS."""
        orig_upload_id = "MOD_UP_PART_01"
        corr_upload_id = "MOD_UP_PART_CORR_01"

        orig_upload = UploadHistory(
            upload_id=orig_upload_id,
            filename="energy_part.csv",
            file_format="CSV",
            file_size_bytes=1024,
            report_type="ENERGY",
            reporting_date=FIXTURE_DATE,
            total_rows=4,
            valid_rows=4,
            mode="INCREMENTAL",
            status="COMPLETED",
            uploaded_at=datetime(2026, 11, 20, 8, 0, 0),
            audit_details=json.dumps({"upload_id": orig_upload_id, "ingested_at": "2026-11-20T08:00:00", "plants_affected": ["IN-TN-01"]}),
        )
        corr_upload = UploadHistory(
            upload_id=corr_upload_id,
            filename="energy_part_corr.csv",
            file_format="CSV",
            file_size_bytes=1024,
            report_type="ENERGY",
            reporting_date=FIXTURE_DATE,
            total_rows=2,
            valid_rows=2,
            mode="OVERWRITE_CORRECTION",
            status="COMPLETED",
            uploaded_at=datetime(2026, 11, 20, 9, 0, 0),
            audit_details=json.dumps({
                "upload_id": corr_upload_id,
                "ingested_at": "2026-11-20T09:00:00",
                "plants_affected": ["IN-TN-01"],
                "superseded_batches": {orig_upload_id: 2},
            }),
        )
        self.session.add_all([orig_upload, corr_upload])

        # 2 surviving rows attributed to orig_upload_id, 2 attributed to corr_upload_id
        for i in range(2):
            self.session.add(
                FactEnergyMeterHourly(
                    meter_reading_id=f"MTR_ORIG_SURV_{i}",
                    timestamp=datetime(2026, 11, 20, i, 0, 0),
                    date=FIXTURE_DATE,
                    plant_id="IN-TN-01",
                    meter_id="MTR-SMT",
                    area="SMT",
                    energy_source="ELECTRICITY",
                    consumption_kwh=Decimal("100.0"),
                    demand_kw=Decimal("25.0"),
                    power_factor=Decimal("0.95"),
                    tariff_inr_per_kwh=Decimal("7.5"),
                    cost_inr=Decimal("750.0"),
                    co2e_kg=Decimal("82.0"),
                    reading_quality="VALID",
                    upload_id=orig_upload_id,
                    ingested_at=datetime(2026, 11, 20, 8, 0, 0),
                )
            )
            self.session.add(
                FactEnergyMeterHourly(
                    meter_reading_id=f"MTR_CORR_SURV_{i}",
                    timestamp=datetime(2026, 11, 20, i + 2, 0, 0),
                    date=FIXTURE_DATE,
                    plant_id="IN-TN-01",
                    meter_id="MTR-SMT",
                    area="SMT",
                    energy_source="ELECTRICITY",
                    consumption_kwh=Decimal("110.0"),
                    demand_kw=Decimal("28.0"),
                    power_factor=Decimal("0.95"),
                    tariff_inr_per_kwh=Decimal("7.5"),
                    cost_inr=Decimal("825.0"),
                    co2e_kg=Decimal("90.0"),
                    reading_quality="VALID",
                    upload_id=corr_upload_id,
                    ingested_at=datetime(2026, 11, 20, 9, 0, 0),
                )
            )
        self.session.commit()

        result = _check_source_consistency(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        part_findings = [f for f in result.findings if f.reason_code == "UPLOAD_RECORDS_PARTIALLY_SUPERSEDED"]
        self.assertEqual(len(part_findings), 1)
        self.assertEqual(part_findings[0].affected_entity, orig_upload_id)
        self.assertEqual(part_findings[0].observed_value, 2)
        self.assertEqual(part_findings[0].expected_value, 2)

    def test_source_consistency_historical_correction_attribution_unavailable(self):
        """Historical correction lacking superseded_batches produces UNAVAILABLE."""
        orig_upload_id = "MOD_UP_HIST_01"
        corr_upload_id = "MOD_UP_HIST_CORR_01"

        orig_upload = UploadHistory(
            upload_id=orig_upload_id,
            filename="energy_hist_orig.csv",
            file_format="CSV",
            file_size_bytes=1024,
            report_type="ENERGY",
            reporting_date=FIXTURE_DATE,
            total_rows=5,
            valid_rows=5,
            mode="INCREMENTAL",
            status="COMPLETED",
            uploaded_at=datetime(2026, 11, 20, 8, 0, 0),
            audit_details=json.dumps({"upload_id": orig_upload_id, "ingested_at": "2026-11-20T08:00:00", "plants_affected": ["IN-TN-01"]}),
        )
        # Historical correction upload has overwritten_records but NO superseded_batches
        corr_upload = UploadHistory(
            upload_id=corr_upload_id,
            filename="energy_hist_corr.csv",
            file_format="CSV",
            file_size_bytes=1024,
            report_type="ENERGY",
            reporting_date=FIXTURE_DATE,
            total_rows=5,
            valid_rows=5,
            mode="OVERWRITE_CORRECTION",
            status="COMPLETED",
            uploaded_at=datetime(2026, 11, 20, 9, 0, 0),
            audit_details=json.dumps({
                "upload_id": corr_upload_id,
                "ingested_at": "2026-11-20T09:00:00",
                "plants_affected": ["IN-TN-01"],
                "overwritten_records": 5,  # Historical count, lacking superseded_batches mapping
            }),
        )
        self.session.add_all([orig_upload, corr_upload])
        self.session.commit()

        result = _check_source_consistency(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        hist_findings = [f for f in result.findings if f.reason_code == "HISTORICAL_CORRECTION_ATTRIBUTION_UNAVAILABLE"]
        self.assertEqual(len(hist_findings), 1)
        self.assertEqual(hist_findings[0].affected_entity, orig_upload_id)
        self.assertEqual(hist_findings[0].status, ReconciliationStatus.UNAVAILABLE)
        self.assertIn("predate exact batch attribution", hist_findings[0].explanation)


class TestReconciliationReferenceIntegrity(BaseReconciliationTestCase):
    """Check 6: CHK_REFERENCE_INTEGRITY tests."""

    def test_reference_integrity_pass_on_valid_references(self):
        """Clean dimension references in seeded dataset pass reference integrity check."""
        result = _check_reference_integrity(self.session, SEEDED_START_DATE, SEEDED_END_DATE)
        self.assertEqual(result.check_id, "CHK_REFERENCE_INTEGRITY")
        self.assertEqual(result.category, ReconciliationCategory.REFERENCE_INTEGRITY)
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        # Verify schema boundary notice is present
        meter_unavail = [f for f in result.findings if f.reason_code == "DIM_METER_TABLE_UNAVAILABLE"]
        self.assertEqual(len(meter_unavail), 1)
        self.assertEqual(meter_unavail[0].status, ReconciliationStatus.UNAVAILABLE)

    def test_reference_integrity_emits_dim_meter_unavailable(self):
        """Schema boundary notice DIM_METER_TABLE_UNAVAILABLE is always emitted."""
        result = _check_reference_integrity(self.session, SEEDED_START_DATE, SEEDED_START_DATE)
        findings = [f for f in result.findings if f.reason_code == "DIM_METER_TABLE_UNAVAILABLE"]
        self.assertEqual(len(findings), 1)
        self.assertIn("dim_meter", findings[0].explanation)

    def test_reference_integrity_detects_unregistered_plant(self):
        """Domain Safeguard: Energy telemetry referencing plant not in dim_production_line triggers FAIL."""
        # Insert energy reading with unregistered plant 'UNKNOWN-PLANT-99'
        unreg_record = FactEnergyMeterHourly(
            meter_reading_id="MTR_UNREG_PLANT_01",
            timestamp=datetime(2026, 11, 20, 10, 0, 0),
            date=FIXTURE_DATE,
            plant_id="UNKNOWN-PLANT-99",
            meter_id="MTR-SMT",
            area="SMT",
            energy_source="ELECTRICITY",
            consumption_kwh=Decimal("100.0"),
            demand_kw=Decimal("25.0"),
            power_factor=Decimal("0.95"),
            tariff_inr_per_kwh=Decimal("7.5"),
            cost_inr=Decimal("750.0"),
            co2e_kg=Decimal("82.0"),
            reading_quality="VALID",
        )
        self.session.add(unreg_record)
        self.session.commit()

        result = _check_reference_integrity(self.session, FIXTURE_DATE, FIXTURE_DATE)
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        unreg_findings = [f for f in result.findings if f.reason_code == "UNREGISTERED_PLANT_REFERENCE"]
        self.assertEqual(len(unreg_findings), 1)
        self.assertEqual(unreg_findings[0].plant_id, "UNKNOWN-PLANT-99")
        self.assertEqual(unreg_findings[0].observed_value, 1)
        self.assertEqual(unreg_findings[0].expected_value, 0)
        self.assertIn("does not exist in dim_production_line", unreg_findings[0].explanation)

    def test_reference_integrity_detects_orphan_production_line(self):
        """Orphan line references not registered in dim_production_line trigger FAIL."""
        mock_session = MagicMock()
        mock_orphan_lines = MagicMock()
        mock_orphan_lines.fetchall.return_value = [("IN-TN-01", "GHOST-LINE-99", 5)]
        mock_orphan_prods = MagicMock()
        mock_orphan_prods.fetchall.return_value = []
        mock_unreg_plants = MagicMock()
        mock_unreg_plants.fetchall.return_value = []
        mock_session.execute.side_effect = [mock_orphan_lines, mock_orphan_prods, mock_unreg_plants]

        result = _check_reference_integrity(mock_session, FIXTURE_DATE, FIXTURE_DATE)
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        orphan_findings = [f for f in result.findings if f.reason_code == "ORPHAN_PRODUCTION_LINE_REFERENCE"]
        self.assertEqual(len(orphan_findings), 1)
        self.assertEqual(orphan_findings[0].affected_entity, "GHOST-LINE-99")
        self.assertEqual(orphan_findings[0].observed_value, 5)
        self.assertEqual(orphan_findings[0].difference_unit, "orphan records")

    def test_reference_integrity_detects_orphan_product(self):
        """Orphan product references not registered in dim_product trigger FAIL."""
        mock_session = MagicMock()
        mock_orphan_lines = MagicMock()
        mock_orphan_lines.fetchall.return_value = []
        mock_orphan_prods = MagicMock()
        mock_orphan_prods.fetchall.return_value = [("IN-TN-01", "GHOST-PROD-99", 12)]
        mock_unreg_plants = MagicMock()
        mock_unreg_plants.fetchall.return_value = []
        mock_session.execute.side_effect = [mock_orphan_lines, mock_orphan_prods, mock_unreg_plants]

        result = _check_reference_integrity(mock_session, FIXTURE_DATE, FIXTURE_DATE)
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        orphan_findings = [f for f in result.findings if f.reason_code == "ORPHAN_PRODUCT_REFERENCE"]
        self.assertEqual(len(orphan_findings), 1)
        self.assertEqual(orphan_findings[0].affected_entity, "GHOST-PROD-99")
        self.assertEqual(orphan_findings[0].observed_value, 12)


class TestReconciliationDataQuality(BaseReconciliationTestCase):
    """Check 7: CHK_DATA_QUALITY tests."""

    def test_data_quality_pass_on_clean_data(self):
        """Physical bounds, mathematical quantity balance, and non-negativity pass on clean data."""
        result = _check_data_quality(self.session, SEEDED_START_DATE, SEEDED_END_DATE)
        self.assertEqual(result.check_id, "CHK_DATA_QUALITY")
        self.assertEqual(result.category, ReconciliationCategory.DATA_QUALITY)
        self.assertEqual(result.status, ReconciliationStatus.PASS)
        self.assertEqual(len(result.findings), 0)

    def test_data_quality_detects_timestamp_dimension_mismatch(self):
        """Mismatch between event_ts hour/date and hour/event_date columns triggers FAIL with EVENT_TIMESTAMP_DIMENSION_MISMATCH."""
        # Insert event with hour = 11 while event_ts is 10:00:00 (mismatch)
        mismatch_event = FactHourlyProduction(
            event_id="PROD_MISMATCH_HOUR_01",
            event_ts=datetime(2026, 11, 20, 10, 0, 0),
            event_date=FIXTURE_DATE,
            year=2026,
            month=11,
            week=47,
            day=20,
            hour=11,  # Mismatched hour
            plant_id="IN-TN-01",
            line_id="SMT-L1",
            shift_id="S1",
            product_id="SPH-A15-128",
            production_order_id="ORD-MM-01",
            target_qty=100,
            actual_qty=100,
            good_qty=95,
            reject_qty=5,
            rework_qty=0,
            downtime_min=0,
            downtime_reason="NONE",
            operator_team="TEAM-A",
            source_system="MES",
            data_quality="VALID",
        )
        self.session.add(mismatch_event)
        self.session.commit()

        result = _check_data_quality(self.session, FIXTURE_DATE, FIXTURE_DATE, plant_id="IN-TN-01")
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        mismatch_findings = [f for f in result.findings if f.reason_code == "EVENT_TIMESTAMP_DIMENSION_MISMATCH"]
        self.assertEqual(len(mismatch_findings), 1)
        self.assertEqual(mismatch_findings[0].affected_entity, "SMT-L1")
        self.assertEqual(mismatch_findings[0].observed_value, 1)
        self.assertEqual(mismatch_findings[0].difference_unit, "mismatched records")

    def test_data_quality_detects_negative_energy_consumption(self):
        """Domain Safeguard: Negative energy consumption (< 0 kWh) triggers FAIL with NEGATIVE_ENERGY_CONSUMPTION."""
        mock_session = MagicMock()
        mock_neg_kwh = MagicMock()
        mock_neg_kwh.fetchall.return_value = [("IN-TN-01", "MTR-SMT", 3, Decimal("-15.5"))]
        mock_empty = MagicMock()
        mock_empty.fetchall.return_value = []
        mock_session.execute.side_effect = [mock_neg_kwh, mock_empty, mock_empty, mock_empty, mock_empty]

        result = _check_data_quality(mock_session, FIXTURE_DATE, FIXTURE_DATE)
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        neg_findings = [f for f in result.findings if f.reason_code == "NEGATIVE_ENERGY_CONSUMPTION"]
        self.assertEqual(len(neg_findings), 1)
        self.assertEqual(neg_findings[0].observed_value, -15.5)
        self.assertEqual(neg_findings[0].expected_value, ">= 0.0 kWh")
        self.assertEqual(neg_findings[0].difference, 3)
        self.assertEqual(neg_findings[0].difference_unit, "negative readings")

    def test_data_quality_detects_invalid_power_factor(self):
        """Power factor outside [0.0, 1.0] triggers FAIL with POWER_FACTOR_OUT_OF_RANGE."""
        mock_session = MagicMock()
        mock_pf = MagicMock()
        mock_pf.fetchall.return_value = [("IN-TN-01", "MTR-SMT", 2)]
        mock_empty = MagicMock()
        mock_empty.fetchall.return_value = []
        mock_session.execute.side_effect = [mock_empty, mock_pf, mock_empty, mock_empty, mock_empty]

        result = _check_data_quality(mock_session, FIXTURE_DATE, FIXTURE_DATE)
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        pf_findings = [f for f in result.findings if f.reason_code == "POWER_FACTOR_OUT_OF_RANGE"]
        self.assertEqual(len(pf_findings), 1)
        self.assertEqual(pf_findings[0].expected_value, "0.0 <= power_factor <= 1.0")
        self.assertEqual(pf_findings[0].difference, 2)

    def test_data_quality_detects_quantity_balance_violation(self):
        """Production record where actual_qty != good_qty + reject_qty triggers FAIL with PRODUCTION_QUANTITY_BALANCE_VIOLATION."""
        mock_session = MagicMock()
        mock_qty = MagicMock()
        mock_qty.fetchall.return_value = [("IN-TN-01", "SMT-L1", 4)]
        mock_empty = MagicMock()
        mock_empty.fetchall.return_value = []
        mock_session.execute.side_effect = [mock_empty, mock_empty, mock_qty, mock_empty, mock_empty]

        result = _check_data_quality(mock_session, FIXTURE_DATE, FIXTURE_DATE)
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        qty_findings = [f for f in result.findings if f.reason_code == "PRODUCTION_QUANTITY_BALANCE_VIOLATION"]
        self.assertEqual(len(qty_findings), 1)
        self.assertEqual(qty_findings[0].expected_value, "actual_qty == good_qty + reject_qty")
        self.assertEqual(qty_findings[0].difference, 4)

    def test_data_quality_detects_invalid_downtime_minutes(self):
        """Downtime minutes outside [0, 60] triggers FAIL with DOWNTIME_MINUTES_OUT_OF_RANGE."""
        mock_session = MagicMock()
        mock_dt = MagicMock()
        mock_dt.fetchall.return_value = [("IN-TN-01", "SMT-L1", 1)]
        mock_empty = MagicMock()
        mock_empty.fetchall.return_value = []
        mock_session.execute.side_effect = [mock_empty, mock_empty, mock_empty, mock_dt, mock_empty]

        result = _check_data_quality(mock_session, FIXTURE_DATE, FIXTURE_DATE)
        self.assertEqual(result.status, ReconciliationStatus.FAIL)
        dt_findings = [f for f in result.findings if f.reason_code == "DOWNTIME_MINUTES_OUT_OF_RANGE"]
        self.assertEqual(len(dt_findings), 1)
        self.assertEqual(dt_findings[0].expected_value, "0 <= downtime_min <= 60")
        self.assertEqual(dt_findings[0].difference, 1)


class TestReconciliationOrchestrationAndSummary(BaseReconciliationTestCase):
    """Orchestration, summary rollup, status hierarchy, and check definitions catalog tests."""

    def test_run_cross_source_reconciliation_pass_on_clean_data(self):
        """Full cross-source reconciliation on seeded data returns PASS status."""
        report = run_cross_source_reconciliation(self.session, SEEDED_START_DATE, SEEDED_END_DATE)
        self.assertIsInstance(report, ReconciliationReportResponse)
        self.assertEqual(report.status, ReconciliationStatus.PASS)
        self.assertEqual(report.counts.pass_count, 7)
        self.assertEqual(report.counts.fail_count, 0)
        self.assertEqual(report.counts.warning_count, 0)
        self.assertEqual(report.counts.total_checks, 7)
        self.assertEqual(len(report.checks), 7)
        self.assertEqual(len(report.limitations), len(STANDARD_LIMITATIONS))

    def test_status_hierarchy_warning_dominates_pass(self):
        """When any check produces WARNING and no check produces FAIL, overall status is WARNING."""
        empty_date = date(2026, 1, 1)
        report = run_cross_source_reconciliation(self.session, empty_date, empty_date)
        self.assertEqual(report.status, ReconciliationStatus.WARNING)
        self.assertTrue(report.counts.warning_count > 0)
        self.assertEqual(report.counts.fail_count, 0)

    def test_status_hierarchy_fail_dominates_warning_and_pass(self):
        """When any check produces FAIL, overall status is FAIL regardless of PASS or WARNING checks."""
        # Insert a subhourly timestamp that causes FAIL in CHK_TIMESTAMP_ALIGNMENT
        subhourly_record = FactEnergyMeterHourly(
            meter_reading_id="MTR_FAIL_HIER_01",
            timestamp=datetime(2026, 11, 20, 10, 30, 0),
            date=FIXTURE_DATE,
            plant_id="IN-TN-01",
            meter_id="MTR-SMT",
            area="SMT",
            energy_source="ELECTRICITY",
            consumption_kwh=Decimal("50.0"),
            demand_kw=Decimal("20.0"),
            power_factor=Decimal("0.95"),
            tariff_inr_per_kwh=Decimal("7.5"),
            cost_inr=Decimal("375.0"),
            co2e_kg=Decimal("41.0"),
            reading_quality="VALID",
        )
        self.session.add(subhourly_record)
        self.session.commit()

        report = run_cross_source_reconciliation(self.session, FIXTURE_DATE, FIXTURE_DATE)
        self.assertEqual(report.status, ReconciliationStatus.FAIL)
        self.assertTrue(report.counts.fail_count >= 1)

    def test_category_filter_executes_only_requested_check(self):
        """When category_filter is specified, only that check is executed and returned."""
        report = run_cross_source_reconciliation(
            self.session,
            SEEDED_START_DATE,
            SEEDED_END_DATE,
            category_filter=ReconciliationCategory.ENERGY_COVERAGE,
        )
        self.assertEqual(len(report.checks), 1)
        self.assertEqual(report.checks[0].check_id, "CHK_ENERGY_COVERAGE")
        self.assertEqual(report.counts.total_checks, 1)

    def test_status_filter_filters_findings_inside_checks(self):
        """When status_filter is specified, only findings matching the status are returned."""
        report = run_cross_source_reconciliation(
            self.session,
            SEEDED_START_DATE,
            SEEDED_END_DATE,
            status_filter=ReconciliationStatus.UNAVAILABLE,
        )
        for chk in report.checks:
            for f in chk.findings:
                self.assertEqual(f.status, ReconciliationStatus.UNAVAILABLE)

    def test_get_reconciliation_summary_structure(self):
        """get_reconciliation_summary returns lightweight summary with category_statuses."""
        summary = get_reconciliation_summary(self.session, SEEDED_START_DATE, SEEDED_END_DATE)
        self.assertIsInstance(summary, ReconciliationSummaryResponse)
        self.assertEqual(summary.status, ReconciliationStatus.PASS)
        self.assertEqual(summary.counts.total_checks, 7)
        self.assertEqual(len(summary.category_statuses), 7)
        for cat in ReconciliationCategory:
            self.assertIn(cat.value, summary.category_statuses)
            self.assertEqual(summary.category_statuses[cat.value], ReconciliationStatus.PASS)

    def test_get_supported_check_definitions_catalog(self):
        """get_supported_check_definitions returns catalog of all 7 checks with dimensions."""
        defs = get_supported_check_definitions()
        self.assertEqual(len(defs), 7)
        check_ids = {d.check_id for d in defs}
        expected_ids = {
            "CHK_ENERGY_COVERAGE",
            "CHK_PRODUCTION_COVERAGE",
            "CHK_TIMESTAMP_ALIGNMENT",
            "CHK_DUPLICATE_RECORDS",
            "CHK_SOURCE_CONSISTENCY",
            "CHK_REFERENCE_INTEGRITY",
            "CHK_DATA_QUALITY",
        }
        self.assertEqual(check_ids, expected_ids)
        for d in defs:
            self.assertTrue(len(d.source_tables) >= 1)
            self.assertTrue(len(d.name) > 0)
            self.assertTrue(len(d.description) > 0)


if __name__ == "__main__":
    unittest.main()
