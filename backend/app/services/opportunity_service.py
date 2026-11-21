"""
Energy-Saving Opportunities Service.

Identifies, scores, and prioritizes operational energy-saving opportunities
for a selected plant and reporting date following daily pipeline execution.
Surfaces actionable trial candidates (e.g. standby shutdown, power factor, baseload)
and evidence-gathering opportunities (when equipment data is missing).
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.findings import FindingOccurrence, OperationalFinding
from app.models.source_data import FactEnergyMeterHourly, FactHourlyProduction


def get_energy_saving_opportunities(
    session: Session,
    reporting_date: date,
    plant_id: str = "IN-TN-01",
) -> List[Dict[str, Any]]:
    """
    Retrieve prioritized energy-saving opportunities for plant and date.
    
    Ranking factors:
    1. Recurrence count (number of historical occurrences)
    2. Observed consumption during stoppage / comparable period (kWh)
    3. Controllable load availability vs missing equipment data
    4. Severity vs savings potential (strictly kept separate)
    """
    day_start = datetime.combine(reporting_date, datetime.min.time())
    day_end = datetime.combine(reporting_date, datetime.max.time())

    # 1. Query findings active on this date or associated with this plant
    findings_stmt = (
        select(OperationalFinding)
        .where(OperationalFinding.plant_id == plant_id)
        .order_by(OperationalFinding.last_detected_at.desc())
    )
    all_findings: List[OperationalFinding] = session.execute(findings_stmt).scalars().all()

    if not all_findings:
        # Fallback to general plant findings
        all_findings = session.execute(
            select(OperationalFinding).order_by(OperationalFinding.last_detected_at.desc()).limit(20)
        ).scalars().all()

    opportunities: List[Dict[str, Any]] = []

    for f in all_findings:
        # Check if finding has occurrences on or near reporting date
        occ_stmt = (
            select(FindingOccurrence)
            .where(FindingOccurrence.finding_id == f.finding_id)
            .order_by(FindingOccurrence.occurrence_ts.desc())
        )
        occs: List[FindingOccurrence] = session.execute(occ_stmt).scalars().all()
        matched_occ = occs[0] if occs else None

        # Filter by date if occurrences exist
        date_matched = False
        if occs:
            for o in occs:
                if o.occurrence_ts and o.occurrence_ts.date() == reporting_date:
                    matched_occ = o
                    date_matched = True
                    break

        atype = (f.anomaly_type or "").upper()
        sev = (f.severity or "MEDIUM").upper()
        obs_kwh = float(f.current_actual_value or 0.0)
        recurrence = int(f.occurrence_count or len(occs) or 1)

        # Determine load controllability & missing equipment data
        has_equipment_evidence = bool(getattr(f, "equipment_id", None)) or ("submeter" in (getattr(f, "current_explanation", "") or "").lower())
        is_standby_candidate = any(k in atype for k in ("STANDBY", "ZERO_PRODUCTION", "STOPPAGE", "RESTART"))
        is_pf_candidate = "POWER_FACTOR" in atype
        is_baseload_candidate = "BASELOAD" in atype

        # Formulate opportunity
        opp_id = f"OPP-{f.finding_id}"
        if is_standby_candidate:
            if has_equipment_evidence:
                title = f"Auxiliary Standby Mode Trial during Stoppages on {f.line_id or f.meter_id or plant_id}"
                savings_potential = "Estimated 30–50 kWh per planned stoppage"
                why_surfaced = (
                    f"Recurrent standby draw observed ({obs_kwh:.2f} kWh) across {recurrence} stoppage episodes "
                    f"with confirmed controllable auxiliary equipment."
                )
                opp_type = "TRIAL_CANDIDATE"
                controllable = True
                missing_equip = False
                rec_action = "Initiate controlled standby trial during scheduled break exceeding restart time."
            else:
                title = f"Evidence Gathering: Isolate Standby Load on {f.line_id or f.meter_id or plant_id}"
                savings_potential = "Unquantified (Equipment-level audit required)"
                why_surfaced = (
                    f"Observed {obs_kwh:.2f} kWh standby draw across {recurrence} stoppage episodes on aggregate "
                    f"process meter {f.meter_id or 'main'}. Subcomponents unmetered."
                )
                opp_type = "EVIDENCE_GATHERING"
                controllable = False
                missing_equip = True
                rec_action = "Check equipment log & attach temporary submeter to isolate auxiliary load before testing change."
        elif is_pf_candidate:
            title = f"Power Factor Penalty Mitigation on {f.meter_id or plant_id}"
            savings_potential = "Avoid statutory PF penalty (< 0.90 lag)"
            why_surfaced = f"Measured power factor below standard threshold (0.90 lag) across {recurrence} monitoring intervals."
            opp_type = "OPTIMIZATION_OPPORTUNITY"
            controllable = True
            missing_equip = False
            rec_action = "Inspect APFC capacitor bank stages and motor idling schedules."
        elif is_baseload_candidate:
            title = f"Off-Shift Baseload Optimization on {f.meter_id or plant_id}"
            savings_potential = "Estimated 15–25 kWh/h continuous baseload reduction"
            why_surfaced = f"Persistent shift in demonstrated low-load baseload ({obs_kwh:.2f} kWh/h) across {recurrence} consecutive intervals."
            opp_type = "TRIAL_CANDIDATE"
            controllable = True
            missing_equip = False
            rec_action = "Audit off-shift auxiliary heating and compressed air setpoints."
        else:
            title = f"Operational Energy Review on {f.line_id or f.meter_id or plant_id}"
            savings_potential = f"Telemetry deviation: {obs_kwh:.2f} kWh"
            why_surfaced = f"Statistical consumption deviation observed across {recurrence} operational intervals."
            opp_type = "INVESTIGATION_OPPORTUNITY"
            controllable = False
            missing_equip = False
            rec_action = "Review operating speed and scrap reject rates."

        # Compute deterministic priority score
        # High recurrence + high consumption + controllable load = highest priority
        sev_score = 30 if sev == "CRITICAL" else (20 if sev == "HIGH" else 10)
        recurrence_score = min(recurrence * 2, 40)
        consumption_score = min(int(obs_kwh * 0.2), 30)
        controllable_bonus = 20 if controllable else 5
        date_bonus = 15 if date_matched else 0

        priority_score = sev_score + recurrence_score + consumption_score + controllable_bonus + date_bonus

        priority_rank = "HIGH" if priority_score >= 60 else ("MEDIUM" if priority_score >= 35 else "LOW")

        opportunities.append({
            "opportunity_id": opp_id,
            "finding_id": f.finding_id,
            "occurrence_id": matched_occ.occurrence_id if matched_occ else None,
            "title": title,
            "anomaly_type": atype,
            "severity": sev,
            "opportunity_type": opp_type,
            "savings_potential": savings_potential,
            "why_surfaced": why_surfaced,
            "is_controllable_load": controllable,
            "missing_equipment_data": missing_equip,
            "priority_rank": priority_rank,
            "priority_score": priority_score,
            "observed_kwh": obs_kwh,
            "recurrence_count": recurrence,
            "plant_id": f.plant_id or plant_id,
            "meter_id": f.meter_id,
            "line_id": f.line_id,
            "reporting_date": reporting_date.isoformat(),
            "recommended_action": rec_action,
            "date_matched": date_matched,
        })

    # Sort opportunities: date-matched first, then by priority_score descending
    opportunities.sort(key=lambda x: (1 if x["date_matched"] else 0, x["priority_score"]), reverse=True)
    return opportunities
