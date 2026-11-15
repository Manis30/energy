"""
Deterministic Anomaly Detection Services for Industrial Energy Intelligence Platform.

This module provides read-only, mathematically deterministic anomaly detection algorithms:
1. Energy Statistical Anomalies (Global/Period Z-Score per meter & plant)
2. Rolling Historical Energy Baseline Deviations (Strictly historical window, current obs excluded)
3. Low Power Factor Compliance Deficits (< configurable threshold, default 0.90)
4. Zero-Production Period Standby Energy (Dedicated line-meter standby draw during line stoppage)

All calculations are derived exclusively from actual Neon PostgreSQL database records.
No LLM estimation, no artificial baselines, no automatic database mutations.
"""

from datetime import datetime, timedelta
from decimal import Decimal
import math
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import DEFAULT_POWER_FACTOR_THRESHOLD
from app.services.baseline_qualification import (
    BaselineObservation,
    BaselineQualificationResult,
    BaselineQualificationStatus,
    QualificationReasonCode,
    QualificationThresholds,
    evaluate_baseline_series,
)

# Stable explicit detector version identifiers for row-level provenance
DETECTOR_VERSION_STATISTICAL_ZSCORE = "statistical_zscore:1.0.0"
DETECTOR_VERSION_ROLLING_BASELINE = "rolling_baseline:1.0.0"
DETECTOR_VERSION_LOW_POWER_FACTOR = "low_power_factor:1.0.0"
DETECTOR_VERSION_STANDBY_ENERGY = "zero_production_standby:1.0.0"


def _format_decimal(val: Any, decimals: int = 4) -> Optional[Decimal]:
    """Helper to convert float or string to rounded Decimal."""
    if val is None:
        return None
    return round(Decimal(str(val)), decimals)


def _classify_z_severity(z: float) -> str:
    """Classify anomaly severity based on absolute Z-score deviation."""
    abs_z = abs(z)
    if abs_z >= 4.0:
        return "CRITICAL"
    if abs_z >= 3.0:
        return "HIGH"
    if abs_z >= 2.5:
        return "MEDIUM"
    return "LOW"


def _classify_pf_severity(pf: Decimal, threshold: Decimal) -> str:
    """Classify low power factor severity."""
    if pf < Decimal("0.85"):
        return "CRITICAL"
    if pf < Decimal("0.88"):
        return "HIGH"
    return "MEDIUM"


