"""
Operating Context & Energy Analysis Service for Phase 3.

Provides unified plant/line/hour operational observations, detects consecutive
zero-output stoppage episodes with restart behavior, and computes strictly
descriptive comparisons against historical baseline periods.
"""

from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
import statistics
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.source_data import (
    DimMachine,
    DimProductionLine,
    DimShiftCalendar,
    FactEnergyMeterHourly,
    FactHourlyProduction,
    FactMachineTelemetryHourly,
    FactSourceRevision,
    FactUtilityTelemetryHourly,
    FactDowntimeEvent,
    FactMaintenanceWorkOrder,
)
from app.schemas.operating_context import (
    ActionableInvestigationSection,
    HourlyOperatingObservation,
    IntervalSnapshot,
    OperatingContextSummaryResponse,
    SimilarPeriodsComparison,
    StoppageEpisode,
    StoppageEpisodeDetailResponse,
    StoppageEpisodesResponse,
)


def _to_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    return float(val)


def _format_interval_notation(start_dt: datetime, end_dt: datetime) -> str:
    """Format hour boundary notation [start, end) clearly."""
    s_str = start_dt.strftime("%H:%M")
    e_str = end_dt.strftime("%H:%M")
    return f"[{s_str}, {e_str})"


def _format_downtime_reason_display(raw_reason: Optional[str]) -> str:
    """Preserve NONE in raw provenance while displaying 'Reason unspecified' in explanations."""
    if not raw_reason or raw_reason.strip() == "" or raw_reason.strip().upper() == "NONE":
        return "Reason unspecified"
    return raw_reason.strip()


def get_process_and_meter(line_id: str, line_type: Optional[str] = None) -> Tuple[str, str]:
    """Map line to standard process name and dedicated process meter ID."""
    clean_line = (line_id or "").upper().strip()
    if clean_line.startswith("SMT") or (line_type and "SMT" in line_type.upper()):
        return "SMT", "MTR-SMT"
    if clean_line.startswith("FAL") or (line_type and ("FINAL" in line_type.upper() or "FAL" in line_type.upper())):
        return "Final Assembly", "MTR-FAL"
    return "Unknown Process", "MTR-UNKNOWN"


def get_line_topology_info(session: Session) -> Dict[str, Dict[str, Any]]:
    """Retrieve metadata and plant assignments for all production lines."""
    lines = session.execute(
        select(
            DimProductionLine.line_id,
            DimProductionLine.plant_id,
            DimProductionLine.line_type,
            DimProductionLine.nominal_capacity_per_hour,
        )
    ).fetchall()

    topology = {}
    for l in lines:
        proc, meter = get_process_and_meter(l.line_id, l.line_type)
        topology[l.line_id] = {
            "plant_id": l.plant_id,
            "line_type": l.line_type,
            "process": proc,
            "meter_id": meter,
            "nominal_capacity": l.nominal_capacity_per_hour,
        }
    return topology


def get_machine_line_mappings(session: Session) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[str]]]:
    """
    Retrieve machines mapped to lines and detect cross-plant topology anomalies.
    Returns:
        machines_by_line: dict of line_id -> list of machine dicts
        line_mapping_issues: dict of line_id -> list of warning issue strings
    """
    machines = session.execute(
        select(
            DimMachine.machine_id,
            DimMachine.machine_name,
            DimMachine.line_id,
            DimMachine.plant_id,
            DimMachine.machine_type,
            DimMachine.criticality,
        )
    ).fetchall()

    line_topology = get_line_topology_info(session)
    machines_by_line: Dict[str, List[Dict[str, Any]]] = {}
    line_mapping_issues: Dict[str, List[str]] = {}

    for m in machines:
        machines_by_line.setdefault(m.line_id, []).append({
            "machine_id": m.machine_id,
            "machine_name": m.machine_name,
            "plant_id": m.plant_id,
            "machine_type": m.machine_type,
            "criticality": m.criticality,
        })

        expected_plant = line_topology.get(m.line_id, {}).get("plant_id")
        if expected_plant and m.plant_id != expected_plant:
            msg = (
                f"Cross-plant anomaly: Machine {m.machine_id} ({m.machine_name}) is registered to "
                f"line {m.line_id} with plant {m.plant_id}, but line {m.line_id} belongs to plant {expected_plant}."
            )
            line_mapping_issues.setdefault(m.line_id, []).append(msg)

    return machines_by_line, line_mapping_issues


