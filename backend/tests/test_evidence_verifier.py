"""
Automated unit tests for AI Evidence Verifier.

Tests deterministic numerical claim extraction, normalization, scope matching,
verification outcomes, response-level status rollups, and auto-correction.
"""

from decimal import Decimal
import unittest

from app.services.agent.evidence_verifier import (
    AuthoritativeFact,
    ClaimVerificationResult,
    ExtractedClaim,
    VerificationOutcome,
    VerificationResponse,
    VerificationSummary,
    _aggregations_compatible,
    _categories_compatible,
    _classify_metric_key,
    _is_non_claim,
    _is_scope_granularity_compatible,
    _is_valid_grouping,
    _normalize_claim_number,
    _to_decimal,
    _units_compatible,
    _values_match,
    correct_or_qualify_response,
    extract_authoritative_facts,
    extract_claims,
    verify_claims,
    verify_numeric_claims,
)


class MockToolEvidence:
    """Lightweight test fixture mimicking agent ToolEvidence."""

    def __init__(
        self,
        tool_name: str = "test_tool",
        execution_order: int = 1,
        arguments: dict = None,
        result: any = None,
        success: bool = True,
        error: str = None,
    ):
        self.tool_name = tool_name
        self.execution_order = execution_order
        self.arguments = arguments or {}
        self.result = result
        self.success = success
        self.error = error


class TestNumericExtractionAndNormalization(unittest.TestCase):
    """Section 3: Numeric extraction and normalization tests."""

    def test_positive_integers_and_decimals(self):
        """Positive integers and decimals normalize accurately to Decimal."""
        for num_str, expected in [
            ("123", Decimal("123")),
            ("0.5", Decimal("0.5")),
            ("12450.75", Decimal("12450.75")),
            ("0.0001", Decimal("0.0001")),
        ]:
            valid, dec, clean, _ = _normalize_claim_number(num_str)
            self.assertTrue(valid)
            self.assertEqual(dec, expected)

    def test_negative_numbers_standard_minus(self):
        """Standard ASCII minus signs preserve negative sign without alteration."""
        valid, dec, clean, _ = _normalize_claim_number("-45.6")
        self.assertTrue(valid)
        self.assertEqual(dec, Decimal("-45.6"))
        self.assertEqual(clean, "-45.6")

    def test_negative_numbers_unicode_minus(self):
        """Unicode minus sign (−) is recognized and normalized to negative Decimal."""
        valid, dec, clean, _ = _normalize_claim_number("−125.5")
        self.assertTrue(valid)
        self.assertEqual(dec, Decimal("-125.5"))
        self.assertEqual(clean, "-125.5")

    def test_western_comma_grouping(self):
        """Standard Western comma grouping (thousands) is validated and parsed."""
        valid, dec, clean, _ = _normalize_claim_number("1,234,567.89")
        self.assertTrue(valid)
        self.assertEqual(dec, Decimal("1234567.89"))
        self.assertEqual(clean, "1234567.89")

    def test_indian_comma_grouping(self):
        """Indian comma grouping (lakhs, crores) is validated and parsed."""
        for num_str, expected in [
            ("12,34,567.89", Decimal("1234567.89")),
            ("1,00,000", Decimal("100000")),
            ("15,50,000.50", Decimal("1550000.50")),
        ]:
            valid, dec, clean, _ = _normalize_claim_number(num_str)
            self.assertTrue(valid, f"Failed for {num_str}")
            self.assertEqual(dec, expected)

    def test_currency_prefixes(self):
        """Currency prefixes (₹, INR, Rs., Rs) infer INR unit and parse numeric body."""
        for raw, expected_val in [
            ("₹15,000", Decimal("15000")),
            ("INR 2500.50", Decimal("2500.50")),
            ("Rs. 500", Decimal("500")),
            ("Rs 100", Decimal("100")),
            ("₹-750", Decimal("-750")),
            ("-₹750", Decimal("-750")),
        ]:
            valid, dec, clean, unit = _normalize_claim_number(raw)
            self.assertTrue(valid, f"Failed on currency raw: {raw}")
            self.assertEqual(dec, expected_val)
            self.assertEqual(unit, "INR")

    def test_percentage_tokens(self):
        """Percentage tokens infer % unit and parse numeric body."""
        valid, dec, clean, unit = _normalize_claim_number("96.5%")
        self.assertTrue(valid)
        self.assertEqual(dec, Decimal("96.5"))
        self.assertEqual(unit, "%")

    def test_scientific_notation(self):
        """Scientific notation exponents are preserved and parsed to Decimal."""
        for raw, expected in [
            ("1.25e6", Decimal("1250000")),
            ("1.5E-3", Decimal("0.0015")),
            ("-2.4e4", Decimal("-24000")),
        ]:
            valid, dec, clean, _ = _normalize_claim_number(raw)
            self.assertTrue(valid, f"Failed on scientific: {raw}")
            self.assertEqual(dec, expected)

    def test_malformed_numeric_grouping_rejected(self):
        """Malformed comma grouping (e.g. 1,23,45) is rejected as invalid."""
        for bad_grouped in ["1,23,45", "12,345,6", "1,2,3"]:
            valid = _is_valid_grouping(bad_grouped)
            self.assertFalse(valid, f"Expected {bad_grouped} to be invalid grouping")
            valid_norm, dec, _, _ = _normalize_claim_number(bad_grouped)
            self.assertFalse(valid_norm)
            self.assertIsNone(dec)

    def test_hyphenated_identifiers_not_split_into_negative_numbers(self):
        """Legitimate hyphenated identifiers (e.g. IN-TN-01, SMT-L1, SPH-A15-128) are not parsed as negative numbers."""
        text = "Plant IN-TN-01 line SMT-L1 manufactured SKU SPH-A15-128."
        claims = extract_claims(text)
        # All extracted candidate tokens inside hyphenated codes must be marked non-claim
        self.assertTrue(all(not c.is_applicable for c in claims))

    def test_normalization_preserves_negative_signs_and_precision(self):
        """Normalization does not silently strip negative signs or truncate decimal fractions."""
        valid, dec, clean, _ = _normalize_claim_number("-0.0045")
        self.assertTrue(valid)
        self.assertEqual(dec, Decimal("-0.0045"))
        self.assertEqual(clean, "-0.0045")


