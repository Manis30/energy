"""
Deterministic Numeric Claim Verification and Grounding Engine.

Verifies numerical claims in AI Assistant responses against actual, successful
backend analytics tool results executed during the current turn.

Core Engineering Principles:
1. LLM text is never authoritative; backend tool evidence is authoritative.
2. Only successful tool results (success=True, result is not None) support claims.
3. No cross-turn contamination; evidence is strictly scoped to the current turn.
4. Metric type, units, scope (plant, meter, line, product, shift), and date ranges
   must match; a matching number alone is insufficient.
5. Deterministic outcomes: VERIFIED, UNVERIFIED, CONFLICTING, SCOPE_MISMATCH,
   UNIT_MISMATCH, NOT_APPLICABLE.
6. Non-metric numbers (identifiers, dates, version strings, policy rules) are
   classified as NOT_APPLICABLE.
7. Corrects unambiguous conflicting claims using authoritative evidence and qualifies
   unsupported numbers without discarding useful non-numeric explanations.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Outcome Definitions
# ---------------------------------------------------------------------------

class VerificationOutcome:
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTING = "CONFLICTING"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class AuthoritativeFact:
    """A single factual metric extracted from a successful tool execution."""
    tool_name: str
    execution_order: int
    metric_name: str
    metric_category: str  # "energy", "cost", "emissions", "power_factor", "production", "downtime", "sec", "rate", "anomalies", "count", "generic"
    value: Decimal
    unit: Optional[str] = None
    plant_id: Optional[str] = None
    meter_id: Optional[str] = None
    line_id: Optional[str] = None
    product_id: Optional[str] = None
    shift_id: Optional[str] = None
    area: Optional[str] = None
    exact_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    aggregation: Optional[str] = None  # "sum", "avg", "peak", "count", "rate"


@dataclass
class ExtractedClaim:
    """A numerical claim extracted from assistant response text."""
    raw_number_str: str
    cleaned_number_str: str
    claimed_value: Decimal
    sentence: str
    claimed_unit: Optional[str] = None
    claimed_metric: Optional[str] = None
    claimed_scope_plant: Optional[str] = None
    claimed_scope_meter: Optional[str] = None
    claimed_scope_line: Optional[str] = None
    claimed_scope_product: Optional[str] = None
    claimed_scope_shift: Optional[str] = None
    claimed_scope_area: Optional[str] = None
    claimed_date: Optional[str] = None
    claimed_aggregation: Optional[str] = None
    is_applicable: bool = True
    non_claim_reason: Optional[str] = None
    start_in_sentence: int = -1
    end_in_sentence: int = -1


@dataclass
class ClaimVerificationResult:
    """Detailed verification outcome for a single numerical claim."""
    claimed_number: str
    sentence: str
    metric: Optional[str] = None
    unit: Optional[str] = None
    scope: Optional[str] = None
    outcome: str = VerificationOutcome.UNVERIFIED
    authoritative_value: Optional[str] = None
    authoritative_unit: Optional[str] = None
    supporting_tool: Optional[str] = None
    explanation: str = ""
    was_corrected: bool = False
    start_in_sentence: int = -1
    end_in_sentence: int = -1
    can_auto_correct: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claimed_number": self.claimed_number,
            "metric": self.metric,
            "unit": self.unit,
            "scope": self.scope,
            "outcome": self.outcome,
            "authoritative_value": self.authoritative_value,
            "authoritative_unit": self.authoritative_unit,
            "supporting_tool": self.supporting_tool,
            "explanation": self.explanation,
            "was_corrected": self.was_corrected,
        }


@dataclass
class VerificationSummary:
    """Aggregate statistics for response verification."""
    status: str  # "VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED", "CONFLICT_DETECTED", "NO_ANALYTIC_CLAIMS"
    total_claims: int
    verified_claims: int
    unverified_claims: int
    conflicting_claims: int
    scope_mismatches: int
    unit_mismatches: int
    not_applicable_count: int
    supported_by_tools: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "total_claims": self.total_claims,
            "verified_claims": self.verified_claims,
            "unverified_claims": self.unverified_claims,
            "conflicting_claims": self.conflicting_claims,
            "scope_mismatches": self.scope_mismatches,
            "unit_mismatches": self.unit_mismatches,
            "not_applicable_count": self.not_applicable_count,
            "supported_by_tools": self.supported_by_tools,
        }


@dataclass
class VerificationResponse:
    """Full result of the deterministic verification process."""
    final_answer: str
    summary: VerificationSummary
    claims: List[ClaimVerificationResult]


# ---------------------------------------------------------------------------
# Metric Classification & Normalization Constants
# ---------------------------------------------------------------------------

# Peak Energy (DEF-04): separated from cumulative energy
PEAK_ENERGY_KEYS = {
    "peak_kwh", "peak_hourly_kwh", "peak_consumption_kwh", "peak_demand_kw",
}

# Cumulative Energy (DEF-04): total/sum consumption
CUMULATIVE_ENERGY_KEYS = {
    "total_consumption_kwh", "consumption_kwh", "process_kwh", "total_process_kwh",
    "total_plant_kwh", "meter_kwh", "facility_utility_kwh", "smt_standby_kwh",
    "fal_standby_kwh", "total_standby_kwh", "plant_kwh",
}
ENERGY_KEYS = CUMULATIVE_ENERGY_KEYS

COST_KEYS = {"total_cost_inr", "cost_inr", "process_cost_inr"}
EMISSIONS_KEYS = {"total_co2e_kg", "co2e_kg", "process_co2e_kg"}
POWER_FACTOR_KEYS = {
    "avg_power_factor", "arithmetic_avg_power_factor", "power_factor",
    "average_power_factor", "min_power_factor", "max_power_factor",
}
PRODUCTION_TARGET_KEYS = {"target_qty", "total_target_qty"}
PRODUCTION_ACTUAL_KEYS = {"actual_qty", "total_actual_qty", "finished_goods_qty"}
PRODUCTION_GOOD_KEYS = {"good_qty", "total_good_qty"}
PRODUCTION_REJECT_KEYS = {"reject_qty", "total_reject_qty"}
PRODUCTION_REWORK_KEYS = {"rework_qty", "total_rework_qty"}
DOWNTIME_KEYS = {"downtime_min", "total_downtime_min"}

# Specific Rate Categories (DEF-03): separated to prevent cross-rate matching
GOOD_RATE_KEYS = {"good_rate", "yield_rate", "quality_rate"}
REJECT_RATE_KEYS = {"reject_rate", "scrap_rate"}
REWORK_RATE_KEYS = {"rework_rate", "repair_rate"}
ACHIEVEMENT_RATE_KEYS = {"achievement_rate", "target_achievement_rate"}
PERCENTAGE_OF_TOTAL_KEYS = {
    "percentage_of_total", "percentage_of_plant_total", "share_of_total",
    "area_share_pct", "energy_share_pct",
}
PERCENTAGE_BELOW_THRESHOLD_KEYS = {"percentage_below_threshold", "low_pf_percentage"}
PERCENTAGE_OF_DOWNTIME_KEYS = {"percentage_of_downtime", "downtime_percentage"}

RATE_KEYS = (
    GOOD_RATE_KEYS
    | REJECT_RATE_KEYS
    | REWORK_RATE_KEYS
    | ACHIEVEMENT_RATE_KEYS
    | PERCENTAGE_OF_TOTAL_KEYS
    | PERCENTAGE_BELOW_THRESHOLD_KEYS
    | PERCENTAGE_OF_DOWNTIME_KEYS
)

ALL_SPECIFIC_RATE_CATEGORIES = {
    "good_rate",
    "reject_rate",
    "rework_rate",
    "achievement_rate",
    "percentage_of_total",
    "percentage_below_threshold",
    "percentage_of_downtime",
}

ALL_RATE_CATEGORIES = ALL_SPECIFIC_RATE_CATEGORIES | {"generic_rate"}
SEC_KEYS = {
    "process_sec_actual_kwh_per_unit", "process_sec_good_kwh_per_unit",
    "sec_kwh_per_unit", "overall_process_sec_kwh_per_board",
    "overall_process_sec_kwh_per_phone", "factory_sec_kwh_per_phone",
}
ANOMALY_COUNT_KEYS = {"total_anomalies_detected", "anomaly_count", "total_standby_kwh"}
GENERIC_COUNT_KEYS = {
    "total_readings", "distinct_hours", "reading_count", "event_count",
    "operating_hours", "zero_output_hours", "row_count", "total_evaluated_observations",
    "insufficient_history_count", "zero_variance_count", "eligible_groups_count",
    "disqualified_groups_count", "readings_below_threshold",
}

EXCLUDED_KEY_PATTERNS = {
    "id", "event_id", "meter_reading_id", "upload_id", "product_id", "line_id",
    "meter_id", "plant_id", "status", "data_available", "consumption_data_available",
    "cost_data_available", "emissions_data_available", "power_factor_data_available",
    "quantity_balance_valid", "avoidable_waste_claimed", "current_observation_excluded",
}

# Unit compatibility mapping
UNIT_NORMALIZATION = {
    "kwh": "kWh", "kwh/board": "kWh/board", "kwh/phone": "kWh/phone",
    "kwh/unit": "kWh/unit", "inr": "INR", "rs": "INR", "rs.": "INR",
    "rupees": "INR", "₹": "INR", "kg co2e": "kg CO2e", "kg": "kg CO2e",
    "co2e": "kg CO2e", "%": "%", "percent": "%", "percentage": "%",
    "minutes": "minutes", "min": "minutes", "mins": "minutes",
    "hours": "hours", "hrs": "hours", "units": "units", "boards": "boards",
    "phones": "phones", "anomalies": "anomalies", "readings": "readings",
    "events": "events", "rows": "rows", "sigma": "sigma", "z": "sigma",
}

# Non-claim regex patterns (identifiers, dates, version strings, enumeration, rules)
RE_ISO_DATE = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
RE_SLASH_DATE = re.compile(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b')
RE_TIME_FORMAT = re.compile(r'\b\d{1,2}:\d{2}(?::\d{2})?\b')
RE_PLANT_ID = re.compile(r'\bIN-(?:TN|KA)-01\b', re.IGNORECASE)
RE_LINE_ID = re.compile(r'\b(?:SMT|FAL)-L[12]\b', re.IGNORECASE)
RE_METER_ID = re.compile(r'\bMTR-(?:SMT|FAL|HVAC|COMPRESSOR|CHILLER)\b', re.IGNORECASE)
RE_SKU_ID = re.compile(r'\bSPH-(?:A15|PRO)-(?:128|256)\b', re.IGNORECASE)
RE_PRODUCT_NAME = re.compile(r'\bAster\s+(?:15|Pro)\b', re.IGNORECASE)
RE_VERSION = re.compile(r'\bv?\d+\.\d+(?:\.\d+)?\b', re.IGNORECASE)

# Contextual HTTP status code pattern (DEF-01): requires explicit HTTP/status/code/error context
HTTP_CODES = r'200|400|401|403|404|422|429|500|502|503|504'
RE_HTTP_STATUS_CODE = re.compile(
    r'(?:'
    # Leading context: HTTP, HTTP/1.1, status [code], response [code], error [code], code, returned/gave/giving [status/a]
    r'(?:(?:HTTP(?:/[0-9.]+)?|status(?:\s*code)?|response(?:\s*code)?|error(?:\s*code)?|\bcode)\s*(?:of|:)?\s*(?:a\s+|an\s+|was\s+)?|(?:returned|returned\s+status|gave|giving)\s*(?:a\s+|an\s+)?)\s*'
    rf'({HTTP_CODES})\b'
    r'|'
    # Trailing context: status code followed by HTTP status label or 'error' / 'status' / 'response'
    rf'\b({HTTP_CODES})\s+'
    r'(?:OK|Bad\s+Request|Unauthorized|Forbidden|Not\s+Found|Unprocessable(?:\s+Entity)?|Too\s+Many\s+Requests|Internal(?:\s+Server)?\s+Error|Bad\s+Gateway|Service\s+Unavailable|Gateway\s+Timeout|status|error|response\b)'
    r')',
    re.IGNORECASE,
)
RE_STATUS_CODE = RE_HTTP_STATUS_CODE  # Alias for backward compatibility

# Enumeration patterns (DEF-02): numbered lists (1., 2)), step/item labels (Step 1:, Item 2:), and markdown headers
RE_ENUMERATION_MARKER = re.compile(
    r'^\s*(?:'
    r'[-*]\s+'
    r')?'
    r'(?:'
    r'\(?\d{1,3}[\.\)]'
    r'|'
    r'(?:Step|Item|Rule|Section|Phase)\s+\d{1,3}:?'
    r'|'
    r'#{1,6}\s*\d{1,3}:?'
    r')',
    re.IGNORECASE,
)
RE_ENUM_LINE_SPLIT = re.compile(
    r'^((?:[-*]\s+)?(?:\(?\d{1,3}[\.\)]|(?:Step|Item|Rule|Section|Phase)\s+\d{1,3}:?|#{1,6}\s*\d{1,3}:?))(?:\s+(.*))?$',
    re.IGNORECASE,
)
RE_TOOL_LIMIT_REF = re.compile(r'\b(?:limit\s*(?:of)?\s*5|5\s*tool\s*(?:calls?|executions?))\b', re.IGNORECASE)
RE_POLICY_THRESHOLD_PF = re.compile(r'\b(?:threshold\s*(?:of|=)?\s*0\.90|0\.90\s*(?:threshold|cutoff))\b', re.IGNORECASE)
RE_POLICY_THRESHOLD_Z = re.compile(r'\b(?:threshold\s*(?:of|=)?\s*3\.0|3\.0\s*(?:sigma|threshold|z-score))\b', re.IGNORECASE)
RE_EMISSIONS_FACTOR = re.compile(r'\b(?:factor\s*(?:of|=)?\s*0\.716|0\.716\s*kg)\b', re.IGNORECASE)
RE_YEAR_ONLY = re.compile(r'\b(?:in|for|since|year|during|january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(19\d{2}|20\d{2})\b|\b(19\d{2}|20\d{2})\s+(?:data|records|fiscal)\b', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Authoritative Evidence Ingestion
# ---------------------------------------------------------------------------

def _to_decimal(val: Any) -> Optional[Decimal]:
    """Safely convert numeric value to Decimal without floating-point artifacts."""
    if val is None or isinstance(val, bool):
        return None
    try:
        if isinstance(val, Decimal):
            return val
        s = str(val).strip().replace(",", "")
        return Decimal(s)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _classify_metric_key(key: str) -> Tuple[str, Optional[str]]:
    """
    Determine metric_category and standard unit for a given result key.
    Enforces DEF-03 (rate separation) and DEF-04 (cumulative vs peak energy separation).
    """
    k = key.lower().strip()

    # SEC metrics (kWh per product unit)
    if "per_board" in k:
        return "sec", "kWh/board"
    elif "per_phone" in k:
        return "sec", "kWh/phone"
    elif "per_unit" in k:
        return "sec", "kWh/unit"
    elif k in SEC_KEYS or "intensity" in k:
        return "sec", "kWh/unit"

    # Peak Energy (DEF-04): strictly separate from cumulative energy
    if k in PEAK_ENERGY_KEYS or ("peak" in k and ("kwh" in k or "consumption" in k or "hourly" in k or "energy" in k)):
        return "peak_energy", "kWh"

    # Cumulative Energy (DEF-04): total/sum consumption
    if k in CUMULATIVE_ENERGY_KEYS or "kwh" in k or "energy" in k or "consumption" in k:
        return "energy", "kWh"

    # Cost
    if k in COST_KEYS or "cost" in k or "inr" in k:
        return "cost", "INR"

    # Emissions
    if k in EMISSIONS_KEYS or "co2" in k or "emission" in k:
        return "emissions", "kg CO2e"

    # Power Factor
    if k in POWER_FACTOR_KEYS or "power_factor" in k or k == "pf":
        return "power_factor", None

    # Specific Rate Categories (DEF-03): separated into distinct categories
    if k in GOOD_RATE_KEYS or "good_rate" in k or "yield_rate" in k or "quality_rate" in k:
        return "good_rate", "%"
    if k in REJECT_RATE_KEYS or "reject_rate" in k or "scrap_rate" in k:
        return "reject_rate", "%"
    if k in REWORK_RATE_KEYS or "rework_rate" in k or "repair_rate" in k:
        return "rework_rate", "%"
    if k in ACHIEVEMENT_RATE_KEYS or "achievement_rate" in k or "target_achievement" in k:
        return "achievement_rate", "%"
    if (
        k in PERCENTAGE_OF_TOTAL_KEYS
        or "percentage_of_total" in k
        or "percentage_of_plant_total" in k
        or "share_of_total" in k
        or "area_share" in k
        or "energy_share" in k
    ):
        return "percentage_of_total", "%"
    if k in PERCENTAGE_BELOW_THRESHOLD_KEYS or "percentage_below_threshold" in k or "low_pf_percentage" in k:
        return "percentage_below_threshold", "%"
    if k in PERCENTAGE_OF_DOWNTIME_KEYS or "percentage_of_downtime" in k or "downtime_percentage" in k:
        return "percentage_of_downtime", "%"
    if "rate" in k or "percentage" in k or "pct" in k:
        return "generic_rate", "%"

    # Production Quantities (units)
    if k in PRODUCTION_TARGET_KEYS or "target_qty" in k:
        return "target_quantity", "units"
    if k in PRODUCTION_ACTUAL_KEYS or "actual_qty" in k or "finished_goods" in k:
        return "actual_quantity", "units"
    if k in PRODUCTION_GOOD_KEYS or "good_qty" in k:
        return "good_quantity", "units"
    if k in PRODUCTION_REJECT_KEYS or "reject_qty" in k:
        return "reject_quantity", "units"
    if k in PRODUCTION_REWORK_KEYS or "rework_qty" in k:
        return "rework_quantity", "units"

    # Downtime
    if k in DOWNTIME_KEYS or "downtime" in k:
        return "downtime", "minutes"

    # Counts and anomalies
    if k in ANOMALY_COUNT_KEYS or "anomal" in k:
        return "anomalies", "anomalies"
    if k in GENERIC_COUNT_KEYS or "count" in k or "readings" in k or "hours" in k or "rows" in k:
        return "count", "count"

    # Peak fallback (if not caught above)
    if "peak" in k:
        return "peak_energy", "kWh"

    # Z-scores
    if "z" in k or "deviation" in k:
        return "z_score", "sigma"

    return "generic", None


def extract_authoritative_facts(evidence: List[Any]) -> List[AuthoritativeFact]:
    """
    Extract structured factual metrics from all successful tool results in the current turn.
    Guarantees:
    - Only successful tool results (ev.success == True and ev.result is not None) are considered.
    - Captures metric name, numeric value, unit, aggregation, and full entity scope.
    """
    facts: List[AuthoritativeFact] = []

    for ev in evidence:
        if not getattr(ev, "success", False) or getattr(ev, "result", None) is None:
            continue

        tool_name = getattr(ev, "tool_name", "unknown_tool")
        exec_order = getattr(ev, "execution_order", 0)
        args = getattr(ev, "arguments", {}) or {}

        # Base tool-level arguments
        tool_plant = args.get("plant_id")
        tool_line = args.get("line_id")
        tool_meter = args.get("meter_id")
        tool_product = args.get("product_id")
        tool_shift = args.get("shift_id")
        tool_start_date = str(args.get("start_date")) if args.get("start_date") else None
        tool_end_date = str(args.get("end_date")) if args.get("end_date") else None

        def _traverse(data: Any, scope_prefix: str = "", context_scope: Optional[Dict[str, Any]] = None):
            cur_scope = dict(context_scope or {})

            if isinstance(data, dict):
                # Check for localized scope overrides inside nested dictionary
                for sk in ("plant_id", "line_id", "meter_id", "product_id", "shift_id", "area", "date"):
                    if sk in data and data[sk] is not None:
                        cur_scope[sk] = str(data[sk])

                for k, v in data.items():
                    if k.lower() in EXCLUDED_KEY_PATTERNS or v is None:
                        continue

                    full_key = f"{scope_prefix}.{k}" if scope_prefix else k

                    if isinstance(v, (dict, list)):
                        _traverse(v, full_key, cur_scope)
                    elif isinstance(v, (int, float, Decimal)):
                        dec_val = _to_decimal(v)
                        if dec_val is not None:
                            category, unit = _classify_metric_key(k)
                            if category == "peak_energy" or "peak" in k.lower():
                                agg = "peak"
                            elif "avg" in k.lower() or "mean" in k.lower():
                                agg = "avg"
                            elif "total" in k.lower() or "sum" in k.lower() or category == "energy":
                                agg = "sum"
                            else:
                                agg = None
                            fact = AuthoritativeFact(
                                tool_name=tool_name,
                                execution_order=exec_order,
                                metric_name=full_key,
                                metric_category=category,
                                value=dec_val,
                                unit=unit,
                                plant_id=cur_scope.get("plant_id", tool_plant),
                                meter_id=cur_scope.get("meter_id", tool_meter),
                                line_id=cur_scope.get("line_id", tool_line),
                                product_id=cur_scope.get("product_id", tool_product),
                                shift_id=cur_scope.get("shift_id", tool_shift),
                                area=cur_scope.get("area"),
                                exact_date=cur_scope.get("date"),
                                start_date=tool_start_date,
                                end_date=tool_end_date,
                                aggregation=agg,
                            )
                            facts.append(fact)

            elif isinstance(data, list):
                for item in data:
                    _traverse(item, scope_prefix, cur_scope)

        _traverse(ev.result, context_scope={
            "plant_id": tool_plant,
            "line_id": tool_line,
            "meter_id": tool_meter,
            "product_id": tool_product,
            "shift_id": tool_shift,
        })

    return facts


# ---------------------------------------------------------------------------
# Numerical Claim Extraction from Response Text
# ---------------------------------------------------------------------------

# Regex pattern supporting positive/negative numbers, Western/Indian grouping,
# currency prefixes (₹, INR, Rs), percentages, and scientific notation (DEF-05)
RE_NUMBER = re.compile(
    r'(?<![a-zA-Z0-9])'                         # Cannot be preceded by letter or digit
    r'[-−]?'                                     # Optional leading negative sign
    r'(?:₹|INR\s*|Rs\.\s*|Rs\s*)?'              # Optional currency prefix
    r'[-−]?'                                     # Optional sign after currency
    r'\d+(?:,\d+)*'                              # Integer part (digits with optional comma separators)
    r'(?:\.\d+)?'                                # Optional decimal fraction
    r'(?:[eE][+-]?\d+)?'                         # Optional scientific notation
    r'%?'                                        # Optional percentage
    r'(?![a-zA-Z0-9])'                           # Cannot be followed by letter or digit
)

RE_WESTERN_GROUPING = re.compile(r'^\d{1,3}(?:,\d{3})+$')
RE_INDIAN_GROUPING = re.compile(r'^\d{1,2}(?:,\d{2})*,\d{3}$')


def _is_valid_grouping(int_str: str) -> bool:
    """Validate that comma separators follow Western or Indian grouping conventions (DEF-05)."""
    if "," not in int_str:
        return True
    return bool(RE_WESTERN_GROUPING.match(int_str) or RE_INDIAN_GROUPING.match(int_str))


def _normalize_claim_number(raw_match: str) -> Tuple[bool, Optional[Decimal], str, Optional[str]]:
    """
    Safely parse and normalize raw extracted number token to Decimal (DEF-05).
    Guarantees:
    - Preserves negative signs regardless of position relative to currency symbols.
    - Validates Western and Indian comma grouping before stripping commas.
    - Preserves scientific notation exponents (e.g. 1.25e6, -1.5E-3).
    - Infers currency ('INR') or percentage ('%') units directly from token.
    - Returns (is_valid, decimal_value, cleaned_str, inferred_unit).
    """
    m = re.match(r'^\s*([-−]?)\s*(?:₹|INR|Rs\.|Rs|\$|€|£)?\s*([-−]?)\s*([0-9].*)$', raw_match, re.I)
    if not m:
        return False, None, raw_match, None

    sign1, sign2, body = m.group(1), m.group(2), m.group(3)
    is_neg = (sign1 in ('-', '−')) or (sign2 in ('-', '−'))

    # Infer unit from currency prefix or percentage suffix
    unit = None
    if any(c in raw_match for c in ('₹', 'INR', 'Rs')):
        unit = 'INR'
    elif '%' in raw_match:
        unit = '%'

    # Validate comma grouping in integer portion
    int_part = re.split(r'[\.eE%]', body)[0]
    if not _is_valid_grouping(int_part):
        return False, None, raw_match, unit

    # Remove comma separators and percentage symbol for Decimal conversion
    clean_body = body.replace(',', '').replace('%', '').strip()
    clean_num = ('-' if is_neg else '') + clean_body

    try:
        dec_val = Decimal(clean_num)
        return True, dec_val, clean_num, unit
    except (InvalidOperation, ValueError, TypeError):
        return False, None, raw_match, unit


def _split_into_sentences(text: str) -> List[str]:
    """Split text into distinct sentences and bullet lines preserving enumeration prefixes."""
    raw_lines = text.split("\n")
    sentences: List[str] = []
    for line in raw_lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        m_enum = RE_ENUM_LINE_SPLIT.match(line_clean)
        if m_enum:
            prefix = m_enum.group(1)
            rest = m_enum.group(2)
            if rest:
                parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9*#>-])', rest)
                if parts:
                    sentences.append(f"{prefix} {parts[0].strip()}")
                    for p in parts[1:]:
                        p_strip = p.strip()
                        if p_strip:
                            sentences.append(p_strip)
            else:
                sentences.append(prefix)
        else:
            parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9*#>-])', line_clean)
            for p in parts:
                p_strip = p.strip()
                if p_strip:
                    sentences.append(p_strip)
    return sentences


def _is_non_claim(sentence: str, match_start: int, match_end: int, num_str: str) -> Tuple[bool, Optional[str]]:
    """
    Determine if a candidate number in sentence is an identifier, date,
    enumeration marker, or system policy rule rather than an analytical claim.
    """
    # 1. Check if number is part of an ISO or slash date
    for m in RE_ISO_DATE.finditer(sentence):
        if m.start() <= match_start and match_end <= m.end():
            return True, "Part of ISO date"
    for m in RE_SLASH_DATE.finditer(sentence):
        if m.start() <= match_start and match_end <= m.end():
            return True, "Part of slash date"
    for m in RE_TIME_FORMAT.finditer(sentence):
        if m.start() <= match_start and match_end <= m.end():
            return True, "Part of time expression"

    # 2. Check if number is a 4-digit year in context (e.g., 'in 2026', 'year 2025')
    if len(num_str) == 4 and (num_str.startswith("19") or num_str.startswith("20")):
        for m in RE_YEAR_ONLY.finditer(sentence):
            if m.start() <= match_start and match_end <= m.end():
                return True, "Calendar year identifier"

    # 3. Check if number is part of an entity code or SKU
    for pat, label in [
        (RE_PLANT_ID, "Plant identifier"),
        (RE_LINE_ID, "Line identifier"),
        (RE_METER_ID, "Meter identifier"),
        (RE_SKU_ID, "Product SKU identifier"),
        (RE_PRODUCT_NAME, "Product model name"),
        (RE_VERSION, "Algorithm or tool version"),
        (RE_HTTP_STATUS_CODE, "HTTP status code"),
    ]:
        for m in pat.finditer(sentence):
            if m.start() <= match_start and match_end <= m.end():
                return True, label

    # 4. Check if number is part of list enumeration at start of sentence (e.g. '1. ', '2) ', 'Step 1:')
    m_enum = RE_ENUMERATION_MARKER.match(sentence)
    if m_enum and m_enum.start() <= match_start and match_end <= m_enum.end():
        return True, "List enumeration or step marker"

    # 5. Check if number is a static system constant or execution limit
    for pat, label in [
        (RE_TOOL_LIMIT_REF, "Tool execution limit constant (5)"),
        (RE_POLICY_THRESHOLD_PF, "Policy power factor threshold constant (0.90)"),
        (RE_POLICY_THRESHOLD_Z, "Policy Z-score threshold constant (3.0)"),
        (RE_EMISSIONS_FACTOR, "Dataset emissions factor constant (0.716)"),
    ]:
        for m in pat.finditer(sentence):
            if m.start() <= match_start and match_end <= m.end():
                return True, label

    return False, None


def _infer_unit_from_context(sentence: str, match_start: int, match_end: int) -> Optional[str]:
    """Inspect immediate neighboring context around the number to determine stated unit."""
    tok = sentence[match_start:match_end]
    # Check if number token itself includes %
    if tok.endswith("%") or "%" in tok:
        return "%"

    # Check if number token itself includes currency prefix (DEF-05)
    if any(c in tok for c in ("₹", "INR", "Rs")):
        return "INR"

    # Check trailing text (up to 30 chars)
    trailing = sentence[match_end:match_end + 30].strip()
    # Check leading text (up to 15 chars)
    leading = sentence[max(0, match_start - 15):match_start].strip()

    # Leading currency symbol
    if any(c in leading for c in ("₹", "Rs", "INR", "Rs.")):
        return "INR"

    # Trailing unit checks
    t_lower = trailing.lower()
    if t_lower.startswith("kwh/board"):
        return "kWh/board"
    if t_lower.startswith("kwh/phone"):
        return "kWh/phone"
    if t_lower.startswith("kwh/unit"):
        return "kWh/unit"
    if t_lower.startswith("kwh") or t_lower.startswith("mwh"):
        return "kWh"
    if t_lower.startswith("inr") or t_lower.startswith("rupees"):
        return "INR"
    if t_lower.startswith("kg co2e") or t_lower.startswith("kg") or t_lower.startswith("co2e"):
        return "kg CO2e"
    if t_lower.startswith("%") or t_lower.startswith("percent"):
        return "%"
    if t_lower.startswith("minute") or t_lower.startswith("min"):
        return "minutes"
    if t_lower.startswith("hour") or t_lower.startswith("hr"):
        return "hours"
    if t_lower.startswith("phone") or t_lower.startswith("board") or t_lower.startswith("unit"):
        return "units"
    if t_lower.startswith("anomal") or t_lower.startswith("spike") or t_lower.startswith("outlier"):
        return "anomalies"

    return None


def _infer_metric_from_sentence(
    sentence: str,
    unit: Optional[str],
    match_start: Optional[int] = None,
    match_end: Optional[int] = None,
) -> str:
    """
    Infer the metric category from sentence context words, local match window, and stated unit.
    Enforces DEF-03 (rate separation) and DEF-04 (cumulative vs peak energy separation).
    """
    s_lower = sentence.lower()

    # Clause-bounded localized window around the number token (DEF-01 / DEF-03 / DEF-04)
    if match_start is not None and match_end is not None:
        leading = sentence[max(0, match_start - 35):match_start]
        trailing = sentence[match_end:min(len(sentence), match_end + 30)]
        lead_clause = re.split(r'\b(?:with|and|while|whereas|but)\b|[,;]', leading)[-1]
        trail_clause = re.split(r'\b(?:with|and|while|whereas|but)\b|[,;]', trailing)[0]
        local_window = (lead_clause + " " + sentence[match_start:match_end] + " " + trail_clause).strip().lower()
    else:
        local_window = s_lower

    # 1. SEC metrics (kWh per unit/board/phone)
    if unit in ("kWh/board", "kWh/phone", "kWh/unit"):
        return "sec"
    if "per_board" in local_window or "kwh/board" in local_window:
        return "sec"
    if "per_phone" in local_window or "kwh/phone" in local_window:
        return "sec"
    if "per_unit" in local_window or "kwh/unit" in local_window:
        return "sec"
    if any(w in local_window for w in ("sec", "specific energy")):
        return "sec"

    # 2. Rate / Percentage claims (DEF-03)
    # Check if this token or context represents a rate/percentage
    is_rate = (
        unit == "%"
        or "%" in local_window
        or any(w in local_window for w in ("rate", "percentage", "pct", "yield", "share", "ratio"))
    )

    if is_rate:
        # Check specific rate qualifiers in local window first, fallback to sentence
        ctx = local_window if any(w in local_window for w in (
            "reject", "scrap", "rework", "repair", "good", "yield", "quality",
            "achievement", "target", "share", "of total", "threshold", "downtime"
        )) else s_lower

        if any(w in ctx for w in ("reject", "scrap")):
            return "reject_rate"
        if any(w in ctx for w in ("rework", "repair")):
            return "rework_rate"
        if any(w in ctx for w in ("yield", "good rate", "quality rate", "passed rate")) or (
            "good" in ctx and ("rate" in ctx or "%" in ctx or "unit" not in ctx)
        ):
            return "good_rate"
        if any(w in ctx for w in ("achievement", "target rate", "target achievement")):
            return "achievement_rate"
        if any(w in ctx for w in ("share of total", "share of plant", "percentage of total", "% of total", "area share", "energy share")) or (
            "share" in ctx and ("%" in ctx or "rate" in ctx or "total" in ctx)
        ):
            return "percentage_of_total"
        if any(w in ctx for w in ("below threshold", "low power factor", "low pf")):
            return "percentage_below_threshold"
        if any(w in ctx for w in ("downtime", "stoppage", "outage")) and ("%" in ctx or "rate" in ctx or "pct" in ctx):
            return "percentage_of_downtime"
        return "generic_rate"

    # 3. Currency / Cost
    if unit == "INR" or any(w in local_window for w in ("cost", "bill", "inr", "rupee", "₹")):
        return "cost"

    # 4. Emissions
    if unit == "kg CO2e" or any(w in local_window for w in ("emission", "co2", "carbon")):
        return "emissions"

    # 5. Power Factor
    if "power factor" in local_window or re.search(r'\bpf\b', local_window):
        return "power_factor"

    # 6. Downtime duration
    if unit == "minutes" or any(w in local_window for w in ("downtime", "stoppage", "outage")):
        return "downtime"

    # 7. Energy: Peak vs Cumulative (DEF-04)
    # Check if local window indicates peak energy
    is_peak = any(w in local_window for w in ("peak", "maximum hourly", "max hourly", "highest hourly", "peak hourly"))
    if not is_peak and local_window != s_lower:
        if any(w in s_lower for w in ("peak", "maximum hourly", "max hourly", "highest hourly", "peak hourly")):
            if not any(w in s_lower for w in ("total", "sum", "cumulative", "overall")):
                is_peak = True

    if is_peak:
        if unit == "kWh" or any(w in local_window for w in ("kwh", "energy", "consumption", "power", "demand")) or any(w in s_lower for w in ("kwh", "energy", "consumption")):
            return "peak_energy"

    # Cumulative energy (total/sum/consumption)
    if unit == "kWh" or any(w in local_window for w in ("energy", "consumption", "consumed", "kwh")) or any(w in s_lower for w in ("energy", "consumption", "consumed", "kwh")):
        return "energy"

    # 8. Production Quantities (non-rate discrete units)
    if "target" in local_window:
        return "target_quantity"
    if "good" in local_window or "passed" in local_window:
        return "good_quantity"
    if any(w in local_window for w in ("reject", "scrap", "defect")):
        return "reject_quantity"
    if "rework" in local_window:
        return "rework_quantity"
    if any(w in local_window for w in ("actual", "produced", "output", "manufactured")):
        return "actual_quantity"

    # 9. Anomalies
    if unit == "anomalies" or any(w in local_window for w in ("anomal", "outlier", "spike")):
        return "anomalies"

    # Fallback to full sentence for general concepts if local window had no clues
    if any(w in s_lower for w in ("target",)):
        return "target_quantity"
    if any(w in s_lower for w in ("good", "passed")):
        return "good_quantity"
    if any(w in s_lower for w in ("reject", "scrap", "defect")):
        return "reject_quantity"
    if any(w in s_lower for w in ("rework",)):
        return "rework_quantity"
    if any(w in s_lower for w in ("actual", "produced", "output", "manufactured")):
        return "actual_quantity"

    return "generic"


def _extract_scope_from_sentence(sentence: str) -> Dict[str, Optional[str]]:
    """Extract mentioned plant, line, meter, product, and shift scopes from sentence."""
    s_clean = sentence.upper()
    scope = {
        "plant_id": None,
        "line_id": None,
        "meter_id": None,
        "product_id": None,
        "shift_id": None,
        "date": None,
    }

    # Plants
    for p in ("IN-TN-01", "IN-KA-01"):
        if p in s_clean:
            scope["plant_id"] = p
            break

    # Lines
    for l in ("SMT-L1", "SMT-L2", "FAL-L1", "FAL-L2"):
        if l in s_clean:
            scope["line_id"] = l
            break

    # Meters
    for m in ("MTR-SMT", "MTR-FAL", "MTR-HVAC", "MTR-COMPRESSOR", "MTR-CHILLER"):
        if m in s_clean:
            scope["meter_id"] = m
            break

    # Products
    for pr in ("SPH-A15-128", "SPH-A15-256", "SPH-PRO-256"):
        if pr in s_clean:
            scope["product_id"] = pr
            break

    # Shifts
    for sh in ("SHIFT A", "SHIFT B", "SHIFT C"):
        if sh in s_clean:
            scope["shift_id"] = sh[-1]
            break

    # Date
    date_match = RE_ISO_DATE.search(sentence)
    if date_match:
        scope["date"] = date_match.group(0)

    return scope


def _infer_aggregation_from_sentence(
    sentence: str,
    match_start: Optional[int] = None,
    match_end: Optional[int] = None,
) -> Optional[str]:
    """Infer aggregation type from sentence context words and local match window."""
    s_lower = sentence.lower()
    if match_start is not None and match_end is not None:
        leading = sentence[max(0, match_start - 35):match_start]
        trailing = sentence[match_end:min(len(sentence), match_end + 30)]
        lead_clause = re.split(r'\b(?:with|and|while|whereas|but)\b|[,;]', leading)[-1]
        trail_clause = re.split(r'\b(?:with|and|while|whereas|but)\b|[,;]', trailing)[0]
        local_window = (lead_clause + " " + sentence[match_start:match_end] + " " + trail_clause).strip().lower()
    else:
        local_window = s_lower

    if any(w in local_window for w in ("peak", "highest", "maximum", "max hourly", "peak hourly")):
        return "peak"
    if any(w in local_window for w in ("average", "avg", "mean", "hourly average")):
        return "avg"
    if any(w in local_window for w in ("total", "sum", "cumulative", "overall", "aggregate")):
        return "sum"

    # Fallback to full sentence if local window has no aggregation word
    if any(w in s_lower for w in ("peak", "highest", "maximum", "max hourly", "peak hourly")):
        if not any(w in s_lower for w in ("total", "sum", "cumulative", "overall")):
            return "peak"
    if any(w in s_lower for w in ("average", "avg", "mean", "hourly average")):
        return "avg"
    if any(w in s_lower for w in ("total", "sum", "cumulative", "overall", "aggregate")):
        return "sum"

    return None


def extract_claims(text: str) -> List[ExtractedClaim]:
    """Extract all numerical claims from the assistant response text."""
    claims: List[ExtractedClaim] = []
    sentences = _split_into_sentences(text)

    for sentence in sentences:
        for m in RE_NUMBER.finditer(sentence):
            raw_match = m.group(0)

            # Safely validate grouping and normalize to Decimal (DEF-05)
            is_valid, dec_val, clean_num, token_unit = _normalize_claim_number(raw_match)
            if not is_valid or dec_val is None:
                claims.append(
                    ExtractedClaim(
                        raw_number_str=raw_match,
                        cleaned_number_str=clean_num,
                        claimed_value=Decimal(0),
                        sentence=sentence,
                        is_applicable=False,
                        non_claim_reason="Malformed numeric format or unsupported grouping",
                        start_in_sentence=m.start(),
                        end_in_sentence=m.end(),
                    )
                )
                continue

            # Check if this number is an identifier, date, or non-claim
            is_nc, nc_reason = _is_non_claim(sentence, m.start(), m.end(), clean_num)

            if is_nc:
                claims.append(
                    ExtractedClaim(
                        raw_number_str=raw_match,
                        cleaned_number_str=clean_num,
                        claimed_value=dec_val,
                        sentence=sentence,
                        is_applicable=False,
                        non_claim_reason=nc_reason,
                        start_in_sentence=m.start(),
                        end_in_sentence=m.end(),
                    )
                )
                continue

            unit = token_unit or _infer_unit_from_context(sentence, m.start(), m.end())
            metric = _infer_metric_from_sentence(sentence, unit, m.start(), m.end())
            scope = _extract_scope_from_sentence(sentence)
            agg = _infer_aggregation_from_sentence(sentence, m.start(), m.end())
            if agg is None:
                if metric == "peak_energy":
                    agg = "peak"
                elif metric == "energy":
                    agg = "sum"

            claims.append(
                ExtractedClaim(
                    raw_number_str=raw_match,
                    cleaned_number_str=clean_num,
                    claimed_value=dec_val,
                    sentence=sentence,
                    claimed_unit=unit,
                    claimed_metric=metric,
                    claimed_scope_plant=scope["plant_id"],
                    claimed_scope_meter=scope["meter_id"],
                    claimed_scope_line=scope["line_id"],
                    claimed_scope_product=scope["product_id"],
                    claimed_scope_shift=scope["shift_id"],
                    claimed_date=scope["date"],
                    claimed_aggregation=agg,
                    is_applicable=True,
                    start_in_sentence=m.start(),
                    end_in_sentence=m.end(),
                )
            )

    return claims


# ---------------------------------------------------------------------------
# Verification Logic
# ---------------------------------------------------------------------------

def _values_match(v1: Decimal, v2: Decimal) -> bool:
    """
    Test whether two numerical values match, accounting for legitimate
    rounding and formatting differences (e.g. 12450.50 vs 12450.5023 or 96 vs 96.04).
    """
    if v1 == v2:
        return True

    # Check standard roundings to 0, 1, 2, or 4 places
    for places in (0, 1, 2, 4):
        if round(v2, places) == v1 or round(v1, places) == v2:
            return True

    # Relative tolerance: 0.2% difference or 0.01 absolute
    diff = abs(v1 - v2)
    max_val = max(abs(v1), abs(v2))
    if max_val > 0 and (diff / max_val) <= Decimal("0.002"):
        return True
    if diff <= Decimal("0.01"):
        return True

    return False


def _categories_compatible(cat1: str, cat2: str) -> bool:
    """
    Check if claimed metric category is compatible with authoritative fact category.
    Enforces DEF-03 (rate separation) and DEF-04 (cumulative vs peak energy separation).
    """
    if cat1 == "generic" or cat2 == "generic":
        return True
    if cat1 == cat2:
        return True

    # Yield rate and good rate are mutual aliases (DEF-03)
    if {cat1, cat2} <= {"good_rate", "yield_rate"}:
        return True

    # Incompatible rate categories must NEVER match each other (DEF-03)
    if cat1 in ALL_RATE_CATEGORIES or cat2 in ALL_RATE_CATEGORIES:
        return False

    # Cumulative energy and peak energy must NEVER match each other (DEF-04)
    if {cat1, cat2} & {"energy", "peak_energy"}:
        return False

    # Production quantity grouping
    production_group = {
        "production", "actual_quantity", "target_quantity",
        "good_quantity", "reject_quantity", "rework_quantity",
    }
    if cat1 in production_group and cat2 in production_group:
        return cat1 == cat2 or cat1 == "production" or cat2 == "production"

    return False


def _units_compatible(u1: Optional[str], u2: Optional[str]) -> bool:
    """Check if claimed unit matches authoritative unit."""
    if not u1 or not u2:
        return True  # If one is unstated, pass to avoid penalizing implicit units
    n1 = UNIT_NORMALIZATION.get(u1.lower(), u1.lower())
    n2 = UNIT_NORMALIZATION.get(u2.lower(), u2.lower())
    return n1 == n2


def _aggregations_compatible(claimed_agg: Optional[str], fact_agg: Optional[str]) -> bool:
    """
    Check if aggregation semantics are compatible (DEF-02 & DEF-04):
    - Peak facts require peak claims. A claim cannot match a peak fact without peak semantics.
    - Cumulative claims (total, sum) must not match peak or average facts.
    - Average claims must not match sum or peak facts.
    """
    if claimed_agg == "peak" or fact_agg == "peak":
        return claimed_agg == fact_agg
    if not claimed_agg or not fact_agg:
        return True
    if claimed_agg == "sum" and fact_agg != "sum":
        return False
    if claimed_agg == "avg" and fact_agg != "avg":
        return False
    return claimed_agg == fact_agg


def _is_scope_granularity_compatible(claim: ExtractedClaim, fact: AuthoritativeFact) -> Tuple[bool, Optional[str]]:
    """
    Verify scope and granularity compatibility (DEF-02):
    - Sub-entity levels (meter, line, product, shift) must match exactly if specified.
    - An aggregate/plant-wide claim (where meter/line/product/shift is None) must NEVER
      be verified or corrected using an individual sub-entity reading (meter or line).
    - An individual sub-entity claim must NEVER be verified or corrected using a plant-wide aggregate.
    - Date scopes must match if specified.
    """
    # 1. Meter scope
    if claim.claimed_scope_meter:
        if not fact.meter_id:
            return False, f"Claim specifies meter '{claim.claimed_scope_meter}', but evidence is aggregate without meter"
        if claim.claimed_scope_meter != fact.meter_id:
            return False, f"Meter mismatch (claim: '{claim.claimed_scope_meter}', evidence: '{fact.meter_id}')"
    elif fact.meter_id:
        return False, f"Claim is plant-level/unscoped to meter, but evidence is for specific meter '{fact.meter_id}'"

    # 2. Line scope
    if claim.claimed_scope_line:
        if not fact.line_id:
            return False, f"Claim specifies line '{claim.claimed_scope_line}', but evidence is aggregate without line"
        if claim.claimed_scope_line != fact.line_id:
            return False, f"Line mismatch (claim: '{claim.claimed_scope_line}', evidence: '{fact.line_id}')"
    elif fact.line_id:
        return False, f"Claim is plant-level/unscoped to line, but evidence is for specific line '{fact.line_id}'"

    # 3. Product scope
    if claim.claimed_scope_product:
        if not fact.product_id:
            return False, f"Claim specifies product '{claim.claimed_scope_product}', but evidence is without product"
        if claim.claimed_scope_product != fact.product_id:
            return False, f"Product mismatch (claim: '{claim.claimed_scope_product}', evidence: '{fact.product_id}')"
    elif fact.product_id:
        return False, f"Claim is unscoped to product, but evidence is for specific product '{fact.product_id}'"

    # 4. Shift scope
    if claim.claimed_scope_shift:
        if not fact.shift_id:
            return False, f"Claim specifies shift '{claim.claimed_scope_shift}', but evidence is without shift"
        if claim.claimed_scope_shift != fact.shift_id:
            return False, f"Shift mismatch (claim: '{claim.claimed_scope_shift}', evidence: '{fact.shift_id}')"
    elif fact.shift_id:
        return False, f"Claim is unscoped to shift, but evidence is for specific shift '{fact.shift_id}'"

    # 5. Plant scope
    if claim.claimed_scope_plant and fact.plant_id:
        if claim.claimed_scope_plant != fact.plant_id:
            return False, f"Plant mismatch (claim: '{claim.claimed_scope_plant}', evidence: '{fact.plant_id}')"

    # 6. Date scope
    if claim.claimed_date and fact.exact_date:
        if claim.claimed_date != fact.exact_date:
            return False, f"Date mismatch (claim: '{claim.claimed_date}', evidence: '{fact.exact_date}')"
    elif fact.exact_date and not claim.claimed_date:
        return False, f"Claim has no date, but evidence is for specific date '{fact.exact_date}'"

    return True, None


def _scopes_compatible(claim: ExtractedClaim, fact: AuthoritativeFact) -> Tuple[bool, Optional[str]]:
    """Legacy alias redirecting to granular scope verification."""
    return _is_scope_granularity_compatible(claim, fact)


def verify_claims(
    claims: List[ExtractedClaim],
    facts: List[AuthoritativeFact],
) -> List[ClaimVerificationResult]:
    """
    Deterministically compare each numerical claim with authoritative tool evidence.
    Enforces DEF-02: Strict scope granularity, aggregation, and unambiguous candidate selection.
    """
    results: List[ClaimVerificationResult] = []

    for c in claims:
        # Non-claims are immediately NOT_APPLICABLE
        if not c.is_applicable:
            results.append(
                ClaimVerificationResult(
                    claimed_number=c.raw_number_str,
                    sentence=c.sentence,
                    outcome=VerificationOutcome.NOT_APPLICABLE,
                    explanation=c.non_claim_reason or "Non-analytical number",
                    start_in_sentence=c.start_in_sentence,
                    end_in_sentence=c.end_in_sentence,
                )
            )
            continue

        scope_desc = c.claimed_scope_plant or c.claimed_scope_line or c.claimed_scope_meter or "unspecified"
        claimed_metric = c.claimed_metric or "generic"

        # Special handling for generic_rate (DEF-03):
        # A claim specifying a generic rate or percentage without qualification cannot be verified
        # if multiple distinct rate categories exist in evidence, resolving to UNVERIFIED.
        if claimed_metric == "generic_rate":
            rate_facts = [f for f in facts if f.metric_category in ALL_SPECIFIC_RATE_CATEGORIES]
            distinct_rate_cats = {f.metric_category for f in rate_facts}
            if len(distinct_rate_cats) > 1:
                results.append(
                    ClaimVerificationResult(
                        claimed_number=c.raw_number_str,
                        sentence=c.sentence,
                        metric="generic_rate",
                        unit=c.claimed_unit,
                        scope=scope_desc,
                        outcome=VerificationOutcome.UNVERIFIED,
                        explanation=(
                            f"Claim specifies a generic rate or percentage without identifying the rate type, "
                            f"while evidence contains multiple distinct rate metrics "
                            f"({', '.join(sorted(distinct_rate_cats))}), making authoritative resolution ambiguous."
                        ),
                        start_in_sentence=c.start_in_sentence,
                        end_in_sentence=c.end_in_sentence,
                        can_auto_correct=False,
                    )
                )
                continue
            elif len(distinct_rate_cats) == 1:
                # Exactly one rate category exists in evidence
                single_cat = next(iter(distinct_rate_cats))
                matching_category_facts = [f for f in rate_facts if f.metric_category == single_cat]
            else:
                matching_category_facts = []
        else:
            # 1. Candidate facts that match metric category
            matching_category_facts = [
                f for f in facts if _categories_compatible(claimed_metric, f.metric_category)
            ]

        # 2. Check for exact or rounded value match
        found_verified_fact: Optional[AuthoritativeFact] = None
        scope_mismatch_fact: Optional[Tuple[AuthoritativeFact, str]] = None
        unit_mismatch_fact: Optional[AuthoritativeFact] = None

        # Check facts in matching category
        for f in matching_category_facts:
            if _values_match(c.claimed_value, f.value):
                # Value matches! Check unit, aggregation, and scope granularity
                if not _units_compatible(c.claimed_unit, f.unit):
                    unit_mismatch_fact = f
                    continue

                if not _aggregations_compatible(c.claimed_aggregation, f.aggregation):
                    continue

                scope_ok, scope_err = _is_scope_granularity_compatible(c, f)
                if not scope_ok:
                    scope_mismatch_fact = (f, scope_err or "Scope differs")
                    continue

                # Complete match!
                found_verified_fact = f
                break

        if found_verified_fact is not None:
            results.append(
                ClaimVerificationResult(
                    claimed_number=c.raw_number_str,
                    sentence=c.sentence,
                    metric=claimed_metric,
                    unit=c.claimed_unit or found_verified_fact.unit,
                    scope=scope_desc,
                    outcome=VerificationOutcome.VERIFIED,
                    authoritative_value=str(found_verified_fact.value),
                    authoritative_unit=found_verified_fact.unit,
                    supporting_tool=found_verified_fact.tool_name,
                    explanation=f"Matches verified {found_verified_fact.metric_name} ({found_verified_fact.value} {found_verified_fact.unit or ''}) from {found_verified_fact.tool_name}.",
                    start_in_sentence=c.start_in_sentence,
                    end_in_sentence=c.end_in_sentence,
                    can_auto_correct=False,
                )
            )
            continue

        # If value matched but unit was incompatible
        if unit_mismatch_fact is not None:
            results.append(
                ClaimVerificationResult(
                    claimed_number=c.raw_number_str,
                    sentence=c.sentence,
                    metric=claimed_metric,
                    unit=c.claimed_unit,
                    scope=scope_desc,
                    outcome=VerificationOutcome.UNIT_MISMATCH,
                    authoritative_value=str(unit_mismatch_fact.value),
                    authoritative_unit=unit_mismatch_fact.unit,
                    supporting_tool=unit_mismatch_fact.tool_name,
                    explanation=f"Value {c.claimed_value} exists in {unit_mismatch_fact.tool_name}, but with incompatible unit '{unit_mismatch_fact.unit}' vs claimed '{c.claimed_unit}'.",
                    start_in_sentence=c.start_in_sentence,
                    end_in_sentence=c.end_in_sentence,
                    can_auto_correct=False,
                )
            )
            continue

        # If value matched but scope differed
        if scope_mismatch_fact is not None:
            f_mismatch, err_detail = scope_mismatch_fact
            results.append(
                ClaimVerificationResult(
                    claimed_number=c.raw_number_str,
                    sentence=c.sentence,
                    metric=claimed_metric,
                    unit=c.claimed_unit,
                    scope=scope_desc,
                    outcome=VerificationOutcome.SCOPE_MISMATCH,
                    authoritative_value=str(f_mismatch.value),
                    authoritative_unit=f_mismatch.unit,
                    supporting_tool=f_mismatch.tool_name,
                    explanation=f"Value {c.claimed_value} matches {f_mismatch.metric_name}, but scope conflicts: {err_detail}.",
                    start_in_sentence=c.start_in_sentence,
                    end_in_sentence=c.end_in_sentence,
                    can_auto_correct=False,
                )
            )
            continue

        # 3. Check for CONFLICTING claims (DEF-02):
        # Require compatibility of metric, unit, aggregation, date, and scope granularity.
        # Never select the first candidate merely because it appears first.
        candidate_conflicts: List[AuthoritativeFact] = []
        for f in matching_category_facts:
            scope_ok, _ = _is_scope_granularity_compatible(c, f)
            if not scope_ok:
                continue
            if not _units_compatible(c.claimed_unit, f.unit):
                continue
            if not _aggregations_compatible(c.claimed_aggregation, f.aggregation):
                continue
            candidate_conflicts.append(f)

        if len(candidate_conflicts) == 1:
            # Unambiguous single candidate!
            conflicting_fact = candidate_conflicts[0]
            # Generic rate claims should never be auto-corrected into a specific rate metric
            can_correct = True if claimed_metric != "generic_rate" else False
            results.append(
                ClaimVerificationResult(
                    claimed_number=c.raw_number_str,
                    sentence=c.sentence,
                    metric=claimed_metric,
                    unit=c.claimed_unit or conflicting_fact.unit,
                    scope=scope_desc,
                    outcome=VerificationOutcome.CONFLICTING,
                    authoritative_value=str(conflicting_fact.value),
                    authoritative_unit=conflicting_fact.unit,
                    supporting_tool=conflicting_fact.tool_name,
                    explanation=f"Evidence from '{conflicting_fact.tool_name}' reports {conflicting_fact.metric_name} = {conflicting_fact.value} {conflicting_fact.unit or ''}, contradicting claimed {c.raw_number_str}.",
                    start_in_sentence=c.start_in_sentence,
                    end_in_sentence=c.end_in_sentence,
                    can_auto_correct=can_correct,
                )
            )
            continue
        elif len(candidate_conflicts) > 1:
            # Multiple candidates exist! Check if all candidates are demonstrably equivalent in value and unit
            all_same_value = all(f.value == candidate_conflicts[0].value for f in candidate_conflicts)
            all_same_unit = all(f.unit == candidate_conflicts[0].unit for f in candidate_conflicts)

            if all_same_value and all_same_unit:
                # Value is identical across equivalent facts, but we qualify rather than auto-correct
                conflicting_fact = candidate_conflicts[0]
                results.append(
                    ClaimVerificationResult(
                        claimed_number=c.raw_number_str,
                        sentence=c.sentence,
                        metric=claimed_metric,
                        unit=c.claimed_unit or conflicting_fact.unit,
                        scope=scope_desc,
                        outcome=VerificationOutcome.CONFLICTING,
                        authoritative_value=str(conflicting_fact.value),
                        authoritative_unit=conflicting_fact.unit,
                        supporting_tool=conflicting_fact.tool_name,
                        explanation=f"Evidence reports {conflicting_fact.metric_name} = {conflicting_fact.value} {conflicting_fact.unit or ''}, contradicting claimed {c.raw_number_str}.",
                        start_in_sentence=c.start_in_sentence,
                        end_in_sentence=c.end_in_sentence,
                        can_auto_correct=False,  # Ambiguous multi-fact source: qualify rather than auto-correct
                    )
                )
                continue
            else:
                # Multiple candidates with differing values: ambiguous!
                # Never select the first candidate; classify as UNVERIFIED
                results.append(
                    ClaimVerificationResult(
                        claimed_number=c.raw_number_str,
                        sentence=c.sentence,
                        metric=claimed_metric,
                        unit=c.claimed_unit,
                        scope=scope_desc,
                        outcome=VerificationOutcome.UNVERIFIED,
                        explanation=f"Multiple candidate facts exist with differing values for metric '{claimed_metric}' in scope '{scope_desc}', making authoritative resolution ambiguous.",
                        start_in_sentence=c.start_in_sentence,
                        end_in_sentence=c.end_in_sentence,
                        can_auto_correct=False,
                    )
                )
                continue

        # 4. Otherwise, claim is UNVERIFIED (no supporting evidence found)
        results.append(
            ClaimVerificationResult(
                claimed_number=c.raw_number_str,
                sentence=c.sentence,
                metric=claimed_metric,
                unit=c.claimed_unit,
                scope=scope_desc,
                outcome=VerificationOutcome.UNVERIFIED,
                explanation=f"No successful tool results in the current turn provide evidence for metric '{claimed_metric}' with value {c.raw_number_str}.",
                start_in_sentence=c.start_in_sentence,
                end_in_sentence=c.end_in_sentence,
                can_auto_correct=False,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Response Qualification & Correction
# ---------------------------------------------------------------------------

def correct_or_qualify_response(
    answer: str,
    verifications: List[ClaimVerificationResult],
) -> str:
    """
    Apply safe deterministic adjustments to response (DEF-01):
    1. Only conflicting claims with can_auto_correct=True, authoritative_value,
       and authoritative_unit are eligible for automatic replacement.
    2. Replacement is strictly scoped to the exact sentence and exact character token
       associated with the claim.
    3. Safe token-boundary validation ensures a number like '5' cannot modify '50',
       '2026-05-15', or '240'.
    4. Repeated numeric values in the same sentence are handled by processing
       token spans in descending order (right-to-left) without offset drift.
    5. If the exact claim occurrence or sentence cannot be identified unambiguously,
       do not automatically replace it. Retain original response and qualify via notice.
    """
    updated_answer = answer
    unverified_items: List[ClaimVerificationResult] = []

    # Group eligible conflicting claims by sentence
    conflicts_by_sentence: Dict[str, List[ClaimVerificationResult]] = {}
    for v in verifications:
        if (
            v.outcome == VerificationOutcome.CONFLICTING
            and getattr(v, "can_auto_correct", False)
            and v.authoritative_value
            and v.authoritative_unit
            and v.sentence
        ):
            conflicts_by_sentence.setdefault(v.sentence, []).append(v)
        elif v.outcome != VerificationOutcome.VERIFIED and v.outcome != VerificationOutcome.NOT_APPLICABLE:
            unverified_items.append(v)

    # Process each sentence that contains conflicting claims
    for orig_sentence, claim_list in conflicts_by_sentence.items():
        # Check that sentence appears uniquely in updated_answer
        if updated_answer.count(orig_sentence) != 1:
            # Ambiguous sentence occurrence in answer! Fallback to qualification
            unverified_items.extend(claim_list)
            continue

        # Sort claims within this sentence in descending order of start_in_sentence (right-to-left)
        # to ensure that earlier token offsets remain valid during replacement.
        claim_list.sort(key=lambda x: getattr(x, "start_in_sentence", -1), reverse=True)

        # Pre-validate all claims in this sentence before modifying anything
        sentence_valid = True
        for v in claim_list:
            start = getattr(v, "start_in_sentence", -1)
            end = getattr(v, "end_in_sentence", -1)

            if start < 0 or end <= start or end > len(orig_sentence):
                sentence_valid = False
                break

            # Verify that the exact slice in orig_sentence matches the claimed token
            if orig_sentence[start:end] != v.claimed_number:
                sentence_valid = False
                break

            # Safe token-boundary check: ensure number is not part of a larger number or date/identifier
            left_char = orig_sentence[start - 1] if start > 0 else " "
            right_char = orig_sentence[end] if end < len(orig_sentence) else " "

            # Cannot be preceded or followed by digits or letters or hyphens
            if left_char.isalnum() or left_char in "-_":
                sentence_valid = False
                break
            if right_char.isalnum() or right_char in "-_":
                sentence_valid = False
                break

        if not sentence_valid:
            # Token boundaries or positions failed validation: do not auto-correct!
            unverified_items.extend(claim_list)
            continue

        # All claims in this sentence validated safely! Apply right-to-left replacement:
        cur_sentence = orig_sentence
        for v in claim_list:
            start = v.start_in_sentence
            end = v.end_in_sentence
            replacement = f"{v.authoritative_value} {v.authoritative_unit} [Verified from {v.supporting_tool}]"

            cur_sentence = cur_sentence[:start] + replacement + cur_sentence[end:]
            v.was_corrected = True
            v.outcome = VerificationOutcome.VERIFIED
            v.explanation += f" (Corrected from {v.claimed_number} to {v.authoritative_value} {v.authoritative_unit})"

        # Replace the single occurrence of orig_sentence in updated_answer
        updated_answer = updated_answer.replace(orig_sentence, cur_sentence, 1)

    # If unverified claims remain, attach a transparent qualification notice
    if unverified_items:
        notice_lines = [
            "\n\n> [!WARNING] **Data Verification Notice:** The following numerical claim(s) could not be authoritatively verified against backend tool evidence:",
        ]
        for it in unverified_items:
            m_label = it.metric or "metric"
            u_label = f" {it.unit}" if it.unit else ""
            notice_lines.append(f"> - **{it.claimed_number}{u_label}** ({m_label}): {it.explanation}")
        notice_lines.append("> Non-verified figures should not be treated as authoritative plant measurements.")
        updated_answer += "\n".join(notice_lines)

    return updated_answer


# ---------------------------------------------------------------------------
# Main Verification Pipeline Entry Point
# ---------------------------------------------------------------------------

def verify_numeric_claims(
    answer: str,
    evidence: List[Any],
    user_question: Optional[str] = None,
) -> VerificationResponse:
    """
    End-to-end deterministic verification pipeline for AI Assistant responses.

    1. Extracts authoritative facts from successful ToolEvidence records in the current turn.
    2. Identifies all numerical claims and classifies non-claims as NOT_APPLICABLE.
    3. Compares each claim with authoritative facts checking metric, value, unit, and scope.
    4. Computes verification summary.
    5. Applies deterministic correction/qualification to the final answer.
    """
    # 1. Harvest facts from current turn evidence
    facts = extract_authoritative_facts(evidence)

    # 2. Extract claims from response
    claims = extract_claims(answer)

    # 3. Perform deterministic verification
    verifications = verify_claims(claims, facts)

    # 4. Correct or qualify response text
    final_answer = correct_or_qualify_response(answer, verifications)

    # 5. Compile summary statistics (DEF-06)
    # Exclude non-claims (NOT_APPLICABLE) from applicable claims
    applicable_claims = [v for v in verifications if v.outcome != VerificationOutcome.NOT_APPLICABLE]
    # Verified claims count (including successfully corrected claims)
    verified_count = sum(1 for v in applicable_claims if v.outcome == VerificationOutcome.VERIFIED)
    # Unverified claims: every applicable claim whose final outcome is not VERIFIED (DEF-06)
    # Strictly maintains invariant: total_claims = verified_claims + unverified_claims
    unverified_count = sum(1 for v in applicable_claims if v.outcome != VerificationOutcome.VERIFIED)
    conflicting_count = sum(1 for v in applicable_claims if v.outcome == VerificationOutcome.CONFLICTING)
    scope_mismatch_count = sum(1 for v in applicable_claims if v.outcome == VerificationOutcome.SCOPE_MISMATCH)
    unit_mismatch_count = sum(1 for v in applicable_claims if v.outcome == VerificationOutcome.UNIT_MISMATCH)
    not_applicable_count = sum(1 for v in verifications if v.outcome == VerificationOutcome.NOT_APPLICABLE)

    if not applicable_claims:
        status_label = "NO_ANALYTIC_CLAIMS"
    elif verified_count == len(applicable_claims):
        status_label = "VERIFIED"
    elif conflicting_count > 0:
        status_label = "CONFLICT_DETECTED"
    elif verified_count > 0:
        status_label = "PARTIALLY_VERIFIED"
    else:
        status_label = "UNVERIFIED"

    supporting_tools = sorted(list({f.tool_name for f in facts}))

    summary = VerificationSummary(
        status=status_label,
        total_claims=len(applicable_claims),
        verified_claims=verified_count,
        unverified_claims=unverified_count,
        conflicting_claims=conflicting_count,
        scope_mismatches=scope_mismatch_count,
        unit_mismatches=unit_mismatch_count,
        not_applicable_count=not_applicable_count,
        supported_by_tools=supporting_tools,
    )

    return VerificationResponse(
        final_answer=final_answer,
        summary=summary,
        claims=verifications,
    )