def detect_energy_statistical_anomalies(
    session: Session,
    plant_id: Optional[str] = None,
    meter_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    lookback_days: int = 30,
    threshold_z: float = 3.0,
    min_observations: int = 10,
    limit: Optional[int] = None,
    evaluation_scope: str = "latest_day",
) -> Dict[str, Any]:
    """
    Detect hourly energy consumption anomalies using sample Z-score per (plant_id, meter_id).

    Evaluates observations within the evaluation period [eval_start, eval_end] against a
    strictly segregated historical baseline period [baseline_start, baseline_end).

    Key Engineering Protections:
    - Baseline mean, sample standard deviation (STDDEV_SAMP), and observation count are calculated
      using ONLY records strictly earlier than the evaluation period start (timestamp < eval_start).
    - Evaluation observations and future observations are strictly excluded from the baseline.
    - Baseline groups are partitioned strictly by (plant_id, meter_id).
    - Safe handling when start_time is absent: governed by evaluation_scope:
      - 'latest_day' (default): evaluates the 24-hour period ending at eval_end against the preceding lookback_days.
      - 'historical': evaluates all historical observations following an initial lookback_days baseline window.
      Does not use the same rows as both baseline and evaluation set.
    - Groups with historical observations < min_observations are reported as INSUFFICIENT_HISTORY
      and their observations are NOT classified as normal or anomalous.
    - Groups with historical stddev == 0 are reported as ZERO_VARIANCE and no Z-score is calculated.
    - Configurable lookback_days duration with documented default (30 days / 720 hours, range 1-90).
    - Baseline period and evaluation period boundaries returned in response.
    """
    if threshold_z <= 0:
        raise ValueError("threshold_z must be positive")
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2")
    if lookback_days < 1 or lookback_days > 90:
        raise ValueError("lookback_days must be between 1 and 90")
    if evaluation_scope not in ("latest_day", "historical"):
        raise ValueError("evaluation_scope must be either 'latest_day' or 'historical'")

    # Determine evaluation period boundaries safely
    max_ts: Optional[datetime] = None
    min_ts: Optional[datetime] = None
    if start_time is None or end_time is None:
        max_query_parts = []
        max_params: Dict[str, Any] = {}
        if plant_id:
            max_query_parts.append("plant_id = :plant_id")
            max_params["plant_id"] = plant_id
        if meter_id:
            max_query_parts.append("meter_id = :meter_id")
            max_params["meter_id"] = meter_id
        where_max = f"WHERE {' AND '.join(max_query_parts)}" if max_query_parts else ""
        max_sql = f"SELECT MAX(timestamp), MIN(timestamp) FROM fact_energy_meter_hourly {where_max}"
        bounds_row = session.execute(text(max_sql), max_params).fetchone()
        if bounds_row:
            max_ts, min_ts = bounds_row[0], bounds_row[1]

    if end_time is not None:
        eval_end = end_time
    elif max_ts is not None:
        eval_end = max_ts
    else:
        eval_end = datetime.utcnow()

    if start_time is not None:
        eval_start = start_time
        baseline_end = eval_start
        baseline_start = eval_start - timedelta(days=int(lookback_days))
    elif evaluation_scope == "historical" and min_ts is not None:
        baseline_start = min_ts
        baseline_end = min_ts + timedelta(days=int(lookback_days))
        eval_start = baseline_end
        if eval_start > eval_end:
            eval_start = eval_end
    elif max_ts is not None:
        eval_start = eval_end - timedelta(days=1)
        baseline_end = eval_start
        baseline_start = eval_start - timedelta(days=int(lookback_days))
    else:
        eval_start = eval_end - timedelta(days=1)
        baseline_end = eval_start
        baseline_start = eval_start - timedelta(days=int(lookback_days))

    if eval_start > eval_end:
        raise ValueError(f"start_time ({eval_start}) cannot be after end_time ({eval_end})")

    params: Dict[str, Any] = {
        "baseline_start": baseline_start,
        "baseline_end": baseline_end,
        "eval_start": eval_start,
        "eval_end": eval_end,
        "threshold_z": float(threshold_z),
        "min_obs": int(min_observations),
    }

    base_filter_parts: List[str] = []
    outer_filter_parts: List[str] = []
    if plant_id:
        base_filter_parts.append("plant_id = :plant_id")
        outer_filter_parts.append("f.plant_id = :plant_id")
        params["plant_id"] = plant_id
    if meter_id:
        base_filter_parts.append("meter_id = :meter_id")
        outer_filter_parts.append("f.meter_id = :meter_id")
        params["meter_id"] = meter_id

    base_filter_clause = f"AND {' AND '.join(base_filter_parts)}" if base_filter_parts else ""
    outer_filter_clause = f"AND {' AND '.join(outer_filter_parts)}" if outer_filter_parts else ""

    # 1. Fetch raw historical baseline telemetry partitioned per meter
    # Query all hourly observations strictly within [baseline_start, baseline_end)
    baseline_obs_sql = f"""
        SELECT
            plant_id,
            meter_id,
            timestamp,
            consumption_kwh,
            reading_quality
        FROM fact_energy_meter_hourly
        WHERE timestamp >= :baseline_start
          AND timestamp < :baseline_end
          {base_filter_clause}
        ORDER BY plant_id, meter_id, timestamp ASC
    """
    obs_rows = session.execute(text(baseline_obs_sql), params).fetchall()

    baseline_obs_by_group: Dict[str, List[BaselineObservation]] = {}
    for r in obs_rows:
        pid, mid, ts, val, q_flag = r
        g_key = f"{pid}_{mid}"
        if g_key not in baseline_obs_by_group:
            baseline_obs_by_group[g_key] = []
        baseline_obs_by_group[g_key].append(
            BaselineObservation(
                timestamp=ts,
                consumption_kwh=Decimal(str(val)),
                reading_quality=str(q_flag) if q_flag is not None else None,
                meter_id=mid,
                plant_id=pid,
            )
        )

    # 2. Query distinct groups in the evaluation period to catch meters with zero baseline history
    eval_groups_sql = f"""
        SELECT DISTINCT plant_id, meter_id
        FROM fact_energy_meter_hourly
        WHERE timestamp >= :eval_start
          AND timestamp <= :eval_end
          {base_filter_clause}
        ORDER BY plant_id, meter_id
    """
    eval_group_rows = session.execute(text(eval_groups_sql), params).fetchall()

    all_group_keys: Set[str] = set(baseline_obs_by_group.keys())
    for r in eval_group_rows:
        all_group_keys.add(f"{r[0]}_{r[1]}")

    meter_baselines: Dict[str, Any] = {}
    eligible_groups: List[str] = []
    qualified_groups: List[str] = []
    inconclusive_groups: List[str] = []
    disqualified_groups: List[str] = []
    zero_variance_groups: List[str] = []
    insufficient_obs_groups: List[str] = []

    # Configure qualification thresholds (parameterized with caller's min_observations)
    qual_thresholds = QualificationThresholds(
        min_observations=min_observations,
    )

    # 3. Deterministic Baseline Qualification before Statistical Z-Score Evaluation
    for group_key in sorted(all_group_keys):
        pid, mid = group_key.split("_", 1)
        group_obs = baseline_obs_by_group.get(group_key, [])

        qual_result: BaselineQualificationResult = evaluate_baseline_series(
            observations=group_obs,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            evaluation_start=eval_start,
            evaluation_end=eval_end,
            thresholds=qual_thresholds,
            plant_id=pid,
            meter_id=mid,
        )

        q_status = qual_result.status
        is_zero_var = qual_result.metrics.is_zero_variance
        is_insufficient = qual_result.metrics.observed_hours < min_observations

        b_info: Dict[str, Any] = {
            "plant_id": pid,
            "meter_id": mid,
            "obs_count": qual_result.metrics.observed_hours,
            "mean_kwh": _format_decimal(qual_result.metrics.mean_consumption_kwh, 4) if qual_result.metrics.mean_consumption_kwh is not None else None,
            "std_kwh": _format_decimal(qual_result.metrics.std_consumption_kwh, 4) if qual_result.metrics.std_consumption_kwh is not None else None,
            "min_kwh": _format_decimal(qual_result.metrics.min_consumption_kwh, 4) if qual_result.metrics.min_consumption_kwh is not None else None,
            "max_kwh": _format_decimal(qual_result.metrics.max_consumption_kwh, 4) if qual_result.metrics.max_consumption_kwh is not None else None,
            "zero_variance": is_zero_var,
            "insufficient_observations": is_insufficient,
            "qualification_status": q_status.value,
            "qualification_reasons": [rc.value for rc in qual_result.reason_codes],
            "hard_failures": [hf.value for hf in qual_result.hard_failures],
            "warnings": [w.value for w in qual_result.warnings],
            "informational_flags": [inf.value for inf in qual_result.informational_flags],
            "qualifying_signals": [qs.value for qs in qual_result.qualifying_signals],
            "qualification_summary": qual_result.summary,
            "confidence_limitations": qual_result.summary if q_status == BaselineQualificationStatus.INCONCLUSIVE else None,
            "qualification_metrics": {
                "expected_hours": qual_result.metrics.expected_hours,
                "observed_hours": qual_result.metrics.observed_hours,
                "completeness_ratio": round(qual_result.metrics.completeness_ratio, 4) if qual_result.metrics.completeness_ratio is not None else None,
                "max_contiguous_gap_hours": qual_result.metrics.max_contiguous_gap_hours,
                "reading_quality_status": qual_result.metrics.reading_quality_status,
                "valid_readings_ratio": round(qual_result.metrics.valid_readings_ratio, 4) if qual_result.metrics.valid_readings_ratio is not None else None,
                "duplicate_timestamps_count": qual_result.metrics.duplicate_timestamps_count,
            },
        }

        if q_status == BaselineQualificationStatus.QUALIFIED:
            b_info["status"] = "ELIGIBLE"
            eligible_groups.append(group_key)
            qualified_groups.append(group_key)
        elif q_status == BaselineQualificationStatus.INCONCLUSIVE:
            # Preserve detector results with tentative status and limitations
            b_info["status"] = "ELIGIBLE"
            eligible_groups.append(group_key)
            inconclusive_groups.append(group_key)
        else:  # NOT_QUALIFIED
            b_info["status"] = "NOT_QUALIFIED"
            disqualified_groups.append(group_key)
            if is_zero_var or QualificationReasonCode.ZERO_VARIANCE_FLATLINE in qual_result.hard_failures:
                zero_variance_groups.append(group_key)
            if (
                is_insufficient
                or QualificationReasonCode.CRITICAL_INSUFFICIENT_HISTORY in qual_result.hard_failures
                or QualificationReasonCode.EMPTY_BASELINE_PERIOD in qual_result.hard_failures
            ):
                insufficient_obs_groups.append(group_key)

        meter_baselines[group_key] = b_info

    # 4. Query individual anomalies strictly for eligible groups during the evaluation period
    anomalies: List[Dict[str, Any]] = []
    if eligible_groups:
        query_sql = f"""
            WITH baseline_stats AS (
                SELECT
                    plant_id,
                    meter_id,
                    COUNT(*) as obs_count,
                    AVG(consumption_kwh) as mean_kwh,
                    COALESCE(STDDEV_SAMP(consumption_kwh), 0) as std_kwh
                FROM fact_energy_meter_hourly
                WHERE timestamp >= :baseline_start
                  AND timestamp < :baseline_end
                  {base_filter_clause}
                GROUP BY plant_id, meter_id
                HAVING COUNT(*) >= :min_obs
                   AND COALESCE(STDDEV_SAMP(consumption_kwh), 0) > 0
            )
            SELECT
                f.plant_id,
                f.meter_id,
                f.timestamp,
                f.consumption_kwh,
                s.mean_kwh,
                s.std_kwh,
                s.obs_count,
                (f.consumption_kwh - s.mean_kwh) / s.std_kwh as z_score,
                f.meter_reading_id,
                f.upload_id
            FROM fact_energy_meter_hourly f
            JOIN baseline_stats s ON f.plant_id = s.plant_id AND f.meter_id = s.meter_id
            WHERE f.timestamp >= :eval_start
              AND f.timestamp <= :eval_end
              {outer_filter_clause}
              AND ABS((f.consumption_kwh - s.mean_kwh) / s.std_kwh) >= :threshold_z
            ORDER BY ABS((f.consumption_kwh - s.mean_kwh) / s.std_kwh) DESC, f.timestamp DESC
        """
        rows = session.execute(text(query_sql), params).fetchall()

        for r in rows:
            pid, mid, ts, val, mean_v, std_v, count, z_val, reading_id, upl_id = r
            group_key = f"{pid}_{mid}"

            # HARD PROTECT: Only evaluate anomalies for groups that were qualified or tentatively eligible
            if group_key not in eligible_groups:
                continue

            z_float = float(z_val)
            abs_z = abs(z_float)
            anomaly_type = "ENERGY_STATISTICAL_SPIKE" if z_float > 0 else "ENERGY_STATISTICAL_DROP"
            direction = "above" if z_float > 0 else "below"
            sev = _classify_z_severity(z_float)

            b_info = meter_baselines.get(group_key, {})
            q_status_str = b_info.get("qualification_status", "QUALIFIED")

            explanation = (
                f"Measured hourly consumption of {val:.4f} kWh is {abs_z:.2f} standard deviations "
                f"{direction} the historical baseline mean ({mean_v:.4f} kWh, std dev: {std_v:.4f} kWh) "
                f"for meter {mid} at plant {pid}."
            )

            context_flags = {
                "sample_size": count,
                "std_kwh": float(round(std_v, 4)),
                "threshold_z": float(threshold_z),
                "is_spike": z_float > 0,
                "lookback_days": lookback_days,
                "baseline_start": baseline_start.isoformat(),
                "baseline_end": baseline_end.isoformat(),
                "evaluation_start": eval_start.isoformat(),
                "evaluation_end": eval_end.isoformat(),
                "baseline_qualification_status": q_status_str,
                "baseline_trust_level": "TRUSTED" if q_status_str == "QUALIFIED" else "TENTATIVE",
                "qualification_reasons": b_info.get("qualification_reasons", []),
                "source_table": "fact_energy_meter_hourly",
                "source_record_id": str(reading_id) if reading_id else None,
                "upload_id": str(upl_id) if upl_id else None,
                "detector_version": DETECTOR_VERSION_STATISTICAL_ZSCORE,
                "lineage_status": "AVAILABLE" if reading_id else "UNAVAILABLE",
            }

            if q_status_str == "INCONCLUSIVE":
                context_flags["confidence_limitations"] = b_info.get("confidence_limitations")
                warning_list = b_info.get("warnings", [])
                warn_str = ", ".join(warning_list) if warning_list else "telemetry degradation"
                explanation += f" [Baseline Caveat: Baseline is INCONCLUSIVE ({warn_str}). Operational comparisons should proceed with caution.]"

            anomalies.append({
                "anomaly_type": anomaly_type,
                "plant_id": pid,
                "meter_id": mid,
                "line_id": None,
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "actual_value": _format_decimal(val, 4),
                "baseline_value": _format_decimal(mean_v, 4),
                "deviation_score": round(z_float, 4),
                "severity": sev,
                "explanation": explanation,
                "context_flags": context_flags,
                "source_table": "fact_energy_meter_hourly",
                "source_record_id": str(reading_id) if reading_id else None,
                "upload_id": str(upl_id) if upl_id else None,
                "detector_version": DETECTOR_VERSION_STATISTICAL_ZSCORE,
            })

    return {
        "analysis_type": "statistical_zscore",
        "threshold_z": threshold_z,
        "min_observations": min_observations,
        "lookback_days": lookback_days,
        "total_anomalies_detected": len(anomalies),
        "eligible_groups_count": len(eligible_groups),
        "qualified_groups_count": len(qualified_groups),
        "inconclusive_groups_count": len(inconclusive_groups),
        "disqualified_groups_count": len(disqualified_groups),
        "zero_variance_groups": zero_variance_groups,
        "insufficient_observations_groups": insufficient_obs_groups,
        "disqualified_groups": disqualified_groups,
        "baseline_period": {
            "start_time": baseline_start.isoformat(),
            "end_time": baseline_end.isoformat(),
            "lookback_days": lookback_days,
        },
        "evaluation_period": {
            "start_time": eval_start.isoformat(),
            "end_time": eval_end.isoformat(),
            "evaluation_scope": evaluation_scope,
        },
        "meter_baselines": meter_baselines,
        "anomalies": anomalies[:limit] if limit is not None and limit >= 0 else anomalies,
    }