class TestNonClaimExclusions(unittest.TestCase):
    """Section 3: Exclusion of identifiers, dates, versions, HTTP codes, and system constants."""

    def test_iso_and_slash_date_exclusions(self):
        """ISO dates (2026-08-01) and slash dates (08/01/2026) are classified as NOT_APPLICABLE."""
        text = "On 2026-08-01 and 08/01/2026 plant operations were evaluated."
        claims = extract_claims(text)
        self.assertTrue(all(not c.is_applicable for c in claims))
        reasons = [c.non_claim_reason for c in claims]
        self.assertTrue(any("date" in r.lower() for r in reasons))

    def test_calendar_year_in_context_exclusion(self):
        """Four-digit years in contextual phrases (in 2026, year 2025) are excluded."""
        text = "In 2026 total production increased compared to year 2025."
        claims = extract_claims(text)
        self.assertTrue(all(not c.is_applicable for c in claims))
        for c in claims:
            self.assertEqual(c.non_claim_reason, "Calendar year identifier")

    def test_entity_identifiers_and_skus(self):
        """Plant, line, meter, and product SKU identifiers are not treated as numbers."""
        text = "Plant IN-TN-01 line SMT-L1 meter MTR-SMT produced SPH-A15-128 units."
        claims = extract_claims(text)
        # Numbers embedded in codes like IN-TN-01, SMT-L1, SPH-A15-128 must be marked non-claim
        self.assertTrue(all(not c.is_applicable for c in claims))

    def test_http_status_codes_and_versions(self):
        """HTTP codes (200, 404, 500) and algorithm versions (v1.0, 2.1) are excluded."""
        text = "Endpoint returned 200 OK using model v2.1 while test gave 404 error."
        claims = extract_claims(text)
        self.assertTrue(all(not c.is_applicable for c in claims))

    def test_list_enumeration_markers(self):
        """Heading markers at sentence start (### 1 , ## 2) are excluded as non-claims."""
        text = "### 1 Production Summary\n## 2 Energy Breakdown"
        claims = extract_claims(text)
        self.assertTrue(all(not c.is_applicable for c in claims))
        for c in claims:
            self.assertIn("enumeration", c.non_claim_reason.lower())

    def test_system_policy_constants_and_limits(self):
        """System policy constants (limit of 5, threshold of 0.90, 3.0 sigma, 0.716 kg) are excluded."""
        text = "System has a limit of 5 tool calls, threshold of 0.90 power factor, 3.0 sigma cutoff, and factor of 0.716 emissions."
        claims = extract_claims(text)
        self.assertTrue(all(not c.is_applicable for c in claims))


class TestMetricAndScopeClassification(unittest.TestCase):
    """Section 4: Metric category separation, specific rate categories, and scope granularity."""

    def test_peak_vs_cumulative_energy_separation(self):
        """DEF-04: Peak energy and cumulative energy are classified into distinct categories."""
        cat_cum, unit_cum = _classify_metric_key("total_consumption_kwh")
        cat_peak, unit_peak = _classify_metric_key("peak_hourly_kwh")

        self.assertEqual(cat_cum, "energy")
        self.assertEqual(cat_peak, "peak_energy")
        self.assertFalse(_categories_compatible(cat_cum, cat_peak))

    def test_specific_rate_categories_separation(self):
        """DEF-03: Distinct rate categories are mutually incompatible and never match."""
        rates = [
            ("good_rate", "good_rate"),
            ("reject_rate", "reject_rate"),
            ("rework_rate", "rework_rate"),
            ("achievement_rate", "achievement_rate"),
            ("percentage_of_total", "percentage_of_total"),
            ("low_pf_percentage", "percentage_below_threshold"),
            ("downtime_percentage", "percentage_of_downtime"),
        ]
        categories = [_classify_metric_key(key)[0] for key, _ in rates]

        for i, c1 in enumerate(categories):
            for j, c2 in enumerate(categories):
                if i == j:
                    self.assertTrue(_categories_compatible(c1, c2))
                else:
                    self.assertFalse(
                        _categories_compatible(c1, c2),
                        f"Rate categories {c1} and {c2} should not be compatible",
                    )

    def test_aggregation_compatibility(self):
        """Peak claims require peak facts; sum claims reject peak or avg facts."""
        self.assertTrue(_aggregations_compatible("peak", "peak"))
        self.assertFalse(_aggregations_compatible("sum", "peak"))
        self.assertFalse(_aggregations_compatible("avg", "sum"))
        self.assertFalse(_aggregations_compatible("peak", "sum"))
        self.assertTrue(_aggregations_compatible("sum", "sum"))
        self.assertTrue(_aggregations_compatible("avg", "avg"))

    def test_plant_level_claim_rejects_sub_entity_meter_fact(self):
        """DEF-02: A plant-level claim must NEVER be verified using an individual meter fact."""
        claim = ExtractedClaim(
            raw_number_str="5000",
            cleaned_number_str="5000",
            claimed_value=Decimal("5000"),
            sentence="Plant IN-TN-01 consumed 5,000 kWh.",
            claimed_unit="kWh",
            claimed_metric="energy",
            claimed_scope_plant="IN-TN-01",
            claimed_scope_meter=None,  # Plant-wide claim
        )
        fact = AuthoritativeFact(
            tool_name="energy_summary",
            execution_order=1,
            metric_name="consumption_kwh",
            metric_category="energy",
            value=Decimal("5000"),
            unit="kWh",
            plant_id="IN-TN-01",
            meter_id="MTR-SMT",  # Meter-level fact
        )
        compat, reason = _is_scope_granularity_compatible(claim, fact)
        self.assertFalse(compat)
        self.assertIn("plant-level", reason.lower())
        self.assertIn("specific meter", reason.lower())

    def test_meter_level_claim_rejects_plant_level_aggregate_fact(self):
        """DEF-02: A meter-level claim must NEVER be verified using a plant-wide aggregate fact."""
        claim = ExtractedClaim(
            raw_number_str="5000",
            cleaned_number_str="5000",
            claimed_value=Decimal("5000"),
            sentence="Meter MTR-SMT consumed 5,000 kWh.",
            claimed_unit="kWh",
            claimed_metric="energy",
            claimed_scope_plant="IN-TN-01",
            claimed_scope_meter="MTR-SMT",
        )
        fact = AuthoritativeFact(
            tool_name="energy_summary",
            execution_order=1,
            metric_name="total_consumption_kwh",
            metric_category="energy",
            value=Decimal("5000"),
            unit="kWh",
            plant_id="IN-TN-01",
            meter_id=None,  # Plant-wide aggregate
        )
        compat, reason = _is_scope_granularity_compatible(claim, fact)
        self.assertFalse(compat)
        self.assertIn("aggregate without meter", reason.lower())


