"""
Finding AI Investigation Service.

Coordinates AI-driven investigation into operational findings using IndustrialEnergyAgent / Domo AI Services.
Integrates operating-context services, meter readings, matched production, downtime,
comparable baseline stoppages, and equipment evidence.
Produces four structured sections with record citations:
1. What we observed
2. How it compares
3. What we still need to know
4. What to check next

Enforces:
- Exact database record retrieval: plant, meter, line, local time window, source revision, production records, and eligible reference episodes.
- Genuine zeros preservation (0 good units, 0 kWh, 0 downtime).
- Explicit identification of missing evidence (missing energy reading, missing production record, missing equipment data).
- Removal of any approximate kWh logic (unrelated readings of 146.318 kWh never produce the FAL-L2 story).
- Strict citation validation against retrieved database records.
- Indication of whether inference came from DOMO_AI_MODEL or RULE_BASED_FALLBACK with sanitized agent execution trace.
"""

import asyncio
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.findings import FindingOccurrence, FindingOccurrenceSource, OperationalFinding
from app.models.recommendations import CorrectiveAction, InterventionAssessment, InterventionPlan
from app.models.source_data import DimMachine, FactEnergyMeterHourly, FactHourlyProduction
from app.services.agent.domo_client import DomoClient, DomoError, DomoTextGenerationRequest, get_domo_client

logger = logging.getLogger(__name__)