def detect_rolling_baseline_anomalies(
    session: Session,
    plant_id: Optional[str] = None,
    meter_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    window_size: int = 24,
    min_observations: int = 12,
    threshold_z: float = 3.0,
    limit: Optional[int] = None,
    evaluation_scope: str = "latest_day",
) -> Dict[str, Any]:
    """
    Calculate rolling historical baselines and detect dynamic anomalies.

    Strict rules enforced:
    - Uses observations within the preceding timestamp duration, excluding the current hour
      (RANGE BETWEEN INTERVAL '{w_size} hours' PRECEDING AND INTERVAL '1 microsecond' PRECEDING).
    - The current observation and all future observations are NEVER included in the baseline.
    - Explicit window_size (default 24 hours, max 720 hours / 30 days) and min_observations.
    - Partitioned strictly by (plant_id, meter_id) to avoid comparing unrelated meters or plants.
    - Evaluated observation count, insufficient-history count, zero-variance count, and anomaly
      count are reported with affected meter IDs.
    - Evaluation period boundaries returned in response.
    """
    if threshold_z <= 0:
        raise ValueError("threshold_z must be positive")
    w_size = int(window_size)
    if w_size < 2 or w_size > 720:
        raise ValueError("window_size must be between 2 and 720 hours (30 days)")
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2")
    if min_observations > w_size:
        raise ValueError("min_observations cannot exceed window_size")
    if evaluation_scope not in ("latest_day", "historical"):
        raise ValueError("evaluation_scope must be either 'latest_day' or 'historical'")

    # Determine evaluation boundaries safely
    max_ts: Optional[datetime] = None
    min_ts: Optional[datetime] = None
    if start_time is None or end_time is None:
        max_query_parts = []
        max_params: Dict[str, Any] = {}
        if plant_id:
            max_query_parts.append("plant_id = :plant_id")
            max_params["plant_id"] = plant_id
        if meter_id:
            max_query_parts.append("meter_id = :meter_id")
            max_params["meter_id"] = meter_id
        where_max = f"WHERE {' AND '.join(max_query_parts)}" if max_query_parts else ""
        max_sql = f"SELECT MAX(timestamp), MIN(timestamp) FROM fact_energy_meter_hourly {where_max}"
        bounds_row = session.execute(text(max_sql), max_params).fetchone()
        if bounds_row:
            max_ts, min_ts = bounds_row[0], bounds_row[1]

    if end_time is not None:
        eval_end = end_time
    elif max_ts is not None:
        eval_end = max_ts
    else:
        eval_end = datetime.utcnow()

    if start_time is not None:
        eval_start = start_time
    elif evaluation_scope == "historical" and min_ts is not None:
        eval_start = min_ts + timedelta(hours=w_size)
        if eval_start > eval_end:
            eval_start = eval_end
    elif max_ts is not None:
        eval_start = eval_end - timedelta(days=1)
    else:
        eval_start = eval_end - timedelta(days=1)

    if eval_start > eval_end:
        raise ValueError(f"start_time ({eval_start}) cannot be after end_time ({eval_end})")

    # To calculate rolling window for rows starting at eval_start, history must extend back w_size hours
    rolling_history_start = eval_start - timedelta(hours=w_size)
    baseline_start = rolling_history_start
    baseline_end = eval_start

    params: Dict[str, Any] = {
        "threshold_z": float(threshold_z),
        "min_obs": int(min_observations),
        "eval_start": eval_start,
        "eval_end": eval_end,
        "history_start": rolling_history_start,
        "baseline_start": baseline_start,
        "baseline_end": baseline_end,
    }

    base_filters: List[str] = []
    outer_filters: List[str] = []
    if plant_id:
        base_filters.append("plant_id = :plant_id")
        outer_filters.append("plant_id = :plant_id")
        params["plant_id"] = plant_id
    if meter_id:
        base_filters.append("meter_id = :meter_id")
        outer_filters.append("meter_id = :meter_id")
        params["meter_id"] = meter_id

    base_filter_clause = f"AND {' AND '.join(base_filters)}" if base_filters else ""
    outer_filter_clause = f"AND {' AND '.join(outer_filters)}" if outer_filters else ""

    # 1. Fetch raw historical baseline telemetry partitioned per meter strictly within [baseline_start, baseline_end)
    baseline_obs_sql = f"""
        SELECT
            plant_id,
            meter_id,
            timestamp,
            consumption_kwh,
            reading_quality
        FROM fact_energy_meter_hourly
        WHERE timestamp >= :baseline_start
          AND timestamp < :baseline_end
          {base_filter_clause}
        ORDER BY plant_id, meter_id, timestamp ASC
    """
    obs_rows = session.execute(text(baseline_obs_sql), params).fetchall()

    baseline_obs_by_group: Dict[str, List[BaselineObservation]] = {}
    for r in obs_rows:
        pid, mid, ts, val, q_flag = r
        g_key = f"{pid}_{mid}"
        if g_key not in baseline_obs_by_group:
            baseline_obs_by_group[g_key] = []
        baseline_obs_by_group[g_key].append(
            BaselineObservation(
                timestamp=ts,
                consumption_kwh=Decimal(str(val)),
                reading_quality=str(q_flag) if q_flag is not None else None,
                meter_id=mid,
                plant_id=pid,
            )
        )

    # 2. Query distinct groups in the evaluation period to catch meters with zero baseline history
    eval_groups_sql = f"""
        SELECT DISTINCT plant_id, meter_id
        FROM fact_energy_meter_hourly
        WHERE timestamp >= :eval_start
          AND timestamp <= :eval_end
          {base_filter_clause}
        ORDER BY plant_id, meter_id
    """
    eval_group_rows = session.execute(text(eval_groups_sql), params).fetchall()

    all_group_keys: Set[str] = set(baseline_obs_by_group.keys())
    for r in eval_group_rows:
        all_group_keys.add(f"{r[0]}_{r[1]}")

    meter_baselines: Dict[str, Any] = {}
    eligible_groups: List[str] = []
    qualified_groups: List[str] = []
    inconclusive_groups: List[str] = []
    disqualified_groups: List[str] = []
    zero_variance_groups: List[str] = []
    insufficient_obs_groups: List[str] = []

    # Configure qualification thresholds (parameterized with caller's min_observations)
    qual_thresholds = QualificationThresholds(
        min_observations=min_observations,
    )

    # 3. Deterministic Baseline Qualification before Rolling Anomaly Evaluation
    for group_key in sorted(all_group_keys):
        pid, mid = group_key.split("_", 1)
        group_obs = baseline_obs_by_group.get(group_key, [])

        qual_result: BaselineQualificationResult = evaluate_baseline_series(
            observations=group_obs,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            evaluation_start=eval_start,
            evaluation_end=eval_end,
            thresholds=qual_thresholds,
            plant_id=pid,
            meter_id=mid,
        )

        q_status = qual_result.status
        is_zero_var = qual_result.metrics.is_zero_variance
        is_insufficient = qual_result.metrics.observed_hours < min_observations

        b_info: Dict[str, Any] = {
            "plant_id": pid,
            "meter_id": mid,
            "obs_count": qual_result.metrics.observed_hours,
            "mean_kwh": _format_decimal(qual_result.metrics.mean_consumption_kwh, 4) if qual_result.metrics.mean_consumption_kwh is not None else None,
            "std_kwh": _format_decimal(qual_result.metrics.std_consumption_kwh, 4) if qual_result.metrics.std_consumption_kwh is not None else None,
            "min_kwh": _format_decimal(qual_result.metrics.min_consumption_kwh, 4) if qual_result.metrics.min_consumption_kwh is not None else None,
            "max_kwh": _format_decimal(qual_result.metrics.max_consumption_kwh, 4) if qual_result.metrics.max_consumption_kwh is not None else None,
            "zero_variance": is_zero_var,
            "insufficient_observations": is_insufficient,
            "qualification_status": q_status.value,
            "qualification_reasons": [rc.value for rc in qual_result.reason_codes],
            "hard_failures": [hf.value for hf in qual_result.hard_failures],
            "warnings": [w.value for w in qual_result.warnings],
            "informational_flags": [inf.value for inf in qual_result.informational_flags],
            "qualifying_signals": [qs.value for qs in qual_result.qualifying_signals],
            "qualification_summary": qual_result.summary,
            "confidence_limitations": qual_result.summary if q_status == BaselineQualificationStatus.INCONCLUSIVE else None,
            "qualification_metrics": {
                "expected_hours": qual_result.metrics.expected_hours,
                "observed_hours": qual_result.metrics.observed_hours,
                "completeness_ratio": round(qual_result.metrics.completeness_ratio, 4) if qual_result.metrics.completeness_ratio is not None else None,
                "max_contiguous_gap_hours": qual_result.metrics.max_contiguous_gap_hours,
                "reading_quality_status": qual_result.metrics.reading_quality_status,
                "valid_readings_ratio": round(qual_result.metrics.valid_readings_ratio, 4) if qual_result.metrics.valid_readings_ratio is not None else None,
                "duplicate_timestamps_count": qual_result.metrics.duplicate_timestamps_count,
            },
        }

        if q_status == BaselineQualificationStatus.QUALIFIED:
            b_info["status"] = "ELIGIBLE"
            eligible_groups.append(group_key)
            qualified_groups.append(group_key)
        elif q_status == BaselineQualificationStatus.INCONCLUSIVE:
            # Preserve detector results with tentative status and limitations
            b_info["status"] = "ELIGIBLE"
            eligible_groups.append(group_key)
            inconclusive_groups.append(group_key)
        else:  # NOT_QUALIFIED
            b_info["status"] = "NOT_QUALIFIED"
            disqualified_groups.append(group_key)
            if is_zero_var or QualificationReasonCode.ZERO_VARIANCE_FLATLINE in qual_result.hard_failures:
                zero_variance_groups.append(group_key)
            if (
                is_insufficient
                or QualificationReasonCode.CRITICAL_INSUFFICIENT_HISTORY in qual_result.hard_failures
                or QualificationReasonCode.EMPTY_BASELINE_PERIOD in qual_result.hard_failures
            ):
                insufficient_obs_groups.append(group_key)

        meter_baselines[group_key] = b_info

    # 4. Summary metrics query over evaluated observations in [eval_start, eval_end]
    # Restrict to eligible groups so total_evaluated_observations reflects only observations
    # from groups eligible for anomaly evaluation.
    if not eligible_groups:
        total_evaluated = 0
        insufficient_count = 0
        zero_var_count = 0
        anomaly_count = 0
        insufficient_meters = []
        zero_var_meters = []
    else:
        disqual_filter_clause = ""
        if disqualified_groups:
            disqual_conditions = []
            for i, g in enumerate(disqualified_groups):
                p, m = g.split("_", 1)
                p_key = f"disq_p_{i}"
                m_key = f"disq_m_{i}"
                params[p_key] = p
                params[m_key] = m
                disqual_conditions.append(f"(plant_id = :{p_key} AND meter_id = :{m_key})")
            disqual_filter_clause = f"AND NOT ({' OR '.join(disqual_conditions)})"

        summary_sql = f"""
            WITH rolling AS (
                SELECT
                    timestamp,
                    plant_id,
                    meter_id,
                    consumption_kwh,
                    AVG(consumption_kwh) OVER w as rolling_mean,
                    COALESCE(STDDEV_SAMP(consumption_kwh) OVER w, 0) as rolling_std,
                    COUNT(consumption_kwh) OVER w as window_obs_count
                FROM fact_energy_meter_hourly
                WHERE timestamp >= :history_start
                  AND timestamp <= :eval_end
                  {base_filter_clause}
                WINDOW w AS (
                    PARTITION BY plant_id, meter_id
                    ORDER BY timestamp
                    RANGE BETWEEN INTERVAL '{w_size} hours' PRECEDING
                              AND INTERVAL '1 microsecond' PRECEDING
                )
            ),
            eval_obs AS (
                SELECT
                    plant_id,
                    meter_id,
                    timestamp,
                    consumption_kwh,
                    rolling_mean,
                    rolling_std,
                    window_obs_count,
                    CASE
                        WHEN window_obs_count < :min_obs THEN 'INSUFFICIENT_HISTORY'
                        WHEN rolling_std = 0 THEN 'ZERO_VARIANCE'
                        WHEN ABS((consumption_kwh - rolling_mean) / rolling_std) >= :threshold_z THEN 'ANOMALY'
                        ELSE 'NORMAL'
                    END AS eval_status
                FROM rolling
                WHERE timestamp >= :eval_start
                  AND timestamp <= :eval_end
                  {outer_filter_clause}
                  {disqual_filter_clause}
            )
            SELECT
                COUNT(*) as total_obs,
                COUNT(*) FILTER (WHERE eval_status = 'INSUFFICIENT_HISTORY') as insufficient_count,
                COUNT(*) FILTER (WHERE eval_status = 'ZERO_VARIANCE') as zero_var_count,
                COUNT(*) FILTER (WHERE eval_status = 'ANOMALY') as anomaly_count,
                ARRAY_AGG(DISTINCT meter_id) FILTER (WHERE eval_status = 'INSUFFICIENT_HISTORY') as insufficient_meters,
                ARRAY_AGG(DISTINCT meter_id) FILTER (WHERE eval_status = 'ZERO_VARIANCE') as zero_var_meters
            FROM eval_obs
        """
        summary_row = session.execute(text(summary_sql), params).fetchone()

        total_evaluated = int(summary_row[0]) if summary_row and summary_row[0] is not None else 0
        insufficient_count = int(summary_row[1]) if summary_row and summary_row[1] is not None else 0
        zero_var_count = int(summary_row[2]) if summary_row and summary_row[2] is not None else 0
        anomaly_count = int(summary_row[3]) if summary_row and summary_row[3] is not None else 0
        insufficient_meters = list(summary_row[4]) if summary_row and summary_row[4] is not None else []
        zero_var_meters = list(summary_row[5]) if summary_row and summary_row[5] is not None else []

    all_insufficient_meters = set(insufficient_meters)
    for g in insufficient_obs_groups:
        all_insufficient_meters.add(g.split("_", 1)[1])

    all_zero_var_meters = set(zero_var_meters)
    for g in zero_variance_groups:
        all_zero_var_meters.add(g.split("_", 1)[1])

    # 5. Query individual anomalies strictly for eligible groups during the evaluation period
    anomalies: List[Dict[str, Any]] = []
    if eligible_groups and anomaly_count > 0:
        approved_set = qual_thresholds.approved_reading_qualities or {"VALID"}
        approved_sql_list = ", ".join(f"'{str(q).strip().upper()}'" for q in approved_set)

        anomaly_sql = f"""
            WITH rolling AS (
                SELECT
                    timestamp,
                    plant_id,
                    meter_id,
                    consumption_kwh,
                    AVG(consumption_kwh) OVER w as rolling_mean,
                    COALESCE(STDDEV_SAMP(consumption_kwh) OVER w, 0) as rolling_std,
                    COUNT(consumption_kwh) OVER w as window_obs_count,
                    COUNT(reading_quality) FILTER (WHERE reading_quality IS NOT NULL AND TRIM(reading_quality) != '') OVER w as window_quality_count,
                    COUNT(reading_quality) FILTER (WHERE UPPER(TRIM(reading_quality)) IN ({approved_sql_list})) OVER w as window_valid_count,
                    meter_reading_id,
                    upload_id
                FROM fact_energy_meter_hourly
                WHERE timestamp >= :history_start
                  AND timestamp <= :eval_end
                  {base_filter_clause}
                WINDOW w AS (
                    PARTITION BY plant_id, meter_id
                    ORDER BY timestamp
                    RANGE BETWEEN INTERVAL '{w_size} hours' PRECEDING
                              AND INTERVAL '1 microsecond' PRECEDING
                )
            )
            SELECT
                plant_id,
                meter_id,
                timestamp,
                consumption_kwh,
                rolling_mean,
                rolling_std,
                window_obs_count,
                window_quality_count,
                window_valid_count,
                (consumption_kwh - rolling_mean) / rolling_std as rolling_z,
                meter_reading_id,
                upload_id
            FROM rolling
            WHERE timestamp >= :eval_start
              AND timestamp <= :eval_end
              {outer_filter_clause}
              AND window_obs_count >= :min_obs
              AND rolling_std > 0
              AND ABS((consumption_kwh - rolling_mean) / rolling_std) >= :threshold_z
            ORDER BY ABS((consumption_kwh - rolling_mean) / rolling_std) DESC, timestamp DESC
        """
        rows = session.execute(text(anomaly_sql), params).fetchall()

        for r in rows:
            pid, mid, ts, val, r_mean, r_std, obs_count, win_qual_count, win_valid_count, r_z, reading_id, upl_id = r
            group_key = f"{pid}_{mid}"

            # HARD PROTECT: Only evaluate anomalies for groups that were qualified or tentatively eligible
            if group_key not in eligible_groups:
                continue

            z_float = float(r_z)
            abs_z = abs(z_float)
            anomaly_type = "ROLLING_BASELINE_SPIKE" if z_float > 0 else "ROLLING_BASELINE_DROP"
            direction = "above" if z_float > 0 else "below"
            sev = _classify_z_severity(z_float)

            b_info = meter_baselines.get(group_key, {})
            q_status_str = b_info.get("qualification_status", "QUALIFIED")

            # Dynamic comparison-window quality and coverage evaluation
            # Reuses existing QualificationThresholds and QualificationReasonCode conventions
            dynamic_warnings: List[str] = []
            expected_hours = w_size
            effective_target_obs = qual_thresholds.target_observations or max(
                qual_thresholds.min_observations,
                math.ceil(expected_hours * qual_thresholds.target_observation_ratio),
            )
            completeness_ratio = min(1.0, obs_count / float(expected_hours)) if expected_hours > 0 else 1.0

            # 1. Coverage / observation sufficiency
            if completeness_ratio < qual_thresholds.min_completeness_ratio:
                dynamic_warnings.append(QualificationReasonCode.CRITICAL_DATA_SPARSITY.value)
            elif completeness_ratio < qual_thresholds.target_completeness_ratio:
                dynamic_warnings.append(QualificationReasonCode.SUBTARGET_COMPLETENESS.value)

            if obs_count < effective_target_obs:
                if (
                    QualificationReasonCode.CRITICAL_DATA_SPARSITY.value not in dynamic_warnings
                    and QualificationReasonCode.SUBTARGET_COMPLETENESS.value not in dynamic_warnings
                    and QualificationReasonCode.MARGINAL_OBSERVATION_COUNT.value not in dynamic_warnings
                ):
                    dynamic_warnings.append(QualificationReasonCode.MARGINAL_OBSERVATION_COUNT.value)

            # 2. Reading quality
            qual_evaluated_count = int(win_qual_count) if win_qual_count is not None else 0
            valid_qual_count = int(win_valid_count) if win_valid_count is not None else 0
            valid_readings_ratio: Optional[float] = None

            if qual_evaluated_count > 0:
                qual_coverage_ratio = qual_evaluated_count / float(obs_count) if obs_count > 0 else 0.0
                valid_readings_ratio = valid_qual_count / float(qual_evaluated_count)

                if qual_coverage_ratio < qual_thresholds.min_quality_coverage_ratio:
                    dynamic_warnings.append(QualificationReasonCode.PARTIAL_READING_QUALITY_COVERAGE.value)
                else:
                    if valid_readings_ratio < qual_thresholds.min_valid_reading_ratio:
                        dynamic_warnings.append(QualificationReasonCode.POOR_READING_QUALITY.value)
                    elif valid_readings_ratio < qual_thresholds.target_valid_reading_ratio:
                        dynamic_warnings.append(QualificationReasonCode.DEGRADED_READING_QUALITY.value)

            # Determine dynamic trust level:
            # - INCONCLUSIVE is strictly preserved as TENTATIVE
            # - QUALIFIED is downgraded to TENTATIVE if dynamic window is materially degraded
            if q_status_str == BaselineQualificationStatus.INCONCLUSIVE.value:
                trust_level = "TENTATIVE"
            elif dynamic_warnings:
                trust_level = "TENTATIVE"
            else:
                trust_level = "TRUSTED"

            explanation = (
                f"Observation of {val:.4f} kWh at {ts} is {abs_z:.2f} standard deviations {direction} "
                f"the preceding {w_size}-hour window using {obs_count} available observations "
                f"(mean: {r_mean:.4f} kWh, std dev: {r_std:.4f} kWh) for meter {mid} at plant {pid}."
            )

            # Combine initial baseline qualification reasons with dynamic comparison-window warnings
            combined_reasons = list(b_info.get("qualification_reasons", []))
            for dw in dynamic_warnings:
                if dw not in combined_reasons:
                    combined_reasons.append(dw)

            context_flags = {
                "window_size_hours": w_size,
                "historical_observations_used": obs_count,
                "current_observation_excluded": True,
                "rolling_std_kwh": float(round(r_std, 4)),
                "threshold_z": float(threshold_z),
                "evaluation_start": eval_start.isoformat(),
                "evaluation_end": eval_end.isoformat(),
                "baseline_qualification_status": q_status_str,
                "baseline_trust_level": trust_level,
                "qualification_reasons": combined_reasons,
                "window_coverage_ratio": round(completeness_ratio, 4),
                "source_table": "fact_energy_meter_hourly",
                "source_record_id": str(reading_id) if reading_id else None,
                "upload_id": str(upl_id) if upl_id else None,
                "detector_version": DETECTOR_VERSION_ROLLING_BASELINE,
                "lineage_status": "AVAILABLE" if reading_id else "UNAVAILABLE",
            }
            if valid_readings_ratio is not None:
                context_flags["window_valid_readings_ratio"] = round(valid_readings_ratio, 4)
            if dynamic_warnings:
                context_flags["dynamic_window_warnings"] = dynamic_warnings

            if q_status_str == BaselineQualificationStatus.INCONCLUSIVE.value:
                base_limitations = b_info.get("confidence_limitations") or "Baseline is INCONCLUSIVE"
                if dynamic_warnings:
                    context_flags["confidence_limitations"] = f"{base_limitations}; Dynamic comparison window warnings: {', '.join(dynamic_warnings)}"
                else:
                    context_flags["confidence_limitations"] = base_limitations
                warning_list = b_info.get("warnings", [])
                all_warns = list(warning_list)
                for dw in dynamic_warnings:
                    if dw not in all_warns:
                        all_warns.append(dw)
                warn_str = ", ".join(all_warns) if all_warns else "telemetry degradation"
                explanation += f" [Baseline Caveat: Baseline is INCONCLUSIVE ({warn_str}). Operational comparisons should proceed with caution.]"
            elif dynamic_warnings:
                warn_str = ", ".join(dynamic_warnings)
                context_flags["confidence_limitations"] = f"Comparison window telemetry degraded ({warn_str})"
                explanation += f" [Baseline Caveat: Comparison window telemetry is degraded ({warn_str}). Operational comparisons should proceed with caution.]"

            anomalies.append({
                "anomaly_type": anomaly_type,
                "plant_id": pid,
                "meter_id": mid,
                "line_id": None,
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "actual_value": _format_decimal(val, 4),
                "baseline_value": _format_decimal(r_mean, 4),
                "deviation_score": round(z_float, 4),
                "severity": sev,
                "explanation": explanation,
                "context_flags": context_flags,
                "source_table": "fact_energy_meter_hourly",
                "source_record_id": str(reading_id) if reading_id else None,
                "upload_id": str(upl_id) if upl_id else None,
                "detector_version": DETECTOR_VERSION_ROLLING_BASELINE,
            })

    return {
        "analysis_type": "rolling_baseline",
        "window_size_hours": w_size,
        "min_observations": min_observations,
        "threshold_z": threshold_z,
        "total_anomalies_detected": len(anomalies),
        "total_evaluated_observations": total_evaluated,
        "insufficient_history_count": insufficient_count,
        "zero_variance_count": zero_var_count,
        "insufficient_history_meters": sorted([m for m in all_insufficient_meters if m]),
        "zero_variance_meters": sorted([m for m in all_zero_var_meters if m]),
        "eligible_groups_count": len(eligible_groups),
        "qualified_groups_count": len(qualified_groups),
        "inconclusive_groups_count": len(inconclusive_groups),
        "disqualified_groups_count": len(disqualified_groups),
        "disqualified_groups": disqualified_groups,
        "zero_variance_groups": zero_variance_groups,
        "insufficient_observations_groups": insufficient_obs_groups,
        "baseline_period": {
            "start_time": baseline_start.isoformat(),
            "end_time": baseline_end.isoformat(),
            "window_size_hours": w_size,
        },
        "evaluation_period": {
            "start_time": eval_start.isoformat(),
            "end_time": eval_end.isoformat(),
            "evaluation_scope": evaluation_scope,
        },
        "meter_baselines": meter_baselines,
        "anomalies": anomalies[:limit] if limit is not None and limit >= 0 else anomalies,
    }