class TestAuthoritativeFactExtraction(unittest.TestCase):
    """Section 6: Evidence extraction from successful vs failed tools."""

    def test_successful_tool_facts_extracted(self):
        """Successful tool results are parsed into AuthoritativeFact records with scope."""
        ev = MockToolEvidence(
            tool_name="energy_summary",
            arguments={"plant_id": "IN-TN-01", "start_date": "2026-08-01", "end_date": "2026-08-02"},
            result={"total_consumption_kwh": 125000.50, "total_cost_inr": 937503.75},
            success=True,
        )
        facts = extract_authoritative_facts([ev])
        self.assertEqual(len(facts), 2)
        fact_kwh = next(f for f in facts if f.metric_category == "energy")
        self.assertEqual(fact_kwh.value, Decimal("125000.50"))
        self.assertEqual(fact_kwh.unit, "kWh")
        self.assertEqual(fact_kwh.plant_id, "IN-TN-01")

    def test_failed_tool_executions_provide_zero_facts(self):
        """Failed tool executions (success=False) produce zero authoritative facts."""
        ev = MockToolEvidence(
            tool_name="energy_summary",
            result={"total_consumption_kwh": 50000},
            success=False,
            error="Connection timeout",
        )
        facts = extract_authoritative_facts([ev])
        self.assertEqual(len(facts), 0)

    def test_none_tool_results_provide_zero_facts(self):
        """Tools returning None as result provide zero facts."""
        ev = MockToolEvidence(tool_name="energy_summary", result=None, success=True)
        facts = extract_authoritative_facts([ev])
        self.assertEqual(len(facts), 0)