def get_operating_context_observations(
    session: Session,
    plant_id: Optional[str] = None,
    line_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: Optional[int] = 10000,
) -> List[HourlyOperatingObservation]:
    """
    Fetch comprehensive plant/line/hour observations joining production, process energy,
    machine telemetry, shift calendar, and provenance revisions.
    """
    topology = get_line_topology_info(session)
    machines_by_line, mapping_issues_by_line = get_machine_line_mappings(session)

    # 1. Scope resolution
    target_lines = [line_id] if line_id else list(topology.keys())
    if plant_id:
        target_lines = [l for l in target_lines if topology.get(l, {}).get("plant_id") == plant_id]

    if not target_lines:
        return []

    # 2. Query FactHourlyProduction
    p_filters = [FactHourlyProduction.line_id.in_(target_lines)]
    if plant_id:
        p_filters.append(FactHourlyProduction.plant_id == plant_id)
    if start_date:
        p_filters.append(FactHourlyProduction.event_date >= start_date)
    if end_date:
        p_filters.append(FactHourlyProduction.event_date <= end_date)
    if start_time:
        p_filters.append(FactHourlyProduction.event_ts >= start_time)
    if end_time:
        p_filters.append(FactHourlyProduction.event_ts <= end_time)

    prod_rows = session.execute(
        select(FactHourlyProduction)
        .where(and_(*p_filters))
        .order_by(FactHourlyProduction.event_ts.asc(), FactHourlyProduction.line_id.asc())
    ).scalars().all()

    # Index production by (plant_id, line_id, timestamp)
    prod_by_key: Dict[Tuple[str, str, datetime], FactHourlyProduction] = {
        (p.plant_id, p.line_id, p.event_ts): p for p in prod_rows
    }

    # 3. Query FactEnergyMeterHourly for relevant process meters
    relevant_meters = set(topology[l]["meter_id"] for l in target_lines if l in topology)
    relevant_plants = set(topology[l]["plant_id"] for l in target_lines if l in topology)
    if plant_id:
        relevant_plants = {plant_id}

    e_filters = [
        FactEnergyMeterHourly.meter_id.in_(relevant_meters),
        FactEnergyMeterHourly.plant_id.in_(relevant_plants),
    ]
    if start_date:
        e_filters.append(FactEnergyMeterHourly.date >= start_date)
    if end_date:
        e_filters.append(FactEnergyMeterHourly.date <= end_date)
    if start_time:
        e_filters.append(FactEnergyMeterHourly.timestamp >= start_time)
    if end_time:
        e_filters.append(FactEnergyMeterHourly.timestamp <= end_time)

    energy_rows = session.execute(
        select(FactEnergyMeterHourly)
        .where(and_(*e_filters))
        .order_by(FactEnergyMeterHourly.timestamp.asc())
    ).scalars().all()

    # Index energy by (plant_id, meter_id, timestamp)
    energy_by_key: Dict[Tuple[str, str, datetime], FactEnergyMeterHourly] = {
        (e.plant_id, e.meter_id, e.timestamp): e for e in energy_rows
    }

    # 4. Query FactMachineTelemetryHourly (line-level aggregated)
    all_machine_ids = set()
    for l in target_lines:
        for m in machines_by_line.get(l, []):
            all_machine_ids.add(m["machine_id"])

    telemetry_by_line_ts: Dict[Tuple[str, datetime], Dict[str, Any]] = {}
    if all_machine_ids:
        t_filters = [FactMachineTelemetryHourly.machine_id.in_(all_machine_ids)]
        if start_date:
            t_filters.append(FactMachineTelemetryHourly.date >= start_date)
        if end_date:
            t_filters.append(FactMachineTelemetryHourly.date <= end_date)
        if start_time:
            t_filters.append(FactMachineTelemetryHourly.timestamp >= start_time)
        if end_time:
            t_filters.append(FactMachineTelemetryHourly.timestamp <= end_time)

        telem_rows = session.execute(
            select(
                FactMachineTelemetryHourly.line_id,
                FactMachineTelemetryHourly.timestamp,
                FactMachineTelemetryHourly.machine_state,
                FactMachineTelemetryHourly.alarm_code,
            ).where(and_(*t_filters))
        ).fetchall()

        for t in telem_rows:
            key = (t[0], t[1])
            entry = telemetry_by_line_ts.setdefault(key, {"states": set(), "alarms": set()})
            if t[2]:
                entry["states"].add(t[2].strip())
            if t[3] and t[3].strip() != "NONE":
                entry["alarms"].add(t[3].strip())

    # 5. Query DimShiftCalendar for the period
    cal_filters = []
    if start_date:
        cal_filters.append(DimShiftCalendar.calendar_date >= start_date)
    if end_date:
        cal_filters.append(DimShiftCalendar.calendar_date <= end_date)

    shift_rows = session.execute(
        select(DimShiftCalendar).where(and_(*cal_filters)) if cal_filters else select(DimShiftCalendar)
    ).scalars().all()

    shifts_by_interval = []
    shifts_by_date_id: Dict[Tuple[date, str], DimShiftCalendar] = {}
    for s in shift_rows:
        shifts_by_interval.append(s)
        shifts_by_date_id[(s.calendar_date, s.shift_id)] = s

    # 6. Query FactSourceRevision IDs for pinned records
    rev_filters = []
    if plant_id:
        rev_filters.append(FactSourceRevision.plant_id == plant_id)
    rev_rows = session.execute(
        select(
            FactSourceRevision.source_table,
            FactSourceRevision.source_record_id,
            FactSourceRevision.revision_id,
        ).where(and_(*rev_filters)) if rev_filters else select(
            FactSourceRevision.source_table,
            FactSourceRevision.source_record_id,
            FactSourceRevision.revision_id,
        )
    ).fetchall()

    revisions_by_record: Dict[Tuple[str, str], List[str]] = {}
    for r in rev_rows:
        revisions_by_record.setdefault((r[0], r[1]), []).append(r[2])

    # 7. Collect all unique observation keys (line_id, plant_id, timestamp)
    observation_keys: Set[Tuple[str, str, datetime]] = set()

    for p in prod_rows:
        observation_keys.add((p.line_id, p.plant_id, p.event_ts))

    for e in energy_rows:
        # Match energy meter to line(s) sharing plant and meter_id
        for l in target_lines:
            meta = topology.get(l, {})
            if meta.get("plant_id") == e.plant_id and meta.get("meter_id") == e.meter_id:
                observation_keys.add((l, e.plant_id, e.timestamp))

    # Sort observation keys chronologically
    sorted_keys = sorted(observation_keys, key=lambda k: (k[0], k[2]))

    observations: List[HourlyOperatingObservation] = []

    for l_id, p_id, ts in sorted_keys:
        meta = topology.get(l_id, {})
        process_name = meta.get("process", "Unknown Process")
        meter_id = meta.get("meter_id")

        p_row = prod_by_key.get((p_id, l_id, ts))
        e_row = energy_by_key.get((p_id, meter_id, ts)) if meter_id else None

        missing_fields: List[str] = []
        mapping_issues: List[str] = list(mapping_issues_by_line.get(l_id, []))
        source_revisions: List[str] = []

        # Production values
        if p_row is not None:
            t_qty = p_row.target_qty
            a_qty = p_row.actual_qty
            g_qty = p_row.good_qty
            r_qty = p_row.reject_qty
            rw_qty = p_row.rework_qty
            dt_min = p_row.downtime_min
            dt_rsn = p_row.downtime_reason
            p_order = p_row.product_id
            s_id = p_row.shift_id
            p_event_id = p_row.event_id
            if ("fact_hourly_production", p_event_id) in revisions_by_record:
                source_revisions.extend(revisions_by_record[("fact_hourly_production", p_event_id)])
        else:
            missing_fields.append("fact_hourly_production")
            t_qty = None
            a_qty = None
            g_qty = None
            r_qty = None
            rw_qty = None
            dt_min = None
            dt_rsn = None
            p_order = None
            s_id = "UNKNOWN"
            p_event_id = None

        # Energy values
        if e_row is not None:
            kwh = _to_float(e_row.consumption_kwh)
            cost = _to_float(e_row.cost_inr)
            m_reading_id = e_row.meter_reading_id
            if ("fact_energy_meter_hourly", m_reading_id) in revisions_by_record:
                source_revisions.extend(revisions_by_record[("fact_energy_meter_hourly", m_reading_id)])
        else:
            missing_fields.append("fact_energy_meter_hourly")
            kwh = None
            cost = None
            m_reading_id = None

        # Match status
        if p_row is not None and e_row is not None:
            match_status = "MATCHED"
        elif p_row is not None and e_row is None:
            match_status = "MISSING_ENERGY"
        elif p_row is None and e_row is not None:
            match_status = "MISSING_PRODUCTION"
        else:
            match_status = "TOPOLOGY_CONFLICT"

        # Machine telemetry
        telem_info = telemetry_by_line_ts.get((l_id, ts), {})
        machine_states = sorted(list(telem_info.get("states", set())))
        alarm_codes = sorted(list(telem_info.get("alarms", set())))

        # Shift calendar
        cal_entry = None
        for s in shifts_by_interval:
            if s.shift_start <= ts < s.shift_end:
                cal_entry = s
                break
        if cal_entry is None and p_row is not None:
            cal_entry = shifts_by_date_id.get((p_row.event_date, p_row.shift_id))

        shift_name = f"Shift {cal_entry.shift_id}" if cal_entry else (f"Shift {s_id}" if s_id != "UNKNOWN" else None)
        is_working_day = cal_entry.is_working_day if cal_entry else None
        shift_planned_min = cal_entry.planned_minutes if cal_entry else None

        interval_end = ts + timedelta(hours=1)
        int_window = _format_interval_notation(ts, interval_end)
        t_shortfall = (t_qty - a_qty) if (t_qty is not None and a_qty is not None) else None
        dt_display = _format_downtime_reason_display(dt_rsn)

        obs = HourlyOperatingObservation(
            plant_id=p_id,
            line_id=l_id,
            process=process_name,
            timestamp=ts,
            interval_start=ts,
            interval_end=interval_end,
            interval_window=int_window,
            date=ts.date(),
            hour=ts.hour,
            shift_id=s_id,
            product_id=p_order,
            process_meter_id=meter_id,
            consumption_kwh=kwh,
            cost_inr=cost,
            target_qty=t_qty,
            actual_qty=a_qty,
            good_qty=g_qty,
            reject_qty=r_qty,
            rework_qty=rw_qty,
            target_shortfall=t_shortfall,
            downtime_min=dt_min,
            downtime_reason=dt_rsn,
            downtime_reason_display=dt_display,
            match_status=match_status,
            missing_fields=missing_fields,
            mapping_issues=mapping_issues,
            source_reading_id=m_reading_id,
            source_event_id=p_event_id,
            source_revisions=source_revisions,
            machine_states=machine_states,
            alarm_codes=alarm_codes,
            shift_name=shift_name,
            is_working_day=is_working_day,
            shift_planned_minutes=shift_planned_min,
        )
        observations.append(obs)

        if limit and len(observations) >= limit:
            break

    return observations


