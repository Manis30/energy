"""
Automated database-backed tests for Daily Reports ingestion, duplicates, corrections, and coverage.

Targeting disposable PostgreSQL database (energy_disposable_db):
1. Preview vs Ingest consistency.
2. Invalid-row reporting and partial ingestion.
3. Transaction rollback on ingestion failure.
4. Correct upload-history creation and audit metadata.
5. Fact record upload provenance and legacy record distinction.
6. Incremental duplicate detection and idempotent re-upload.
7. Explicit overwrite/correction behavior and superseded-batch tracking.
8. Energy and production correction isolation.
9. Repeated correction chains.
10. Coverage and history API responses (including empty range semantics).
"""

from datetime import date, datetime
from decimal import Decimal
import json
import unittest
from unittest.mock import patch

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.models.source_data import FactEnergyMeterHourly, FactHourlyProduction
from app.models.upload_history import UploadHistory
from app.services.daily_report_service import (
    get_daily_report_coverage,
    ingest_validated_report,
    validate_report_file,
)

# Test dates chosen outside seeded range (seeded: 2026-01-01 to 2026-03-31)
TEST_DATE_1 = date(2026, 5, 10)
TEST_DATE_2 = date(2026, 5, 11)
TEST_DATE_EMPTY = date(2026, 5, 25)


def _build_energy_csv(
    reporting_date: date,
    plant_id: str = "IN-TN-01",
    meter_id: str = "MTR-SMT",
    consumption_kwh: float = 120.0,
    demand_kw: float = 45.0,
    power_factor: float = 0.95,
) -> bytes:
    """Helper to construct valid energy daily report CSV bytes."""
    header = (
        "timestamp,date,plant_id,meter_id,area,energy_source,consumption_kwh,demand_kw,"
        "power_factor,tariff_inr_per_kwh,cost_inr,co2e_kg,reading_quality\n"
    )
    rows = []
    for h in [0, 1]:
        ts = f"{reporting_date.isoformat()} {h:02d}:00:00"
        cost = round(consumption_kwh * 7.5, 2)
        co2 = round(consumption_kwh * 0.82, 2)
        rows.append(
            f"{ts},{reporting_date.isoformat()},{plant_id},{meter_id},SMT,ELECTRICITY,"
            f"{consumption_kwh},{demand_kw},{power_factor},7.50,{cost},{co2},VALID\n"
        )
    return (header + "".join(rows)).encode("utf-8")


def _build_production_csv(
    reporting_date: date,
    plant_id: str = "IN-TN-01",
    line_id: str = "SMT-L1",
    product_id: str = "SPH-A15-128",
    actual_qty: int = 500,
    good_qty: int = 490,
    reject_qty: int = 10,
) -> bytes:
    """Helper to construct valid production daily report CSV bytes."""
    header = (
        "event_ts,event_date,plant_id,line_id,shift_id,product_id,production_order_id,"
        "target_qty,actual_qty,good_qty,reject_qty,rework_qty,downtime_min,downtime_reason,"
        "operator_team,source_system,data_quality,hour\n"
    )
    rows = []
    for h in [8, 9]:
        ts = f"{reporting_date.isoformat()} {h:02d}:00:00"
        rows.append(
            f"{ts},{reporting_date.isoformat()},{plant_id},{line_id},SHIFT-A,{product_id},"
            f"PO-2026-TEST,{actual_qty},{actual_qty},{good_qty},{reject_qty},0,0,None,"
            f"Team-A,MES,VALID,{h}\n"
        )
    return (header + "".join(rows)).encode("utf-8")