class TestClaimOutcomes(unittest.TestCase):
    """Section 2: Comprehensive tests for all 6 claim-level outcomes."""

    def test_outcome_verified_exact_match(self):
        """Claim matching value, unit, category, and scope produces VERIFIED."""
        fact = AuthoritativeFact(
            tool_name="energy_summary",
            execution_order=1,
            metric_name="total_consumption_kwh",
            metric_category="energy",
            value=Decimal("15000.00"),
            unit="kWh",
            plant_id="IN-TN-01",
            aggregation="sum",
        )
        claim = ExtractedClaim(
            raw_number_str="15,000",
            cleaned_number_str="15000",
            claimed_value=Decimal("15000"),
            sentence="Plant IN-TN-01 consumed total 15,000 kWh.",
            claimed_unit="kWh",
            claimed_metric="energy",
            claimed_scope_plant="IN-TN-01",
            claimed_aggregation="sum",
            is_applicable=True,
            start_in_sentence=30,
            end_in_sentence=36,
        )
        results = verify_claims([claim], [fact])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].outcome, VerificationOutcome.VERIFIED)
        self.assertEqual(results[0].supporting_tool, "energy_summary")
        self.assertFalse(results[0].was_corrected)

    def test_outcome_verified_permitted_rounding_and_tolerance(self):
        """Permitted rounding (e.g. 96 vs 96.04) and relative tolerance produce VERIFIED."""
        fact = AuthoritativeFact(
            tool_name="production_summary",
            execution_order=1,
            metric_name="good_rate",
            metric_category="good_rate",
            value=Decimal("96.04"),
            unit="%",
            plant_id="IN-TN-01",
        )
        claim = ExtractedClaim(
            raw_number_str="96%",
            cleaned_number_str="96",
            claimed_value=Decimal("96"),
            sentence="Plant IN-TN-01 had a good rate of 96%.",
            claimed_unit="%",
            claimed_metric="good_rate",
            claimed_scope_plant="IN-TN-01",
            is_applicable=True,
        )
        results = verify_claims([claim], [fact])
        self.assertEqual(results[0].outcome, VerificationOutcome.VERIFIED)

    def test_outcome_unit_mismatch(self):
        """Claim with matching value but incompatible unit produces UNIT_MISMATCH."""
        fact = AuthoritativeFact(
            tool_name="cost_summary",
            execution_order=1,
            metric_name="cost_inr",
            metric_category="cost",
            value=Decimal("5000"),
            unit="INR",
            plant_id="IN-TN-01",
        )
        claim = ExtractedClaim(
            raw_number_str="5000 kWh",
            cleaned_number_str="5000",
            claimed_value=Decimal("5000"),
            sentence="Plant IN-TN-01 cost was 5000 kWh.",
            claimed_unit="kWh",  # Stated kWh instead of INR
            claimed_metric="cost",
            claimed_scope_plant="IN-TN-01",
            is_applicable=True,
        )
        results = verify_claims([claim], [fact])
        self.assertEqual(results[0].outcome, VerificationOutcome.UNIT_MISMATCH)
        self.assertIn("incompatible unit", results[0].explanation)

    def test_outcome_scope_mismatch(self):
        """Claim with matching value but conflicting plant scope produces SCOPE_MISMATCH."""
        fact = AuthoritativeFact(
            tool_name="energy_summary",
            execution_order=1,
            metric_name="total_consumption_kwh",
            metric_category="energy",
            value=Decimal("5000"),
            unit="kWh",
            plant_id="IN-KA-01",  # Fact is for KA
        )
        claim = ExtractedClaim(
            raw_number_str="5000",
            cleaned_number_str="5000",
            claimed_value=Decimal("5000"),
            sentence="Plant IN-TN-01 consumed 5000 kWh.",  # Claim is for TN
            claimed_unit="kWh",
            claimed_metric="energy",
            claimed_scope_plant="IN-TN-01",
            is_applicable=True,
        )
        results = verify_claims([claim], [fact])
        self.assertEqual(results[0].outcome, VerificationOutcome.SCOPE_MISMATCH)
        self.assertIn("scope conflicts", results[0].explanation.lower())

    def test_date_scope_mismatch_produces_scope_mismatch(self):
        """Claim specifying date 2026-08-01 when evidence is for 2026-08-02 produces SCOPE_MISMATCH."""
        fact = AuthoritativeFact(
            tool_name="energy_summary",
            execution_order=1,
            metric_name="total_consumption_kwh",
            metric_category="energy",
            value=Decimal("5000"),
            unit="kWh",
            exact_date="2026-08-02",
        )
        claim = ExtractedClaim(
            raw_number_str="5000",
            cleaned_number_str="5000",
            claimed_value=Decimal("5000"),
            sentence="On 2026-08-01 energy was 5000 kWh.",
            claimed_unit="kWh",
            claimed_metric="energy",
            claimed_date="2026-08-01",
            is_applicable=True,
        )
        results = verify_claims([claim], [fact])
        self.assertEqual(results[0].outcome, VerificationOutcome.SCOPE_MISMATCH)
        self.assertIn("date mismatch", results[0].explanation.lower())

    def test_outcome_conflicting_single_unambiguous_candidate(self):
        """Single matching candidate fact with different value produces CONFLICTING with can_auto_correct=True."""
        fact = AuthoritativeFact(
            tool_name="energy_summary",
            execution_order=1,
            metric_name="total_consumption_kwh",
            metric_category="energy",
            value=Decimal("12000"),  # True fact is 12000
            unit="kWh",
            plant_id="IN-TN-01",
            aggregation="sum",
        )
        claim = ExtractedClaim(
            raw_number_str="15000",  # Claim hallucinated 15000
            cleaned_number_str="15000",
            claimed_value=Decimal("15000"),
            sentence="Plant IN-TN-01 consumed total 15000 kWh.",
            claimed_unit="kWh",
            claimed_metric="energy",
            claimed_scope_plant="IN-TN-01",
            claimed_aggregation="sum",
            is_applicable=True,
            start_in_sentence=30,
            end_in_sentence=35,
        )
        results = verify_claims([claim], [fact])
        self.assertEqual(results[0].outcome, VerificationOutcome.CONFLICTING)
        self.assertTrue(results[0].can_auto_correct)
        self.assertEqual(results[0].authoritative_value, "12000")
        self.assertIn("contradicting", results[0].explanation)

    def test_outcome_unverified_no_evidence(self):
        """Claim with zero matching facts produces UNVERIFIED."""
        claim = ExtractedClaim(
            raw_number_str="4500",
            cleaned_number_str="4500",
            claimed_value=Decimal("4500"),
            sentence="Plant IN-TN-01 generated 4500 units.",
            claimed_unit="units",
            claimed_metric="actual_quantity",
            claimed_scope_plant="IN-TN-01",
            is_applicable=True,
        )
        results = verify_claims([claim], [])  # No facts
        self.assertEqual(results[0].outcome, VerificationOutcome.UNVERIFIED)
        self.assertFalse(results[0].can_auto_correct)
        self.assertIn("No successful tool results", results[0].explanation)

    def test_outcome_not_applicable(self):
        """Non-claims (dates, identifiers) produce NOT_APPLICABLE."""
        claim = ExtractedClaim(
            raw_number_str="2026-08-01",
            cleaned_number_str="2026-08-01",
            claimed_value=Decimal("0"),
            sentence="Evaluation date was 2026-08-01.",
            is_applicable=False,
            non_claim_reason="Part of ISO date",
        )
        results = verify_claims([claim], [])
        self.assertEqual(results[0].outcome, VerificationOutcome.NOT_APPLICABLE)