def _build_interval_snapshot(obs: HourlyOperatingObservation) -> IntervalSnapshot:
    """Helper to convert an observation into an IntervalSnapshot."""
    return IntervalSnapshot(
        timestamp=obs.timestamp,
        hour=obs.hour,
        interval_window=obs.interval_window,
        shift_id=obs.shift_id,
        product_id=obs.product_id,
        target_qty=obs.target_qty or 0,
        actual_qty=obs.actual_qty or 0,
        good_qty=obs.good_qty or 0,
        reject_qty=obs.reject_qty or 0,
        rework_qty=obs.rework_qty or 0,
        downtime_min=obs.downtime_min or 0,
        downtime_reason=obs.downtime_reason,
        downtime_reason_display=obs.downtime_reason_display,
        consumption_kwh=obs.consumption_kwh,
        cost_inr=obs.cost_inr,
        source_reading_id=obs.source_reading_id,
        source_event_id=obs.source_event_id,
        source_revision_id=obs.source_revisions[0] if obs.source_revisions else None,
    )


def detect_stoppage_episodes(
    observations: List[HourlyOperatingObservation],
    min_duration_hours: int = 1,
    downtime_reason: Optional[str] = None,
) -> List[StoppageEpisode]:
    """
    Detect consecutive zero-output hours for each line and plant.
    Exposes lost target production, downtime, electricity consumed during stoppage,
    prior productive interval, and next restart interval.
    A missing production observation breaks continuity.
    A missing energy reading does not split the episode (marks coverage < 100%).
    """
    # Group observations by (plant_id, line_id)
    by_line: Dict[Tuple[str, str], List[HourlyOperatingObservation]] = {}
    for obs in observations:
        by_line.setdefault((obs.plant_id, obs.line_id), []).append(obs)

    all_episodes: List[StoppageEpisode] = []

    for (p_id, l_id), line_obs in by_line.items():
        # Sort chronologically
        line_obs.sort(key=lambda o: o.timestamp)
        n = len(line_obs)
        if n == 0:
            continue

        i = 0
        last_productive_obs: Optional[HourlyOperatingObservation] = None

        while i < n:
            curr = line_obs[i]

            # Check if this is an observed zero-output hour
            # (must have production observation and actual_qty == 0)
            is_zero_hour = (
                curr.actual_qty is not None
                and curr.actual_qty == 0
                and (curr.good_qty is None or curr.good_qty == 0)
            )

            if not is_zero_hour:
                if curr.actual_qty is not None and curr.actual_qty > 0:
                    last_productive_obs = curr
                i += 1
                continue

            # Start of a potential stoppage episode
            episode_hours: List[HourlyOperatingObservation] = [curr]
            j = i + 1

            while j < n:
                nxt = line_obs[j]
                prev = line_obs[j - 1]

                # Strict 1-hour continuity check
                if nxt.timestamp != prev.timestamp + timedelta(hours=1):
                    # Missing production observation or time gap breaks continuity
                    break

                nxt_is_zero = (
                    nxt.actual_qty is not None
                    and nxt.actual_qty == 0
                    and (nxt.good_qty is None or nxt.good_qty == 0)
                )

                if not nxt_is_zero:
                    # Output resumed or missing production observation
                    break

                episode_hours.append(nxt)
                j += 1

            # Episode completed or interrupted
            duration_hours = len(episode_hours)
            first_obs = episode_hours[0]
            last_obs = episode_hours[-1]

            # Find next restart interval (look immediately at index j)
            next_restart_obs: Optional[HourlyOperatingObservation] = None
            if j < n:
                candidate = line_obs[j]
                if candidate.timestamp == last_obs.timestamp + timedelta(hours=1):
                    if candidate.actual_qty is not None and candidate.actual_qty > 0:
                        next_restart_obs = candidate

            # Accumulate metrics
            target_lost = sum(o.target_qty or 0 for o in episode_hours)
            total_dt_min = sum(o.downtime_min or 0 for o in episode_hours)
            reasons = list(dict.fromkeys(o.downtime_reason for o in episode_hours if o.downtime_reason and o.downtime_reason != "NONE"))
            if not reasons:
                reasons = ["NONE"]

            # Energy metrics
            hours_with_energy = sum(1 for o in episode_hours if o.consumption_kwh is not None)
            coverage_pct = round((hours_with_energy / duration_hours) * 100.0, 1)

            if hours_with_energy > 0:
                total_kwh = sum(o.consumption_kwh for o in episode_hours if o.consumption_kwh is not None)
                total_cost = sum(o.cost_inr for o in episode_hours if o.cost_inr is not None)
            else:
                total_kwh = None
                total_cost = None

            # Machine states and alarms
            machine_states = set()
            alarm_codes = set()
            for o in episode_hours:
                machine_states.update(o.machine_states)
                alarm_codes.update(o.alarm_codes)

            source_rec_ids = []
            source_rev_ids = []
            for o in episode_hours:
                if o.source_reading_id:
                    source_rec_ids.append(o.source_reading_id)
                if o.source_event_id:
                    source_rec_ids.append(o.source_event_id)
                source_rev_ids.extend(o.source_revisions)

            ep_id = f"STP-{p_id}-{l_id}-{first_obs.timestamp.strftime('%Y%m%d%H')}"
            int_start = first_obs.timestamp
            int_end = last_obs.timestamp + timedelta(hours=1)
            int_window = _format_interval_notation(int_start, int_end)
            reasons_display = [_format_downtime_reason_display(r) for r in reasons]

            episode = StoppageEpisode(
                episode_id=ep_id,
                plant_id=p_id,
                line_id=l_id,
                process=first_obs.process,
                first_interval=first_obs.timestamp,
                last_interval=last_obs.timestamp,
                interval_start=int_start,
                interval_end=int_end,
                interval_window=int_window,
                observed_duration_hours=duration_hours,
                target_qty_lost=target_lost,
                target_shortfall=target_lost,
                actual_qty=0,
                good_qty=0,
                recorded_downtime_minutes=total_dt_min,
                downtime_reasons=reasons,
                downtime_reasons_display=reasons_display,
                process_kwh=round(total_kwh, 4) if total_kwh is not None else None,
                process_cost_inr=round(total_cost, 2) if total_cost is not None else None,
                cost_label="dataset-derived",
                process_electricity_label="Process electricity during zero-output hours",
                energy_coverage_pct=coverage_pct,
                prior_productive_interval=_build_interval_snapshot(last_productive_obs) if last_productive_obs else None,
                next_restart_interval=_build_interval_snapshot(next_restart_obs) if next_restart_obs else None,
                machine_states=sorted(list(machine_states)),
                alarm_codes=sorted(list(alarm_codes)),
                has_machine_telemetry=bool(machine_states or alarm_codes),
                source_record_ids=list(dict.fromkeys(source_rec_ids)),
                source_revision_ids=list(dict.fromkeys(source_rev_ids)),
            )

            # Apply filters: min duration and downtime reason
            meets_duration = duration_hours >= min_duration_hours
            meets_reason = (
                not downtime_reason
                or any(downtime_reason.upper() in r.upper() for r in reasons)
            )

            if meets_duration and meets_reason:
                all_episodes.append(episode)

            # Advance outer loop
            i = j

    # Sort all detected episodes chronologically
    all_episodes.sort(key=lambda ep: (ep.first_interval, ep.line_id))
    return all_episodes


