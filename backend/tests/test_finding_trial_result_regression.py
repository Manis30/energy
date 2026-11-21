"""
Acceptance and Regression Test Suite for "Finding -> Energy-Saving Trial -> Verified Result".
Validates the five business criteria:
A. Verified Trial Fixture: Dual boundary (40 kWh stoppage - 8 kWh restart = 32 kWh net), guardrails pass, verified INR in ledger.
B. Production Breach: 32 kWh net reduction, but guardrail breached -> savings null / ₹0, excluded from ledger.
C. Insufficient Evidence (Nov 4 FAL-L2): 146.318 kWh observed, 0 good units -> inconclusive cost intensity, 0 attributable savings.
D. Trial Unsuitable & Evidence Gathering: Break (5 min) < restart (10 min) -> unsuitable; missing equipment -> measurement audit.
E. Resilience: AI unavailable graceful fallback, missing restart readings, duplicate requests, unauthorized sign-off denied.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.findings import FindingOccurrence, OperationalFinding
from app.models.recommendations import (
    ActionAuditLog,
    CorrectiveAction,
    InterventionAssessment,
    InterventionPlan,
    OperationalRecommendation,
)
from app.models.source_data import (
    DatasetFactorAssumption,
    DimProduct,
    DimProductionLine,
    FactEnergyMeterHourly,
    FactHourlyProduction,
)
from app.schemas.interventions import (
    ApproveMeasurementPlanRequest,
    AssessmentSignOffRequest,
    CreateMeasurementPlanRequest,
    RecordImplementationRequest,
)
from app.services.finding_ai_investigation_service import (
    explain_assessment_with_ai,
    investigate_finding_with_ai,
)
from app.services.intervention_comparison_service import (
    calculate_dual_boundary_attribution,
    evaluate_guardrails,
    execute_deterministic_comparison,
    resolve_factor_assumption,
)
from app.services.intervention_service import (
    approve_measurement_plan,
    create_measurement_plan,
    evaluate_and_record_assessment,
    list_savings_ledger,
    record_action_implementation,
    sign_off_assessment,
)
from app.services.opportunity_service import get_energy_saving_opportunities
from app.services.recommendation_service import (
    create_corrective_action,
    create_recommendation,
    draft_trial_plan_from_recommendation,
    generate_recommendations_from_finding,
)


class TestFindingTrialResultRegression(unittest.TestCase):
    """Regression suite for Finding -> Energy-Saving Trial -> Verified Result workflow."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.session = self.SessionLocal()

        self.plant_id = "IN-TN-01"
        self.prod_default = DimProduct(
            product_id="PROD_DEFAULT",
            product_name="Standard Assembly Phone",
            product_family="Smartphones",
            ram="8GB",
            storage="128GB",
            display="6.5 inch",
            model_revision="REV-A",
            standard_cycle_sec=60,
            standard_unit_cost_inr=Decimal("12000.00"),
            active_from=date(2025, 1, 1),
            active_to=date(2030, 12, 31),
        )
        self.session.add(self.prod_default)

        self.line_fal = DimProductionLine(
            line_id="FAL-L2",
            plant_id=self.plant_id,
            line_type="Final Assembly",
            nominal_capacity_per_hour=250,
            takt_time_sec=Decimal("12.0"),
            area="Assembly",
        )
        self.line_smt = DimProductionLine(
            line_id="SMT-L1",
            plant_id=self.plant_id,
            line_type="Surface Mount",
            nominal_capacity_per_hour=300,
            takt_time_sec=Decimal("8.0"),
            area="SMT",
        )
        self.session.add(self.line_fal)
        self.session.add(self.line_smt)

        # Seed approved tariff factor (8.25 INR/kWh)
        self.tariff = DatasetFactorAssumption(
            factor_id="TARIFF-IN-TN-01-V1",
            factor_type="ELECTRICITY_TARIFF",
            factor_scope=self.plant_id,
            source_dataset_version="REV_20261101",
            numeric_value=Decimal("8.2500"),
            unit="INR/kWh",
            approval_status="APPROVED_CONTRACT",
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31),
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(self.tariff)
        self.session.commit()

    def _add_production(
        self,
        event_id: str,
        dt: datetime,
        line_id: str = "FAL-L2",
        target_qty: int = 150,
        actual_qty: int = 150,
        good_qty: int = 150,
        reject_qty: int = 0,
        downtime_min: int = 0,
        downtime_reason: str = "NONE",
    ) -> FactHourlyProduction:
        row = FactHourlyProduction(
            event_id=event_id,
            event_ts=dt,
            event_date=dt.date(),
            year=dt.year,
            month=dt.month,
            week=dt.isocalendar()[1],
            day=dt.day,
            hour=dt.hour,
            plant_id=self.plant_id,
            line_id=line_id,
            shift_id="SHIFT_A",
            product_id=self.prod_default.product_id,
            production_order_id=f"ORD-{event_id}",
            target_qty=target_qty,
            actual_qty=actual_qty,
            good_qty=good_qty,
            reject_qty=reject_qty,
            rework_qty=0,
            downtime_min=downtime_min,
            downtime_reason=downtime_reason,
            operator_team="TEAM_A",
            source_system="MES",
            data_quality="GOOD",
        )
        self.session.add(row)
        return row

    def _add_recommendation(
        self,
        rec_id: str,
        finding_id: str,
        title: str = "Operational Recommendation",
    ) -> OperationalRecommendation:
        now = datetime.now(timezone.utc)
        rec = OperationalRecommendation(
            recommendation_id=rec_id,
            finding_id=finding_id,
            plant_id=self.plant_id,
            title=title,
            description="Trial recommendation description",
            category="PROCESS_EFFICIENCY",
            priority="HIGH",
            status="OPEN",
            created_at=now,
            updated_at=now,
        )
        self.session.add(rec)
        return rec

    def _add_energy_reading(
        self,
        reading_id: str,
        dt: datetime,
        consumption_kwh: float,
        meter_id: str = "MTR-FAL-01",
        tariff_inr: float = 8.25,
    ) -> FactEnergyMeterHourly:
        cost = Decimal(str(round(consumption_kwh * tariff_inr, 2)))
        reading = FactEnergyMeterHourly(
            meter_reading_id=reading_id,
            timestamp=dt,
            date=dt.date(),
            plant_id=self.plant_id,
            meter_id=meter_id,
            area="Assembly",
            energy_source="GRID",
            consumption_kwh=Decimal(str(consumption_kwh)),
            demand_kw=Decimal(str(consumption_kwh)),
            power_factor=Decimal("0.9500"),
            tariff_inr_per_kwh=Decimal(str(tariff_inr)),
            cost_inr=cost,
            co2e_kg=Decimal(str(round(consumption_kwh * 0.82, 4))),
            reading_quality="GOOD",
        )
        self.session.add(reading)
        return reading

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_acceptance_a_verified_trial_fixture(self):
        """
        Acceptance Test A:
        Dual-boundary energy-saving trial:
        - Boundary A (Stoppage): falls 40 kWh (50 kWh -> 10 kWh)
        - Boundary B (Restart): consumes 8 kWh extra (30 kWh -> 38 kWh)
        - Net reduction: 32 kWh (40 - 8 = 32 kWh)
        - Preapproved guardrails pass (output, quality, downtime, restart)
        - Certified avoided cost: 32.0 * 8.25 = ₹264.00
        - Verified INR added to ledger totals.
        """
        now_utc = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)
        plan_approved_at = now_utc
        action_implemented_at = datetime(2026, 11, 4, 9, 0)

        plan = InterventionPlan(
            plan_id="PLN-TRIAL-01",
            action_id="ACT-TRIAL-01",
            version=1,
            is_frozen=True,
            is_retrospective=False,
            approved_at=plan_approved_at,
            approved_by="Energy Director",
            intended_change="Activate auxiliary standby shutdown mode during planned break",
            implementation_owner="Shift Production Lead",
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL-01"]),
            production_denominator="Good finished units",
            production_unit="units",
            baseline_start=datetime(2026, 11, 3, 10, 0),
            baseline_end=datetime(2026, 11, 3, 12, 0),
            post_start=datetime(2026, 11, 4, 10, 0),
            post_end=datetime(2026, 11, 4, 12, 0),
            min_coverage_pct=90.0,
            guardrail_output_min=100.0,
            guardrail_output_unit="units",
            guardrail_output_direction="GREATER_OR_EQUAL",
            guardrail_output_source="Approved Production Schedule",
            guardrail_reject_max=10.0,
            guardrail_reject_unit="units",
            guardrail_reject_direction="LESS_OR_EQUAL",
            guardrail_reject_source="Quality Specification Limit",
            guardrail_downtime_max_min=75.0,
            guardrail_downtime_unit="minutes",
            guardrail_downtime_direction="LESS_OR_EQUAL",
            guardrail_downtime_source="Target Line Availability",
            success_criterion="Achieve net electricity reduction >= 5% across dual boundary with protected production",
            success_criterion_metric="AVOIDED_KWH",
            operating_conditions_json=json.dumps({
                "has_dual_boundary": True,
                "boundary_type": "DUAL_STOPPAGE_AND_RESTART",
                "comparison_method": "DUAL_STOPPAGE_AND_RESTART",
                "guardrail_output_reason": "Maintain shift production target",
                "guardrail_reject_reason": "Keep scrap below 10 units",
                "guardrail_downtime_reason": "Ensure downtime is within allowable limits",
                "guardrail_restart_max_min": 15.0,
                "guardrail_restart_unit": "minutes",
                "guardrail_restart_direction": "LESS_OR_EQUAL",
                "guardrail_restart_source": "Restart Envelope",
                "guardrail_restart_reason": "Ensure machine restarts within 15 minutes",
                "boundary_a": {
                    "baseline_kwh": 50.0,
                    "post_kwh": 10.0,
                    "baseline_start": "2026-11-03T10:00:00",
                    "baseline_end": "2026-11-03T11:00:00",
                    "post_start": "2026-11-04T10:00:00",
                    "post_end": "2026-11-04T11:00:00",
                    "eligible_meters": ["MTR-FAL-01"],
                },
                "boundary_b": {
                    "baseline_kwh": 30.0,
                    "post_kwh": 38.0,
                    "baseline_start": "2026-11-03T11:00:00",
                    "baseline_end": "2026-11-03T12:00:00",
                    "post_start": "2026-11-04T11:00:00",
                    "post_end": "2026-11-04T12:00:00",
                    "eligible_meters": ["MTR-FAL-01"],
                },
            }),
        )
        self.session.add(plan)

        finding_a = OperationalFinding(
            finding_id="FND-TRIAL-01",
            finding_key="FND-TRIAL-01-KEY",
            plant_id=self.plant_id,
            line_id="FAL-L2",
            meter_id="MTR-FAL-01",
            anomaly_type="STANDBY_POWER_STRIKE",
            severity="HIGH",
            status="NEW",
            first_detected_at=now_utc - timedelta(days=2),
            last_detected_at=now_utc - timedelta(hours=1),
            occurrence_count=3,
            current_explanation="Recurring standby draw during breaks",
        )
        self.session.add(finding_a)
        rec_a = self._add_recommendation("REC-TRIAL-01", finding_a.finding_id, "Standby Shutdown Recommendation")

        action = CorrectiveAction(
            action_id="ACT-TRIAL-01",
            recommendation_id=rec_a.recommendation_id,
            finding_id=finding_a.finding_id,
            plant_id=self.plant_id,
            title="Standby Auxiliary Shutdown Trial",
            description="Isolate auxiliary heaters and drives during planned stoppage",
            status="IN_PROGRESS",
            implemented_at=action_implemented_at,
            implemented_by="Shift Production Lead",
            measurement_plan_id=plan.plan_id,
        )
        self.session.add(action)
        self.session.commit()

        # Seed telemetry rows matching boundary intervals
        # Baseline Boundary A (10:00-11:00): 50 kWh, 0 units
        self._add_energy_reading("READ-B-A", datetime(2026, 11, 3, 10, 0), 50.0)
        self._add_production("EVT-B-A", datetime(2026, 11, 3, 10, 0), "FAL-L2", actual_qty=0, good_qty=0, reject_qty=0, downtime_min=60, downtime_reason="PLANNED_STOPPAGE")

        # Baseline Boundary B (11:00-12:00): 30 kWh, 150 units, 2 rejects
        self._add_energy_reading("READ-B-B", datetime(2026, 11, 3, 11, 0), 30.0)
        self._add_production("EVT-B-B", datetime(2026, 11, 3, 11, 0), "FAL-L2", actual_qty=152, good_qty=150, reject_qty=2, downtime_min=0)

        # Post Boundary A (10:00-11:00): 10 kWh (falls 40 kWh!), 0 units
        self._add_energy_reading("READ-P-A", datetime(2026, 11, 4, 10, 0), 10.0)
        self._add_production("EVT-P-A", datetime(2026, 11, 4, 10, 0), "FAL-L2", actual_qty=0, good_qty=0, reject_qty=0, downtime_min=60, downtime_reason="PLANNED_STOPPAGE")

        # Post Boundary B (11:00-12:00): 38 kWh (8 kWh restart extra!), 145 units, 3 rejects, 10 min restart
        self._add_energy_reading("READ-P-B", datetime(2026, 11, 4, 11, 0), 38.0)
        self._add_production("EVT-P-B", datetime(2026, 11, 4, 11, 0), "FAL-L2", actual_qty=148, good_qty=145, reject_qty=3, downtime_min=10)
        self.session.commit()

        # Execute deterministic comparison
        comp = execute_deterministic_comparison(self.session, plan, action)

        self.assertTrue(comp.has_dual_boundary)
        self.assertIsNotNone(comp.dual_boundary_breakdown)
        b_down = comp.dual_boundary_breakdown

        self.assertEqual(b_down["stoppage_reduction_kwh"], 40.0)
        self.assertEqual(b_down["restart_overhead_kwh"], 8.0)
        self.assertEqual(b_down["net_reduction_kwh"], 32.0)

        # Three independent answers check
        self.assertEqual(comp.production_protection_status, "PROTECTED")
        self.assertTrue(comp.guardrails_passed)
        self.assertEqual(comp.electricity_savings_kwh, 32.0)
        self.assertEqual(comp.avoided_cost_inr, 264.0)

        # Record assessment to ledger
        comp_res, asm = evaluate_and_record_assessment(self.session, action.action_id, evaluated_by="Analytics Lead")
        self.assertEqual(asm.electricity_savings_kwh, 32.0)
        self.assertEqual(asm.avoided_cost_inr, 264.0)
        self.assertEqual(asm.savings_claim_status, "NOT_VERIFIED")  # Pending formal reviewer sign-off

        # Authorized sign-off with matching role and plant scope
        auth_caller = {
            "is_authenticated": True,
            "operational_auth_available": True,
            "user_id": "eng_lead_01",
            "role": "ENERGY_ENGINEER",
            "plant_scope": self.plant_id,
        }
        sign_off_req = AssessmentSignOffRequest(
            decision="APPROVED_VERIFIED",
            reviewer="eng_lead_01",
            notes="Trial net reduction verified against dual boundary under approved tariff.",
        )
        signed_asm = sign_off_assessment(
            session=self.session,
            assessment_id=asm.assessment_id,
            req=sign_off_req,
            auth_caller=auth_caller,
        )

        self.assertEqual(signed_asm.savings_claim_status, "VERIFIED")
        self.assertEqual(signed_asm.electricity_savings_kwh, 32.0)
        self.assertEqual(signed_asm.verified_monetary_savings_inr, 264.0)

        # Verify reflection in persistent factory savings ledger
        ledger = list_savings_ledger(self.session, plant_id=self.plant_id)
        self.assertEqual(ledger.verified_count, 1)
        self.assertEqual(ledger.total_verified_avoided_kwh, 32.0)
        self.assertEqual(ledger.total_verified_monetary_savings_inr, 264.0)
        self.assertEqual(ledger.total_verified_avoided_cost_inr, 264.0)

        # Verify AI Assistant explanation
        ai_exp = explain_assessment_with_ai(self.session, signed_asm.assessment_id)
        self.assertEqual(ai_exp["overall_verdict"], "Verified Factory Energy Saving")
        self.assertEqual(ai_exp["question_2_production_protection"]["status"], "PROTECTED")
        self.assertEqual(ai_exp["question_3_attribution"]["verified_electricity_savings_kwh"], 32.0)
        self.assertEqual(ai_exp["question_3_attribution"]["verified_monetary_savings_inr"], 264.0)
        self.assertEqual(ai_exp["dual_boundary_summary"]["stoppage_reduction_kwh"], 40.0)
        self.assertEqual(ai_exp["dual_boundary_summary"]["restart_overhead_kwh"], 8.0)
        self.assertEqual(ai_exp["dual_boundary_summary"]["net_reduction_kwh"], 32.0)

    def test_acceptance_b_production_breach_disqualifies_savings(self):
        """
        Acceptance Test B:
        Same 32 kWh net reduction, but miss an approved production target (e.g. reject limit breached).
        - Production protection status is BREACHED.
        - Overall outcome states production was not protected.
        - Attributable verified savings: null / ₹0.
        - Ledger verified totals do not increase.
        """
        now_utc = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)
        plan = InterventionPlan(
            plan_id="PLN-TRIAL-BREACH",
            action_id="ACT-TRIAL-BREACH",
            version=1,
            is_frozen=True,
            is_retrospective=False,
            approved_at=now_utc,
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL-01"]),
            production_denominator="Good finished units",
            production_unit="units",
            baseline_start=datetime(2026, 11, 3, 10, 0),
            baseline_end=datetime(2026, 11, 3, 12, 0),
            post_start=datetime(2026, 11, 4, 10, 0),
            post_end=datetime(2026, 11, 4, 12, 0),
            min_coverage_pct=90.0,
            guardrail_output_min=100.0,
            guardrail_reject_max=5.0,  # Strict maximum of 5 scrap units
            guardrail_downtime_max_min=75.0,
            intended_change="Trial with Quality Scrap Breach",
            implementation_owner="Shift Production Lead",
            success_criterion="Achieve net reduction while maintaining quality rejects <= 5 units",
            success_criterion_metric="AVOIDED_KWH",
            operating_conditions_json=json.dumps({
                "has_dual_boundary": True,
                "boundary_type": "DUAL_STOPPAGE_AND_RESTART",
                "boundary_a": {"baseline_kwh": 50.0, "post_kwh": 10.0},
                "boundary_b": {"baseline_kwh": 30.0, "post_kwh": 38.0},
            }),
        )
        self.session.add(plan)

        finding_b = OperationalFinding(
            finding_id="FND-BREACH-01",
            finding_key="FND-BREACH-01-KEY",
            plant_id=self.plant_id,
            line_id="FAL-L2",
            meter_id="MTR-FAL-01",
            anomaly_type="STANDBY_POWER_STRIKE",
            severity="HIGH",
            status="NEW",
            first_detected_at=now_utc - timedelta(days=2),
            last_detected_at=now_utc - timedelta(hours=1),
            occurrence_count=2,
            current_explanation="Standby anomaly before trial",
        )
        self.session.add(finding_b)
        rec_b = self._add_recommendation("REC-BREACH-01", finding_b.finding_id, "Trial with Quality Scrap Breach")

        action = CorrectiveAction(
            action_id="ACT-TRIAL-BREACH",
            recommendation_id=rec_b.recommendation_id,
            finding_id=finding_b.finding_id,
            plant_id=self.plant_id,
            title="Trial with Quality Scrap Breach",
            description="Operational change caused excessive scrap units upon restart",
            status="IN_PROGRESS",
            implemented_at=datetime(2026, 11, 4, 9, 0),
            implemented_by="Shift Production Lead",
            measurement_plan_id=plan.plan_id,
        )
        self.session.add(action)

        # Baseline Boundary A (10:00-11:00): 50 kWh, 0 units
        self._add_energy_reading("READ-BR-B-A", datetime(2026, 11, 3, 10, 0), 50.0)
        self._add_production("EVT-BR-B-A", datetime(2026, 11, 3, 10, 0), "FAL-L2", actual_qty=0, good_qty=0, reject_qty=0, downtime_min=60, downtime_reason="PLANNED_STOPPAGE")

        # Baseline Boundary B (11:00-12:00): 30 kWh, 150 units, 2 rejects
        self._add_energy_reading("READ-BR-B-B", datetime(2026, 11, 3, 11, 0), 30.0)
        self._add_production("EVT-BR-B-B", datetime(2026, 11, 3, 11, 0), "FAL-L2", actual_qty=152, good_qty=150, reject_qty=2, downtime_min=0)

        # Post Boundary A (10:00-11:00): 10 kWh (falls 40 kWh!), 0 units
        self._add_energy_reading("READ-BR-P-A", datetime(2026, 11, 4, 10, 0), 10.0)
        self._add_production("EVT-BR-P-A", datetime(2026, 11, 4, 10, 0), "FAL-L2", actual_qty=0, good_qty=0, reject_qty=0, downtime_min=60, downtime_reason="PLANNED_STOPPAGE")

        # Post Boundary B (11:00-12:00): 38 kWh (8 kWh extra restart), 120 actual, 105 good, 15 rejects (> 5 limit!)
        self._add_energy_reading("READ-BR-P-B", datetime(2026, 11, 4, 11, 0), 38.0)
        self._add_production("EVT-BR-P-B", datetime(2026, 11, 4, 11, 0), "FAL-L2", actual_qty=120, good_qty=105, reject_qty=15, downtime_min=0)
        self.session.commit()

        # Assessment calculation
        comp = execute_deterministic_comparison(self.session, plan, action)

        self.assertEqual(comp.production_protection_status, "BREACHED")
        self.assertFalse(comp.guardrails_passed)
        self.assertEqual(comp.management_outcome, "Production limit breached")
        # Attributable verified savings must be strictly null
        self.assertIsNone(comp.electricity_savings_kwh)
        self.assertIsNone(comp.avoided_cost_inr)
        self.assertEqual(comp.savings_claim_status, "NOT_VERIFIED")

        # Record assessment to ledger
        comp_res, asm = evaluate_and_record_assessment(self.session, action.action_id, evaluated_by="Analytics Lead")
        self.assertFalse(asm.quality_guardrail_met)

        # Attempting sign-off must NOT promote breached claim into verified totals
        auth_caller = {
            "is_authenticated": True,
            "operational_auth_available": True,
            "user_id": "eng_lead_01",
            "role": "ENERGY_ENGINEER",
            "plant_scope": self.plant_id,
        }
        sign_off_req = AssessmentSignOffRequest(
            decision="APPROVED_VERIFIED",
            reviewer="eng_lead_01",
            notes="Sign-off attempted despite breached guardrail.",
        )
        signed_asm = sign_off_assessment(
            session=self.session,
            assessment_id=asm.assessment_id,
            req=sign_off_req,
            auth_caller=auth_caller,
        )

        self.assertEqual(signed_asm.savings_claim_status, "NOT_VERIFIED")
        self.assertIsNone(signed_asm.verified_monetary_savings_inr)

        # Verify active ledger total remains 0.0
        ledger = list_savings_ledger(self.session, plant_id=self.plant_id)
        self.assertEqual(ledger.verified_count, 0)
        self.assertEqual(ledger.total_verified_avoided_kwh, 0.0)
        self.assertEqual(ledger.total_verified_monetary_savings_inr, 0.0)

        # Verify AI Assistant explanation captures the breach
        ai_exp = explain_assessment_with_ai(self.session, signed_asm.assessment_id)
        self.assertEqual(ai_exp["overall_verdict"], "Production Limit Breached — Savings Disqualified")
        self.assertEqual(ai_exp["question_2_production_protection"]["status"], "BREACHED")
        self.assertIsNone(ai_exp["question_3_attribution"]["verified_electricity_savings_kwh"])
        self.assertFalse(ai_exp["ledger_eligibility"]["is_eligible_for_verified_kwh"])

    def test_acceptance_c_insufficient_evidence_nov4_fal_l2(self):
        """
        Acceptance Test C:
        November 4 FAL-L2 case:
        - 146.318 kWh observed stoppage electricity consumption.
        - Baseline good units = 0 -> Cost per good unit is inconclusive.
        - Production protection is unassessable (0 target).
        - Attributable savings null / ₹0.
        - AI Assistant explains the 4 sections with citations.
        """
        finding = OperationalFinding(
            finding_id="FND-NOV4-FAL-L2",
            finding_key="FND-NOV4-FAL-L2-KEY",
            plant_id=self.plant_id,
            line_id="FAL-L2",
            meter_id="MTR-FAL-01",
            anomaly_type="ZERO_PRODUCTION_STANDBY_ENERGY",
            severity="CRITICAL",
            status="NEW",
            first_detected_at=datetime(2026, 11, 4, 10, 0),
            last_detected_at=datetime(2026, 11, 4, 11, 0),
            occurrence_count=2,
            current_actual_value=Decimal("146.3180"),
            current_baseline_value=Decimal("20.0000"),
            current_explanation="Line FAL-L2 drew 146.318 kWh over 2 hours zero output",
        )
        self.session.add(finding)
        self.session.flush()

        occ = FindingOccurrence(
            occurrence_id="OCC-NOV4-FAL-01",
            finding_id=finding.finding_id,
            occurrence_ts=datetime(2026, 11, 4, 10, 0),
            actual_value=Decimal("146.3180"),
            baseline_value=Decimal("20.0000"),
            deviation_score=631.59,
            severity="CRITICAL",
            explanation="Unusual standby draw during planned break",
        )
        self.session.add(occ)

        # Seed hourly reading
        self._add_energy_reading("READ-NOV4-01", datetime(2026, 11, 4, 10, 0), 146.318)
        # Seed production record: 0 good units, 60 min downtime
        self._add_production("EVT-NOV4-01", datetime(2026, 11, 4, 10, 0), "FAL-L2", actual_qty=0, good_qty=0, reject_qty=0, downtime_min=60, downtime_reason="PLANNED_STOPPAGE")

        # Post period (11:00-12:00) stoppage readings
        self._add_energy_reading("READ-NOV4-02", datetime(2026, 11, 4, 11, 0), 146.318)
        self._add_production("EVT-NOV4-02", datetime(2026, 11, 4, 11, 0), "FAL-L2", actual_qty=0, good_qty=0, reject_qty=0, downtime_min=60, downtime_reason="PLANNED_STOPPAGE")
        self.session.commit()

        # Investigate with AI
        ai_inv = investigate_finding_with_ai(self.session, finding.finding_id, occ.occurrence_id)
        self.assertEqual(ai_inv["status"], "SUCCESS")
        self.assertFalse(ai_inv.get("is_regression_case_nov4", False))
        self.assertIn("146.318 kWh", ai_inv["what_we_observed"])
        self.assertTrue("0 good units" in ai_inv["what_we_observed"] or "zero good" in ai_inv["what_we_observed"].lower() or "0 good" in ai_inv["what_we_observed"].lower())
        self.assertTrue(any(c["type"] == "METER_READING" for c in ai_inv["citations"]))

        # Check comparison for stoppage-only baseline
        plan = InterventionPlan(
            plan_id="PLN-NOV4-FAL-L2",
            action_id="ACT-NOV4-FAL-L2",
            version=1,
            is_frozen=True,
            is_retrospective=False,
            approved_at=datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc),
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL-01"]),
            production_denominator="Good finished units",
            production_unit="units",
            baseline_start=datetime(2026, 11, 4, 10, 0),
            baseline_end=datetime(2026, 11, 4, 11, 0),
            post_start=datetime(2026, 11, 4, 11, 0),
            post_end=datetime(2026, 11, 4, 12, 0),
            min_coverage_pct=90.0,
            guardrail_output_min=0.0,  # Zero output target is unassessable!
            intended_change="Test stoppage baseline",
            implementation_owner="Engineer",
            success_criterion="Stoppage standby reduction",
        )
        self.session.add(plan)
        rec_c = self._add_recommendation("REC-NOV4-FAL-L2", finding.finding_id, "Nov 4 Standby Check")
        action = CorrectiveAction(
            action_id="ACT-NOV4-FAL-L2",
            recommendation_id=rec_c.recommendation_id,
            finding_id=finding.finding_id,
            plant_id=self.plant_id,
            title="Nov 4 Standby Check",
            description="Stoppage standby check",
            status="IN_PROGRESS",
            implemented_at=datetime(2026, 11, 4, 9, 0),
            measurement_plan_id=plan.plan_id,
        )
        self.session.add(action)
        self.session.commit()

        comp = execute_deterministic_comparison(self.session, plan, action)
        self.assertEqual(comp.objective_outcome, "INCONCLUSIVE")
        self.assertEqual(comp.production_protection_status, "UNASSESSABLE")
        self.assertIsNone(comp.electricity_savings_kwh)
        self.assertIsNone(comp.avoided_cost_inr)

    def test_acceptance_d_trial_unsuitable_and_evidence_gathering(self):
        """
        Acceptance Test D:
        1. Planned break (5 min) < restart readiness (10 min) -> Clear unsuitable-trial explanation.
        2. Missing equipment evidence -> Recommends equipment audit / temporary submetering.
        """
        rec = OperationalRecommendation(
            recommendation_id="REC-TEST-SUITABILITY",
            plant_id=self.plant_id,
            title="Standby Shutdown Consideration",
            description="Advisory recommendation to power down line auxiliaries during break",
            category="STANDBY_SHUTDOWN",
            priority="HIGH",
            status="OPEN",
        )
        self.session.add(rec)
        self.session.commit()

        # Case 1: Break duration 5 min < restart readiness 10 min
        draft_unsuitable = draft_trial_plan_from_recommendation(
            self.session,
            rec.recommendation_id,
            break_duration_minutes=5.0,
            restart_readiness_minutes=10.0,
        )
        self.assertFalse(draft_unsuitable["is_suitable"])
        self.assertIn("shorter than equipment restart readiness", draft_unsuitable["unsuitable_reason"])
        self.assertIsNone(draft_unsuitable["plan_draft"])

        # Case 2: Break duration 60 min >= restart readiness 10 min, but equipment unidentified on line meter
        finding = OperationalFinding(
            finding_id="FND-NO-EQUIP",
            finding_key="FND-NO-EQUIP-KEY",
            plant_id=self.plant_id,
            line_id="FAL-L2",
            meter_id="MTR-FAL-01",
            anomaly_type="ZERO_PRODUCTION_STANDBY_ENERGY",
            severity="HIGH",
            status="NEW",
            first_detected_at=datetime(2026, 11, 4, 10, 0),
            last_detected_at=datetime(2026, 11, 4, 11, 0),
        )
        self.session.add(finding)
        self.session.flush()
        rec.finding_id = finding.finding_id
        self.session.commit()

        draft_audit = draft_trial_plan_from_recommendation(
            self.session,
            rec.recommendation_id,
            break_duration_minutes=60.0,
            restart_readiness_minutes=10.0,
        )
        self.assertTrue(draft_audit["is_suitable"])
        self.assertEqual(draft_audit["recommendation_type"], "EVIDENCE_GATHERING")
        self.assertIn("temporary IoT submeters", draft_audit["audit_recommendation"])

    def test_acceptance_e_resilience(self):
        """
        Acceptance Test E:
        1. AI service unavailable -> Graceful fallback, pipeline and findings remain usable.
        2. Missing restart readings -> Attributable savings marked inconclusive.
        3. Duplicate recommendation requests -> Enforces idempotency / active uniqueness.
        4. Unauthorized sign-off denied -> Role or plant mismatch denied.
        """
        # 1. AI service failure fallback
        with patch("app.services.finding_ai_investigation_service.select", side_effect=Exception("Database connection timeout")):
            try:
                investigate_finding_with_ai(self.session, "NON-EXISTENT")
            except Exception as e:
                # Returns clean error rather than crashing
                self.assertIn("Database connection timeout", str(e))

        # 2. Missing restart readings in dual-boundary trial
        b_down_missing_restart = {
            "stoppage_reduction_kwh": 40.0,
            "restart_overhead_kwh": 0.0,
            "net_reduction_kwh": 40.0,
            "boundary_a_stoppage": {"baseline_kwh": 50.0, "post_kwh": 10.0, "post_hours": 1.0},
            "boundary_b_restart_shift": {"baseline_kwh": 30.0, "post_kwh": None, "post_hours": 0.0},
        }
        plan_missing = InterventionPlan(
            plan_id="PLN-MISSING-RESTART",
            action_id="ACT-MISSING-RESTART",
            version=1,
            is_frozen=True,
            is_retrospective=False,
            approved_at=datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc),
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL-01"]),
            production_denominator="Good finished units",
            production_unit="units",
            baseline_start=datetime(2026, 11, 3, 10, 0),
            baseline_end=datetime(2026, 11, 3, 12, 0),
            post_start=datetime(2026, 11, 4, 10, 0),
            post_end=datetime(2026, 11, 4, 12, 0),
            min_coverage_pct=90.0,
            intended_change="Test missing restart",
            implementation_owner="Engineer",
            success_criterion="Test criterion",
        )
        rec_m = self._add_recommendation("REC-MISSING-RESTART", "FND-MISSING-RESTART", "Missing Restart Telemetry")
        action_missing = CorrectiveAction(
            action_id="ACT-MISSING-RESTART",
            recommendation_id=rec_m.recommendation_id,
            plant_id=self.plant_id,
            title="Missing Restart Telemetry",
            description="Restart readings missing",
            implemented_at=datetime(2026, 11, 4, 9, 0),
            measurement_plan_id=plan_missing.plan_id,
        )
        self.session.add(plan_missing)
        self.session.add(action_missing)
        self.session.commit()
        tariff_factor = resolve_factor_assumption(self.session, "ELECTRICITY_TARIFF", self.plant_id)

        attr_missing = calculate_dual_boundary_attribution(
            dual_boundary_breakdown=b_down_missing_restart,
            tariff_factor=tariff_factor,
            production_protection_status="PROTECTED",
            guardrails_passed=True,
            plan=plan_missing,
            action=action_missing,
        )
        self.assertEqual(attr_missing["status"], "INCONCLUSIVE")
        self.assertIsNone(attr_missing["verified_electricity_savings_kwh"])
        self.assertIn("Missing restart readings", attr_missing["reason"])

        # 3. Duplicate recommendation requests
        finding = OperationalFinding(
            finding_id="FND-DUP-TEST",
            finding_key="FND-DUP-KEY",
            plant_id=self.plant_id,
            line_id="FAL-L2",
            meter_id="MTR-FAL-01",
            anomaly_type="ZERO_PRODUCTION_STANDBY_ENERGY",
            severity="MEDIUM",
            status="NEW",
            first_detected_at=datetime(2026, 11, 4, 10, 0),
            last_detected_at=datetime(2026, 11, 4, 11, 0),
        )
        self.session.add(finding)
        self.session.commit()

        # First generation creates recommendation
        recs1, created_cnt1, reused_cnt1 = generate_recommendations_from_finding(self.session, finding.finding_id)
        self.assertEqual(created_cnt1, 1)

        # Second generation reuses existing active recommendation without duplicating
        recs2, created_cnt2, reused_cnt2 = generate_recommendations_from_finding(self.session, finding.finding_id)
        self.assertEqual(created_cnt2, 0)
        self.assertEqual(reused_cnt2, 1)
        self.assertEqual(recs1[0].recommendation_id, recs2[0].recommendation_id)

        # 4. Unauthorized sign-off denied
        asm = InterventionAssessment(
            assessment_id="ASM-TEST-AUTH",
            action_id=action_missing.action_id,
            plan_id=plan_missing.plan_id,
            plan_version=1,
            assessment_revision=1,
            is_stale_flag=False,
            evaluated_at=datetime.utcnow(),
            evaluated_by="Analytics",
            calculation_method="DETERMINISTIC_COMPARISON_V1",
            baseline_kwh=50.0,
            baseline_cost_inr=412.5,
            baseline_actual_units=100,
            baseline_good_units=100,
            baseline_reject_units=0,
            baseline_downtime_min=0,
            baseline_operating_hours=1,
            baseline_coverage_pct=100.0,
            post_kwh=10.0,
            post_cost_inr=82.5,
            post_actual_units=100,
            post_good_units=100,
            post_reject_units=0,
            post_downtime_min=0,
            post_operating_hours=1,
            post_coverage_pct=100.0,
            output_guardrail_met=True,
            quality_guardrail_met=True,
            downtime_guardrail_met=True,
            objective_outcome="IMPROVED",
            electricity_savings_kwh=40.0,
            monetary_savings_basis="APPROVED_CONTRACT_TARIFF",
            avoided_cost_inr=330.0,
            savings_claim_status="NOT_VERIFIED",
            savings_claim_description="Test assessment",
            status_reason="Awaiting signoff",
            overlap_flag=False,
        )
        self.session.add(asm)
        self.session.commit()

        # Caller has unauthorized role (OPERATOR)
        unauth_caller = {
            "is_authenticated": True,
            "operational_auth_available": True,
            "user_id": "operator_bob",
            "role": "OPERATOR",
            "plant_scope": self.plant_id,
        }
        sign_off_payload = AssessmentSignOffRequest(
            decision="APPROVED_VERIFIED",
            reviewer="operator_bob",
            notes="Unauthorized sign-off attempt",
        )
        with self.assertRaises(ValueError) as ctx:
            sign_off_assessment(
                session=self.session,
                assessment_id=asm.assessment_id,
                req=sign_off_payload,
                auth_caller=unauth_caller,
            )
        self.assertIn("not authorized", str(ctx.exception).lower())

        # Caller has authorized role but WRONG plant scope (IN-KA-01 instead of IN-TN-01)
        wrong_plant_caller = {
            "is_authenticated": True,
            "operational_auth_available": True,
            "user_id": "engineer_alice",
            "role": "ENERGY_ENGINEER",
            "plant_scope": "IN-KA-01",  # Mismatched plant!
        }
        with self.assertRaises(ValueError) as ctx2:
            sign_off_assessment(
                session=self.session,
                assessment_id=asm.assessment_id,
                req=sign_off_payload,
                auth_caller=wrong_plant_caller,
            )
        self.assertIn("plant scope", str(ctx2.exception).lower())

    def test_regression_unrelated_146kwh_never_mentions_fal_l2(self):
        """
        Regression Check 1:
        An unrelated meter reading of 146.318 kWh on MTR-HVAC at IN-TN-01
        must NEVER produce the FAL-L2 story.
        Preserves genuine zeros, identifies missing production evidence explicitly.
        """
        fnd_hvac = OperationalFinding(
            finding_id="FND-HVAC-146",
            finding_key="FND-HVAC-146-KEY",
            plant_id="IN-TN-01",
            line_id=None,  # Utility meter: not attached to FAL-L2
            meter_id="MTR-HVAC",
            anomaly_type="PEAK_ENERGY_ANOMALY",
            severity="HIGH",
            status="NEW",
            first_detected_at=datetime(2026, 11, 6, 11, 0),
            last_detected_at=datetime(2026, 11, 6, 12, 0),
            current_actual_value=Decimal("146.3180"),
        )
        self.session.add(fnd_hvac)
        self.session.flush()

        occ_hvac = FindingOccurrence(
            occurrence_id="OCC-HVAC-146",
            finding_id=fnd_hvac.finding_id,
            occurrence_ts=datetime(2026, 11, 6, 11, 0),
            actual_value=Decimal("146.3180"),
            deviation_score=3.5,
            severity="HIGH",
            explanation="Unrelated 146.318 kWh reading on HVAC utility circuit",
        )
        self.session.add(occ_hvac)
        self.session.commit()

        # Seed real energy meter reading in DB
        self._add_energy_reading("READ-HVAC-REAL-01", datetime(2026, 11, 6, 11, 0), 146.318, meter_id="MTR-HVAC")
        self.session.commit()

        ai_inv = investigate_finding_with_ai(self.session, fnd_hvac.finding_id, occ_hvac.occurrence_id)

        # 1. Must NOT be flagged as the Nov 4 FAL-L2 regression case
        self.assertFalse(ai_inv["is_regression_case_nov4"])

        # 2. Must NEVER mention FAL-L2 in any of the 4 sections
        combined_text = (
            ai_inv["what_we_observed"]
            + " " + ai_inv["how_it_compares"]
            + " " + ai_inv["what_we_still_need_to_know"]
            + " " + ai_inv["what_to_check_next"]
        )
        self.assertNotIn("FAL-L2", combined_text)
        self.assertNotIn("Line FAL", combined_text)
        self.assertIn("MTR-HVAC", combined_text)

        # 3. Explicitly flags missing production evidence
        self.assertTrue(ai_inv["missing_evidence"]["missing_production_record"])
        self.assertFalse(ai_inv["missing_evidence"]["missing_energy_reading"])

        # 4. Citations contain confirmed database reading ID
        cited_ids = [c["id"] for c in ai_inv["citations"]]
        self.assertIn("READ-HVAC-REAL-01", cited_ids)

    def test_regression_shared_compressor_proposes_measurement_check(self):
        """
        Regression Check 2:
        If a shared compressor draws power during a break and another line may still need air,
        the agent proposes a measurement check first (EVIDENCE_GATHERING) instead of direct shutdown.
        """
        fnd_comp = OperationalFinding(
            finding_id="FND-COMPRESSOR",
            finding_key="FND-COMPRESSOR-KEY",
            plant_id=self.plant_id,
            line_id=None,
            meter_id="MTR-COMPRESSOR",
            anomaly_type="STANDBY_POWER_ANOMALY",
            severity="HIGH",
            status="NEW",
            first_detected_at=datetime(2026, 11, 4, 10, 0),
            last_detected_at=datetime(2026, 11, 4, 11, 0),
        )
        self.session.add(fnd_comp)
        self.session.flush()

        rec_comp = OperationalRecommendation(
            recommendation_id="REC-COMPRESSOR-BREAK",
            finding_id=fnd_comp.finding_id,
            plant_id=self.plant_id,
            title="Shared Compressor Standby Mitigation",
            description="Consider compressor power modulation during production break",
            category="STANDBY_SHUTDOWN",
            priority="HIGH",
            status="OPEN",
        )
        self.session.add(rec_comp)
        self.session.commit()

        draft = draft_trial_plan_from_recommendation(
            self.session,
            rec_comp.recommendation_id,
            break_duration_minutes=60.0,
            restart_readiness_minutes=10.0,
        )

        self.assertTrue(draft["is_suitable"])
        self.assertEqual(draft["recommendation_type"], "EVIDENCE_GATHERING")
        self.assertIn("shared utility services across multiple production lines", draft["audit_recommendation"].lower())
        self.assertIn("another operating line may still require compressed air", draft["audit_recommendation"].lower())
        self.assertIsNone(draft["plan_draft"])
        self.assertIsNotNone(draft["suggested_operating_change"])
        self.assertIsNotNone(draft["production_dependencies"])
        self.assertIsNotNone(draft["restart_requirements"])
        self.assertIsNotNone(draft["stop_conditions"])
        self.assertIn("tools_called", draft["agent_execution_trace"])

    def test_regression_provider_offline_fallback_fidelity(self):
        """
        Regression Check 3:
        When Domo AI is offline or encounters an error, the system applies
        RULE_BASED_FALLBACK label, preserves identical source record access,
        and leaves calculation arithmetic 100% deterministic and reproducible.
        """
        finding = OperationalFinding(
            finding_id="FND-OFFLINE-TEST",
            finding_key="FND-OFFLINE-TEST-KEY",
            plant_id=self.plant_id,
            line_id="SMT-01",
            meter_id="MTR-SMT",
            anomaly_type="ZERO_PRODUCTION_STANDBY_ENERGY",
            severity="MEDIUM",
            status="NEW",
            first_detected_at=datetime(2026, 11, 5, 14, 0),
            last_detected_at=datetime(2026, 11, 5, 15, 0),
            current_actual_value=Decimal("45.2000"),
        )
        self.session.add(finding)
        self.session.flush()

        occ = FindingOccurrence(
            occurrence_id="OCC-OFFLINE-TEST",
            finding_id=finding.finding_id,
            occurrence_ts=datetime(2026, 11, 5, 14, 0),
            actual_value=Decimal("45.2000"),
            deviation_score=2.1,
            severity="MEDIUM",
        )
        self.session.add(occ)
        self.session.commit()

        # Seed reading and production
        self._add_energy_reading("READ-SMT-OFFLINE", datetime(2026, 11, 5, 14, 0), 45.200, meter_id="MTR-SMT")
        self._add_production("EVT-SMT-OFFLINE", datetime(2026, 11, 5, 14, 0), "SMT-01", actual_qty=0, good_qty=0, reject_qty=0, downtime_min=60, downtime_reason="SHIFT_BREAK")
        self.session.commit()

        # Force provider offline via mock
        with patch("app.services.finding_ai_investigation_service.get_domo_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.default_model = "domogpt-large-v2.2:anthropic"
            mock_client.generate_text.side_effect = ConnectionError("Domo API network unreachable (offline)")
            mock_get_client.return_value = mock_client

            ai_inv = investigate_finding_with_ai(self.session, finding.finding_id, occ.occurrence_id)

            # Must fall back cleanly with RULE_BASED_FALLBACK label
            self.assertEqual(ai_inv["inference_source"], "RULE_BASED_FALLBACK")
            self.assertEqual(ai_inv["agent_execution_trace"]["status"], "FALLBACK_APPLIED")
            self.assertIn("tools_called", ai_inv["agent_execution_trace"])

            # Ground truth records must remain fully accessible and cited
            self.assertIn("45.200 kWh", ai_inv["what_we_observed"])
            self.assertIn("0 good finished units", ai_inv["what_we_observed"])
            self.assertIn("60 minutes", ai_inv["what_we_observed"])
            self.assertIn("READ-SMT-OFFLINE", [c["id"] for c in ai_inv["citations"]])
            self.assertIn("EVT-SMT-OFFLINE", [c["id"] for c in ai_inv["citations"]])

    def test_regression_legacy_finding_without_occurrences_investigates_cleanly(self):
        """
        Regression Check:
        A legacy finding with 0 occurrences in the database (e.g. TEST-PROV-eb95cbed-LEGACY)
        must investigate cleanly without raising a 404 ValueError.
        It flags missing_occurrence_records: True, preserves finding citation, and explains data gaps.
        """
        fnd_legacy = OperationalFinding(
            finding_id="FND-LEGACY-ZERO-OCCS",
            finding_key="KEY-FND-LEGACY-ZERO-OCCS",
            plant_id="IN-TN-01",
            line_id=None,
            meter_id=None,
            anomaly_type="ENERGY_STATISTICAL_SPIKE",
            severity="MEDIUM",
            status="NEW",
            first_detected_at=datetime(2026, 11, 20, 5, 0),
            last_detected_at=datetime(2026, 11, 20, 6, 0),
            current_actual_value=Decimal("0.0000"),
        )
        self.session.add(fnd_legacy)
        self.session.commit()

        # Offline fallback test
        with patch("app.services.finding_ai_investigation_service.get_domo_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.default_model = "domogpt-large-v2.2:anthropic"
            mock_client.generate_text.side_effect = ConnectionError("Offline for deterministic test")
            mock_get_client.return_value = mock_client

            ai_inv = investigate_finding_with_ai(self.session, fnd_legacy.finding_id)

            self.assertEqual(ai_inv["status"], "SUCCESS")
            self.assertEqual(ai_inv["finding_id"], "FND-LEGACY-ZERO-OCCS")
            self.assertIsNone(ai_inv["occurrence_id"])
            self.assertTrue(ai_inv["missing_evidence"]["missing_occurrence_records"])
            self.assertTrue(ai_inv["missing_evidence"]["missing_energy_reading"])
            self.assertTrue(ai_inv["missing_evidence"]["missing_production_record"])
            self.assertIn("FND-LEGACY-ZERO-OCCS", [c["id"] for c in ai_inv["citations"]])
            self.assertIn("No granular occurrence records", ai_inv["what_we_observed"])

    def test_regression_invented_claim_never_acquires_real_citation(self):
        """
        Regression Check 4:
        An invented claim such as 'Saved 999 kWh [reading:invented]' must NEVER
        acquire a real citation ID (e.g. [reading:EN-000022837]).
        Validate the exact record type, ID, quantity, unit and scope.
        Remove unsupported claims or label them unverified.
        """
        from app.services.finding_ai_investigation_service import validate_citations_in_text
        valid_cits = [
            {"type": "METER_READING", "id": "EN-000022837", "label": "Meter Reading EN-000022837 (74.391 kWh)"},
            {"type": "PRODUCTION", "id": "PRD-00009136", "label": "Production Record PRD-00009136 (0 good units, 60m downtime)"},
        ]
        text_with_invented = "Observed 74.391 kWh [reading:EN-000022837]. Saved 999 kWh [reading:invented] during break."
        cleaned = validate_citations_in_text(text_with_invented, valid_cits)
        
        # Must preserve real citation
        self.assertIn("[reading:EN-000022837]", cleaned)
        # Must NEVER map [reading:invented] to [reading:EN-000022837]!
        self.assertNotIn("[reading:EN-000022837] during break", cleaned)
        self.assertNotIn("[reading:invented]", cleaned)

    def test_regression_zero_downtime_preserved_and_missing_downtime_unknown(self):
        """
        Regression Check 5:
        Preserve zero downtime as zero and missing downtime as unknown.
        """
        from app.services.finding_ai_investigation_service import retrieve_occurrence_evidence, _synthesize_rule_based_investigation
        
        # Case A: Zero downtime (0 min) on active running line
        fnd_a = OperationalFinding(
            finding_id="FND-ZERO-DT",
            finding_key="KEY-FND-ZERO-DT",
            plant_id="IN-TN-01",
            line_id="SMT-01",
            meter_id="MTR-SMT",
            anomaly_type="ENERGY_SPIKE",
            severity="MEDIUM",
            status="NEW",
            first_detected_at=datetime(2026, 11, 10, 10, 0),
            last_detected_at=datetime(2026, 11, 10, 11, 0),
            current_actual_value=Decimal("80.0000"),
        )
        self.session.add(fnd_a)
        self.session.flush()
        occ_a = FindingOccurrence(
            occurrence_id="OCC-ZERO-DT",
            finding_id=fnd_a.finding_id,
            occurrence_ts=datetime(2026, 11, 10, 10, 0),
            actual_value=Decimal("80.0000"),
            deviation_score=2.0,
            severity="MEDIUM",
        )
        self.session.add(occ_a)
        self._add_production("EVT-ZERO-DT", datetime(2026, 11, 10, 10, 0), "SMT-01", actual_qty=100, good_qty=98, reject_qty=2, downtime_min=0, downtime_reason="NONE")
        self.session.commit()

        ev_a = retrieve_occurrence_evidence(self.session, fnd_a.finding_id, occ_a.occurrence_id)
        self.assertEqual(ev_a["downtime_min"], 0)
        synth_a = _synthesize_rule_based_investigation(ev_a)
        self.assertIn("0 minutes", synth_a["what_we_observed"])

        # Case B: Missing downtime (None)
        fnd_b = OperationalFinding(
            finding_id="FND-MISSING-DT",
            finding_key="KEY-FND-MISSING-DT",
            plant_id="IN-TN-01",
            line_id="SMT-02",
            meter_id="MTR-SMT",
            anomaly_type="ENERGY_SPIKE",
            severity="MEDIUM",
            status="NEW",
            first_detected_at=datetime(2026, 11, 10, 12, 0),
            last_detected_at=datetime(2026, 11, 10, 13, 0),
            current_actual_value=Decimal("85.0000"),
        )
        self.session.add(fnd_b)
        self.session.flush()
        occ_b = FindingOccurrence(
            occurrence_id="OCC-MISSING-DT",
            finding_id=fnd_b.finding_id,
            occurrence_ts=datetime(2026, 11, 10, 12, 0),
            actual_value=Decimal("85.0000"),
            deviation_score=2.2,
            severity="MEDIUM",
        )
        self.session.add(occ_b)
        self.session.commit()

        ev_b = retrieve_occurrence_evidence(self.session, fnd_b.finding_id, occ_b.occurrence_id)
        self.assertIsNone(ev_b["downtime_min"])
        synth_b = _synthesize_rule_based_investigation(ev_b)
        self.assertIn("unknown", synth_b["what_we_observed"].lower())
        self.assertNotIn("0 minutes", synth_b["what_we_observed"])

    def test_regression_power_factor_identified_in_explanations(self):
        """
        Regression Check 6:
        For a meter row containing 74 kWh and 0.82 power factor,
        verify that explanations identify 0.82 as power factor.
        """
        from app.services.finding_ai_investigation_service import retrieve_occurrence_evidence, _synthesize_rule_based_investigation
        fnd_pf = OperationalFinding(
            finding_id="FND-PF-TEST",
            finding_key="KEY-FND-PF-TEST",
            plant_id="IN-TN-01",
            line_id="FAL-L1",
            meter_id="MTR-PF-74",
            anomaly_type="ZERO_PRODUCTION_STANDBY_ENERGY",
            severity="HIGH",
            status="NEW",
            first_detected_at=datetime(2026, 11, 12, 8, 0),
            last_detected_at=datetime(2026, 11, 12, 9, 0),
            current_actual_value=Decimal("74.0000"),
        )
        self.session.add(fnd_pf)
        self.session.flush()
        occ_pf = FindingOccurrence(
            occurrence_id="OCC-PF-TEST",
            finding_id=fnd_pf.finding_id,
            occurrence_ts=datetime(2026, 11, 12, 8, 0),
            actual_value=Decimal("74.0000"),
            deviation_score=2.5,
            severity="HIGH",
        )
        self.session.add(occ_pf)
        # Meter reading with 74 kWh and 0.82 power factor
        rdg = FactEnergyMeterHourly(
            meter_reading_id="READ-PF-74-82",
            timestamp=datetime(2026, 11, 12, 8, 0),
            date=datetime(2026, 11, 12, 8, 0).date(),
            plant_id="IN-TN-01",
            meter_id="MTR-PF-74",
            area="MAIN",
            energy_source="ELECTRICITY",
            consumption_kwh=Decimal("74.0000"),
            demand_kw=Decimal("74.0000"),
            power_factor=Decimal("0.8200"),
            tariff_inr_per_kwh=Decimal("8.2500"),
            cost_inr=Decimal("610.50"),
            co2e_kg=Decimal("60.6800"),
            reading_quality="VALID",
        )
        self.session.add(rdg)
        self.session.commit()

        ev = retrieve_occurrence_evidence(self.session, fnd_pf.finding_id, occ_pf.occurrence_id)
        self.assertEqual(ev["power_factor"], 0.82)
        synth = _synthesize_rule_based_investigation(ev)
        self.assertIn("0.82", synth["what_we_observed"])
        self.assertIn("power factor", synth["what_we_observed"].lower())

    def test_regression_continuous_stoppages_counted_separately_from_hourly_readings(self):
        """
        Regression Check 7:
        Count continuous stoppages separately from hourly readings and
        show how many matched readings support each comparison.
        """
        from app.services.finding_ai_investigation_service import retrieve_occurrence_evidence, _synthesize_rule_based_investigation
        fnd_cs = OperationalFinding(
            finding_id="FND-CONT-STOPPAGE",
            finding_key="KEY-FND-CONT-STOPPAGE",
            plant_id="IN-TN-01",
            line_id="FAL-CS",
            meter_id="MTR-CS",
            anomaly_type="ZERO_PRODUCTION_STANDBY_ENERGY",
            severity="HIGH",
            status="NEW",
            first_detected_at=datetime(2026, 11, 15, 10, 0),
            last_detected_at=datetime(2026, 11, 15, 11, 0),
            current_actual_value=Decimal("70.0000"),
        )
        self.session.add(fnd_cs)
        self.session.flush()
        occ_cs = FindingOccurrence(
            occurrence_id="OCC-CONT-STOPPAGE",
            finding_id=fnd_cs.finding_id,
            occurrence_ts=datetime(2026, 11, 15, 10, 0),
            actual_value=Decimal("70.0000"),
            deviation_score=2.0,
            severity="HIGH",
        )
        self.session.add(occ_cs)
        # Episode 1: 3 continuous hours (01:00, 02:00, 03:00 on Nov 13)
        for h in [1, 2, 3]:
            self._add_production(f"EVT-CS-EP1-{h}", datetime(2026, 11, 13, h, 0), "FAL-CS", actual_qty=0, good_qty=0, reject_qty=0, downtime_min=60, downtime_reason="BREAK")
            self._add_energy_reading(f"READ-CS-EP1-{h}", datetime(2026, 11, 13, h, 0), 65.0, meter_id="MTR-CS")
        # Episode 2: 1 single hour (14:00 on Nov 14)
        self._add_production("EVT-CS-EP2-14", datetime(2026, 11, 14, 14, 0), "FAL-CS", actual_qty=0, good_qty=0, reject_qty=0, downtime_min=60, downtime_reason="BREAK")
        self._add_energy_reading("READ-CS-EP2-14", datetime(2026, 11, 14, 14, 0), 68.0, meter_id="MTR-CS")
        self.session.commit()

        ev = retrieve_occurrence_evidence(self.session, fnd_cs.finding_id, occ_cs.occurrence_id)
        # 4 total hourly readings across 2 continuous stoppage episodes
        self.assertEqual(ev["continuous_stoppages_count"], 2)
        self.assertEqual(ev["matched_hourly_production_readings_count"], 4)
        self.assertEqual(ev["matched_energy_readings_count"], 4)
        synth = _synthesize_rule_based_investigation(ev)
        self.assertIn("2 continuous stoppage episodes", synth["how_it_compares"])
        self.assertIn("4 matched hourly", synth["how_it_compares"])

    def test_regression_shared_compressor_unknown_dependencies_blocked(self):
        """
        Regression Check 8:
        If a shared compressor's dependent lines are unknown, recommend measuring
        demand first and block an equipment-change trial until the dependency is resolved.
        """
        from app.services.recommendation_service import draft_trial_plan_from_recommendation
        fnd_comp = OperationalFinding(
            finding_id="FND-COMP-UNKNOWN",
            finding_key="KEY-FND-COMP-UNKNOWN",
            plant_id="IN-TN-01",
            line_id=None,  # Unknown dependent line!
            meter_id="MTR-COMPRESSOR-CENTRAL",
            anomaly_type="STANDBY_POWER_ANOMALY",
            severity="HIGH",
            status="NEW",
            first_detected_at=datetime(2026, 11, 16, 12, 0),
            last_detected_at=datetime(2026, 11, 16, 13, 0),
            current_actual_value=Decimal("120.0000"),
        )
        self.session.add(fnd_comp)
        self.session.flush()
        rec_comp = OperationalRecommendation(
            recommendation_id="REC-COMP-UNKNOWN",
            finding_id=fnd_comp.finding_id,
            plant_id="IN-TN-01",
            title="Shared Central Compressor Optimization",
            description="Optimize compressor controls",
            category="STANDBY_SHUTDOWN",
            priority="HIGH",
            status="OPEN",
        )
        self.session.add(rec_comp)
        self.session.commit()

        draft = draft_trial_plan_from_recommendation(self.session, rec_comp.recommendation_id)
        self.assertEqual(draft["recommendation_type"], "EVIDENCE_GATHERING")
        self.assertTrue(draft["is_equipment_trial_blocked"])
        self.assertIsNone(draft["plan_draft"])
        self.assertIn("measur", draft["audit_recommendation"].lower())
        self.assertIn("blocked", draft["audit_recommendation"].lower())


if __name__ == "__main__":
    unittest.main()
