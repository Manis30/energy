"""
Automated Regression and Integrity Test Suite for Source Record Provenance Drill-Down.

Phase 5.1 — Task 2 Verification:
1. All 5 Lineage States:
   - AVAILABLE: Both physical source record and batch upload history exist.
   - MULTI_SOURCE: Production and energy records both exist and retain semantic roles.
   - LEGACY_UNLINKED: Historical finding/occurrence has no stored source identity.
   - SOURCE_MISSING: Stored source record identifier exists, but physical row is absent.
   - UPLOAD_UNAVAILABLE: Physical source record exists, but upload history is unavailable.
2. Distinct Status Decoupling:
   - Physical source record status ('FOUND'/'MISSING') and upload status ('AVAILABLE'/'UNAVAILABLE_HISTORICAL') remain decoupled.
3. Integrity and Security Boundaries:
   - 404 on non-existent finding.
   - 404 on non-existent occurrence.
   - 404 on occurrence belonging to a different finding (strict ownership validation).
   - Unsupported source table rejected without query execution.
   - Graceful handling of invalid or missing source identifiers.
   - Multi-source occurrences preserve individual roles and stream lineage states.
   - Legacy records receive no fabricated IDs or upload metadata.
   - Provenance retrieval is strictly read-only and causes zero state mutations.
4. Performance and Query Complexity:
   - Zero N+1 queries: multi-source occurrences resolve in <= 4 batch queries.
5. API Contract & Schema Compliance:
   - Evaluates both /api/findings and /api/v1/findings routes.
   - Validates response schemas against OccurrenceProvenanceResponse.
   - Validates proper JSON serialization of decimals and nullable fields.
   - Ensures zero credentials or sensitive connector settings leak in responses.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.db import get_engine, get_session_factory
from app.main import app
from app.models.findings import FindingAuditLog, FindingOccurrence, OperationalFinding
from app.models.source_data import FactEnergyMeterHourly, FactHourlyProduction
from app.models.upload_history import UploadHistory
from app.schemas.findings import OccurrenceProvenanceResponse
from app.services.finding_lifecycle_service import get_occurrence_provenance


@contextmanager
def capture_queries(engine):
    """Context manager to intercept and count all SQL statements executed on the engine."""
    statements = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


class BaseProvenanceTestCase(unittest.TestCase):
    """Base test fixture ensuring clean isolated sessions and automatic fixture cleanup."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        if cls.engine is None:
            raise RuntimeError("Database engine unavailable for provenance regression tests.")
        cls.session_factory = get_session_factory()
        cls.client = TestClient(app)

    def setUp(self):
        self.session = self.session_factory()
        self.test_prefix = f"TEST-PROV-{uuid4().hex[:8]}"

    def tearDown(self):
        # Guarantee 100% cleanup of any test-created records
        try:
            self.session.rollback()
            # Clean any committed test records matching prefix
            self.session.query(FindingOccurrence).filter(
                FindingOccurrence.occurrence_id.like("OCC-TEST%")
            ).delete(synchronize_session=False)
            self.session.query(FindingOccurrence).filter(
                FindingOccurrence.finding_id.like("TEST-PROV%")
            ).delete(synchronize_session=False)
            self.session.query(FindingAuditLog).filter(
                FindingAuditLog.finding_id.like("TEST-PROV%")
            ).delete(synchronize_session=False)
            self.session.query(OperationalFinding).filter(
                OperationalFinding.finding_id.like("TEST-PROV%")
            ).delete(synchronize_session=False)
            self.session.query(UploadHistory).filter(
                UploadHistory.upload_id.like("TEST-UPL-%")
            ).delete(synchronize_session=False)
            self.session.commit()
        except Exception:
            self.session.rollback()
        finally:
            self.session.close()