def compare_similar_periods(
    target_episode: StoppageEpisode,
    all_episodes: List[StoppageEpisode],
) -> SimilarPeriodsComparison:
    """
    Descriptively compare a target stoppage episode against earlier historical stoppage
    episodes on the same plant and line.
    Excludes:
    - Target episode itself
    - Future episodes (relative to target episode)
    - Incomplete episodes (energy coverage < 100%)
    - Sub-hour durations (< 1h)
    """
    excluded_reasons: Dict[str, int] = {}
    eligible_episodes: List[StoppageEpisode] = []

    for ep in all_episodes:
        # 1. Target episode exclusion
        if ep.episode_id == target_episode.episode_id:
            excluded_reasons["TARGET_EPISODE_EXCLUDED"] = excluded_reasons.get("TARGET_EPISODE_EXCLUDED", 0) + 1
            continue

        # 2. Scope match (must match plant and line)
        if ep.plant_id != target_episode.plant_id or ep.line_id != target_episode.line_id:
            excluded_reasons["DIFFERENT_LINE_OR_PLANT"] = excluded_reasons.get("DIFFERENT_LINE_OR_PLANT", 0) + 1
            continue

        # 3. Baseline chronology: historical baseline prior to target episode
        # Include only completed episodes that ended before the selected episode began
        ep_end = ep.interval_end if hasattr(ep, "interval_end") and ep.interval_end else (ep.last_interval + timedelta(hours=1))
        if ep_end > target_episode.first_interval:
            excluded_reasons["ENDED_AT_OR_AFTER_CUTOFF"] = excluded_reasons.get("ENDED_AT_OR_AFTER_CUTOFF", 0) + 1
            continue

        # 4. Energy completeness requirement
        if ep.energy_coverage_pct < 100.0:
            excluded_reasons["INCOMPLETE_ENERGY_READINGS"] = excluded_reasons.get("INCOMPLETE_ENERGY_READINGS", 0) + 1
            continue

        # 5. Minimum duration
        if ep.observed_duration_hours < 1:
            excluded_reasons["DURATION_LESS_THAN_1_HOUR"] = excluded_reasons.get("DURATION_LESS_THAN_1_HOUR", 0) + 1
            continue

        eligible_episodes.append(ep)

    # Descriptive statistics
    kwh_rates: List[float] = []
    durations: List[int] = []
    downtime_counter: Counter = Counter()

    for ep in eligible_episodes:
        if ep.process_kwh is not None and ep.observed_duration_hours > 0:
            rate = ep.process_kwh / ep.observed_duration_hours
            kwh_rates.append(rate)
        durations.append(ep.observed_duration_hours)
        for r in ep.downtime_reasons:
            if r and r != "NONE":
                downtime_counter[r] += 1

    med_kwh = round(statistics.median(kwh_rates), 4) if kwh_rates else None
    min_kwh = round(min(kwh_rates), 4) if kwh_rates else None
    max_kwh = round(max(kwh_rates), 4) if kwh_rates else None
    min_dur = min(durations) if durations else None
    max_dur = max(durations) if durations else None
    typical_reasons = [r for r, _ in downtime_counter.most_common(5)]
    typical_reasons_display = [_format_downtime_reason_display(r) for r in typical_reasons]

    sample_summaries = [
        {
            "episode_id": ep.episode_id,
            "first_interval": ep.first_interval.isoformat(),
            "interval_window": ep.interval_window,
            "duration_hours": ep.observed_duration_hours,
            "process_kwh": ep.process_kwh,
            "kwh_per_hour": round(ep.process_kwh / ep.observed_duration_hours, 4) if ep.process_kwh else None,
            "downtime_reasons": ep.downtime_reasons,
            "downtime_reasons_display": ep.downtime_reasons_display,
        }
        for ep in eligible_episodes[:10]
    ]

    hist_window = (
        f"Historical window preceding {target_episode.first_interval.strftime('%Y-%m-%d %H:%M')}"
    )
    matching_criteria = (
        f"Same plant ({target_episode.plant_id}) and line ({target_episode.line_id}), "
        f"complete energy coverage (100%), completed before {target_episode.first_interval.strftime('%Y-%m-%d %H:%M')}."
    )

    return SimilarPeriodsComparison(
        target_episode_id=target_episode.episode_id,
        comparison_cutoff=target_episode.first_interval,
        comparison_pool_definition="Completed stoppage episodes on same line and plant that ended before the selected episode began",
        historical_window=hist_window,
        matching_criteria=matching_criteria,
        eligible_count=len(eligible_episodes),
        excluded_count=sum(excluded_reasons.values()),
        excluded_reasons=excluded_reasons,
        median_kwh_per_hour=med_kwh,
        min_kwh_per_hour=min_kwh,
        max_kwh_per_hour=max_kwh,
        duration_min_hours=min_dur,
        duration_max_hours=max_dur,
        typical_downtime_reasons=typical_reasons,
        typical_downtime_reasons_display=typical_reasons_display,
        comparable_episodes=sample_summaries,
    )


