"""
PostgreSQL 18.6 data integrity, concurrency, lifecycle, and audit persistence tests.

Targeting disposable PostgreSQL database on port 5433 (energy_disposable_db):
1. Concurrent recommendation generation and unique-index conflict recovery (uq_active_rec_finding_category).
2. Atomic audit log generation (audit records committed atomically; rolled back on transaction abort).
3. Audit history preserving dismissal reasons across reopening.
4. Action lifecycle restrictions under DISMISSED and IMPLEMENTED recommendations.
5. Foreign key deletion behavior (ON DELETE SET NULL on finding_id).
6. Application-level vs DB-level audit immutability distinction.
"""

import concurrent.futures
from datetime import datetime
from decimal import Decimal
import unittest

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_engine, get_session_factory
from app.models.findings import FindingOccurrence, OperationalFinding
from app.models.recommendations import (
    ActionAuditLog,
    CorrectiveAction,
    OperationalRecommendation,
    RecommendationAuditLog,
)
from app.schemas.recommendations import (
    CreateActionRequest,
    CreateRecommendationRequest,
)
from app.services.recommendation_service import (
    create_corrective_action,
    create_recommendation,
    generate_recommendations_from_finding,
    get_recommendation_audit_logs,
    update_recommendation_status,
)


class TestPostgresIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        if cls.engine is None:
            raise RuntimeError("Database engine not available.")
        cls.session_factory = get_session_factory()

    def setUp(self):
        self.session = self.session_factory()
        self._test_finding_ids = []

    def tearDown(self):
        try:
            self.session.rollback()
            if self._test_finding_ids:
                from sqlalchemy import text
                for f_id in self._test_finding_ids:
                    # Clean up dependent records in child-to-parent order
                    self.session.execute(text("""
                        DELETE FROM action_audit_log WHERE action_id IN (
                            SELECT action_id FROM corrective_actions WHERE recommendation_id IN (
                                SELECT recommendation_id FROM operational_recommendations WHERE finding_id = :fid
                            )
                        );
                    """), {"fid": f_id})
                    self.session.execute(text("""
                        DELETE FROM corrective_actions WHERE recommendation_id IN (
                            SELECT recommendation_id FROM operational_recommendations WHERE finding_id = :fid
                        );
                    """), {"fid": f_id})
                    self.session.execute(text("""
                        DELETE FROM recommendation_audit_log WHERE recommendation_id IN (
                            SELECT recommendation_id FROM operational_recommendations WHERE finding_id = :fid
                        );
                    """), {"fid": f_id})
                    self.session.execute(text("""
                        DELETE FROM operational_recommendations WHERE finding_id = :fid;
                    """), {"fid": f_id})
                    self.session.execute(text("""
                        DELETE FROM finding_occurrence_sources WHERE occurrence_id IN (
                            SELECT occurrence_id FROM finding_occurrences WHERE finding_id = :fid
                        );
                    """), {"fid": f_id})
                    self.session.execute(text("""
                        DELETE FROM finding_occurrences WHERE finding_id = :fid;
                    """), {"fid": f_id})
                    self.session.execute(text("""
                        DELETE FROM finding_audit_log WHERE finding_id = :fid;
                    """), {"fid": f_id})
                    self.session.execute(text("""
                        DELETE FROM operational_findings WHERE finding_id = :fid;
                    """), {"fid": f_id})
                self.session.commit()
        except Exception:
            self.session.rollback()
        finally:
            self.session.close()

    def _create_test_finding(self, finding_id: str, plant_id: str = "IN-TN-01") -> OperationalFinding:
        """Helper to create an isolated operational finding."""
        if hasattr(self, '_test_finding_ids'):
            self._test_finding_ids.append(finding_id)
        now = datetime.now()
        finding = OperationalFinding(
            finding_id=finding_id,
            finding_key=f"KEY-{finding_id}",
            plant_id=plant_id,
            meter_id="MTR-SMT",
            line_id=None,
            anomaly_type="LOW_POWER_FACTOR",
            status="NEW",
            severity="HIGH",
            occurrence_count=1,
            current_actual_value=Decimal("0.8500"),
            current_baseline_value=Decimal("0.9000"),
            current_deviation_score=0.1500,
            first_detected_at=now,
            last_detected_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(finding)
        self.session.commit()
        return finding

    # =========================================================================
    # 1. Concurrent Generation & Unique Index Conflict Recovery
    # =========================================================================

    def test_concurrent_recommendation_generation_conflict_recovery(self):
        """Verify concurrent recommendation generation for the same finding recovers gracefully via uq_active_rec_finding_category."""
        finding_id = f"FND-CONCUR-{int(datetime.now().timestamp())}"
        self._create_test_finding(finding_id)

        results = []
        errors = []

        def worker():
            s = self.session_factory()
            try:
                recs = generate_recommendations_from_finding(
                    s, finding_id, caller_attribution="test_concurrency_worker"
                )
                return recs[0].recommendation_id
            except Exception as e:
                return f"ERROR: {str(e)}"
            finally:
                s.close()

        # Execute 2 concurrent generation calls
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker)
            f2 = executor.submit(worker)
            r1 = f1.result()
            r2 = f2.result()

        # Both workers should successfully return a valid recommendation ID
        self.assertFalse(str(r1).startswith("ERROR"), f"Worker 1 failed: {r1}")
        self.assertFalse(str(r2).startswith("ERROR"), f"Worker 2 failed: {r2}")
        # Both must return the EXACT same recommendation ID (graceful conflict recovery)
        self.assertEqual(r1, r2)

        # Database must contain exactly 1 recommendation for this finding
        count = self.session.execute(
            select(OperationalRecommendation).where(
                OperationalRecommendation.finding_id == finding_id,
                OperationalRecommendation.status.in_(["OPEN", "IN_PROGRESS"]),
            )
        ).scalars().all()
        self.assertEqual(len(count), 1)

    # =========================================================================
    # 2. Atomic Audit Log Generation & Rollback
    # =========================================================================

    def test_atomic_audit_log_rollback(self):
        """Verify that rolling back an uncommitted transaction rolls back both entity and audit log atomically."""
        rec_id = f"REC-ATOMIC-{int(datetime.now().timestamp())}"
        finding_id = f"FND-ATOMIC-{int(datetime.now().timestamp())}"
        self._create_test_finding(finding_id)

        rec = OperationalRecommendation(
            recommendation_id=rec_id,
            finding_id=finding_id,
            plant_id="IN-TN-01",
            category="POWER_FACTOR_CORRECTION",
            status="OPEN",
            priority="HIGH",
            title="Atomic Test Recommendation",
            description="Testing atomic rollback",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        audit = RecommendationAuditLog(
            audit_id=f"AUD-{rec_id}",
            recommendation_id=rec_id,
            entity_id=rec_id,
            action="CREATED",
            from_status=None,
            to_status="OPEN",
            comment="Initial creation",
            performed_at=datetime.now(),
        )

        self.session.add(rec)
        self.session.add(audit)
        self.session.flush()

        # Both exist in uncommitted session
        uncommitted_rec = self.session.execute(
            select(OperationalRecommendation).where(
                OperationalRecommendation.recommendation_id == rec_id
            )
        ).scalar_one_or_none()
        uncommitted_audit = self.session.execute(
            select(RecommendationAuditLog).where(
                RecommendationAuditLog.audit_id == f"AUD-{rec_id}"
            )
        ).scalar_one_or_none()
        self.assertIsNotNone(uncommitted_rec)
        self.assertIsNotNone(uncommitted_audit)

        # Rollback
        self.session.rollback()

        # Both must be absent from DB
        check_rec = self.session.execute(
            select(OperationalRecommendation).where(
                OperationalRecommendation.recommendation_id == rec_id
            )
        ).scalar_one_or_none()
        check_audit = self.session.execute(
            select(RecommendationAuditLog).where(
                RecommendationAuditLog.audit_id == f"AUD-{rec_id}"
            )
        ).scalar_one_or_none()
        self.assertIsNone(check_rec)
        self.assertIsNone(check_audit)

    # =========================================================================
    # 3. Audit History Preserving Dismissal Reasons Across Reopening
    # =========================================================================

    def test_audit_history_preserves_dismissal_reasons_across_reopening(self):
        """Verify that dismissing and then reopening preserves the dismissal event and reason in the audit history."""
        finding_id = f"FND-DISM-{int(datetime.now().timestamp())}"
        self._create_test_finding(finding_id)

        # 1. Create recommendation
        rec_req = CreateRecommendationRequest(
            plant_id="IN-TN-01",
            finding_id=finding_id,
            category="POWER_FACTOR_CORRECTION",
            priority="HIGH",
            title="Capacitor Bank Inspection",
            description="Inspect bank capacitors",
        )
        rec = create_recommendation(self.session, rec_req, caller_attribution="lead_eng")
        rec_id = rec.recommendation_id

        # 2. Dismiss recommendation with specific operational reason
        dismissal_reason = "Capacitor bank decommissioned during substation upgrade"
        update_recommendation_status(
            self.session,
            recommendation_id=rec_id,
            new_status="DISMISSED",
            reason=dismissal_reason,
            caller_attribution="plant_manager",
        )

        # 3. Reopen recommendation
        reopening_reason = "Substation upgrade finished early, re-evaluating capacitor bank"
        update_recommendation_status(
            self.session,
            recommendation_id=rec_id,
            new_status="OPEN",
            reason=reopening_reason,
            caller_attribution="lead_eng",
        )

        # 4. Fetch audit logs
        logs = get_recommendation_audit_logs(self.session, rec_id)
        self.assertEqual(len(logs), 3)

        # Chronological verification
        dismiss_log = next(log for log in logs if log.to_status == "DISMISSED")
        reopen_log = next(log for log in logs if log.to_status == "OPEN" and log.from_status == "DISMISSED")
        created_log = next(log for log in logs if log.action == "CREATED")

        self.assertEqual(dismiss_log.comment, dismissal_reason)
        self.assertIn(reopening_reason, reopen_log.comment)
        self.assertIn(dismissal_reason, reopen_log.comment)
        self.assertEqual(reopen_log.from_status, "DISMISSED")
        self.assertEqual(reopen_log.to_status, "OPEN")

    # =========================================================================
    # 4. Action Lifecycle Restrictions Under Closed Recommendations
    # =========================================================================

    def test_action_lifecycle_restrictions_dismissed_and_implemented(self):
        """Verify that corrective actions cannot be created under DISMISSED or IMPLEMENTED recommendations."""
        finding_id = f"FND-ACTLIFECYCLE-{int(datetime.now().timestamp())}"
        self._create_test_finding(finding_id)

        rec = create_recommendation(
            self.session,
            CreateRecommendationRequest(
                plant_id="IN-TN-01",
                finding_id=finding_id,
                category="POWER_FACTOR_CORRECTION",
                priority="HIGH",
                title="Action Restriction Test",
                description="Testing lifecycle constraints",
            ),
        )
        rec_id = rec.recommendation_id

        # Dismiss recommendation
        update_recommendation_status(
            self.session, rec_id, "DISMISSED", reason="Testing action creation block"
        )

        # Attempt to create action under DISMISSED
        action_req = CreateActionRequest(
            title="Illegal Action Under Dismissed",
            description="Testing rejection under closed recommendation",
            priority="HIGH",
        )
        with self.assertRaises(ValueError) as ctx_dism:
            create_corrective_action(self.session, rec_id, action_req)
        self.assertIn("Cannot create corrective action under DISMISSED", str(ctx_dism.exception))

        # Reopen to OPEN, then implement
        update_recommendation_status(self.session, rec_id, "OPEN", reason="Reopen to test implemented")
        update_recommendation_status(self.session, rec_id, "IMPLEMENTED", reason="Completed works")

        # Attempt to create action under IMPLEMENTED
        with self.assertRaises(ValueError) as ctx_impl:
            create_corrective_action(self.session, rec_id, action_req)
        self.assertIn("Cannot create corrective action under IMPLEMENTED", str(ctx_impl.exception))

    # =========================================================================
    # 5. Foreign Key Deletion Behavior (ON DELETE SET NULL)
    # =========================================================================

    def test_foreign_key_deletion_preserves_recommendation_with_null_finding(self):
        """Verify deleting an operational finding nullifies recommendation finding_id without deleting recommendation."""
        finding_id = f"FND-FKDEL-{int(datetime.now().timestamp())}"
        finding = self._create_test_finding(finding_id)

        rec = create_recommendation(
            self.session,
            CreateRecommendationRequest(
                plant_id="IN-TN-01",
                finding_id=finding_id,
                category="POWER_FACTOR_CORRECTION",
                priority="HIGH",
                title="FK Deletion Test",
                description="Testing SET NULL on parent finding deletion",
            ),
        )
        rec_id = rec.recommendation_id

        # Directly delete the finding record
        self.session.execute(
            text("DELETE FROM operational_findings WHERE finding_id = :fid"),
            {"fid": finding_id},
        )
        self.session.commit()

        # The recommendation must still exist, with finding_id set to None
        refreshed_rec = self.session.execute(
            select(OperationalRecommendation).where(
                OperationalRecommendation.recommendation_id == rec_id
            )
        ).scalar_one_or_none()
        self.assertIsNotNone(refreshed_rec)
        self.assertIsNone(refreshed_rec.finding_id)

    # =========================================================================
    # 6. Application-Level vs DB-Level Audit Immutability
    # =========================================================================

    def test_audit_immutability_architectural_distinction(self):
        """Verify application append-only logic vs DB-level trigger status.
        
        The platform enforces append-only semantics via the application service layer:
        - recommendation_service exposes NO update or delete functions for audit entities.
        - Direct database connections by non-application superusers are not blocked by triggers.
        """
        # Service layer guarantees: only creation functions exist, no update/delete
        import app.services.recommendation_service as rec_svc

        self.assertTrue(hasattr(rec_svc, "get_recommendation_audit_logs"))
        self.assertTrue(hasattr(rec_svc, "get_action_audit_logs"))
        self.assertFalse(hasattr(rec_svc, "update_recommendation_audit_log"))
        self.assertFalse(hasattr(rec_svc, "delete_recommendation_audit_log"))
        self.assertFalse(hasattr(rec_svc, "update_action_audit_log"))
        self.assertFalse(hasattr(rec_svc, "delete_action_audit_log"))


if __name__ == "__main__":
    unittest.main()
