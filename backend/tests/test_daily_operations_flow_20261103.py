"""
End-to-end integration test validating the complete Daily Operations pipeline flow
for reporting date 2026-11-03 on the local disposable PostgreSQL database.

Validates:
1. File validation succeeds (Energy: 240 rows, Production: 96 rows).
2. Explicit confirmation triggers ingestion.
3. Energy and production records are inserted correctly into fact tables.
4. Upload IDs link to the inserted records.
5. Pipeline Phase 3 becomes COMPLETED.
6. Phase 4 (Data Reconciliation) becomes available (unlocked from BLOCKED to NOT_STARTED).
7. Refreshing pipeline status preserves the correct state from database ground truth.
8. Repeated confirmation does not create duplicate records.
"""

from datetime import date
import os
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.main import app
from app.models.source_data import FactEnergyMeterHourly, FactHourlyProduction
from app.models.upload_history import UploadHistory
from app.services.daily_pipeline_service import get_daily_pipeline_status, reset_daily_pipeline_state
from app.services.daily_report_service import clear_staged_report

TEST_DATE = date(2026, 11, 3)
PLANT_ID = "IN-TN-01"

ENERGY_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "datasets",
    "synthetic_daily_reports_nov_2026",
    "energy_2026-11-03.csv",
)
PROD_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "datasets",
    "synthetic_daily_reports_nov_2026",
    "production_2026-11-03.csv",
)