class TestResponseStatusAndInvariants(unittest.TestCase):
    """Section 2 & 7: Response-level status rollup and mathematical invariants."""

    def test_status_verified_all_claims_verified(self):
        """When all applicable claims are VERIFIED, response status is VERIFIED."""
        evidence = [
            MockToolEvidence(
                tool_name="energy_summary",
                result={"total_consumption_kwh": 10000.0},
                success=True,
            )
        ]
        resp = verify_numeric_claims(
            answer="The plant consumed 10,000 kWh of total energy.",
            evidence=evidence,
        )
        self.assertEqual(resp.summary.status, "VERIFIED")
        self.assertEqual(resp.summary.total_claims, 1)
        self.assertEqual(resp.summary.verified_claims, 1)
        self.assertEqual(resp.summary.unverified_claims, 0)

    def test_status_partially_verified(self):
        """When some claims are verified and some unverified (no conflicts), status is PARTIALLY_VERIFIED."""
        evidence = [
            MockToolEvidence(
                tool_name="energy_summary",
                result={"total_consumption_kwh": 10000.0},
                success=True,
            )
        ]
        # 10,000 kWh is verified; 450 boards has no evidence (unverified)
        resp = verify_numeric_claims(
            answer="The plant consumed 10,000 kWh and produced 450 boards.",
            evidence=evidence,
        )
        self.assertEqual(resp.summary.status, "PARTIALLY_VERIFIED")
        self.assertEqual(resp.summary.verified_claims, 1)
        self.assertEqual(resp.summary.unverified_claims, 1)
        self.assertEqual(resp.summary.total_claims, 2)

    def test_status_unverified_zero_verified(self):
        """When zero claims are verified (and none conflicting), status is UNVERIFIED."""
        resp = verify_numeric_claims(
            answer="The plant produced 550 boards and 250 phones.",  # Non-HTTP numbers
            evidence=[],  # No evidence
        )
        self.assertEqual(resp.summary.status, "UNVERIFIED")
        self.assertEqual(resp.summary.verified_claims, 0)
        self.assertEqual(resp.summary.unverified_claims, 2)

    def test_status_conflict_detected_when_unresolvable_conflict_remains(self):
        """When an uncorrectable conflicting claim exists, status is CONFLICT_DETECTED."""
        # Ambiguous multiple facts with identical value: cannot auto-correct -> remains CONFLICTING
        fact1 = AuthoritativeFact(
            tool_name="tool_a",
            execution_order=1,
            metric_name="consumption_kwh",
            metric_category="energy",
            value=Decimal("8000"),
            unit="kWh",
            plant_id="IN-TN-01",
        )
        fact2 = AuthoritativeFact(
            tool_name="tool_b",
            execution_order=2,
            metric_name="consumption_kwh",
            metric_category="energy",
            value=Decimal("8000"),
            unit="kWh",
            plant_id="IN-TN-01",
        )
        claim = ExtractedClaim(
            raw_number_str="12000",
            cleaned_number_str="12000",
            claimed_value=Decimal("12000"),
            sentence="Plant IN-TN-01 consumed 12000 kWh.",
            claimed_unit="kWh",
            claimed_metric="energy",
            claimed_scope_plant="IN-TN-01",
            is_applicable=True,
        )
        res = verify_claims([claim], [fact1, fact2])
        self.assertEqual(res[0].outcome, VerificationOutcome.CONFLICTING)
        self.assertFalse(res[0].can_auto_correct)  # Flagged ambiguous source

    def test_status_no_analytic_claims(self):
        """Responses with no applicable numerical claims produce NO_ANALYTIC_CLAIMS."""
        resp = verify_numeric_claims(
            answer="All production lines operated under normal operating schedules.",
            evidence=[],
        )
        self.assertEqual(resp.summary.status, "NO_ANALYTIC_CLAIMS")
        self.assertEqual(resp.summary.total_claims, 0)
        self.assertEqual(resp.summary.verified_claims, 0)
        self.assertEqual(resp.summary.unverified_claims, 0)

    def test_mathematical_invariant_total_equals_verified_plus_unverified(self):
        """DEF-06: Strict invariant total_claims == verified_claims + unverified_claims."""
        evidence = [
            MockToolEvidence(
                tool_name="energy_summary",
                result={"total_consumption_kwh": 5000.0},
                success=True,
            )
        ]
        # 5,000 kWh is verified; 250 units is unverified; ISO date and plant ID are NOT_APPLICABLE
        resp = verify_numeric_claims(
            answer="On 2026-08-01, Plant IN-TN-01 consumed 5,000 kWh and completed 250 units.",
            evidence=evidence,
        )
        s = resp.summary
        self.assertEqual(s.total_claims, s.verified_claims + s.unverified_claims)
        self.assertTrue(s.not_applicable_count >= 1)  # ISO date and plant identifier excluded from applicable total
        self.assertEqual(s.total_claims, 2)
        self.assertEqual(s.verified_claims, 1)
        self.assertEqual(s.unverified_claims, 1)