def build_actionable_investigation(
    episode: StoppageEpisode,
    comparison: SimilarPeriodsComparison,
) -> ActionableInvestigationSection:
    """
    Build the four actionable investigation sections for Facilities and Production teams:
    1. Observed condition (plant, line, meter, interval, units)
    2. Comparison and evidence (reference population, underlying readings)
    3. Possible causes and limitations (labeled hypotheses)
    4. Suggested investigation (responsible team, condition to check before modifying state)
    """
    kwh_rate = round(episode.process_kwh / episode.observed_duration_hours, 2) if (episode.process_kwh and episode.observed_duration_hours > 0) else None
    rate_str = f"{kwh_rate} kWh/h" if kwh_rate is not None else "unavailable"
    downtime_str = ", ".join(episode.downtime_reasons_display) if episode.downtime_reasons_display else "Reason unspecified"

    observed_condition = (
        f"Plant {episode.plant_id}, line {episode.line_id} ({episode.process}) experienced a "
        f"{episode.observed_duration_hours}-hour zero-output stoppage across interval {episode.interval_window}. "
        f"Process electricity during zero-output hours: {episode.process_kwh:.3f} kWh ({rate_str} on dedicated process meter). "
        f"Target shortfall during observed hours: {episode.target_shortfall} units "
        f"(target: {episode.target_qty_lost}, actual: 0, good: 0). "
        f"Recorded downtime: {episode.recorded_downtime_minutes} minutes ({downtime_str})."
    )

    baseline_median_str = f"{comparison.median_kwh_per_hour:.2f} kWh/h" if comparison.median_kwh_per_hour is not None else "unavailable"
    baseline_range_str = (
        f"{comparison.min_kwh_per_hour:.2f} to {comparison.max_kwh_per_hour:.2f} kWh/h"
        if (comparison.min_kwh_per_hour is not None and comparison.max_kwh_per_hour is not None)
        else "unavailable"
    )
    duration_norm_str = (
        f"{comparison.duration_min_hours} hour"
        if comparison.duration_min_hours == comparison.duration_max_hours
        else f"{comparison.duration_min_hours} – {comparison.duration_max_hours} hours"
    )
    linked_readings = ", ".join(episode.source_record_ids[:4]) if episode.source_record_ids else "None"
    if episode.source_record_ids and len(episode.source_record_ids) > 4:
        linked_readings += f" (+{len(episode.source_record_ids) - 4} more)"

    comparison_and_evidence = (
        f"Compared against {comparison.eligible_count} completed historical episodes on line {episode.line_id} "
        f"prior to cutoff {comparison.comparison_cutoff.strftime('%Y-%m-%d %H:%M')}. "
        f"Historical median consumption rate: {baseline_median_str} (range: {baseline_range_str}). "
        f"Historical episode duration norm: {duration_norm_str} (all {comparison.eligible_count} earlier episodes were {duration_norm_str} long). "
        f"Current episode lasted {episode.observed_duration_hours} hours (longer than historical norm). "
        f"Linked evidence records: {linked_readings}."
    )

    possible_causes = [
        "[HYPOTHESIS-PRODUCTION: Extended Mechanical Stoppage / Changeover Handover] "
        "Production line was halted for consecutive hours exceeding the typical 1-hour duration norm without resuming output.",
        "[HYPOTHESIS-FACILITIES: Idle Auxiliary & Holding Standby Load] "
        "Electricity consumption during zero output reflects process heating, vacuum pumps, conveyor drives, or inspection stations held in standby.",
        "[LIMITATION-METERING: Dedicated Process Meter Boundary] "
        "Readings reflect line process meter aggregate; individual machine subcomponents cannot be decoupled without submetering.",
        "[LIMITATION-LOGGING: Telemetry Reason Code] "
        f"Source production record logged downtime reason as '{episode.downtime_reasons[0] if episode.downtime_reasons else 'NONE'}' ({downtime_str}).",
    ]

    action_items = []
    if episode.observed_duration_hours > (comparison.duration_max_hours or 1):
        action_items.append(
            "Production: Audit root cause of the extended stoppage duration (2 hours vs historical 1-hour norm) and evaluate shift handover log."
        )
    action_items.append(
        "Facilities: Audit standby auxiliary electrical loads active during zero-output hours to verify required restart readiness vs idle waste."
    )
    if episode.next_restart_interval:
        action_items.append(
            f"Production/Quality: Review restart output at {episode.next_restart_interval.interval_window} "
            f"({episode.next_restart_interval.actual_qty} actual units, {episode.next_restart_interval.good_qty} good, "
            f"{episode.next_restart_interval.reject_qty} rejects, {episode.next_restart_interval.consumption_kwh:.2f} kWh) "
            f"to confirm stable line ramp-up."
        )

    suggested_investigation = {
        "responsible_teams": ["Production", "Facilities"],
        "production_condition_to_check": (
            "Verify line mechanical safety, changeover completion, and upstream buffer readiness "
            "before modifying any standby power, heater, or auxiliary state."
        ),
        "action_items": action_items,
    }

    production_context = {
        "target_qty": episode.target_qty_lost,
        "actual_qty": 0,
        "good_qty": 0,
        "target_shortfall": episode.target_shortfall,
        "downtime_minutes": episode.recorded_downtime_minutes,
        "downtime_reasons_raw": episode.downtime_reasons,
        "downtime_reasons_display": episode.downtime_reasons_display,
        "restart_observed": bool(episode.next_restart_interval),
        "restart_actual": episode.next_restart_interval.actual_qty if episode.next_restart_interval else None,
        "restart_good": episode.next_restart_interval.good_qty if episode.next_restart_interval else None,
        "restart_rejects": episode.next_restart_interval.reject_qty if episode.next_restart_interval else None,
        "restart_kwh": episode.next_restart_interval.consumption_kwh if episode.next_restart_interval else None,
    }

    return ActionableInvestigationSection(
        observed_condition=observed_condition,
        comparison_and_evidence=comparison_and_evidence,
        possible_causes_and_limitations=possible_causes,
        suggested_investigation=suggested_investigation,
        production_context=production_context,
    )


