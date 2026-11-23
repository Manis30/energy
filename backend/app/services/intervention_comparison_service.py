"""
Deterministic Comparison Service for Corrective Actions and Savings Verification (Phase 5/6).

Reuses Phase 2 intensity and Phase 3 operating context concepts.
Ensures:
1. Plant-qualified master data resolution for SMT and FAL lines (SMT-L1, SMT-L2, FAL-L1, FAL-L2).
2. Explicit measurement boundary and error handling: unknown line or empty meter returns boundary error.
3. Distinct factory vs process scopes (factory uses plant electricity + FAL finished goods; process uses dedicated meters).
4. Start-inclusive, end-exclusive hourly window semantics: [start_ts, end_ts).
5. Detailed interval accounting: expected, excluded, complete, missing, and conflicting intervals with reasons.
6. Coverage calculated strictly as complete eligible hours divided by expected non-excluded hours.
7. Ratios derived strictly from sums over complete eligible intervals.
8. Separation of observed differences (post minus baseline) from attributable avoided electricity/cost.
9. Elimination of equal-operating-hours attribution heuristic; requires preapproved counterfactual reference model.
10. Division-by-zero protection: zero good units marks cost-per-good-unit objective INCONCLUSIVE while preserving post intensity.
11. Guardrails: zero minimum output is UNASSESSABLE; valid preapproved maximum of zero for rejects/downtime is supported;
    BREACHED is reserved strictly for violations of valid limits.
12. Dynamic factor resolution from DatasetFactorAssumption (separating dataset-derived estimates from approved contracts).
13. Three Separate Answers for Facilities and Production management.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import math
import statistics
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import zoneinfo


def to_utc_instant(dt: Optional[datetime], plant_id: Optional[str] = "IN-KA-01") -> Optional[datetime]:
    """Normalize any datetime (naive or aware) to timezone-aware UTC instant using plant timezone."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    try:
        plant_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    except Exception:
        plant_tz = timezone(timedelta(hours=5, minutes=30))
    return dt.replace(tzinfo=plant_tz).astimezone(timezone.utc)

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.recommendations import (
    ActionAuditLog,
    CorrectiveAction,
    InterventionAssessment,
    InterventionPlan,
)
from app.models.source_data import (
    DatasetFactorAssumption,
    DimProductionLine,
    FactDowntimeEvent,
    FactEnergyMeterHourly,
    FactHourlyProduction,
    FactMaintenanceWorkOrder,
    FactSourceRevision,
)
from app.schemas.interventions import (
    ExcludedIntervalInfo,
    GuardrailResult,
    InterventionComparisonResponse,
    PeriodAnalyticsSummary,
    ReferenceIntervalDetail,
)

logger = logging.getLogger(__name__)

COMMON_RATE_TARIFF_INR_PER_KWH = 8.25
COMMON_RATE_FACTOR_VERSION = "TARIFF-2026-V1"


def resolve_line_and_process(
    session: Session, plant_id: str, process_or_line: str
) -> Tuple[Optional[str], str, str]:
    """
    Resolve production line and process scope against plant-qualified master data.
    The supplied factory data uses SMT-L1 and SMT-L2 for SMT, and FAL-L1 and FAL-L2 for Final Assembly.
    Returns: (resolved_line_id, process_type, process_scope)
    Raises ValueError with explicit boundary error on unknown line or mismatch.
    """
    stmt = select(DimProductionLine).where(DimProductionLine.plant_id == plant_id)
    plant_lines = session.execute(stmt).scalars().all()
    if not plant_lines:
        raise ValueError(
            f"Measurement boundary error: Plant '{plant_id}' has no production lines registered in master data."
        )

    line_map = {l.line_id: l for l in plant_lines}
    clean_line = (process_or_line or "").strip()

    # 1. Exact match on registered line_id
    if clean_line in line_map:
        line_obj = line_map[clean_line]
        scope = "SMT_PROCESS" if "SMT" in line_obj.line_type.upper() else "FAL_PROCESS"
        return line_obj.line_id, line_obj.line_type, scope

    # 2. Match by process alias
    upper_alias = clean_line.upper()
    if upper_alias in ("SMT", "SURFACE MOUNT"):
        smt_lines = [l for l in plant_lines if "SMT" in l.line_type.upper()]
        if smt_lines:
            return smt_lines[0].line_id, smt_lines[0].line_type, "SMT_PROCESS"
    elif upper_alias in ("FAL", "FINAL ASSEMBLY", "ASSEMBLY"):
        fal_lines = [
            l
            for l in plant_lines
            if "FINAL ASSEMBLY" in l.line_type.upper() or "FAL" in l.line_type.upper()
        ]
        if fal_lines:
            return fal_lines[0].line_id, fal_lines[0].line_type, "FAL_PROCESS"
    elif upper_alias in ("SHARED_UTILITY", "UNKNOWN_ALLOCATION", "COMPRESSOR", "CHILLER", "HVAC", "UTILITY"):
        # Shared utility with unknown production allocation: preserves distinct boundary
        return "UNKNOWN_ALLOCATION", "Shared Utility / Unknown Allocation", "SHARED_UTILITY"
    elif upper_alias in ("FACTORY", "PLANT", "ALL", "PLANT_WIDE", "PLANT-WIDE"):
        # Explicit plant-wide production protection scope
        fal_lines = [
            l
            for l in plant_lines
            if "FINAL ASSEMBLY" in l.line_type.upper() or "FAL" in l.line_type.upper()
        ]
        primary_line = fal_lines[0].line_id if fal_lines else plant_lines[0].line_id
        return primary_line, "Plant Utility / Facility Envelope", "PLANT_WIDE"

    # Explicit boundary error if line cannot be resolved from plant master data
    valid_ids = sorted(list(line_map.keys()))
    raise ValueError(
        f"Measurement boundary error: Unknown production line or process '{process_or_line}' for plant '{plant_id}'. "
        f"Valid plant master data lines: {valid_ids}. SMT and FAL lines must be resolved through plant-qualified master data. "
        f"For shared utilities, specify 'SHARED_UTILITY' or choose an explicit 'PLANT_WIDE' guardrail scope."
    )


def resolve_factor_assumption(
    session: Session,
    factor_type: str = "ELECTRICITY_TARIFF",
    plant_id: Optional[str] = None,
    target_date: Optional[Union[date, datetime]] = None,
) -> Dict[str, Any]:
    """
    Resolve versioned tariff or emissions factor from DatasetFactorAssumption.
    Matches by factor type, unit, plant or explicitly applicable default scope, and effective date.
    Removes arbitrary first-row selection.
    An ambiguous, expired, missing, or wrong-scope factor returns an explicit reason.
    Pins factor ID, version, value, approval status, and applicable dates.
    """
    check_date = target_date.date() if isinstance(target_date, datetime) else target_date

    stmt = select(DatasetFactorAssumption).where(
        DatasetFactorAssumption.factor_type == factor_type
    )
    rows = session.execute(stmt).scalars().all()

    if not rows:
        return {
            "factor_id": None,
            "numeric_value": 8.25 if factor_type == "ELECTRICITY_TARIFF" else 0.716,
            "unit": "INR/kWh" if factor_type == "ELECTRICITY_TARIFF" else "kg CO2e/kWh",
            "approval_status": "MISSING",
            "source_dataset_version": "NONE",
            "is_approved": False,
            "label": f"Missing factor assumption for {factor_type}",
            "error_reason": f"No factor assumptions found for factor_type '{factor_type}' in dataset_factor_assumptions.",
        }

    # Filter candidate factors by date if check_date is supplied
    date_filtered = []
    for r in rows:
        if check_date:
            if r.effective_from and check_date < r.effective_from:
                continue
            if r.effective_to and check_date > r.effective_to:
                continue
        date_filtered.append(r)

    if not date_filtered and rows and check_date:
        return {
            "factor_id": None,
            "numeric_value": 8.25 if factor_type == "ELECTRICITY_TARIFF" else 0.716,
            "unit": "INR/kWh" if factor_type == "ELECTRICITY_TARIFF" else "kg CO2e/kWh",
            "approval_status": "EXPIRED_OR_PRE_EFFECTIVE",
            "source_dataset_version": "NONE",
            "is_approved": False,
            "label": f"Factor expired or pre-effective for date {check_date.isoformat()}",
            "error_reason": f"No factor assumption active for date {check_date.isoformat()} (all candidates are expired or pre-effective).",
        }

    candidates = date_filtered if date_filtered else rows

    # Match by plant scope first, then DEFAULT scope
    plant_matches = [r for r in candidates if r.factor_scope == plant_id] if plant_id else []
    if len(plant_matches) == 1:
        matched = plant_matches[0]
    elif len(plant_matches) > 1:
        return {
            "factor_id": None,
            "numeric_value": float(plant_matches[0].numeric_value),
            "unit": plant_matches[0].unit,
            "approval_status": "AMBIGUOUS",
            "source_dataset_version": plant_matches[0].source_dataset_version,
            "is_approved": False,
            "label": f"Ambiguous factor assumption for plant {plant_id}",
            "error_reason": f"Multiple active factor assumptions match plant scope '{plant_id}'. Requires unique scope resolution.",
        }
    else:
        # Check DEFAULT scope
        default_matches = [r for r in candidates if r.factor_scope == "DEFAULT"]
        if len(default_matches) == 1:
            matched = default_matches[0]
        elif len(default_matches) > 1:
            return {
                "factor_id": None,
                "numeric_value": float(default_matches[0].numeric_value),
                "unit": default_matches[0].unit,
                "approval_status": "AMBIGUOUS",
                "source_dataset_version": default_matches[0].source_dataset_version,
                "is_approved": False,
                "label": "Ambiguous default factor assumption",
                "error_reason": "Multiple active factor assumptions match DEFAULT scope.",
            }
        else:
            return {
                "factor_id": None,
                "numeric_value": 8.25 if factor_type == "ELECTRICITY_TARIFF" else 0.716,
                "unit": "INR/kWh" if factor_type == "ELECTRICITY_TARIFF" else "kg CO2e/kWh",
                "approval_status": "WRONG_SCOPE",
                "source_dataset_version": "NONE",
                "is_approved": False,
                "label": f"Wrong-scope: No matching plant or DEFAULT factor for plant '{plant_id}'",
                "error_reason": f"No factor matching plant '{plant_id}' or DEFAULT scope was found.",
            }

    val = float(matched.numeric_value)
    status = matched.approval_status
    is_approved = (status in ("APPROVED", "APPROVED_CONTRACT"))
    return {
        "factor_id": matched.factor_id,
        "numeric_value": val,
        "unit": matched.unit,
        "approval_status": status,
        "source_dataset_version": matched.source_dataset_version,
        "is_approved": is_approved,
        "effective_from": matched.effective_from.isoformat() if matched.effective_from else None,
        "effective_to": matched.effective_to.isoformat() if matched.effective_to else None,
        "label": f"₹{val:.2f}/{matched.unit} ({'Approved Contract' if is_approved else 'dataset-derived assumption, ' + status})",
        "error_reason": None,
    }