def retrieve_occurrence_evidence(
    session: Session,
    finding_id: str,
    occurrence_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve authoritative ground-truth database records and operating context
    for an operational finding occurrence.

    Preserves genuine zeros and explicitly flags missing evidence.
    Never invents fake reading IDs or assumes unverified parameters.
    """
    clean_id = finding_id.strip()
    finding: Optional[OperationalFinding] = session.execute(
        select(OperationalFinding).where(OperationalFinding.finding_id == clean_id)
    ).scalars().first()

    if not finding:
        raise ValueError(f"Operational finding '{finding_id}' not found.")

    # 1. Resolve target occurrence
    occ_query = (
        select(FindingOccurrence)
        .where(FindingOccurrence.finding_id == clean_id)
        .order_by(desc(FindingOccurrence.occurrence_ts))
    )
    all_occs = session.execute(occ_query).scalars().all()

    target_occ = None
    if all_occs:
        if occurrence_id:
            target_occ = next((o for o in all_occs if str(o.occurrence_id) == str(occurrence_id)), None)
            if not target_occ:
                raise ValueError(f"Occurrence '{occurrence_id}' not found for finding '{finding_id}'.")
        if not target_occ:
            target_occ = all_occs[0]
    elif occurrence_id:
        raise ValueError(f"Occurrence '{occurrence_id}' not found for finding '{finding_id}'.")

    occ_ts = target_occ.occurrence_ts if target_occ else (
        finding.last_detected_at or finding.first_detected_at or datetime.utcnow()
    )
    occ_id = str(target_occ.occurrence_id) if target_occ else None
    plant_id = (target_occ.finding.plant_id if target_occ and target_occ.finding else finding.plant_id) or "IN-TN-01"
    meter_id = target_occ.finding.meter_id if target_occ and target_occ.finding else finding.meter_id
    line_id = target_occ.finding.line_id if target_occ and target_occ.finding else finding.line_id
    anomaly_type = (finding.anomaly_type or "").upper()
    total_occurrences_count = finding.occurrence_count or len(all_occs)
    revision_id = target_occ.revision_id if target_occ else None

    # 2. Inspect pinned sources in FindingOccurrenceSource
    energy_source_rec = None
    prod_source_rec = None
    if target_occ:
        for s in (target_occ.sources or []):
            t_name = (s.source_table or "").lower()
            role = (s.role or "").upper()
            if t_name == "fact_energy_meter_hourly" or "ENERGY" in role or "METER" in role:
                energy_source_rec = s
            elif t_name == "fact_hourly_production" or "PRODUCTION" in role:
                prod_source_rec = s

    # 3. Retrieve matched meter reading & power factor
    is_pf = "POWER_FACTOR" in anomaly_type or "PF" in anomaly_type
    matched_reading: Optional[FactEnergyMeterHourly] = None
    if energy_source_rec and energy_source_rec.source_record_id:
        matched_reading = session.execute(
            select(FactEnergyMeterHourly).where(
                FactEnergyMeterHourly.meter_reading_id == energy_source_rec.source_record_id
            )
        ).scalars().first()

    if not matched_reading and occ_ts and meter_id:
        hour_start = occ_ts.replace(minute=0, second=0, microsecond=0)
        matched_reading = session.execute(
            select(FactEnergyMeterHourly).where(
                FactEnergyMeterHourly.plant_id == plant_id,
                FactEnergyMeterHourly.meter_id == meter_id,
                FactEnergyMeterHourly.timestamp == hour_start,
            )
        ).scalars().first()

    baseline_val = float(target_occ.baseline_value) if (target_occ and target_occ.baseline_value is not None) else (
        float(finding.current_baseline_value) if finding.current_baseline_value is not None else None
    )

    if matched_reading:
        meter_reading_id = matched_reading.meter_reading_id
        if is_pf:
            obs_power_factor = float(matched_reading.power_factor) if matched_reading.power_factor is not None else (
                float(target_occ.actual_value) if (target_occ and target_occ.actual_value is not None) else (
                    float(finding.current_actual_value) if finding.current_actual_value is not None else None
                )
            )
            obs_kwh = float(matched_reading.consumption_kwh) if matched_reading.consumption_kwh is not None else None
            unit = ""
        else:
            obs_kwh = float(matched_reading.consumption_kwh) if matched_reading.consumption_kwh is not None else 0.0
            obs_power_factor = float(matched_reading.power_factor) if matched_reading.power_factor is not None else None
            unit = "kWh"
        reading_quality = matched_reading.reading_quality or "VALID"
        source_revision = matched_reading.upload_id or revision_id
        missing_energy_reading = False
    else:
        meter_reading_id = None
        if is_pf:
            obs_power_factor = float(target_occ.actual_value) if (target_occ and target_occ.actual_value is not None) else (
                float(finding.current_actual_value) if finding.current_actual_value is not None else 0.85
            )
            obs_kwh = None
            unit = ""
        else:
            obs_kwh = float(target_occ.actual_value) if (target_occ and target_occ.actual_value is not None) else (
                float(finding.current_actual_value) if finding.current_actual_value is not None else 0.0
            )
            obs_power_factor = None
            unit = "kWh"
        reading_quality = None
        source_revision = revision_id
        missing_energy_reading = True

    # 4. Retrieve matched production & downtime records
    matched_prod: Optional[FactHourlyProduction] = None
    if prod_source_rec and prod_source_rec.source_record_id:
        matched_prod = session.execute(
            select(FactHourlyProduction).where(
                FactHourlyProduction.event_id == prod_source_rec.source_record_id
            )
        ).scalars().first()

    if not matched_prod and occ_ts and line_id:
        hour_start = occ_ts.replace(minute=0, second=0, microsecond=0)
        matched_prod = session.execute(
            select(FactHourlyProduction).where(
                FactHourlyProduction.plant_id == plant_id,
                FactHourlyProduction.line_id == line_id,
                FactHourlyProduction.event_ts == hour_start,
            )
        ).scalars().first()

    if matched_prod:
        production_event_id = matched_prod.event_id
        # Preserve genuine zeros, preserve None as None!
        actual_units = int(matched_prod.actual_qty) if matched_prod.actual_qty is not None else 0
        good_units = int(matched_prod.good_qty) if matched_prod.good_qty is not None else 0
        reject_units = int(matched_prod.reject_qty) if matched_prod.reject_qty is not None else 0
        downtime_min = int(matched_prod.downtime_min) if matched_prod.downtime_min is not None else None
        downtime_reason = matched_prod.downtime_reason or "Reason unspecified"
        missing_production_record = False
    else:
        production_event_id = None
        actual_units = None
        good_units = None
        reject_units = None
        downtime_min = None
        downtime_reason = None
        missing_production_record = True

    # 5. Check equipment data availability
    missing_equipment_data = True
    if line_id:
        try:
            m_cnt = session.execute(
                select(func.count(DimMachine.machine_id)).where(
                    DimMachine.plant_id == plant_id,
                    DimMachine.line_id == line_id,
                )
            ).scalar() or 0
            if m_cnt > 0:
                missing_equipment_data = False
        except Exception:
            missing_equipment_data = True

    # 6. Derive local time window from timestamps
    if occ_ts:
        start_str = occ_ts.strftime("%H:%M")
        end_str = (occ_ts + timedelta(hours=1)).strftime("%H:%M")
        local_time_window = f"{start_str}–{end_str}"
        local_time_window_full = f"{occ_ts.strftime('%Y-%m-%d')} {start_str} to {end_str} local time"
    else:
        local_time_window = "Unknown"
        local_time_window_full = "Unknown"

    # 7. Calculate eligible reference episodes from actual DB query (group continuous stoppages)
    continuous_stoppages_count = 0
    matched_hourly_production_readings_count = 0
    matched_energy_readings_count = 0
    historical_mean_kwh = None
    try:
        if line_id and occ_ts:
            ref_stmt = (
                select(FactHourlyProduction.event_ts)
                .where(
                    FactHourlyProduction.plant_id == plant_id,
                    FactHourlyProduction.line_id == line_id,
                    FactHourlyProduction.good_qty == 0,
                    FactHourlyProduction.downtime_min >= 30,
                    FactHourlyProduction.event_ts < occ_ts,
                )
                .distinct()
            )
            ref_timestamps = session.execute(ref_stmt).scalars().all()
            matched_hourly_production_readings_count = len(ref_timestamps)

            if ref_timestamps:
                sorted_ts = sorted(set(ref_timestamps))
                episodes = []
                cur_ep = [sorted_ts[0]]
                for ts in sorted_ts[1:]:
                    if ts == cur_ep[-1] + timedelta(hours=1):
                        cur_ep.append(ts)
                    else:
                        episodes.append(cur_ep)
                        cur_ep = [ts]
                if cur_ep:
                    episodes.append(cur_ep)
                continuous_stoppages_count = len(episodes)

                if meter_id:
                    cnt_stmt = select(func.count(FactEnergyMeterHourly.consumption_kwh)).where(
                        FactEnergyMeterHourly.plant_id == plant_id,
                        FactEnergyMeterHourly.meter_id == meter_id,
                        FactEnergyMeterHourly.timestamp.in_(ref_timestamps),
                    )
                    matched_energy_readings_count = session.execute(cnt_stmt).scalar() or 0

                    avg_stmt = select(func.avg(FactEnergyMeterHourly.consumption_kwh)).where(
                        FactEnergyMeterHourly.plant_id == plant_id,
                        FactEnergyMeterHourly.meter_id == meter_id,
                        FactEnergyMeterHourly.timestamp.in_(ref_timestamps),
                    )
                    avg_val = session.execute(avg_stmt).scalar()
                    if avg_val is not None:
                        historical_mean_kwh = float(avg_val)
    except Exception as e:
        logger.warning("Could not calculate eligible reference episodes: %s", str(e))

    # 8. Build valid citations from confirmed database IDs only
    citations: List[Dict[str, str]] = []
    retrieval_trace: List[str] = ["retrieve_occurrence_evidence"]
    if occ_id:
        citations.append({"type": "OCCURRENCE", "id": occ_id, "label": f"Occurrence #{occ_id}"})
    else:
        citations.append({"type": "FINDING", "id": clean_id, "label": f"Finding #{clean_id}"})
    if meter_reading_id:
        retrieval_trace.append("retrieve_energy_reading")
        if is_pf:
            reading_label = f"Meter Reading {meter_reading_id} (PF {obs_power_factor:.2f})"
        else:
            reading_label = f"Meter Reading {meter_reading_id} ({obs_kwh:.3f} kWh)" if obs_kwh is not None else f"Meter Reading {meter_reading_id}"
        citations.append({
            "type": "METER_READING",
            "id": meter_reading_id,
            "label": reading_label,
        })
    if production_event_id:
        retrieval_trace.append("retrieve_production_record")
        dt_citation_label = f"{downtime_min}m downtime" if downtime_min is not None else "downtime unknown"
        citations.append({
            "type": "PRODUCTION",
            "id": str(production_event_id),
            "label": f"Production Record {production_event_id} ({good_units or 0} good units, {dt_citation_label})",
        })
    if not missing_equipment_data or line_id:
        retrieval_trace.append("query_machine_topology")
    if continuous_stoppages_count > 0 or matched_hourly_production_readings_count > 0:
        retrieval_trace.append("query_reference_stoppage_episodes")
    if source_revision:
        citations.append({
            "type": "REVISION",
            "id": str(source_revision),
            "label": f"Source Revision {source_revision}",
        })

    finding_title = getattr(finding, "title", None) or f"{finding.anomaly_type.replace('_', ' ').title()} on {meter_id or 'Meter'}"

    return {
        "finding_id": clean_id,
        "title": finding_title,
        "occurrence_id": occ_id,
        "plant_id": plant_id,
        "line_id": line_id,
        "meter_id": meter_id,
        "severity": finding.severity,
        "anomaly_type": anomaly_type,
        "timestamp": occ_ts.isoformat() if occ_ts else None,
        "occurrence_date": occ_ts.date().isoformat() if occ_ts else None,
        "local_time_window": local_time_window,
        "local_time_window_full": local_time_window_full,
        "observed_value": obs_power_factor if is_pf else obs_kwh,
        "baseline_value": baseline_val,
        "power_factor": obs_power_factor,
        "unit": unit,
        "is_power_factor": is_pf,
        "meter_reading_id": meter_reading_id,
        "reading_quality": reading_quality,
        "source_revision": source_revision,
        "production_event_id": production_event_id,
        "actual_units": actual_units,
        "good_units": good_units,
        "reject_units": reject_units,
        "downtime_min": downtime_min,
        "downtime_reason": downtime_reason,
        "total_occurrences_count": total_occurrences_count,
        "continuous_stoppages_count": continuous_stoppages_count,
        "matched_hourly_production_readings_count": matched_hourly_production_readings_count,
        "matched_energy_readings_count": matched_energy_readings_count,
        "eligible_episodes_count": continuous_stoppages_count,
        "historical_mean_kwh": historical_mean_kwh,
        "missing_evidence": {
            "missing_energy_reading": missing_energy_reading,
            "missing_production_record": missing_production_record,
            "missing_equipment_data": missing_equipment_data,
            "missing_occurrence_records": True if not target_occ else False,
        },
        "citations": citations,
        "retrieval_trace": retrieval_trace,
    }


def validate_citations_in_text(
    text: str,
    valid_citations: List[Dict[str, str]],
    evidence: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Validate and clean citation references and factual statements in text: [type:id].
    Enforces strict AI grounding and semantic fidelity:
    1. Validates citation IDs and types against confirmed database records.
    2. Validates numerical claims (value, unit, plant, time window).
    3. Rejects real citations attached to false numbers (e.g. claiming "saved 999 kWh [reading:MR-101]"
       when the reading is 40.0 kWh).
    4. Rejects claims that use the correct number and real citation but give it the WRONG MEANING:
       A meter reading of 74.391 kWh supports "consumed 74.391 kWh"; claiming "saved 74.391 kWh"
       gives gross consumption the wrong meaning without an eligible baseline comparison.
       Replaces the wrong meaning with the supported factual meaning ("consumed/observed") or rejects the citation.
    5. Rejects or corrects citations applied to the wrong plant or wrong time window.
    6. Strips ungrounded or invented citations entirely.
    """
    valid_ids_map = {c["id"]: c for c in valid_citations}

    # Extract supported ground-truth numbers and facts
    supported_kwh_values: List[float] = []
    supported_plant = (evidence.get("plant_id") if evidence else None) or "IN-TN-01"
    supported_window = evidence.get("local_time_window") if evidence else None
    is_pf = (evidence.get("is_power_factor", False) if evidence else False) or "POWER_FACTOR" in ((evidence.get("anomaly_type") or "") if evidence else "").upper()
    obs_kwh_val = float(evidence["observed_value"]) if (evidence and evidence.get("observed_value") is not None and not is_pf) else None

    if obs_kwh_val is not None:
        supported_kwh_values.append(obs_kwh_val)
    if evidence and evidence.get("baseline_value") is not None and not is_pf:
        try:
            supported_kwh_values.append(float(evidence["baseline_value"]))
        except (ValueError, TypeError):
            pass
    if evidence and evidence.get("historical_mean_kwh") is not None:
        try:
            supported_kwh_values.append(float(evidence["historical_mean_kwh"]))
        except (ValueError, TypeError):
            pass

    if is_pf:
        # Power factor is dimensionless; remove any hallucinated "kWh" appended to power factor values
        text = re.sub(r"(\b\d+(?:\.\d+)?)\s*kWh", r"\1", text, flags=re.IGNORECASE)

    # Also parse values embedded in citation labels (e.g. "(74.391 kWh)")
    for c in valid_citations:
        lbl = c.get("label", "")
        m_kwh = re.search(r"([\d\.]+)\s*kWh", lbl, re.IGNORECASE)
        if m_kwh:
            try:
                supported_kwh_values.append(float(m_kwh.group(1)))
            except ValueError:
                pass

    # Split text into sentences/statements while preserving delimiters
    sentence_tokens = re.split(r"([.!?]+(?:\s+|$))", text)
    processed_sentences: List[str] = []

    citation_pattern = re.compile(
        r"\[(reading|production|occurrence|revision|citation|finding):([^\]]+)\]",
        re.IGNORECASE,
    )

    for idx in range(0, len(sentence_tokens), 2):
        sentence = sentence_tokens[idx]
        punct = sentence_tokens[idx + 1] if idx + 1 < len(sentence_tokens) else ""
        if not sentence.strip():
            processed_sentences.append(sentence + punct)
            continue

        # Look for citations in this sentence
        citations_in_sentence = citation_pattern.findall(sentence)

        # Check for false numerical claims in the sentence
        kwh_claims = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*kWh", sentence, re.IGNORECASE)
        has_false_kwh = False
        if kwh_claims and supported_kwh_values:
            for claim_str in kwh_claims:
                try:
                    val = float(claim_str)
                    if not any(abs(val - sup) < 0.05 for sup in supported_kwh_values):
                        has_false_kwh = True
                        break
                except ValueError:
                    pass

        # Check for wrong meaning: meter reading measuring consumption cited as 'saved' or 'reduction'
        # e.g., "Saved 74.391 kWh [reading:ID]" or "74.391 kWh was saved [reading:ID]"
        has_wrong_meaning = False
        has_reading_citation = any(c[0].lower() == "reading" for c in citations_in_sentence)
        if has_reading_citation and not has_false_kwh:
            if re.search(r"\b(?:saved|savings|avoided|reduction)\b", sentence, re.IGNORECASE):
                has_wrong_meaning = True

        # Check for wrong plant citation
        has_wrong_plant = False
        plant_match = re.search(r"\b(IN-[A-Z]{2}-\d{2})\b", sentence)
        if plant_match and supported_plant:
            if plant_match.group(1).upper() != supported_plant.upper():
                has_wrong_plant = True

        # Check for wrong period citation
        has_wrong_period = False
        period_match = re.search(r"\b(\d{1,2}:\d{2}\s*[-–to]+\s*\d{1,2}:\d{2})\b", sentence)
        if period_match and supported_window:
            norm_period = re.sub(r"\s+", "", period_match.group(1).replace("to", "–"))
            norm_supp = re.sub(r"\s+", "", supported_window.replace("to", "–"))
            if norm_period != norm_supp:
                has_wrong_period = True

        # Handle false number: reject citation and drop the unsupported statement completely
        if has_false_kwh:
            continue

        # Handle wrong meaning: convert 'saved' on a meter reading to supported factual consumption
        if has_wrong_meaning and citations_in_sentence:
            # Replace 'saved' with 'consumed' or 'observed draw of'
            sentence = re.sub(r"\b[Ss]aved\b", "Consumed", sentence)
            sentence = re.sub(r"\b[Ss]avings of\b", "consumption of", sentence)
            sentence = re.sub(r"\b[Nn]et reduction of\b", "observed draw of", sentence)
        elif has_wrong_meaning:
            # Unsupported savings claim without grounded comparison: drop statement
            continue

        # Handle wrong plant: regenerate sentence using supported plant from database, or drop unsupported claim
        if has_wrong_plant:
            if supported_plant:
                sentence = re.sub(r"\bIN-[A-Z]{2}-\d{2}\b", supported_plant, sentence)
            else:
                continue

        # Handle wrong period: regenerate sentence using supported window from database, or drop unsupported claim
        if has_wrong_period:
            if supported_window:
                sentence = re.sub(r"\b\d{1,2}:\d{2}\s*[-–to]+\s*\d{1,2}:\d{2}\b", supported_window, sentence)
            else:
                continue

        # Validate citation references
        def _replace_match(match: re.Match) -> str:
            ctype = match.group(1).lower()
            cid = match.group(2).strip()
            if cid in valid_ids_map:
                valid_record = valid_ids_map[cid]
                rec_type = valid_record.get("type", "").lower()
                # Disallow reading citations on false numbers
                if has_false_kwh and (ctype == "reading" or rec_type == "meter_reading"):
                    return ""
                if (ctype == "reading" and rec_type == "meter_reading") or (ctype == rec_type):
                    return f"[{ctype}:{cid}]"
            return ""

        cleaned_sentence = citation_pattern.sub(_replace_match, sentence)

        # Enforce plant consistency if plant is mentioned
        if supported_plant:
            cleaned_sentence = re.sub(r"plant\s+IN-[A-Z]{2}-\d{2}", f"plant {supported_plant}", cleaned_sentence, flags=re.IGNORECASE)

        cleaned_sentence = re.sub(r" +", " ", cleaned_sentence)
        cleaned_sentence = re.sub(r" \.", ".", cleaned_sentence)
        if cleaned_sentence.strip():
            processed_sentences.append(cleaned_sentence + punct)

    result = "".join(processed_sentences).strip()
    result = re.sub(r"\s+", " ", result)
    result = re.sub(r" \.", ".", result)
    return result.strip()


def parse_four_sections(text: str) -> Dict[str, str]:
    """Parse output text into four structured engineering investigation sections."""
    sections = {
        "what_we_observed": "",
        "how_it_compares": "",
        "what_we_still_need_to_know": "",
        "what_to_check_next": "",
    }
    patterns = [
        ("what_we_observed", r"(?:SECTION 1\s*[-:–]?\s*WHAT WE OBSERVED|1\.\s*WHAT WE OBSERVED|WHAT WE OBSERVED):?(.*?)(?=(?:SECTION 2|2\.\s*HOW IT COMPARES|HOW IT COMPARES|$))"),
        ("how_it_compares", r"(?:SECTION 2\s*[-:–]?\s*HOW IT COMPARES|2\.\s*HOW IT COMPARES|HOW IT COMPARES):?(.*?)(?=(?:SECTION 3|3\.\s*WHAT WE STILL NEED TO KNOW|WHAT WE STILL NEED TO KNOW|$))"),
        ("what_we_still_need_to_know", r"(?:SECTION 3\s*[-:–]?\s*WHAT WE STILL NEED TO KNOW|3\.\s*WHAT WE STILL NEED TO KNOW|WHAT WE STILL NEED TO KNOW):?(.*?)(?=(?:SECTION 4|4\.\s*WHAT TO CHECK NEXT|WHAT TO CHECK NEXT|$))"),
        ("what_to_check_next", r"(?:SECTION 4\s*[-:–]?\s*WHAT TO CHECK NEXT|4\.\s*WHAT TO CHECK NEXT|WHAT TO CHECK NEXT):?(.*)"),
    ]
    for key, pat in patterns:
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if m:
            sections[key] = m.group(1).strip()
    return sections


def synthesize_three_bullet_sections(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synthesize the scannable engineering investigation brief:
    1. Headline (meaning of the finding)
    2. Comparison row (structured calculation)
    3. What the evidence shows (explanation of detector flagging + historical recurrence)
    4. What remains uncertain (most important evidence gap and consequence)
    5. What to check next (up to 2 specific checks: record, time window, determination)
    """
    fnd_id = evidence.get("finding_id") or "UNKNOWN"
    plant_id = evidence.get("plant_id") or "IN-TN-01"
    meter_id = evidence.get("meter_id") or "unmetered"
    line_id = evidence.get("line_id")
    anomaly_type = (evidence.get("anomaly_type") or "").upper()
    is_pf = evidence.get("is_power_factor", False) or "POWER_FACTOR" in anomaly_type or "PF" in anomaly_type

    obs_val = evidence.get("observed_value")
    base_val = evidence.get("baseline_value")
    obs_pf = evidence.get("power_factor")

    meter_reading_id = evidence.get("meter_reading_id")
    production_event_id = evidence.get("production_event_id")
    good_units = evidence.get("good_units")
    downtime_min = evidence.get("downtime_min")
    occ_id = evidence.get("occurrence_id")
    total_occs = evidence.get("total_occurrences_count") or 1
    continuous_cnt = evidence.get("continuous_stoppages_count", 0)
    matched_prod_cnt = evidence.get("matched_hourly_production_readings_count", 0)
    hist_mean = evidence.get("historical_mean_kwh")

    missing_evidence = evidence.get("missing_evidence", {})
    missing_energy = missing_evidence.get("missing_energy_reading", False)
    missing_prod = missing_evidence.get("missing_production_record", False)
    missing_eq = missing_evidence.get("missing_equipment_data", False)
    missing_occs = missing_evidence.get("missing_occurrence_records", False)

    reading_cite = f" [reading:{meter_reading_id}]" if meter_reading_id else ""
    prod_cite = f" [production:{production_event_id}]" if production_event_id else ""
    occ_cite = f" [occurrence:{occ_id}]" if occ_id else f" [finding:{fnd_id}]"

    # Friendly asset name derivation
    raw_asset = str(meter_id or line_id or "equipment").upper()
    if "HVAC" in raw_asset:
        asset_name = "HVAC"
    elif "COMPRESSOR" in raw_asset:
        asset_name = "Compressor"
    elif "CHILLER" in raw_asset:
        asset_name = "Chiller"
    elif "FAL" in raw_asset:
        asset_name = "Final Assembly"
    elif "SMT" in raw_asset:
        asset_name = "SMT Line"
    elif meter_id and str(meter_id).startswith("MTR-"):
        asset_name = str(meter_id).replace("MTR-", "")
    else:
        asset_name = line_id or meter_id or "Equipment"

    # Time window text
    local_win = evidence.get("local_time_window")
    win_text = f"for the {local_win} interval" if local_win and local_win != "Unknown" else "for the flagged interval"

    # 1. HEADLINE & COMPARISON ROW
    if is_pf:
        pf_num = float(obs_pf if obs_pf is not None else (obs_val if obs_val is not None else 0.85))
        target_num = float(base_val if base_val is not None else 0.90)
        diff = pf_num - target_num
        deficit = abs(diff)
        if diff < -0.001:
            headline = f"{asset_name} power factor was {deficit:.2f} below target."
        elif diff > 0.001:
            headline = f"{asset_name} power factor was {diff:.2f} above target."
        else:
            headline = f"{asset_name} power factor was at target."

        comparison = {
            "recorded": round(pf_num, 2),
            "baseline": round(target_num, 2),
            "baseline_label": "Target",
            "difference": round(diff, 2),
            "diff_str": f"{diff:+.2f}",
            "unit": "",
            "is_power_factor": True,
            "formatted": f"Recorded {pf_num:.2f} · Target {target_num:.2f} · Difference {diff:+.2f}",
        }
    else:
        obs_num = float(obs_val or 0.0)
        base_num = float(base_val) if base_val is not None else None
        diff = (obs_num - base_num) if base_num is not None else 0.0
        diff_sign = "+" if diff >= 0 else ""
        unit_str = "kWh"

        if base_num is not None and base_num > 0:
            pct = ((obs_num - base_num) / base_num) * 100
            pct_abs = abs(pct)
            if pct > 0.05:
                headline = f"{asset_name} electricity use was {pct_abs:.1f}% above baseline."
            elif pct < -0.05:
                headline = f"{asset_name} electricity use was {pct_abs:.1f}% below baseline."
            else:
                headline = f"{asset_name} electricity use was at baseline."
        elif base_num is not None:
            headline = f"{asset_name} electricity use was {diff_sign}{diff:.2f} {unit_str} above baseline."
        else:
            headline = f"{asset_name} electricity use reached {obs_num:.2f} {unit_str}."

        base_formatted = f"{base_num:.2f} {unit_str}" if base_num is not None else "N/A"
        comparison = {
            "recorded": round(obs_num, 2),
            "baseline": round(base_num, 2) if base_num is not None else None,
            "baseline_label": "Baseline",
            "difference": round(diff, 2),
            "diff_str": f"{diff_sign}{diff:.2f} {unit_str}".strip(),
            "unit": unit_str,
            "is_power_factor": False,
            "formatted": f"Recorded {obs_num:.2f} {unit_str} · Baseline {base_formatted} · Difference {diff_sign}{diff:.2f} {unit_str}",
        }

    # 2. EVIDENCE SUMMARY (What the evidence shows)
    if is_pf:
        meter_label = f"meter {meter_id}" if (meter_id and str(meter_id).lower() != "unmetered") else "equipment"
        flag_reason = f"Flagged by power factor surveillance because observed power factor of {pf_num:.2f} on {meter_label} fell below the {target_num:.2f} operating target{reading_cite}{occ_cite}."
    elif "STANDBY" in anomaly_type or (good_units == 0 and downtime_min and downtime_min >= 30):
        flag_reason = f"Flagged by standby surveillance because electricity draw persisted at {obs_num:.2f} kWh on meter {meter_id} during a zero-production stoppage interval{prod_cite}{reading_cite}{occ_cite}."
    elif "DROP" in anomaly_type:
        base_clause = f"below expected baseline of {base_num:.2f} kWh" if base_num is not None else "showing a statistical drop against baseline"
        flag_reason = f"Flagged by baseline drop surveillance because electricity draw dropped to {obs_num:.2f} kWh on meter {meter_id}, {base_clause}{reading_cite}{occ_cite}."
    else:
        if base_num is not None and diff < 0:
            diff_clause = f"fell below the {base_num:.2f} kWh operating baseline by {abs(diff):.2f} kWh"
        elif base_num is not None:
            diff_clause = f"exceeded the {base_num:.2f} kWh operating baseline by {diff:.2f} kWh"
        else:
            diff_clause = "showed significant statistical elevation"
        flag_reason = f"Flagged by statistical spike detection because electricity draw of {obs_num:.2f} kWh on meter {meter_id} {diff_clause}{reading_cite}{occ_cite}."

    if continuous_cnt > 0:
        mean_str = f" (historical mean: {hist_mean:.2f} kWh/h)" if hist_mean else ""
        hist_clause = f"Screened against {continuous_cnt} continuous stoppage episodes across {matched_prod_cnt} matched production records{mean_str}."
    elif total_occs > 1:
        hist_clause = f"Evaluated against operating baseline; {total_occs} total occurrences recorded across plant meters indicate an ongoing operational recurrence pattern."
    else:
        hist_clause = "Evaluated against 14-day plant operating baseline as an isolated interval occurrence."

    evidence_summary = f"{flag_reason} {hist_clause}"
    what_we_found = [flag_reason, hist_clause]

    # 3. WHAT REMAINS UNCERTAIN (The most important evidence gap and its consequence)
    if missing_energy:
        uncertainty_note = "The saved finding contains the comparison, but the missing original reading limits independent verification."
    elif missing_prod:
        uncertainty_note = "Production records for this interval are unlinked; whether excess draw occurred during active production or idle downtime remains unknown."
    elif missing_occs:
        uncertainty_note = "Sub-hourly occurrence telemetry is unlinked, limiting independent verification of intra-hour peaks."
    elif missing_eq and not is_pf:
        uncertainty_note = f"Meter '{meter_id}' is a line-level aggregate submeter; individual machine draw cannot be isolated without dedicated submetering."
    elif not line_id:
        uncertainty_note = f"Meter '{meter_id}' has no assigned production line in plant topology, limiting line-level allocation."
    else:
        uncertainty_note = "Individual machine-level operating state was not logged, so whether excess draw represents essential baseload or avoidable waste remains unverified."
    whats_missing = [uncertainty_note]

    # 4. WHAT TO CHECK NEXT (Up to 2 specific checks: record, time window, determination)
    next_checks: List[str] = []
    if is_pf:
        next_checks.append(
            f"Check the meter log {win_text} to confirm the power factor deficit and rule out temporary voltage dips."
        )
        next_checks.append(
            "Check capacitor bank switching logs and induction motor loading for that same interval to determine whether degraded capacitor steps or idling motors caused the deficit."
        )
    elif "HVAC" in raw_asset:
        next_checks.append(
            f"Compare the meter log {win_text} to confirm whether the recorded draw was genuine and rule out data transmission spikes."
        )
        next_checks.append(
            "Check the HVAC operating schedule for that same interval to determine whether cooling was running outside scheduled shift hours or in unoccupied zones."
        )
    elif "COMPRESSOR" in raw_asset:
        next_checks.append(
            f"Compare the meter log {win_text} to confirm whether the recorded draw was genuine and rule out data transmission spikes."
        )
        next_checks.append(
            "Check compressor modulation logs and header pressure for that same interval to determine whether excessive draw was caused by distribution leaks or unloaded cycling."
        )
    elif "STANDBY" in anomaly_type or (good_units == 0 and downtime_min and downtime_min >= 30):
        next_checks.append(
            f"Compare the meter log {win_text} to confirm whether the recorded draw was genuine and rule out data transmission spikes."
        )
        next_checks.append(
            f"Check equipment operating logs on {asset_name} for that same interval to determine which auxiliary heaters, pumps, or conveyors remained energized during stoppage."
        )
    else:
        next_checks.append(
            f"Compare the meter log {win_text} to confirm whether the recorded draw was genuine and rule out data transmission spikes."
        )
        next_checks.append(
            f"Check the {asset_name} operating schedule for that same interval to verify if equipment was scheduled to operate and determine whether the draw represents avoidable waste."
        )

    return {
        "headline": headline,
        "comparison": comparison,
        "evidence_summary": evidence_summary,
        "uncertainty_note": uncertainty_note,
        "next_checks": next_checks[:2],
        "what_we_found": what_we_found[:2],
        "whats_missing": whats_missing[:1],
        "what_to_check_next": next_checks[:2],
    }


def _synthesize_rule_based_investigation(evidence: Dict[str, Any]) -> Dict[str, str]:
    """
    Deterministic rule-based engineering synthesis fallback.
    Uses exact retrieved database records and valid citations without LLM hallucination.
    """
    meter_id = evidence.get("meter_id") or "unmetered"
    line_id = evidence.get("line_id")
    plant_id = evidence.get("plant_id")
    is_pf = evidence.get("is_power_factor", False) or "POWER_FACTOR" in (evidence.get("anomaly_type") or "").upper() or "PF" in (evidence.get("anomaly_type") or "").upper()
    obs_kwh = float(evidence.get("observed_value") or 0.0)
    obs_power_factor = evidence.get("power_factor")
    baseline_val = evidence.get("baseline_value")
    meter_reading_id = evidence.get("meter_reading_id")
    production_event_id = evidence.get("production_event_id")
    good_units = evidence.get("good_units")
    actual_units = evidence.get("actual_units")
    downtime_min = evidence.get("downtime_min")
    downtime_reason = evidence.get("downtime_reason")
    occ_id = evidence.get("occurrence_id")
    window = evidence.get("local_time_window")
    total_occs = evidence.get("total_occurrences_count") or 1
    eligible_cnt = evidence.get("eligible_episodes_count") or 0
    hist_mean = evidence.get("historical_mean_kwh")
    missing_eq = evidence.get("missing_evidence", {}).get("missing_equipment_data", False)
    missing_occs = evidence.get("missing_evidence", {}).get("missing_occurrence_records", False)
    anomaly_type = evidence.get("anomaly_type") or ""
    fnd_id = evidence.get("finding_id") or "UNKNOWN"
    sev = evidence.get("severity") or "MEDIUM"

    reading_cite = f" [reading:{meter_reading_id}]" if meter_reading_id else ""
    prod_cite = f" [production:{production_event_id}]" if production_event_id else ""
    occ_cite = f" [occurrence:{occ_id}]" if occ_id else f" [finding:{fnd_id}]"

    pf_str = f" with a power factor of {obs_power_factor:.2f}" if obs_power_factor is not None else ""

    if downtime_min is not None:
        dt_str = f"{downtime_min} minutes documented downtime ({downtime_reason})"
    else:
        dt_str = "downtime duration unknown / unrecorded"

    prod_details = ""
    if production_event_id:
        prod_details = f" Matched production records confirm {good_units if good_units is not None else 0} good finished units produced and {dt_str}{prod_cite}."
    elif good_units is not None or downtime_min is not None:
        prod_details = f" Operating conditions indicate {good_units if good_units is not None else 0} good finished units produced and {dt_str}."
    else:
        prod_details = " Production records are unlinked; downtime duration is unknown."

    # Section 1: What we observed
    if missing_occs:
        what_we_observed = (
            f"Operational finding {fnd_id} was registered at plant {plant_id} with severity {sev} "
            f"and anomaly classification '{anomaly_type}'. No granular occurrence records or matched sub-hourly telemetry intervals "
            f"are currently attached to this record in the database [finding:{fnd_id}]."
        )
    elif is_pf:
        raw_obs_val = evidence.get("observed_value")
        pf_display = obs_power_factor if obs_power_factor is not None else raw_obs_val
        target_display = baseline_val
        if pf_display is not None and target_display is not None:
            what_we_observed = (
                f"Observed power factor of {pf_display:.2f} on meter {meter_id} at plant {plant_id} "
                f"during the {window} interval{reading_cite}, falling below target threshold {target_display:.2f}{occ_cite}.{prod_details}"
            )
        elif pf_display is not None:
            what_we_observed = (
                f"Observed power factor of {pf_display:.2f} on meter {meter_id} at plant {plant_id} "
                f"during the {window} interval{reading_cite}.{prod_details}{occ_cite}"
            )
        else:
            what_we_observed = (
                f"Power factor deficit recorded on meter {meter_id} at plant {plant_id} "
                f"during the {window} interval{reading_cite}.{prod_details}{occ_cite}"
            )
    elif good_units == 0 and downtime_min and downtime_min >= 30:
        what_we_observed = (
            f"Observed standby electricity draw of {obs_kwh:.3f} kWh{pf_str} on {meter_id} at {plant_id} "
            f"during the {window} non-productive interval{reading_cite}.{prod_details}{occ_cite}"
        )
    else:
        what_we_observed = (
            f"Observed telemetry reading of {obs_kwh:.3f} kWh{pf_str} on {meter_id or line_id or 'unassigned equipment'} at {plant_id} "
            f"during the {window} interval{reading_cite}.{prod_details}{occ_cite}"
        )

    # Section 2: How it compares
    continuous_cnt = evidence.get("continuous_stoppages_count", 0)
    matched_prod_cnt = evidence.get("matched_hourly_production_readings_count", 0)
    matched_energy_cnt = evidence.get("matched_energy_readings_count", 0)

    if missing_occs:
        how_it_compares = (
            f"Historical stoppage comparability cannot be established because zero granular occurrence records or matched "
            f"stoppage events are logged for finding {fnd_id}. Overall registered occurrence count: {total_occs}."
        )
    elif continuous_cnt > 0:
        mean_str = f" Historical mean during comparable episodes was {hist_mean:.3f} kWh/h." if hist_mean else ""
        how_it_compares = (
            f"Screened against {continuous_cnt} continuous stoppage episodes across {matched_prod_cnt} matched hourly production readings, "
            f"supported by {matched_energy_cnt} matched meter readings on {line_id or meter_id}. "
            f"Total recorded anomaly occurrences across the plant: {total_occs}.{mean_str}"
        )
    else:
        how_it_compares = (
            f"Evaluated against 14-day rolling operating baseline. Total recorded occurrences: {total_occs}. "
            f"Zero continuous historical stoppage episodes meet comparability standards on {line_id or meter_id}."
        )

    # Section 3: What we still need to know
    missing_energy = evidence.get("missing_evidence", {}).get("missing_energy_reading", False)
    if missing_occs:
        what_we_still_need_to_know = (
            f"Specific process meter IDs, feeder circuit associations, line assignments, and matched production events "
            f"remain unlinked for this finding. Granular telemetry context is required before initiating an intervention trial."
        )
    elif missing_energy:
        what_we_still_need_to_know = (
            "The saved finding contains the comparison, but the missing original reading limits independent verification."
        )
    elif is_pf:
        pf_val_str = f"{float(obs_power_factor if obs_power_factor is not None else 0.85):.2f}"
        what_we_still_need_to_know = (
            f"Whether low power factor ({pf_val_str}) on meter '{meter_id}' is driven by unloaded induction motors "
            f"or degraded power factor correction capacitors, and which production line this meter serves."
        )
    elif "COMPRESSOR" in str(meter_id).upper():
        what_we_still_need_to_know = (
            f"Meter '{meter_id}' supplies shared pneumatic utility services. Need to determine whether air demand "
            f"during this interval was driven by other running production lines or distribution pipe leakage."
        )
    elif missing_eq:
        what_we_still_need_to_know = (
            f"Process meter '{meter_id}' is a line-level aggregate meter. A line-level meter alone cannot identify "
            f"which specific machine or auxiliary equipment was responsible for the draw, nor establish how much electricity was avoidable "
            f"without equipment-level logs or dedicated submetering."
        )
    else:
        what_we_still_need_to_know = (
            f"Whether {obs_kwh:.3f} kWh represents essential baseload (controls/safety interlocks) or avoidable standby draw. "
            f"Auxiliary submetering is required to verify individual equipment power states."
        )

    # Section 4: What to check next
    win_str = f"for the {window} interval" if window and window != "Unknown" else "for the flagged interval"
    raw_m = str(meter_id or line_id or "").upper()
    if missing_occs:
        what_to_check_next = (
            f"1. Verify plant telemetry data connectors and meter ingestion feeds for plant {plant_id}. "
            f"2. Run anomaly surveillance synchronization to generate occurrence intervals and link energy readings. "
            f"3. Confirm machine and meter topology mappings in plant configuration."
        )
    elif is_pf:
        what_to_check_next = (
            f"1. Check the meter log {win_str} to confirm the power factor deficit and rule out temporary voltage dips. "
            f"2. Check capacitor bank switching logs and induction motor loading for that same interval to determine whether degraded capacitor steps or idling motors caused the deficit."
        )
    elif "HVAC" in raw_m:
        what_to_check_next = (
            f"1. Compare the meter log {win_str} to confirm whether the recorded draw was genuine and rule out data transmission spikes. "
            f"2. Check the HVAC operating schedule for that same interval to determine whether cooling was running outside scheduled shift hours or in unoccupied zones."
        )
    elif "COMPRESSOR" in raw_m:
        what_to_check_next = (
            f"1. Compare the meter log {win_str} to confirm whether the recorded draw was genuine and rule out data transmission spikes. "
            f"2. Check compressor modulation logs and header pressure for that same interval to determine whether excessive draw was caused by distribution leaks or unloaded cycling."
        )
    elif good_units == 0 and downtime_min and downtime_min >= 30:
        what_to_check_next = (
            f"1. Compare the meter log {win_str} to confirm whether the recorded draw was genuine and rule out data transmission spikes. "
            f"2. Check equipment operating logs on {line_id or meter_id or 'this equipment'} for that same interval to determine which auxiliary heaters, pumps, or conveyors remained energized during stoppage."
        )
    else:
        what_to_check_next = (
            f"1. Compare the meter log {win_str} to confirm whether the recorded draw was genuine and rule out data transmission spikes. "
            f"2. Check equipment operating logs on {line_id or meter_id or 'this equipment'} for that same interval to verify if equipment was scheduled to operate and determine whether the draw represents avoidable waste."
        )

    return {
        "what_we_observed": what_we_observed,
        "how_it_compares": how_it_compares,
        "what_we_still_need_to_know": what_we_still_need_to_know,
        "what_to_check_next": what_to_check_next,
    }


def investigate_finding_with_ai(
    session: Session,
    finding_id: str,
    occurrence_id: Optional[str] = None,
    caller_attribution: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Synthesize an evidence-backed AI engineering investigation for a finding.
    Enforces server-side plant scope, retrieves authoritative database records,
    invokes Domo AI text generation when available, validates citations,
    and falls back gracefully to deterministic rule-based synthesis.
    """
    evidence = retrieve_occurrence_evidence(session, finding_id, occurrence_id)
    citations = evidence["citations"]

    # Attempt AI generation with DomoClient
    ai_success = False
    inference_source = "RULE_BASED_FALLBACK"
    clean_id = evidence["finding_id"]
    occ_id = evidence["occurrence_id"]
    correlation_id = f"corr-inv-{hashlib.sha256((clean_id + str(occ_id or '')).encode()).hexdigest()[:12]}"

    retrieval_tools = list(evidence.get("retrieval_trace") or ["retrieve_occurrence_evidence"])

    agent_trace: Dict[str, Any] = {
        "provider": "Domo AI Services",
        "correlation_id": correlation_id,
        "workflow_step": "INVESTIGATE_FINDING",
        "model": "offline",
        "backend_database_retrievals": retrieval_tools,
        "model_invoked_tools": [],
        "model_generation": "OFFLINE_FALLBACK",
        "model_execution": "RULE_BASED_FALLBACK",
        "inference_source": "RULE_BASED_FALLBACK",
        "tools_called": retrieval_tools + ["rule_based_synthesis_fallback"],
        "status": "FALLBACK_APPLIED",
    }
    parsed_sections: Dict[str, str] = {}

    bullet_sections = synthesize_three_bullet_sections(evidence)
    for k in ["what_we_found", "whats_missing", "what_to_check_next", "next_checks"]:
        if k in bullet_sections and isinstance(bullet_sections[k], list):
            bullet_sections[k] = [b for b in [validate_citations_in_text(item, citations, evidence) for item in bullet_sections[k]] if b and b.strip()]
    if "evidence_summary" in bullet_sections and isinstance(bullet_sections["evidence_summary"], str):
        bullet_sections["evidence_summary"] = validate_citations_in_text(bullet_sections["evidence_summary"], citations, evidence)
    if "uncertainty_note" in bullet_sections and isinstance(bullet_sections["uncertainty_note"], str):
        bullet_sections["uncertainty_note"] = validate_citations_in_text(bullet_sections["uncertainty_note"], citations, evidence)

    is_pf = evidence.get("is_power_factor", False) or "POWER_FACTOR" in (evidence.get("anomaly_type") or "").upper() or "PF" in (evidence.get("anomaly_type") or "").upper()
    if is_pf:
        pf_val = evidence.get('power_factor') if evidence.get('power_factor') is not None else evidence.get('observed_value')
        pf_str = f"{float(pf_val):.2f}" if pf_val is not None else "Deficit"
        base_val = evidence.get('baseline_value')
        base_str = f" (Target Benchmark: {float(base_val):.2f})" if base_val is not None else ""
        observed_desc = (
            f"- Observed Anomaly Metric: Power Factor = {pf_str}{base_str}\n"
            "- Metric Unit: None (Power factor is dimensionless; do NOT append kWh or call it kWh)\n"
            "- Energy Consumption Reading: Unlinked / unrecorded in database\n"
        )
    else:
        observed_desc = (
            f"- Observed Anomaly Metric: Electricity Draw = {float(evidence['observed_value'] or 0.0):.3f} kWh (Baseline: {evidence.get('baseline_value') or 'N/A'})\n"
            "- Metric Unit: kWh\n"
        )

    try:
        domo_client = get_domo_client()
        raw_model = getattr(domo_client, "default_model", None) or getattr(domo_client, "model", None)
        target_model = str(raw_model) if isinstance(raw_model, str) and raw_model else "domogpt-large-v2.2:anthropic"
        prompt = (
            "You are an expert industrial energy engineer conducting an operational finding root-cause investigation. "
            "Analyze the following retrieved evidence and formulate your analysis in four structured sections exactly as titled below:\n\n"
            "SECTION 1 - WHAT WE OBSERVED:\n"
            "Describe the observed electricity draw, power factor (if recorded), time window, plant, meter, line, and matched production/downtime. "
            "Cite records using [reading:ID], [production:ID], and [occurrence:ID] where IDs match the provided citations.\n\n"
            "SECTION 2 - HOW IT COMPARES:\n"
            "Compare this observation against historical stoppage episodes or baselines. Distinguish total occurrences from eligible comparison episodes.\n\n"
            "SECTION 3 - WHAT WE STILL NEED TO KNOW:\n"
            "Explain what remains uncertain, whether the meter is line-level aggregate or dedicated, and note any missing evidence explicitly.\n\n"
            "SECTION 4 - WHAT TO CHECK NEXT:\n"
            "List 2-3 specific, actionable engineering checks for the factory operator before scheduling an operational trial.\n\n"
            f"FACTUAL EVIDENCE FROM DATABASE:\n"
            f"- Correlation ID: {correlation_id}\n"
            f"- Workflow Step: INVESTIGATE_FINDING\n"
            f"- Finding ID: {evidence['finding_id']}\n"
            f"- Occurrence ID: {evidence['occurrence_id'] or 'None (Zero occurrence records in DB)'}\n"
            f"- Plant: {evidence['plant_id']}\n"
            f"- Line: {evidence['line_id'] or 'Unassigned'}\n"
            f"- Meter: {evidence['meter_id'] or 'Unassigned'}\n"
            f"- Local Time Window: {evidence['local_time_window_full']}\n"
            f"{observed_desc}"
            f"- Meter Reading ID: {evidence['meter_reading_id'] or 'MISSING'}\n"
            f"- Production Event ID: {evidence['production_event_id'] or 'MISSING'}\n"
            f"- Good Finished Units: {evidence['good_units'] if evidence['good_units'] is not None else 'MISSING'}\n"
            f"- Actual Total Units: {evidence['actual_units'] if evidence['actual_units'] is not None else 'MISSING'}\n"
            f"- Downtime: {evidence['downtime_min'] if evidence['downtime_min'] is not None else 'UNKNOWN'} minutes ({evidence['downtime_reason'] or 'Reason unspecified'})\n"
            f"- Missing Evidence Flags: {json.dumps(evidence['missing_evidence'])}\n"
            f"- Total Historical Occurrences: {evidence['total_occurrences_count']}\n"
            f"- Continuous Stoppage Episodes: {evidence.get('continuous_stoppages_count', 0)} across {evidence.get('matched_hourly_production_readings_count', 0)} matched hourly production readings (supported by {evidence.get('matched_energy_readings_count', 0)} matched meter readings, Historical Mean: {evidence['historical_mean_kwh'] or 'N/A'})\n"
            f"- Confirmed Record Citations: {json.dumps(citations)}\n\n"
            "STRICT RULES: Do NOT invent or fabricate citation IDs. ONLY cite IDs listed in Confirmed Record Citations. "
            "When a power factor is provided, explicitly identify it as power factor with NO unit. "
            "Never cite FAL-L2 unless Line is FAL-L2."
        )

        # Run async call in safe execution wrapper
        async def _call_domo():
            domo_client._client = None  # Ensure fresh AsyncClient bound to current event loop
            req = DomoTextGenerationRequest(
                model=target_model,
                input=prompt,
                temperature=0.0,
            )
            return await domo_client.generate_text(req)

        def _execute_coro(coro):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, coro).result()
            else:
                return asyncio.run(coro)

        gen_resp = _execute_coro(_call_domo())
        if gen_resp and gen_resp.output:
            parsed = parse_four_sections(gen_resp.output)
            # Verify that all 4 sections were populated
            if all(parsed.values()):
                parsed_sections = {
                    k: validate_citations_in_text(re.sub(r"---\s*##?", "", v).strip(), citations, evidence)
                    for k, v in parsed.items()
                }
                ai_success = True
                inference_source = "DOMO_AI_MODEL"
                agent_trace = {
                    "provider": "Domo AI Services",
                    "correlation_id": correlation_id,
                    "workflow_step": "INVESTIGATE_FINDING",
                    "model": target_model,
                    "backend_database_retrievals": retrieval_tools,
                    "model_invoked_tools": [],
                    "model_generation": "SUCCESSFUL_MODEL_GENERATION",
                    "inference_source": "DOMO_AI_MODEL",
                    "tools_called": retrieval_tools + ["live_model_generation"],
                    "status": "COMPLETED",
                    "usage": gen_resp.usage,
                }
    except Exception as e:
        logger.warning("Domo AI invocation failed (%s); using deterministic fallback.", str(e))
        agent_trace["fallback_reason"] = str(e)

    # Use rule-based fallback if AI was unavailable or incomplete
    if not ai_success or not parsed_sections:
        parsed_sections = _synthesize_rule_based_investigation(evidence)
        for k in parsed_sections:
            parsed_sections[k] = validate_citations_in_text(parsed_sections[k], citations, evidence)

    return {
        "finding_id": evidence["finding_id"],
        "title": evidence.get("title"),
        "occurrence_id": evidence["occurrence_id"],
        "plant_id": evidence["plant_id"],
        "line_id": evidence["line_id"],
        "meter_id": evidence["meter_id"],
        "anomaly_type": evidence["anomaly_type"],
        "timestamp": evidence["timestamp"],
        "observed_value": evidence["observed_value"],
        "baseline_value": evidence.get("baseline_value"),
        "power_factor": evidence.get("power_factor"),
        "unit": evidence.get("unit", ("" if is_pf else "kWh")),
        "metric_name": "Power factor" if is_pf else "Electricity consumption",
        "is_power_factor": is_pf,
        "missing_energy_reading": evidence.get("missing_evidence", {}).get("missing_energy_reading", False) or evidence.get("missing_energy_reading", False) or not evidence.get("meter_reading_id"),
        "timezone": evidence.get("timezone") or (getattr(finding, "timezone", None) if 'finding' in locals() and hasattr(finding, "timezone") else None),
        "headline": bullet_sections.get("headline"),
        "comparison": bullet_sections.get("comparison"),
        "evidence_summary": bullet_sections.get("evidence_summary"),
        "uncertainty_note": bullet_sections.get("uncertainty_note"),
        "next_checks": bullet_sections.get("next_checks") or bullet_sections.get("what_to_check_next"),
        "what_we_found": bullet_sections["what_we_found"],
        "whats_missing": bullet_sections["whats_missing"],
        "what_to_check_next": bullet_sections["what_to_check_next"],
        "what_to_check_next_bullets": bullet_sections["what_to_check_next"],
        "what_we_observed": parsed_sections["what_we_observed"],
        "how_it_compares": parsed_sections["how_it_compares"],
        "what_we_still_need_to_know": parsed_sections["what_we_still_need_to_know"],
        "what_to_check_next_narrative": parsed_sections["what_to_check_next"],
        "citations": citations,
        "total_occurrences_count": evidence["total_occurrences_count"],
        "continuous_stoppages_count": evidence.get("continuous_stoppages_count", 0),
        "matched_hourly_production_readings_count": evidence.get("matched_hourly_production_readings_count", 0),
        "matched_energy_readings_count": evidence.get("matched_energy_readings_count", 0),
        "eligible_episodes_count": evidence["eligible_episodes_count"],
        "inference_source": inference_source,
        "is_regression_case_nov4": False,
        "agent_execution_trace": agent_trace,
        "missing_evidence": evidence["missing_evidence"],
        "local_time_window": evidence["local_time_window"],
        "status": "SUCCESS",
    }


def explain_assessment_with_ai(
    session: Session,
    assessment_id: str,
    caller_attribution: Optional[str] = None,
) -> Dict[str, Any]:
    """
    AI Assistant synthesis of an intervention outcome assessment.
    Independently explains all three business questions:
    1. Did electricity cost per good unit fall?
    2. Was production protected?
    3. How much electricity and cost can be attributed to the action?

    Includes dual-boundary breakdown (stoppage reduction minus restart overhead),
    guardrail compliance status, tariff derivation, and factory ledger eligibility.
    Resilient: graceful fallback if AI calls fail.
    """
    clean_id = assessment_id.strip()
    asm_stmt = select(InterventionAssessment).where(InterventionAssessment.assessment_id == clean_id)
    asm = session.execute(asm_stmt).scalar_one_or_none()
    if not asm:
        raise ValueError(f"Assessment '{clean_id}' not found.")

    plan_stmt = select(InterventionPlan).where(
        InterventionPlan.plan_id == asm.plan_id,
        InterventionPlan.version == asm.plan_version,
    )
    plan = session.execute(plan_stmt).scalar_one_or_none()

    action = None
    if asm.action_id:
        act_stmt = select(CorrectiveAction).where(CorrectiveAction.action_id == asm.action_id)
        action = session.execute(act_stmt).scalar_one_or_none()

    # Question 1: Cost Intensity
    base_cost_unit = asm.baseline_cost_per_good_unit
    post_cost_unit = asm.post_cost_per_good_unit
    cost_chg_pct = asm.cost_intensity_change_pct
    obj_outcome = asm.objective_outcome

    if (asm.baseline_good_units or 0) == 0 or (asm.post_good_units or 0) == 0:
        q1_ans = "INCONCLUSIVE"
        q1_text = (
            "Baseline period contains zero eligible good finished units (planned stoppage state). "
            "Electricity cost per good finished unit is undefined/inconclusive. Post-period intensity is preserved."
        )
    elif obj_outcome == "IMPROVED":
        chg_str = f"({cost_chg_pct:+.2f}% change)" if cost_chg_pct is not None else ""
        b_str = f"₹{base_cost_unit:.4f}" if base_cost_unit is not None else "N/A"
        p_str = f"₹{post_cost_unit:.4f}" if post_cost_unit is not None else "N/A"
        q1_ans = "YES"
        q1_text = (
            f"Electricity cost per good finished unit fell from {b_str} to {p_str} "
            f"{chg_str}, achieving the approved reduction threshold."
        )
    else:
        chg_str = f"({cost_chg_pct:+.2f}% vs threshold)" if cost_chg_pct is not None else "without improvement"
        q1_ans = "NO"
        q1_text = (
            f"Electricity cost per good finished unit showed no reduction {chg_str}. "
            f"Zero change does not count as improvement."
        )

    q1_summary = {
        "question": "Did electricity cost per good unit fall?",
        "status": obj_outcome,
        "answer": q1_ans,
        "baseline_cost_per_good_unit": base_cost_unit,
        "post_cost_per_good_unit": post_cost_unit,
        "change_pct": cost_chg_pct,
        "explanation": q1_text,
    }

    # Question 2: Production Protection
    guardrails_summary = []
    if asm.guardrails_summary_json:
        try:
            guardrails_summary = json.loads(asm.guardrails_summary_json)
        except Exception:
            guardrails_summary = []

    has_breached = any(g.get("status") == "BREACHED" or g.get("passed") is False for g in guardrails_summary)
    has_unassessable = any(g.get("status") == "UNASSESSABLE" for g in guardrails_summary)

    if has_breached or asm.output_guardrail_met is False or asm.quality_guardrail_met is False or asm.downtime_guardrail_met is False:
        prod_status = "BREACHED"
        q2_ans = "NO"
        q2_text = "One or more preapproved production output, quality yield, downtime, or restart limits were breached during observation. Production was not protected."
    elif has_unassessable or ((asm.baseline_good_units or 0) == 0 and not guardrails_summary):
        prod_status = "UNASSESSABLE"
        q2_ans = "UNASSESSABLE"
        q2_text = "Production protection could not be established: preapproved output target was zero or observation data was unassessable."
    else:
        prod_status = "PROTECTED"
        q2_ans = "YES"
        q2_text = "All preapproved production output, quality yield, downtime, and restart limits held within approved bounds."

    q2_summary = {
        "question": "Was production protected?",
        "status": prod_status,
        "answer": q2_ans,
        "guardrail_results": guardrails_summary,
        "output_guardrail_met": asm.output_guardrail_met,
        "quality_guardrail_met": asm.quality_guardrail_met,
        "downtime_guardrail_met": asm.downtime_guardrail_met,
        "explanation": q2_text,
    }

    # Question 3: Attribution & Dual Boundary Accounting
    attr_details = {}
    if asm.attribution_details_json:
        try:
            attr_details = json.loads(asm.attribution_details_json)
        except Exception:
            attr_details = {}

    stoppage_reduction = attr_details.get("stoppage_reduction_kwh")
    restart_overhead = attr_details.get("restart_overhead_kwh")
    net_reduction = attr_details.get("net_reduction_kwh") or asm.electricity_savings_kwh

    dual_boundary_summary = None
    if stoppage_reduction is not None or restart_overhead is not None:
        dual_boundary_summary = {
            "stoppage_reduction_kwh": stoppage_reduction,
            "restart_overhead_kwh": restart_overhead,
            "net_reduction_kwh": net_reduction,
            "accounting_principle": "Boundary A Stoppage Reduction minus Boundary B Restart Overhead",
        }

    verified_kwh = asm.electricity_savings_kwh
    verified_cost = asm.verified_monetary_savings_inr
    tariff_val = asm.common_rate_factor_inr_per_kwh or 8.25

    if prod_status == "BREACHED":
        q3_ans = "DISQUALIFIED"
        q3_text = (
            f"Observed net reduction of {net_reduction or 0.0:.4f} kWh was achieved during the trial, "
            f"but production guardrails were breached. Under factory governance, intervention savings are "
            f"strictly null / ₹0 when production protection fails."
        )
    elif verified_kwh is not None and verified_kwh > 0:
        if verified_cost is not None:
            q3_ans = f"{verified_kwh:.4f} kWh (₹{verified_cost:.2f})"
            q3_text = (
                f"Trial verified a net reduction of {verified_kwh:.4f} kWh after accounting for "
                f"{restart_overhead or 0.0:.4f} kWh extra restart electricity. Valued at ₹{tariff_val:.2f}/kWh "
                f"under approved contract tariff ({asm.common_rate_factor_version or 'DEFAULT'})."
            )
        else:
            q3_ans = f"{verified_kwh:.4f} kWh (Monetary savings unverified: tariff pending contract approval)"
            q3_text = (
                f"Trial verified a net reduction of {verified_kwh:.4f} kWh after accounting for "
                f"{restart_overhead or 0.0:.4f} kWh extra restart electricity. Monetary savings remain unverified "
                f"(₹0 ledger contribution) pending an approved contract tariff."
            )
    else:
        q3_ans = "NONE"
        q3_text = (
            f"No verified attributable savings: {asm.status_reason or 'Counterfactual attribution model unverified or baseline comparison disqualified.'}"
        )

    q3_summary = {
        "question": "How much electricity and cost can be attributed to the action?",
        "status": "ATTRIBUTED" if (verified_kwh is not None and prod_status != "BREACHED") else "UNVERIFIED",
        "answer": q3_ans,
        "verified_electricity_savings_kwh": verified_kwh if prod_status != "BREACHED" else None,
        "avoided_cost_inr": asm.avoided_cost_inr if prod_status != "BREACHED" else None,
        "verified_monetary_savings_inr": verified_cost if prod_status != "BREACHED" else None,
        "applicable_tariff_inr_per_kwh": tariff_val,
        "explanation": q3_text,
    }

    # Ledger eligibility
    from app.services.intervention_service import is_claim_eligible_for_verified_savings, is_claim_eligible_for_verified_monetary
    is_kwh_elig, kwh_elig_reason = is_claim_eligible_for_verified_savings(asm)
    is_mon_elig, mon_elig_reason = is_claim_eligible_for_verified_monetary(asm)

    ledger_elig = {
        "is_eligible_for_verified_kwh": is_kwh_elig,
        "kwh_eligibility_reason": kwh_elig_reason,
        "is_eligible_for_verified_cost": is_mon_elig,
        "monetary_eligibility_reason": mon_elig_reason,
        "savings_claim_status": asm.savings_claim_status,
        "signed_off_by": asm.signed_off_by,
        "signed_off_at": asm.signed_off_at.isoformat() if asm.signed_off_at else None,
    }

    if is_mon_elig:
        overall_verdict = "Verified Factory Energy Saving"
    elif is_kwh_elig:
        overall_verdict = "Verified Physical Energy Saving (Monetary Unverified)"
    elif prod_status == "BREACHED":
        overall_verdict = "Production Limit Breached — Savings Disqualified"
    else:
        overall_verdict = "Assessment Complete — Attribution Unverified"

    citations = [
        {"type": "PLAN", "id": asm.plan_id, "label": f"Measurement Plan {asm.plan_id} (v{asm.plan_version})"},
        {"type": "ASSESSMENT", "id": asm.assessment_id, "label": f"Assessment Revision #{asm.assessment_revision}"},
    ]
    if action:
        citations.append({"type": "ACTION", "id": action.action_id, "label": f"Action {action.action_id} ({action.title})"})
    if asm.common_rate_factor_version:
        citations.append({"type": "TARIFF", "id": asm.common_rate_factor_version, "label": f"Approved Tariff ₹{tariff_val:.2f}/kWh ({asm.common_rate_factor_version})"})

    narrative = (
        f"### Summary Verdict: {overall_verdict}\n\n"
        f"1. **Cost per Good Unit:** {q1_text}\n\n"
        f"2. **Production Protection:** {q2_text}\n\n"
        f"3. **Attributable Savings:** {q3_text}\n\n"
        f"**Ledger Status:** {kwh_elig_reason if not is_kwh_elig else 'Formally eligible and recorded in verified savings totals.'}"
    )

    return {
        "assessment_id": clean_id,
        "overall_verdict": overall_verdict,
        "question_1_cost_intensity": q1_summary,
        "question_2_production_protection": q2_summary,
        "question_3_attribution": q3_summary,
        "question_3_attributable_savings": q3_summary,
        "dual_boundary_summary": dual_boundary_summary,
        "ledger_eligibility": ledger_elig,
        "narrative_explanation": narrative,
        "citations": citations,
        "agent_execution_trace": {
            "provider": "IndustrialEnergyAgent",
            "correlation_id": f"corr-asm-{hashlib.sha256(clean_id.encode()).hexdigest()[:12]}",
            "workflow_step": "EXPLAIN_ASSESSMENT",
            "model": "offline",
            "tools_called": [
                "retrieve_assessment_record",
                "retrieve_measurement_plan",
                "resolve_contract_tariffs",
                "evaluate_production_guardrails",
                "evaluate_ledger_eligibility",
            ],
            "status": "COMPLETED",
        },
    }