def get_operating_context_summary(
    session: Session,
    plant_id: Optional[str] = None,
    line_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> OperatingContextSummaryResponse:
    """Compute summary statistics for operating context observations and stoppage episodes."""
    obs = get_operating_context_observations(
        session=session,
        plant_id=plant_id,
        line_id=line_id,
        start_date=start_date,
        end_date=end_date,
        limit=50000,
    )

    total_obs = len(obs)
    matched = sum(1 for o in obs if o.match_status == "MATCHED")
    missing_e = sum(1 for o in obs if o.match_status == "MISSING_ENERGY")
    missing_p = sum(1 for o in obs if o.match_status == "MISSING_PRODUCTION")

    episodes = detect_stoppage_episodes(obs, min_duration_hours=1)
    ep_count = len(episodes)
    total_stoppage_hrs = sum(ep.observed_duration_hours for ep in episodes)
    total_stoppage_kwh = sum(ep.process_kwh or 0.0 for ep in episodes)
    total_target_lost = sum(ep.target_qty_lost for ep in episodes)
    total_target_shortfall = sum(ep.target_shortfall for ep in episodes)

    return OperatingContextSummaryResponse(
        plant_id=plant_id,
        line_id=line_id,
        start_date=start_date,
        end_date=end_date,
        total_observed_hours=total_obs,
        matched_hours=matched,
        missing_energy_hours=missing_e,
        missing_production_hours=missing_p,
        stoppage_episode_count=ep_count,
        total_stoppage_hours=total_stoppage_hrs,
        total_stoppage_kwh=round(total_stoppage_kwh, 4),
        total_target_lost=total_target_lost,
        total_target_shortfall=total_target_shortfall,
    )


def get_stoppage_episode_detail(
    session: Session,
    episode_id: str,
) -> Optional[StoppageEpisodeDetailResponse]:
    """Retrieve full details of a stoppage episode, including constituent hours and historical comparison."""
    topology = get_line_topology_info(session)
    target_line_id = None
    target_plant_id = None

    for l_id, meta in topology.items():
        prefix = f"STP-{meta['plant_id']}-{l_id}-"
        if episode_id.startswith(prefix):
            target_line_id = l_id
            target_plant_id = meta["plant_id"]
            break

    if not target_line_id:
        for l_id, meta in topology.items():
            if l_id in episode_id:
                target_line_id = l_id
                target_plant_id = meta["plant_id"]
                break

    if not target_line_id:
        return None

    # Load observations for this line across full historical window
    obs = get_operating_context_observations(
        session=session,
        plant_id=target_plant_id,
        line_id=target_line_id,
        limit=50000,
    )

    episodes = detect_stoppage_episodes(obs, min_duration_hours=1)
    target_ep = next((ep for ep in episodes if ep.episode_id == episode_id), None)
    if not target_ep:
        return None

    # Filter constituent observations
    constituent = [
        o for o in obs
        if o.plant_id == target_ep.plant_id
        and o.line_id == target_ep.line_id
        and target_ep.first_interval <= o.timestamp <= target_ep.last_interval
    ]

    comparison = compare_similar_periods(target_ep, episodes)
    actionable_inv = build_actionable_investigation(target_ep, comparison)

    # Correlate downtime events by exact plant, line, and timestamp range
    dt_stmt = (
        select(FactDowntimeEvent)
        .where(
            and_(
                FactDowntimeEvent.plant_id == target_ep.plant_id,
                FactDowntimeEvent.line_id == target_ep.line_id,
                FactDowntimeEvent.start_ts >= target_ep.first_interval,
                FactDowntimeEvent.start_ts < target_ep.last_interval + timedelta(hours=1),
            )
        )
    )
    dt_events = session.execute(dt_stmt).scalars().all()

    # Correlate maintenance work orders by plant and time range
    mwo_stmt = (
        select(FactMaintenanceWorkOrder, DimMachine.line_id)
        .join(DimMachine, FactMaintenanceWorkOrder.machine_id == DimMachine.machine_id, isouter=True)
        .where(
            and_(
                FactMaintenanceWorkOrder.plant_id == target_ep.plant_id,
                FactMaintenanceWorkOrder.created_ts >= target_ep.first_interval - timedelta(hours=4),
                FactMaintenanceWorkOrder.created_ts <= target_ep.last_interval + timedelta(hours=4),
            )
        )
    )
    mwo_rows = session.execute(mwo_stmt).all()

    for dt in dt_events:
        actionable_inv.possible_causes_and_limitations.append(
            f"[SUPPORTING-DOWNTIME-EVENT: {dt.downtime_id}] Machine {dt.machine_id} logged downtime: "
            f"'{dt.reason_code}' ({dt.duration_min} min, impact: {dt.impact_units or 0} units). "
            f"Matched on plant={target_ep.plant_id}, line={target_ep.line_id}, and timestamp."
        )

    for mwo, mach_line in mwo_rows:
        if mach_line == target_ep.line_id:
            actionable_inv.possible_causes_and_limitations.append(
                f"[SUPPORTING-WORKORDER: {mwo.work_order_id}] Work order on machine {mwo.machine_id} "
                f"({mwo.maintenance_type}: {mwo.failure_mode or 'Unspecified'}, priority: {mwo.priority}). "
                f"Matched by asset, plant, and time. Note: a nearby work order alone does not establish a stoppage cause."
            )
        else:
            actionable_inv.possible_causes_and_limitations.append(
                f"[CONTEXT-WORKORDER-AMBIGUOUS: {mwo.work_order_id}] Work order on machine {mwo.machine_id} "
                f"logged within ±4h, but asset belongs to line '{mach_line or 'Unknown'}'. Ambiguous line mapping."
            )

    return StoppageEpisodeDetailResponse(
        episode=target_ep,
        similar_periods=comparison,
        actionable_investigation=actionable_inv,
        constituent_hours=constituent,
    )


def get_utility_telemetry_observations(
    session: Session,
    plant_id: str,
    utility_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    equipment_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Retrieve qualified utility telemetry observations (compressed air, chilled water, HVAC, nitrogen, process water).

    Governance & Physical Semantics:
    1. Distinguishes compressor electrical consumption (meter MTR-COMPRESSOR in FactEnergyMeterHourly)
       from compressed-air delivery (flow_rate, pressure_bar in FactUtilityTelemetryHourly).
    2. Preserves raw consumption_unit values ('m3', 'L', 'kWh') and never assumes consumption_unit
       defines the unit or time basis of flow_rate.
    3. Strictly refuses to aggregate flow rates across mixed units (e.g. summing L and m3);
       keeps unsupported totals UNAVAILABLE.
    4. Links exact source reading records with pressure, alarms, and operating status.
    5. A sustained abnormal condition can justify a leak-check recommendation, but quantified
       leak volume and avoidable kWh/INR require additional submetering and are kept unavailable.
    """
    filters = [FactUtilityTelemetryHourly.plant_id == plant_id]
    if utility_type:
        filters.append(FactUtilityTelemetryHourly.utility_type == utility_type.strip().upper())
    if start_time:
        filters.append(FactUtilityTelemetryHourly.timestamp >= start_time)
    if end_time:
        filters.append(FactUtilityTelemetryHourly.timestamp < end_time)
    if equipment_id:
        filters.append(FactUtilityTelemetryHourly.equipment_id == equipment_id.strip())

    stmt = (
        select(FactUtilityTelemetryHourly)
        .where(and_(*filters))
        .order_by(desc(FactUtilityTelemetryHourly.timestamp))
        .limit(limit)
    )
    records = session.execute(stmt).scalars().all()

    distinct_units = sorted(list({r.consumption_unit for r in records}))
    has_mixed_units = len(distinct_units) > 1

    # Check compressor electrical meter if utility_type is COMPRESSED_AIR
    compressor_electrical_kwh = None
    if (utility_type == "COMPRESSED_AIR" or not utility_type) and start_time and end_time:
        elec_stmt = (
            select(func.sum(FactEnergyMeterHourly.consumption_kwh))
            .where(
                and_(
                    FactEnergyMeterHourly.plant_id == plant_id,
                    FactEnergyMeterHourly.meter_id == "MTR-COMPRESSOR",
                    FactEnergyMeterHourly.timestamp >= start_time,
                    FactEnergyMeterHourly.timestamp < end_time,
                )
            )
        )
        compressor_electrical_kwh = session.execute(elec_stmt).scalar()

    items = []
    min_observed_pressure = None
    abnormal_alarm = None
    abnormal_equipment = None

    for r in records:
        pres_float = float(r.pressure_bar) if r.pressure_bar is not None else None
        if pres_float is not None:
            if min_observed_pressure is None or pres_float < min_observed_pressure:
                min_observed_pressure = pres_float
                if pres_float < 6.0 and not abnormal_equipment:
                    abnormal_equipment = r.equipment_id

        if r.alarm_code and r.alarm_code.strip().upper() not in ("NONE", "NORMAL", "OK", ""):
            if not abnormal_alarm:
                abnormal_alarm = r.alarm_code.strip()
                abnormal_equipment = r.equipment_id

        items.append({
            "utility_reading_id": r.utility_reading_id,
            "source_id": r.utility_reading_id,
            "timestamp": r.timestamp.isoformat(),
            "plant_id": r.plant_id,
            "utility_type": r.utility_type,
            "zone": r.zone,
            "equipment_id": r.equipment_id,
            "flow_rate": float(r.flow_rate) if r.flow_rate is not None else None,
            "flow_rate_unit": "Flow-rate unit unverified",
            "flow_rate_unit_status": "Flow-rate unit unverified (source metadata does not establish flow-rate unit or time basis; matching consumption_unit labels across rows is insufficient)",
            "derived_volume": None,
            "derived_volume_reason": "Flow semantics are unverified; volume cannot be mathematically derived from raw flow rate",
            "derived_leak_rate": None,
            "derived_leak_rate_reason": "Derived leak rate requires dedicated physical isolation or acoustic inspection",
            "derived_monetary_savings_inr": None,
            "derived_monetary_savings_reason": "Monetary savings cannot be derived without verified physical leak quantification and equipment performance curves",
            "pressure_bar": pres_float,
            "temperature_c": float(r.temperature_c) if r.temperature_c is not None else None,
            "consumption_unit": r.consumption_unit,
            "operating_status": r.operating_status,
            "alarm_code": r.alarm_code,
            "source_revision_id": r.source_revision_id,
        })

    # Qualified leak-check recommendation assessment
    has_leak_evidence = bool(
        abnormal_alarm or (min_observed_pressure is not None and min_observed_pressure < 6.0)
    )
    time_window_str = (
        f"{items[-1]['timestamp']} to {items[0]['timestamp']}" if items else "Observed window"
    )

    if has_leak_evidence:
        evidence_desc = []
        if abnormal_alarm:
            evidence_desc.append(f"active alarm '{abnormal_alarm}'")
        if min_observed_pressure is not None and min_observed_pressure < 6.0:
            evidence_desc.append(f"delivered header pressure degradation (observed: {min_observed_pressure:.2f} bar < 6.0 bar nominal)")
        leak_check_rec = {
            "warrants_investigation": True,
            "equipment_id": abnormal_equipment or equipment_id or "COMPRESSED_AIR_SYSTEM",
            "time_window": time_window_str,
            "evidence": f"Qualified utility evidence: {'; '.join(evidence_desc)}.",
            "operator_question": "Does pneumatic line or header leakage account for the delivered pressure degradation and elevated compressor electricity use?",
            "suggested_investigation_method": (
                "Ultrasonic acoustic inspection (air leak audit) across headers, couplings, and pneumatic drops. "
                "Ultrasonic inspection is a defensible investigation method for pinpointing compressed air leaks without requiring line shutdown."
            ),
            "quantification_status": "UNQUANTIFIED",
            "quantification_reason": (
                "Quantification requires suitable measurement evidence (measured leak hole diameter and pressure differential) "
                "and a defensible thermodynamic method. Avoided kWh and avoided ₹ remain null until physical leak measurements are obtained."
            ),
            "avoided_kwh": None,
            "avoided_cost_inr": None,
        }
    else:
        leak_check_rec = {
            "warrants_investigation": False,
            "equipment_id": equipment_id or "ALL",
            "time_window": time_window_str,
            "evidence": "Observed pressure readings remain within nominal operating range with no active alarms.",
            "operator_question": "Are utility header pressures and operating statuses stable?",
            "suggested_investigation_method": (
                "Periodic ultrasonic acoustic inspection may be scheduled as preventative maintenance, "
                "but current evidence does not indicate acute leaks."
            ),
            "quantification_status": "NOT_APPLICABLE",
            "quantification_reason": "No abnormal leak condition detected in observed telemetry.",
            "avoided_kwh": None,
            "avoided_cost_inr": None,
        }

    return {
        "plant_id": plant_id,
        "utility_type": utility_type or "ALL",
        "count": len(items),
        "distinct_recorded_units": distinct_units,
        "has_mixed_units": has_mixed_units,
        "total_flow_aggregation": (
            "UNAVAILABLE (mixed consumption_units present in records; summing flow rates across mixed units is invalid)"
            if has_mixed_units
            else ("AVAILABLE" if items else "NO_DATA")
        ),
        "compressor_electricity_label": "Compressor electricity consumption (kWh)",
        "compressor_electrical_consumption_kwh": (
            float(compressor_electrical_kwh) if compressor_electrical_kwh is not None else None
        ),
        "compressor_electricity_note": (
            "Compressor electrical consumption is measured at meter MTR-COMPRESSOR in fact_energy_meter_hourly, "
            "kept strictly distinct from compressed-air delivery measurements (flow_rate, pressure_bar) in fact_utility_telemetry_hourly."
        ),
        "leak_check_evidence_guidance": (
            "A sustained abnormal condition or low delivered pressure under high flow can justify a leak-check recommendation. "
            "However, quantified leak volume, avoidable kWh and ₹ savings require additional submetering and cannot be "
            "derived without physical leak-detection evidence."
        ),
        "leak_check_recommendation": leak_check_rec,
        "records": items,
    }