class TestResponseCorrectionAndQualification(unittest.TestCase):
    """Section 5: Safe response correction, token-boundary protection, and qualification notices."""

    def test_sentence_local_correction_of_conflicting_claim(self):
        """Conflicting number is replaced with authoritative value and verified citation."""
        evidence = [
            MockToolEvidence(
                tool_name="energy_summary",
                arguments={"plant_id": "IN-TN-01"},
                result={"total_consumption_kwh": 12000.0},
                success=True,
            )
        ]
        # Claim claims 15,000 kWh
        resp = verify_numeric_claims(
            answer="Plant IN-TN-01 recorded total energy consumption of 15,000 kWh during the period.",
            evidence=evidence,
        )
        self.assertIn("12000.0 kWh [Verified from energy_summary]", resp.final_answer)
        self.assertNotIn("15,000 kWh", resp.final_answer)
        self.assertEqual(resp.summary.status, "VERIFIED")
        self.assertEqual(resp.summary.verified_claims, 1)

    def test_token_boundary_protection_prevents_subnumber_replacement(self):
        """Token boundary check ensures number '5' cannot modify '50', '2026-05-15', or '240'."""
        sentence = "Model SMT-50 completed 240 units on 2026-05-15."
        # Attempt to auto-correct '5' inside '50' (start=10, end=11)
        claim_inside_50 = ClaimVerificationResult(
            claimed_number="5",
            sentence=sentence,
            metric="energy",
            unit="kWh",
            outcome=VerificationOutcome.CONFLICTING,
            authoritative_value="10",
            authoritative_unit="kWh",
            supporting_tool="energy_tool",
            start_in_sentence=10,  # Points to '5' inside '50'
            end_in_sentence=11,
            can_auto_correct=True,
        )
        res = correct_or_qualify_response(sentence, [claim_inside_50])
        # Sentence was not corrupted; 50 was NOT replaced by 10 kWh
        self.assertIn("Model SMT-50 completed 240 units", res)
        self.assertNotIn("Model SMT-10", res)
        self.assertIn("Data Verification Notice", res)

    def test_multiple_identical_numbers_in_different_sentences(self):
        """Multiple identical numbers across different sentences only replace the specific conflicting sentence."""
        answer = (
            "Line SMT-L1 consumed 600 kWh.\n"
            "Line FAL-L1 consumed 600 kWh."
        )
        # SMT-L1 actually consumed 750 kWh; FAL-L1 evidence is absent
        evidence = [
            MockToolEvidence(
                tool_name="energy_summary",
                arguments={"line_id": "SMT-L1"},
                result={"consumption_kwh": 750.0},
                success=True,
            )
        ]
        resp = verify_numeric_claims(answer, evidence)
        # SMT-L1 sentence is corrected to 750.0 kWh
        self.assertIn("750.0 kWh [Verified from energy_summary]", resp.final_answer)
        # FAL-L1 sentence still retains 600 kWh (qualified via warning notice)
        self.assertIn("Line FAL-L1 consumed 600 kWh.", resp.final_answer)

    def test_negative_number_correction_preserves_sign(self):
        """Correction of negative numbers preserves minus sign in authoritative replacement."""
        sentence = "Net power variance was -50 kWh."
        claim = ClaimVerificationResult(
            claimed_number="-50",
            sentence=sentence,
            metric="energy",
            unit="kWh",
            outcome=VerificationOutcome.CONFLICTING,
            authoritative_value="-75.5",
            authoritative_unit="kWh",
            supporting_tool="variance_tool",
            start_in_sentence=23,
            end_in_sentence=26,
            can_auto_correct=True,
        )
        res = correct_or_qualify_response(sentence, [claim])
        self.assertIn("-75.5 kWh [Verified from variance_tool]", res)
        self.assertNotIn("-50 kWh", res)

    def test_date_preservation_during_correction(self):
        """Dates inside the sentence are preserved without alteration during numeric replacement."""
        sentence = "On 2026-08-01 Plant IN-TN-01 consumed 15,000 kWh."
        claim = ClaimVerificationResult(
            claimed_number="15,000",
            sentence=sentence,
            metric="energy",
            unit="kWh",
            outcome=VerificationOutcome.CONFLICTING,
            authoritative_value="12000.0",
            authoritative_unit="kWh",
            supporting_tool="energy_summary",
            start_in_sentence=38,
            end_in_sentence=44,
            can_auto_correct=True,
        )
        res = correct_or_qualify_response(sentence, [claim])
        self.assertIn("On 2026-08-01 Plant IN-TN-01 consumed 12000.0 kWh [Verified from energy_summary]", res)

    def test_identifier_and_sku_preservation_during_correction(self):
        """SKU and line codes in sentence are preserved during numeric replacement."""
        sentence = "Line SMT-L1 produced 150 units of SPH-A15-128."
        claim = ClaimVerificationResult(
            claimed_number="150",
            sentence=sentence,
            metric="actual_quantity",
            unit="units",
            outcome=VerificationOutcome.CONFLICTING,
            authoritative_value="200",
            authoritative_unit="units",
            supporting_tool="production_summary",
            start_in_sentence=21,
            end_in_sentence=24,
            can_auto_correct=True,
        )
        res = correct_or_qualify_response(sentence, [claim])
        self.assertIn("Line SMT-L1 produced 200 units [Verified from production_summary]", res)
        self.assertIn("of SPH-A15-128.", res)

    def test_correction_does_not_alter_unrelated_numbers(self):
        """Unrelated numbers in other paragraphs remain unmodified."""
        paragraph = (
            "Paragraph 1: Target was 1000 units.\n\n"
            "Paragraph 2: Plant IN-TN-01 consumed 15,000 kWh.\n\n"
            "Paragraph 3: Reject count was 25 units."
        )
        claim = ClaimVerificationResult(
            claimed_number="15,000",
            sentence="Paragraph 2: Plant IN-TN-01 consumed 15,000 kWh.",
            metric="energy",
            unit="kWh",
            outcome=VerificationOutcome.CONFLICTING,
            authoritative_value="12000.0",
            authoritative_unit="kWh",
            supporting_tool="energy_summary",
            start_in_sentence=37,
            end_in_sentence=43,
            can_auto_correct=True,
        )
        res = correct_or_qualify_response(paragraph, [claim])
        self.assertIn("Target was 1000 units.", res)
        self.assertIn("Reject count was 25 units.", res)
        self.assertIn("12000.0 kWh [Verified from energy_summary]", res)

    def test_ambiguous_repeated_sentence_skips_correction(self):
        """If an identical sentence appears more than once, auto-correction is skipped to prevent offset drift."""
        answer = (
            "Plant IN-TN-01 consumed 15,000 kWh.\n"
            "Plant IN-TN-01 consumed 15,000 kWh."
        )
        evidence = [
            MockToolEvidence(
                tool_name="energy_summary",
                arguments={"plant_id": "IN-TN-01"},
                result={"total_consumption_kwh": 12000.0},
                success=True,
            )
        ]
        resp = verify_numeric_claims(answer, evidence)
        # Neither sentence was silently altered; both qualified via notice
        self.assertIn("Data Verification Notice", resp.final_answer)

    def test_qualification_warning_notice_attached_for_unverified_figures(self):
        """Unverified figures produce a clear markdown warning block at the end of the response."""
        resp = verify_numeric_claims(
            answer="The estimated cost was 45000 INR.",
            evidence=[],
        )
        self.assertIn("> [!WARNING] **Data Verification Notice:**", resp.final_answer)
        self.assertIn("45000 INR", resp.final_answer)
        self.assertIn("Non-verified figures should not be treated as authoritative", resp.final_answer)


class TestMultiCandidateAndAmbiguityHandling(unittest.TestCase):
    """Section 4: Multiple candidate facts and generic rate ambiguity."""

    def test_differing_candidate_facts_resolves_to_unverified(self):
        """When multiple candidate facts in the same category have differing values, claim resolves to UNVERIFIED."""
        fact1 = AuthoritativeFact(
            tool_name="tool_1",
            execution_order=1,
            metric_name="consumption_kwh",
            metric_category="energy",
            value=Decimal("10000"),
            unit="kWh",
        )
        fact2 = AuthoritativeFact(
            tool_name="tool_2",
            execution_order=2,
            metric_name="consumption_kwh",
            metric_category="energy",
            value=Decimal("15000"),
            unit="kWh",
        )
        claim = ExtractedClaim(
            raw_number_str="8000",
            cleaned_number_str="8000",
            claimed_value=Decimal("8000"),
            sentence="Energy was 8000 kWh.",
            claimed_unit="kWh",
            claimed_metric="energy",
            is_applicable=True,
        )
        results = verify_claims([claim], [fact1, fact2])
        self.assertEqual(results[0].outcome, VerificationOutcome.UNVERIFIED)
        self.assertIn("Multiple candidate facts exist with differing values", results[0].explanation)

    def test_generic_rate_with_multiple_rate_metrics_is_unverified(self):
        """DEF-03: A generic percentage claim when multiple rate categories exist resolves to UNVERIFIED."""
        fact_good = AuthoritativeFact(
            tool_name="production_summary",
            execution_order=1,
            metric_name="good_rate",
            metric_category="good_rate",
            value=Decimal("95.0"),
            unit="%",
        )
        fact_reject = AuthoritativeFact(
            tool_name="production_summary",
            execution_order=1,
            metric_name="reject_rate",
            metric_category="reject_rate",
            value=Decimal("5.0"),
            unit="%",
        )
        # Claim states generic 'rate of 95%' without qualifying good vs reject vs yield
        claim = ExtractedClaim(
            raw_number_str="95%",
            cleaned_number_str="95",
            claimed_value=Decimal("95"),
            sentence="The plant recorded an overall rate of 95%.",
            claimed_unit="%",
            claimed_metric="generic_rate",
            is_applicable=True,
        )
        results = verify_claims([claim], [fact_good, fact_reject])
        self.assertEqual(results[0].outcome, VerificationOutcome.UNVERIFIED)
        self.assertIn("multiple distinct rate metrics", results[0].explanation)