class TestLineageStatesRegression(BaseProvenanceTestCase):
    """Step 2: Verification of all 5 explicit lineage states."""

    def test_lineage_state_available(self):
        """AVAILABLE: Source record exists in fact table AND upload history exists in upload_history."""
        test_upload_id = f"TEST-UPL-{uuid4().hex[:6]}"
        test_finding_id = f"{self.test_prefix}-AVAIL"
        test_occ_id = f"OCC-{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # 1. Insert test upload record
        upload_rec = UploadHistory(
            upload_id=test_upload_id,
            uploaded_at=now,
            report_type="ENERGY",
            filename="meter_report_20261101.csv",
            file_format="CSV",
            sheet_name=None,
            reporting_date=now.date(),
            file_size_bytes=2048,
            total_rows=24,
            valid_rows=24,
            rejected_rows=0,
            duplicate_rows=0,
            status="COMPLETED",
            mode="INCREMENTAL",
        )
        self.session.add(upload_rec)

        # 2. Insert test finding
        finding = OperationalFinding(
            finding_id=test_finding_id,
            finding_key=f"TEST-KEY-{uuid4().hex[:6]}",
            anomaly_type="ENERGY_STATISTICAL_SPIKE",
            plant_id="IN-TN-01",
            meter_id="MTR-COMPRESSOR",
            status="NEW",
            severity="HIGH",
            first_detected_at=now,
            last_detected_at=now,
            occurrence_count=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(finding)

        # 3. Insert test occurrence linking to existing physical record EN-000022044 and test upload
        occ = FindingOccurrence(
            occurrence_id=test_occ_id,
            finding_id=test_finding_id,
            occurrence_ts=now,
            actual_value=Decimal("53.58"),
            baseline_value=Decimal("40.00"),
            deviation_score=1.8,
            severity="HIGH",
            source_table="fact_energy_meter_hourly",
            source_record_id="EN-000022044",  # physical baseline record that exists
            upload_id=test_upload_id,
            detector_version="rolling_baseline:1.0.0",
            context_flags_json=json.dumps({
                "source_table": "fact_energy_meter_hourly",
                "source_record_id": "EN-000022044",
                "upload_id": test_upload_id,
            }),
            recorded_at=now,
        )
        self.session.add(occ)
        self.session.commit()

        # Execute provenance drill-down
        result = get_occurrence_provenance(self.session, test_finding_id, test_occ_id)

        self.assertEqual(result["overall_lineage_state"], "AVAILABLE")
        self.assertFalse(result["is_multi_source"])
        self.assertEqual(len(result["source_records"]), 1)

        rec = result["source_records"][0]
        self.assertEqual(rec["record_status"], "FOUND")
        self.assertEqual(rec["lineage_state"], "AVAILABLE")
        self.assertEqual(rec["upload_status"], "AVAILABLE")
        self.assertIsNotNone(rec["upload"])
        self.assertEqual(rec["upload"]["upload_id"], test_upload_id)
        self.assertEqual(rec["upload"]["filename"], "meter_report_20261101.csv")
        self.assertEqual(rec["upload"]["valid_rows"], 24)
        self.assertIn("verified in the database", result["lineage_explanation"])

    def test_lineage_state_multi_source(self):
        """MULTI_SOURCE: Composite finding cross-correlating production and energy records."""
        # Query existing multi-source finding in database
        result = get_occurrence_provenance(self.session, "FND-IN-TN-01-F49D91078C")

        self.assertEqual(result["overall_lineage_state"], "MULTI_SOURCE")
        self.assertTrue(result["is_multi_source"])
        self.assertEqual(len(result["source_records"]), 2)
        self.assertIn("cross-correlating 2 discrete source telemetry records", result["lineage_explanation"])

        # Check semantic roles preservation
        roles = {s["role"]: s for s in result["source_records"]}
        self.assertIn("PRODUCTION_ZERO_OUTPUT_EVENT", roles)
        self.assertIn("PROCESS_ENERGY_MEASUREMENT", roles)

        prod_stream = roles["PRODUCTION_ZERO_OUTPUT_EVENT"]
        self.assertEqual(prod_stream["source_table"], "fact_hourly_production")
        self.assertEqual(prod_stream["record_status"], "FOUND")
        self.assertEqual(prod_stream["entity_type"], "LINE")
        self.assertIsNotNone(prod_stream["raw_data"])
        self.assertIn("target_qty", prod_stream["raw_data"])
        self.assertIn("actual_qty", prod_stream["raw_data"])

        energy_stream = roles["PROCESS_ENERGY_MEASUREMENT"]
        self.assertEqual(energy_stream["source_table"], "fact_energy_meter_hourly")
        self.assertEqual(energy_stream["record_status"], "FOUND")
        self.assertEqual(energy_stream["entity_type"], "METER")
        self.assertIsNotNone(energy_stream["raw_data"])
        self.assertIn("consumption_kwh", energy_stream["raw_data"])
        self.assertIn("demand_kw", energy_stream["raw_data"])

    def test_lineage_state_legacy_unlinked(self):
        """LEGACY_UNLINKED: Historical finding with no recorded occurrences or source telemetry links."""
        # Query existing finding without occurrences
        result = get_occurrence_provenance(self.session, "FND-ATOMIC-1794727303")

        self.assertEqual(result["overall_lineage_state"], "LEGACY_UNLINKED")
        self.assertFalse(result["is_multi_source"])
        self.assertEqual(len(result["source_records"]), 0)
        self.assertIn("no recorded occurrences or source telemetry links", result["lineage_explanation"])

    def test_lineage_state_source_missing(self):
        """SOURCE_MISSING: Stored source record identifier exists, but physical row is absent from table."""
        test_finding_id = f"{self.test_prefix}-MISSING"
        test_occ_id = f"OCC-{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        finding = OperationalFinding(
            finding_id=test_finding_id,
            finding_key=f"TEST-KEY-{uuid4().hex[:6]}",
            anomaly_type="ENERGY_STATISTICAL_SPIKE",
            plant_id="IN-TN-01",
            meter_id="MTR-SMT",
            status="NEW",
            severity="MEDIUM",
            first_detected_at=now,
            last_detected_at=now,
            occurrence_count=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(finding)

        occ = FindingOccurrence(
            occurrence_id=test_occ_id,
            finding_id=test_finding_id,
            occurrence_ts=now,
            actual_value=Decimal("150.00"),
            baseline_value=Decimal("100.00"),
            deviation_score=2.0,
            severity="MEDIUM",
            source_table="fact_energy_meter_hourly",
            source_record_id="EN-DOES-NOT-EXIST-999999",  # deliberate missing record
            upload_id=None,
            detector_version="1.0.0",
            recorded_at=now,
        )
        self.session.add(occ)
        self.session.commit()

        result = get_occurrence_provenance(self.session, test_finding_id, test_occ_id)

        self.assertEqual(result["overall_lineage_state"], "SOURCE_MISSING")
        self.assertFalse(result["is_multi_source"])
        self.assertEqual(len(result["source_records"]), 1)

        rec = result["source_records"][0]
        self.assertEqual(rec["record_status"], "MISSING")
        self.assertEqual(rec["lineage_state"], "SOURCE_MISSING")
        self.assertIsNone(rec["raw_data"])
        self.assertIn("was not found in database table 'fact_energy_meter_hourly'", rec["lineage_note"])

    def test_lineage_state_upload_unavailable(self):
        """UPLOAD_UNAVAILABLE: Physical source record exists, but upload history metadata is unavailable."""
        # Query single-source finding with baseline record EN-000022044 (upload_id is NULL)
        result = get_occurrence_provenance(self.session, "FND-IN-TN-01-670442A4C1")

        self.assertEqual(result["overall_lineage_state"], "UPLOAD_UNAVAILABLE")
        self.assertEqual(len(result["source_records"]), 1)

        rec = result["source_records"][0]
        self.assertEqual(rec["record_status"], "FOUND")
        self.assertEqual(rec["upload_status"], "UNAVAILABLE_HISTORICAL")
        self.assertEqual(rec["lineage_state"], "UPLOAD_UNAVAILABLE")
        self.assertIsNone(rec["upload"])
        self.assertIn("batch upload metadata is unavailable", rec["lineage_note"])

    def test_source_status_and_upload_status_remain_distinct(self):
        """Source record status and upload status remain decoupled across states."""
        # Case A: Record FOUND, Upload UNAVAILABLE
        res_a = get_occurrence_provenance(self.session, "FND-IN-TN-01-670442A4C1")
        rec_a = res_a["source_records"][0]
        self.assertEqual(rec_a["record_status"], "FOUND")
        self.assertEqual(rec_a["upload_status"], "UNAVAILABLE_HISTORICAL")
        self.assertEqual(rec_a["lineage_state"], "UPLOAD_UNAVAILABLE")

        # Case B: Multi-source where records are FOUND and uploads are historical
        res_b = get_occurrence_provenance(self.session, "FND-IN-TN-01-F49D91078C")
        for stream in res_b["source_records"]:
            self.assertEqual(stream["record_status"], "FOUND")
            self.assertEqual(stream["upload_status"], "UNAVAILABLE_HISTORICAL")


class TestProvenanceIntegrityBoundaries(BaseProvenanceTestCase):
    """Step 3: Verification of integrity boundaries, security constraints, and error handling."""

    def test_finding_not_found_returns_404(self):
        """Non-existent finding ID raises KeyError and returns HTTP 404."""
        with self.assertRaises(KeyError) as ctx:
            get_occurrence_provenance(self.session, "FND-NON-EXISTENT-XYZ")
        self.assertIn("Finding 'FND-NON-EXISTENT-XYZ' not found.", str(ctx.exception))

        # API check
        resp = self.client.get("/api/findings/FND-NON-EXISTENT-XYZ/provenance")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"], "Finding 'FND-NON-EXISTENT-XYZ' not found.")

    def test_occurrence_not_found_returns_404(self):
        """Non-existent occurrence ID on valid finding raises ValueError and returns HTTP 404."""
        with self.assertRaises(ValueError) as ctx:
            get_occurrence_provenance(self.session, "FND-IN-TN-01-670442A4C1", "OCC-NON-EXISTENT")
        self.assertIn("Occurrence 'OCC-NON-EXISTENT' not found for finding 'FND-IN-TN-01-670442A4C1'.", str(ctx.exception))

        # API check
        resp = self.client.get("/api/findings/FND-IN-TN-01-670442A4C1/occurrences/OCC-NON-EXISTENT/provenance")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"], "Occurrence 'OCC-NON-EXISTENT' not found for finding 'FND-IN-TN-01-670442A4C1'.")

    def test_occurrence_belonging_to_different_finding_rejected_404(self):
        """Occurrence belonging to a different finding is strictly rejected with explicit mismatch detail."""
        # OCC-1A1278941335 belongs to FND-IN-TN-01-F49D91078C, NOT FND-IN-TN-01-670442A4C1
        with self.assertRaises(ValueError) as ctx:
            get_occurrence_provenance(self.session, "FND-IN-TN-01-670442A4C1", "OCC-1A1278941335")
        err = str(ctx.exception)
        self.assertIn("OCC-1A1278941335", err)
        self.assertIn("FND-IN-TN-01-F49D91078C", err)
        self.assertIn("FND-IN-TN-01-670442A4C1", err)

        # API check
        resp = self.client.get("/api/findings/FND-IN-TN-01-670442A4C1/occurrences/OCC-1A1278941335/provenance")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("belongs to finding 'FND-IN-TN-01-F49D91078C', not 'FND-IN-TN-01-670442A4C1'", resp.json()["detail"])

    def test_unsupported_source_table_rejected_without_query(self):
        """Unsupported source tables are rejected without executing arbitrary SQL queries."""
        test_finding_id = f"{self.test_prefix}-TABLE-GUARD"
        test_occ_id = f"OCC-{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        finding = OperationalFinding(
            finding_id=test_finding_id,
            finding_key=f"TEST-KEY-{uuid4().hex[:6]}",
            anomaly_type="LOW_POWER_FACTOR",
            plant_id="IN-TN-01",
            status="NEW",
            severity="LOW",
            first_detected_at=now,
            last_detected_at=now,
            occurrence_count=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(finding)

        # Occurrence injected with disallowed table name
        occ = FindingOccurrence(
            occurrence_id=test_occ_id,
            finding_id=test_finding_id,
            occurrence_ts=now,
            actual_value=Decimal("0.82"),
            baseline_value=Decimal("0.95"),
            deviation_score=1.2,
            severity="LOW",
            source_table="dim_product",  # disallowed table!
            source_record_id="SPH-A15-256",
            upload_id=None,
            detector_version="1.0.0",
            recorded_at=now,
        )
        self.session.add(occ)
        self.session.commit()

        # Monitor queries during execution to ensure no queries target dim_product
        with capture_queries(self.engine) as queries:
            result = get_occurrence_provenance(self.session, test_finding_id, test_occ_id)

        # Assert no query touched dim_product
        dim_queries = [q for q in queries if "dim_product" in q.lower()]
        self.assertEqual(len(dim_queries), 0, "Disallowed table should never be queried via SQL.")

        self.assertEqual(len(result["source_records"]), 1)
        rec = result["source_records"][0]
        self.assertEqual(rec["record_status"], "UNSUPPORTED_TABLE")
        self.assertEqual(rec["lineage_state"], "SOURCE_MISSING")
        self.assertIn("not in the allowlisted schema tables", rec["lineage_note"])

    def test_invalid_or_missing_source_identifiers(self):
        """Occurrence with empty or whitespace-only source record ID handles gracefully without crashing."""
        test_finding_id = f"{self.test_prefix}-EMPTY-ID"
        test_occ_id = f"OCC-{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        finding = OperationalFinding(
            finding_id=test_finding_id,
            finding_key=f"TEST-KEY-{uuid4().hex[:6]}",
            anomaly_type="LOW_POWER_FACTOR",
            plant_id="IN-TN-01",
            status="NEW",
            severity="LOW",
            first_detected_at=now,
            last_detected_at=now,
            occurrence_count=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(finding)

        occ = FindingOccurrence(
            occurrence_id=test_occ_id,
            finding_id=test_finding_id,
            occurrence_ts=now,
            actual_value=Decimal("0.85"),
            baseline_value=Decimal("0.95"),
            deviation_score=1.0,
            severity="LOW",
            source_table="fact_energy_meter_hourly",
            source_record_id="",  # empty string ID
            upload_id=None,
            detector_version="1.0.0",
            recorded_at=now,
        )
        self.session.add(occ)
        self.session.commit()

        result = get_occurrence_provenance(self.session, test_finding_id, test_occ_id)
        self.assertEqual(result["overall_lineage_state"], "LEGACY_UNLINKED")
        self.assertEqual(len(result["source_records"]), 0)

    def test_multi_source_preserves_independent_roles_and_states(self):
        """Composite multi-source occurrence preserves individual stream roles, tables, and states."""
        test_finding_id = f"{self.test_prefix}-MULTI-ROLES"
        test_occ_id = f"OCC-{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        finding = OperationalFinding(
            finding_id=test_finding_id,
            finding_key=f"TEST-KEY-{uuid4().hex[:6]}",
            anomaly_type="ZERO_PRODUCTION_STANDBY_ENERGY",
            plant_id="IN-TN-01",
            status="NEW",
            severity="HIGH",
            first_detected_at=now,
            last_detected_at=now,
            occurrence_count=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(finding)

        # Multi-source where stream 1 is FOUND and stream 2 is MISSING
        occ = FindingOccurrence(
            occurrence_id=test_occ_id,
            finding_id=test_finding_id,
            occurrence_ts=now,
            actual_value=Decimal("80.00"),
            baseline_value=Decimal("0.00"),
            deviation_score=2.5,
            severity="HIGH",
            detector_version="zero_production_standby:1.0.0",
            context_flags_json=json.dumps({
                "source_records": [
                    {
                        "source_table": "fact_hourly_production",
                        "source_record_id": "PRD-00008199",  # exists
                        "role": "PRODUCTION_ZERO_OUTPUT_EVENT",
                        "upload_id": None,
                    },
                    {
                        "source_table": "fact_energy_meter_hourly",
                        "source_record_id": "EN-GHOST-MISSING",  # does not exist
                        "role": "PROCESS_ENERGY_MEASUREMENT",
                        "upload_id": None,
                    },
                ]
            }),
            recorded_at=now,
        )
        self.session.add(occ)
        self.session.commit()

        result = get_occurrence_provenance(self.session, test_finding_id, test_occ_id)
        self.assertEqual(result["overall_lineage_state"], "MULTI_SOURCE")
        self.assertEqual(len(result["source_records"]), 2)

        streams = {s["role"]: s for s in result["source_records"]}
        self.assertEqual(streams["PRODUCTION_ZERO_OUTPUT_EVENT"]["record_status"], "FOUND")
        self.assertEqual(streams["PRODUCTION_ZERO_OUTPUT_EVENT"]["lineage_state"], "UPLOAD_UNAVAILABLE")

        self.assertEqual(streams["PROCESS_ENERGY_MEASUREMENT"]["record_status"], "MISSING")
        self.assertEqual(streams["PROCESS_ENERGY_MEASUREMENT"]["lineage_state"], "SOURCE_MISSING")

    def test_legacy_records_do_not_receive_fabricated_metadata(self):
        """Legacy records without source IDs receive no fabricated IDs, upload IDs, or timestamps."""
        result = get_occurrence_provenance(self.session, "FND-ATOMIC-1794727303")
        self.assertEqual(result["overall_lineage_state"], "LEGACY_UNLINKED")
        self.assertEqual(result["source_records"], [])
        self.assertEqual(result["occurrence_id"], "NONE")

    def test_provenance_retrieval_does_not_modify_database(self):
        """Provenance retrieval is strictly read-only and does not mutate any tables or records."""
        # Record pre-counts
        pre_findings = self.session.query(OperationalFinding).count()
        pre_occs = self.session.query(FindingOccurrence).count()
        pre_energy = self.session.query(FactEnergyMeterHourly).count()
        pre_prod = self.session.query(FactHourlyProduction).count()
        pre_upload = self.session.query(UploadHistory).count()

        # Execute multiple provenance requests
        get_occurrence_provenance(self.session, "FND-IN-TN-01-F49D91078C")
        get_occurrence_provenance(self.session, "FND-IN-TN-01-670442A4C1")
        get_occurrence_provenance(self.session, "FND-ATOMIC-1794727303")

        # Execute HTTP API calls
        self.client.get("/api/findings/FND-IN-TN-01-F49D91078C/provenance")
        self.client.get("/api/v1/findings/FND-IN-TN-01-670442A4C1/provenance")

        # Record post-counts
        post_findings = self.session.query(OperationalFinding).count()
        post_occs = self.session.query(FindingOccurrence).count()
        post_energy = self.session.query(FactEnergyMeterHourly).count()
        post_prod = self.session.query(FactHourlyProduction).count()
        post_upload = self.session.query(UploadHistory).count()

        self.assertEqual(pre_findings, post_findings)
        self.assertEqual(pre_occs, post_occs)
        self.assertEqual(pre_energy, post_energy)
        self.assertEqual(pre_prod, post_prod)
        self.assertEqual(pre_upload, post_upload)


class TestQueryCountAndPerformance(BaseProvenanceTestCase):
    """Step 3 & 4: Zero N+1 query and batch optimization verification."""

    def test_zero_n_plus_one_queries_multi_source(self):
        """Retrieving provenance for multi-source occurrence executes <= 4 total queries with zero N+1 lookups."""
        with capture_queries(self.engine) as queries:
            result = get_occurrence_provenance(self.session, "FND-IN-TN-01-F49D91078C")

        self.assertEqual(result["overall_lineage_state"], "MULTI_SOURCE")
        self.assertEqual(len(result["source_records"]), 2)

        # Queries executed should be:
        # 1. Finding lookup with occurrences
        # 2. FactEnergyMeterHourly IN (...) query
        # 3. FactHourlyProduction IN (...) query
        # 4. UploadHistory IN (...) query (if uploads present)
        # Total queries must not exceed 4 regardless of the number of contributing records
        self.assertLessEqual(len(queries), 4, f"Executed {len(queries)} queries, expected <= 4.")

        # Ensure no individual scalar lookup (WHERE meter_reading_id = '...' or WHERE event_id = '...') was run
        for q in queries:
            sql_lower = q.lower()
            if "fact_energy_meter_hourly" in sql_lower:
                self.assertIn("in (", sql_lower, "Energy lookup must use set batching (IN operator).")
            if "fact_hourly_production" in sql_lower:
                self.assertIn("in (", sql_lower, "Production lookup must use set batching (IN operator).")


class TestProvenanceApiContract(BaseProvenanceTestCase):
    """Step 4: API prefixes, schema consistency, numeric serialization, and credential protection."""

    def test_api_findings_prefix(self):
        """Endpoint works under /api/findings route prefix."""
        resp = self.client.get("/api/findings/FND-IN-TN-01-F49D91078C/provenance")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["finding_id"], "FND-IN-TN-01-F49D91078C")
        self.assertEqual(body["overall_lineage_state"], "MULTI_SOURCE")

    def test_api_v1_findings_prefix(self):
        """Endpoint works under /api/v1/findings route prefix with identical response content."""
        resp_v1 = self.client.get("/api/v1/findings/FND-IN-TN-01-F49D91078C/provenance")
        self.assertEqual(resp_v1.status_code, 200)

        resp_v0 = self.client.get("/api/findings/FND-IN-TN-01-F49D91078C/provenance")
        self.assertEqual(resp_v0.status_code, 200)

        body_v1 = resp_v1.json()
        body_v0 = resp_v0.json()

        # Both endpoints should return identical content (excluding retrieved_at timestamp)
        del body_v1["retrieved_at"]
        del body_v0["retrieved_at"]
        self.assertEqual(body_v1, body_v0)

    def test_response_schema_validation(self):
        """Validate response payload matches Pydantic OccurrenceProvenanceResponse schema."""
        resp = self.client.get("/api/findings/FND-IN-TN-01-F49D91078C/provenance")
        self.assertEqual(resp.status_code, 200)

        # Validate with Pydantic model
        validated = OccurrenceProvenanceResponse.model_validate(resp.json())
        self.assertEqual(validated.finding_id, "FND-IN-TN-01-F49D91078C")
        self.assertEqual(validated.overall_lineage_state, "MULTI_SOURCE")
        self.assertEqual(len(validated.source_records), 2)

    def test_raw_record_serialization_handles_nulls_and_numerics(self):
        """Raw record attributes serialize Decimal and Date fields to standard JSON numbers and strings."""
        resp = self.client.get("/api/findings/FND-IN-TN-01-F49D91078C/provenance")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        energy_record = next(r for r in body["source_records"] if r["source_table"] == "fact_energy_meter_hourly")
        raw = energy_record["raw_data"]

        # Ensure consumption_kwh and cost_inr are floats, not strings or Decimal objects
        self.assertIsInstance(raw["consumption_kwh"], float)
        self.assertIsInstance(raw["cost_inr"], float)
        self.assertIsInstance(raw["demand_kw"], float)
        self.assertIsInstance(raw["power_factor"], float)

        # Nullable fields correctly serialize as null / None
        self.assertIsNone(raw["upload_id"])

    def test_no_sensitive_credentials_in_response(self):
        """API responses contain zero connection strings, passwords, or internal secret credentials."""
        resp = self.client.get("/api/findings/FND-IN-TN-01-F49D91078C/provenance")
        self.assertEqual(resp.status_code, 200)
        raw_body_text = resp.text.lower()

        # Assert no sensitive keywords or connection string fragments leaked
        sensitive_patterns = [
            "password",
            "postgresql://",
            "postgres://",
            "ep-sample",
            "neon.tech",
            "secret",
            "developer_token",
            "auth_token",
        ]
        for pattern in sensitive_patterns:
            self.assertNotIn(pattern, raw_body_text, f"Potential credential leak detected: '{pattern}' found in response.")


if __name__ == "__main__":
    unittest.main()