class TestDailyReportsIngestAndCorrection(unittest.TestCase):
    """Database-backed test suite for daily reports workflows."""

    @classmethod
    def setUpClass(cls):
        cls.session_factory = get_session_factory()

    def setUp(self):
        self.session: Session = self.session_factory()
        self._cleanup_test_data()

    def tearDown(self):
        self._cleanup_test_data()
        self.session.close()

    def _cleanup_test_data(self):
        """Clean up any records created for the test dates to preserve database cleanliness."""
        test_dates = [TEST_DATE_1, TEST_DATE_2, TEST_DATE_EMPTY]
        self.session.execute(
            delete(FactEnergyMeterHourly).where(FactEnergyMeterHourly.date.in_(test_dates))
        )
        self.session.execute(
            delete(FactHourlyProduction).where(FactHourlyProduction.event_date.in_(test_dates))
        )
        self.session.execute(
            delete(UploadHistory).where(UploadHistory.reporting_date.in_(test_dates))
        )
        self.session.commit()

    # ---------------------------------------------------------
    # 1. Preview vs Ingestion Consistency & Partial Ingestion
    # ---------------------------------------------------------

    def test_preview_valid_and_invalid_rows_reporting(self):
        """Preview reports row numbers and error details for mixed files without mutating DB."""
        # Row 1 valid, Row 2 invalid (negative consumption)
        csv_bytes = (
            "timestamp,date,plant_id,meter_id,area,energy_source,consumption_kwh,demand_kw,"
            "power_factor,tariff_inr_per_kwh,cost_inr,co2e_kg,reading_quality\n"
            f"{TEST_DATE_1.isoformat()} 00:00:00,{TEST_DATE_1.isoformat()},IN-TN-01,MTR-SMT,SMT,ELECTRICITY,100,25,0.95,7.5,750,82,VALID\n"
            f"{TEST_DATE_1.isoformat()} 01:00:00,{TEST_DATE_1.isoformat()},IN-TN-01,MTR-SMT,SMT,ELECTRICITY,-50,25,0.95,7.5,750,82,VALID\n"
        ).encode("utf-8")

        res = validate_report_file(
            session=self.session,
            filename="mixed_energy.csv",
            file_bytes=csv_bytes,
            report_type="ENERGY",
            confirmed_date=TEST_DATE_1,
        )

        self.assertEqual(res["summary"].total_rows, 2)
        self.assertEqual(res["summary"].valid_rows, 1)
        self.assertEqual(res["summary"].rejected_rows, 1)
        self.assertEqual(len(res["preview"]), 2)
        self.assertEqual(res["preview"][0].status, "VALID")
        self.assertEqual(res["preview"][1].status, "REJECTED")
        self.assertTrue(any(e.column == "consumption_kwh" for e in res["errors"]))

        # Database remains untouched
        count = self.session.execute(
            select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.date == TEST_DATE_1)
        ).scalars().all()
        self.assertEqual(len(count), 0)

    def test_ingest_partial_report_only_valid_records_imported(self):
        """When an upload has partial valid rows, valid records are ingested and status is PARTIAL."""
        csv_bytes = (
            "timestamp,date,plant_id,meter_id,area,energy_source,consumption_kwh,demand_kw,"
            "power_factor,tariff_inr_per_kwh,cost_inr,co2e_kg,reading_quality\n"
            f"{TEST_DATE_1.isoformat()} 00:00:00,{TEST_DATE_1.isoformat()},IN-TN-01,MTR-SMT,SMT,ELECTRICITY,100,25,0.95,7.5,750,82,VALID\n"
            f"{TEST_DATE_1.isoformat()} 01:00:00,{TEST_DATE_1.isoformat()},IN-TN-01,MTR-SMT,SMT,ELECTRICITY,-50,25,0.95,7.5,750,82,VALID\n"
        ).encode("utf-8")

        res = ingest_validated_report(
            session=self.session,
            filename="partial_energy.csv",
            file_bytes=csv_bytes,
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="INCREMENTAL",
        )

        self.assertEqual(res["status"], "PARTIAL")
        self.assertEqual(res["imported_rows"], 1)
        self.assertEqual(res["rejected_rows"], 1)

        # Verify exactly 1 record is persisted in FactEnergyMeterHourly
        db_records = self.session.execute(
            select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.date == TEST_DATE_1)
        ).scalars().all()
        self.assertEqual(len(db_records), 1)
        self.assertEqual(db_records[0].consumption_kwh, Decimal("100"))
        self.assertEqual(db_records[0].upload_id, res["upload_id"])

        # Verify UploadHistory entry
        history = self.session.execute(
            select(UploadHistory).where(UploadHistory.upload_id == res["upload_id"])
        ).scalar_one()
        self.assertEqual(history.status, "PARTIAL")
        self.assertEqual(history.valid_rows, 1)
        self.assertEqual(history.rejected_rows, 1)

    def test_ingest_zero_valid_records_aborts(self):
        """When 0 valid records exist, ingestion aborts with ValueError and inserts zero records."""
        all_invalid_csv = (
            "timestamp,date,plant_id,meter_id,area,energy_source,consumption_kwh,demand_kw,"
            "power_factor,tariff_inr_per_kwh,cost_inr,co2e_kg,reading_quality\n"
            f"{TEST_DATE_1.isoformat()} 00:00:00,{TEST_DATE_1.isoformat()},IN-TN-01,MTR-SMT,SMT,ELECTRICITY,-10,25,0.95,7.5,750,82,VALID\n"
        ).encode("utf-8")

        with self.assertRaises(ValueError) as ctx:
            ingest_validated_report(
                session=self.session,
                filename="all_invalid.csv",
                file_bytes=all_invalid_csv,
                report_type="ENERGY",
                reporting_date=TEST_DATE_1,
            )
        self.assertIn("0 valid records found", str(ctx.exception))

        count = self.session.execute(
            select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.date == TEST_DATE_1)
        ).scalars().all()
        self.assertEqual(len(count), 0)

    # ---------------------------------------------------------
    # 2. Transaction Rollback on Ingestion Failure
    # ---------------------------------------------------------

    def test_transaction_rollback_on_database_error(self):
        """If database insertion fails mid-transaction, session is rolled back completely."""
        csv_bytes = _build_energy_csv(TEST_DATE_1)

        with patch.object(
            self.session, "bulk_insert_mappings", side_effect=RuntimeError("Simulated Database I/O Error")
        ):
            with self.assertRaises(RuntimeError):
                ingest_validated_report(
                    session=self.session,
                    filename="rollback_test.csv",
                    file_bytes=csv_bytes,
                    report_type="ENERGY",
                    reporting_date=TEST_DATE_1,
                )

        # Confirm zero records exist in fact table
        db_records = self.session.execute(
            select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.date == TEST_DATE_1)
        ).scalars().all()
        self.assertEqual(len(db_records), 0)

    # ---------------------------------------------------------
    # 3. Provenance and Legacy Record Distinguishability
    # ---------------------------------------------------------

    def test_fact_record_provenance_stamping(self):
        """Ingested fact records are stamped with upload_id and ingested_at timestamp."""
        csv_bytes = _build_energy_csv(TEST_DATE_1)
        res = ingest_validated_report(
            session=self.session,
            filename="provenance_test.csv",
            file_bytes=csv_bytes,
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
        )

        db_records = self.session.execute(
            select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.date == TEST_DATE_1)
        ).scalars().all()
        self.assertEqual(len(db_records), 2)
        for r in db_records:
            self.assertEqual(r.upload_id, res["upload_id"])
            self.assertIsNotNone(r.ingested_at)
            self.assertIsInstance(r.ingested_at, datetime)

    def test_legacy_records_remain_distinguishable(self):
        """Pre-existing records with upload_id IS NULL are preserved and distinguishable."""
        # Insert a simulated legacy record directly
        legacy_rec = FactEnergyMeterHourly(
            meter_reading_id="EN-LEGACY-001",
            timestamp=datetime(2026, 5, 10, 12, 0, 0),
            date=TEST_DATE_1,
            plant_id="IN-TN-01",
            meter_id="MTR-SMT",
            area="SMT",
            energy_source="ELECTRICITY",
            consumption_kwh=Decimal("95.0"),
            demand_kw=Decimal("20.0"),
            power_factor=Decimal("0.94"),
            tariff_inr_per_kwh=Decimal("7.5"),
            cost_inr=Decimal("712.5"),
            co2e_kg=Decimal("77.9"),
            reading_quality="VALID",
            upload_id=None,  # Legacy record
            ingested_at=None,
        )
        self.session.add(legacy_rec)
        self.session.commit()

        # Ingest a new batch for hour 0 and 1
        csv_bytes = _build_energy_csv(TEST_DATE_1)
        res = ingest_validated_report(
            session=self.session,
            filename="batch_with_legacy.csv",
            file_bytes=csv_bytes,
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="INCREMENTAL",
        )

        # Total 3 records: 2 new from upload, 1 legacy untouched
        all_recs = self.session.execute(
            select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.date == TEST_DATE_1)
        ).scalars().all()
        self.assertEqual(len(all_recs), 3)

        legacy = [r for r in all_recs if r.upload_id is None]
        new_batch = [r for r in all_recs if r.upload_id == res["upload_id"]]
        self.assertEqual(len(legacy), 1)
        self.assertEqual(len(new_batch), 2)
        self.assertEqual(legacy[0].meter_reading_id, "EN-LEGACY-001")

    # ---------------------------------------------------------
    # 4. Duplicate Handling & Idempotency
    # ---------------------------------------------------------

    def test_incremental_duplicate_detection_and_idempotency(self):
        """In INCREMENTAL mode, re-uploading identical rows skips them without duplicate insertion."""
        csv_bytes = _build_energy_csv(TEST_DATE_1)

        # Initial upload
        res1 = ingest_validated_report(
            session=self.session,
            filename="energy_initial.csv",
            file_bytes=csv_bytes,
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="INCREMENTAL",
        )
        self.assertEqual(res1["imported_rows"], 2)

        # Re-validate: reports DUPLICATE_IN_DATABASE
        val2 = validate_report_file(
            session=self.session,
            filename="energy_initial.csv",
            file_bytes=csv_bytes,
            report_type="ENERGY",
            confirmed_date=TEST_DATE_1,
            mode="INCREMENTAL",
        )
        self.assertEqual(val2["summary"].valid_rows, 0)
        self.assertEqual(val2["summary"].duplicate_rows, 2)
        self.assertTrue(all(p.status == "DUPLICATE" for p in val2["preview"]))

        # Re-uploading raises ValueError (0 valid records to import)
        with self.assertRaises(ValueError) as ctx:
            ingest_validated_report(
                session=self.session,
                filename="energy_initial.csv",
                file_bytes=csv_bytes,
                report_type="ENERGY",
                reporting_date=TEST_DATE_1,
                mode="INCREMENTAL",
            )
        self.assertIn("0 valid records found", str(ctx.exception))

        # Still exactly 2 rows in database
        db_records = self.session.execute(
            select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.date == TEST_DATE_1)
        ).scalars().all()
        self.assertEqual(len(db_records), 2)

    # ---------------------------------------------------------
    # 5. Explicit Overwrite/Correction Behavior & Supersession
    # ---------------------------------------------------------

    def test_overwrite_correction_replaces_exact_business_keys(self):
        """OVERWRITE_CORRECTION replaces matching keys, stamps new upload_id, and records superseded batch."""
        # Initial batch (consumption 100)
        csv_batch_1 = _build_energy_csv(TEST_DATE_1, consumption_kwh=100.0)
        res1 = ingest_validated_report(
            session=self.session,
            filename="batch1.csv",
            file_bytes=csv_batch_1,
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="INCREMENTAL",
        )
        upload_id_1 = res1["upload_id"]

        # Correction batch (consumption 150)
        csv_batch_2 = _build_energy_csv(TEST_DATE_1, consumption_kwh=150.0)
        res2 = ingest_validated_report(
            session=self.session,
            filename="batch2_corrected.csv",
            file_bytes=csv_batch_2,
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="OVERWRITE_CORRECTION",
        )
        upload_id_2 = res2["upload_id"]

        self.assertEqual(res2["status"], "COMPLETED")
        self.assertEqual(res2["imported_rows"], 2)
        self.assertEqual(res2["replaced_rows"], 2)

        # Verify fact table holds updated consumption values and Batch 2 upload_id
        records = self.session.execute(
            select(FactEnergyMeterHourly)
            .where(FactEnergyMeterHourly.date == TEST_DATE_1)
            .order_by(FactEnergyMeterHourly.timestamp)
        ).scalars().all()
        self.assertEqual(len(records), 2)
        for r in records:
            self.assertEqual(r.consumption_kwh, Decimal("150.0"))
            self.assertEqual(r.upload_id, upload_id_2)

        # Verify audit details record the superseded batch
        history2 = self.session.execute(
            select(UploadHistory).where(UploadHistory.upload_id == upload_id_2)
        ).scalar_one()
        audit_info = json.loads(history2.audit_details)
        self.assertEqual(audit_info["overwritten_records"], 2)
        self.assertEqual(audit_info["superseded_batches"].get(upload_id_1), 2)

    def test_repeated_correction_chains(self):
        """Repeated corrections (A -> B -> C) preserve full audit trail in UploadHistory."""
        # Batch 1
        res1 = ingest_validated_report(
            session=self.session,
            filename="batch1.csv",
            file_bytes=_build_energy_csv(TEST_DATE_1, consumption_kwh=100.0),
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="INCREMENTAL",
        )

        # Batch 2 correcting Batch 1
        res2 = ingest_validated_report(
            session=self.session,
            filename="batch2.csv",
            file_bytes=_build_energy_csv(TEST_DATE_1, consumption_kwh=150.0),
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="OVERWRITE_CORRECTION",
        )

        # Batch 3 correcting Batch 2
        res3 = ingest_validated_report(
            session=self.session,
            filename="batch3.csv",
            file_bytes=_build_energy_csv(TEST_DATE_1, consumption_kwh=200.0),
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="OVERWRITE_CORRECTION",
        )

        # Final state matches Batch 3
        records = self.session.execute(
            select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.date == TEST_DATE_1)
        ).scalars().all()
        self.assertEqual(len(records), 2)
        self.assertTrue(all(r.consumption_kwh == Decimal("200.0") for r in records))
        self.assertTrue(all(r.upload_id == res3["upload_id"] for r in records))

        # Check Batch 3 audit details supersedes Batch 2
        h3 = self.session.execute(
            select(UploadHistory).where(UploadHistory.upload_id == res3["upload_id"])
        ).scalar_one()
        audit3 = json.loads(h3.audit_details)
        self.assertEqual(audit3["superseded_batches"].get(res2["upload_id"]), 2)

        # All 3 history entries exist
        history_list = self.session.execute(
            select(UploadHistory)
            .where(UploadHistory.reporting_date == TEST_DATE_1)
            .order_by(UploadHistory.uploaded_at.asc())
        ).scalars().all()
        self.assertEqual(len(history_list), 3)

    # ---------------------------------------------------------
    # 6. Energy and Production Correction Isolation
    # ---------------------------------------------------------

    def test_energy_and_production_correction_isolation(self):
        """Overwriting Energy does not touch Production records on the same date, and vice versa."""
        # Ingest Energy for TEST_DATE_1
        res_energy1 = ingest_validated_report(
            session=self.session,
            filename="energy_day1.csv",
            file_bytes=_build_energy_csv(TEST_DATE_1, consumption_kwh=100.0),
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="INCREMENTAL",
        )

        # Ingest Production for same date TEST_DATE_1
        res_prod1 = ingest_validated_report(
            session=self.session,
            filename="prod_day1.csv",
            file_bytes=_build_production_csv(TEST_DATE_1, actual_qty=500),
            report_type="PRODUCTION",
            reporting_date=TEST_DATE_1,
            mode="INCREMENTAL",
        )

        # Overwrite ENERGY only
        ingest_validated_report(
            session=self.session,
            filename="energy_corrected.csv",
            file_bytes=_build_energy_csv(TEST_DATE_1, consumption_kwh=160.0),
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="OVERWRITE_CORRECTION",
        )

        # Verify Production records are completely untouched
        prod_records = self.session.execute(
            select(FactHourlyProduction).where(FactHourlyProduction.event_date == TEST_DATE_1)
        ).scalars().all()
        self.assertEqual(len(prod_records), 2)
        self.assertTrue(all(p.upload_id == res_prod1["upload_id"] for p in prod_records))
        self.assertTrue(all(p.actual_qty == 500 for p in prod_records))

        # Overwrite PRODUCTION only
        ingest_validated_report(
            session=self.session,
            filename="prod_corrected.csv",
            file_bytes=_build_production_csv(TEST_DATE_1, actual_qty=600, good_qty=590, reject_qty=10),
            report_type="PRODUCTION",
            reporting_date=TEST_DATE_1,
            mode="OVERWRITE_CORRECTION",
        )

        # Verify Energy records are completely untouched
        energy_records = self.session.execute(
            select(FactEnergyMeterHourly).where(FactEnergyMeterHourly.date == TEST_DATE_1)
        ).scalars().all()
        self.assertEqual(len(energy_records), 2)
        self.assertTrue(all(e.consumption_kwh == Decimal("160.0") for e in energy_records))

    # ---------------------------------------------------------
    # 7. Coverage API and Empty Dataset Semantics
    # ---------------------------------------------------------

    def test_get_daily_report_coverage_and_empty_range(self):
        """Coverage accurately groups persisted data and returns NO_RECORDS for unpopulated dates."""
        # Ingest records on TEST_DATE_1
        ingest_validated_report(
            session=self.session,
            filename="energy_cov.csv",
            file_bytes=_build_energy_csv(TEST_DATE_1),
            report_type="ENERGY",
            reporting_date=TEST_DATE_1,
            mode="INCREMENTAL",
        )

        cov = get_daily_report_coverage(
            session=self.session,
            start_date=TEST_DATE_1,
            end_date=TEST_DATE_EMPTY,
        )

        self.assertIn("energy_coverage", cov)
        self.assertIn("production_coverage", cov)
        self.assertIn("registered_energy_meters", cov)

        # Find TEST_DATE_1 in energy coverage for IN-TN-01
        day1_cov = next(
            (
                c
                for c in cov["energy_coverage"]
                if c["reporting_date"] == TEST_DATE_1 and c["plant_id"] == "IN-TN-01"
            ),
            None,
        )
        self.assertIsNotNone(day1_cov)
        self.assertEqual(day1_cov["record_status"], "OBSERVED")
        self.assertEqual(day1_cov["record_count"], 2)
        self.assertIn("MTR-SMT", day1_cov["observed_entities"])

        # Find TEST_DATE_EMPTY in energy coverage
        empty_cov = next((c for c in cov["energy_coverage"] if c["reporting_date"] == TEST_DATE_EMPTY), None)
        if empty_cov:
            self.assertEqual(empty_cov["record_status"], "NO_RECORDS")
            self.assertEqual(empty_cov["record_count"], 0)


if __name__ == "__main__":
    unittest.main()
