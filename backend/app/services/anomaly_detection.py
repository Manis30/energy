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
DETECTOR_VERSION_PERSISTENT_BASELOAD = "persistent_baseload:1.0.0"
DETECTOR_VERSION_ZERO_OUTPUT_RESTART = "zero_output_restart:1.0.0"

# Central Evidence Classification constants across finding lifecycle and schemas
EVIDENCE_TRUSTED = "TRUSTED"
EVIDENCE_TENTATIVE = "TENTATIVE"
EVIDENCE_INCONCLUSIVE = "INCONCLUSIVE"
EVIDENCE_DISQUALIFIED = "DISQUALIFIED"


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

    Evaluates observations within the evaluation period [eval_start, eval_end) against a
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

    if start_time is not None and end_time is not None:
        eval_start = start_time
        if end_time == start_time:
            eval_end = start_time + timedelta(days=1)
        elif end_time.hour == 23 and end_time.minute == 0 and end_time.second == 0:
            eval_end = end_time + timedelta(hours=1)
        else:
            eval_end = end_time
        baseline_end = eval_start
        baseline_start = eval_start - timedelta(days=int(lookback_days))
    elif start_time is not None:
        eval_start = start_time
        eval_end = start_time + timedelta(days=1)
        baseline_end = eval_start
        baseline_start = eval_start - timedelta(days=int(lookback_days))
    elif end_time is not None:
        eval_end = end_time
        eval_start = eval_end - timedelta(days=1)
        baseline_end = eval_start
        baseline_start = eval_start - timedelta(days=int(lookback_days))
    elif max_ts is not None:
        if evaluation_scope == "historical" and min_ts is not None:
            baseline_start = min_ts
            baseline_end = min_ts + timedelta(days=int(lookback_days))
            eval_start = baseline_end
            eval_end = datetime.combine(max_ts.date() + timedelta(days=1), datetime.min.time()) if max_ts else datetime.utcnow()
            if eval_start > eval_end:
                eval_start = eval_end
        else:
            # Single latest day scope: 24-hour half-open window ending at next day midnight
            eval_end = datetime.combine(max_ts.date() + timedelta(days=1), datetime.min.time())
            eval_start = datetime.combine(max_ts.date(), datetime.min.time())
            baseline_end = eval_start
            baseline_start = eval_start - timedelta(days=int(lookback_days))
    else:
        now = datetime.utcnow()
        eval_end = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        eval_start = datetime.combine(now.date(), datetime.min.time())
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
          AND timestamp < :eval_end
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
              AND f.timestamp < :eval_end
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

            if q_status_str == "QUALIFIED":
                evidence_cls = EVIDENCE_TRUSTED
            elif q_status_str == "INCONCLUSIVE":
                evidence_cls = EVIDENCE_INCONCLUSIVE
            elif q_status_str in ("NOT_QUALIFIED", "DISQUALIFIED"):
                evidence_cls = EVIDENCE_DISQUALIFIED
            else:
                evidence_cls = EVIDENCE_TENTATIVE

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
                "baseline_trust_level": evidence_cls,
                "evidence_classification": evidence_cls,
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
                "qualification_status": q_status_str,
                "trust_level": evidence_cls,
                "evidence_classification": evidence_cls,
                "confidence": "HIGH" if q_status_str == "QUALIFIED" else ("LOW" if q_status_str == "NOT_QUALIFIED" else "MEDIUM"),
                "reason_codes": b_info.get("qualification_reasons", []),
                "comparison_window": f"{lookback_days}d",
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

    if start_time is not None and end_time is not None:
        eval_start = start_time
        if end_time == start_time:
            eval_end = start_time + timedelta(days=1)
        elif end_time.hour == 23 and end_time.minute == 0 and end_time.second == 0:
            eval_end = end_time + timedelta(hours=1)
        else:
            eval_end = end_time
    elif start_time is not None:
        eval_start = start_time
        eval_end = start_time + timedelta(days=1)
    elif end_time is not None:
        eval_end = end_time
        eval_start = eval_end - timedelta(days=1)
    elif max_ts is not None:
        if evaluation_scope == "historical" and min_ts is not None:
            eval_start = min_ts + timedelta(hours=w_size)
            eval_end = datetime.combine(max_ts.date() + timedelta(days=1), datetime.min.time()) if max_ts else datetime.utcnow()
            if eval_start > eval_end:
                eval_start = eval_end
        else:
            # Single latest day scope: 24-hour half-open window ending at next day midnight
            eval_end = datetime.combine(max_ts.date() + timedelta(days=1), datetime.min.time())
            eval_start = datetime.combine(max_ts.date(), datetime.min.time())
    else:
        now = datetime.utcnow()
        eval_end = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        eval_start = datetime.combine(now.date(), datetime.min.time())

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
          AND timestamp < :eval_end
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
                  AND timestamp < :eval_end
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
                  AND timestamp < :eval_end
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
                  AND timestamp < :eval_end
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
              AND timestamp < :eval_end
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

            if q_status_str == BaselineQualificationStatus.QUALIFIED.value:
                evidence_cls = EVIDENCE_TRUSTED
            elif q_status_str == BaselineQualificationStatus.INCONCLUSIVE.value:
                evidence_cls = EVIDENCE_INCONCLUSIVE
            elif q_status_str == BaselineQualificationStatus.NOT_QUALIFIED.value:
                evidence_cls = EVIDENCE_DISQUALIFIED
            else:
                evidence_cls = EVIDENCE_TENTATIVE

            context_flags = {
                "window_size_hours": w_size,
                "historical_observations_used": obs_count,
                "current_observation_excluded": True,
                "rolling_std_kwh": float(round(r_std, 4)),
                "threshold_z": float(threshold_z),
                "evaluation_start": eval_start.isoformat(),
                "evaluation_end": eval_end.isoformat(),
                "baseline_qualification_status": q_status_str,
                "baseline_trust_level": evidence_cls,
                "evidence_classification": evidence_cls,
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
                "qualification_status": q_status_str,
                "trust_level": evidence_cls,
                "evidence_classification": evidence_cls,
                "confidence": "HIGH" if q_status_str == BaselineQualificationStatus.QUALIFIED.value else "MEDIUM",
                "reason_codes": b_info.get("qualification_reasons", []),
                "comparison_window": f"{w_size}h",
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


def _record_baseload_anomaly(
    run_rows: List[Any],
    b_data: Dict[str, Any],
    direction: str,
    threshold_pct: float,
    persistence_rule: int,
    lookback_days: int,
    anomalies: List[Dict[str, Any]],
):
    pid = run_rows[0][0]
    mid = run_rows[0][1]
    start_ts = run_rows[0][2]
    end_ts = run_rows[-1][2]
    readings_ids = [str(r[4]) for r in run_rows if r[4]]
    kwh_values = [float(r[3]) for r in run_rows]
    avg_kwh = sum(kwh_values) / len(kwh_values)
    base_val = b_data["mean_kwh"]
    dev_pct = ((avg_kwh - base_val) / base_val) * 100.0
    streak_len = len(run_rows)

    anomaly_type = (
        f"PERSISTENT_BASELOAD_{direction}"
        if b_data.get("low_load_proven")
        else f"COMPARABLE_PERIOD_ELECTRICITY_{direction}"
    )
    sev = "CRITICAL" if abs(dev_pct) >= 35.0 else ("HIGH" if abs(dev_pct) >= 25.0 else "MEDIUM")
    load_cls = b_data["load_classification"]

    start_str = start_ts.strftime("%Y-%m-%d %H:%M") if hasattr(start_ts, "strftime") else str(start_ts)
    end_str = (end_ts + timedelta(hours=1)).strftime("%H:%M") if hasattr(end_ts, "strftime") else str(end_ts)
    window_notation = f"[{start_ts.strftime('%H:%M') if hasattr(start_ts, 'strftime') else ''}, {end_str})"

    ref_win = b_data.get("reference_window", f"{lookback_days}d prior")
    stab_thresh = b_data.get("stability_threshold", "CV < 0.15")
    ll_evidence = b_data.get("low_load_evidence", {})

    explanation = (
        f"Persistent {direction.lower()} in {load_cls.lower()} detected across {streak_len} consecutive intervals "
        f"({window_notation} on {start_ts.strftime('%Y-%m-%d') if hasattr(start_ts, 'strftime') else ''}): "
        f"average rate of {avg_kwh:.2f} kWh/h vs baseline of {base_val:.2f} kWh/h "
        f"(observed change: {dev_pct:+.1f}%, threshold: ±{threshold_pct:.0f}%) on meter {mid} at plant {pid}. "
        f"Reference window: {ref_win} (N={b_data['sample_size']} eligible intervals, {stab_thresh}). "
        f"Low-load evidence: {ll_evidence.get('status', 'UNPROVEN')}. {b_data['boundary_note']}"
    )

    evidence_cls = EVIDENCE_TRUSTED if b_data.get("low_load_proven") and b_data["sample_size"] >= 10 else EVIDENCE_TENTATIVE

    anomalies.append({
        "anomaly_type": anomaly_type,
        "plant_id": pid,
        "meter_id": mid,
        "line_id": None,
        "timestamp": start_ts.isoformat() if hasattr(start_ts, "isoformat") else str(start_ts),
        "actual_value": _format_decimal(avg_kwh, 4),
        "baseline_value": _format_decimal(base_val, 4),
        "deviation_score": float(round(dev_pct, 2)),
        "severity": sev,
        "explanation": explanation,
        "context_flags": {
            "load_classification": load_cls,
            "boundary_note": b_data["boundary_note"],
            "reference_window": ref_win,
            "eligible_intervals": b_data["sample_size"],
            "low_load_evidence": ll_evidence,
            "exclusions": b_data.get("exclusions", []),
            "stability_threshold": stab_thresh,
            "observed_change": f"{dev_pct:+.2f}% ({avg_kwh:.2f} kWh/h vs baseline {base_val:.2f} kWh/h)",
            "streak_length_intervals": streak_len,
            "persistence_rule": f"At least {persistence_rule} consecutive intervals",
            "deviation_threshold_pct": threshold_pct,
            "prior_window_days": lookback_days,
            "sample_size": b_data["sample_size"],
            "baseline_std_kwh": b_data["std_kwh"],
            "interval_window": window_notation,
            "source_record_ids": readings_ids,
            "detector_version": DETECTOR_VERSION_PERSISTENT_BASELOAD,
            "evidence_classification": evidence_cls,
            "limits_of_interpretation": (
                "Persistent shift in verified low-load baseload. Facilities inspection required to verify auxiliary equipment off-shift state."
                if b_data.get("low_load_proven") else
                "Sustained shift in comparable-period electricity use. Root cause investigation requires checking operating schedule, auxiliary equipment setpoints, or shift handover."
            ),
        },
        "source_table": "fact_energy_meter_hourly",
        "source_record_id": readings_ids[0] if readings_ids else None,
        "upload_id": str(run_rows[0][5]) if run_rows[0][5] else None,
        "detector_version": DETECTOR_VERSION_PERSISTENT_BASELOAD,
        "qualification_status": "QUALIFIED",
        "trust_level": evidence_cls,
        "evidence_classification": evidence_cls,
        "confidence": "HIGH" if evidence_cls == EVIDENCE_TRUSTED else "MEDIUM",
        "reason_codes": [f"PERSISTENT_BASELOAD_{direction}", "CONSECUTIVE_INTERVALS_MET"],
        "comparison_window": f"{lookback_days}d",
    })


def detect_persistent_baseload_anomalies(
    session: Session,
    plant_id: Optional[str] = None,
    meter_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    lookback_days: int = 14,
    min_sample_size: int = 5,
    deviation_threshold_pct: float = 15.0,
    persistence_intervals: int = 3,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Detect persistent baseload or comparable-period electricity use changes.

    Requirements:
    - Screen shifts in kWh/h across low-load or comparable intervals for a plant or meter.
    - Qualify what is true plant unvarying baseload vs 'Change in comparable-period electricity use'
      (e.g., process line standby vs plant unvarying infrastructure load).
    - Explicit prior window (default 14 days), minimum sample size (default 5 intervals),
      deviation threshold (default 15%), and persistence rule (at least 3 consecutive intervals).
    - Deterministic derivation from database records.
    - Central evidence classification: TRUSTED, TENTATIVE, INCONCLUSIVE, DISQUALIFIED.
    """
    if lookback_days < 1:
        raise ValueError("lookback_days must be at least 1")
    if min_sample_size < 2:
        raise ValueError("min_sample_size must be at least 2")
    if deviation_threshold_pct <= 0:
        raise ValueError("deviation_threshold_pct must be positive")
    if persistence_intervals < 2:
        raise ValueError("persistence_intervals must be at least 2")

    # Time boundaries determination
    if start_time is not None and end_time is not None:
        eval_start = start_time
        if end_time == start_time:
            eval_end = start_time + timedelta(days=1)
        elif end_time.hour == 23 and end_time.minute == 0 and end_time.second == 0:
            eval_end = end_time + timedelta(hours=1)
        else:
            eval_end = end_time
    elif start_time is not None:
        eval_start = start_time
        eval_end = start_time + timedelta(days=1)
    else:
        max_ts_row = session.execute(text("SELECT MAX(timestamp) FROM fact_energy_meter_hourly")).fetchone()
        max_ts = max_ts_row[0] if max_ts_row and max_ts_row[0] else datetime.utcnow()
        eval_end = datetime.combine(max_ts.date() + timedelta(days=1), datetime.min.time())
        eval_start = datetime.combine(max_ts.date(), datetime.min.time())

    baseline_start = eval_start - timedelta(days=lookback_days)
    baseline_end = eval_start

    # Query baseline stats partitioned by (plant_id, meter_id)
    where_parts = []
    params: Dict[str, Any] = {
        "b_start": baseline_start,
        "b_end": baseline_end,
        "e_start": eval_start,
        "e_end": eval_end,
    }
    if plant_id:
        where_parts.append("plant_id = :plant_id")
        params["plant_id"] = plant_id
    if meter_id:
        where_parts.append("meter_id = :meter_id")
        params["meter_id"] = meter_id
    extra_filter = f"AND {' AND '.join(where_parts)}" if where_parts else ""

    # Query baseline intervals and production records partitioned by (plant_id, meter_id)
    where_parts = []
    params: Dict[str, Any] = {
        "b_start": baseline_start,
        "b_end": baseline_end,
        "e_start": eval_start,
        "e_end": eval_end,
    }
    if plant_id:
        where_parts.append("plant_id = :plant_id")
        params["plant_id"] = plant_id
    if meter_id:
        where_parts.append("meter_id = :meter_id")
        params["meter_id"] = meter_id
    extra_filter = f"AND {' AND '.join(where_parts)}" if where_parts else ""

    # Fetch individual baseline intervals to evaluate low-load evidence and stability independently
    baseline_intervals_sql = f"""
        SELECT
            plant_id,
            meter_id,
            timestamp,
            consumption_kwh,
            meter_reading_id
        FROM fact_energy_meter_hourly
        WHERE timestamp >= :b_start AND timestamp < :b_end
          AND consumption_kwh > 0
          {extra_filter}
        ORDER BY plant_id, meter_id, timestamp ASC
    """
    b_interval_rows = session.execute(text(baseline_intervals_sql), params).fetchall()

    # Group baseline readings by (plant_id, meter_id)
    baseline_by_group: Dict[Tuple[str, str], List[Any]] = {}
    for r in b_interval_rows:
        k = (r[0], r[1])
        baseline_by_group.setdefault(k, []).append(r)

    # Query matched production records in the reference window to evaluate low-load condition
    prod_where = ["event_ts >= :b_start", "event_ts < :b_end"]
    prod_params: Dict[str, Any] = {"b_start": baseline_start, "b_end": baseline_end}
    if plant_id:
        prod_where.append("plant_id = :plant_id")
        prod_params["plant_id"] = plant_id

    prod_sql = f"""
        SELECT
            plant_id,
            line_id,
            event_ts,
            actual_qty AS actual_units_produced,
            good_qty AS good_units_produced,
            downtime_min AS downtime_minutes
        FROM fact_hourly_production
        WHERE {' AND '.join(prod_where)}
    """
    prod_rows = session.execute(text(prod_sql), prod_params).fetchall()
    prod_by_plant_ts: Dict[Tuple[str, datetime], List[Any]] = {}
    for pr in prod_rows:
        k_prod = (pr[0], pr[2])
        prod_by_plant_ts.setdefault(k_prod, []).append(pr)

    # Fetch registered lines per plant to know full meter and utility boundaries
    line_rows = session.execute(text("SELECT line_id, plant_id, line_type FROM dim_production_line")).fetchall()
    lines_by_plant: Dict[str, List[str]] = {}
    for lr in line_rows:
        lines_by_plant.setdefault(lr[1], []).append(lr[0])

    group_baselines = {}
    disqualified_groups = {}
    CV_STABILITY_THRESHOLD = 0.15  # Maximum coefficient of variation allowed for stable baseline

    for (pid, mid), group_rows in baseline_by_group.items():
        all_readings = [float(r[3]) for r in group_rows]
        cnt = len(all_readings)

        # Disqualification check 1: Sample size
        if cnt < min_sample_size:
            disqualified_groups[f"{pid}_{mid}"] = (
                f"Sample size {cnt} is below minimum requirement of {min_sample_size} intervals"
            )
            continue

        # Determine meter boundary lines
        is_dedicated = False
        plant_lines = lines_by_plant.get(pid, [])
        if "SMT" in mid.upper():
            boundary_lines = [l for l in plant_lines if "SMT" in l.upper()]
            is_dedicated = True
        elif "FAL" in mid.upper() or "ASSEMBLY" in mid.upper():
            boundary_lines = [l for l in plant_lines if "FAL" in l.upper()]
            is_dedicated = True
        else:
            # Shared utility meter: serves all lines across the plant
            boundary_lines = plant_lines
            is_dedicated = False

        # Evaluate Condition 1: Low-load evidence across boundary lines
        # For dedicated process meter: matched production records must show zero output / stoppage on its lines
        # For shared utility meter: a single stopped line cannot establish low load across the utility boundary;
        # whole-plant non-operating state (all lines at plant stopped) is required.
        low_load_rows = []
        excluded_active_intervals = 0

        for r in group_rows:
            ts = r[2]
            p_records = prod_by_plant_ts.get((pid, ts), [])
            if not p_records or not boundary_lines:
                # No production records to prove low-load
                continue

            # Check if all boundary lines were non-operating / stopped in this interval
            boundary_prod = [p for p in p_records if p[1] in boundary_lines]
            if len(boundary_prod) == len(boundary_lines):
                # We have complete matched records for all boundary lines
                # Distinguish missing reading (None) from measured zero (0)
                all_stopped = all(
                    (p[3] is not None and p[4] is not None and p[3] == 0 and p[4] == 0) or
                    (p[5] is not None and p[5] >= 60)
                    for p in boundary_prod
                )
                if all_stopped:
                    low_load_rows.append(r)
                else:
                    excluded_active_intervals += 1

        low_load_proven = len(low_load_rows) >= min_sample_size

        # Select candidate evaluation set:
        # If low-load is proven across eligible intervals, evaluate statistics on the low-load intervals.
        # Otherwise, use the comparable historical population.
        if low_load_proven:
            eval_dataset = [float(r[3]) for r in low_load_rows]
            eval_count = len(eval_dataset)
            exclusions_list = [f"Excluded {excluded_active_intervals} active production intervals from low-load baseline population"]
            low_load_detail = (
                f"Demonstrated low-load condition confirmed by complete matched production records "
                f"across all boundary lines ({', '.join(boundary_lines)}). N={eval_count} low-load intervals."
            )
        else:
            eval_dataset = all_readings
            eval_count = cnt
            exclusions_list = [
                f"Low-load condition unverified across full meter boundary ({', '.join(boundary_lines)}). "
                f"Comparison population uses {cnt} historical operating intervals."
            ]
            low_load_detail = (
                f"Low-load evidence missing across full meter boundary ({', '.join(boundary_lines)}). "
                f"A single stopped line cannot establish low load for a shared utility or process boundary."
            )

        mean_v = sum(eval_dataset) / eval_count
        med_v = sorted(eval_dataset)[eval_count // 2]
        variance = sum((x - mean_v) ** 2 for x in eval_dataset) / (eval_count - 1) if eval_count > 1 else 0.0
        std_v = math.sqrt(variance)

        # Disqualification check 2: Zero variance flatline
        if std_v == 0.0:
            disqualified_groups[f"{pid}_{mid}"] = "Baseline exhibits zero-variance flatline (stddev == 0.0000 kWh)"
            continue

        # Evaluate Condition 2: Stability (low coefficient of variation establishes stability only)
        cv = (std_v / mean_v) if mean_v > 0 else 1.0
        is_stable = cv < CV_STABILITY_THRESHOLD

        if not is_stable:
            disqualified_groups[f"{pid}_{mid}"] = (
                f"Comparison inadequate: baseline stability threshold not met "
                f"(observed CV={cv:.2f} >= {CV_STABILITY_THRESHOLD:.2f}, threshold: CV < {CV_STABILITY_THRESHOLD:.2f})"
            )
            continue

        # Classification of load type:
        # Use "Baseload drift" ONLY when low-load evidence, sample size, stability, and persistence rules all pass.
        # When low-load evidence is missing but comparable historical change exists, use "Change in comparable-period electricity use".
        if low_load_proven:
            load_cls = "Baseload drift"
            boundary_note = (
                f"Demonstrated low-load reference period with verified non-operating production boundary "
                f"and stable electricity consumption (CV={cv:.2f}, N={eval_count} low-load intervals)."
            )
        else:
            load_cls = "Change in comparable-period electricity use"
            boundary_note = (
                f"Electricity use compared against historical reference population of {cnt} intervals "
                f"(CV={cv:.2f}, mean={mean_v:.2f} kWh/h on meter {mid}). "
                f"Low-load evidence across full meter boundary is unverified; classified as comparable-period change."
            )

        ref_window_str = f"[{baseline_start.strftime('%Y-%m-%d %H:%M')}, {baseline_end.strftime('%Y-%m-%d %H:%M')})"
        group_baselines[(pid, mid)] = {
            "sample_size": eval_count,
            "mean_kwh": mean_v,
            "median_kwh": med_v,
            "std_kwh": std_v,
            "cv": cv,
            "load_classification": load_cls,
            "boundary_note": boundary_note,
            "low_load_proven": low_load_proven,
            "reference_window": ref_window_str,
            "stability_threshold": f"CV < {CV_STABILITY_THRESHOLD:.2f} (observed CV={cv:.4f})",
            "exclusions": exclusions_list,
            "low_load_evidence": {
                "status": "QUALIFIED" if low_load_proven else "UNPROVEN",
                "meter_boundary": "DEDICATED_PROCESS" if is_dedicated else "SHARED_UTILITY",
                "detail": low_load_detail,
                "matched_production_checked": True,
                "boundary_lines": boundary_lines,
                "low_load_sample_count": len(low_load_rows),
            },
        }

    # Query evaluation observations
    eval_sql = f"""
        SELECT
            plant_id,
            meter_id,
            timestamp,
            consumption_kwh,
            meter_reading_id,
            upload_id
        FROM fact_energy_meter_hourly
        WHERE timestamp >= :e_start AND timestamp < :e_end
          AND consumption_kwh > 0
          {extra_filter}
        ORDER BY plant_id, meter_id, timestamp ASC
    """
    e_rows = session.execute(text(eval_sql), params).fetchall()

    # Group evaluation rows by (plant_id, meter_id)
    eval_by_group: Dict[Tuple[str, str], List[Any]] = {}
    for r in e_rows:
        k = (r[0], r[1])
        if k not in eval_by_group:
            eval_by_group[k] = []
        eval_by_group[k].append(r)

    anomalies: List[Dict[str, Any]] = []

    for group_key, rows_in_group in eval_by_group.items():
        if group_key not in group_baselines:
            continue

        b_data = group_baselines[group_key]
        base_val = b_data["mean_kwh"]
        if base_val <= 0:
            continue

        pid, mid = group_key

        # Track persistent consecutive runs
        current_run: List[Any] = []
        current_direction: Optional[str] = None

        for r in rows_in_group:
            kwh_float = float(r[3])
            pct_dev = ((kwh_float - base_val) / base_val) * 100.0

            if abs(pct_dev) >= deviation_threshold_pct:
                direction = "INCREASE" if pct_dev > 0 else "DECREASE"
                if current_direction == direction:
                    current_run.append(r)
                else:
                    if len(current_run) >= persistence_intervals:
                        _record_baseload_anomaly(current_run, b_data, current_direction, deviation_threshold_pct, persistence_intervals, lookback_days, anomalies)
                    current_run = [r]
                    current_direction = direction
            else:
                if len(current_run) >= persistence_intervals:
                    _record_baseload_anomaly(current_run, b_data, current_direction, deviation_threshold_pct, persistence_intervals, lookback_days, anomalies)
                current_run = []
                current_direction = None

        # Check trailing run
        if len(current_run) >= persistence_intervals:
            _record_baseload_anomaly(current_run, b_data, current_direction, deviation_threshold_pct, persistence_intervals, lookback_days, anomalies)

    return {
        "analysis_type": "persistent_baseload",
        "prior_window_days": lookback_days,
        "min_sample_size": min_sample_size,
        "deviation_threshold_pct": deviation_threshold_pct,
        "persistence_intervals": persistence_intervals,
        "baseline_period": {"start_time": baseline_start.isoformat(), "end_time": baseline_end.isoformat()},
        "evaluation_period": {"start_time": eval_start.isoformat(), "end_time": eval_end.isoformat()},
        "total_anomalies_detected": len(anomalies),
        "disqualified_groups": disqualified_groups,
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
        actual_end = end_time
        if start_time and actual_end == start_time:
            actual_end = start_time + timedelta(days=1)
        elif actual_end.hour == 23 and actual_end.minute == 0 and actual_end.second == 0:
            actual_end = actual_end + timedelta(hours=1)
        where_parts.append("timestamp < :end_time")
        params["end_time"] = actual_end
    elif start_time:
        where_parts.append("timestamp < :end_time")
        params["end_time"] = start_time + timedelta(days=1)

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
            "explanation": (
                f"Measured power factor of {pf_dec:.4f} at {ts} is below the engineering monitoring benchmark "
                f"of {thresh_dec:.4f} (deficit: {deficit:.4f}, source: CEA Technical Standards / IEEE 519 benchmark) "
                f"on meter {mid} at plant {pid}. Active energy: {kwh:.4f} kWh. "
                f"Note: Financial tariff penalty claims require the unsupplied utility billing contract."
            ),
            "context_flags": {
                "threshold": float(threshold),
                "threshold_source": "CEA Technical Standards / IEEE 519 benchmark (0.90 lag)",
                "deficit": float(round(deficit, 4)),
                "consumption_kwh": float(round(kwh, 4)),
                "tariff_penalty_claimed": False,
                "tariff_penalty_disclaimer": "Tariff penalty claims require the unsupplied utility billing contract.",
                "note": "Power factor deficit detected; monetary penalty requires site-specific utility tariff schedule.",
                "source_table": "fact_energy_meter_hourly",
                "source_record_id": str(reading_id) if reading_id else None,
                "upload_id": str(upl_id) if upl_id else None,
                "detector_version": DETECTOR_VERSION_LOW_POWER_FACTOR,
                "lineage_status": "AVAILABLE" if reading_id else "UNAVAILABLE",
                "evidence_classification": EVIDENCE_TRUSTED if reading_id else EVIDENCE_TENTATIVE,
            },
            "source_table": "fact_energy_meter_hourly",
            "source_record_id": str(reading_id) if reading_id else None,
            "upload_id": str(upl_id) if upl_id else None,
            "detector_version": DETECTOR_VERSION_LOW_POWER_FACTOR,
            "qualification_status": "QUALIFIED",
            "trust_level": EVIDENCE_TRUSTED if reading_id else EVIDENCE_TENTATIVE,
            "evidence_classification": EVIDENCE_TRUSTED if reading_id else EVIDENCE_TENTATIVE,
            "confidence": "HIGH",
            "reason_codes": ["POWER_FACTOR_BELOW_THRESHOLD"],
            "comparison_window": "HOURLY_METER_READING",
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
        actual_end = end_time
        if start_time and actual_end == start_time:
            actual_end = start_time + timedelta(days=1)
        elif actual_end.hour == 23 and actual_end.minute == 0 and actual_end.second == 0:
            actual_end = actual_end + timedelta(hours=1)
        where_parts.append("p.event_ts < :end_time")
        params["end_time"] = actual_end
    elif start_time:
        where_parts.append("p.event_ts < :end_time")
        params["end_time"] = start_time + timedelta(days=1)

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

        # Look up following productive interval if available
        following_row = session.execute(
            text("""
                SELECT event_ts, good_qty, actual_qty
                FROM fact_hourly_production
                WHERE plant_id = :pid AND line_id = :lid AND event_ts > :event_ts AND good_qty > 0
                ORDER BY event_ts ASC
                LIMIT 1
            """),
            {"pid": pid, "lid": lid, "event_ts": event_ts},
        ).fetchone()

        following_info = None
        following_str = ""
        if following_row:
            f_ts, f_good, f_act = following_row
            f_time_str = f_ts.strftime("%H:%M") if hasattr(f_ts, "strftime") else str(f_ts)
            following_str = f" At {f_time_str} the line produced {f_good} good units."
            following_info = {
                "timestamp": f_ts.isoformat() if hasattr(f_ts, "isoformat") else str(f_ts),
                "good_qty": int(f_good),
                "actual_qty": int(f_act),
            }

        hour_str = event_ts.strftime("%H:%M") if hasattr(event_ts, "strftime") else str(event_ts)
        observed_condition = (
            f"electricity consumed during zero-output hour at {hour_str} "
            f"(target: {target_q} units, actual: {actual_q}, downtime: {dt_min} min, reason: {dt_reason}). "
            f"Associated {mid} readings registered {kwh_dec:.4f} kWh."
        )
        limits_of_interpretation = (
            "The avoidable portion and verified savings are unknown. "
            "No expected-energy baseline is available."
        )
        suggested_investigation = "Investigate operating conditions and restart requirements."

        explanation = f"{observed_condition}{following_str} {suggested_investigation} {limits_of_interpretation}"

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
                "observed_condition": observed_condition,
                "limits_of_interpretation": limits_of_interpretation,
                "suggested_investigation": suggested_investigation,
                "following_productive_interval": following_info,
                "note": "Electricity consumed during zero-output interval; investigate operating conditions and restart requirements. The avoidable portion and verified savings are unknown.",
                "detector_version": DETECTOR_VERSION_STANDBY_ENERGY,
                "lineage_status": "MULTI_SOURCE",
                "lineage_reason": "Cross-domain correlation between zero-output production interval and process meter energy draw.",
                "source_records": source_records,
            },
            "source_table": None,
            "source_record_id": None,
            "upload_id": None,
            "detector_version": DETECTOR_VERSION_STANDBY_ENERGY,
            "qualification_status": "QUALIFIED",
            "trust_level": EVIDENCE_TRUSTED,
            "evidence_classification": EVIDENCE_TRUSTED,
            "confidence": "MEDIUM",
            "reason_codes": ["ZERO_OUTPUT_PROCESS_DRAW"],
            "comparison_window": "HOURLY_CROSS_STREAM",
            "source_records": source_records,
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


def detect_zero_output_and_restart_anomalies(
    session: Session,
    plant_id: Optional[str] = None,
    line_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Detect zero-output line stoppage and restart anomalies reusing Phase 3 operating context service.

    Requirements:
    - Reuses Phase 3 operating-context service (get_operating_context_observations, detect_stoppage_episodes, compare_similar_periods).
    - Distinguishes three specific subtypes:
      1. UNUSUALLY_LONG_STOPPAGE: stoppage duration vs historical median duration
      2. HIGH_STOPPAGE_ENERGY_RATE: stoppage electricity rate (kWh/h) vs historical median rate
      3. UNUSUAL_RESTART_BEHAVIOR: restart good output, scrap, downtime
    - Protects the boundary: actual > 0 with good = 0 is a quality scrap event, NOT zero production.
    - Central evidence classification: TRUSTED, TENTATIVE, INCONCLUSIVE, DISQUALIFIED.
    """
    from app.services.operating_context import (
        build_actionable_investigation,
        compare_similar_periods,
        detect_stoppage_episodes,
        get_operating_context_observations,
    )

    # Load all observations for the selected line/plant across full dataset to support historical comparison
    obs = get_operating_context_observations(
        session=session,
        plant_id=plant_id,
        line_id=line_id,
        start_date=None,
        end_date=None,
        limit=50000,
    )

    all_episodes = detect_stoppage_episodes(obs, min_duration_hours=1)

    # Filter evaluation episodes matching parameters
    eval_episodes = []
    for ep in all_episodes:
        if plant_id and ep.plant_id != plant_id:
            continue
        if line_id and ep.line_id != line_id:
            continue
        if start_time and ep.last_interval < start_time:
            continue
        if end_time and ep.first_interval >= end_time:
            continue
        eval_episodes.append(ep)

    anomalies: List[Dict[str, Any]] = []

    for ep in eval_episodes:
        # STRICT BOUNDARY PROTECTION: actual_qty must be 0 for zero-production stoppage
        if ep.actual_qty > 0:
            # actual_qty > 0 with good_qty = 0 is a quality scrap event, NOT zero production
            continue

        comparison = compare_similar_periods(ep, all_episodes)
        actionable_inv = build_actionable_investigation(ep, comparison)

        evidence_cls = (
            EVIDENCE_TRUSTED
            if (comparison.eligible_count >= 5 and ep.energy_coverage_pct >= 100.0)
            else (EVIDENCE_TENTATIVE if comparison.eligible_count >= 1 else EVIDENCE_INCONCLUSIVE)
        )

        kwh_rate = round(ep.process_kwh / ep.observed_duration_hours, 2) if (ep.process_kwh and ep.observed_duration_hours > 0) else None
        source_rec_id = ep.source_record_ids[0] if ep.source_record_ids else None

        # 1. Unusually long stoppage (duration vs historical median / norm)
        hist_norm_dur = comparison.duration_max_hours or 1
        if comparison.eligible_count > 0 and ep.observed_duration_hours > hist_norm_dur:
            dur_diff = ep.observed_duration_hours - hist_norm_dur
            dur_sev = "HIGH" if ep.observed_duration_hours >= 3 else "MEDIUM"
            dur_explanation = (
                f"Line {ep.line_id} ({ep.process}) experienced an unusually long stoppage of {ep.observed_duration_hours} hours "
                f"across interval {ep.interval_window} (historical norm across {comparison.eligible_count} earlier episodes was {hist_norm_dur} hour). "
                f"Process electricity during zero-output hours: {ep.process_kwh:.3f} kWh. "
                f"Target shortfall during observed hours: {ep.target_shortfall} units. "
                f"Recorded downtime: {ep.recorded_downtime_minutes} min ({', '.join(ep.downtime_reasons_display)})."
            )
            anomalies.append({
                "anomaly_type": "UNUSUALLY_LONG_STOPPAGE",
                "plant_id": ep.plant_id,
                "meter_id": ep.meter_id if hasattr(ep, "meter_id") else None,
                "line_id": ep.line_id,
                "timestamp": ep.first_interval.isoformat(),
                "actual_value": _format_decimal(ep.observed_duration_hours, 2),
                "baseline_value": _format_decimal(hist_norm_dur, 2),
                "deviation_score": float(dur_diff),
                "severity": dur_sev,
                "explanation": dur_explanation,
                "context_flags": {
                    "subtype": "UNUSUALLY_LONG_STOPPAGE",
                    "interval_window": ep.interval_window,
                    "target_shortfall": ep.target_shortfall,
                    "process_kwh": ep.process_kwh,
                    "process_electricity_label": "Process electricity during zero-output hours",
                    "downtime_reasons_display": ep.downtime_reasons_display,
                    "historical_eligible_count": comparison.eligible_count,
                    "historical_median_duration": comparison.duration_max_hours,
                    "actionable_investigation": actionable_inv.model_dump(),
                    "source_records": [{"source_table": "fact_hourly_production", "source_record_id": s} for s in ep.source_record_ids],
                    "detector_version": DETECTOR_VERSION_ZERO_OUTPUT_RESTART,
                    "evidence_classification": evidence_cls,
                },
                "source_table": "fact_hourly_production",
                "source_record_id": source_rec_id,
                "upload_id": None,
                "detector_version": DETECTOR_VERSION_ZERO_OUTPUT_RESTART,
                "qualification_status": "QUALIFIED" if evidence_cls == EVIDENCE_TRUSTED else "PARTIAL",
                "trust_level": evidence_cls,
                "evidence_classification": evidence_cls,
                "confidence": "HIGH" if evidence_cls == EVIDENCE_TRUSTED else "MEDIUM",
                "reason_codes": ["UNUSUALLY_LONG_STOPPAGE_DURATION", "HISTORICAL_COMPARISON_EXCEEDED"],
                "comparison_window": comparison.historical_window,
            })

        # 2. High stoppage energy rate (kWh/h vs historical median rate)
        if (
            comparison.median_kwh_per_hour is not None
            and kwh_rate is not None
            and kwh_rate > (comparison.median_kwh_per_hour * 1.15)
        ):
            rate_deficit = kwh_rate - comparison.median_kwh_per_hour
            rate_sev = "HIGH" if kwh_rate > (comparison.median_kwh_per_hour * 1.30) else "MEDIUM"
            rate_explanation = (
                f"Line {ep.line_id} ({ep.process}) registered an elevated stoppage consumption rate of {kwh_rate:.2f} kWh/h "
                f"during interval {ep.interval_window} (historical median rate: {comparison.median_kwh_per_hour:.2f} kWh/h across {comparison.eligible_count} earlier episodes). "
                f"Process electricity during zero-output hours: {ep.process_kwh:.3f} kWh."
            )
            anomalies.append({
                "anomaly_type": "HIGH_STOPPAGE_ENERGY_RATE",
                "plant_id": ep.plant_id,
                "meter_id": ep.meter_id if hasattr(ep, "meter_id") else None,
                "line_id": ep.line_id,
                "timestamp": ep.first_interval.isoformat(),
                "actual_value": _format_decimal(kwh_rate, 4),
                "baseline_value": _format_decimal(comparison.median_kwh_per_hour, 4),
                "deviation_score": float(round(rate_deficit, 4)),
                "severity": rate_sev,
                "explanation": rate_explanation,
                "context_flags": {
                    "subtype": "HIGH_STOPPAGE_ENERGY_RATE",
                    "interval_window": ep.interval_window,
                    "process_kwh": ep.process_kwh,
                    "process_electricity_label": "Process electricity during zero-output hours",
                    "historical_median_kwh_per_hour": comparison.median_kwh_per_hour,
                    "actionable_investigation": actionable_inv.model_dump(),
                    "source_records": [{"source_table": "fact_energy_meter_hourly", "source_record_id": s} for s in ep.source_record_ids],
                    "detector_version": DETECTOR_VERSION_ZERO_OUTPUT_RESTART,
                    "evidence_classification": evidence_cls,
                },
                "source_table": "fact_energy_meter_hourly",
                "source_record_id": source_rec_id,
                "upload_id": None,
                "detector_version": DETECTOR_VERSION_ZERO_OUTPUT_RESTART,
                "qualification_status": "QUALIFIED" if evidence_cls == EVIDENCE_TRUSTED else "PARTIAL",
                "trust_level": evidence_cls,
                "evidence_classification": evidence_cls,
                "confidence": "HIGH" if evidence_cls == EVIDENCE_TRUSTED else "MEDIUM",
                "reason_codes": ["HIGH_STOPPAGE_ENERGY_DRAW", "MEDIAN_RATE_EXCEEDED"],
                "comparison_window": comparison.historical_window,
            })

        # 3. Unusual restart behavior (restart good output, scrap, downtime)
        if ep.next_restart_interval:
            rst = ep.next_restart_interval
            has_restart_scrap = (rst.reject_qty or 0) > 0
            has_low_ramp = (rst.actual_qty or 0) < 100 and (rst.consumption_kwh or 0) > 40.0
            has_restart_downtime = (rst.downtime_min or 0) > 15

            if has_restart_scrap or has_low_ramp or has_restart_downtime:
                rst_sev = "HIGH" if (rst.reject_qty or 0) >= 30 else "MEDIUM"
                rst_reasons = []
                if has_restart_scrap:
                    rst_reasons.append(f"{rst.reject_qty} scrap units on restart")
                if has_low_ramp:
                    rst_reasons.append(f"low output ramp ({rst.actual_qty} units at {rst.consumption_kwh:.2f} kWh)")
                if has_restart_downtime:
                    rst_reasons.append(f"{rst.downtime_min} min restart downtime")

                rst_explanation = (
                    f"Line {ep.line_id} ({ep.process}) exhibited unusual restart behavior following stoppage at {ep.interval_window}: "
                    f"restart interval {rst.interval_window} recorded {', '.join(rst_reasons)} "
                    f"({rst.actual_qty} actual units, {rst.good_qty} good, {rst.consumption_kwh:.2f} kWh)."
                )
                anomalies.append({
                    "anomaly_type": "UNUSUAL_RESTART_BEHAVIOR",
                    "plant_id": ep.plant_id,
                    "meter_id": ep.meter_id if hasattr(ep, "meter_id") else None,
                    "line_id": ep.line_id,
                    "timestamp": rst.timestamp.isoformat(),
                    "actual_value": _format_decimal(rst.reject_qty, 2),
                    "baseline_value": Decimal("0.00"),
                    "deviation_score": float(rst.reject_qty or 0),
                    "severity": rst_sev,
                    "explanation": rst_explanation,
                    "context_flags": {
                        "subtype": "UNUSUAL_RESTART_BEHAVIOR",
                        "stoppage_episode_id": ep.episode_id,
                        "restart_interval_window": rst.interval_window,
                        "restart_actual_qty": rst.actual_qty,
                        "restart_good_qty": rst.good_qty,
                        "restart_reject_qty": rst.reject_qty,
                        "restart_kwh": rst.consumption_kwh,
                        "restart_downtime_min": rst.downtime_min,
                        "actionable_investigation": actionable_inv.model_dump(),
                        "detector_version": DETECTOR_VERSION_ZERO_OUTPUT_RESTART,
                        "evidence_classification": EVIDENCE_TRUSTED,
                    },
                    "source_table": "fact_hourly_production",
                    "source_record_id": str(rst.event_id) if hasattr(rst, "event_id") and rst.event_id else None,
                    "upload_id": None,
                    "detector_version": DETECTOR_VERSION_ZERO_OUTPUT_RESTART,
                    "qualification_status": "QUALIFIED",
                    "trust_level": EVIDENCE_TRUSTED,
                    "evidence_classification": EVIDENCE_TRUSTED,
                    "confidence": "HIGH",
                    "reason_codes": ["UNUSUAL_RESTART_SCRAP_OR_RAMP", "QUALITY_SCRAP_ON_RESTART"],
                    "comparison_window": "POST_STOPPAGE_RESTART_INTERVAL",
                })

    return {
        "analysis_type": "zero_output_restart",
        "total_anomalies_detected": len(anomalies),
        "total_stoppage_episodes_evaluated": len(eval_episodes),
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
    baseload_anomalies = detect_persistent_baseload_anomalies(
        session=session,
        plant_id=plant_id,
        meter_id=meter_id,
        start_time=start_time,
        end_time=end_time,
        lookback_days=14,
        min_sample_size=5,
        deviation_threshold_pct=15.0,
        persistence_intervals=3,
        limit=limit,
    )
    restart_anomalies = detect_zero_output_and_restart_anomalies(
        session=session,
        plant_id=plant_id,
        line_id=None,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )

    total_count = (
        stat_anomalies["total_anomalies_detected"]
        + rolling_anomalies["total_anomalies_detected"]
        + pf_anomalies["total_anomalies_detected"]
        + standby_anomalies["total_events_detected"]
        + baseload_anomalies["total_anomalies_detected"]
        + restart_anomalies["total_anomalies_detected"]
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
        "persistent_baseload": baseload_anomalies,
        "zero_output_restart": restart_anomalies,
    }
