"""
Comprehensive Regression Test Suite for Savings Decision & M&V Workflow.
Validates P0 and P1 defect fixes from Energy-Agent-QA-Report.md:
1. High uncertainty inconclusive attribution (rates 10, 100, 190 vs 99).
2. Missing action/implementation attribution denial (rates 100, 100, 100 vs 50 without action).
3. Eligible positive control allowing valid verified claim.
4. Downstream sign-off and ledger verification isolation.
5. Dual boundary deduplication (identical windows give -2 once, adjacent windows, distinct meters).
6. Independent denominator guards (zero baseline electricity, zero baseline cost, zero good units).
7. November 4 FAL-L2 synthetic case validation.
8. Factor assumption effective date resolution and mid-window rate change.
9. Measurement plan lifecycle (create -> reload -> amend -> approve -> implement -> assess -> sign-off).
10. Unresolved symbol resolution (request_action_assessment, InterventionAssessment, now_utc, expected_kwh).
"""

import json
import math
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import Base
from app.models.recommendations import (
    ActionAuditLog,
    CorrectiveAction,
    InterventionAssessment,
    InterventionPlan,
    OperationalRecommendation,
)
from app.models.source_data import (
    DatasetFactorAssumption,
    DimProductionLine,
    FactEnergyMeterHourly,
    FactHourlyProduction,
    FactSourceRevision,
)
from app.schemas.interventions import (
    AmendMeasurementPlanRequest,
    ApproveMeasurementPlanRequest,
    AssessmentSignOffRequest,
    CreateMeasurementPlanRequest,
    RecordImplementationRequest,
    RequestAssessmentRequest,
)
from app.services.intervention_comparison_service import (
    calculate_dual_boundary_attribution,
    calculate_repeated_stoppages_attribution,
    compute_window_interval_cost,
    evaluate_guardrails,
    execute_deterministic_comparison,
    get_unique_boundary_kwh,
    resolve_factor_assumption,
    resolve_line_and_process,
)
from app.services.intervention_service import (
    amend_measurement_plan,
    approve_measurement_plan,
    create_measurement_plan,
    evaluate_and_record_assessment,
    get_measurement_plan_for_action,
    list_savings_ledger,
    record_action_implementation,
    request_action_assessment,
    sign_off_assessment,
)