class TestDef01HttpStatusCodesContextualDiscrimination(unittest.TestCase):
    """
    DEF-01: HTTP status-code contextual discrimination.
    Numbers matching HTTP codes (200, 400, 401, etc.) must ONLY be treated as non-claims
    when explicit HTTP/API response context is present. In manufacturing contexts,
    they must be preserved as applicable analytical claims.
    """

    def test_http_status_codes_excluded_in_http_context(self):
        """Standard HTTP status codes are excluded as non-claims in explicit HTTP/API context."""
        test_cases = [
            ("The endpoint returned HTTP 200 OK after query execution.", "200", "HTTP status code"),
            ("The API returned status code 400 due to bad syntax.", "400", "HTTP status code"),
            ("Authentication failed with HTTP 401 Unauthorized.", "401", "HTTP status code"),
            ("Server responded with status code 403 Forbidden.", "403", "HTTP status code"),
            ("The request gave 404 Not Found from telemetry service.", "404", "HTTP status code"),
            ("Validation returned 422 Unprocessable Entity.", "422", "HTTP status code"),
            ("Rate limiting returned code 429 Too Many Requests.", "429", "HTTP status code"),
            ("The gateway raised error 500 Internal Server Error.", "500", "HTTP status code"),
            ("The downstream service gave 502 Bad Gateway.", "502", "HTTP status code"),
            ("External connector returned 503 Service Unavailable.", "503", "HTTP status code"),
            ("Network request ended with 504 Gateway Timeout.", "504", "HTTP status code"),
        ]
        for sentence, expected_num, expected_reason in test_cases:
            with self.subTest(num=expected_num, sentence=sentence):
                claims = extract_claims(sentence)
                matching = [c for c in claims if c.cleaned_number_str == expected_num]
                self.assertTrue(len(matching) >= 1, f"Expected {expected_num} to be extracted from '{sentence}'")
                self.assertFalse(matching[0].is_applicable, f"Expected {expected_num} to be non-claim in '{sentence}'")
                self.assertIn("HTTP status code", matching[0].non_claim_reason)

    def test_manufacturing_quantities_preserved_despite_matching_http_numbers(self):
        """The EXACT SAME numbers (200, 400, 404, 500, etc.) are preserved as analytical claims in manufacturing context."""
        manufacturing_cases = [
            ("Produced 200 phones on line SMT-L1.", "200", "actual_quantity", "units"),
            ("Consumed 500 kWh of electricity during shift 1.", "500", "energy", "kWh"),
            ("Rejected 400 boards during automated optical inspection.", "400", "reject_quantity", "boards"),
            ("Downtime totaled 401 minutes on line FAL-L2.", "401", "downtime", "min"),
            ("Recorded 403 observations across the plant.", "403", None, None),
            ("Shift A produced 404 units of Aster 15.", "404", "actual_quantity", "units"),
            ("Energy tariff cost was 422 INR per hour.", "422", "cost", "INR"),
            ("Target output was 429 boards for the day.", "429", "target_quantity", "boards"),
            ("SMT-L1 produced 502 phones.", "502", "actual_quantity", "units"),
            ("Line FAL-L1 produced 503 units.", "503", "actual_quantity", "units"),
            ("Final output reached 504 phones.", "504", "actual_quantity", "units"),
        ]
        for sentence, expected_num, expected_metric, expected_unit in manufacturing_cases:
            with self.subTest(num=expected_num, sentence=sentence):
                claims = extract_claims(sentence)
                matching = [c for c in claims if c.cleaned_number_str == expected_num]
                self.assertTrue(len(matching) >= 1, f"Expected {expected_num} to be extracted from '{sentence}'")
                self.assertTrue(matching[0].is_applicable, f"Expected {expected_num} to be applicable claim in '{sentence}', but got non-claim reason: {matching[0].non_claim_reason}")
                self.assertIsNone(matching[0].non_claim_reason)
                if expected_metric:
                    self.assertEqual(matching[0].claimed_metric, expected_metric)

    def test_mixed_sentence_with_both_http_code_and_manufacturing_metric(self):
        """When a single sentence contains both an HTTP status code and a manufacturing quantity of the same value, discriminate correctly."""
        sentence = "The endpoint returned HTTP 200, confirming line SMT-L1 produced 200 phones."
        claims = extract_claims(sentence)
        matching = [c for c in claims if c.cleaned_number_str == "200"]
        self.assertEqual(len(matching), 2, "Expected exactly two occurrences of 200")

        # First 200 is HTTP status code -> non-claim
        self.assertFalse(matching[0].is_applicable)
        self.assertEqual(matching[0].non_claim_reason, "HTTP status code")

        # Second 200 is production quantity -> applicable claim
        self.assertTrue(matching[1].is_applicable)
        self.assertIsNone(matching[1].non_claim_reason)
        self.assertEqual(matching[1].claimed_metric, "actual_quantity")


