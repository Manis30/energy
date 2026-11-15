"""
Baseline Qualification Engine for Industrial Energy Intelligence Platform.

This module provides a deterministic, data-driven qualification mechanism to
evaluate whether historical energy consumption data is sufficiently robust, continuous,
and trustworthy to serve as an operational baseline.

Qualification Dimensions:
1. Strict Temporal Separation: Baseline window must strictly precede evaluation period (anti-leakage).
2. Data Completeness & Duration-Aware Sufficiency: Dynamically evaluated sample count and temporal coverage.
3. Continuity & Gaps: Maximum contiguous missing telemetry span analysis including leading/trailing edges.
4. Physical & Data Integrity: Non-negativity, zero-variance flatline detection using unrounded standard deviation.
5. Sensor Reading Quality: Evaluated conditionally without penalizing missing metadata; reports partial coverage.
6. Schema-Bounded Transparency: Explicitly reporting unavailable dimensions (weather, schedules,
   independent peak demand, undefined plant boundaries) rather than assuming or fabricating them.

Discrete Outcomes:
- QUALIFIED: Dataset satisfies all data integrity, sample sufficiency, and continuity requirements.
- NOT_QUALIFIED: Dataset violates critical integrity constraints or falls below absolute minimum floors.
- INCONCLUSIVE: Dataset exhibits no corruptions but suffers from marginal sample size or elevated intermittency.

Design Principles:
- Pure Core Logic: The qualification assessment engine is pure and independently reusable without DB access.
- Hard Failures vs. Configurable Thresholds: Hard mathematical/physical impossibilities (e.g., negative
  readings, zero variance, temporal overlap) are separated from tuneable engineering thresholds.
- Independent of Production Dependency: Energy consumption is NOT assumed to be production-dependent.
- Zero Predictive / Savings Fabrications: No savings or synthetic predictions are generated.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.source_data import FactEnergyMeterHourly


class BaselineQualificationStatus(str, Enum):
    """Discrete outcome states for baseline qualification."""

    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"


class QualificationReasonCode(str, Enum):
    """
    Standardized machine- and human-readable reason codes explaining qualification outcomes.
    
    Categorized into:
    - Positive validation signals (surfaced only in qualifying_signals and QUALIFIED outcomes)
    - Hard data-integrity failures (NOT_QUALIFIED)
    - Borderline or degraded conditions (INCONCLUSIVE)
    - Informational advisories (does not downgrade qualification status)
    """

    # --- Positive Validation Signals ---
    BASELINE_CRITERIA_MET = "BASELINE_CRITERIA_MET"
    SUFFICIENT_HISTORICAL_DATA = "SUFFICIENT_HISTORICAL_DATA"
    EXCELLENT_DATA_CONTINUITY = "EXCELLENT_DATA_CONTINUITY"
    HIGH_READING_QUALITY = "HIGH_READING_QUALITY"

    # --- Hard Data-Integrity Failures (NOT_QUALIFIED) ---
    TEMPORAL_SEQUENCE_VIOLATION = "TEMPORAL_SEQUENCE_VIOLATION"
    NEGATIVE_CONSUMPTION_DETECTED = "NEGATIVE_CONSUMPTION_DETECTED"
    ZERO_VARIANCE_FLATLINE = "ZERO_VARIANCE_FLATLINE"
    CRITICAL_INSUFFICIENT_HISTORY = "CRITICAL_INSUFFICIENT_HISTORY"
    CRITICAL_DATA_SPARSITY = "CRITICAL_DATA_SPARSITY"
    EXCESSIVE_CONTIGUOUS_GAP = "EXCESSIVE_CONTIGUOUS_GAP"
    POOR_READING_QUALITY = "POOR_READING_QUALITY"
    EMPTY_BASELINE_PERIOD = "EMPTY_BASELINE_PERIOD"
    INVALID_WINDOW_BOUNDS = "INVALID_WINDOW_BOUNDS"
    PLANT_METER_BOUNDARY_UNDEFINED = "PLANT_METER_BOUNDARY_UNDEFINED"
    INCOMPLETE_METER_PARTICIPATION = "INCOMPLETE_METER_PARTICIPATION"

    # --- Borderline / Degraded Telemetry Conditions (INCONCLUSIVE) ---
    MARGINAL_OBSERVATION_COUNT = "MARGINAL_OBSERVATION_COUNT"
    SUBTARGET_COMPLETENESS = "SUBTARGET_COMPLETENESS"
    MODERATE_TELEMETRY_INTERMITTENCY = "MODERATE_TELEMETRY_INTERMITTENCY"
    DEGRADED_READING_QUALITY = "DEGRADED_READING_QUALITY"
    PARTIAL_READING_QUALITY_COVERAGE = "PARTIAL_READING_QUALITY_COVERAGE"
    DUPLICATE_TIMESTAMPS_DETECTED = "DUPLICATE_TIMESTAMPS_DETECTED"

    # --- Informational Advisory Signals (Does NOT downgrade status) ---
    HIGH_VOLATILITY_WARNING = "HIGH_VOLATILITY_WARNING"


# Sets of reason codes defining deterministic outcome triggers
HARD_FAILURE_CODES: Set[QualificationReasonCode] = {
    QualificationReasonCode.TEMPORAL_SEQUENCE_VIOLATION,
    QualificationReasonCode.NEGATIVE_CONSUMPTION_DETECTED,
    QualificationReasonCode.ZERO_VARIANCE_FLATLINE,
    QualificationReasonCode.CRITICAL_INSUFFICIENT_HISTORY,
    QualificationReasonCode.CRITICAL_DATA_SPARSITY,
    QualificationReasonCode.EXCESSIVE_CONTIGUOUS_GAP,
    QualificationReasonCode.POOR_READING_QUALITY,
    QualificationReasonCode.EMPTY_BASELINE_PERIOD,
    QualificationReasonCode.INVALID_WINDOW_BOUNDS,
    QualificationReasonCode.PLANT_METER_BOUNDARY_UNDEFINED,
    QualificationReasonCode.INCOMPLETE_METER_PARTICIPATION,
}

DEGRADATION_WARNING_CODES: Set[QualificationReasonCode] = {
    QualificationReasonCode.MARGINAL_OBSERVATION_COUNT,
    QualificationReasonCode.SUBTARGET_COMPLETENESS,
    QualificationReasonCode.MODERATE_TELEMETRY_INTERMITTENCY,
    QualificationReasonCode.DEGRADED_READING_QUALITY,
    QualificationReasonCode.PARTIAL_READING_QUALITY_COVERAGE,
    QualificationReasonCode.DUPLICATE_TIMESTAMPS_DETECTED,
}

INFORMATIONAL_CODES: Set[QualificationReasonCode] = {
    QualificationReasonCode.HIGH_VOLATILITY_WARNING,
}


@dataclass(frozen=True)
class QualificationThresholds:
    """
    Configurable engineering parameters for baseline qualification.

    IMPORTANT NOTE:
    These default values are internal engineering defaults, NOT approved business
    rules or regulatory mandates. Platform operators and analytics engineers should
    configure these thresholds based on meter criticality, sampling interval, and
    operational tolerances.
    """

    # Absolute minimum observation floor (N >= 2 required mathematically for sample variance)
    min_observations: int = 10

    # Target observation count or dynamic duration-scaled requirement.
    # If target_observations is None (default), the target is dynamically derived from:
    #   max(min_observations, math.ceil(expected_hours * target_observation_ratio))
    # This scales observation sufficiency proportionally with baseline window duration.
    target_observations: Optional[int] = None

    # Ratio of expected hours required for target observation sufficiency when dynamically derived.
    target_observation_ratio: float = 0.85

    # Minimum data completeness ratio (N_observed / N_expected) below which data is NOT_QUALIFIED
    min_completeness_ratio: float = 0.50

    # Target data completeness ratio required for QUALIFIED status (between min and target is INCONCLUSIVE)
    target_completeness_ratio: float = 0.85

    # Maximum contiguous missing hours before flagging moderate intermittency (INCONCLUSIVE)
    max_gap_warning_hours: int = 12

    # Hard maximum contiguous missing hours before failing qualification (NOT_QUALIFIED)
    max_gap_failure_hours: int = 48

    # Reading quality thresholds
    # Minimum coverage ratio of quality metadata required before enforcing quality thresholds
    min_quality_coverage_ratio: float = 0.50

    # Minimum valid reading ratio among evaluated quality readings
    min_valid_reading_ratio: float = 0.80
    target_valid_reading_ratio: float = 0.95

    # Approved quality string values (case-insensitive); defaults to {"VALID"} from source data
    approved_reading_qualities: Optional[Set[str]] = None

    # Minimum standard deviation below which data is considered zero variance / sensor flatline
    min_std_dev: float = 1e-6

    # Maximum coefficient of variation (std_dev / mean) before triggering informational volatility flag
    # NOTE: High CV is purely informational and does NOT downgrade qualification status.
    max_coefficient_of_variation: Optional[float] = 3.0


@dataclass
class BaselineObservation:
    """Individual timestamped energy observation for baseline qualification."""

    timestamp: datetime
    consumption_kwh: Decimal
    reading_quality: Optional[str] = None
    meter_id: Optional[str] = None
    plant_id: Optional[str] = None


@dataclass
class BaselineMetrics:
    """
    Deterministic empirical metrics derived from historical baseline telemetry.
    
    Includes schema-bounded availability flags for unsupported dimensions.
    """

    # Sample counts and completeness
    expected_hours: int
    observed_hours: int
    completeness_ratio: Optional[float]
    completeness_status: str  # "EVALUATED" or "UNAVAILABLE"
    effective_target_observations: int
    missing_hours: int
    max_contiguous_gap_hours: int

    # Statistical distribution (Decimal for precision)
    mean_consumption_kwh: Optional[Decimal]
    std_consumption_kwh: Optional[Decimal]
    min_consumption_kwh: Optional[Decimal]
    max_consumption_kwh: Optional[Decimal]
    median_consumption_kwh: Optional[Decimal]
    coefficient_of_variation: Optional[float]

    # Data integrity signals
    negative_readings_count: int
    zero_readings_count: int
    duplicate_timestamps_count: int
    is_zero_variance: bool
    temporal_separation_hours: Optional[float]

    # Reading quality signals (telemetry-dependent)
    quality_evaluated_count: Optional[int]
    quality_coverage_ratio: Optional[float]
    valid_readings_count: Optional[int]
    valid_readings_ratio: Optional[float]
    reading_quality_status: str  # "EVALUATED", "PARTIAL_COVERAGE", or "UNAVAILABLE"

    # Plant-level boundary audit signals
    plant_meter_boundary_status: str  # "SINGLE_METER", "EXPLICIT_BOUNDARIES", or "UNDEFINED"
    incomplete_meter_hours_count: Optional[int] = None

    # Explicit schema availability indicators
    weather_normalization_status: str = "UNAVAILABLE"
    schedule_normalization_status: str = "UNAVAILABLE"
    independent_peak_demand_status: str = "UNAVAILABLE"
    production_dependency_evaluated: bool = False


@dataclass
class BaselineQualificationResult:
    """Comprehensive structured outcome of baseline qualification evaluation."""

    status: BaselineQualificationStatus
    reason_codes: List[QualificationReasonCode]
    hard_failures: List[QualificationReasonCode]
    warnings: List[QualificationReasonCode]
    informational_flags: List[QualificationReasonCode]
    qualifying_signals: List[QualificationReasonCode]
    metrics: BaselineMetrics
    thresholds: QualificationThresholds
    plant_id: Optional[str] = None
    meter_id: Optional[str] = None
    meter_ids: Optional[List[str]] = None
    baseline_start: Optional[datetime] = None
    baseline_end: Optional[datetime] = None
    evaluation_start: Optional[datetime] = None
    evaluation_end: Optional[datetime] = None
    summary: str = ""

    @property
    def is_qualified(self) -> bool:
        """Convenience property indicating whether baseline is fully qualified."""
        return self.status == BaselineQualificationStatus.QUALIFIED

    def to_dict(self) -> Dict[str, Any]:
        """Convert result into a JSON-serializable dictionary."""
        completeness_ratio_val = (
            round(self.metrics.completeness_ratio, 4)
            if self.metrics.completeness_ratio is not None
            else None
        )
        return {
            "status": self.status.value,
            "is_qualified": self.is_qualified,
            "plant_id": self.plant_id,
            "meter_id": self.meter_id,
            "meter_ids": self.meter_ids,
            "baseline_start": self.baseline_start.isoformat() if self.baseline_start else None,
            "baseline_end": self.baseline_end.isoformat() if self.baseline_end else None,
            "evaluation_start": self.evaluation_start.isoformat() if self.evaluation_start else None,
            "evaluation_end": self.evaluation_end.isoformat() if self.evaluation_end else None,
            "reason_codes": [rc.value for rc in self.reason_codes],
            "hard_failures": [rc.value for rc in self.hard_failures],
            "warnings": [rc.value for rc in self.warnings],
            "informational_flags": [rc.value for rc in self.informational_flags],
            "qualifying_signals": [rc.value for rc in self.qualifying_signals],
            "summary": self.summary,
            "metrics": {
                "expected_hours": self.metrics.expected_hours,
                "observed_hours": self.metrics.observed_hours,
                "effective_target_observations": self.metrics.effective_target_observations,
                "completeness_ratio": completeness_ratio_val,
                "completeness_status": self.metrics.completeness_status,
                "missing_hours": self.metrics.missing_hours,
                "max_contiguous_gap_hours": self.metrics.max_contiguous_gap_hours,
                "mean_consumption_kwh": float(self.metrics.mean_consumption_kwh) if self.metrics.mean_consumption_kwh is not None else None,
                "std_consumption_kwh": float(self.metrics.std_consumption_kwh) if self.metrics.std_consumption_kwh is not None else None,
                "min_consumption_kwh": float(self.metrics.min_consumption_kwh) if self.metrics.min_consumption_kwh is not None else None,
                "max_consumption_kwh": float(self.metrics.max_consumption_kwh) if self.metrics.max_consumption_kwh is not None else None,
                "median_consumption_kwh": float(self.metrics.median_consumption_kwh) if self.metrics.median_consumption_kwh is not None else None,
                "coefficient_of_variation": round(self.metrics.coefficient_of_variation, 4) if self.metrics.coefficient_of_variation is not None else None,
                "negative_readings_count": self.metrics.negative_readings_count,
                "zero_readings_count": self.metrics.zero_readings_count,
                "duplicate_timestamps_count": self.metrics.duplicate_timestamps_count,
                "is_zero_variance": self.metrics.is_zero_variance,
                "temporal_separation_hours": round(self.metrics.temporal_separation_hours, 2) if self.metrics.temporal_separation_hours is not None else None,
                "quality_evaluated_count": self.metrics.quality_evaluated_count,
                "quality_coverage_ratio": round(self.metrics.quality_coverage_ratio, 4) if self.metrics.quality_coverage_ratio is not None else None,
                "valid_readings_count": self.metrics.valid_readings_count,
                "valid_readings_ratio": round(self.metrics.valid_readings_ratio, 4) if self.metrics.valid_readings_ratio is not None else None,
                "reading_quality_status": self.metrics.reading_quality_status,
                "plant_meter_boundary_status": self.metrics.plant_meter_boundary_status,
                "incomplete_meter_hours_count": self.metrics.incomplete_meter_hours_count,
                "weather_normalization_status": self.metrics.weather_normalization_status,
                "schedule_normalization_status": self.metrics.schedule_normalization_status,
                "independent_peak_demand_status": self.metrics.independent_peak_demand_status,
                "production_dependency_evaluated": self.metrics.production_dependency_evaluated,
            },
            "thresholds": asdict(self.thresholds),
        }


# ============================================================================
# PURE CORE QUALIFICATION LOGIC
# ============================================================================

def _compute_distribution_stats(
    values: List[Decimal],
) -> Tuple[
    Optional[Decimal],
    Optional[Decimal],
    Optional[Decimal],
    Optional[Decimal],
    Optional[Decimal],
    Optional[float],
    Optional[float],
]:
    """
    Calculate mean, sample standard deviation (N-1), min, max, median, CV, and unrounded raw std.
    
    Returns:
        (mean_val, std_val, min_val, max_val, median_val, cv, raw_std_float)
    """
    n = len(values)
    if n == 0:
        return None, None, None, None, None, None, None

    float_vals = [float(v) for v in values]
    sorted_vals = sorted(float_vals)

    min_val = Decimal(str(round(sorted_vals[0], 4)))
    max_val = Decimal(str(round(sorted_vals[-1], 4)))

    # Median
    mid = n // 2
    if n % 2 == 1:
        median_float = sorted_vals[mid]
    else:
        median_float = (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
    median_val = Decimal(str(round(median_float, 4)))

    mean_float = sum(float_vals) / n
    mean_val = Decimal(str(round(mean_float, 4)))

    if n < 2:
        return mean_val, Decimal("0.0"), min_val, max_val, median_val, None, 0.0

    # Sample standard deviation (N-1 degrees of freedom)
    sum_sq_diff = sum((x - mean_float) ** 2 for x in float_vals)
    variance = sum_sq_diff / (n - 1)
    raw_std_float = math.sqrt(variance)
    std_val = Decimal(str(round(raw_std_float, 4)))

    # Coefficient of variation
    cv: Optional[float] = None
    if mean_float > 1e-9:
        cv = round(raw_std_float / mean_float, 4)

    return mean_val, std_val, min_val, max_val, median_val, cv, raw_std_float


def _compute_max_contiguous_gap(
    timestamps: List[datetime],
    window_start: datetime,
    window_end: datetime,
) -> int:
    """
    Compute the maximum contiguous missing hours in a chronological timestamp series.
    
    Includes edge gaps:
    - Between window_start and first observation
    - Between consecutive observations
    - Between last observation and window_end
    """
    if not timestamps:
        total_hours = int((window_end - window_start).total_seconds() // 3600)
        return max(0, total_hours)

    max_gap = 0

    # 1. Leading edge gap
    lead_gap_sec = (timestamps[0] - window_start).total_seconds()
    lead_gap_hours = max(0, int(lead_gap_sec // 3600))
    if lead_gap_hours > max_gap:
        max_gap = lead_gap_hours

    # 2. Interior gaps between consecutive hourly observations
    for i in range(len(timestamps) - 1):
        diff_sec = (timestamps[i + 1] - timestamps[i]).total_seconds()
        # For hourly data, a 1-hour step has 0 missing hours. 2 hours has 1 missing hour.
        missing_hours = max(0, int(diff_sec // 3600) - 1)
        if missing_hours > max_gap:
            max_gap = missing_hours

    # 3. Trailing edge gap
    trail_gap_sec = (window_end - timestamps[-1]).total_seconds()
    trail_gap_hours = max(0, int(trail_gap_sec // 3600) - 1)
    if trail_gap_hours > max_gap:
        max_gap = trail_gap_hours

    return max_gap


def evaluate_baseline_series(
    observations: Sequence[BaselineObservation],
    baseline_start: datetime,
    baseline_end: datetime,
    evaluation_start: Optional[datetime] = None,
    evaluation_end: Optional[datetime] = None,
    thresholds: Optional[QualificationThresholds] = None,
    plant_id: Optional[str] = None,
    meter_id: Optional[str] = None,
    meter_ids: Optional[Sequence[str]] = None,
) -> BaselineQualificationResult:
    """
    Pure assessment function to evaluate baseline qualification.
    
    This function takes in-memory observations and temporal bounds, executes
    deterministic qualification checks, and returns a fully populated
    BaselineQualificationResult with metrics, explicit reason codes, and summary.
    
    No database operations or network calls are made.
    """
    cfg = thresholds or QualificationThresholds()

    hard_failures: List[QualificationReasonCode] = []
    warnings: List[QualificationReasonCode] = []
    informational_flags: List[QualificationReasonCode] = []
    qualifying_signals: List[QualificationReasonCode] = []

    # -------------------------------------------------------------------------
    # 1. Window Bounds Validation
    # -------------------------------------------------------------------------
    if baseline_end <= baseline_start:
        hard_failures.append(QualificationReasonCode.INVALID_WINDOW_BOUNDS)
        metrics = BaselineMetrics(
            expected_hours=0,
            observed_hours=0,
            completeness_ratio=0.0,
            completeness_status="EVALUATED",
            effective_target_observations=cfg.min_observations,
            missing_hours=0,
            max_contiguous_gap_hours=0,
            mean_consumption_kwh=None,
            std_consumption_kwh=None,
            min_consumption_kwh=None,
            max_consumption_kwh=None,
            median_consumption_kwh=None,
            coefficient_of_variation=None,
            negative_readings_count=0,
            zero_readings_count=0,
            duplicate_timestamps_count=0,
            is_zero_variance=False,
            temporal_separation_hours=None,
            quality_evaluated_count=None,
            quality_coverage_ratio=None,
            valid_readings_count=None,
            valid_readings_ratio=None,
            reading_quality_status="UNAVAILABLE",
            plant_meter_boundary_status="SINGLE_METER" if not meter_ids else "EXPLICIT_BOUNDARIES",
            incomplete_meter_hours_count=None,
        )
        return BaselineQualificationResult(
            status=BaselineQualificationStatus.NOT_QUALIFIED,
            reason_codes=[QualificationReasonCode.INVALID_WINDOW_BOUNDS],
            hard_failures=hard_failures,
            warnings=[],
            informational_flags=[],
            qualifying_signals=[],
            metrics=metrics,
            thresholds=cfg,
            plant_id=plant_id,
            meter_id=meter_id,
            meter_ids=list(meter_ids) if meter_ids else None,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
            summary="Baseline end timestamp must be strictly later than baseline start timestamp.",
        )

    expected_hours = max(1, int((baseline_end - baseline_start).total_seconds() // 3600))

    # P1 Requirement 8: Duration-aware observation sufficiency target
    if cfg.target_observations is not None:
        effective_target_obs = cfg.target_observations
    else:
        effective_target_obs = max(
            cfg.min_observations,
            int(math.ceil(expected_hours * cfg.target_observation_ratio)),
        )

    # -------------------------------------------------------------------------
    # 2. Strict Temporal Separation (Anti-Leakage) Check
    # -------------------------------------------------------------------------
    temporal_sep_hours: Optional[float] = None
    if evaluation_start is not None:
        temporal_sep_hours = (evaluation_start - baseline_end).total_seconds() / 3600.0
        if temporal_sep_hours < 0:
            # Baseline end is later than evaluation start: temporal overlap / future leakage!
            hard_failures.append(QualificationReasonCode.TEMPORAL_SEQUENCE_VIOLATION)

    # -------------------------------------------------------------------------
    # 3. Filter, Audit Duplicate Timestamps & Chronologically Order
    # -------------------------------------------------------------------------
    valid_window_obs: List[BaselineObservation] = []
    seen_timestamps: Set[datetime] = set()
    duplicate_timestamps_count = 0

    for obs in observations:
        ts = obs.timestamp
        # Check for data leakage against evaluation_start
        if evaluation_start is not None and ts >= evaluation_start:
            if QualificationReasonCode.TEMPORAL_SEQUENCE_VIOLATION not in hard_failures:
                hard_failures.append(QualificationReasonCode.TEMPORAL_SEQUENCE_VIOLATION)
            continue

        if baseline_start <= ts < baseline_end:
            if ts in seen_timestamps:
                # P1 Requirement 6: Track duplicate timestamps explicitly
                duplicate_timestamps_count += 1
            else:
                seen_timestamps.add(ts)
                valid_window_obs.append(obs)

    if duplicate_timestamps_count > 0:
        warnings.append(QualificationReasonCode.DUPLICATE_TIMESTAMPS_DETECTED)

    valid_window_obs.sort(key=lambda o: o.timestamp)
    observed_hours = len(valid_window_obs)

    # -------------------------------------------------------------------------
    # 4. Handle Empty Baseline
    # -------------------------------------------------------------------------
    if observed_hours == 0:
        hard_failures.append(QualificationReasonCode.EMPTY_BASELINE_PERIOD)
        hard_failures.append(QualificationReasonCode.CRITICAL_INSUFFICIENT_HISTORY)
        metrics = BaselineMetrics(
            expected_hours=expected_hours,
            observed_hours=0,
            completeness_ratio=0.0,
            completeness_status="EVALUATED",
            effective_target_observations=effective_target_obs,
            missing_hours=expected_hours,
            max_contiguous_gap_hours=expected_hours,
            mean_consumption_kwh=None,
            std_consumption_kwh=None,
            min_consumption_kwh=None,
            max_consumption_kwh=None,
            median_consumption_kwh=None,
            coefficient_of_variation=None,
            negative_readings_count=0,
            zero_readings_count=0,
            duplicate_timestamps_count=duplicate_timestamps_count,
            is_zero_variance=False,
            temporal_separation_hours=temporal_sep_hours,
            quality_evaluated_count=None,
            quality_coverage_ratio=None,
            valid_readings_count=None,
            valid_readings_ratio=None,
            reading_quality_status="UNAVAILABLE",
            plant_meter_boundary_status="SINGLE_METER" if not meter_ids else "EXPLICIT_BOUNDARIES",
            incomplete_meter_hours_count=None,
        )
        return BaselineQualificationResult(
            status=BaselineQualificationStatus.NOT_QUALIFIED,
            reason_codes=[
                QualificationReasonCode.EMPTY_BASELINE_PERIOD,
                QualificationReasonCode.CRITICAL_INSUFFICIENT_HISTORY,
            ],
            hard_failures=hard_failures,
            warnings=warnings,
            informational_flags=[],
            qualifying_signals=[],
            metrics=metrics,
            thresholds=cfg,
            plant_id=plant_id,
            meter_id=meter_id,
            meter_ids=list(meter_ids) if meter_ids else None,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
            summary="Zero baseline observations found within the specified historical window.",
        )

    # -------------------------------------------------------------------------
    # 5. Extract Metrics & Empirical Distribution
    # -------------------------------------------------------------------------
    values = [obs.consumption_kwh for obs in valid_window_obs]
    timestamps = [obs.timestamp for obs in valid_window_obs]

    # Negative & zero counts
    negative_count = sum(1 for v in values if v < 0)
    zero_count = sum(1 for v in values if v == 0)

    # Physical validity check: negative consumption
    if negative_count > 0:
        hard_failures.append(QualificationReasonCode.NEGATIVE_CONSUMPTION_DETECTED)

    # Statistical properties
    mean_kwh, std_kwh, min_kwh, max_kwh, median_kwh, cv, raw_std_float = _compute_distribution_stats(values)

    # P0 Requirement 1: Zero variance check using unrounded raw_std_float
    is_zero_variance = False
    if observed_hours >= 2 and raw_std_float is not None:
        if raw_std_float <= cfg.min_std_dev:
            is_zero_variance = True
            hard_failures.append(QualificationReasonCode.ZERO_VARIANCE_FLATLINE)

    # -------------------------------------------------------------------------
    # 6. Sample Sufficiency Evaluation (Duration-Aware)
    # -------------------------------------------------------------------------
    completeness_ratio = min(1.0, observed_hours / float(expected_hours))
    missing_hours = max(0, expected_hours - observed_hours)
    max_gap_hours = _compute_max_contiguous_gap(timestamps, baseline_start, baseline_end)

    if observed_hours < 2 or observed_hours < cfg.min_observations:
        hard_failures.append(QualificationReasonCode.CRITICAL_INSUFFICIENT_HISTORY)
    elif observed_hours < effective_target_obs:
        warnings.append(QualificationReasonCode.MARGINAL_OBSERVATION_COUNT)
    else:
        # P1 Requirement 5: Emit SUFFICIENT_HISTORICAL_DATA only when BOTH observation target
        # and completeness target are satisfied
        if completeness_ratio >= cfg.target_completeness_ratio:
            qualifying_signals.append(QualificationReasonCode.SUFFICIENT_HISTORICAL_DATA)

    # -------------------------------------------------------------------------
    # 7. Completeness & Gap Continuity Evaluation
    # -------------------------------------------------------------------------
    if completeness_ratio < cfg.min_completeness_ratio:
        hard_failures.append(QualificationReasonCode.CRITICAL_DATA_SPARSITY)
    elif completeness_ratio < cfg.target_completeness_ratio:
        warnings.append(QualificationReasonCode.SUBTARGET_COMPLETENESS)

    if max_gap_hours > cfg.max_gap_failure_hours:
        hard_failures.append(QualificationReasonCode.EXCESSIVE_CONTIGUOUS_GAP)
    elif max_gap_hours > cfg.max_gap_warning_hours:
        warnings.append(QualificationReasonCode.MODERATE_TELEMETRY_INTERMITTENCY)
    else:
        qualifying_signals.append(QualificationReasonCode.EXCELLENT_DATA_CONTINUITY)

    # -------------------------------------------------------------------------
    # 8. Sensor Reading Quality Evaluation (Conditional & Safe)
    # -------------------------------------------------------------------------
    # P0 Requirement 2: Do not treat missing metadata as invalid reading; report partial coverage
    quality_obs = [obs for obs in valid_window_obs if obs.reading_quality is not None and obs.reading_quality.strip()]
    quality_evaluated_count = len(quality_obs)
    valid_readings_count: Optional[int] = None
    valid_readings_ratio: Optional[float] = None
    quality_coverage_ratio: Optional[float] = None
    reading_quality_status = "UNAVAILABLE"

    if quality_evaluated_count == 0:
        reading_quality_status = "UNAVAILABLE"
    else:
        quality_coverage_ratio = quality_evaluated_count / float(observed_hours)
        approved_set = cfg.approved_reading_qualities or {"VALID"}
        valid_readings_count = sum(1 for obs in quality_obs if obs.reading_quality.strip().upper() in approved_set)
        # Ratio calculated strictly against evaluated quality count, NOT total observed_hours
        valid_readings_ratio = valid_readings_count / float(quality_evaluated_count)

        if quality_coverage_ratio < cfg.min_quality_coverage_ratio:
            # Partial coverage: do NOT falsely reject the baseline
            reading_quality_status = "PARTIAL_COVERAGE"
            warnings.append(QualificationReasonCode.PARTIAL_READING_QUALITY_COVERAGE)
        else:
            reading_quality_status = "EVALUATED"
            if valid_readings_ratio < cfg.min_valid_reading_ratio:
                hard_failures.append(QualificationReasonCode.POOR_READING_QUALITY)
            elif valid_readings_ratio < cfg.target_valid_reading_ratio:
                warnings.append(QualificationReasonCode.DEGRADED_READING_QUALITY)
            else:
                qualifying_signals.append(QualificationReasonCode.HIGH_READING_QUALITY)

    # -------------------------------------------------------------------------
    # 9. Volatility Flag (P1 Requirement 9: Informational Only)
    # -------------------------------------------------------------------------
    if cv is not None and cfg.max_coefficient_of_variation is not None:
        if cv > cfg.max_coefficient_of_variation:
            informational_flags.append(QualificationReasonCode.HIGH_VOLATILITY_WARNING)

    # -------------------------------------------------------------------------
    # 10. Assemble Empirical Metrics
    # -------------------------------------------------------------------------
    metrics = BaselineMetrics(
        expected_hours=expected_hours,
        observed_hours=observed_hours,
        completeness_ratio=completeness_ratio,
        completeness_status="EVALUATED",
        effective_target_observations=effective_target_obs,
        missing_hours=missing_hours,
        max_contiguous_gap_hours=max_gap_hours,
        mean_consumption_kwh=mean_kwh,
        std_consumption_kwh=std_kwh,
        min_consumption_kwh=min_kwh,
        max_consumption_kwh=max_kwh,
        median_consumption_kwh=median_kwh,
        coefficient_of_variation=cv,
        negative_readings_count=negative_count,
        zero_readings_count=zero_count,
        duplicate_timestamps_count=duplicate_timestamps_count,
        is_zero_variance=is_zero_variance,
        temporal_separation_hours=temporal_sep_hours,
        quality_evaluated_count=quality_evaluated_count if quality_evaluated_count > 0 else None,
        quality_coverage_ratio=quality_coverage_ratio,
        valid_readings_count=valid_readings_count,
        valid_readings_ratio=valid_readings_ratio,
        reading_quality_status=reading_quality_status,
        plant_meter_boundary_status="SINGLE_METER" if not meter_ids else "EXPLICIT_BOUNDARIES",
        incomplete_meter_hours_count=None,
        weather_normalization_status="UNAVAILABLE",
        schedule_normalization_status="UNAVAILABLE",
        independent_peak_demand_status="UNAVAILABLE",
        production_dependency_evaluated=False,
    )

    # -------------------------------------------------------------------------
    # 11. Determine Discrete Outcome Status (P1 Requirement 7: Clean Segregation)
    # -------------------------------------------------------------------------
    completeness_display = f"{completeness_ratio * 100:.1f}%"

    if hard_failures:
        status = BaselineQualificationStatus.NOT_QUALIFIED
        # P1 Requirement 7: NOT_QUALIFIED reason_codes contains ONLY failures and warnings.
        # Positive qualifying signals are completely excluded.
        ordered_reason_codes: List[QualificationReasonCode] = []
        for rc in hard_failures + warnings:
            if rc not in ordered_reason_codes:
                ordered_reason_codes.append(rc)
        failure_reasons = ", ".join(hf.value for hf in hard_failures)
        summary = (
            f"Baseline is NOT_QUALIFIED due to {len(hard_failures)} critical data integrity failure(s): "
            f"[{failure_reasons}]. Observations: {observed_hours}/{expected_hours} "
            f"({completeness_display}), Max Gap: {max_gap_hours}h."
        )
    elif warnings:
        status = BaselineQualificationStatus.INCONCLUSIVE
        ordered_reason_codes = []
        for rc in warnings:
            if rc not in ordered_reason_codes:
                ordered_reason_codes.append(rc)
        warning_reasons = ", ".join(w.value for w in warnings)
        summary = (
            f"Baseline is INCONCLUSIVE due to telemetry degradation: [{warning_reasons}]. "
            f"Observed: {observed_hours}/{expected_hours} ({completeness_display}), "
            f"Max Gap: {max_gap_hours}h. Operational comparisons may proceed with caution."
        )
    else:
        status = BaselineQualificationStatus.QUALIFIED
        qualifying_signals.insert(0, QualificationReasonCode.BASELINE_CRITERIA_MET)
        ordered_reason_codes = []
        for rc in qualifying_signals:
            if rc not in ordered_reason_codes:
                ordered_reason_codes.append(rc)
        summary = (
            f"Baseline is QUALIFIED. All data integrity and continuity criteria satisfied. "
            f"Observed: {observed_hours}/{expected_hours} ({completeness_display}), "
            f"Mean: {mean_kwh} kWh, StdDev: {std_kwh} kWh, Max Gap: {max_gap_hours}h."
        )

    # Append informational notes if volatility advisory present
    if informational_flags:
        info_str = ", ".join(inf.value for inf in informational_flags)
        summary += f" [Advisory: {info_str}]"

    return BaselineQualificationResult(
        status=status,
        reason_codes=ordered_reason_codes,
        hard_failures=hard_failures,
        warnings=warnings,
        informational_flags=informational_flags,
        qualifying_signals=qualifying_signals,
        metrics=metrics,
        thresholds=cfg,
        plant_id=plant_id,
        meter_id=meter_id,
        meter_ids=list(meter_ids) if meter_ids else None,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        summary=summary,
    )


# ============================================================================
# DATABASE RETRIEVAL HELPERS (READ-ONLY)
# ============================================================================

def qualify_meter_baseline(
    session: Session,
    plant_id: str,
    meter_id: str,
    baseline_start: datetime,
    baseline_end: datetime,
    evaluation_start: Optional[datetime] = None,
    evaluation_end: Optional[datetime] = None,
    thresholds: Optional[QualificationThresholds] = None,
) -> BaselineQualificationResult:
    """
    Retrieve hourly telemetry from Neon PostgreSQL for a specific meter and qualify it.
    
    Reads from fact_energy_meter_hourly strictly within [baseline_start, baseline_end).
    Does not modify database records or create anomalies.
    """
    query = text("""
        SELECT
            timestamp,
            consumption_kwh,
            reading_quality
        FROM fact_energy_meter_hourly
        WHERE plant_id = :plant_id
          AND meter_id = :meter_id
          AND timestamp >= :baseline_start
          AND timestamp < :baseline_end
        ORDER BY timestamp ASC
    """)
    params = {
        "plant_id": plant_id,
        "meter_id": meter_id,
        "baseline_start": baseline_start,
        "baseline_end": baseline_end,
    }

    rows = session.execute(query, params).fetchall()

    observations = [
        BaselineObservation(
            timestamp=r[0],
            consumption_kwh=Decimal(str(r[1])),
            reading_quality=str(r[2]) if r[2] is not None else None,
            meter_id=meter_id,
            plant_id=plant_id,
        )
        for r in rows
    ]

    return evaluate_baseline_series(
        observations=observations,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        thresholds=thresholds,
        plant_id=plant_id,
        meter_id=meter_id,
    )


def qualify_plant_baseline(
    session: Session,
    plant_id: str,
    baseline_start: datetime,
    baseline_end: datetime,
    meter_ids: Optional[Sequence[str]] = None,
    evaluation_start: Optional[datetime] = None,
    evaluation_end: Optional[datetime] = None,
    thresholds: Optional[QualificationThresholds] = None,
) -> BaselineQualificationResult:
    """
    Retrieve aggregated plant-level hourly telemetry and evaluate baseline qualification.
    
    CRITICAL ARCHITECTURAL SAFETY (P0 Requirement 3 & 4):
    - Requires an explicit sequence of non-overlapping meter IDs representing the plant boundary.
    - If meter_ids is not supplied, returns NOT_QUALIFIED with PLANT_METER_BOUNDARY_UNDEFINED
      and reports completeness as UNAVAILABLE. Never sums all meters indiscriminately.
    - Audits meter participation per timestamp to prevent partial meter participation from
      corrupting plant baseline sums.
    """
    cfg = thresholds or QualificationThresholds()

    # P0 Requirement 3: Guard against undefined plant meter boundaries
    if not meter_ids:
        expected_hours = (
            max(1, int((baseline_end - baseline_start).total_seconds() // 3600))
            if baseline_end > baseline_start
            else 0
        )
        metrics = BaselineMetrics(
            expected_hours=expected_hours,
            observed_hours=0,
            completeness_ratio=None,
            completeness_status="UNAVAILABLE",
            effective_target_observations=cfg.min_observations,
            missing_hours=expected_hours,
            max_contiguous_gap_hours=expected_hours,
            mean_consumption_kwh=None,
            std_consumption_kwh=None,
            min_consumption_kwh=None,
            max_consumption_kwh=None,
            median_consumption_kwh=None,
            coefficient_of_variation=None,
            negative_readings_count=0,
            zero_readings_count=0,
            duplicate_timestamps_count=0,
            is_zero_variance=False,
            temporal_separation_hours=None,
            quality_evaluated_count=None,
            quality_coverage_ratio=None,
            valid_readings_count=None,
            valid_readings_ratio=None,
            reading_quality_status="UNAVAILABLE",
            plant_meter_boundary_status="UNDEFINED",
            incomplete_meter_hours_count=None,
        )
        return BaselineQualificationResult(
            status=BaselineQualificationStatus.NOT_QUALIFIED,
            reason_codes=[QualificationReasonCode.PLANT_METER_BOUNDARY_UNDEFINED],
            hard_failures=[QualificationReasonCode.PLANT_METER_BOUNDARY_UNDEFINED],
            warnings=[],
            informational_flags=[],
            qualifying_signals=[],
            metrics=metrics,
            thresholds=cfg,
            plant_id=plant_id,
            meter_id=None,
            meter_ids=None,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
            summary=(
                "Plant-level baseline qualification requires an explicit list of non-overlapping "
                "meter IDs to prevent hierarchical double-counting. Meter boundaries are undefined."
            ),
        )

    clean_meter_ids = [m.strip() for m in meter_ids if m.strip()]
    if not clean_meter_ids:
        return qualify_plant_baseline(
            session=session,
            plant_id=plant_id,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            meter_ids=None,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
            thresholds=thresholds,
        )

    expected_meter_count = len(clean_meter_ids)

    # Query strictly the specified non-overlapping meter IDs
    stmt = (
        select(
            FactEnergyMeterHourly.timestamp,
            func.sum(FactEnergyMeterHourly.consumption_kwh).label("total_kwh"),
            func.count(func.distinct(FactEnergyMeterHourly.meter_id)).label("active_meter_count"),
        )
        .where(
            FactEnergyMeterHourly.plant_id == plant_id,
            FactEnergyMeterHourly.meter_id.in_(clean_meter_ids),
            FactEnergyMeterHourly.timestamp >= baseline_start,
            FactEnergyMeterHourly.timestamp < baseline_end,
        )
        .group_by(FactEnergyMeterHourly.timestamp)
        .order_by(FactEnergyMeterHourly.timestamp.asc())
    )
    rows = session.execute(stmt).fetchall()

    # P0 Requirement 4: Audit meter participation per timestamp
    incomplete_meter_hours_count = 0
    observations: List[BaselineObservation] = []

    for r in rows:
        ts = r[0]
        total_kwh = r[1]
        active_meter_count = r[2]

        if active_meter_count < expected_meter_count:
            # Drop incomplete hours to prevent corrupted partial sums from entering baseline statistics
            incomplete_meter_hours_count += 1
            continue

        observations.append(
            BaselineObservation(
                timestamp=ts,
                consumption_kwh=Decimal(str(total_kwh)),
                reading_quality=None,  # Aggregated; not a single physical meter
                meter_id="PLANT_AGGREGATE",
                plant_id=plant_id,
            )
        )

    result = evaluate_baseline_series(
        observations=observations,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        thresholds=cfg,
        plant_id=plant_id,
        meter_id="PLANT_AGGREGATE",
        meter_ids=clean_meter_ids,
    )

    # Augment metrics with plant aggregation audit
    result.metrics.plant_meter_boundary_status = "EXPLICIT_BOUNDARIES"
    result.metrics.incomplete_meter_hours_count = incomplete_meter_hours_count

    # If any hour suffered from missing meter streams, flag failure
    if incomplete_meter_hours_count > 0:
        result.hard_failures.append(QualificationReasonCode.INCOMPLETE_METER_PARTICIPATION)
        result.status = BaselineQualificationStatus.NOT_QUALIFIED
        if QualificationReasonCode.INCOMPLETE_METER_PARTICIPATION not in result.reason_codes:
            result.reason_codes.insert(0, QualificationReasonCode.INCOMPLETE_METER_PARTICIPATION)
        result.summary = (
            f"Baseline is NOT_QUALIFIED: Incomplete meter participation in {incomplete_meter_hours_count} "
            f"hour(s) where not all {expected_meter_count} boundary meters reported. "
            f"Observations: {result.metrics.observed_hours}/{result.metrics.expected_hours}."
        )

    return result