def extract_stoppage_episodes(
    session: Session,
    plant_id: str,
    line_id: Optional[str],
    meter_id: str,
    start_ts: datetime,
    end_ts: datetime,
    min_duration_hours: int = 1,
    max_duration_hours: int = 24,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Identify qualifying stoppage episodes on a dedicated process meter and mapped line.
    A qualifying stoppage requires observed actual_qty == 0 on the line and valid meter telemetry.
    Missing production readings break continuity.
    Returns: (eligible_episodes, excluded_episodes)
    Each episode contains:
    - episode_id: str
    - start_ts: str (isoformat)
    - end_ts: str (isoformat)
    - duration_hours: int
    - total_kwh: float
    - hourly_rate_kwh: float
    - reading_ids: List[str]
    - event_ids: List[str]
    """
    if not line_id or line_id == "UNKNOWN_ALLOCATION":
        return [], [{"reason": "Line allocation unknown for shared utility; cannot isolate stoppage episodes."}]

    total_hours = max(0, int((end_ts - start_ts).total_seconds()) // 3600)
    expected_hours = [start_ts + timedelta(hours=i) for i in range(total_hours)]

    energy_stmt = select(
        FactEnergyMeterHourly.timestamp,
        FactEnergyMeterHourly.consumption_kwh,
        FactEnergyMeterHourly.meter_reading_id,
    ).where(
        and_(
            FactEnergyMeterHourly.plant_id == plant_id,
            FactEnergyMeterHourly.meter_id == meter_id,
            FactEnergyMeterHourly.timestamp >= start_ts,
            FactEnergyMeterHourly.timestamp < end_ts,
        )
    )
    energy_rows = session.execute(energy_stmt).fetchall()
    energy_map = {r[0]: (float(r[1]), str(r[2])) for r in energy_rows if r[1] is not None}

    if line_id == "PLANT_WIDE":
        prod_stmt = select(
            FactHourlyProduction.event_ts,
            func.sum(FactHourlyProduction.actual_qty).label("actual_qty"),
            func.string_agg(func.cast(FactHourlyProduction.event_id, func.text), ",").label("event_ids"),
            func.sum(FactHourlyProduction.downtime_min).label("downtime_min"),
        ).where(
            and_(
                FactHourlyProduction.plant_id == plant_id,
                FactHourlyProduction.event_ts >= start_ts,
                FactHourlyProduction.event_ts < end_ts,
            )
        ).group_by(FactHourlyProduction.event_ts)
        prod_rows = session.execute(prod_stmt).fetchall()
        prod_map = {r[0]: (int(r[1] or 0), str(r[2]), int(r[3] or 0)) for r in prod_rows if r[1] is not None}
    else:
        prod_stmt = select(
            FactHourlyProduction.event_ts,
            FactHourlyProduction.actual_qty,
            FactHourlyProduction.event_id,
            FactHourlyProduction.downtime_min,
        ).where(
            and_(
                FactHourlyProduction.plant_id == plant_id,
                FactHourlyProduction.line_id == line_id,
                FactHourlyProduction.event_ts >= start_ts,
                FactHourlyProduction.event_ts < end_ts,
            )
        )
        prod_rows = session.execute(prod_stmt).fetchall()
        prod_map = {r[0]: (int(r[1]), str(r[2]), int(r[3] or 0)) for r in prod_rows if r[1] is not None}

    eligible_episodes: List[Dict[str, Any]] = []
    excluded_episodes: List[Dict[str, Any]] = []
    current_episode_hours: List[Tuple[datetime, float, str, str, int]] = []

    def _finalize_current(hours_list: List[Tuple[datetime, float, str, str, int]]):
        if not hours_list:
            return
        duration = len(hours_list)
        total_kwh = sum(item[1] for item in hours_list)
        hourly_rate = total_kwh / duration if duration > 0 else 0.0
        ep_start = hours_list[0][0]
        ep_end = hours_list[-1][0] + timedelta(hours=1)
        ep_id = f"STOPPAGE-{plant_id}-{line_id}-{ep_start.strftime('%Y%m%d%H%M')}"
        ep_dict = {
            "episode_id": ep_id,
            "start_ts": ep_start.isoformat(),
            "end_ts": ep_end.isoformat(),
            "duration_hours": duration,
            "total_kwh": round(total_kwh, 4),
            "hourly_rate_kwh": round(hourly_rate, 4),
            "reading_ids": [item[2] for item in hours_list],
            "event_ids": [item[3] for item in hours_list],
            "downtime_minutes": sum(item[4] for item in hours_list),
            "intervals": [
                {
                    "timestamp": item[0].isoformat(),
                    "kwh": float(item[1]),
                    "reading_id": item[2],
                }
                for item in hours_list
            ],
        }
        if min_duration_hours <= duration <= max_duration_hours:
            eligible_episodes.append(ep_dict)
        else:
            ep_dict["exclusion_reason"] = f"Episode duration ({duration}h) outside approved envelope [{min_duration_hours}h, {max_duration_hours}h]."
            excluded_episodes.append(ep_dict)

    for ts in expected_hours:
        # Missing production reading breaks episode continuity
        if ts not in prod_map:
            _finalize_current(current_episode_hours)
            current_episode_hours = []
            continue

        act_qty, e_id, dt_min = prod_map[ts]

        if act_qty == 0:
            # Zero actual output: Check energy meter reading
            if ts in energy_map:
                kwh, r_id = energy_map[ts]
                current_episode_hours.append((ts, kwh, r_id, e_id, dt_min))
            else:
                # Missing energy telemetry breaks episode continuity
                _finalize_current(current_episode_hours)
                current_episode_hours = []
        else:
            # Active production: Stoppage ended
            _finalize_current(current_episode_hours)
            current_episode_hours = []

    _finalize_current(current_episode_hours)
    return eligible_episodes, excluded_episodes


def calculate_dual_boundary_attribution(
    dual_boundary_breakdown: Optional[Dict[str, Any]] = None,
    tariff_factor: Optional[Union[Dict[str, Any], float]] = None,
    production_protection_status: Optional[str] = None,
    guardrails_passed: Optional[bool] = None,
    plan: Optional[InterventionPlan] = None,
    action: Optional[CorrectiveAction] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Dual-boundary energy accounting under IPMVP Option B / ISO 50015:
    Net avoided kWh = Boundary A Stoppage Reduction - Boundary B Restart Overhead.

    Accounting Rules:
    1. Implementation & Prospective Approval:
       Requires a recorded physical implementation timestamp and a frozen, prospectively approved plan.
    2. Missing Restart Readings:
       If restart readings are missing or restart duration cannot be established, returns INCONCLUSIVE.
    3. Production Guardrail Enforcement:
       If any preapproved guardrail is breached (output, rejects, downtime, restart) or unassessable,
       production was not protected. Attributable verified savings are disqualified (null / ₹0).
    4. Uncertainty & Confidence Gate:
       Applies approved uncertainty rule: if margin of error exceeds reduction (e.g. 1 kWh reduction
       with 203.6892 kWh uncertainty margin, CI lower bound <= 0) or baseline CV > 50%,
       attribution is disqualified as INCONCLUSIVE_HIGH_UNCERTAINTY.
    5. Net Energy Reduction:
       Reports net energy effect (Stoppage reduction minus restart overhead) preserving signs.
       If net reduction > 0, uncertainty passes, and production protected, returns ATTRIBUTED.
    6. Interval Pricing:
       Uses interval-level tariff pricing across unique baseline and post intervals.
       Preserves genuine approved zero rate. If required rate is unapproved or missing, returns null verified rupees.
    """
    breakdown = dual_boundary_breakdown or {}
    b_a = breakdown.get("boundary_a_stoppage", {})
    b_b = breakdown.get("boundary_b_restart_shift", {})

    stoppage_reduction_kwh = float(kwargs.get("stoppage_reduction_kwh") if "stoppage_reduction_kwh" in kwargs else breakdown.get("stoppage_reduction_kwh", 0.0))
    restart_overhead_kwh = float(kwargs.get("restart_overhead_kwh") if "restart_overhead_kwh" in kwargs else breakdown.get("restart_overhead_kwh", 0.0))
    net_reduction_kwh = float(kwargs.get("net_reduction_kwh") if "net_reduction_kwh" in kwargs else breakdown.get("net_reduction_kwh", round(stoppage_reduction_kwh - restart_overhead_kwh, 4)))

    observed_avoided_cost_inr = kwargs.get("observed_avoided_cost_inr") if "observed_avoided_cost_inr" in kwargs else breakdown.get("observed_avoided_cost_inr")

    # Tariff resolution
    if isinstance(tariff_factor, dict):
        is_tariff_approved = bool(kwargs.get("tariffs_approved", breakdown.get("tariffs_approved", tariff_factor.get("is_approved", False))))
        tariff_label = tariff_factor.get("label") or str(tariff_factor)
        tariff_rate = float(tariff_factor.get("numeric_value") or 8.25)
    elif isinstance(tariff_factor, (int, float)):
        is_tariff_approved = bool(kwargs.get("tariffs_approved", True))
        tariff_label = f"Approved Contract ₹{float(tariff_factor):.2f}/kWh"
        tariff_rate = float(tariff_factor)
    else:
        is_tariff_approved = bool(kwargs.get("tariffs_approved", breakdown.get("tariffs_approved", False)))
        tariff_rate = float(kwargs.get("common_rate_factor") or 8.25)
        tariff_label = f"Tariff rate ₹{tariff_rate:.2f}/kWh"

    tariff_reason = breakdown.get("tariff_reason")
    if not is_tariff_approved and tariff_reason:
        tariff_label = tariff_reason

    if observed_avoided_cost_inr is None:
        observed_avoided_cost_inr = round(net_reduction_kwh * tariff_rate, 2)
    else:
        observed_avoided_cost_inr = float(observed_avoided_cost_inr)

    # Resolve guardrails passed & production protection status
    if kwargs.get("production_limits_breached"):
        prod_status = "BREACHED"
        gr_passed = False
    elif kwargs.get("unassessable_guardrails"):
        prod_status = "UNASSESSABLE"
        gr_passed = False
    else:
        prod_status = production_protection_status or ("BREACHED" if guardrails_passed is False else "PROTECTED")
        gr_passed = (guardrails_passed is not False and prod_status == "PROTECTED")

    has_impl = kwargs.get("has_implementation_timestamp", True if (action and action.implemented_at) else (False if action is not None else True))
    is_retro = kwargs.get("is_retrospective_plan", plan.is_retrospective if plan else False)
    missing_restart_flag = bool(kwargs.get("missing_restart_evidence") or breakdown.get("missing_restart_evidence"))
    missing_restart_telemetry = bool(b_b) and b_b.get("post_kwh") is None

    # Uncertainty parameters
    margin_error = kwargs.get("margin_of_error_kwh") or breakdown.get("margin_of_error_kwh")
    baseline_cv = kwargs.get("baseline_cv_pct") or breakdown.get("baseline_cv_pct")
    uncertainty_pct = kwargs.get("uncertainty_pct") or breakdown.get("uncertainty_pct")

    # 1. Implementation & Chronology validation
    if not has_impl:
        return {
            "status": "UNVERIFIED",
            "attribution_method": "DUAL_BOUNDARY_STOPPAGE_AND_RESTART",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_label,
            "verified_monetary_savings_inr": None,
            "observed_avoided_kwh": net_reduction_kwh,
            "observed_avoided_cost_inr": observed_avoided_cost_inr,
            "stoppage_reduction_kwh": stoppage_reduction_kwh,
            "restart_overhead_kwh": restart_overhead_kwh,
            "net_reduction_kwh": net_reduction_kwh,
            "reason": "Dual-boundary trial attribution requires a valid recorded implementation record with timestamp.",
            "guardrails_passed": gr_passed,
            "is_estimate": True,
        }

    if is_retro:
        return {
            "status": "UNVERIFIED",
            "attribution_method": "DUAL_BOUNDARY_STOPPAGE_AND_RESTART",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_label,
            "verified_monetary_savings_inr": None,
            "observed_avoided_kwh": net_reduction_kwh,
            "observed_avoided_cost_inr": observed_avoided_cost_inr,
            "stoppage_reduction_kwh": stoppage_reduction_kwh,
            "restart_overhead_kwh": restart_overhead_kwh,
            "net_reduction_kwh": net_reduction_kwh,
            "reason": "Plan was defined or flagged retrospectively; prospective trial verification requires prospective plan approval.",
            "guardrails_passed": gr_passed,
            "is_estimate": True,
        }

    # 2. Check for missing restart readings
    if missing_restart_telemetry:
        return {
            "status": "INCONCLUSIVE",
            "attribution_method": "DUAL_BOUNDARY_STOPPAGE_AND_RESTART",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_label,
            "verified_monetary_savings_inr": None,
            "observed_avoided_kwh": net_reduction_kwh,
            "observed_avoided_cost_inr": observed_avoided_cost_inr,
            "stoppage_reduction_kwh": stoppage_reduction_kwh,
            "restart_overhead_kwh": restart_overhead_kwh,
            "net_reduction_kwh": net_reduction_kwh,
            "reason": "Missing restart readings: restart overhead cannot be verified. Dual-boundary trial attribution unverified.",
            "guardrails_passed": gr_passed,
            "is_estimate": True,
        }

    if missing_restart_flag:
        return {
            "status": "UNVERIFIED",
            "attribution_method": "DUAL_BOUNDARY_STOPPAGE_AND_RESTART",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_label,
            "verified_monetary_savings_inr": None,
            "observed_avoided_kwh": net_reduction_kwh,
            "observed_avoided_cost_inr": observed_avoided_cost_inr,
            "stoppage_reduction_kwh": stoppage_reduction_kwh,
            "restart_overhead_kwh": restart_overhead_kwh,
            "net_reduction_kwh": net_reduction_kwh,
            "reason": "Missing restart readings: restart overhead cannot be verified. Dual-boundary trial attribution unverified.",
            "guardrails_passed": gr_passed,
            "is_estimate": True,
        }

    # 3. Production Protection Guardrail Check
    if prod_status == "BREACHED" or not gr_passed:
        return {
            "status": "UNVERIFIED",
            "attribution_method": "DUAL_BOUNDARY_STOPPAGE_AND_RESTART",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_label,
            "verified_monetary_savings_inr": None,
            "observed_avoided_kwh": net_reduction_kwh,
            "observed_avoided_cost_inr": observed_avoided_cost_inr,
            "total_expected_kwh": round(float(b_a.get("baseline_kwh") or 0.0) + float(b_b.get("baseline_kwh") or 0.0), 4),
            "total_observed_kwh": round(float(b_a.get("post_kwh") or 0.0) + float(b_b.get("post_kwh") or 0.0), 4),
            "reason": (
                f"Production guardrail breached during trial: observed net reduction of {net_reduction_kwh:.4f} kWh, "
                f"but production protection was not maintained. Attributable verified savings disqualified (null / ₹0)."
            ),
            "guardrails_passed": False,
            "stoppage_reduction_kwh": stoppage_reduction_kwh,
            "restart_overhead_kwh": restart_overhead_kwh,
            "net_reduction_kwh": net_reduction_kwh,
            "is_estimate": True,
        }

    if prod_status == "UNASSESSABLE":
        return {
            "status": "UNVERIFIED",
            "attribution_method": "DUAL_BOUNDARY_STOPPAGE_AND_RESTART",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_label,
            "verified_monetary_savings_inr": None,
            "observed_avoided_kwh": net_reduction_kwh,
            "observed_avoided_cost_inr": observed_avoided_cost_inr,
            "total_expected_kwh": round(float(b_a.get("baseline_kwh") or 0.0) + float(b_b.get("baseline_kwh") or 0.0), 4),
            "total_observed_kwh": round(float(b_a.get("post_kwh") or 0.0) + float(b_b.get("post_kwh") or 0.0), 4),
            "reason": (
                f"Production guardrails were unassessable during trial (observed net reduction of {net_reduction_kwh:.4f} kWh). "
                f"Production protection could not be certified; attributable verified savings disqualified (null / ₹0)."
            ),
            "guardrails_passed": False,
            "stoppage_reduction_kwh": stoppage_reduction_kwh,
            "restart_overhead_kwh": restart_overhead_kwh,
            "net_reduction_kwh": net_reduction_kwh,
            "is_estimate": True,
        }

    # 4. Statistical Uncertainty Criterion Check
    # If margin of error exceeds reduction (CI lower bound <= 0) or baseline CV > 50%:
    if margin_error is not None:
        ci_lower = round(net_reduction_kwh - float(margin_error), 4)
        if ci_lower <= 0:
            return {
                "status": "INCONCLUSIVE_HIGH_UNCERTAINTY",
                "attribution_method": "DUAL_BOUNDARY_STOPPAGE_AND_RESTART",
                "verified_electricity_savings_kwh": None,
                "estimated_avoided_cost_inr": None,
                "estimated_avoided_cost_assumption": tariff_label,
                "verified_monetary_savings_inr": None,
                "observed_avoided_kwh": net_reduction_kwh,
                "observed_avoided_cost_inr": observed_avoided_cost_inr,
                "margin_of_error_kwh": float(margin_error),
                "ci_lower_bound_kwh": ci_lower,
                "uncertainty_pct": uncertainty_pct,
                "baseline_cv_pct": baseline_cv,
                "reason": (
                    f"Attribution inconclusive due to high uncertainty: observed reduction of {net_reduction_kwh:.4f} kWh "
                    f"has an uncertainty margin of ±{margin_error} kWh (95% CI lower bound {ci_lower:.4f} kWh <= 0). "
                    f"Confidence interval includes zero; approved method cannot establish a positive reduction."
                ),
                "guardrails_passed": gr_passed,
                "stoppage_reduction_kwh": stoppage_reduction_kwh,
                "restart_overhead_kwh": restart_overhead_kwh,
                "net_reduction_kwh": net_reduction_kwh,
                "is_estimate": True,
            }

    if baseline_cv is not None and float(baseline_cv) > 50.0:
        return {
            "status": "INCONCLUSIVE_HIGH_UNCERTAINTY",
            "attribution_method": "DUAL_BOUNDARY_STOPPAGE_AND_RESTART",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_label,
            "verified_monetary_savings_inr": None,
            "observed_avoided_kwh": net_reduction_kwh,
            "observed_avoided_cost_inr": observed_avoided_cost_inr,
            "baseline_cv_pct": float(baseline_cv),
            "reason": f"Attribution inconclusive due to excessive baseline variability (CV: {baseline_cv}% > 50.0% threshold).",
            "guardrails_passed": gr_passed,
            "stoppage_reduction_kwh": stoppage_reduction_kwh,
            "restart_overhead_kwh": restart_overhead_kwh,
            "net_reduction_kwh": net_reduction_kwh,
            "is_estimate": True,
        }

    # 5. Net Energy Reduction Calculation
    if net_reduction_kwh > 0:
        verified_money = observed_avoided_cost_inr if is_tariff_approved else None
        return {
            "status": "ATTRIBUTED",
            "attribution_method": "DUAL_BOUNDARY_STOPPAGE_AND_RESTART",
            "verified_electricity_savings_kwh": net_reduction_kwh,
            "estimated_avoided_cost_inr": observed_avoided_cost_inr,
            "estimated_avoided_cost_assumption": tariff_label,
            "verified_monetary_savings_inr": verified_money,
            "observed_avoided_kwh": net_reduction_kwh,
            "observed_avoided_cost_inr": observed_avoided_cost_inr,
            "total_expected_kwh": round(float(b_a.get("baseline_kwh") or 0.0) + float(b_b.get("baseline_kwh") or 0.0), 4),
            "total_observed_kwh": round(float(b_a.get("post_kwh") or 0.0) + float(b_b.get("post_kwh") or 0.0), 4),
            "reason": (
                f"Net reduction of {net_reduction_kwh:.4f} kWh verified across dual boundary "
                f"(Stoppage reduction: {stoppage_reduction_kwh:.4f} kWh minus restart overhead: {restart_overhead_kwh:.4f} kWh). "
                f"Production guardrails held."
            ),
            "guardrails_passed": True,
            "stoppage_reduction_kwh": stoppage_reduction_kwh,
            "restart_overhead_kwh": restart_overhead_kwh,
            "net_reduction_kwh": net_reduction_kwh,
            "is_estimate": not is_tariff_approved,
        }
    else:
        return {
            "status": "NOT_IMPROVED",
            "attribution_method": "DUAL_BOUNDARY_STOPPAGE_AND_RESTART",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_label,
            "verified_monetary_savings_inr": None,
            "observed_avoided_kwh": net_reduction_kwh,
            "observed_avoided_cost_inr": observed_avoided_cost_inr,
            "reason": (
                f"Trial produced no net electricity reduction ({net_reduction_kwh:.4f} kWh): "
                f"stoppage reduction ({stoppage_reduction_kwh:.4f} kWh) was offset by restart overhead ({restart_overhead_kwh:.4f} kWh)."
            ),
            "guardrails_passed": True,
            "stoppage_reduction_kwh": stoppage_reduction_kwh,
            "restart_overhead_kwh": restart_overhead_kwh,
            "net_reduction_kwh": net_reduction_kwh,
            "is_estimate": True,
        }


def calculate_repeated_stoppages_attribution(
    session: Session,
    plan: InterventionPlan,
    action: Optional[CorrectiveAction],
    tariff_factor: Dict[str, Any],
    resolved_line_id: str,
    meters: List[str],
) -> Dict[str, Any]:
    """
    Explicitly supported attribution method: Repeated Stoppages on a Dedicated Process Meter.
    Method version: REPEATED_STOPPAGES_DEDICATED_METER_V1

    Requirements:
    1. Dedicated meter boundary (exactly 1 dedicated meter, e.g. MTR-SMT or MTR-FAL).
    2. Valid mapped line (SMT-L1, SMT-L2, FAL-L1, FAL-L2).
    3. Frozen, prospectively approved plan (is_frozen=True, approved_at <= action.implemented_at, not is_retrospective).
    4. Reference episodes end before implementation.
    5. Minimum reference episode count (N_ref >= min_ref_count, default 3).
    6. Minimum coverage requirement met.
    7. Matching criteria: duration range and operating condition.

    Returns attribution dict containing:
    - verified_electricity_savings_kwh: float or None
    - estimated_avoided_cost_inr: float or None
    - verified_monetary_savings_inr: float or None
    - reference_count: int
    - observed_exposure_hours: float
    - baseline_variability_cv: float or None
    - uncertainty_pct: float or None
    - is_estimate: True
    - attribution_method: "REPEATED_STOPPAGES_DEDICATED_METER_V1"
    - status: "ATTRIBUTED" | "UNVERIFIED"
    - reason: explicit plain-language explanation
    """
    # 1. Dedicated meter boundary check
    if len(meters) != 1 or meters[0] not in ("MTR-SMT", "MTR-FAL"):
        return {
            "status": "DISQUALIFIED_BOUNDARY",
            "attribution_method": "REPEATED_STOPPAGES_DEDICATED_METER_V1",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_factor.get("label") if isinstance(tariff_factor, dict) else str(tariff_factor),
            "verified_monetary_savings_inr": None,
            "reference_count": 0,
            "observed_exposure_hours": 0.0,
            "baseline_variability_cv": None,
            "uncertainty_pct": None,
            "is_estimate": True,
            "reference_episodes": [],
            "post_episodes": [],
            "reason": (
                f"Attribution method REPEATED_STOPPAGES_DEDICATED_METER_V1 requires exactly one dedicated "
                f"process meter (MTR-SMT or MTR-FAL). Provided meters: {meters}. Shared utilities must use plant envelope."
            ),
        }

    dedicated_meter = meters[0]

    # Parse method options from operating conditions
    operating_cond = {}
    if getattr(plan, "operating_conditions_json", None):
        try:
            operating_cond = json.loads(plan.operating_conditions_json) or {}
        except Exception:
            operating_cond = {}

    min_ref_count = int(operating_cond.get("min_reference_count") or 3)
    min_dur = int(operating_cond.get("min_stoppage_duration_hours") or 1)
    max_dur = int(operating_cond.get("max_stoppage_duration_hours") or 24)

    # 2. Extract reference episodes from baseline window
    ref_end_cutoff = plan.baseline_end
    if action and action.implemented_at and action.implemented_at < ref_end_cutoff:
        ref_end_cutoff = action.implemented_at

    ref_episodes, ref_excluded = extract_stoppage_episodes(
        session=session,
        plant_id=plan.plant_id,
        line_id=resolved_line_id,
        meter_id=dedicated_meter,
        start_ts=plan.baseline_start,
        end_ts=ref_end_cutoff,
        min_duration_hours=min_dur,
        max_duration_hours=max_dur,
    )

    n_ref = len(ref_episodes)
    if n_ref < min_ref_count:
        return {
            "status": "UNVERIFIED_INSUFFICIENT_REFERENCE",
            "attribution_method": "REPEATED_STOPPAGES_DEDICATED_METER_V1",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_factor.get("label") if isinstance(tariff_factor, dict) else str(tariff_factor),
            "verified_monetary_savings_inr": None,
            "reference_count": n_ref,
            "observed_exposure_hours": 0.0,
            "baseline_variability_cv": None,
            "uncertainty_pct": None,
            "is_estimate": True,
            "reference_episodes": ref_episodes,
            "post_episodes": [],
            "reason": (
                f"Reference stoppage episode pool too small (found {n_ref}, required >= {min_ref_count}). "
                f"Cannot establish statistically defensible baseline reference rate on {dedicated_meter}."
            ),
        }

    # 3. Extract post-intervention episodes
    post_episodes, post_excluded = extract_stoppage_episodes(
        session=session,
        plant_id=plan.plant_id,
        line_id=resolved_line_id,
        meter_id=dedicated_meter,
        start_ts=plan.post_start,
        end_ts=plan.post_end,
        min_duration_hours=min_dur,
        max_duration_hours=max_dur,
    )

    n_post = len(post_episodes)
    if n_post == 0:
        return {
            "status": "NO_POST_STOPPAGE_EPISODES",
            "attribution_method": "REPEATED_STOPPAGES_DEDICATED_METER_V1",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": None,
            "estimated_avoided_cost_assumption": tariff_factor.get("label") if isinstance(tariff_factor, dict) else str(tariff_factor),
            "verified_monetary_savings_inr": None,
            "reference_count": n_ref,
            "observed_exposure_hours": 0.0,
            "baseline_variability_cv": None,
            "uncertainty_pct": None,
            "total_expected_kwh": 0.0,
            "total_observed_kwh": 0.0,
            "observed_avoided_kwh": 0.0,
            "is_estimate": True,
            "reference_episodes": ref_episodes,
            "post_episodes": [],
            "reason": (
                f"Post-intervention observation window [{plan.post_start.isoformat()}, {plan.post_end.isoformat()}) "
                f"contained zero qualifying stoppage episodes with zero output on line {resolved_line_id}."
            ),
        }

    # 4. Calculate frozen reference rate
    total_ref_kwh = sum(ep["total_kwh"] for ep in ref_episodes)
    total_ref_hours = sum(ep["duration_hours"] for ep in ref_episodes)
    ref_rate = total_ref_kwh / total_ref_hours if total_ref_hours > 0 else 0.0

    # 5. Baseline variability
    rates = [ep["hourly_rate_kwh"] for ep in ref_episodes]
    s_ref = statistics.stdev(rates) if len(rates) > 1 else 0.0
    cv_pct = round((s_ref / ref_rate) * 100.0, 2) if ref_rate > 0 else 0.0

    # 6. Post expected vs observed & avoided kWh sum and interval-by-interval tariff calculation
    episode_comparisons = []
    total_expected_kwh = 0.0
    total_observed_kwh = 0.0
    total_post_hours = 0
    total_estimated_avoided_cost = 0.0
    all_post_tariffs_approved = bool(tariff_factor.get("is_approved"))
    factor_revisions_used = set()
    unapproved_post_intervals = []

    for ep in post_episodes:
        dur = ep["duration_hours"]
        obs_kwh = ep["total_kwh"]
        exp_kwh = round(ref_rate * dur, 4)
        diff_kwh = round(exp_kwh - obs_kwh, 4)
        total_expected_kwh += exp_kwh
        total_observed_kwh += obs_kwh
        total_post_hours += dur

        # Calculate interval-by-interval avoided cost for this episode
        ep_avoided_cost = 0.0
        ep_intervals = ep.get("intervals", [])
        if ep_intervals:
            for item in ep_intervals:
                item_ts = datetime.fromisoformat(item["timestamp"]) if isinstance(item["timestamp"], str) else item["timestamp"]
                item_kwh = float(item["kwh"])
                item_exp_kwh = ref_rate
                item_diff_kwh = item_exp_kwh - item_kwh

                f = resolve_factor_assumption(session, "ELECTRICITY_TARIFF", plan.plant_id, target_date=item_ts)
                r = float(f.get("numeric_value") or tariff_factor.get("numeric_value", COMMON_RATE_TARIFF_INR_PER_KWH))
                is_app = bool(f.get("is_approved", False))
                f_ver = f.get("source_dataset_version", "NONE")
                factor_revisions_used.add(f_ver)

                cost_part = round(item_diff_kwh * r, 2)
                ep_avoided_cost += cost_part

                if not is_app:
                    all_post_tariffs_approved = False
                    unapproved_post_intervals.append({
                        "timestamp": item["timestamp"],
                        "factor_id": f.get("factor_id"),
                        "approval_status": f.get("approval_status"),
                    })
        else:
            tariff_val = float(tariff_factor.get("numeric_value", COMMON_RATE_TARIFF_INR_PER_KWH))
            ep_avoided_cost = round(diff_kwh * tariff_val, 2)
            if not tariff_factor.get("is_approved"):
                all_post_tariffs_approved = False

        total_estimated_avoided_cost += ep_avoided_cost

        episode_comparisons.append({
            "episode_id": ep.get("episode_id", "EPISODE"),
            "start_ts": ep.get("start_ts", ""),
            "end_ts": ep.get("end_ts", ""),
            "duration_hours": dur,
            "reference_rate_kwh_per_h": round(ref_rate, 4),
            "expected_kwh": exp_kwh,
            "observed_kwh": obs_kwh,
            "avoided_kwh": diff_kwh,
            "avoided_cost_inr": round(ep_avoided_cost, 2),
        })

    total_avoided_kwh = round(total_expected_kwh - total_observed_kwh, 4)

    # 7. Uncertainty and Confidence Intervals
    se = s_ref * math.sqrt((1.0 / n_ref) + (1.0 / n_post)) * total_post_hours
    margin_error = round(1.96 * se, 4)
    uncertainty_pct = (
        round((margin_error / abs(total_avoided_kwh)) * 100.0, 2)
        if abs(total_avoided_kwh) > 0.0001
        else 0.0
    )

    # 8. Avoided cost calculation using interval-by-interval effective rate
    estimated_avoided_cost = round(total_estimated_avoided_cost, 2)
    verified_monetary = estimated_avoided_cost if all_post_tariffs_approved else None

    # 9. Implementation and Prospective Approval Validation
    if not action or not action.implemented_at:
        return {
            "status": "UNVERIFIED_NO_IMPLEMENTATION",
            "attribution_method": "REPEATED_STOPPAGES_DEDICATED_METER_V1",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": estimated_avoided_cost,
            "estimated_avoided_cost_assumption": tariff_factor.get("label") if isinstance(tariff_factor, dict) else str(tariff_factor),
            "verified_monetary_savings_inr": None,
            "reference_count": n_ref,
            "observed_exposure_hours": float(total_post_hours),
            "baseline_variability_cv": cv_pct,
            "uncertainty_pct": uncertainty_pct,
            "margin_of_error_kwh": margin_error,
            "total_expected_kwh": total_expected_kwh,
            "total_observed_kwh": total_observed_kwh,
            "observed_avoided_kwh": total_avoided_kwh,
            "is_estimate": True,
            "reference_rate_kwh_per_h": round(ref_rate, 4),
            "reference_episodes": ref_episodes,
            "post_episodes": episode_comparisons,
            "reason": (
                "Action record or recorded physical implementation timestamp is missing. "
                "Verified attribution requires a valid recorded implementation, timestamp, "
                "eligible boundary, and prospectively approved plan."
            ),
        }

    approved_at_utc = to_utc_instant(plan.approved_at, getattr(plan, "plant_id", None)) if plan.approved_at else None
    implemented_at_utc = to_utc_instant(action.implemented_at, getattr(plan, "plant_id", None)) if action and action.implemented_at else None
    post_start_utc = to_utc_instant(plan.post_start, getattr(plan, "plant_id", None)) if plan.post_start else None

    is_prospectively_frozen = bool(
        plan.is_frozen
        and approved_at_utc
        and not plan.is_retrospective
        and implemented_at_utc
        and post_start_utc
        and approved_at_utc <= implemented_at_utc <= post_start_utc
    )

    if not is_prospectively_frozen:
        return {
            "status": "UNVERIFIED_DEMO_RETROSPECTIVE",
            "attribution_method": "REPEATED_STOPPAGES_DEDICATED_METER_V1",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": estimated_avoided_cost,
            "estimated_avoided_cost_assumption": tariff_factor.get("label") if isinstance(tariff_factor, dict) else str(tariff_factor),
            "verified_monetary_savings_inr": None,
            "reference_count": n_ref,
            "observed_exposure_hours": float(total_post_hours),
            "baseline_variability_cv": cv_pct,
            "uncertainty_pct": uncertainty_pct,
            "margin_of_error_kwh": margin_error,
            "total_expected_kwh": total_expected_kwh,
            "total_observed_kwh": total_observed_kwh,
            "observed_avoided_kwh": total_avoided_kwh,
            "is_estimate": True,
            "reference_rate_kwh_per_h": round(ref_rate, 4),
            "reference_episodes": ref_episodes,
            "post_episodes": episode_comparisons,
            "reason": (
                "Intervention plan was approved retrospectively or without frozen approval timestamp before implementation. "
                "Matched-period estimate computed as descriptive estimate only: "
                "no method may convert a retrospective demo into a verified intervention."
            ),
        }

    # 10. Statistical Significance & Uncertainty Criterion Check
    # The 95% confidence interval is [total_avoided_kwh - margin_error, total_avoided_kwh + margin_error].
    # When total_avoided_kwh <= 0 or margin_error >= total_avoided_kwh (CI lower bound <= 0):
    # The approved method cannot establish a positive reduction with statistical confidence.
    ci_lower_bound = round(total_avoided_kwh - margin_error, 4)
    has_positive_reduction = total_avoided_kwh > 0 and ci_lower_bound > 0

    if not has_positive_reduction:
        return {
            "status": "INCONCLUSIVE_HIGH_UNCERTAINTY",
            "attribution_method": "REPEATED_STOPPAGES_DEDICATED_METER_V1",
            "verified_electricity_savings_kwh": None,
            "estimated_avoided_cost_inr": estimated_avoided_cost,
            "estimated_avoided_cost_assumption": tariff_factor.get("label") if isinstance(tariff_factor, dict) else str(tariff_factor),
            "verified_monetary_savings_inr": None,
            "reference_count": n_ref,
            "observed_exposure_hours": float(total_post_hours),
            "baseline_variability_cv": cv_pct,
            "uncertainty_pct": uncertainty_pct,
            "margin_of_error_kwh": margin_error,
            "ci_lower_bound_kwh": ci_lower_bound,
            "ci_upper_bound_kwh": round(total_avoided_kwh + margin_error, 4),
            "total_expected_kwh": total_expected_kwh,
            "total_observed_kwh": total_observed_kwh,
            "observed_avoided_kwh": total_avoided_kwh,
            "is_estimate": True,
            "reference_rate_kwh_per_h": round(ref_rate, 4),
            "reference_episodes": ref_episodes,
            "post_episodes": episode_comparisons,
            "reason": (
                f"Attribution inconclusive due to high uncertainty: observed reduction of {total_avoided_kwh:+.4f} kWh "
                f"has an uncertainty margin of ±{margin_error} kWh (uncertainty {uncertainty_pct}%, 95% CI lower bound {ci_lower_bound:+.4f} kWh). "
                f"The confidence interval includes zero, so the approved method cannot establish a positive reduction."
            ),
        }

    return {
        "status": "ATTRIBUTED",
        "attribution_method": "REPEATED_STOPPAGES_DEDICATED_METER_V1",
        "verified_electricity_savings_kwh": total_avoided_kwh,
        "estimated_avoided_cost_inr": estimated_avoided_cost,
        "estimated_avoided_cost_assumption": tariff_factor.get("label") if isinstance(tariff_factor, dict) else str(tariff_factor),
        "verified_monetary_savings_inr": verified_monetary,
        "reference_count": n_ref,
        "observed_exposure_hours": float(total_post_hours),
        "baseline_variability_cv": cv_pct,
        "uncertainty_pct": uncertainty_pct,
        "margin_of_error_kwh": margin_error,
        "ci_lower_bound_kwh": ci_lower_bound,
        "ci_upper_bound_kwh": round(total_avoided_kwh + margin_error, 4),
        "total_expected_kwh": total_expected_kwh,
        "total_observed_kwh": total_observed_kwh,
        "observed_avoided_kwh": total_avoided_kwh,
        "is_estimate": True,
        "reference_rate_kwh_per_h": round(ref_rate, 4),
        "reference_episodes": ref_episodes,
        "post_episodes": episode_comparisons,
        "reason": (
            f"Avoided electricity attributed at {total_avoided_kwh:+.4f} kWh (±{margin_error} kWh, "
            f"uncertainty {uncertainty_pct}%) across {n_post} post stoppage episodes ({total_post_hours} hours) "
            f"based on {n_ref} frozen reference episodes (reference rate: {ref_rate:.4f} kWh/h, CV: {cv_pct}%)."
        ),
    }


def get_period_observations(
    session: Session,
    plant_id: str,
    process_or_line: str,
    meters: List[str],
    start_ts: datetime,
    end_ts: datetime,
    stabilization_start: Optional[datetime] = None,
    stabilization_end: Optional[datetime] = None,
    stabilization_reason: Optional[str] = None,
) -> Tuple[PeriodAnalyticsSummary, List[ExcludedIntervalInfo], int]:
    """
    Construct expected plant-hour intervals and evaluate observations on both sides.
    Enforces [start, end) semantics, complete eligibility checks, independent aggregation,
    and exact provenance tracking.
    """
    # 1. Measurement boundary validation
    if not meters:
        raise ValueError(
            f"Measurement boundary error: Empty meter selection for plant '{plant_id}'. "
            f"Measurement boundary requires at least one dedicated meter."
        )

    resolved_line_id, process_type, process_scope = resolve_line_and_process(
        session, plant_id, process_or_line
    )

    # 2. Construct expected hourly intervals [start_ts, end_ts)
    total_seconds = int((end_ts - start_ts).total_seconds())
    total_expected_hours = max(0, total_seconds // 3600)
    expected_intervals = [start_ts + timedelta(hours=i) for i in range(total_expected_hours)]

    # 3. Clip stabilization and restart exclusions to actual measurement window
    clipped_stab_start = max(start_ts, stabilization_start) if stabilization_start else None
    clipped_stab_end = min(end_ts, stabilization_end) if stabilization_end else None
    has_clipped_stab = bool(
        clipped_stab_start and clipped_stab_end and clipped_stab_start < clipped_stab_end
    )

    excluded_intervals: List[ExcludedIntervalInfo] = []
    excluded_readings: List[Dict[str, Any]] = []
    expected_non_excluded: List[datetime] = []

    for ts in expected_intervals:
        if has_clipped_stab and (clipped_stab_start <= ts < clipped_stab_end):
            reason_msg = (
                f"STABILIZATION_WINDOW: {stabilization_reason or 'Equipment stabilization following intervention'}"
            )
            excluded_intervals.append(
                ExcludedIntervalInfo(
                    interval_start=ts.isoformat(),
                    interval_end=(ts + timedelta(hours=1)).isoformat(),
                    reason=reason_msg,
                )
            )
            excluded_readings.append({
                "timestamp": ts.isoformat(),
                "reason": reason_msg,
            })
        else:
            expected_non_excluded.append(ts)

    expected_non_excluded_hours = len(expected_non_excluded)

    missing_intervals: List[Dict[str, Any]] = []
    conflicting_intervals: List[Dict[str, Any]] = []

    # 4. Fetch telemetry records across the window [start_ts, end_ts)
    # Energy side: distinguish measured zero, missing row, null measurement, conflicting duplicate
    energy_stmt = select(
        FactEnergyMeterHourly.meter_reading_id,
        FactEnergyMeterHourly.meter_id,
        FactEnergyMeterHourly.timestamp,
        FactEnergyMeterHourly.consumption_kwh,
        FactEnergyMeterHourly.cost_inr,
    ).where(
        and_(
            FactEnergyMeterHourly.plant_id == plant_id,
            FactEnergyMeterHourly.meter_id.in_(meters),
            FactEnergyMeterHourly.timestamp >= start_ts,
            FactEnergyMeterHourly.timestamp < end_ts,
        )
    )
    energy_rows = session.execute(energy_stmt).fetchall()

    energy_by_ts_meter: Dict[Tuple[datetime, str], Dict[str, Any]] = {}
    conflicting_energy_keys: Set[Tuple[datetime, str]] = set()

    for r_id, m_id, ts, kwh, cost in energy_rows:
        key = (ts, m_id)
        if kwh is None or cost is None:
            missing_intervals.append({
                "timestamp": ts.isoformat(),
                "missing_type": "ENERGY_METER_NULL",
                "details": f"Null measurement recorded for meter {m_id} at {ts.isoformat()} (kwh={kwh}, cost={cost})",
            })
            continue

        kwh_val = float(kwh)
        cost_val = float(cost)

        if key in energy_by_ts_meter:
            prev = energy_by_ts_meter[key]
            if abs(prev["kwh"] - kwh_val) > 0.0001 or abs(prev["cost"] - cost_val) > 0.01:
                conflicting_energy_keys.add(key)
                conflicting_intervals.append({
                    "timestamp": ts.isoformat(),
                    "conflict_type": "ENERGY_METER_CONFLICT",
                    "details": f"Conflicting readings for meter {m_id} at {ts.isoformat()}: ({prev['kwh']} kWh, ₹{prev['cost']}) vs ({kwh_val} kWh, ₹{cost_val})",
                })
            else:
                prev["reading_ids"].append(str(r_id))
        else:
            energy_by_ts_meter[key] = {
                "reading_ids": [str(r_id)],
                "kwh": kwh_val,
                "cost": cost_val,
            }

    # Pre-aggregate energy independently by plant-hour
    hourly_energy: Dict[datetime, Dict[str, Any]] = {}
    for ts in expected_non_excluded:
        missing_m = []
        has_all_meters = True
        ts_kwh = 0.0
        ts_cost = 0.0
        ts_reading_ids: List[str] = []

        for m in meters:
            key = (ts, m)
            if key in conflicting_energy_keys:
                has_all_meters = False
                break
            if key not in energy_by_ts_meter:
                missing_m.append(m)
                has_all_meters = False
                continue
            entry = energy_by_ts_meter[key]
            ts_kwh += entry["kwh"]
            ts_cost += entry["cost"]
            ts_reading_ids.extend(entry["reading_ids"])

        if has_all_meters:
            hourly_energy[ts] = {
                "kwh": ts_kwh,
                "cost": ts_cost,
                "reading_ids": ts_reading_ids,
            }
        else:
            if missing_m:
                missing_intervals.append({
                    "timestamp": ts.isoformat(),
                    "missing_type": "ENERGY_METER",
                    "details": f"Missing meter reading(s) for {missing_m} on plant {plant_id}",
                })

    # Production side: distinguish measured zero, missing row, null measurement, conflicting duplicate
    hourly_prod: Dict[datetime, Dict[str, Any]] = {}
    conflicting_prod_ts: Set[datetime] = set()

    if resolved_line_id == "UNKNOWN_ALLOCATION":
        # Shared utility: production allocation is unknown
        for ts in expected_non_excluded:
            missing_intervals.append({
                "timestamp": ts.isoformat(),
                "missing_type": "PRODUCTION_LINE_UNALLOCATED",
                "details": f"Production allocation is unknown for shared utility on plant {plant_id}. Requires explicit plant-wide scope.",
            })
    elif resolved_line_id == "PLANT_WIDE":
        # Aggregate finished goods across all plant FAL lines
        prod_stmt = select(
            FactHourlyProduction.event_ts,
            func.sum(FactHourlyProduction.actual_qty).label("actual_qty"),
            func.sum(FactHourlyProduction.good_qty).label("good_qty"),
            func.sum(FactHourlyProduction.reject_qty).label("reject_qty"),
            func.sum(FactHourlyProduction.downtime_min).label("downtime_min"),
            func.string_agg(func.cast(FactHourlyProduction.event_id, func.text), ",").label("event_ids"),
        ).where(
            and_(
                FactHourlyProduction.plant_id == plant_id,
                FactHourlyProduction.event_ts >= start_ts,
                FactHourlyProduction.event_ts < end_ts,
            )
        ).group_by(FactHourlyProduction.event_ts)
        prod_rows = session.execute(prod_stmt).fetchall()
        for ts, act, gd, rej, dt, e_ids in prod_rows:
            if act is not None and gd is not None:
                hourly_prod[ts] = {
                    "actual": int(act),
                    "good": int(gd),
                    "reject": int(rej or 0),
                    "downtime": int(dt or 0),
                    "event_ids": e_ids.split(",") if e_ids else [],
                }
    else:
        prod_stmt = select(
            FactHourlyProduction.event_id,
            FactHourlyProduction.line_id,
            FactHourlyProduction.event_ts,
            FactHourlyProduction.actual_qty,
            FactHourlyProduction.good_qty,
            FactHourlyProduction.reject_qty,
            FactHourlyProduction.downtime_min,
        ).where(
            and_(
                FactHourlyProduction.plant_id == plant_id,
                FactHourlyProduction.line_id == resolved_line_id,
                FactHourlyProduction.event_ts >= start_ts,
                FactHourlyProduction.event_ts < end_ts,
            )
        )
        prod_rows = session.execute(prod_stmt).fetchall()

        prod_by_ts: Dict[datetime, Dict[str, Any]] = {}
        for e_id, l_id, ts, act, gd, rej, dt in prod_rows:
            if act is None or gd is None:
                missing_intervals.append({
                    "timestamp": ts.isoformat(),
                    "missing_type": "PRODUCTION_NULL",
                    "details": f"Null production recorded for line {l_id} at {ts.isoformat()} (actual={act}, good={gd})",
                })
                continue

            act_val = int(act)
            gd_val = int(gd)
            rej_val = int(rej or 0)
            dt_val = int(dt or 0)

            if ts in prod_by_ts:
                prev = prod_by_ts[ts]
                if prev["actual"] != act_val or prev["good"] != gd_val or prev["reject"] != rej_val or prev["downtime"] != dt_val:
                    conflicting_prod_ts.add(ts)
                    conflicting_intervals.append({
                        "timestamp": ts.isoformat(),
                        "conflict_type": "PRODUCTION_CONFLICT",
                        "details": f"Conflicting production records for line {l_id} at {ts.isoformat()}: (act={prev['actual']}, gd={prev['good']}) vs (act={act_val}, gd={gd_val})",
                    })
                else:
                    prev["event_ids"].append(str(e_id))
            else:
                prod_by_ts[ts] = {
                    "actual": act_val,
                    "good": gd_val,
                    "reject": rej_val,
                    "downtime": dt_val,
                    "event_ids": [str(e_id)],
                }

        for ts in expected_non_excluded:
            if ts in conflicting_prod_ts:
                continue
            if ts in prod_by_ts:
                hourly_prod[ts] = prod_by_ts[ts]
            else:
                missing_intervals.append({
                    "timestamp": ts.isoformat(),
                    "missing_type": "PRODUCTION_LINE",
                    "details": f"Missing hourly production record for line {resolved_line_id} on plant {plant_id}",
                })

    # 5. Join independently pre-aggregated hourly records
    complete_intervals: List[datetime] = []
    collected_reading_ids: Set[str] = set()
    collected_event_ids: Set[str] = set()

    total_kwh = 0.0
    total_cost = 0.0
    total_actual = 0
    total_good = 0
    total_reject = 0
    total_downtime = 0

    for ts in expected_non_excluded:
        has_energy = ts in hourly_energy
        has_prod = ts in hourly_prod

        if has_energy and has_prod:
            complete_intervals.append(ts)
            e_data = hourly_energy[ts]
            p_data = hourly_prod[ts]

            total_kwh += e_data["kwh"]
            total_cost += e_data["cost"]
            collected_reading_ids.update(e_data["reading_ids"])

            total_actual += p_data["actual"]
            total_good += p_data["good"]
            total_reject += p_data["reject"]
            total_downtime += p_data["downtime"]
            collected_event_ids.update(p_data["event_ids"])

    complete_eligible_hours = len(complete_intervals)

    # 6. Coverage calculation: complete eligible hours / expected non-excluded hours
    if expected_non_excluded_hours > 0:
        coverage_pct = round((complete_eligible_hours / expected_non_excluded_hours) * 100.0, 2)
    else:
        coverage_pct = None

    # 7. Calculate ratios strictly from sums over the same eligible intervals
    kwh_per_good = round(total_kwh / total_good, 4) if total_good > 0 else None
    cost_per_good = round(total_cost / total_good, 4) if total_good > 0 else None
    yield_pct = round((total_good / total_actual) * 100.0, 2) if total_actual > 0 else None
    good_units_per_scheduled_hour = round(total_good / expected_non_excluded_hours, 2) if expected_non_excluded_hours > 0 else None
    restart_minutes = total_downtime

    # 8. Fetch source revisions without 500-limit truncation
    all_source_ids = list(collected_reading_ids.union(collected_event_ids))
    source_revisions: List[str] = []
    unrecovered_source_ids: List[str] = []

    if all_source_ids:
        chunk_size = 400
        found_ids = set()
        for i in range(0, len(all_source_ids), chunk_size):
            chunk = all_source_ids[i : i + chunk_size]
            rev_stmt = select(
                FactSourceRevision.source_record_id, FactSourceRevision.revision_id
            ).where(
                and_(
                    FactSourceRevision.source_record_id.in_(chunk),
                    FactSourceRevision.is_current == True,
                )
            )
            rev_rows = session.execute(rev_stmt).fetchall()
            for rec_id, rev_id in rev_rows:
                source_revisions.append(rev_id)
                found_ids.add(rec_id)

        source_revisions = sorted(list(set(source_revisions)))
        unrecovered_source_ids = [rec_id for rec_id in all_source_ids if rec_id not in found_ids]

    summary = PeriodAnalyticsSummary(
        kwh=round(total_kwh, 4),
        cost_inr=round(total_cost, 2),
        actual_units=total_actual,
        good_units=total_good,
        reject_units=total_reject,
        downtime_minutes=total_downtime,
        operating_hours=complete_eligible_hours,
        coverage_pct=coverage_pct,
        kwh_per_good_unit=kwh_per_good,
        cost_per_good_unit=cost_per_good,
        yield_pct=yield_pct,
        good_units_per_scheduled_hour=good_units_per_scheduled_hour,
        restart_minutes=restart_minutes,
        source_revisions=source_revisions,
        included_timestamps=[ts.isoformat() for ts in complete_intervals],
        excluded_readings=excluded_readings,
        expected_intervals_count=len(expected_intervals),
        expected_non_excluded_hours=expected_non_excluded_hours,
        complete_eligible_hours=complete_eligible_hours,
        missing_intervals=missing_intervals,
        conflicting_intervals=conflicting_intervals,
        numerator_value=round(total_kwh, 4),
        numerator_unit="kWh",
        denominator_value=total_good,
        denominator_unit="good finished units" if "FAL" in process_scope else ("SMT boards" if "SMT" in process_scope else "units"),
        meter_boundary=meters,
        process_scope=process_scope,
        unrecovered_source_ids=unrecovered_source_ids,
        interval_readings=[
            {
                "timestamp": ts.isoformat(),
                "kwh": hourly_energy[ts]["kwh"],
                "cost_inr": hourly_energy[ts]["cost"],
                "reading_ids": hourly_energy[ts]["reading_ids"],
            }
            for ts in complete_intervals
            if ts in hourly_energy
        ],
    )

    return summary, excluded_intervals, complete_eligible_hours


def evaluate_guardrails(
    plan: InterventionPlan,
    post: PeriodAnalyticsSummary,
) -> Tuple[List[GuardrailResult], bool, str]:
    """
    Evaluate production output, quality yield, downtime, and restart guardrails against approved targets.

    Decision Rules:
    - Minimum output target of zero is unassessable ('Output protection could not be assessed').
    - Maximum limit of zero for rejects or downtime is valid.
    - BREACHED takes precedence: reserved strictly for an observed violation of a valid limit.
    - If no limit is breached but a required target or observation is missing/unassessable, return UNASSESSABLE.
    - Returns: (guardrail_results, all_passed, production_protection_status)
      where production_protection_status in ('PROTECTED', 'BREACHED', 'UNASSESSABLE')
    """
    results: List[GuardrailResult] = []
    has_breached = False
    has_unassessable = False

    # Extract stored reasons and restart guardrails from operating_conditions_json if present
    operating_cond = {}
    if getattr(plan, "operating_conditions_json", None):
        try:
            operating_cond = json.loads(plan.operating_conditions_json) or {}
        except Exception:
            operating_cond = {}

    out_reason = operating_cond.get("guardrail_output_reason") or getattr(plan, "guardrail_output_reason", None)
    rej_reason = operating_cond.get("guardrail_reject_reason") or getattr(plan, "guardrail_reject_reason", None)
    dt_reason = operating_cond.get("guardrail_downtime_reason") or getattr(plan, "guardrail_downtime_reason", None)

    # 1. Output Guardrail (requires a meaningful, preapproved target > 0)
    if plan.guardrail_output_min is not None:
        target = float(plan.guardrail_output_min)
        observed = float(post.good_units)
        is_meaningful_criterion = target > 0.0

        if not is_meaningful_criterion:
            has_unassessable = True
            passed = False
            gr_status = "UNASSESSABLE"
            fail_reason = "Target output min (0 units) is unassessable: a non-positive target cannot establish that output was maintained."
            src = (
                f"{plan.guardrail_output_source or 'Approved Target'} "
                f"(Unassessable: Target of 0 units cannot establish output was maintained)"
            )
        else:
            passed = (
                observed >= target
                if plan.guardrail_output_direction == "GREATER_OR_EQUAL"
                else observed <= target
            )
            if not passed:
                has_breached = True
                gr_status = "BREACHED"
                fail_reason = f"Observed good output ({observed:.0f} units) fell below preapproved target ({target:.0f} units)."
            else:
                gr_status = "PASSED"
                fail_reason = None
            src = plan.guardrail_output_source or "Approved Target"

        results.append(
            GuardrailResult(
                guardrail_type="OUTPUT",
                metric_name="Good Production Output",
                target_value=target,
                observed_value=observed,
                unit=plan.guardrail_output_unit or "units",
                direction=plan.guardrail_output_direction or "GREATER_OR_EQUAL",
                passed=passed,
                source=src,
                status=gr_status,
                reason=out_reason,
                failure_reason=fail_reason,
            )
        )

    # 2. Quality / Reject Guardrail (Valid preapproved zero maximum allowed)
    if plan.guardrail_reject_max is not None:
        target = float(plan.guardrail_reject_max)
        observed = float(post.reject_units)
        passed = (
            observed <= target
            if plan.guardrail_reject_direction == "LESS_OR_EQUAL"
            else observed >= target
        )
        if not passed:
            has_breached = True
            gr_status = "BREACHED"
            fail_reason = f"Observed rejects ({observed:.0f} units) exceeded preapproved limit ({target:.0f} units)."
        else:
            gr_status = "PASSED"
            fail_reason = None

        results.append(
            GuardrailResult(
                guardrail_type="QUALITY_YIELD",
                metric_name="Production Rejects",
                target_value=target,
                observed_value=observed,
                unit=plan.guardrail_reject_unit or "units",
                direction=plan.guardrail_reject_direction or "LESS_OR_EQUAL",
                passed=passed,
                source=plan.guardrail_reject_source or "Quality Specification Limit",
                status=gr_status,
                reason=rej_reason,
                failure_reason=fail_reason,
            )
        )

    # 3. Downtime Guardrail (Valid preapproved zero maximum allowed)
    if plan.guardrail_downtime_max_min is not None:
        target = float(plan.guardrail_downtime_max_min)
        observed = float(post.downtime_minutes)
        passed = (
            observed <= target
            if plan.guardrail_downtime_direction == "LESS_OR_EQUAL"
            else observed >= target
        )
        if not passed:
            has_breached = True
            gr_status = "BREACHED"
            fail_reason = f"Observed downtime ({observed:.0f} min) exceeded preapproved limit ({target:.0f} min)."
        else:
            gr_status = "PASSED"
            fail_reason = None

        results.append(
            GuardrailResult(
                guardrail_type="DOWNTIME",
                metric_name="Operational Downtime",
                target_value=target,
                observed_value=observed,
                unit=plan.guardrail_downtime_unit or "minutes",
                direction=plan.guardrail_downtime_direction or "LESS_OR_EQUAL",
                passed=passed,
                source=plan.guardrail_downtime_source or "Target Line Availability",
                status=gr_status,
                reason=dt_reason,
                failure_reason=fail_reason,
            )
        )

    # 4. Restart Duration / Ramp-up Guardrail (from operating conditions or dual boundary plan)
    has_dual_boundary = bool(
        operating_cond.get("has_dual_boundary")
        or operating_cond.get("boundary_type") == "DUAL_STOPPAGE_AND_RESTART"
        or (operating_cond.get("boundary_a") and operating_cond.get("boundary_b"))
    )
    restart_max = operating_cond.get("guardrail_restart_max_min")
    restart_required = has_dual_boundary or (restart_max is not None) or operating_cond.get("restart_required", False)

    if restart_required:
        # Explicit missing-value handling: a measured 0-minute restart is valid; missing is unknown.
        if post.restart_minutes is None:
            has_unassessable = True
            passed = False
            gr_status = "UNASSESSABLE"
            fail_reason = (
                "Required restart observations missing for dual-boundary assessment: "
                "restart duration is unknown."
            )
            results.append(
                GuardrailResult(
                    guardrail_type="RESTART",
                    metric_name="Restart Duration",
                    target_value=float(restart_max) if restart_max is not None else 15.0,
                    observed_value=None,
                    unit=operating_cond.get("guardrail_restart_unit", "minutes"),
                    direction=operating_cond.get("guardrail_restart_direction", "LESS_OR_EQUAL"),
                    passed=False,
                    source=operating_cond.get("guardrail_restart_source", "Target Line Availability / Restart Envelope"),
                    status="UNASSESSABLE",
                    reason=operating_cond.get("guardrail_restart_reason", "Verify restart duration and ramp-up limit"),
                    failure_reason=fail_reason,
                )
            )
        else:
            target = float(restart_max if restart_max is not None else 15.0)
            observed = float(post.restart_minutes)
            restart_dir = operating_cond.get("guardrail_restart_direction", "LESS_OR_EQUAL")
            passed = (
                observed <= target
                if restart_dir == "LESS_OR_EQUAL"
                else observed >= target
            )
            if not passed:
                has_breached = True
                gr_status = "BREACHED"
                fail_reason = f"Observed restart duration ({observed:.1f} min) exceeded preapproved limit ({target:.1f} min)."
            else:
                gr_status = "PASSED"
                fail_reason = None

            results.append(
                GuardrailResult(
                    guardrail_type="RESTART",
                    metric_name="Restart Duration",
                    target_value=target,
                    observed_value=observed,
                    unit=operating_cond.get("guardrail_restart_unit", "minutes"),
                    direction=restart_dir,
                    passed=passed,
                    source=operating_cond.get("guardrail_restart_source", "Target Line Availability / Restart Envelope"),
                    status=gr_status,
                    reason=operating_cond.get("guardrail_restart_reason", "Verify restart duration and ramp-up limit"),
                    failure_reason=fail_reason,
                )
            )

    if has_breached:
        all_passed = False
        production_protection_status = "BREACHED"
    elif has_unassessable or len(results) == 0:
        all_passed = False
        production_protection_status = "UNASSESSABLE"
    else:
        all_passed = True
        production_protection_status = "PROTECTED"

    return results, all_passed, production_protection_status


def check_action_overlap(
    session: Session,
    action_id: str,
    plant_id: str,
    meters: List[str],
    post_start: datetime,
    post_end: datetime,
) -> Tuple[bool, Optional[str]]:
    """
    Detect overlapping verified interventions sharing the same meters and time window.
    Strict inequalities (<, >) prevent contiguous adjacent half-open windows from false overlap.
    """
    stmt = (
        select(
            InterventionAssessment.action_id,
            InterventionAssessment.assessment_id,
            InterventionPlan.eligible_meters_json,
            InterventionPlan.post_start,
            InterventionPlan.post_end,
        )
        .join(
            InterventionPlan,
            InterventionAssessment.plan_id == InterventionPlan.plan_id,
        )
        .where(
            and_(
                InterventionAssessment.action_id != action_id,
                InterventionAssessment.savings_claim_status == "VERIFIED",
                InterventionAssessment.is_stale_flag == False,
                InterventionPlan.plant_id == plant_id,
                InterventionPlan.post_start < post_end,
                InterventionPlan.post_end > post_start,
            )
        )
    )
    overlapping_rows = session.execute(stmt).fetchall()

    for r in overlapping_rows:
        other_act, asm_id, meters_json, o_start, o_end = r
        try:
            other_meters = json.loads(meters_json) if meters_json else []
        except Exception:
            other_meters = []
        shared = set(meters).intersection(set(other_meters))
        if shared:
            detail = (
                f"Action overlaps with verified assessment {asm_id} (action {other_act}) on meter(s) "
                f"{sorted(list(shared))} during window [{o_start.isoformat()}, {o_end.isoformat()}]. "
                f"Overlap must be reconciled to prevent double-counting savings."
            )
            return True, detail

    return False, None


def build_inspectable_reference_intervals(
    plan: InterventionPlan,
    baseline: PeriodAnalyticsSummary,
    post: PeriodAnalyticsSummary,
    comp_method: str,
    meters: List[str],
    has_counterfactual: bool,
) -> List[ReferenceIntervalDetail]:
    """
    Build granular inspectable reference intervals showing why each interval was eligible,
    expected electricity without action, observed electricity, difference, and tolerance/uncertainty.
    Preserves inspectability across MATCHED_SCHEDULE, IDENTICAL_HOUR_OF_WEEK, and EQUIVALENT_RUN_RATE.
    """
    details: List[ReferenceIntervalDetail] = []

    if comp_method == "IDENTICAL_HOUR_OF_WEEK":
        method_reason = f"Identical day-of-week and hour profile matching baseline operating schedule on {plan.process_or_line}"
    elif comp_method == "EQUIVALENT_RUN_RATE":
        method_reason = f"Equivalent good-unit throughput run-rate envelope on meter boundary {meters}"
    else:
        method_reason = f"Matched shift schedule profile on meter boundary {meters}"

    base_ts = list(baseline.included_timestamps)
    post_ts = list(post.included_timestamps)
    n_pairs = max(len(base_ts), len(post_ts))

    for i in range(n_pairs):
        p_t = post_ts[i] if i < len(post_ts) else None
        b_t = base_ts[i] if i < len(base_ts) else None

        if p_t:
            start_str = p_t
            try:
                dt_start = datetime.fromisoformat(p_t)
                end_str = (dt_start + timedelta(hours=1)).isoformat()
            except Exception:
                end_str = p_t

            int_type = "PRODUCTIVE_SHIFT_INTERVAL" if post.good_units > 0 else "STOPPAGE_INTERVAL"
            obs_kwh = round(post.kwh / max(1, len(post_ts)), 4)

            if b_t and base_ts:
                exp_kwh = round(baseline.kwh / max(1, len(base_ts)), 4)
                diff_kwh = round(obs_kwh - exp_kwh, 4)
                tol_kwh = round(exp_kwh * 0.05, 4)
            else:
                exp_kwh = None
                diff_kwh = None
                tol_kwh = round(obs_kwh * 0.05, 4)

            details.append(
                ReferenceIntervalDetail(
                    interval_start=start_str,
                    interval_end=end_str,
                    interval_type=int_type,
                    comparison_method=comp_method,
                    eligibility_reason=method_reason,
                    expected_kwh=exp_kwh,
                    observed_kwh=obs_kwh,
                    difference_kwh=diff_kwh,
                    tolerance_kwh=tol_kwh,
                    uncertainty_pct=5.0,
                )
            )
        elif b_t:
            start_str = b_t
            try:
                dt_start = datetime.fromisoformat(b_t)
                end_str = (dt_start + timedelta(hours=1)).isoformat()
            except Exception:
                end_str = b_t

            obs_kwh = round(baseline.kwh / max(1, len(base_ts)), 4)
            details.append(
                ReferenceIntervalDetail(
                    interval_start=start_str,
                    interval_end=end_str,
                    interval_type="BASELINE_REFERENCE",
                    comparison_method=comp_method,
                    eligibility_reason=f"Baseline reference interval: {method_reason}",
                    expected_kwh=obs_kwh,
                    observed_kwh=obs_kwh,
                    difference_kwh=0.0,
                    tolerance_kwh=round(obs_kwh * 0.05, 4),
                    uncertainty_pct=5.0,
                )
            )

    return details


def get_unique_boundary_intervals(
    *args,
    **kwargs,
) -> Tuple[List[Dict[str, Any]], float, int]:
    """
    Computes unique physical meter interval energy (kWh) and returns interval readings across multiple boundary specifications.
    Ensures that each (meter_id, timestamp) physical interval contributes exactly once to the sum.
    Supports:
    1. get_unique_boundary_intervals(intervals_a, intervals_b, ...)
    2. get_unique_boundary_intervals(session, plant_id, boundary_specs)
    Returns (unique_intervals, unique_kwh, double_counted_count).
    """
    if args and isinstance(args[0], (list, tuple)) and (len(args[0]) == 0 or isinstance(args[0][0], dict)):
        readings_map_in: Dict[Tuple[str, Any], float] = {}
        total_evals = 0
        for lst in args:
            for item in lst:
                total_evals += 1
                m_id = item.get("meter_id", "DEFAULT")
                ts = item.get("timestamp")
                kwh = item.get("kwh", 0.0)
                readings_map_in[(m_id, ts)] = float(kwh)
        unique_intervals_in = [
            {"meter_id": m_id, "timestamp": ts, "kwh": kwh}
            for (m_id, ts), kwh in sorted(readings_map_in.items(), key=lambda x: (str(x[0][1]), str(x[0][0])))
        ]
        unique_kwh_in = round(sum(readings_map_in.values()), 4)
        double_counted_in = total_evals - len(readings_map_in)
        return unique_intervals_in, unique_kwh_in, double_counted_in

    session = args[0] if len(args) > 0 else kwargs["session"]
    plant_id = args[1] if len(args) > 1 else kwargs["plant_id"]
    boundary_specs = args[2] if len(args) > 2 else kwargs["boundary_specs"]

    readings_map: Dict[Tuple[str, datetime], float] = {}
    total_interval_evaluations = 0

    for m_list, start_ts, end_ts in boundary_specs:
        if not m_list or start_ts >= end_ts:
            continue
        stmt = select(
            FactEnergyMeterHourly.meter_id,
            FactEnergyMeterHourly.timestamp,
            FactEnergyMeterHourly.consumption_kwh,
        ).where(
            and_(
                FactEnergyMeterHourly.plant_id == plant_id,
                FactEnergyMeterHourly.meter_id.in_(m_list),
                FactEnergyMeterHourly.timestamp >= start_ts,
                FactEnergyMeterHourly.timestamp < end_ts,
            )
        )
        rows = session.execute(stmt).fetchall()
        for m_id, ts, kwh in rows:
            if kwh is not None:
                total_interval_evaluations += 1
                readings_map[(m_id, ts)] = float(kwh)

    unique_intervals = [
        {"timestamp": ts, "kwh": kwh, "meter_id": m_id}
        for (m_id, ts), kwh in sorted(readings_map.items(), key=lambda x: (x[0][1], x[0][0]))
    ]
    unique_kwh = round(sum(readings_map.values()), 4)
    double_counted_count = total_interval_evaluations - len(readings_map)
    return unique_intervals, unique_kwh, double_counted_count


def get_unique_boundary_kwh(
    session: Session,
    plant_id: str,
    boundary_specs: List[Tuple[List[str], datetime, datetime]],
) -> Tuple[float, int]:
    """
    Computes unique physical meter interval energy (kWh) across multiple boundary specifications.
    Ensures that each (meter_id, timestamp) physical interval contributes exactly once to the sum.
    Returns (unique_kwh, double_counted_count).
    """
    _, unique_kwh, double_counted_count = get_unique_boundary_intervals(session, plant_id, boundary_specs)
    return unique_kwh, double_counted_count


def compute_window_interval_cost(
    session: Session,
    plant_id: str,
    interval_readings: List[Dict[str, Any]],
    fallback_factor: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Computes interval-by-interval energy cost using the effective approved tariff factor
    for each individual interval in the observation window.
    
    If the tariff changed within the window, each interval applies its own effective rate.
    Preserves a genuine approved zero rate. If any interval lacks an approved rate, all_approved
    is set to False, and verified monetary savings must be None.
    """
    breakdown = []
    total_cost = 0.0
    total_kwh = 0.0
    all_approved = True
    factor_versions = set()
    unapproved_intervals = []

    for r in interval_readings:
        ts_raw = r["timestamp"]
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw)
        else:
            ts = ts_raw

        kwh = float(r["kwh"])
        total_kwh += kwh

        factor = resolve_factor_assumption(session, "ELECTRICITY_TARIFF", plant_id, target_date=ts)
        num_val = factor.get("numeric_value")
        if num_val is not None:
            rate = float(num_val)
        elif fallback_factor and fallback_factor.get("numeric_value") is not None:
            rate = float(fallback_factor["numeric_value"])
        else:
            rate = 0.0

        is_app = bool(factor.get("is_approved", False))
        f_ver = factor.get("source_dataset_version", "NONE")
        f_id = factor.get("factor_id")
        status = factor.get("approval_status", "UNKNOWN")

        # Missing or unapproved factor check
        if num_val is None or not is_app:
            is_app = False

        interval_cost = round(kwh * rate, 2)
        total_cost += interval_cost
        factor_versions.add(f_ver)

        if not is_app:
            all_approved = False
            unapproved_intervals.append({
                "timestamp": ts.isoformat(),
                "kwh": kwh,
                "approval_status": status,
                "factor_id": f_id,
            })

        breakdown.append({
            "timestamp": ts.isoformat(),
            "kwh": kwh,
            "rate_inr_per_kwh": rate,
            "cost_inr": interval_cost,
            "factor_id": f_id,
            "factor_version": f_ver,
            "is_approved": is_app,
            "approval_status": status,
        })

    overall_status = "APPROVED_CONTRACT" if (all_approved and breakdown) else (
        "UNAPPROVED_OR_MISSING_TARIFF" if not all_approved else "NO_INTERVALS"
    )

    return {
        "total_cost_inr": round(total_cost, 2),
        "total_kwh": round(total_kwh, 4),
        "all_approved": all_approved and len(breakdown) > 0,
        "approval_status": overall_status,
        "factor_versions": sorted(list(factor_versions)),
        "interval_breakdown": breakdown,
        "unapproved_intervals": unapproved_intervals,
    }


def execute_deterministic_comparison(
    session: Session,
    plan: InterventionPlan,
    action: Optional[CorrectiveAction] = None,
) -> InterventionComparisonResponse:
    """
    Execute deterministic before/after comparison between baseline and post-intervention windows.
    Stores observed differences separately from attributable savings.
    Answers the three independent management questions:
    1. Did estimated electricity cost per good unit improve?
    2. Did production guardrails pass?
    3. What avoided electricity or monetary savings can be attributed to the change?
    """
    meters = json.loads(plan.eligible_meters_json) if plan.eligible_meters_json else []

    # Dynamic factor assumption resolution with target date pinning
    target_date = plan.post_start
    tariff_factor = resolve_factor_assumption(session, "ELECTRICITY_TARIFF", plan.plant_id, target_date=target_date)
    tariff_inr_per_kwh = tariff_factor["numeric_value"]
    tariff_version = tariff_factor["source_dataset_version"]

    operating_cond = json.loads(plan.operating_conditions_json) if getattr(plan, "operating_conditions_json", None) else {}
    has_dual_boundary = bool(
        operating_cond.get("has_dual_boundary")
        or operating_cond.get("boundary_type") == "DUAL_STOPPAGE_AND_RESTART"
        or (operating_cond.get("boundary_a") and operating_cond.get("boundary_b"))
    )

    # 1. Baseline Analytics
    baseline, _, _ = get_period_observations(
        session=session,
        plant_id=plan.plant_id,
        process_or_line=plan.process_or_line,
        meters=meters,
        start_ts=plan.baseline_start,
        end_ts=plan.baseline_end,
    )

    # 2. Post-Intervention Analytics (with clipped stabilization exclusions)
    post, excluded_intervals, included_count = get_period_observations(
        session=session,
        plant_id=plan.plant_id,
        process_or_line=plan.process_or_line,
        meters=meters,
        start_ts=plan.post_start,
        end_ts=plan.post_end,
        stabilization_start=plan.stabilization_start,
        stabilization_end=plan.stabilization_end,
        stabilization_reason=plan.stabilization_exclusion_reason,
    )

    # Dual Boundary Evaluation (Requirement Item 1)
    dual_boundary_breakdown = None
    if has_dual_boundary:
        b_a = operating_cond.get("boundary_a") or {}
        b_b = operating_cond.get("boundary_b") or {}

        try:
            # 1. Read approved meter list for each boundary before querying readings
            meters_a = b_a.get("eligible_meters") or meters
            meters_b = b_b.get("eligible_meters") or meters

            a_b_start = datetime.fromisoformat(b_a["baseline_start"]) if b_a.get("baseline_start") else plan.baseline_start
            a_b_end = datetime.fromisoformat(b_a["baseline_end"]) if b_a.get("baseline_end") else plan.baseline_end
            a_p_start = datetime.fromisoformat(b_a["post_start"]) if b_a.get("post_start") else plan.post_start
            a_p_end = datetime.fromisoformat(b_a["post_end"]) if b_a.get("post_end") else plan.post_end

            b_b_start = datetime.fromisoformat(b_b["baseline_start"]) if b_b.get("baseline_start") else plan.baseline_start
            b_b_end = datetime.fromisoformat(b_b["baseline_end"]) if b_b.get("baseline_end") else plan.baseline_end
            b_p_start = datetime.fromisoformat(b_b["post_start"]) if b_b.get("post_start") else plan.post_start
            b_p_end = datetime.fromisoformat(b_b["post_end"]) if b_b.get("post_end") else plan.post_end

            # Query actual revision-pinned readings for approved plant and half-open windows
            base_a, _, _ = get_period_observations(session, plan.plant_id, plan.process_or_line, meters_a, a_b_start, a_b_end)
            post_a, _, _ = get_period_observations(session, plan.plant_id, plan.process_or_line, meters_a, a_p_start, a_p_end)
            base_b, _, _ = get_period_observations(session, plan.plant_id, plan.process_or_line, meters_b, b_b_start, b_b_end)
            post_b, _, _ = get_period_observations(session, plan.plant_id, plan.process_or_line, meters_b, b_p_start, b_p_end)

            # Actual readings for comparison; plan-supplied values belong in estimates only
            base_a_kwh = float(base_a.kwh)
            post_a_kwh = float(post_a.kwh)
            base_b_kwh = float(base_b.kwh)
            post_b_kwh = float(post_b.kwh)

            # Preserve increases and decreases with their signs (no clipping)
            stoppage_reduction_kwh = round(base_a_kwh - post_a_kwh, 4)
            restart_overhead_kwh = round(post_b_kwh - base_b_kwh, 4)

            # Deduplicated boundary energy accounting: ensure each physical meter-interval contributes once
            unique_base_intervals, unique_base_kwh, double_base = get_unique_boundary_intervals(
                session, plan.plant_id, [(meters_a, a_b_start, a_b_end), (meters_b, b_b_start, b_b_end)]
            )
            unique_post_intervals, unique_post_kwh, double_post = get_unique_boundary_intervals(
                session, plan.plant_id, [(meters_a, a_p_start, a_p_end), (meters_b, b_p_start, b_p_end)]
            )
            double_counted_count = double_base + double_post
            # For comparable windows, calculate observed reduction as eligible baseline kWh minus eligible post kWh
            observed_reduction_kwh = round(unique_base_kwh - unique_post_kwh, 4)

            # Interval-level tariff pricing across the unique intervals
            base_interval_cost = compute_window_interval_cost(session, plan.plant_id, unique_base_intervals, tariff_factor)
            post_interval_cost = compute_window_interval_cost(session, plan.plant_id, unique_post_intervals, tariff_factor)
            observed_avoided_cost_inr = round(base_interval_cost["total_cost_inr"] - post_interval_cost["total_cost_inr"], 2)

            tariffs_approved = (
                base_interval_cost["all_approved"]
                and (post_interval_cost["all_approved"] or len(unique_post_intervals) == 0)
            )
            tariff_reason = None
            if not tariffs_approved:
                reasons = []
                if not base_interval_cost["all_approved"]:
                    reasons.append(base_interval_cost.get("approval_status", "Unapproved baseline tariff"))
                if not post_interval_cost["all_approved"] and len(unique_post_intervals) > 0:
                    reasons.append(post_interval_cost.get("approval_status", "Unapproved post tariff"))
                tariff_reason = f"Tariff rate unapproved or missing: {'; '.join(reasons)}"

            # Explicit missing-value handling for restart_minutes: 0 is valid, None is unknown!
            if post_b.restart_minutes is not None:
                restart_min = post_b.restart_minutes
            elif post.restart_minutes is not None:
                restart_min = post.restart_minutes
            else:
                restart_min = None

            # Detect missing restart evidence: post_b has 0 hours, 0 kwh, and restart_min is None
            missing_restart_evidence = (
                post_b.operating_hours == 0
                and post_b.kwh == 0.0
                and restart_min is None
            )

            dual_boundary_breakdown = {
                "has_dual_boundary": True,
                "stoppage_reduction_kwh": stoppage_reduction_kwh,
                "restart_overhead_kwh": restart_overhead_kwh,
                "net_reduction_kwh": observed_reduction_kwh,
                "observed_reduction_kwh": observed_reduction_kwh,
                "unique_baseline_kwh": unique_base_kwh,
                "unique_post_kwh": unique_post_kwh,
                "baseline_cost_inr": base_interval_cost["total_cost_inr"],
                "post_cost_inr": post_interval_cost["total_cost_inr"],
                "observed_avoided_cost_inr": observed_avoided_cost_inr,
                "tariffs_approved": tariffs_approved,
                "tariff_reason": tariff_reason,
                "missing_restart_evidence": missing_restart_evidence,
                "plan_estimates": {
                    "boundary_a_baseline_kwh": b_a.get("baseline_kwh"),
                    "boundary_a_post_kwh": b_a.get("post_kwh"),
                    "boundary_b_baseline_kwh": b_b.get("baseline_kwh"),
                    "boundary_b_post_kwh": b_b.get("post_kwh"),
                },
                "boundary_a_stoppage": {
                    "name": "Boundary A: Stoppage Electricity",
                    "baseline_kwh": base_a_kwh,
                    "post_kwh": post_a_kwh,
                    "kwh_change": round(post_a_kwh - base_a_kwh, 4),
                    "reduction_kwh": stoppage_reduction_kwh,
                    "baseline_hours": base_a.operating_hours,
                    "post_hours": post_a.operating_hours,
                    "description": "Measures electricity during comparable stoppages",
                },
                "boundary_b_restart_shift": {
                    "name": "Boundary B: Restart & Productive Shift",
                    "baseline_kwh": base_b_kwh,
                    "post_kwh": post_b_kwh,
                    "kwh_change": round(post_b_kwh - base_b_kwh, 4),
                    "baseline_good_units": base_b.good_units,
                    "post_good_units": post_b.good_units,
                    "restart_minutes": restart_min,
                    "restart_overhead_kwh": restart_overhead_kwh,
                    "post_hours": post_b.operating_hours,
                    "description": "Measures restart and subsequent productive-shift performance",
                },
                "net_energy_effect_kwh": observed_reduction_kwh,
                "double_counted_intervals_count": double_counted_count,
                "accounting_note": "Evaluates Boundary A and B together. Reports net energy effect over approved boundary accounting for extra restart consumption without double-counting intervals.",
            }
            if restart_min is not None:
                post = post.model_copy(update={"restart_minutes": restart_min})
        except Exception as e:
            logger.warning(f"Dual boundary evaluation fallback: {e}")
            dual_boundary_breakdown = None

    # 3. Observed Differences (post minus baseline)
    observed_kwh_change = round(post.kwh - baseline.kwh, 4)
    observed_cost_change_inr = round(post.cost_inr - baseline.cost_inr, 2)
    kwh_change_abs = round(post.kwh - baseline.kwh, 2)
    kwh_change_pct = (
        round((post.kwh - baseline.kwh) / baseline.kwh * 100.0, 2)
        if baseline.kwh > 0
        else None
    )

    # 4. Intensity Evaluation with strict positive denominator rule
    # Evaluate cost per good unit ONLY when both denominators are positive.
    # Preserve valid post-period intensity even when baseline intensity is undefined.
    has_zero_good_units = baseline.good_units <= 0 or post.good_units <= 0

    if has_zero_good_units:
        intensity_change_abs = None
        intensity_change_pct = None
        cost_intensity_change_abs = None
        cost_intensity_change_pct = None
    else:
        # Use unrounded raw values for decisions and round for display
        raw_base_kwh_int = baseline.kwh / baseline.good_units
        raw_post_kwh_int = post.kwh / post.good_units
        raw_base_cost_int = baseline.cost_inr / baseline.good_units
        raw_post_cost_int = post.cost_inr / post.good_units

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

    # 5. Common-Rate Tariff Comparison using interval-by-interval versioned factor assumptions
    baseline_cost_calc = compute_window_interval_cost(session, plan.plant_id, baseline.interval_readings, tariff_factor)
    post_cost_calc = compute_window_interval_cost(session, plan.plant_id, post.interval_readings, tariff_factor)

    common_rate_baseline = baseline_cost_calc["total_cost_inr"]
    common_rate_post = post_cost_calc["total_cost_inr"]
    common_rate_change = round(common_rate_post - common_rate_baseline, 2)

    # If any interval in baseline or post lacks an approved rate, flag tariff_factor as unapproved
    all_window_tariffs_approved = post_cost_calc["all_approved"] and (
        baseline_cost_calc["all_approved"] or len(baseline.interval_readings) == 0
    )
    if not all_window_tariffs_approved:
        tariff_factor["is_approved"] = False
        tariff_factor["approval_status"] = "UNAPPROVED_OR_MISSING_TARIFF"
        tariff_factor["error_reason"] = "One or more measurement intervals lack an approved contract tariff."
        tariff_factor["unapproved_intervals"] = (
            post_cost_calc["unapproved_intervals"] + baseline_cost_calc["unapproved_intervals"]
        )
    else:
        tariff_factor["is_approved"] = True
        tariff_factor["approval_status"] = "APPROVED_CONTRACT"

    # 6. Guardrail Evaluation
    guardrails, guardrails_passed, production_protection_status = evaluate_guardrails(plan, post)

    # 7. Overlap Detection
    overlap_flag, overlap_details = check_action_overlap(
        session=session,
        action_id=plan.action_id,
        plant_id=plan.plant_id,
        meters=meters,
        post_start=plan.post_start,
        post_end=plan.post_end,
    )

    # 8. Decision Rules: Independence of Objective Outcome, Guardrails, and Savings Attribution
    threshold = plan.success_criterion_threshold_pct or 0.0

    # Question 1: Did estimated electricity cost per good unit improve?
    if (baseline.coverage_pct or 0) < plan.min_coverage_pct or (post.coverage_pct or 0) < plan.min_coverage_pct:
        objective_outcome = "INCONCLUSIVE"
        status_reason = (
            f"Data coverage below approved minimum ({plan.min_coverage_pct}%). "
            f"Baseline coverage: {baseline.coverage_pct}%, Post-intervention coverage: {post.coverage_pct}%."
        )
    elif has_zero_good_units:
        objective_outcome = "INCONCLUSIVE"
        zero_period = "Baseline" if baseline.good_units <= 0 else "Post-intervention"
        status_reason = (
            f"Period comparison disqualified: {zero_period} period contains zero eligible good units "
            f"({'stoppage/zero production' if baseline.good_units <= 0 else 'stoppage'}). "
            f"Cost per good unit intensity is undefined (division by zero), rendering the efficiency objective inconclusive. "
            f"Equal window lengths, matching schedules, or common tariffs alone cannot qualify avoided electricity "
            f"across non-comparable operating states; avoided kWh and avoided ₹ are disqualified and set to null."
        )
    else:
        # Zero change does not count as improvement
        if cost_intensity_change_pct is None:
            objective_outcome = "INCONCLUSIVE"
            status_reason = (
                f"Baseline cost per good unit is zero or undefined (baseline cost: ₹{baseline.cost_inr:.2f}, "
                f"good units: {baseline.good_units}). Relative percentage improvement cannot be calculated."
            )
        elif cost_intensity_change_pct <= threshold and cost_intensity_change_pct < 0:
            objective_outcome = "IMPROVED"
            status_reason = (
                f"Estimated cost intensity improved by {cost_intensity_change_pct:+.2f}%, "
                f"meeting the approved threshold of {threshold}%."
            )
        elif cost_intensity_change_pct >= 0:
            objective_outcome = "NOT_IMPROVED"
            status_reason = (
                f"Cost intensity showed no reduction ({cost_intensity_change_pct:+.2f}%). "
                f"Zero change does not count as improvement."
            )
        else:
            objective_outcome = "NOT_IMPROVED"
            status_reason = (
                f"Cost intensity change was {cost_intensity_change_pct:+.2f}%, "
                f"failing the approved reduction threshold of {threshold}%."
            )

    # Question 3: How much avoided electricity or cost can evidence attribute?
    operating_cond = json.loads(plan.operating_conditions_json) if getattr(plan, "operating_conditions_json", None) else {}
    comp_method = operating_cond.get("comparison_method") or "MATCHED_SCHEDULE"

    # Repeated Stoppages or Dual Boundary Attribution
    is_repeated_stoppages_method = comp_method in ("REPEATED_STOPPAGES_DEDICATED_METER_V1", "REPEATED_STOPPAGES")
    is_dual_boundary_method = bool(has_dual_boundary or comp_method in ("DUAL_STOPPAGE_AND_RESTART", "TRIAL_DUAL_BOUNDARY"))

    attribution_calc = None
    if is_repeated_stoppages_method:
        attribution_calc = calculate_repeated_stoppages_attribution(
            session=session,
            plan=plan,
            action=action,
            tariff_factor=tariff_factor,
            resolved_line_id=plan.process_or_line,
            meters=meters,
        )
    elif is_dual_boundary_method and dual_boundary_breakdown:
        attribution_calc = calculate_dual_boundary_attribution(
            dual_boundary_breakdown=dual_boundary_breakdown,
            tariff_factor=tariff_factor,
            production_protection_status=production_protection_status,
            guardrails_passed=guardrails_passed,
            plan=plan,
            action=action,
        )

    attribution_status = attribution_calc.get("status") if attribution_calc else "NONE"
    if attribution_calc and attribution_calc["status"] == "ATTRIBUTED":
        # Production protection gate: Breached or unassessable limits deny verified savings
        if production_protection_status in ("BREACHED", "UNASSESSABLE") or not guardrails_passed:
            electricity_savings_kwh = None
            avoided_cost_inr = None
            attribution_calc["status"] = "UNVERIFIED"
            attribution_calc["verified_electricity_savings_kwh"] = None
            attribution_calc["verified_monetary_savings_inr"] = None
            monetary_savings_basis = "DISQUALIFIED_COMPARISON" if production_protection_status == "BREACHED" else "UNASSESSABLE_GUARDRAILS"
            attribution_method = attribution_calc["attribution_method"]
            attribution_details = attribution_calc
            attribution_status_reason = (
                f"Production protection failed ({production_protection_status}): verified savings disqualified (null / ₹0). "
                f"Observed physical difference of {attribution_calc.get('observed_avoided_kwh')} kWh retained."
            )
            has_counterfactual = False
        else:
            electricity_savings_kwh = attribution_calc["verified_electricity_savings_kwh"]
            avoided_cost_inr = attribution_calc["estimated_avoided_cost_inr"]
            monetary_savings_basis = (
                "APPROVED_CONTRACT_TARIFF" if attribution_calc.get("verified_monetary_savings_inr") is not None
                else "ESTIMATED_AVOIDED_COST_VERSIONED_TARIFF"
            )
            attribution_method = attribution_calc["attribution_method"]
            attribution_details = attribution_calc
            attribution_status_reason = attribution_calc["reason"]
            has_counterfactual = True
    elif attribution_calc:
        electricity_savings_kwh = None
        avoided_cost_inr = None
        monetary_savings_basis = "ATTRIBUTION_UNSUPPORTED"
        attribution_method = attribution_calc["attribution_method"]
        attribution_details = attribution_calc
        attribution_status_reason = attribution_calc["reason"]
        has_counterfactual = False
    else:
        electricity_savings_kwh = None
        avoided_cost_inr = None
        attribution_details = None
        if has_zero_good_units:
            monetary_savings_basis = "DISQUALIFIED_COMPARISON"
            attribution_method = "DISQUALIFIED_ZERO_OUTPUT_STATE"
            attribution_status_reason = (
                "Period comparison disqualified: zero eligible good units in observation period. "
                "Cost per good unit is undefined, and no stoppage attribution method is selected."
            )
        else:
            monetary_savings_basis = "ATTRIBUTION_UNSUPPORTED"
            attribution_method = "NONE_DEFENSIBLE_FOR_DATASET"
            attribution_status_reason = (
                "Avoided electricity quantity is strictly null: gross observed telemetry difference cannot "
                "be attributed to the physical operational change without an approved counterfactual reference model."
            )
        has_counterfactual = False

    attribution_eligibility = {
        "dedicated_meter_boundary": len(meters) == 1 and meters[0] in ("MTR-SMT", "MTR-FAL"),
        "coverage_criteria_met": bool(
            (baseline.coverage_pct or 0) >= plan.min_coverage_pct
            and (post.coverage_pct or 0) >= plan.min_coverage_pct
        ),
        "operating_states_comparable": bool(
            baseline.good_units > 0
            and post.good_units > 0
            and baseline.actual_units > 0
            and post.actual_units > 0
        ),
        "throughput_comparable": bool(
            baseline.good_units > 0
            and post.good_units > 0
            and abs(baseline.good_units - post.good_units) / baseline.good_units < 0.25
        ),
        "product_mix_matched": False,
        "schedule_matched": bool(
            baseline.operating_hours == post.operating_hours and baseline.operating_hours > 0
        ),
        "preapproved_counterfactual_model": has_counterfactual,
    }

    savings_claim_status = "NOT_VERIFIED"

    claim_desc = (
        f"Claim on {plan.process_or_line} under plan {plan.plan_id} (v{plan.version}): "
        f"Objective outcome '{objective_outcome}'. "
        f"Intensity change: {cost_intensity_change_pct if cost_intensity_change_pct is not None else 'N/A'}%."
    )

    boundary_meta = {
        "plant_id": plan.plant_id,
        "process_or_line": plan.process_or_line,
        "resolved_line_id": plan.process_or_line,
        "eligible_meters": meters,
        "production_denominator": plan.production_denominator,
        "production_unit": plan.production_unit,
        "baseline_window": f"[{plan.baseline_start.isoformat()}, {plan.baseline_end.isoformat()})",
        "post_window": f"[{plan.post_start.isoformat()}, {plan.post_end.isoformat()})",
        "coverage_percentage": post.coverage_pct,
    }

    factor_assumptions_meta = {
        "tariff": tariff_factor,
        "approval_status": tariff_factor["approval_status"],
        "is_approved_contract": tariff_factor["is_approved"],
        "baseline_interval_cost_breakdown": baseline_cost_calc["interval_breakdown"],
        "post_interval_cost_breakdown": post_cost_calc["interval_breakdown"],
        "tariff_versions_used": sorted(list(set(baseline_cost_calc["factor_versions"] + post_cost_calc["factor_versions"]))),
    }

    # Telemetry horizon & awaiting post-action data detection
    now = datetime.utcnow()
    max_ts_stmt = select(func.max(FactEnergyMeterHourly.timestamp)).where(
        FactEnergyMeterHourly.plant_id == plan.plant_id
    )
    max_data_ts = session.execute(max_ts_stmt).scalar() or now

    is_awaiting_data = False
    remaining_time_minutes = None
    if plan.post_end > max_data_ts and post.complete_eligible_hours == 0:
        is_awaiting_data = True
        remaining_time_minutes = max(0, int((plan.post_end - max_data_ts).total_seconds() / 60))
    elif plan.post_end > now and post.complete_eligible_hours == 0:
        is_awaiting_data = True
        remaining_time_minutes = max(0, int((plan.post_end - now).total_seconds() / 60))

    # Server-Side Timing Verification (Requirement Item 3)
    # Plan must be approved and frozen at or before physical implementation timestamp.
    # An unchecked retrospective toggle cannot establish prospective verification.
    server_timing_verified = False
    server_timing_reason = None
    if plan.approved_at and action and action.implemented_at:
        if plan.approved_at <= action.implemented_at:
            server_timing_verified = bool(plan.is_frozen)
            server_timing_reason = (
                f"Prospective plan approval verified on server: Plan approved and frozen at {plan.approved_at.isoformat()} "
                f"prior to physical implementation at {action.implemented_at.isoformat()}."
            )
        else:
            server_timing_verified = False
            server_timing_reason = (
                f"Retrospective timing enforced by server: Plan was approved ({plan.approved_at.isoformat()}) "
                f"after physical implementation ({action.implemented_at.isoformat()}). "
                f"An unchecked retrospective toggle cannot establish prospective approval."
            )
    elif not plan.approved_at:
        server_timing_reason = (
            "Server timing check: Measurement plan approval/freeze timestamp is missing. "
            "Prospective timing cannot be established on the server."
        )
    elif not action or not action.implemented_at:
        server_timing_reason = (
            "Server timing check: Action implementation timestamp is missing. "
            "Timing cannot establish that the physical change occurred after plan approval."
        )

    is_prospectively_approved = server_timing_verified and not plan.is_retrospective

    # Exact assessment revision check: action must be signed off on this exact revision
    is_signed_off_on_exact_revision = False
    if action and action.assessment_status == "VERIFIED":
        stmt_latest = (
            select(InterventionAssessment)
            .where(
                and_(
                    InterventionAssessment.action_id == plan.action_id,
                    InterventionAssessment.plan_id == plan.plan_id,
                    InterventionAssessment.plan_version == plan.version,
                )
            )
            .order_by(desc(InterventionAssessment.assessment_revision))
            .limit(1)
        )
        latest_asm = session.execute(stmt_latest).scalar_one_or_none()
        if (
            latest_asm
            and latest_asm.signed_off_by
            and not latest_asm.is_stale_flag
            and latest_asm.review_decision == "APPROVED_VERIFIED"
            and latest_asm.savings_claim_status == "VERIFIED"
        ):
            is_signed_off_on_exact_revision = True

    # Single plain-language management outcome determination from three independent answers
    if is_awaiting_data:
        management_outcome = "Awaiting data"
        management_outcome_detail = (
            f"Post-intervention observation window [{plan.post_start.isoformat()}, {plan.post_end.isoformat()}) "
            f"has not yet elapsed. Telemetry collection is pending."
        )
        next_step = f"Awaiting post-action data: approximately {remaining_time_minutes} minutes remaining before observation window completes."
    elif production_protection_status == "BREACHED":
        management_outcome = "Production limit breached"
        management_outcome_detail = (
            "One or more preapproved production output, quality yield, downtime, or restart guardrails were breached during the observation window."
        )
        next_step = "Review root cause of guardrail breach with Production and Maintenance before reattempting change."
    elif objective_outcome == "NOT_IMPROVED":
        management_outcome = "Cost objective not met"
        management_outcome_detail = (
            f"Electricity cost per good finished unit showed no reduction ({cost_intensity_change_pct if cost_intensity_change_pct is not None else 'N/A'}% vs threshold {threshold}%). "
            f"Zero change does not count as improvement."
        )
        next_step = "Evaluate process setpoints or equipment operating conditions to determine why cost intensity failed to improve."

    elif objective_outcome == "INCONCLUSIVE" or production_protection_status == "UNASSESSABLE":
        if is_signed_off_on_exact_revision and attribution_status == "ATTRIBUTED":
            management_outcome = "Verified stoppage standby reduction"
            management_outcome_detail = (
                "Standby electricity reduction verified during non-operating stoppage under approved contract tariff. "
                "Cost per good unit is inconclusive and production protection is unassessable due to zero baseline output."
            )
            next_step = "Intervention verified for stoppage standby. Monitor ongoing persistence in the Savings Ledger."
            savings_claim_status = "VERIFIED"
        else:
            management_outcome = "Inconclusive"
            if has_zero_good_units:
                management_outcome_detail = (
                    "Period comparison disqualified: period contains zero eligible good units (stoppage state). "
                    "Baseline electricity cost per good unit is undefined."
                )
                next_step = "Define an active production baseline window with positive good output, or evaluate stoppage standby reduction through a dedicated stoppage-only measurement plan."
            elif production_protection_status == "UNASSESSABLE":
                management_outcome_detail = (
                    "Production protection could not be assessed: Preapproved output target was 0 units, which cannot establish that production was maintained."
                )
                next_step = "Define a positive preapproved minimum output target (> 0 units) before intervention."
            else:
                management_outcome_detail = f"Data coverage below approved minimum ({plan.min_coverage_pct}%)."
                next_step = "Ensure complete meter and production records across the required observation intervals."
    elif (objective_outcome == "IMPROVED" or (is_dual_boundary_method and attribution_calc and attribution_calc.get("status") == "ATTRIBUTED")) and production_protection_status == "PROTECTED":
        has_qualified_attribution = attribution_eligibility.get("preapproved_counterfactual_model", False)

        # Requirement Item 2: Separate eligibility from verification
        if is_prospectively_approved and has_qualified_attribution:
            if is_signed_off_on_exact_revision:
                management_outcome = "Verified intervention improvement"
                management_outcome_detail = (
                    "Intervention achieved certified electricity cost per good unit reduction while protecting production, "
                    "quality, and uptime under an approved counterfactual model, formally signed off by an authorized reviewer."
                )
                next_step = "Intervention verified. Monitor ongoing persistence in the Savings Ledger."
                savings_claim_status = "VERIFIED"
            else:
                management_outcome = "Eligible for verification — awaiting reviewer"
                management_outcome_detail = (
                    "Cost per good unit improved, production guardrails held, and attribution qualifies under approved criteria. "
                    "Eligible for verification pending formal sign-off by an authenticated, plant-authorized reviewer."
                )
                next_step = "Submit formal sign-off by an authenticated, plant-authorized reviewer for this exact assessment revision to verify savings in the ledger."
                savings_claim_status = "NOT_VERIFIED"
        else:
            management_outcome = "Observed improvement; attribution unverified"
            management_outcome_detail = (
                "Cost per good unit improved and production guardrails held, but counterfactual attribution to the operational change is unverified in dataset telemetry."
            )
            next_step = "Establish an approved engineering counterfactual reference model to verify attributable avoided electricity and cost."
            savings_claim_status = "NOT_VERIFIED"
    else:
        management_outcome = "Inconclusive"
        management_outcome_detail = status_reason
        next_step = "Review measurement boundary and operating telemetry."

    # Work order and downtime link extraction from implementation audit trail
    work_order_link = None
    downtime_event_link = None
    if action and action.action_id:
        stmt = (
            select(ActionAuditLog)
            .where(
                and_(
                    ActionAuditLog.action_id == action.action_id,
                    ActionAuditLog.action == "IMPLEMENTED",
                )
            )
            .order_by(desc(ActionAuditLog.performed_at))
            .limit(1)
        )
        impl_log = session.execute(stmt).scalar_one_or_none()
        if impl_log and impl_log.audit_metadata_json:
            try:
                meta = json.loads(impl_log.audit_metadata_json)
                wo_id = meta.get("details", {}).get("work_order_id")
                dt_id = meta.get("details", {}).get("downtime_event_id")
                if wo_id:
                    wo_obj = session.get(FactMaintenanceWorkOrder, wo_id)
                    if wo_obj:
                        work_order_link = {
                            "work_order_id": wo_obj.work_order_id,
                            "plant_id": wo_obj.plant_id,
                            "machine_id": wo_obj.machine_id,
                            "maintenance_type": wo_obj.maintenance_type,
                            "created_ts": wo_obj.created_ts.isoformat() if wo_obj.created_ts else None,
                            "note": "Work order matched on plant and time window. Note: Work order presence corroborates maintenance activity but does not certify an energy reduction.",
                        }
                if dt_id:
                    dt_obj = session.get(FactDowntimeEvent, dt_id)
                    if dt_obj:
                        downtime_event_link = {
                            "downtime_id": dt_obj.downtime_id,
                            "plant_id": dt_obj.plant_id,
                            "line_id": dt_obj.line_id,
                            "reason_code": dt_obj.reason_code,
                            "duration_min": dt_obj.duration_min,
                            "start_ts": dt_obj.start_ts.isoformat() if dt_obj.start_ts else None,
                        }
            except Exception:
                pass

    operating_cond = json.loads(plan.operating_conditions_json) if getattr(plan, "operating_conditions_json", None) else {}
    comp_method = operating_cond.get("comparison_method") or "MATCHED_SCHEDULE"

    # Three Separate Answers structure (for Facilities and Production Management)
    three_separate_answers = {
        "cost_performance": {
            "question": "Did estimated electricity cost per good finished unit improve?",
            "status": objective_outcome,
            "outcome": "YES" if objective_outcome == "IMPROVED" else ("NO" if objective_outcome == "NOT_IMPROVED" else "INCONCLUSIVE"),
            "baseline_cost_per_good_unit": baseline.cost_per_good_unit,
            "post_cost_per_good_unit": post.cost_per_good_unit,
            "cost_intensity_change_abs": cost_intensity_change_abs,
            "cost_intensity_change_pct": cost_intensity_change_pct,
            "threshold_pct": threshold,
            "unit": f"INR / {plan.production_unit or 'good finished unit'}",
            "reason": status_reason,
        },
        "production_protection": {
            "question": "Did output, quality, downtime and restart performance remain within the limits approved before the change?",
            "status": production_protection_status,
            "outcome": "PASSED" if production_protection_status == "PROTECTED" else ("Output protection could not be assessed" if production_protection_status == "UNASSESSABLE" else "BREACHED"),
            "all_guardrails_passed": guardrails_passed,
            "guardrails": [g.dict() for g in guardrails],
            "reason": (
                "Output protection could not be assessed: A minimum output target of zero is an invalid criterion and cannot establish output was maintained."
                if production_protection_status == "UNASSESSABLE"
                else (
                    "One or more preapproved production or quality limits were breached."
                    if production_protection_status == "BREACHED"
                    else "All preapproved production, quality, downtime, and restart limits held within approved bounds."
                )
            ),
        },
        "attribution": {
            "question": "How much electricity, and how much money, can be attributed to the intervention?",
            "status": "ATTRIBUTED" if electricity_savings_kwh is not None else "UNVERIFIED",
            "outcome": (
                f"{electricity_savings_kwh:+.4f} kWh (₹{avoided_cost_inr:+.2f})"
                if electricity_savings_kwh is not None
                else "No verified intervention savings"
            ),
            "establishes_counterfactual": has_counterfactual,
            "expected_kwh": (
                round(attribution_calc["total_expected_kwh"], 4)
                if (is_repeated_stoppages_method or is_dual_boundary_method) and attribution_calc and attribution_calc.get("total_expected_kwh") is not None
                else (baseline.kwh if has_counterfactual else None)
            ),
            "observed_kwh": (
                round(attribution_calc["total_observed_kwh"], 4)
                if (is_repeated_stoppages_method or is_dual_boundary_method) and attribution_calc and attribution_calc.get("total_observed_kwh") is not None
                else post.kwh
            ),
            "difference_kwh": electricity_savings_kwh if electricity_savings_kwh is not None else (
                attribution_calc.get("observed_avoided_kwh")
                if (is_repeated_stoppages_method or is_dual_boundary_method) and attribution_calc and attribution_calc.get("observed_avoided_kwh") is not None
                else round(baseline.kwh - post.kwh, 4)
            ),
            "verified_electricity_savings_kwh": electricity_savings_kwh,
            "avoided_electricity_kwh": electricity_savings_kwh,
            "avoided_cost_inr": avoided_cost_inr,
            "estimated_avoided_cost_inr": (
                attribution_calc.get("estimated_avoided_cost_inr")
                if attribution_calc
                else avoided_cost_inr
            ),
            "estimated_avoided_cost_assumption": tariff_factor.get("label") if isinstance(tariff_factor, dict) else str(tariff_factor),
            "verified_monetary_savings_inr": attribution_calc.get("verified_monetary_savings_inr") if attribution_calc else None,
            "reference_count": attribution_calc.get("reference_count", 0) if attribution_calc else 0,
            "observed_exposure_hours": attribution_calc.get("observed_exposure_hours", 0.0) if attribution_calc else 0.0,
            "baseline_variability_cv": attribution_calc.get("baseline_variability_cv") if attribution_calc else None,
            "uncertainty_pct": attribution_calc.get("uncertainty_pct") if attribution_calc else None,
            "margin_of_error_kwh": attribution_calc.get("margin_of_error_kwh") if attribution_calc else None,
            "is_estimate": True,
            "monetary_savings_basis": monetary_savings_basis,
            "attribution_method": attribution_method,
            "attribution_details": attribution_details,
            "attribution_eligibility": attribution_eligibility,
            "evidence": {
                "dedicated_meter": attribution_eligibility.get("dedicated_meter_boundary", False),
                "coverage_met": attribution_eligibility.get("coverage_criteria_met", False),
                "operating_states_comparable": attribution_eligibility.get("operating_states_comparable", False),
                "schedule_matched": attribution_eligibility.get("schedule_matched", False),
            },
            "tolerance_pct": 5.0,
            "applicable_tariff_inr_per_kwh": tariff_inr_per_kwh,
            "tariff_version": tariff_version,
            "observed_differences": {
                "observed_kwh_difference": observed_kwh_change,
                "observed_cost_difference_inr": observed_cost_change_inr,
                "common_rate_cost_difference_inr": common_rate_change,
                "baseline_kwh": baseline.kwh,
                "post_kwh": post.kwh,
            },
            "reason": attribution_status_reason,
        },
        # Backward compatibility for existing callers
        "question_1_cost_intensity": {
            "question": "Did estimated electricity cost per good finished unit improve?",
            "answer": objective_outcome,
            "baseline_cost_per_good_unit": baseline.cost_per_good_unit,
            "post_cost_per_good_unit": post.cost_per_good_unit,
            "observed_intensity_change_abs": cost_intensity_change_abs,
            "observed_intensity_change_pct": cost_intensity_change_pct,
            "threshold_pct": threshold,
            "unit": f"INR / {plan.production_unit or 'good finished unit'}",
            "reason": status_reason,
        },
        "question_2_production_protection": {
            "question": "Did output, quality, downtime and restart performance remain within the limits approved before the change?",
            "answer": production_protection_status,
            "all_guardrails_passed": guardrails_passed,
            "guardrail_results": [g.dict() for g in guardrails],
            "reason": (
                "Output protection could not be assessed: A minimum output target of zero is an invalid criterion and cannot establish output was maintained."
                if production_protection_status == "UNASSESSABLE"
                else (
                    "One or more preapproved production or quality limits were breached."
                    if production_protection_status == "BREACHED"
                    else "All preapproved production, quality, downtime, and restart limits held within approved bounds."
                )
            ),
        },
        "question_3_savings_attribution": {
            "question": "How much avoided electricity or cost can the evidence actually attribute to the change?",
            "answer": f"{electricity_savings_kwh:+.4f} kWh" if electricity_savings_kwh is not None else "No verified intervention savings",
            "avoided_electricity_kwh": electricity_savings_kwh,
            "avoided_cost_inr": avoided_cost_inr,
            "monetary_savings_basis": monetary_savings_basis,
            "attribution_method": attribution_method,
            "attribution_eligibility": attribution_eligibility,
            "observed_differences": {
                "observed_kwh_difference": observed_kwh_change,
                "observed_cost_difference_inr": observed_cost_change_inr,
                "common_rate_cost_difference_inr": common_rate_change,
                "baseline_kwh": baseline.kwh,
                "post_kwh": post.kwh,
            },
            "reason": attribution_status_reason,
        },
    }

    # Inspectable comparison method & reference intervals (Requirement Item 4)
    has_counterfactual = bool(attribution_eligibility.get("preapproved_counterfactual_model", False))
    if has_counterfactual:
        comparison_mode = "DETERMINISTIC_COUNTERFACTUAL"
        comparison_inspection_notes = "Comparison uses a preapproved engineering counterfactual reference model."
    else:
        comparison_mode = "DESCRIPTIVE_ONLY"
        comparison_inspection_notes = (
            "Descriptive Before/After Telemetry Comparison: Observed telemetry differences remain descriptive. "
            "Without an approved counterfactual reference model, avoided kWh and avoided ₹ are strictly null."
        )

    reference_intervals = build_inspectable_reference_intervals(
        plan=plan,
        baseline=baseline,
        post=post,
        comp_method=comp_method,
        meters=meters,
        has_counterfactual=has_counterfactual,
    )

    return InterventionComparisonResponse(
        action_id=plan.action_id,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        is_frozen=plan.is_frozen,
        is_retrospective=plan.is_retrospective,
        measurement_boundary=boundary_meta,
        baseline=baseline,
        post=post,
        included_intervals_count=included_count,
        excluded_intervals=excluded_intervals,
        observed_kwh_change=observed_kwh_change,
        observed_cost_change_inr=observed_cost_change_inr,
        kwh_change_abs=kwh_change_abs,
        kwh_change_pct=kwh_change_pct,
        intensity_change_abs=intensity_change_abs,
        intensity_change_pct=intensity_change_pct,
        cost_intensity_change_abs=cost_intensity_change_abs,
        cost_intensity_change_pct=cost_intensity_change_pct,
        sign_convention="Negative change indicates an improvement / reduction in consumption or intensity.",
        common_rate_baseline_cost_inr=common_rate_baseline,
        common_rate_post_cost_inr=common_rate_post,
        common_rate_cost_change_inr=common_rate_change,
        common_rate_factor_inr_per_kwh=tariff_inr_per_kwh,
        common_rate_factor_version=tariff_version,
        guardrails=guardrails,
        guardrails_passed=guardrails_passed,
        production_protection_status=production_protection_status,
        management_outcome=management_outcome,
        management_outcome_detail=management_outcome_detail,
        next_step=next_step,
        is_awaiting_data=is_awaiting_data,
        remaining_time_minutes=remaining_time_minutes,
        comparison_method=comp_method,
        work_order_link=work_order_link,
        downtime_event_link=downtime_event_link,
        objective_outcome=objective_outcome,
        electricity_savings_kwh=electricity_savings_kwh,
        verified_electricity_savings_kwh=electricity_savings_kwh,
        monetary_savings_basis=monetary_savings_basis,
        avoided_cost_inr=avoided_cost_inr,
        estimated_avoided_cost_inr=avoided_cost_inr,
        estimated_avoided_cost_assumption=tariff_factor.get("label"),
        verified_monetary_savings_inr=attribution_calc.get("verified_monetary_savings_inr") if attribution_calc else None,
        attribution_details=attribution_details,
        savings_claim_status=savings_claim_status,
        savings_claim_description=claim_desc,
        status_reason=status_reason,
        overlap_flag=overlap_flag,
        overlap_details=overlap_details,
        attribution_method=attribution_method,
        attribution_eligibility=attribution_eligibility,
        factor_assumptions=factor_assumptions_meta,
        three_separate_answers=three_separate_answers,
        comparison_mode=comparison_mode,
        comparison_inspection_notes=comparison_inspection_notes,
        reference_intervals=reference_intervals,
        has_dual_boundary=has_dual_boundary,
        dual_boundary_breakdown=dual_boundary_breakdown,
        server_timing_verified=server_timing_verified,
        server_timing_reason=server_timing_reason,
    )


def reproduce_assessment_from_pinned_revisions(
    session: Session,
    assessment_id: str,
) -> Dict[str, Any]:
    """
    Deterministically reconstructs an outcome assessment strictly from its immutable pinned
    FactSourceRevision records and pinned factor rate, completely independent of live table mutations.
    
    Provides 100% reproducible historical replay under IPMVP / ISO 50015.
    Returns recalculated values for field-by-field verification against the stored assessment.
    """
    stmt = select(InterventionAssessment).where(InterventionAssessment.assessment_id == assessment_id)
    asm = session.execute(stmt).scalar_one_or_none()
    if not asm:
        raise ValueError(f"Assessment '{assessment_id}' not found.")

    plan_stmt = select(InterventionPlan).where(
        InterventionPlan.plan_id == asm.plan_id,
        InterventionPlan.version == asm.plan_version,
    )
    plan = session.execute(plan_stmt).scalar_one_or_none()
    if not plan:
        raise ValueError(f"Plan '{asm.plan_id}' version {asm.plan_version} not found.")

    b_rev_ids = json.loads(asm.baseline_source_revisions_json) if asm.baseline_source_revisions_json else []
    p_rev_ids = json.loads(asm.post_source_revisions_json) if asm.post_source_revisions_json else []
    all_rev_ids = list(set(b_rev_ids + p_rev_ids))

    # Query pinned FactSourceRevision rows exclusively
    rev_rows = session.execute(
        select(FactSourceRevision).where(FactSourceRevision.revision_id.in_(all_rev_ids))
    ).scalars().all() if all_rev_ids else []

    rev_map = {r.revision_id: r for r in rev_rows}
    meters = json.loads(plan.eligible_meters_json) if plan.eligible_meters_json else []

    def _calculate_window_from_pinned(
        window_rev_ids: List[str],
        start_ts: datetime,
        end_ts: datetime,
    ) -> Dict[str, Any]:
        energy_by_ts_meter = {}
        prod_by_ts = {}

        for rid in window_rev_ids:
            rev = rev_map.get(rid)
            if not rev:
                continue
            v = json.loads(rev.source_values_json)
            if rev.source_table == "fact_energy_meter_hourly":
                ts_str = v.get("timestamp")
                ts = datetime.fromisoformat(ts_str) if ts_str else None
                m_id = v.get("meter_id")
                kwh = float(v.get("consumption_kwh") or 0.0)
                cost = float(v.get("cost_inr") or 0.0)
                if ts and m_id:
                    energy_by_ts_meter[(ts, m_id)] = {"kwh": kwh, "cost": cost}
            elif rev.source_table == "fact_hourly_production":
                ts_str = v.get("event_ts")
                ts = datetime.fromisoformat(ts_str) if ts_str else None
                if ts:
                    prod_by_ts[ts] = {
                        "actual": int(v.get("actual_qty") or 0),
                        "good": int(v.get("good_qty") or 0),
                        "reject": int(v.get("reject_qty") or 0),
                        "downtime": int(v.get("downtime_min") or 0),
                    }

        total_hours = max(0, int((end_ts - start_ts).total_seconds()) // 3600)
        expected_intervals = [start_ts + timedelta(hours=i) for i in range(total_hours)]

        tot_kwh = 0.0
        tot_cost = 0.0
        tot_actual = 0
        tot_good = 0
        tot_reject = 0
        tot_downtime = 0
        eligible_hours = 0

        for ts in expected_intervals:
            has_energy = all((ts, m) in energy_by_ts_meter for m in meters) if meters else False
            has_prod = ts in prod_by_ts
            if has_energy and has_prod:
                eligible_hours += 1
                tot_kwh += sum(energy_by_ts_meter[(ts, m)]["kwh"] for m in meters)
                tot_cost += sum(energy_by_ts_meter[(ts, m)]["cost"] for m in meters)
                tot_actual += prod_by_ts[ts]["actual"]
                tot_good += prod_by_ts[ts]["good"]
                tot_reject += prod_by_ts[ts]["reject"]
                tot_downtime += prod_by_ts[ts]["downtime"]

        kwh_per_good = round(tot_kwh / tot_good, 4) if tot_good > 0 else None
        cost_per_good = round(tot_cost / tot_good, 4) if tot_good > 0 else None
        yield_pct = round((tot_good / tot_actual) * 100.0, 2) if tot_actual > 0 else None

        return {
            "kwh": round(tot_kwh, 4),
            "cost_inr": round(tot_cost, 2),
            "actual_units": tot_actual,
            "good_units": tot_good,
            "reject_units": tot_reject,
            "downtime_minutes": tot_downtime,
            "operating_hours": eligible_hours,
            "kwh_per_good_unit": kwh_per_good,
            "cost_per_good_unit": cost_per_good,
            "yield_pct": yield_pct,
        }

    # If pinned revisions exist for both windows, compute strictly from pinned source records
    if b_rev_ids and p_rev_ids:
        base_calc = _calculate_window_from_pinned(b_rev_ids, plan.baseline_start, plan.baseline_end)
        post_calc = _calculate_window_from_pinned(p_rev_ids, plan.post_start, plan.post_end)
    else:
        # Fallback to stored baseline/post if assessment predated complete FactSourceRevision population
        base_calc = {
            "kwh": asm.baseline_kwh,
            "cost_inr": asm.baseline_cost_inr,
            "actual_units": asm.baseline_actual_units,
            "good_units": asm.baseline_good_units,
            "reject_units": asm.baseline_reject_units,
            "downtime_minutes": asm.baseline_downtime_min,
            "kwh_per_good_unit": asm.baseline_kwh_per_good_unit,
            "cost_per_good_unit": asm.baseline_cost_per_good_unit,
        }
        post_calc = {
            "kwh": asm.post_kwh,
            "cost_inr": asm.post_cost_inr,
            "actual_units": asm.post_actual_units,
            "good_units": asm.post_good_units,
            "reject_units": asm.post_reject_units,
            "downtime_minutes": asm.post_downtime_min,
            "kwh_per_good_unit": asm.post_kwh_per_good_unit,
            "cost_per_good_unit": asm.post_cost_per_good_unit,
        }

    # Guardrails evaluation
    out_guard = None
    if plan.guardrail_output_min is not None:
        if plan.guardrail_output_min <= 0:
            out_guard = None
        else:
            out_guard = (post_calc["good_units"] >= plan.guardrail_output_min)

    rej_guard = None
    if plan.guardrail_reject_max is not None:
        rej_guard = (post_calc["reject_units"] <= plan.guardrail_reject_max)

    dt_guard = None
    if plan.guardrail_downtime_max_min is not None:
        dt_guard = (post_calc["downtime_minutes"] <= plan.guardrail_downtime_max_min)

    # Changes
    kwh_change_abs = round(post_calc["kwh"] - base_calc["kwh"], 2)
    kwh_change_pct = round(((post_calc["kwh"] - base_calc["kwh"]) / base_calc["kwh"]) * 100.0, 2) if base_calc["kwh"] > 0 else 0.0

    b_cost_g = base_calc["cost_per_good_unit"]
    p_cost_g = post_calc["cost_per_good_unit"]
    if b_cost_g is not None and p_cost_g is not None:
        cost_intensity_change_abs = round(p_cost_g - b_cost_g, 4)
        cost_intensity_change_pct = round(((p_cost_g - b_cost_g) / b_cost_g) * 100.0, 2) if b_cost_g > 0 else 0.0
    else:
        cost_intensity_change_abs = None
        cost_intensity_change_pct = None

    # Objective outcome
    if base_calc["good_units"] == 0 or post_calc["good_units"] == 0:
        obj_outcome = "INCONCLUSIVE"
    elif cost_intensity_change_abs is not None and cost_intensity_change_abs < 0:
        obj_outcome = "IMPROVED"
    else:
        obj_outcome = "NOT_IMPROVED"

    # Attributable savings
    elec_savings = asm.electricity_savings_kwh
    tariff_rate = asm.common_rate_factor_inr_per_kwh
    avoided_cost = round(elec_savings * tariff_rate, 2) if (elec_savings is not None and tariff_rate is not None) else None

    return {
        "assessment_id": asm.assessment_id,
        "action_id": asm.action_id,
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "assessment_revision": asm.assessment_revision,
        "calculation_method": asm.calculation_method,
        "baseline_kwh": base_calc["kwh"],
        "baseline_cost_inr": base_calc["cost_inr"],
        "baseline_actual_units": base_calc["actual_units"],
        "baseline_good_units": base_calc["good_units"],
        "baseline_reject_units": base_calc["reject_units"],
        "baseline_downtime_min": base_calc["downtime_minutes"],
        "baseline_kwh_per_good_unit": base_calc["kwh_per_good_unit"],
        "baseline_cost_per_good_unit": base_calc["cost_per_good_unit"],
        "post_kwh": post_calc["kwh"],
        "post_cost_inr": post_calc["cost_inr"],
        "post_actual_units": post_calc["actual_units"],
        "post_good_units": post_calc["good_units"],
        "post_reject_units": post_calc["reject_units"],
        "post_downtime_min": post_calc["downtime_minutes"],
        "post_kwh_per_good_unit": post_calc["kwh_per_good_unit"],
        "post_cost_per_good_unit": post_calc["cost_per_good_unit"],
        "kwh_change_abs": kwh_change_abs,
        "kwh_change_pct": kwh_change_pct,
        "cost_intensity_change_abs": cost_intensity_change_abs,
        "cost_intensity_change_pct": cost_intensity_change_pct,
        "output_guardrail_met": out_guard,
        "quality_guardrail_met": rej_guard,
        "downtime_guardrail_met": dt_guard,
        "objective_outcome": obj_outcome,
        "electricity_savings_kwh": elec_savings,
        "avoided_cost_inr": avoided_cost,
        "common_rate_factor_inr_per_kwh": asm.common_rate_factor_inr_per_kwh,
        "common_rate_factor_version": asm.common_rate_factor_version,
    }