def detect_low_power_factor_anomalies(
    session: Session,
    plant_id: Optional[str] = None,
    meter_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    threshold: Decimal = DEFAULT_POWER_FACTOR_THRESHOLD,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Detect meter readings where power factor falls below the application monitoring threshold.

    - Default threshold: 0.90 (application-level engineering monitoring benchmark).
    - Reports occurrence count, timestamps, plant, meter, and measured power factor.
    - Does NOT claim financial penalties or savings without verified utility tariff rate structures.
    """
    if threshold <= Decimal("0") or threshold > Decimal("1.0"):
        raise ValueError("threshold must be between 0 and 1")

    params: Dict[str, Any] = {
        "threshold": float(threshold),
    }
    where_parts = ["power_factor < :threshold"]
    if plant_id:
        where_parts.append("plant_id = :plant_id")
        params["plant_id"] = plant_id
    if meter_id:
        where_parts.append("meter_id = :meter_id")
        params["meter_id"] = meter_id
    if start_time:
        where_parts.append("timestamp >= :start_time")
        params["start_time"] = start_time
    if end_time:
        where_parts.append("timestamp <= :end_time")
        params["end_time"] = end_time

    where_clause = "WHERE " + " AND ".join(where_parts)

    sql = f"""
        SELECT
            timestamp,
            plant_id,
            meter_id,
            power_factor,
            consumption_kwh,
            meter_reading_id,
            upload_id
        FROM fact_energy_meter_hourly
        {where_clause}
        ORDER BY power_factor ASC, timestamp ASC
    """
    rows = session.execute(text(sql), params).fetchall()

    anomalies: List[Dict[str, Any]] = []
    for r in rows:
        ts, pid, mid, pf, kwh, reading_id, upl_id = r
        pf_dec = Decimal(str(pf))
        thresh_dec = Decimal(str(threshold))
        deficit = thresh_dec - pf_dec
        sev = _classify_pf_severity(pf_dec, thresh_dec)

        explanation = (
            f"Measured power factor of {pf_dec:.4f} at {ts} is below the application monitoring threshold "
            f"of {thresh_dec:.4f} (deficit: {deficit:.4f}) on meter {mid} at plant {pid}. "
            f"Active energy during hour: {kwh:.4f} kWh."
        )

        anomalies.append({
            "anomaly_type": "LOW_POWER_FACTOR",
            "plant_id": pid,
            "meter_id": mid,
            "line_id": None,
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "actual_value": _format_decimal(pf_dec, 4),
            "baseline_value": _format_decimal(thresh_dec, 4),
            "deviation_score": float(round(deficit, 4)),
            "severity": sev,
            "explanation": explanation,
            "context_flags": {
                "threshold": float(threshold),
                "deficit": float(round(deficit, 4)),
                "consumption_kwh": float(round(kwh, 4)),
                "tariff_penalty_claimed": False,
                "note": "Power factor deficit detected; monetary penalty requires site-specific utility tariff schedule.",
                "source_table": "fact_energy_meter_hourly",
                "source_record_id": str(reading_id) if reading_id else None,
                "upload_id": str(upl_id) if upl_id else None,
                "detector_version": DETECTOR_VERSION_LOW_POWER_FACTOR,
                "lineage_status": "AVAILABLE" if reading_id else "UNAVAILABLE",
            },
            "source_table": "fact_energy_meter_hourly",
            "source_record_id": str(reading_id) if reading_id else None,
            "upload_id": str(upl_id) if upl_id else None,
            "detector_version": DETECTOR_VERSION_LOW_POWER_FACTOR,
        })

    return {
        "analysis_type": "low_power_factor",
        "threshold": float(threshold),
        "total_anomalies_detected": len(anomalies),
        "anomalies": anomalies[:limit] if limit is not None and limit >= 0 else anomalies,
    }


def detect_zero_production_standby_anomalies(
    session: Session,
    plant_id: Optional[str] = None,
    line_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Identify process-meter energy consumed during zero-output production hours.

    Key Engineering Protections:
    - Verifies 1:1 line-to-process meter topology to prevent duplicate energy assignment.
    - Joins deterministic line-to-process meter mapping:
        SMT lines -> MTR-SMT
        FAL lines -> MTR-FAL
    - Keeps facility utility meters (HVAC, Compressor, Chiller) strictly separate.
    - Filters facility utilities by plant, date range, and the exact zero-production timestamps.
    - Reports observed energy and stoppage duration.
    - Does NOT label energy as avoidable waste or claim savings without an engineering baseline.
    """
    # 1. Topology check: verify single line per process area per plant to prevent silent energy duplication
    topo_sql = """
        SELECT plant_id, line_type, COUNT(*) as cnt
        FROM dim_production_line
        GROUP BY plant_id, line_type
        HAVING COUNT(*) > 1
    """
    multi_line_violation = session.execute(text(topo_sql)).fetchall()
    if multi_line_violation:
        pid, ltype, cnt = multi_line_violation[0]
        raise ValueError(
            f"Multi-line topology limitation: Plant '{pid}' has {cnt} lines for '{ltype}', "
            f"sharing a single process meter. Telemetry schema cannot allocate process standby energy "
            f"without line-level sub-metering."
        )

    params: Dict[str, Any] = {}
    where_parts = ["p.actual_qty = 0"]

    if plant_id:
        where_parts.append("p.plant_id = :plant_id")
        params["plant_id"] = plant_id
    if line_id:
        where_parts.append("p.line_id = :line_id")
        params["line_id"] = line_id
    if start_time:
        where_parts.append("p.event_ts >= :start_time")
        params["start_time"] = start_time
    if end_time:
        where_parts.append("p.event_ts <= :end_time")
        params["end_time"] = end_time

    where_clause = "WHERE " + " AND ".join(where_parts)

    sql = f"""
        SELECT
            p.event_id,
            p.event_ts,
            p.plant_id,
            p.line_id,
            l.line_type,
            l.area,
            p.product_id,
            p.target_qty,
            p.actual_qty,
            p.downtime_min,
            p.downtime_reason,
            e.meter_id,
            e.consumption_kwh as process_kwh,
            p.upload_id as prod_upload_id,
            e.meter_reading_id,
            e.upload_id as energy_upload_id
        FROM fact_hourly_production p
        JOIN dim_production_line l ON p.line_id = l.line_id AND p.plant_id = l.plant_id
        JOIN fact_energy_meter_hourly e ON p.event_ts = e.timestamp AND p.plant_id = e.plant_id
          AND e.consumption_kwh > 0
          AND (
            (p.line_id IN ('SMT-L1', 'SMT-L2') AND e.meter_id = 'MTR-SMT') OR
            (p.line_id IN ('FAL-L1', 'FAL-L2') AND e.meter_id = 'MTR-FAL')
          )
        {where_clause}
        ORDER BY p.event_ts ASC, p.line_id ASC
    """
    rows = session.execute(text(sql), params).fetchall()

    anomalies: List[Dict[str, Any]] = []
    total_standby_kwh = Decimal("0")
    total_downtime_min = 0

    smt_standby_kwh = Decimal("0")
    fal_standby_kwh = Decimal("0")
    reason_counts: Dict[str, int] = {}

    for r in rows:
        (
            event_id,
            event_ts,
            pid,
            lid,
            ltype,
            area,
            prod_id,
            target_q,
            actual_q,
            dt_min,
            dt_reason,
            mid,
            kwh,
            prod_upl_id,
            energy_reading_id,
            energy_upl_id,
        ) = r
        kwh_dec = Decimal(str(kwh))
        total_standby_kwh += kwh_dec
        total_downtime_min += int(dt_min)

        if area == "SMT":
            smt_standby_kwh += kwh_dec
        else:
            fal_standby_kwh += kwh_dec

        reason_counts[dt_reason] = reason_counts.get(dt_reason, 0) + 1

        explanation = (
            f"Line {lid} ({area}) recorded 0 units during hour {event_ts} with reported downtime of "
            f"{dt_min} min ({dt_reason}). Process meter {mid} registered {kwh_dec:.4f} kWh during that interval."
        )

        source_records = [
            {
                "source_table": "fact_hourly_production",
                "source_record_id": str(event_id) if event_id else None,
                "upload_id": str(prod_upl_id) if prod_upl_id else None,
                "role": "PRODUCTION_ZERO_OUTPUT_EVENT",
            },
            {
                "source_table": "fact_energy_meter_hourly",
                "source_record_id": str(energy_reading_id) if energy_reading_id else None,
                "upload_id": str(energy_upl_id) if energy_upl_id else None,
                "role": "PROCESS_ENERGY_MEASUREMENT",
            },
        ]

        anomalies.append({
            "anomaly_type": "ZERO_PRODUCTION_STANDBY_ENERGY",
            "plant_id": pid,
            "meter_id": mid,
            "line_id": lid,
            "timestamp": event_ts.isoformat() if hasattr(event_ts, "isoformat") else str(event_ts),
            "actual_value": _format_decimal(kwh_dec, 4),
            "baseline_value": None,
            "deviation_score": float(round(kwh_dec, 4)),
            "severity": "MEDIUM",
            "explanation": explanation,
            "context_flags": {
                "event_id": event_id,
                "meter_reading_id": energy_reading_id,
                "area": area,
                "downtime_min": dt_min,
                "downtime_reason": dt_reason,
                "target_qty": target_q,
                "product_id": prod_id,
                "category": "STANDBY_POWER",
                "avoidable_waste_claimed": False,
                "note": "Energy during a zero-output interval; no expected-energy baseline is available, and it is not classified as avoidable waste.",
                "detector_version": DETECTOR_VERSION_STANDBY_ENERGY,
                "lineage_status": "MULTI_SOURCE",
                "lineage_reason": "Cross-domain correlation between zero-output production interval and process meter energy draw.",
                "source_records": source_records,
            },
            "source_table": None,
            "source_record_id": None,
            "upload_id": None,
            "detector_version": DETECTOR_VERSION_STANDBY_ENERGY,
        })

    # Query facility utility totals strictly during these intended zero-production timestamps for complete segregation.
    # Respects plant_id and date/time filters. If no zero-production events exist, utility totals are safely 0.
    utility_breakdown = {
        m: {
            "readings": 0,
            "consumption_kwh": Decimal("0.0000"),
        }
        for m in ("MTR-HVAC", "MTR-COMPRESSOR", "MTR-CHILLER")
    }

    utility_sql = f"""
        WITH zero_ts AS (
            SELECT DISTINCT p.plant_id, p.event_ts AS timestamp
            FROM fact_hourly_production p
            {where_clause}
        )
        SELECT
            e.meter_id,
            COUNT(*) as readings_count,
            SUM(e.consumption_kwh) as utility_kwh
        FROM fact_energy_meter_hourly e
        JOIN zero_ts z ON e.plant_id = z.plant_id AND e.timestamp = z.timestamp
        WHERE e.meter_id IN ('MTR-HVAC', 'MTR-COMPRESSOR', 'MTR-CHILLER')
        GROUP BY e.meter_id
        ORDER BY e.meter_id
    """
    util_rows = session.execute(text(utility_sql), params).fetchall()
    for r in util_rows:
        if r[0] in utility_breakdown:
            utility_breakdown[r[0]] = {
                "readings": int(r[1]),
                "consumption_kwh": _format_decimal(r[2], 4),
            }

    return {
        "analysis_type": "zero_production_standby",
        "total_events_detected": len(anomalies),
        "total_standby_energy_kwh": _format_decimal(total_standby_kwh, 4),
        "total_stoppage_minutes": total_downtime_min,
        "smt_standby_energy_kwh": _format_decimal(smt_standby_kwh, 4),
        "fal_standby_energy_kwh": _format_decimal(fal_standby_kwh, 4),
        "downtime_reasons_breakdown": reason_counts,
        "facility_utilities_status": {
            "segregated": True,
            "note": "Facility utilities (HVAC, Compressor, Chiller) provide baseline plant infrastructure and are excluded from process standby.",
            "overall_utility_totals": utility_breakdown,
        },
        "anomalies": anomalies[:limit] if limit is not None and limit >= 0 else anomalies,
    }


def detect_all_anomalies(
    session: Session,
    plant_id: Optional[str] = None,
    meter_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    z_threshold: float = 3.0,
    lookback_days: int = 30,
    rolling_window_hours: int = 24,
    pf_threshold: Decimal = DEFAULT_POWER_FACTOR_THRESHOLD,
    limit: Optional[int] = None,
    evaluation_scope: str = "latest_day",
) -> Dict[str, Any]:
    """
    Run the unified deterministic anomaly suite across energy and production data.
    """
    stat_anomalies = detect_energy_statistical_anomalies(
        session=session,
        plant_id=plant_id,
        meter_id=meter_id,
        start_time=start_time,
        end_time=end_time,
        lookback_days=lookback_days,
        threshold_z=z_threshold,
        limit=limit,
        evaluation_scope=evaluation_scope,
    )
    rolling_anomalies = detect_rolling_baseline_anomalies(
        session=session,
        plant_id=plant_id,
        meter_id=meter_id,
        start_time=start_time,
        end_time=end_time,
        window_size=rolling_window_hours,
        threshold_z=z_threshold,
        limit=limit,
        evaluation_scope=evaluation_scope,
    )
    pf_anomalies = detect_low_power_factor_anomalies(
        session=session,
        plant_id=plant_id,
        meter_id=meter_id,
        start_time=start_time,
        end_time=end_time,
        threshold=pf_threshold,
        limit=limit,
    )
    standby_anomalies = detect_zero_production_standby_anomalies(
        session=session,
        plant_id=plant_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )

    total_count = (
        stat_anomalies["total_anomalies_detected"]
        + rolling_anomalies["total_anomalies_detected"]
        + pf_anomalies["total_anomalies_detected"]
        + standby_anomalies["total_events_detected"]
    )

    return {
        "plant_id": plant_id,
        "analysis_period": {
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
        },
        "total_anomalies_detected": total_count,
        "statistical_zscore": stat_anomalies,
        "rolling_baseline": rolling_anomalies,
        "low_power_factor": pf_anomalies,
        "zero_production_standby": standby_anomalies,
    }
