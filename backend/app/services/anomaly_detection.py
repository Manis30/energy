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

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import DEFAULT_POWER_FACTOR_THRESHOLD


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
    threshold_z: float = 3.0,
    min_observations: int = 10,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Detect hourly energy consumption anomalies using sample Z-score per (plant_id, meter_id).

    Z-score = (x - mean) / stddev
    Handles zero variance and insufficient observations safely.
    Does not compare unrelated meters or plants.
    """
    if threshold_z <= 0:
        raise ValueError("threshold_z must be positive")
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2")
    params: Dict[str, Any] = {
        "threshold_z": float(threshold_z),
        "min_obs": int(min_observations),
    }
    where_parts: List[str] = []
    outer_parts: List[str] = []
    if plant_id:
        where_parts.append("plant_id = :plant_id")
        outer_parts.append("f.plant_id = :plant_id")
        params["plant_id"] = plant_id
    if meter_id:
        where_parts.append("meter_id = :meter_id")
        outer_parts.append("f.meter_id = :meter_id")
        params["meter_id"] = meter_id
    if start_time:
        where_parts.append("timestamp >= :start_time")
        outer_parts.append("f.timestamp >= :start_time")
        params["start_time"] = start_time
    if end_time:
        where_parts.append("timestamp <= :end_time")
        outer_parts.append("f.timestamp <= :end_time")
        params["end_time"] = end_time

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    outer_clause = f"AND {' AND '.join(outer_parts)}" if outer_parts else ""

    # 1. Compute summary stats per meter and plant to detect zero variance & small samples
    stats_sql = f"""
        SELECT
            plant_id,
            meter_id,
            COUNT(*) as obs_count,
            AVG(consumption_kwh) as mean_kwh,
            COALESCE(STDDEV_SAMP(consumption_kwh), 0) as std_kwh,
            MIN(consumption_kwh) as min_kwh,
            MAX(consumption_kwh) as max_kwh
        FROM fact_energy_meter_hourly
        {where_clause}
        GROUP BY plant_id, meter_id
        ORDER BY plant_id, meter_id
    """
    stats_rows = session.execute(text(stats_sql), params).fetchall()

    meter_baselines: Dict[str, Any] = {}
    eligible_groups = []
    zero_variance_groups = []
    insufficient_obs_groups = []

    for r in stats_rows:
        pid, mid, count, mean_val, std_val, min_val, max_val = r
        group_key = f"{pid}_{mid}"
        b_info = {
            "plant_id": pid,
            "meter_id": mid,
            "obs_count": count,
            "mean_kwh": _format_decimal(mean_val, 4),
            "std_kwh": _format_decimal(std_val, 4),
            "min_kwh": _format_decimal(min_val, 4),
            "max_kwh": _format_decimal(max_val, 4),
            "zero_variance": std_val == 0,
            "insufficient_observations": count < min_observations,
        }
        meter_baselines[group_key] = b_info

        if count < min_observations:
            insufficient_obs_groups.append(group_key)
        elif std_val == 0:
            zero_variance_groups.append(group_key)
        else:
            eligible_groups.append((pid, mid))

    # 2. Query individual anomalies for eligible groups
    query_sql = f"""
        WITH stats AS (
            SELECT
                plant_id,
                meter_id,
                COUNT(*) as obs_count,
                AVG(consumption_kwh) as mean_kwh,
                COALESCE(STDDEV_SAMP(consumption_kwh), 0) as std_kwh
            FROM fact_energy_meter_hourly
            {where_clause}
            GROUP BY plant_id, meter_id
        )
        SELECT
            f.plant_id,
            f.meter_id,
            f.timestamp,
            f.consumption_kwh,
            s.mean_kwh,
            s.std_kwh,
            s.obs_count,
            (f.consumption_kwh - s.mean_kwh) / NULLIF(s.std_kwh, 0) as z_score
        FROM fact_energy_meter_hourly f
        JOIN stats s ON f.plant_id = s.plant_id AND f.meter_id = s.meter_id
        WHERE s.obs_count >= :min_obs
          AND s.std_kwh > 0
          AND ABS((f.consumption_kwh - s.mean_kwh) / s.std_kwh) >= :threshold_z
          {outer_clause}
        ORDER BY ABS((f.consumption_kwh - s.mean_kwh) / s.std_kwh) DESC, f.timestamp DESC
    """
    rows = session.execute(text(query_sql), params).fetchall()

    anomalies: List[Dict[str, Any]] = []
    for r in rows:
        pid, mid, ts, val, mean_v, std_v, count, z_val = r
        z_float = float(z_val)
        abs_z = abs(z_float)
        anomaly_type = "ENERGY_STATISTICAL_SPIKE" if z_float > 0 else "ENERGY_STATISTICAL_DROP"
        direction = "above" if z_float > 0 else "below"
        sev = _classify_z_severity(z_float)

        explanation = (
            f"Measured hourly consumption of {val:.4f} kWh is {abs_z:.2f} standard deviations "
            f"{direction} the observed-period mean ({mean_v:.4f} kWh, std dev: {std_v:.4f} kWh) "
            f"for meter {mid} at plant {pid}."
        )

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
            "context_flags": {
                "sample_size": count,
                "std_kwh": float(round(std_v, 4)),
                "threshold_z": float(threshold_z),
                "is_spike": z_float > 0,
            },
        })

    return {
        "analysis_type": "statistical_zscore",
        "threshold_z": threshold_z,
        "min_observations": min_observations,
        "total_anomalies_detected": len(anomalies),
        "eligible_groups_count": len(eligible_groups),
        "zero_variance_groups": zero_variance_groups,
        "insufficient_observations_groups": insufficient_obs_groups,
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
) -> Dict[str, Any]:
    """
    Calculate rolling historical baselines and detect dynamic anomalies.

    Strict rules enforced:
    - Uses observations within the preceding timestamp duration, excluding the current hour.
    - The current observation is NEVER included in its own baseline.
    - Explicit window_size (default 24 hours) and min_observations (default 12).
    - Partitioned strictly by (plant_id, meter_id) to avoid comparing unrelated meters or plants.
    - Zero variance and window start-up periods safely guarded.
    """
    if threshold_z <= 0:
        raise ValueError("threshold_z must be positive")
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2")

    params: Dict[str, Any] = {
        "threshold_z": float(threshold_z),
        "min_obs": int(min_observations),
    }

    # CTE base query partitions by plant_id, meter_id
    # Embed only the validated hour count in the interval literal.
    w_size = int(window_size)
    if w_size < 2:
        raise ValueError("window_size must be at least 2")
    if min_observations > w_size:
        raise ValueError("min_observations cannot exceed window_size")

    outer_filters: List[str] = []
    if plant_id:
        outer_filters.append("plant_id = :plant_id")
        params["plant_id"] = plant_id
    if meter_id:
        outer_filters.append("meter_id = :meter_id")
        params["meter_id"] = meter_id
    if start_time:
        outer_filters.append("timestamp >= :start_time")
        params["start_time"] = start_time
    if end_time:
        outer_filters.append("timestamp <= :end_time")
        params["end_time"] = end_time

    outer_where = f"AND {' AND '.join(outer_filters)}" if outer_filters else ""

    rolling_sql = f"""
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
            (consumption_kwh - rolling_mean) / NULLIF(rolling_std, 0) as rolling_z
        FROM rolling
        WHERE window_obs_count >= :min_obs
          AND rolling_std > 0
          AND ABS((consumption_kwh - rolling_mean) / rolling_std) >= :threshold_z
          {outer_where}
        ORDER BY ABS((consumption_kwh - rolling_mean) / rolling_std) DESC, timestamp DESC
    """
    rows = session.execute(text(rolling_sql), params).fetchall()

    anomalies: List[Dict[str, Any]] = []
    for r in rows:
        pid, mid, ts, val, r_mean, r_std, obs_count, r_z = r
        z_float = float(r_z)
        abs_z = abs(z_float)
        anomaly_type = "ROLLING_BASELINE_SPIKE" if z_float > 0 else "ROLLING_BASELINE_DROP"
        direction = "above" if z_float > 0 else "below"
        sev = _classify_z_severity(z_float)

        explanation = (
            f"Observation of {val:.4f} kWh at {ts} is {abs_z:.2f} standard deviations {direction} "
            f"the preceding {w_size}-hour window using {obs_count} available observations "
            f"(mean: {r_mean:.4f} kWh, std dev: {r_std:.4f} kWh) for meter {mid} at plant {pid}."
        )

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
            "context_flags": {
                "window_size_hours": w_size,
                "historical_observations_used": obs_count,
                "current_observation_excluded": True,
                "rolling_std_kwh": float(round(r_std, 4)),
                "threshold_z": float(threshold_z),
            },
        })

    return {
        "analysis_type": "rolling_baseline",
        "window_size_hours": w_size,
        "min_observations": min_observations,
        "threshold_z": threshold_z,
        "total_anomalies_detected": len(anomalies),
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
            consumption_kwh
        FROM fact_energy_meter_hourly
        {where_clause}
        ORDER BY power_factor ASC, timestamp ASC
    """
    rows = session.execute(text(sql), params).fetchall()

    anomalies: List[Dict[str, Any]] = []
    for r in rows:
        ts, pid, mid, pf, kwh = r
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
            },
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
            e.consumption_kwh as process_kwh
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
                "area": area,
                "downtime_min": dt_min,
                "downtime_reason": dt_reason,
                "target_qty": target_q,
                "product_id": prod_id,
                "category": "STANDBY_POWER",
                "avoidable_waste_claimed": False,
                "note": "Energy during a zero-output interval; no expected-energy baseline is available, and it is not classified as avoidable waste.",
            },
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
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    z_threshold: float = 3.0,
    rolling_window_hours: int = 24,
    pf_threshold: Decimal = DEFAULT_POWER_FACTOR_THRESHOLD,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the unified deterministic anomaly suite across energy and production data.
    """
    stat_anomalies = detect_energy_statistical_anomalies(
        session=session,
        plant_id=plant_id,
        start_time=start_time,
        end_time=end_time,
        threshold_z=z_threshold,
        limit=limit,
    )
    rolling_anomalies = detect_rolling_baseline_anomalies(
        session=session,
        plant_id=plant_id,
        start_time=start_time,
        end_time=end_time,
        window_size=rolling_window_hours,
        threshold_z=z_threshold,
        limit=limit,
    )
    pf_anomalies = detect_low_power_factor_anomalies(
        session=session,
        plant_id=plant_id,
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