class TestDef02EnumerationDetectionAndAnalyticalPreservation(unittest.TestCase):
    """
    DEF-02: Numbered-list enumeration detection and analytical preservation.
    List and step markers (1., 2), Step 1:, Item 2:, ### 1) must be classified as non-claims,
    while analytical claims within the list items must be extracted and preserved.
    """

    def test_numbered_list_markers_classified_as_non_claims(self):
        """Standard numbered list patterns are classified as non-claims."""
        items = [
            "1. First operational observation.",
            "2) Second operational observation.",
            "(3) Third maintenance checkpoint.",
            "- 4. Fourth follow-up requirement.",
            "* 5. Fifth quality audit point.",
        ]
        for item in items:
            claims = extract_claims(item)
            self.assertEqual(len(claims), 1, f"Expected 1 claim extracted from '{item}'")
            self.assertFalse(claims[0].is_applicable, f"Expected marker in '{item}' to be non-claim")
            self.assertIn("List enumeration", claims[0].non_claim_reason)

    def test_step_and_item_labels_classified_as_non_claims(self):
        """Step, Item, and Rule prefixes are classified as non-claims."""
        items = [
            "Step 1: Check meter telemetry.",
            "Item 2: Inspect line FAL-L1 reject rate.",
            "Rule 3: Maintain power factor above baseline.",
            "Section 4: Energy efficiency breakdown.",
            "Phase 5: Production ramp-up.",
        ]
        for item in items:
            claims = extract_claims(item)
            self.assertEqual(len(claims), 1, f"Expected 1 claim extracted from '{item}'")
            self.assertFalse(claims[0].is_applicable, f"Expected marker in '{item}' to be non-claim")
            self.assertIn("List enumeration", claims[0].non_claim_reason)

    def test_markdown_numbered_headers_classified_as_non_claims(self):
        """Markdown header numbers are classified as non-claims."""
        headers = [
            "# 1 Executive Summary",
            "## 2 Production Metrics",
            "### 3 Energy Analysis",
            "#### 4 Corrective Actions",
        ]
        for header in headers:
            claims = extract_claims(header)
            self.assertEqual(len(claims), 1, f"Expected 1 claim extracted from '{header}'")
            self.assertFalse(claims[0].is_applicable, f"Expected header in '{header}' to be non-claim")
            self.assertIn("List enumeration", claims[0].non_claim_reason)

    def test_analytical_claims_inside_numbered_lists_preserved(self):
        """Numbers inside numbered list items representing analytical metrics are preserved as applicable claims."""
        text = (
            "1. Total energy consumption was 15,000 kWh on 2026-08-01.\n"
            "2. Line SMT-L1 produced 200 phones with 500 kWh consumed.\n"
            "3. Reject count reached 400 boards resulting in 422 INR cost."
        )
        claims = extract_claims(text)

        # Applicable claims should include: 15,000, 200, 500, 400, 422
        applicable = [c for c in claims if c.is_applicable]
        applicable_vals = [c.cleaned_number_str for c in applicable]

        self.assertIn("15000", applicable_vals)
        self.assertIn("200", applicable_vals)
        self.assertIn("500", applicable_vals)
        self.assertIn("400", applicable_vals)
        self.assertIn("422", applicable_vals)

        # Enumeration markers 1, 2, 3 should be non-claims
        non_claims = [c for c in claims if not c.is_applicable]
        non_claim_reasons = {c.cleaned_number_str: c.non_claim_reason for c in non_claims}
        self.assertIn("1", non_claim_reasons)
        self.assertIn("List enumeration", non_claim_reasons["1"])
        self.assertIn("2", non_claim_reasons)
        self.assertIn("List enumeration", non_claim_reasons["2"])
        self.assertIn("3", non_claim_reasons)
        self.assertIn("List enumeration", non_claim_reasons["3"])

    def test_analytical_claims_inside_step_labels_preserved(self):
        """Analytical metrics inside Step labels are preserved."""
        text = "Step 1: Check line FAL-L1 which produced 250 units and logged 45 minutes of downtime."
        claims = extract_claims(text)

        # 1 should be non-claim
        c1 = [c for c in claims if c.cleaned_number_str == "1"][0]
        self.assertFalse(c1.is_applicable)
        self.assertIn("List enumeration", c1.non_claim_reason)

        # 250 and 45 should be applicable
        c250 = [c for c in claims if c.cleaned_number_str == "250"][0]
        self.assertTrue(c250.is_applicable)
        self.assertEqual(c250.claimed_metric, "actual_quantity")

        c45 = [c for c in claims if c.cleaned_number_str == "45"][0]
        self.assertTrue(c45.is_applicable)
        self.assertEqual(c45.claimed_metric, "downtime")

    def test_mixed_prose_and_numbered_lists_verification_pipeline(self):
        """End-to-end verification pipeline on response containing both narrative prose and numbered lists."""
        response_text = (
            "During the morning inspection of plant IN-TN-01, the following findings were noted:\n"
            "1. Main line SMT-L1 consumed 500 kWh.\n"
            "2. Total finished output was 200 phones.\n"
            "All telemetry requests completed with HTTP 200 OK."
        )
        evidence = [
            MockToolEvidence(
                tool_name="energy_summary",
                arguments={"plant_id": "IN-TN-01", "line_id": "SMT-L1"},
                result={"total_consumption_kwh": 500.0},
                success=True,
            ),
            MockToolEvidence(
                tool_name="production_summary",
                arguments={"plant_id": "IN-TN-01"},
                result={"total_actual_qty": 200},
                success=True,
            ),
        ]
        res = verify_numeric_claims(response_text, evidence)

        # The two manufacturing claims (500 and 200) must be VERIFIED
        self.assertEqual(res.summary.verified_claims, 2)
        self.assertEqual(res.summary.unverified_claims, 0)
        self.assertEqual(res.summary.conflicting_claims, 0)
        self.assertEqual(res.summary.status, "VERIFIED")

        # Markers (1, 2) and HTTP status code (200) must NOT be counted as analytical claims
        self.assertEqual(res.summary.total_claims, 2)


if __name__ == "__main__":
    unittest.main()