class TestDailyOperationsFlow20261103(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session_factory = get_session_factory()
        cls.client = TestClient(app)
        assert os.path.exists(ENERGY_CSV_PATH), f"Energy CSV missing at {ENERGY_CSV_PATH}"
        assert os.path.exists(PROD_CSV_PATH), f"Production CSV missing at {PROD_CSV_PATH}"

    def setUp(self):
        self.session: Session = self.session_factory()
        self._cleanup_date(TEST_DATE)

    def tearDown(self):
        self._cleanup_date(TEST_DATE)
        self.session.close()

    def _cleanup_date(self, target_date: date):
        self.session.query(FactEnergyMeterHourly).filter(FactEnergyMeterHourly.date == target_date).delete()
        self.session.query(FactHourlyProduction).filter(FactHourlyProduction.event_date == target_date).delete()
        self.session.query(UploadHistory).filter(UploadHistory.reporting_date == target_date).delete()
        self.session.commit()
        clear_staged_report(target_date, "ENERGY")
        clear_staged_report(target_date, "PRODUCTION")

    def test_complete_operations_ingestion_and_verification_flow(self):
        # 1. Verify initial clean state
        status_before = get_daily_pipeline_status(self.session, TEST_DATE, PLANT_ID)
        self.assertFalse(status_before["database_state"]["has_data"])
        self.assertEqual(status_before["stages"]["database_ingestion"]["status"], "BLOCKED")
        self.assertEqual(status_before["stages"]["data_reconciliation"]["status"], "BLOCKED")

        # 2. File Validation: Validate Energy and Production files
        with open(ENERGY_CSV_PATH, "rb") as ef:
            energy_bytes = ef.read()
        with open(PROD_CSV_PATH, "rb") as pf:
            prod_bytes = pf.read()

        val_energy_res = self.client.post(
            "/api/daily-reports/validate",
            data={"report_type": "ENERGY", "confirmed_date": "2026-11-03", "mode": "INCREMENTAL"},
            files={"file": ("energy_2026-11-03.csv", energy_bytes, "text/csv")},
        )
        self.assertEqual(val_energy_res.status_code, 200)
        energy_val = val_energy_res.json()
        self.assertEqual(energy_val["summary"]["valid_rows"], 240)
        self.assertEqual(energy_val["summary"]["rejected_rows"], 0)
        energy_upload_id = energy_val.get("upload_id")
        self.assertTrue(energy_upload_id and energy_upload_id.startswith("UPL-20261103-"))

        val_prod_res = self.client.post(
            "/api/daily-reports/validate",
            data={"report_type": "PRODUCTION", "confirmed_date": "2026-11-03", "mode": "INCREMENTAL"},
            files={"file": ("production_2026-11-03.csv", prod_bytes, "text/csv")},
        )
        self.assertEqual(val_prod_res.status_code, 200)
        prod_val = val_prod_res.json()
        self.assertEqual(prod_val["summary"]["valid_rows"], 96)
        self.assertEqual(prod_val["summary"]["rejected_rows"], 0)
        prod_upload_id = prod_val.get("upload_id")
        self.assertTrue(prod_upload_id and prod_upload_id.startswith("UPL-20261103-"))

        # 3. Verify Pipeline State after validation: Phase 2 COMPLETED, Phase 3 NOT_STARTED, Phase 4 BLOCKED
        status_after_val = self.client.get(
            "/api/daily-reports/pipeline-status",
            params={"reporting_date": "2026-11-03", "plant_id": PLANT_ID},
        ).json()
        self.assertEqual(status_after_val["stages"]["validation"]["status"], "COMPLETED")
        self.assertEqual(status_after_val["stages"]["database_ingestion"]["status"], "NOT_STARTED")
        self.assertEqual(status_after_val["stages"]["data_reconciliation"]["status"], "BLOCKED")
        self.assertFalse(status_after_val["database_state"]["has_data"])

        # 4. Explicit Confirmation triggers real database ingestion (using staged files and upload IDs)
        ingest_energy_res = self.client.post(
            "/api/daily-reports/ingest",
            data={
                "report_type": "ENERGY",
                "reporting_date": "2026-11-03",
                "plant_id": PLANT_ID,
                "upload_id": energy_upload_id,
                "mode": "INCREMENTAL",
            },
        )
        self.assertEqual(ingest_energy_res.status_code, 200)
        energy_ingest_data = ingest_energy_res.json()
        self.assertEqual(energy_ingest_data["upload_id"], energy_upload_id)
        self.assertEqual(energy_ingest_data["imported_rows"], 240)

        ingest_prod_res = self.client.post(
            "/api/daily-reports/ingest",
            data={
                "report_type": "PRODUCTION",
                "reporting_date": "2026-11-03",
                "plant_id": PLANT_ID,
                "upload_id": prod_upload_id,
                "mode": "INCREMENTAL",
            },
        )
        self.assertEqual(ingest_prod_res.status_code, 200)
        prod_ingest_data = ingest_prod_res.json()
        self.assertEqual(prod_ingest_data["upload_id"], prod_upload_id)
        self.assertEqual(prod_ingest_data["imported_rows"], 96)

        # 5. Verify records inserted into PostgreSQL fact tables and linked to upload IDs
        self.session.expire_all()
        energy_in_db = self.session.query(FactEnergyMeterHourly).filter(
            FactEnergyMeterHourly.date == TEST_DATE,
            FactEnergyMeterHourly.upload_id == energy_upload_id,
        ).all()
        self.assertEqual(len(energy_in_db), 240)

        prod_in_db = self.session.query(FactHourlyProduction).filter(
            FactHourlyProduction.event_date == TEST_DATE,
            FactHourlyProduction.upload_id == prod_upload_id,
        ).all()
        self.assertEqual(len(prod_in_db), 96)

        # 6. Verify via Verification Endpoint
        verify_res = self.client.get(
            "/api/daily-reports/verify-ingestion",
            params={"reporting_date": "2026-11-03", "plant_id": PLANT_ID},
        ).json()
        self.assertTrue(verify_res["verified"])
        self.assertEqual(verify_res["linked_energy_records"], 120)  # Plant IN-TN-01 scope
        self.assertEqual(verify_res["linked_production_records"], 48)  # Plant IN-TN-01 scope
        self.assertIn(energy_upload_id, verify_res["upload_ids"])
        self.assertIn(prod_upload_id, verify_res["upload_ids"])

        # 7. Verify Pipeline Stage 3 becomes COMPLETED, Phase 4 becomes available (NOT_STARTED)
        status_after_ingest = self.client.get(
            "/api/daily-reports/pipeline-status",
            params={"reporting_date": "2026-11-03", "plant_id": PLANT_ID},
        ).json()
        self.assertEqual(status_after_ingest["stages"]["database_ingestion"]["status"], "COMPLETED")
        self.assertEqual(status_after_ingest["stages"]["data_reconciliation"]["status"], "NOT_STARTED")
        self.assertEqual(status_after_ingest["current_stage"], "data_reconciliation")
        self.assertTrue(status_after_ingest["database_state"]["has_data"])

        # 8. Refreshing preserves correct state from PostgreSQL ground truth
        status_refreshed = get_daily_pipeline_status(self.session, TEST_DATE, PLANT_ID)
        self.assertEqual(status_refreshed["stages"]["database_ingestion"]["status"], "COMPLETED")
        self.assertEqual(status_refreshed["stages"]["data_reconciliation"]["status"], "NOT_STARTED")
        self.assertEqual(status_refreshed["current_stage"], "data_reconciliation")

        # 9. Repeated confirmation does not create duplicate records
        # Attempting to re-ingest in INCREMENTAL mode:
        repeat_res = self.client.post(
            "/api/daily-reports/ingest",
            data={"report_type": "ENERGY", "reporting_date": "2026-11-03", "mode": "INCREMENTAL"},
            files={"file": ("energy_2026-11-03.csv", energy_bytes, "text/csv")},
        )
        self.assertEqual(repeat_res.status_code, 400)
        self.assertIn("0 valid records found", repeat_res.json()["detail"])

        # Row counts in database remain exactly 240 and 96
        total_energy = self.session.query(func.count(FactEnergyMeterHourly.meter_reading_id)).filter(
            FactEnergyMeterHourly.date == TEST_DATE
        ).scalar()
        total_prod = self.session.query(func.count(FactHourlyProduction.event_id)).filter(
            FactHourlyProduction.event_date == TEST_DATE
        ).scalar()
        self.assertEqual(total_energy, 240)
        self.assertEqual(total_prod, 96)


if __name__ == "__main__":
    unittest.main()