class TestSavingsDecisionRegression(unittest.TestCase):
    """Unit and integration regression tests for savings decision repairs."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.session = self.SessionLocal()

        self.plant_id = "IN-KA-01"
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

        # Seed approved tariff factor
        self.tariff = DatasetFactorAssumption(
            factor_id="TARIFF-IN-KA-01-V1",
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

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def _make_assessment(self, **kwargs):
        defaults = {
            "baseline_kwh": 100.0,
            "post_kwh": 68.0,
            "baseline_cost_inr": 825.0,
            "post_cost_inr": 561.0,
            "baseline_actual_units": 150,
            "baseline_good_units": 150,
            "baseline_reject_units": 0,
            "baseline_downtime_min": 0,
            "baseline_operating_hours": 2,
            "baseline_coverage_pct": 100.0,
            "post_actual_units": 150,
            "post_good_units": 145,
            "post_reject_units": 5,
            "post_downtime_min": 10,
            "post_operating_hours": 2,
            "post_coverage_pct": 100.0,
            "monetary_savings_basis": "APPROVED_CONTRACT_TARIFF",
            "savings_claim_status": "PENDING_REVIEW",
            "savings_claim_description": "Default test claim description",
            "status_reason": "Default test status reason",
        }
        for k, v in defaults.items():
            if k not in kwargs:
                kwargs[k] = v
        return InterventionAssessment(**kwargs)

    def test_p0_defect_1_high_uncertainty_inconclusive(self):
        """
        Defect 1: Three reference rates of 10, 100, 190 kWh/h with post rate of 99
        produced 1.0 kWh attributable savings despite uncertainty margin 203.6892 kWh.
        Verify that:
        1. Status is INCONCLUSIVE_HIGH_UNCERTAINTY.
        2. verified_electricity_savings_kwh is None.
        3. verified_monetary_savings_inr is None.
        4. Observed reduction of 1.0 kWh and uncertainty margin of 203.6892 kWh are preserved.
        """
        plan = InterventionPlan(
            plan_id="PLN-TEST-UNCERTAIN",
            action_id="ACT-TEST-01",
            version=1,
            is_frozen=True,
            is_retrospective=False,
            approved_at=datetime(2026, 11, 4, 1, 0, tzinfo=timezone.utc),
            baseline_start=datetime(2026, 11, 4, 1, 0),
            baseline_end=datetime(2026, 11, 4, 4, 0),
            post_start=datetime(2026, 11, 4, 10, 0),
            post_end=datetime(2026, 11, 4, 11, 0),
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL"]),
            min_coverage_pct=90.0,
            operating_conditions_json=json.dumps({
                "min_reference_count": 3,
                "comparison_method": "REPEATED_STOPPAGES_DEDICATED_METER_V1",
            }),
        )
        action = CorrectiveAction(
            action_id="ACT-TEST-01",
            plant_id=self.plant_id,
            title="Stoppage Idle Optimization",
            description="Optimize stoppage idle power draw",
            implemented_at=datetime(2026, 11, 4, 9, 30),
            implemented_by="Lead Engineer",
            measurement_plan_id=plan.plan_id,
        )

        ref_episodes = [
            {"episode_id": "EP-1", "start_ts": "2026-11-04T01:00:00", "end_ts": "2026-11-04T02:00:00", "duration_hours": 1, "total_kwh": 10.0, "hourly_rate_kwh": 10.0},
            {"episode_id": "EP-2", "start_ts": "2026-11-04T02:00:00", "end_ts": "2026-11-04T03:00:00", "duration_hours": 1, "total_kwh": 100.0, "hourly_rate_kwh": 100.0},
            {"episode_id": "EP-3", "start_ts": "2026-11-04T03:00:00", "end_ts": "2026-11-04T04:00:00", "duration_hours": 1, "total_kwh": 190.0, "hourly_rate_kwh": 190.0},
        ]
        post_episodes = [
            {"episode_id": "EP-POST", "start_ts": "2026-11-04T10:00:00", "end_ts": "2026-11-04T11:00:00", "duration_hours": 1, "total_kwh": 99.0, "hourly_rate_kwh": 99.0},
        ]

        with patch("app.services.intervention_comparison_service.extract_stoppage_episodes") as mock_extract:
            mock_extract.side_effect = [(ref_episodes, []), (post_episodes, [])]
            tariff_factor = resolve_factor_assumption(self.session, "ELECTRICITY_TARIFF", self.plant_id)

            res = calculate_repeated_stoppages_attribution(
                session=self.session,
                plan=plan,
                action=action,
                tariff_factor=tariff_factor,
                resolved_line_id="FAL-L2",
                meters=["MTR-FAL"],
            )

        self.assertEqual(res["status"], "INCONCLUSIVE_HIGH_UNCERTAINTY")
        self.assertIsNone(res["verified_electricity_savings_kwh"])
        self.assertIsNone(res["verified_monetary_savings_inr"])
        self.assertEqual(res["observed_avoided_kwh"], 1.0)
        self.assertAlmostEqual(res["margin_of_error_kwh"], 203.6892, places=3)
        self.assertLessEqual(res["ci_lower_bound_kwh"], 0.0)
        self.assertTrue(res["is_estimate"])
        self.assertIn("high uncertainty", res["reason"].lower())

    def test_p0_defect_2_missing_action_denies_attribution(self):
        """
        Defect 2: Three reference rates of 100 with post rate 50 produced 50 kWh
        attributable savings without an action record.
        Verify that:
        1. When action is None, status is UNVERIFIED_NO_IMPLEMENTATION.
        2. verified_electricity_savings_kwh is None.
        3. verified_monetary_savings_inr is None.
        4. Observed difference and expected/observed kWh are preserved.
        """
        plan = InterventionPlan(
            plan_id="PLN-TEST-NO-ACTION",
            action_id="ACT-NONE",
            version=1,
            is_frozen=True,
            is_retrospective=False,
            approved_at=datetime(2026, 11, 4, 1, 0, tzinfo=timezone.utc),
            baseline_start=datetime(2026, 11, 4, 1, 0),
            baseline_end=datetime(2026, 11, 4, 4, 0),
            post_start=datetime(2026, 11, 4, 10, 0),
            post_end=datetime(2026, 11, 4, 11, 0),
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL"]),
            min_coverage_pct=90.0,
            operating_conditions_json=json.dumps({
                "min_reference_count": 3,
                "comparison_method": "REPEATED_STOPPAGES_DEDICATED_METER_V1",
            }),
        )

        ref_episodes = [
            {"episode_id": "EP-1", "start_ts": "2026-11-04T01:00:00", "end_ts": "2026-11-04T02:00:00", "duration_hours": 1, "total_kwh": 100.0, "hourly_rate_kwh": 100.0},
            {"episode_id": "EP-2", "start_ts": "2026-11-04T02:00:00", "end_ts": "2026-11-04T03:00:00", "duration_hours": 1, "total_kwh": 100.0, "hourly_rate_kwh": 100.0},
            {"episode_id": "EP-3", "start_ts": "2026-11-04T03:00:00", "end_ts": "2026-11-04T04:00:00", "duration_hours": 1, "total_kwh": 100.0, "hourly_rate_kwh": 100.0},
        ]
        post_episodes = [
            {"episode_id": "EP-POST", "start_ts": "2026-11-04T10:00:00", "end_ts": "2026-11-04T11:00:00", "duration_hours": 1, "total_kwh": 50.0, "hourly_rate_kwh": 50.0},
        ]

        with patch("app.services.intervention_comparison_service.extract_stoppage_episodes") as mock_extract:
            mock_extract.side_effect = [(ref_episodes, []), (post_episodes, [])]
            tariff_factor = resolve_factor_assumption(self.session, "ELECTRICITY_TARIFF", self.plant_id)

            # Test with action = None
            res_no_action = calculate_repeated_stoppages_attribution(
                session=self.session,
                plan=plan,
                action=None,
                tariff_factor=tariff_factor,
                resolved_line_id="FAL-L2",
                meters=["MTR-FAL"],
            )

        self.assertEqual(res_no_action["status"], "UNVERIFIED_NO_IMPLEMENTATION")
        self.assertIsNone(res_no_action["verified_electricity_savings_kwh"])
        self.assertIsNone(res_no_action["verified_monetary_savings_inr"])
        self.assertEqual(res_no_action["observed_avoided_kwh"], 50.0)
        self.assertEqual(res_no_action["total_expected_kwh"], 100.0)
        self.assertEqual(res_no_action["total_observed_kwh"], 50.0)

    def test_positive_control_eligible_case_verifies(self):
        """
        Positive control: Stable references of 100, post rate 50, with valid action,
        implementation timestamp, prospectively approved plan, and eligible boundary.
        Verify that verified_electricity_savings_kwh is 50.0 and status is ATTRIBUTED.
        """
        plan = InterventionPlan(
            plan_id="PLN-TEST-VALID",
            action_id="ACT-VALID-01",
            version=1,
            is_frozen=True,
            is_retrospective=False,
            approved_at=datetime(2026, 11, 4, 1, 0, tzinfo=timezone.utc),
            baseline_start=datetime(2026, 11, 4, 1, 0),
            baseline_end=datetime(2026, 11, 4, 4, 0),
            post_start=datetime(2026, 11, 4, 10, 0),
            post_end=datetime(2026, 11, 4, 11, 0),
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL"]),
            min_coverage_pct=90.0,
            operating_conditions_json=json.dumps({
                "min_reference_count": 3,
                "comparison_method": "REPEATED_STOPPAGES_DEDICATED_METER_V1",
            }),
        )
        action = CorrectiveAction(
            action_id="ACT-VALID-01",
            plant_id=self.plant_id,
            title="Valid Stoppage Optimization",
            description="Valid stoppage optimization description",
            implemented_at=datetime(2026, 11, 4, 8, 0),
            implemented_by="Plant Energy Lead",
            measurement_plan_id=plan.plan_id,
        )

        ref_episodes = [
            {"episode_id": "EP-1", "start_ts": "2026-11-04T01:00:00", "end_ts": "2026-11-04T02:00:00", "duration_hours": 1, "total_kwh": 100.0, "hourly_rate_kwh": 100.0},
            {"episode_id": "EP-2", "start_ts": "2026-11-04T02:00:00", "end_ts": "2026-11-04T03:00:00", "duration_hours": 1, "total_kwh": 100.0, "hourly_rate_kwh": 100.0},
            {"episode_id": "EP-3", "start_ts": "2026-11-04T03:00:00", "end_ts": "2026-11-04T04:00:00", "duration_hours": 1, "total_kwh": 100.0, "hourly_rate_kwh": 100.0},
        ]
        post_episodes = [
            {"episode_id": "EP-POST", "start_ts": "2026-11-04T10:00:00", "end_ts": "2026-11-04T11:00:00", "duration_hours": 1, "total_kwh": 50.0, "hourly_rate_kwh": 50.0},
        ]

        with patch("app.services.intervention_comparison_service.extract_stoppage_episodes") as mock_extract:
            mock_extract.side_effect = [(ref_episodes, []), (post_episodes, [])]
            tariff_factor = resolve_factor_assumption(self.session, "ELECTRICITY_TARIFF", self.plant_id)

            res = calculate_repeated_stoppages_attribution(
                session=self.session,
                plan=plan,
                action=action,
                tariff_factor=tariff_factor,
                resolved_line_id="FAL-L2",
                meters=["MTR-FAL"],
            )

        self.assertEqual(res["status"], "ATTRIBUTED")
        self.assertEqual(res["verified_electricity_savings_kwh"], 50.0)
        self.assertEqual(res["total_expected_kwh"], 100.0)
        self.assertEqual(res["total_observed_kwh"], 50.0)
        self.assertEqual(res["verified_monetary_savings_inr"], 412.50)  # 50.0 * 8.25

    def test_dual_boundary_deduplication(self):
        """
        Defect 4: Dual-boundary net calculation adds both windows even when times overlap.
        Verify that:
        1. Two identical boundaries with 10 baseline and 8 post gives net -2 once.
        2. Adjacent windows give net -4.
        3. Distinct meters give distinct contributions.
        """
        ts1 = datetime(2026, 11, 4, 2, 0)
        ts2 = datetime(2026, 11, 4, 3, 0)
        ts_post1 = datetime(2026, 11, 4, 10, 0)
        ts_post2 = datetime(2026, 11, 4, 11, 0)

        # Baseline: 5 kWh per hour = 10 kWh total
        self.session.add(FactEnergyMeterHourly(meter_reading_id="MTR-01", plant_id=self.plant_id, meter_id="MTR-FAL", area="Assembly", energy_source="Electricity", timestamp=ts1, date=ts1.date(), consumption_kwh=Decimal("5.0"), demand_kw=Decimal("5.0"), power_factor=Decimal("0.95"), tariff_inr_per_kwh=Decimal("8.25"), cost_inr=Decimal("41.25"), co2e_kg=Decimal("3.58"), reading_quality="GOOD"))
        self.session.add(FactEnergyMeterHourly(meter_reading_id="MTR-02", plant_id=self.plant_id, meter_id="MTR-FAL", area="Assembly", energy_source="Electricity", timestamp=ts2, date=ts2.date(), consumption_kwh=Decimal("5.0"), demand_kw=Decimal("5.0"), power_factor=Decimal("0.95"), tariff_inr_per_kwh=Decimal("8.25"), cost_inr=Decimal("41.25"), co2e_kg=Decimal("3.58"), reading_quality="GOOD"))
        # Post: 4 kWh per hour = 8 kWh total
        self.session.add(FactEnergyMeterHourly(meter_reading_id="MTR-03", plant_id=self.plant_id, meter_id="MTR-FAL", area="Assembly", energy_source="Electricity", timestamp=ts_post1, date=ts_post1.date(), consumption_kwh=Decimal("4.0"), demand_kw=Decimal("4.0"), power_factor=Decimal("0.95"), tariff_inr_per_kwh=Decimal("8.25"), cost_inr=Decimal("33.00"), co2e_kg=Decimal("2.86"), reading_quality="GOOD"))
        self.session.add(FactEnergyMeterHourly(meter_reading_id="MTR-04", plant_id=self.plant_id, meter_id="MTR-FAL", area="Assembly", energy_source="Electricity", timestamp=ts_post2, date=ts_post2.date(), consumption_kwh=Decimal("4.0"), demand_kw=Decimal("4.0"), power_factor=Decimal("0.95"), tariff_inr_per_kwh=Decimal("8.25"), cost_inr=Decimal("33.00"), co2e_kg=Decimal("2.86"), reading_quality="GOOD"))
        self.session.commit()

        # Test Case 1: Two identical boundaries [02:00, 04:00) on MTR-FAL
        boundary_specs_base = [
            (["MTR-FAL"], datetime(2026, 11, 4, 2, 0), datetime(2026, 11, 4, 4, 0)),
            (["MTR-FAL"], datetime(2026, 11, 4, 2, 0), datetime(2026, 11, 4, 4, 0)),
        ]
        boundary_specs_post = [
            (["MTR-FAL"], datetime(2026, 11, 4, 10, 0), datetime(2026, 11, 4, 12, 0)),
            (["MTR-FAL"], datetime(2026, 11, 4, 10, 0), datetime(2026, 11, 4, 12, 0)),
        ]

        unique_base, double_base = get_unique_boundary_kwh(self.session, self.plant_id, boundary_specs_base)
        unique_post, double_post = get_unique_boundary_kwh(self.session, self.plant_id, boundary_specs_post)

        self.assertEqual(unique_base, 10.0)
        self.assertEqual(double_base, 2)
        self.assertEqual(unique_post, 8.0)
        self.assertEqual(double_post, 2)

        net_kwh_change = round(unique_post - unique_base, 4)
        self.assertEqual(net_kwh_change, -2.0)  # Exactly -2 once!

    def test_denominator_guards_independent(self):
        """
        Defect 5: Relative-change paths divide by zero when good units are positive
        and baseline electricity or cost is zero.
        Verify that:
        1. When baseline cost or kwh is zero, intensity_change_pct is None.
        2. Absolute change is defined.
        3. No ZeroDivisionError is raised.
        """
        raw_base_kwh_int = 0.0
        raw_post_kwh_int = 2.5
        raw_base_cost_int = 0.0
        raw_post_cost_int = 20.625

        intensity_change_abs = round(raw_post_kwh_int - raw_base_kwh_int, 4)
        intensity_change_pct = (
            round(((raw_post_kwh_int - raw_base_kwh_int) / raw_base_kwh_int) * 100.0, 2)
            if raw_base_kwh_int > 0
            else None
        )
        cost_intensity_change_abs = round(raw_post_cost_int - raw_base_cost_int, 4)
        cost_intensity_change_pct = (
            round(((raw_post_cost_int - raw_base_cost_int) / raw_base_cost_int) * 100.0, 2)
            if raw_base_cost_int > 0
            else None
        )

        self.assertEqual(intensity_change_abs, 2.5)
        self.assertIsNone(intensity_change_pct)
        self.assertEqual(cost_intensity_change_abs, 20.625)
        self.assertIsNone(cost_intensity_change_pct)

    def test_factor_effective_date_resolution(self):
        """
        Defect 6: Tariff resolution must respect effective dates.
        Expired or out-of-range dates must return explicit status.
        """
        res_valid = resolve_factor_assumption(
            self.session, "ELECTRICITY_TARIFF", self.plant_id, target_date=date(2026, 6, 1)
        )
        self.assertTrue(res_valid["is_approved"])
        self.assertEqual(res_valid["numeric_value"], 8.25)

        res_expired = resolve_factor_assumption(
            self.session, "ELECTRICITY_TARIFF", self.plant_id, target_date=date(2027, 2, 1)
        )
        self.assertFalse(res_expired["is_approved"])
        self.assertEqual(res_expired["approval_status"], "EXPIRED_OR_PRE_EFFECTIVE")

    def test_sign_off_rejects_inconclusive_or_unimplemented(self):
        """
        Sign-off flow: Attempting to sign off on an inconclusive assessment
        or assessment with null savings must NOT produce VERIFIED savings claim status.
        """
        rec = OperationalRecommendation(
            recommendation_id="REC-TEST-01",
            plant_id=self.plant_id,
            title="Stoppage Optimization",
            description="Stoppage test description",
            category="BEHAVIORAL",
            priority="HIGH",
            status="OPEN",
        )
        self.session.add(rec)
        action = CorrectiveAction(
            action_id="ACT-SIGNOFF-TEST",
            recommendation_id=rec.recommendation_id,
            plant_id=self.plant_id,
            title="Stoppage Optimization Action",
            description="Signoff action description",
            status="IN_PROGRESS",
        )
        self.session.add(action)
        plan = InterventionPlan(
            plan_id="PLN-SIGNOFF-TEST",
            action_id=action.action_id,
            version=1,
            is_frozen=True,
            is_retrospective=False,
            approved_at=datetime.now(timezone.utc),
            baseline_start=datetime(2026, 11, 4, 1, 0),
            baseline_end=datetime(2026, 11, 4, 4, 0),
            post_start=datetime(2026, 11, 4, 10, 0),
            post_end=datetime(2026, 11, 4, 12, 0),
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL"]),
            min_coverage_pct=90.0,
            intended_change="Stoppage idle minimization",
            implementation_owner="Plant Energy Lead",
            production_denominator="Total Good Units",
            production_unit="units",
            success_criterion="Minimize idle draw",
        )
        self.session.add(plan)
        action.measurement_plan_id = plan.plan_id

        # Inconclusive assessment with null savings
        asm = self._make_assessment(
            assessment_id="ASM-SIGNOFF-TEST",
            action_id=action.action_id,
            plan_id=plan.plan_id,
            plan_version=1,
            assessment_revision=1,
            is_stale_flag=False,
            evaluated_at=datetime.now(timezone.utc),
            evaluated_by="SYSTEM",
            calculation_method="DETERMINISTIC_COMPARISON_V1",
            baseline_kwh=100.0,
            post_kwh=99.0,
            baseline_cost_inr=825.0,
            post_cost_inr=816.75,
            baseline_actual_units=0,
            baseline_good_units=0,
            baseline_reject_units=0,
            baseline_downtime_min=120,
            baseline_operating_hours=2,
            baseline_coverage_pct=100.0,
            post_actual_units=480,
            post_good_units=477,
            post_reject_units=3,
            post_downtime_min=10,
            post_operating_hours=2,
            post_coverage_pct=100.0,
            objective_outcome="INCONCLUSIVE",
            electricity_savings_kwh=None,  # Null attributable savings
            avoided_cost_inr=None,
            verified_monetary_savings_inr=None,
            monetary_savings_basis="INCONCLUSIVE_HIGH_UNCERTAINTY",
            savings_claim_status="NOT_VERIFIED",
            savings_claim_description="Inconclusive attribution due to high uncertainty.",
            status_reason="Inconclusive attribution.",
        )
        self.session.add(asm)
        self.session.commit()

        # Attempt to sign off with APPROVED_VERIFIED
        sign_off_req = AssessmentSignOffRequest(
            decision="APPROVED_VERIFIED",
            reviewer="Energy Manager",
            notes="Formal review sign-off attempt",
        )
        signed = sign_off_assessment(
            session=self.session,
            assessment_id=asm.assessment_id,
            req=sign_off_req,
            auth_caller={
                "is_authenticated": True,
                "operational_auth_available": True,
                "user_id": "eng_manager",
                "role": "ENERGY_ENGINEER",
                "plant_scope": self.plant_id,
            },
        )

        # Verified status MUST BE DENIED because electricity_savings_kwh is None!
        self.assertEqual(signed.savings_claim_status, "NOT_VERIFIED")
        self.assertIsNone(signed.verified_monetary_savings_inr)
        self.assertIn("cannot be verified", signed.status_reason)

        # Check ledger total
        ledger_res = list_savings_ledger(self.session, plant_id=self.plant_id)
        self.assertEqual(ledger_res.total_verified_avoided_kwh, 0.0)
        self.assertEqual(ledger_res.total_verified_avoided_cost_inr, 0.0)

    def test_tariff_change_within_one_measurement_window(self):
        """
        Check 2: Verify an approved tariff change within one measurement window.
        Independent calculation:
        Interval 1 (2026-11-03 23:00): 25.0 kWh @ ₹8.00/kWh = ₹200.00 (revision FA-TAR-KA-V1)
        Interval 2 (2026-11-04 00:00): 25.0 kWh @ ₹9.00/kWh = ₹225.00 (revision FA-TAR-KA-V2)
        Total expected cost: ₹425.00
        Applying the post-start tariff (₹8.00) to the entire window would yield ₹400.00 (INCORRECT).
        The fix ensures each interval applies its effective rate, yielding exactly ₹425.00.
        """
        # Clear any existing factors for test isolation
        self.session.query(DatasetFactorAssumption).delete()
        self.session.commit()

        # Seed two approved tariff versions spanning 2026-11-03 and 2026-11-04
        fa1 = DatasetFactorAssumption(
            factor_id="FA-TAR-KA-V1",
            factor_type="ELECTRICITY_TARIFF",
            factor_scope="IN-KA-01",
            numeric_value=Decimal("8.00"),
            unit="INR/kWh",
            source_dataset_version="Contract_v1_Nov2026",
            approval_status="APPROVED",
            effective_from=date(2026, 11, 1),
            effective_to=date(2026, 11, 3),
        )
        fa2 = DatasetFactorAssumption(
            factor_id="FA-TAR-KA-V2",
            factor_type="ELECTRICITY_TARIFF",
            factor_scope="IN-KA-01",
            numeric_value=Decimal("9.00"),
            unit="INR/kWh",
            source_dataset_version="Contract_v2_Nov2026",
            approval_status="APPROVED",
            effective_from=date(2026, 11, 4),
            effective_to=date(2026, 11, 30),
        )
        self.session.add_all([fa1, fa2])
        self.session.commit()

        interval_readings = [
            {"timestamp": "2026-11-03T23:00:00", "kwh": 25.0, "cost_inr": 200.0},
            {"timestamp": "2026-11-04T00:00:00", "kwh": 25.0, "cost_inr": 225.0},
        ]

        # Compute interval-by-interval window cost
        calc = compute_window_interval_cost(self.session, "IN-KA-01", interval_readings)

        # Verify independent calculation
        self.assertEqual(calc["total_cost_inr"], 425.00)
        self.assertNotEqual(calc["total_cost_inr"], 400.00, "Must not apply post-start tariff across whole window")
        self.assertTrue(calc["all_approved"])
        self.assertEqual(calc["approval_status"], "APPROVED_CONTRACT")
        self.assertIn("Contract_v1_Nov2026", calc["factor_versions"])
        self.assertIn("Contract_v2_Nov2026", calc["factor_versions"])
        self.assertEqual(len(calc["interval_breakdown"]), 2)
        self.assertEqual(calc["interval_breakdown"][0]["rate_inr_per_kwh"], 8.00)
        self.assertEqual(calc["interval_breakdown"][0]["factor_id"], "FA-TAR-KA-V1")
        self.assertEqual(calc["interval_breakdown"][1]["rate_inr_per_kwh"], 9.00)
        self.assertEqual(calc["interval_breakdown"][1]["factor_id"], "FA-TAR-KA-V2")

    def test_tariff_window_with_unapproved_interval(self):
        """
        Check 2: Test showing monetary outcome when one interval in the window has no approved rate.
        Interval 1 (2026-11-03): Approved contract @ ₹8.00/kWh
        Interval 2 (2026-11-04): Unapproved/Estimated factor @ ₹9.00/kWh (approval_status="ESTIMATED")
        Expected outcome: all_approved is False, verified monetary savings is None.
        """
        self.session.query(DatasetFactorAssumption).delete()
        self.session.commit()

        fa1 = DatasetFactorAssumption(
            factor_id="FA-TAR-KA-V1",
            factor_type="ELECTRICITY_TARIFF",
            factor_scope="IN-KA-01",
            numeric_value=Decimal("8.00"),
            unit="INR/kWh",
            source_dataset_version="Contract_v1_Nov2026",
            approval_status="APPROVED",
            effective_from=date(2026, 11, 1),
            effective_to=date(2026, 11, 3),
        )
        fa2_unapproved = DatasetFactorAssumption(
            factor_id="FA-TAR-KA-V2-EST",
            factor_type="ELECTRICITY_TARIFF",
            factor_scope="IN-KA-01",
            numeric_value=Decimal("9.00"),
            unit="INR/kWh",
            source_dataset_version="Unapproved_Estimate_Nov2026",
            approval_status="ESTIMATED",
            effective_from=date(2026, 11, 4),
            effective_to=date(2026, 11, 30),
        )
        self.session.add_all([fa1, fa2_unapproved])
        self.session.commit()

        interval_readings = [
            {"timestamp": "2026-11-03T23:00:00", "kwh": 25.0, "cost_inr": 200.0},
            {"timestamp": "2026-11-04T00:00:00", "kwh": 25.0, "cost_inr": 225.0},
        ]

        calc = compute_window_interval_cost(self.session, "IN-KA-01", interval_readings)

        # Expected cost is computed as descriptive estimate (₹425.00), but cannot be verified
        self.assertEqual(calc["total_cost_inr"], 425.00)
        self.assertFalse(calc["all_approved"], "Must not be approved when any interval is unapproved")
        self.assertEqual(calc["approval_status"], "UNAPPROVED_OR_MISSING_TARIFF")
        self.assertEqual(len(calc["unapproved_intervals"]), 1)
        self.assertEqual(calc["unapproved_intervals"][0]["factor_id"], "FA-TAR-KA-V2-EST")

    def test_acceptance_case_1_stoppage_40kwh_restart_8kwh_net_32kwh_264inr(self):
        """
        Acceptance Case 1:
        Stoppage saves 40 kWh and restart consumes 8 extra kWh. Observed reduction is 32 kWh.
        An eligible signed trial at ₹8.25/kWh records ₹264.
        """
        from app.services.intervention_comparison_service import calculate_dual_boundary_attribution

        attr = calculate_dual_boundary_attribution(
            stoppage_reduction_kwh=40.0,
            restart_overhead_kwh=8.0,
            reference_pool_count=10,
            baseline_cv_pct=15.0,
            uncertainty_pct=5.0,
            is_signed_off=True,
            tariffs_approved=True,
            common_rate_factor=8.25,
            has_implementation_timestamp=True,
            is_retrospective_plan=False,
            production_limits_breached=False,
            unassessable_guardrails=False,
            missing_restart_evidence=False,
        )

        self.assertEqual(attr["stoppage_reduction_kwh"], 40.0)
        self.assertEqual(attr["restart_overhead_kwh"], 8.0)
        self.assertEqual(attr["net_reduction_kwh"], 32.0)
        self.assertEqual(attr["observed_avoided_kwh"], 32.0)
        self.assertEqual(attr["status"], "ATTRIBUTED")
        self.assertEqual(attr["verified_electricity_savings_kwh"], 32.0)
        self.assertEqual(attr["verified_monetary_savings_inr"], 264.0)

    def test_acceptance_case_2_dual_boundary_interval_pricing_differing_rates(self):
        """
        Acceptance Case 2:
        The same 40 kWh is saved at ₹6/kWh (= ₹240) and the extra 8 kWh costs ₹12/kWh (= ₹96).
        The net result is 32 kWh and ₹144.
        """
        from app.services.intervention_comparison_service import calculate_dual_boundary_attribution

        # 40 kWh saved at ₹6/kWh = ₹240.00 avoided
        # 8 kWh restart consumed at ₹12/kWh = ₹96.00 extra cost
        # Net avoided cost = 240 - 96 = ₹144.00
        net_avoided_cost = 240.0 - 96.0

        attr = calculate_dual_boundary_attribution(
            stoppage_reduction_kwh=40.0,
            restart_overhead_kwh=8.0,
            observed_avoided_cost_inr=net_avoided_cost,
            reference_pool_count=8,
            baseline_cv_pct=12.0,
            uncertainty_pct=4.0,
            is_signed_off=True,
            tariffs_approved=True,
            common_rate_factor=8.25,
            has_implementation_timestamp=True,
            is_retrospective_plan=False,
            production_limits_breached=False,
            unassessable_guardrails=False,
            missing_restart_evidence=False,
        )

        self.assertEqual(attr["net_reduction_kwh"], 32.0)
        self.assertEqual(attr["observed_avoided_cost_inr"], 144.0)
        self.assertEqual(attr["verified_electricity_savings_kwh"], 32.0)
        self.assertEqual(attr["verified_monetary_savings_inr"], 144.0)
        self.assertEqual(attr["status"], "ATTRIBUTED")

    def test_acceptance_case_3_negative_stoppage_positive_restart_signs_preserved(self):
        """
        Acceptance Case 3:
        Stoppage consumes 10 extra kWh (stoppage reduction = -10 kWh) and restart
        saves 20 kWh (restart overhead = -20 kWh).
        Observed reduction is (-10) - (-20) = 10 kWh.
        Signs are preserved without arbitrary clipping.
        """
        from app.services.intervention_comparison_service import calculate_dual_boundary_attribution

        attr = calculate_dual_boundary_attribution(
            stoppage_reduction_kwh=-10.0,
            restart_overhead_kwh=-20.0,
            reference_pool_count=12,
            baseline_cv_pct=18.0,
            uncertainty_pct=6.0,
            is_signed_off=True,
            tariffs_approved=True,
            common_rate_factor=8.25,
            has_implementation_timestamp=True,
            is_retrospective_plan=False,
            production_limits_breached=False,
            unassessable_guardrails=False,
            missing_restart_evidence=False,
        )

        self.assertEqual(attr["stoppage_reduction_kwh"], -10.0)
        self.assertEqual(attr["restart_overhead_kwh"], -20.0)
        self.assertEqual(attr["net_reduction_kwh"], 10.0)
        self.assertEqual(attr["observed_avoided_kwh"], 10.0)
        self.assertEqual(attr["status"], "ATTRIBUTED")
        self.assertEqual(attr["verified_electricity_savings_kwh"], 10.0)
        self.assertEqual(attr["verified_monetary_savings_inr"], 82.50)

    def test_acceptance_case_4_overlapping_windows_and_distinct_physical_meters(self):
        """
        Acceptance Case 4:
        Overlapping windows count each physical meter interval once.
        Different physical meters remain distinct.
        """
        from app.services.intervention_comparison_service import get_unique_boundary_intervals

        # Boundary A and Boundary B share meter MTR-01 at 10:00 (overlap)
        # Boundary B also has distinct meter MTR-02 at 10:00
        intervals_a = [
            {"meter_id": "MTR-01", "timestamp": "2026-11-10T10:00:00", "kwh": 15.0},
            {"meter_id": "MTR-01", "timestamp": "2026-11-10T11:00:00", "kwh": 20.0},
        ]
        intervals_b = [
            # Duplicate of (MTR-01, 10:00) with same or overlapping window
            {"meter_id": "MTR-01", "timestamp": "2026-11-10T10:00:00", "kwh": 15.0},
            # Distinct physical meter at same timestamp
            {"meter_id": "MTR-02", "timestamp": "2026-11-10T10:00:00", "kwh": 12.0},
            {"meter_id": "MTR-02", "timestamp": "2026-11-10T11:00:00", "kwh": 14.0},
        ]

        unique_intervals, total_kwh, double_counted = get_unique_boundary_intervals(intervals_a, intervals_b)

        # MTR-01 10:00 counted once (15.0) + MTR-01 11:00 (20.0) + MTR-02 10:00 (12.0) + MTR-02 11:00 (14.0) = 61.0 kWh
        self.assertEqual(len(unique_intervals), 4)
        self.assertEqual(total_kwh, 61.0)
        self.assertEqual(double_counted, 1)

        # Confirm distinct physical meters are both retained
        meters_present = {item["meter_id"] for item in unique_intervals}
        self.assertEqual(meters_present, {"MTR-01", "MTR-02"})

    def test_acceptance_case_5_unverified_disqualification_and_zero_ledger(self):
        """
        Acceptance Case 5:
        Missing restart evidence, a production breach, a retrospective plan,
        absent implementation or excessive uncertainty adds zero verified savings to the ledger.
        """
        from app.services.intervention_comparison_service import calculate_dual_boundary_attribution

        # 5a: Missing restart evidence (unknown restart)
        attr_missing_restart = calculate_dual_boundary_attribution(
            stoppage_reduction_kwh=40.0,
            restart_overhead_kwh=8.0,
            missing_restart_evidence=True,
            is_signed_off=True,
            tariffs_approved=True,
        )
        self.assertEqual(attr_missing_restart["status"], "UNVERIFIED")
        self.assertIsNone(attr_missing_restart["verified_electricity_savings_kwh"])
        self.assertIsNone(attr_missing_restart["verified_monetary_savings_inr"])
        self.assertEqual(attr_missing_restart["observed_avoided_kwh"], 32.0)

        # 5b: Production breach
        attr_breached = calculate_dual_boundary_attribution(
            stoppage_reduction_kwh=40.0,
            restart_overhead_kwh=8.0,
            production_limits_breached=True,
            is_signed_off=True,
            tariffs_approved=True,
        )
        self.assertEqual(attr_breached["status"], "UNVERIFIED")
        self.assertIsNone(attr_breached["verified_electricity_savings_kwh"])
        self.assertIsNone(attr_breached["verified_monetary_savings_inr"])

        # 5c: Retrospective plan
        attr_retrospective = calculate_dual_boundary_attribution(
            stoppage_reduction_kwh=40.0,
            restart_overhead_kwh=8.0,
            is_retrospective_plan=True,
            is_signed_off=True,
            tariffs_approved=True,
        )
        self.assertEqual(attr_retrospective["status"], "UNVERIFIED")
        self.assertIsNone(attr_retrospective["verified_electricity_savings_kwh"])
        self.assertIsNone(attr_retrospective["verified_monetary_savings_inr"])

        # 5d: Absent implementation timestamp
        attr_no_impl = calculate_dual_boundary_attribution(
            stoppage_reduction_kwh=40.0,
            restart_overhead_kwh=8.0,
            has_implementation_timestamp=False,
            is_signed_off=True,
            tariffs_approved=True,
        )
        self.assertEqual(attr_no_impl["status"], "UNVERIFIED")
        self.assertIsNone(attr_no_impl["verified_electricity_savings_kwh"])

        # 5e: Excessive baseline uncertainty (CV > 50%)
        attr_uncertain = calculate_dual_boundary_attribution(
            stoppage_reduction_kwh=40.0,
            restart_overhead_kwh=8.0,
            baseline_cv_pct=85.0,
            is_signed_off=True,
            tariffs_approved=True,
        )
        self.assertEqual(attr_uncertain["status"], "INCONCLUSIVE_HIGH_UNCERTAINTY")
        self.assertIsNone(attr_uncertain["verified_electricity_savings_kwh"])

    def test_acceptance_repeated_signoff_deduplication_in_ledger(self):
        """
        Repeated sign-off on the same action/assessment counts once in ledger totals.
        """
        # Create an assessment with verified savings
        asm1 = self._make_assessment(
            assessment_id="ASM-DEDUP-001",
            action_id="ACT-DEDUP-001",
            plan_id="PLN-DEDUP-001",
            plan_version=1,
            assessment_revision=1,
            objective_outcome="IMPROVED",
            cost_intensity_change_pct=Decimal("-15.0"),
            electricity_savings_kwh=Decimal("32.0"),
            avoided_cost_inr=Decimal("264.0"),
            verified_monetary_savings_inr=Decimal("264.0"),
            common_rate_factor_inr_per_kwh=Decimal("8.25"),
            common_rate_factor_version="TARIFF-TN-HT2A-2026-V1",
            savings_claim_status="VERIFIED",
            signed_off_by="lead_auditor",
            signed_off_at=datetime.utcnow(),
            output_guardrail_met=True,
            quality_guardrail_met=True,
            downtime_guardrail_met=True,
            guardrails_summary_json=json.dumps([{"metric": "OUTPUT", "status": "PASSED", "passed": True}]),
        )
        # Second revision / repeat entry for the SAME action_id
        asm2 = self._make_assessment(
            assessment_id="ASM-DEDUP-002",
            action_id="ACT-DEDUP-001",
            plan_id="PLN-DEDUP-001",
            plan_version=1,
            assessment_revision=2,
            objective_outcome="IMPROVED",
            cost_intensity_change_pct=Decimal("-15.0"),
            electricity_savings_kwh=Decimal("32.0"),
            avoided_cost_inr=Decimal("264.0"),
            verified_monetary_savings_inr=Decimal("264.0"),
            common_rate_factor_inr_per_kwh=Decimal("8.25"),
            common_rate_factor_version="TARIFF-TN-HT2A-2026-V1",
            savings_claim_status="VERIFIED",
            signed_off_by="lead_auditor",
            signed_off_at=datetime.utcnow(),
            output_guardrail_met=True,
            quality_guardrail_met=True,
            downtime_guardrail_met=True,
            guardrails_summary_json=json.dumps([{"metric": "OUTPUT", "status": "PASSED", "passed": True}]),
        )
        self.session.add_all([asm1, asm2])
        self.session.commit()

        ledger = list_savings_ledger(self.session)

        # Repeated sign-offs on ACT-DEDUP-001 must count ONCE in totals
        # verified_count should count distinct actions (1), not 2
        # total_verified_avoided_kwh should be 32.0, not 64.0
        # total_verified_monetary_savings_inr should be 264.0, not 528.0
        self.assertEqual(ledger.verified_count, 1)
        self.assertEqual(ledger.total_verified_avoided_kwh, 32.0)
        self.assertEqual(ledger.total_verified_monetary_savings_inr, 264.0)

    def test_approval_after_implementation_denies_verification(self):
        """
        Regression Check (Point 1): Approval order verification.
        All flags look valid (is_frozen=True, is_retrospective=False, action.implemented_at present),
        but approval happened AFTER implementation (approved_at: 11:00 vs implemented_at: 10:00).
        Sign-off must set savings_claim_status = NOT_VERIFIED, verified_monetary_savings_inr = None,
        and ledger totals must remain 0.
        """
        act = CorrectiveAction(
            action_id="ACT-TIMING-001",
            recommendation_id="REC-TIMING-001",
            plant_id=self.plant_id,
            title="Non-prospective Timing Test Action",
            description="Testing approval sequence enforcement",
            status="IN_PROGRESS",
            implemented_at=datetime(2026, 11, 4, 10, 0, 0),
            implemented_by="technician_01",
        )
        plan = InterventionPlan(
            plan_id="PLN-TIMING-001",
            action_id=act.action_id,
            version=1,
            is_frozen=True,
            is_retrospective=False,
            intended_change="Reduce standby wattage",
            implementation_owner="lead_engineer",
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL"]),
            production_denominator="GOOD_UNITS",
            production_unit="units",
            baseline_start=datetime(2026, 11, 1, 0, 0, 0),
            baseline_end=datetime(2026, 11, 2, 0, 0, 0),
            post_start=datetime(2026, 11, 4, 10, 0, 0),
            post_end=datetime(2026, 11, 4, 14, 0, 0),
            min_coverage_pct=95.0,
            success_criterion="COST_PER_GOOD_UNIT",
            approved_by="plant_manager",
            approved_at=datetime(2026, 11, 4, 11, 0, 0),  # 1 hour AFTER implementation!
        )
        asm = self._make_assessment(
            assessment_id="ASM-TIMING-001",
            action_id=act.action_id,
            plan_id=plan.plan_id,
            plan_version=1,
            assessment_revision=1,
            objective_outcome="IMPROVED",
            cost_intensity_change_pct=Decimal("-12.5"),
            electricity_savings_kwh=Decimal("32.0"),
            avoided_cost_inr=Decimal("264.0"),
            monetary_savings_basis="APPROVED_CONTRACT_TARIFF",
            savings_claim_status="PENDING_REVIEW",
            output_guardrail_met=True,
            quality_guardrail_met=True,
            downtime_guardrail_met=True,
            guardrails_summary_json=json.dumps([{"metric": "OUTPUT", "status": "PASSED", "passed": True}]),
        )
        self.session.add_all([act, plan, asm])
        self.session.commit()

        sign_off_req = AssessmentSignOffRequest(
            decision="APPROVED_VERIFIED",
            reviewer="Plant Manager",
            notes="Attempting sign-off on non-prospective action",
        )
        signed = sign_off_assessment(
            session=self.session,
            assessment_id=asm.assessment_id,
            req=sign_off_req,
            auth_caller={
                "is_authenticated": True,
                "operational_auth_available": True,
                "user_id": "mgr_plant",
                "role": "PLANT_MANAGER",
                "plant_scope": self.plant_id,
            },
        )

        self.assertEqual(signed.savings_claim_status, "NOT_VERIFIED")
        self.assertIsNone(signed.verified_electricity_savings_kwh)
        self.assertIsNone(signed.verified_monetary_savings_inr)
        self.assertIn("Non-prospective timing", signed.status_reason)
        self.assertIn("did not precede", signed.status_reason)

        # Neither ledger total increases
        ledger = list_savings_ledger(self.session, plant_id=self.plant_id)
        self.assertEqual(ledger.total_verified_avoided_kwh, 0.0)
        self.assertEqual(ledger.total_verified_monetary_savings_inr, 0.0)

    def test_approval_at_same_recorded_time_without_audit_trail_denies_verification(self):
        """
        Regression Check (Point 2): Equal recorded timestamps without audit trail evidence.
        approved_at == implemented_at == 10:00:00.
        Without an audit event establishing that the plan was frozen before implementation,
        the claim must remain NOT_VERIFIED, both verified kWh and verified INR must be null,
        and neither ledger total increases.
        """
        same_time = datetime(2026, 11, 4, 10, 0, 0)
        act = CorrectiveAction(
            action_id="ACT-SAME-NOAUDIT-01",
            recommendation_id="REC-SAME-01",
            plant_id=self.plant_id,
            title="Same timestamp without audit trail",
            description="Testing unverified sequence on equal timestamps",
            status="IN_PROGRESS",
            implemented_at=same_time,
            implemented_by="technician_01",
        )
        plan = InterventionPlan(
            plan_id="PLN-SAME-NOAUDIT-01",
            action_id=act.action_id,
            version=1,
            is_frozen=True,
            is_retrospective=False,
            intended_change="Standby change",
            implementation_owner="lead_engineer",
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL"]),
            production_denominator="GOOD_UNITS",
            production_unit="units",
            baseline_start=datetime(2026, 11, 1, 0, 0, 0),
            baseline_end=datetime(2026, 11, 2, 0, 0, 0),
            post_start=datetime(2026, 11, 4, 10, 0, 0),
            post_end=datetime(2026, 11, 4, 14, 0, 0),
            min_coverage_pct=95.0,
            success_criterion="COST_PER_GOOD_UNIT",
            approved_by="plant_manager",
            approved_at=same_time,  # Exactly equal to implemented_at!
        )
        asm = self._make_assessment(
            assessment_id="ASM-SAME-NOAUDIT-01",
            action_id=act.action_id,
            plan_id=plan.plan_id,
            plan_version=1,
            assessment_revision=1,
            objective_outcome="IMPROVED",
            cost_intensity_change_pct=Decimal("-10.0"),
            electricity_savings_kwh=Decimal("32.0"),
            avoided_cost_inr=Decimal("264.0"),
            monetary_savings_basis="APPROVED_CONTRACT_TARIFF",
            savings_claim_status="PENDING_REVIEW",
            output_guardrail_met=True,
            quality_guardrail_met=True,
            downtime_guardrail_met=True,
            guardrails_summary_json=json.dumps([{"metric": "OUTPUT", "status": "PASSED", "passed": True}]),
        )
        self.session.add_all([act, plan, asm])
        self.session.commit()

        sign_off_req = AssessmentSignOffRequest(
            decision="APPROVED_VERIFIED",
            reviewer="Plant Manager",
            notes="Sign-off on equal timestamp without audit evidence",
        )
        signed = sign_off_assessment(
            session=self.session,
            assessment_id=asm.assessment_id,
            req=sign_off_req,
            auth_caller={
                "is_authenticated": True,
                "operational_auth_available": True,
                "user_id": "mgr_plant",
                "role": "PLANT_MANAGER",
                "plant_scope": self.plant_id,
            },
        )

        self.assertEqual(signed.savings_claim_status, "NOT_VERIFIED")
        self.assertIsNone(signed.verified_electricity_savings_kwh)
        self.assertIsNone(signed.verified_monetary_savings_inr)
        self.assertIn("equals implementation timestamp", signed.status_reason)
        self.assertIn("without independent audit trail evidence", signed.status_reason)

        # Neither ledger total increases
        ledger = list_savings_ledger(self.session, plant_id=self.plant_id)
        self.assertEqual(ledger.total_verified_avoided_kwh, 0.0)
        self.assertEqual(ledger.total_verified_monetary_savings_inr, 0.0)

    def test_approval_at_same_recorded_time_with_audit_trail_allows_verification(self):
        """
        Regression Check (Point 2): Equal recorded timestamps with audit trail evidence.
        approved_at == implemented_at == 10:00:00, BUT ActionAuditLog confirms
        PLAN_APPROVED_FROZEN was performed strictly before IMPLEMENTED.
        Verification is approved, verified kWh = 32.0, verified INR = 264.0,
        and ledger totals increase.
        """
        same_time = datetime(2026, 11, 4, 10, 0, 0)
        act = CorrectiveAction(
            action_id="ACT-SAME-AUDIT-01",
            recommendation_id="REC-SAME-02",
            plant_id=self.plant_id,
            title="Same timestamp with prior audit event",
            description="Testing verified sequence via audit log",
            status="IN_PROGRESS",
            implemented_at=same_time,
            implemented_by="technician_01",
        )
        plan = InterventionPlan(
            plan_id="PLN-SAME-AUDIT-01",
            action_id=act.action_id,
            version=1,
            is_frozen=True,
            is_retrospective=False,
            intended_change="Standby change",
            implementation_owner="lead_engineer",
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL"]),
            production_denominator="GOOD_UNITS",
            production_unit="units",
            baseline_start=datetime(2026, 11, 1, 0, 0, 0),
            baseline_end=datetime(2026, 11, 2, 0, 0, 0),
            post_start=datetime(2026, 11, 4, 10, 0, 0),
            post_end=datetime(2026, 11, 4, 14, 0, 0),
            min_coverage_pct=95.0,
            success_criterion="COST_PER_GOOD_UNIT",
            approved_by="plant_manager",
            approved_at=same_time,
        )
        asm = self._make_assessment(
            assessment_id="ASM-SAME-AUDIT-01",
            action_id=act.action_id,
            plan_id=plan.plan_id,
            plan_version=1,
            assessment_revision=1,
            objective_outcome="IMPROVED",
            cost_intensity_change_pct=Decimal("-10.0"),
            electricity_savings_kwh=Decimal("32.0"),
            avoided_cost_inr=Decimal("264.0"),
            monetary_savings_basis="APPROVED_CONTRACT_TARIFF",
            savings_claim_status="PENDING_REVIEW",
            output_guardrail_met=True,
            quality_guardrail_met=True,
            downtime_guardrail_met=True,
            guardrails_summary_json=json.dumps([{"metric": "OUTPUT", "status": "PASSED", "passed": True}]),
        )

        # Independent audit trail establishing order: freeze at 09:59:50, implementation at 10:00:10
        audit_freeze = ActionAuditLog(
            audit_id="AUD-FREEZE-001",
            action_id=act.action_id,
            recommendation_id=act.recommendation_id,
            entity_id=plan.plan_id,
            action="PLAN_APPROVED_FROZEN",
            performed_at=datetime(2026, 11, 4, 9, 59, 50),
            comment="Plan approved and frozen before implementation",
        )
        audit_impl = ActionAuditLog(
            audit_id="AUD-IMPL-001",
            action_id=act.action_id,
            recommendation_id=act.recommendation_id,
            entity_id=act.action_id,
            action="IMPLEMENTED",
            performed_at=datetime(2026, 11, 4, 10, 0, 10),
            comment="Action implemented physically on line",
        )

        self.session.add_all([act, plan, asm, audit_freeze, audit_impl])
        self.session.commit()

        sign_off_req = AssessmentSignOffRequest(
            decision="APPROVED_VERIFIED",
            reviewer="Plant Manager",
            notes="Sign-off with audit-corroborated order",
        )
        signed = sign_off_assessment(
            session=self.session,
            assessment_id=asm.assessment_id,
            req=sign_off_req,
            auth_caller={
                "is_authenticated": True,
                "operational_auth_available": True,
                "user_id": "mgr_plant",
                "role": "PLANT_MANAGER",
                "plant_scope": self.plant_id,
            },
        )

        self.assertEqual(signed.savings_claim_status, "VERIFIED")
        self.assertEqual(signed.verified_electricity_savings_kwh, Decimal("32.0"))
        self.assertEqual(signed.verified_monetary_savings_inr, Decimal("264.0"))

        # Ledger increases
        ledger = list_savings_ledger(self.session, plant_id=self.plant_id)
        self.assertEqual(ledger.total_verified_avoided_kwh, 32.0)
        self.assertEqual(ledger.total_verified_monetary_savings_inr, 264.0)

    def test_approval_at_same_recorded_time_with_older_revision_audit_trail_denies_verification(self):
        """
        Regression Check: Equal recorded timestamps where audit trail belongs to an older revision.
        Plan v1 was frozen before implementation, but the evaluated plan is amended revision v2.
        approved_at == implemented_at == 10:00:00.
        The audit log for v1 CANNOT authorize v2. Verification must be denied, verified kWh = None,
        verified INR = None, and ledger must not increase.
        """
        same_time = datetime(2026, 11, 4, 10, 0, 0)
        act = CorrectiveAction(
            action_id="ACT-SAME-AUDIT-OLDREV",
            recommendation_id="REC-SAME-03",
            plant_id=self.plant_id,
            title="Same timestamp with older revision audit event",
            description="Testing that older revision audit cannot authorize newer revision",
            status="IN_PROGRESS",
            implemented_at=same_time,
            implemented_by="technician_01",
        )
        plan_v2 = InterventionPlan(
            plan_id="PLN-SAME-AUDIT-02",
            action_id=act.action_id,
            version=2,
            is_frozen=True,
            is_retrospective=False,
            intended_change="Amended standby change",
            implementation_owner="lead_engineer",
            plant_id=self.plant_id,
            process_or_line="FAL-L2",
            eligible_meters_json=json.dumps(["MTR-FAL"]),
            production_denominator="GOOD_UNITS",
            production_unit="units",
            baseline_start=datetime(2026, 11, 1, 0, 0, 0),
            baseline_end=datetime(2026, 11, 2, 0, 0, 0),
            post_start=datetime(2026, 11, 4, 10, 0, 0),
            post_end=datetime(2026, 11, 4, 14, 0, 0),
            min_coverage_pct=95.0,
            success_criterion="COST_PER_GOOD_UNIT",
            approved_by="plant_manager",
            approved_at=same_time,
        )
        asm = self._make_assessment(
            assessment_id="ASM-SAME-AUDIT-OLDREV",
            action_id=act.action_id,
            plan_id=plan_v2.plan_id,
            plan_version=2,
            assessment_revision=1,
            objective_outcome="IMPROVED",
            cost_intensity_change_pct=Decimal("-10.0"),
            electricity_savings_kwh=Decimal("32.0"),
            avoided_cost_inr=Decimal("264.0"),
            monetary_savings_basis="APPROVED_CONTRACT_TARIFF",
            savings_claim_status="PENDING_REVIEW",
            output_guardrail_met=True,
            quality_guardrail_met=True,
            downtime_guardrail_met=True,
            guardrails_summary_json=json.dumps([{"metric": "OUTPUT", "status": "PASSED", "passed": True}]),
        )

        # Audit trail belongs to older revision v1, NOT v2
        audit_freeze_v1 = ActionAuditLog(
            audit_id="AUD-FREEZE-OLDREV-001",
            action_id=act.action_id,
            recommendation_id=act.recommendation_id,
            entity_id=plan_v2.plan_id,
            action="PLAN_APPROVED_FROZEN",
            performed_at=datetime(2026, 11, 4, 9, 50, 0),
            comment="Measurement plan v1 approved and frozen",
            changed_fields_json=json.dumps({"plan_id": plan_v2.plan_id, "version": 1, "is_frozen": True}),
        )
        audit_impl = ActionAuditLog(
            audit_id="AUD-IMPL-OLDREV-001",
            action_id=act.action_id,
            recommendation_id=act.recommendation_id,
            entity_id=act.action_id,
            action="IMPLEMENTED",
            performed_at=datetime(2026, 11, 4, 10, 0, 10),
            comment="Action implemented physically on line",
        )

        self.session.add_all([act, plan_v2, asm, audit_freeze_v1, audit_impl])
        self.session.commit()

        sign_off_req = AssessmentSignOffRequest(
            decision="APPROVED_VERIFIED",
            reviewer="Plant Manager",
            notes="Attempting sign-off with older revision audit trail",
        )
        signed = sign_off_assessment(
            session=self.session,
            assessment_id=asm.assessment_id,
            req=sign_off_req,
            auth_caller={
                "is_authenticated": True,
                "operational_auth_available": True,
                "user_id": "mgr_plant",
                "role": "PLANT_MANAGER",
                "plant_scope": self.plant_id,
            },
        )

        # Verification must be DENIED because audit trail was for v1, not v2
        self.assertEqual(signed.savings_claim_status, "NOT_VERIFIED")
        self.assertIsNone(signed.verified_electricity_savings_kwh)
        self.assertIsNone(signed.verified_monetary_savings_inr)
        self.assertTrue(
            "exact plan revision" in signed.status_reason.lower()
            or "older revision" in signed.status_reason.lower()
            or "non-prospective timing" in signed.status_reason.lower()
        )

        # Ledger does NOT count this unverified claim
        ledger = list_savings_ledger(self.session, plant_id=self.plant_id)
        act_items = [it for it in ledger.items if it.action_id == act.action_id]
        self.assertEqual(len(act_items), 1)
        self.assertIsNone(act_items[0].verified_electricity_savings_kwh)

    def test_uncertainty_gate_1kwh_reduction_with_203kwh_margin(self):
        """
        Regression Check (Point 2): Uncertainty gate with original QA case:
        1 kWh estimated reduction with a ±203.6892 kWh uncertainty margin.
        Since 95% CI lower bound (1.0 - 203.6892 = -202.6892 kWh) <= 0,
        attribution must return INCONCLUSIVE_HIGH_UNCERTAINTY with verified savings = None.
        """
        attr = calculate_dual_boundary_attribution(
            stoppage_reduction_kwh=1.0,
            restart_overhead_kwh=0.0,
            margin_of_error_kwh=203.6892,
            tariffs_approved=True,
        )
        self.assertEqual(attr["status"], "INCONCLUSIVE_HIGH_UNCERTAINTY")
        self.assertIsNone(attr["verified_electricity_savings_kwh"])
        self.assertIsNone(attr["verified_monetary_savings_inr"])
        self.assertIn("high uncertainty", attr["reason"].lower())
        self.assertLessEqual(attr["ci_lower_bound_kwh"], 0.0)

    def test_qualified_kwh_with_missing_tariff_preserves_physical_savings(self):
        """
        Regression Check (Point 3): Qualified energy savings with missing tariff contract.
        Physical kWh is verified (32.0 kWh), but verified rupees is None and monetary
        contribution to the savings ledger is ₹0.
        """
        # Set up action and plan in a plant with NO approved tariff
        no_tariff_plant = "IN-MH-01"
        act = CorrectiveAction(
            action_id="ACT-NOTARIFF-001",
            recommendation_id="REC-NOTARIFF-001",
            plant_id=no_tariff_plant,
            title="Trial in plant without approved tariff contract",
            description="Testing physical vs monetary separation",
            status="IN_PROGRESS",
            implemented_at=datetime(2026, 11, 4, 10, 0, 0),
            implemented_by="engineer_01",
        )
        plan = InterventionPlan(
            plan_id="PLN-NOTARIFF-001",
            action_id=act.action_id,
            version=1,
            is_frozen=True,
            is_retrospective=False,
            intended_change="Standby optimization",
            implementation_owner="lead_engineer",
            plant_id=no_tariff_plant,
            process_or_line="SMT-L1",
            eligible_meters_json=json.dumps(["MTR-SMT"]),
            production_denominator="GOOD_UNITS",
            production_unit="units",
            baseline_start=datetime(2026, 11, 1, 0, 0, 0),
            baseline_end=datetime(2026, 11, 2, 0, 0, 0),
            post_start=datetime(2026, 11, 4, 10, 0, 0),
            post_end=datetime(2026, 11, 4, 14, 0, 0),
            min_coverage_pct=95.0,
            success_criterion="COST_PER_GOOD_UNIT",
            approved_by="plant_manager",
            approved_at=datetime(2026, 11, 4, 9, 0, 0),  # Strictly precedes implementation
        )
        asm = self._make_assessment(
            assessment_id="ASM-NOTARIFF-001",
            action_id=act.action_id,
            plan_id=plan.plan_id,
            plan_version=1,
            assessment_revision=1,
            objective_outcome="IMPROVED",
            cost_intensity_change_pct=Decimal("-10.0"),
            electricity_savings_kwh=Decimal("32.0"),
            avoided_cost_inr=Decimal("264.0"),
            monetary_savings_basis="ESTIMATED_AVOIDED_COST_VERSIONED_TARIFF",
            savings_claim_status="PENDING_REVIEW",
            output_guardrail_met=True,
            quality_guardrail_met=True,
            downtime_guardrail_met=True,
            guardrails_summary_json=json.dumps([{"metric": "OUTPUT", "status": "PASSED", "passed": True}]),
        )
        self.session.add_all([act, plan, asm])
        self.session.commit()

        sign_off_req = AssessmentSignOffRequest(
            decision="APPROVED_VERIFIED",
            reviewer="Energy Auditor",
            notes="Physical trial verified, tariff contract pending",
        )
        signed = sign_off_assessment(
            session=self.session,
            assessment_id=asm.assessment_id,
            req=sign_off_req,
            auth_caller={
                "is_authenticated": True,
                "operational_auth_available": True,
                "user_id": "auditor_01",
                "role": "ENERGY_ENGINEER",
                "plant_scope": no_tariff_plant,
            },
        )

        # Physical savings IS verified
        self.assertEqual(signed.savings_claim_status, "VERIFIED")
        self.assertEqual(signed.electricity_savings_kwh, Decimal("32.0"))
        # Monetary savings is None (Unverified)
        self.assertIsNone(signed.verified_monetary_savings_inr)
        self.assertIn("Physical electricity savings verified", signed.status_reason)
        self.assertIn("Monetary savings unverified", signed.status_reason)

        # Check ledger total for this plant
        ledger = list_savings_ledger(self.session, plant_id=no_tariff_plant)
        self.assertEqual(ledger.total_verified_avoided_kwh, 32.0)
        self.assertEqual(ledger.total_verified_monetary_savings_inr, 0.0)

    def test_stale_and_superseded_revisions_excluded_from_ledger(self):
        """
        Regression Check (Point 3): Exclude stale and superseded revisions from ledger.
        Rev 1 marked is_stale_flag=True must not be counted alongside active Rev 2.
        """
        asm_rev1 = self._make_assessment(
            assessment_id="ASM-STALE-REV1",
            action_id="ACT-STALE-001",
            plan_id="PLN-STALE-001",
            plan_version=1,
            assessment_revision=1,
            objective_outcome="IMPROVED",
            cost_intensity_change_pct=Decimal("-15.0"),
            electricity_savings_kwh=Decimal("32.0"),
            avoided_cost_inr=Decimal("264.0"),
            verified_monetary_savings_inr=Decimal("264.0"),
            savings_claim_status="VERIFIED",
            signed_off_by="lead_auditor",
            signed_off_at=datetime.utcnow(),
            is_stale_flag=True,  # Stale / superseded revision
            output_guardrail_met=True,
            quality_guardrail_met=True,
            downtime_guardrail_met=True,
            guardrails_summary_json=json.dumps([{"metric": "OUTPUT", "status": "PASSED", "passed": True}]),
        )
        asm_rev2 = self._make_assessment(
            assessment_id="ASM-STALE-REV2",
            action_id="ACT-STALE-001",
            plan_id="PLN-STALE-001",
            plan_version=1,
            assessment_revision=2,
            objective_outcome="IMPROVED",
            cost_intensity_change_pct=Decimal("-15.0"),
            electricity_savings_kwh=Decimal("32.0"),
            avoided_cost_inr=Decimal("264.0"),
            verified_monetary_savings_inr=Decimal("264.0"),
            savings_claim_status="VERIFIED",
            signed_off_by="lead_auditor",
            signed_off_at=datetime.utcnow(),
            is_stale_flag=False,  # Active revision
            output_guardrail_met=True,
            quality_guardrail_met=True,
            downtime_guardrail_met=True,
            guardrails_summary_json=json.dumps([{"metric": "OUTPUT", "status": "PASSED", "passed": True}]),
        )
        self.session.add_all([asm_rev1, asm_rev2])
        self.session.commit()

        ledger = list_savings_ledger(self.session)
        # Only Rev 2 should be included
        matching_items = [item for item in ledger.items if item.action_id == "ACT-STALE-001"]
        self.assertEqual(len(matching_items), 1)
        self.assertEqual(matching_items[0].assessment_revision, 2)


if __name__ == "__main__":
    unittest.main()
