"""Deterministic energy intensity (SEC) and process-energy service."""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models.source_data import (
    DimProduct,
    DimProductionLine,
    FactEnergyMeterHourly,
    FactHourlyProduction,
)

FACILITY_UTILITY_METERS = ["MTR-HVAC", "MTR-COMPRESSOR", "MTR-CHILLER"]


def validate_line_meter_topology(session: Session, plant_id: Optional[str] = None) -> None:
    """
    Verify the 1:1 line-to-process-meter topology assumption.
    The current factory schema provides one MTR-SMT and one MTR-FAL meter per plant.
    If multiple lines of the same type exist in a single plant without dedicated sub-metering,
    fail safely rather than producing multiplied/duplicated energy totals.
    """
    q = select(
        DimProductionLine.plant_id,
        DimProductionLine.line_type,
        func.count(DimProductionLine.line_id).label("line_count"),
    ).group_by(
        DimProductionLine.plant_id,
        DimProductionLine.line_type,
    )
    if plant_id:
        q = q.where(DimProductionLine.plant_id == plant_id)
    rows = session.execute(q).fetchall()
    for pid, ltype, count in rows:
        if count > 1:
            raise ValueError(
                f"Multi-line topology limitation: Plant '{pid}' has {count} lines configured for '{ltype}', "
                f"but the telemetry schema only provides a single plant-level process meter. "
                f"Line-level energy cannot be allocated safely without dedicated sub-metering."
            )


def _process_meter_condition():
    """Deterministic join condition connecting production line to its dedicated process meter."""
    return or_(
        and_(FactHourlyProduction.line_id.in_(["SMT-L1", "SMT-L2"]), FactEnergyMeterHourly.meter_id == "MTR-SMT"),
        and_(FactHourlyProduction.line_id.in_(["FAL-L1", "FAL-L2"]), FactEnergyMeterHourly.meter_id == "MTR-FAL"),
    )


def get_process_energy_analytics(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Calculate process-level energy consumption and Specific Energy Consumption (SEC).
    SEC is calculated strictly as process meter kWh divided by actual line output.
    Returns None for SEC when production output is zero (safe zero-division guard).
    """
    validate_line_meter_topology(session, plant_id)
    conditions = [
        FactHourlyProduction.event_ts == FactEnergyMeterHourly.timestamp,
        FactHourlyProduction.plant_id == FactEnergyMeterHourly.plant_id,
        _process_meter_condition(),
    ]
    if plant_id:
        conditions.append(FactHourlyProduction.plant_id == plant_id)
    if start_date:
        conditions.append(FactHourlyProduction.event_date >= start_date)
    if end_date:
        conditions.append(FactHourlyProduction.event_date <= end_date)

    q = select(
        FactHourlyProduction.line_id,
        FactHourlyProduction.plant_id,
        DimProductionLine.line_type,
        FactEnergyMeterHourly.meter_id,
        func.sum(FactHourlyProduction.actual_qty).label("total_actual_qty"),
        func.sum(FactHourlyProduction.good_qty).label("total_good_qty"),
        func.sum(FactEnergyMeterHourly.consumption_kwh).label("total_process_kwh"),
        func.sum(FactEnergyMeterHourly.cost_inr).label("total_process_cost"),
        func.sum(FactEnergyMeterHourly.co2e_kg).label("total_process_co2e"),
        func.count(FactHourlyProduction.event_id).label("hours_count"),
        func.sum(case((FactHourlyProduction.actual_qty == 0, 1), else_=0)).label("zero_output_hours"),
    ).join(
        DimProductionLine,
        and_(
            FactHourlyProduction.line_id == DimProductionLine.line_id,
            FactHourlyProduction.plant_id == DimProductionLine.plant_id,
        ),
    ).join(
        FactEnergyMeterHourly,
        and_(*conditions),
    ).group_by(
        FactHourlyProduction.line_id,
        FactHourlyProduction.plant_id,
        DimProductionLine.line_type,
        FactEnergyMeterHourly.meter_id,
    ).order_by(FactHourlyProduction.line_id.asc())

    rows = session.execute(q).fetchall()

    line_results = []
    overall_smt_kwh = Decimal("0")
    overall_smt_qty = 0
    overall_fal_kwh = Decimal("0")
    overall_fal_qty = 0

    for r in rows:
        actual_qty = int(r[4])
        good_qty = int(r[5])
        process_kwh = Decimal(str(r[6]))
        cost_inr = Decimal(str(r[7]))
        co2e_kg = Decimal(str(r[8]))

        sec_actual = round(process_kwh / actual_qty, 4) if actual_qty > 0 else None
        sec_good = round(process_kwh / good_qty, 4) if good_qty > 0 else None

        line_type = r[2]
        if line_type == "SMT":
            overall_smt_kwh += process_kwh
            overall_smt_qty += actual_qty
        elif line_type == "Final Assembly":
            overall_fal_kwh += process_kwh
            overall_fal_qty += actual_qty

        line_results.append({
            "line_id": r[0],
            "plant_id": r[1],
            "line_type": line_type,
            "meter_id": r[3],
            "actual_qty": actual_qty,
            "good_qty": good_qty,
            "process_kwh": process_kwh,
            "process_cost_inr": cost_inr,
            "process_co2e_kg": co2e_kg,
            "process_sec_actual_kwh_per_unit": sec_actual,
            "process_sec_good_kwh_per_unit": sec_good,
            "operating_hours": int(r[9]),
            "zero_output_hours": int(r[10]),
        })

    smt_overall_sec = round(overall_smt_kwh / overall_smt_qty, 4) if overall_smt_qty > 0 else None
    fal_overall_sec = round(overall_fal_kwh / overall_fal_qty, 4) if overall_fal_qty > 0 else None

    return {
        "plant_id": plant_id,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "lines": line_results,
        "smt_summary": {
            "total_process_kwh": overall_smt_kwh,
            "total_actual_qty": overall_smt_qty,
            "overall_process_sec_kwh_per_board": smt_overall_sec,
        },
        "fal_summary": {
            "total_process_kwh": overall_fal_kwh,
            "total_actual_qty": overall_fal_qty,
            "overall_process_sec_kwh_per_phone": fal_overall_sec,
        },
    }


def get_factory_energy_analytics(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Calculate factory-level energy metrics and Factory SEC.
    - Factory SEC = Total Plant Energy (all 5 meters) / Final Assembly Output.
    - Facility utility consumption (HVAC, Compressor, Chiller) is reported separately.
    """
    # 1. Total Plant Energy across all 5 meters
    e_conditions = []
    if plant_id:
        e_conditions.append(FactEnergyMeterHourly.plant_id == plant_id)
    if start_date:
        e_conditions.append(FactEnergyMeterHourly.date >= start_date)
    if end_date:
        e_conditions.append(FactEnergyMeterHourly.date <= end_date)

    q_total = select(
        func.coalesce(func.sum(FactEnergyMeterHourly.consumption_kwh), Decimal("0")),
        func.coalesce(func.sum(FactEnergyMeterHourly.cost_inr), Decimal("0")),
        func.coalesce(func.sum(FactEnergyMeterHourly.co2e_kg), Decimal("0")),
    )
    if e_conditions:
        q_total = q_total.where(and_(*e_conditions))
    row_total = session.execute(q_total).fetchone()

    total_plant_kwh = Decimal(str(row_total[0]))
    total_plant_cost = Decimal(str(row_total[1]))
    total_plant_co2e = Decimal(str(row_total[2]))

    # 2. Facility Utilities Breakdown (MTR-HVAC, MTR-COMPRESSOR, MTR-CHILLER)
    q_util = select(
        FactEnergyMeterHourly.meter_id,
        FactEnergyMeterHourly.area,
        func.sum(FactEnergyMeterHourly.consumption_kwh).label("kwh"),
        func.sum(FactEnergyMeterHourly.cost_inr).label("cost"),
        func.sum(FactEnergyMeterHourly.co2e_kg).label("co2e"),
    ).where(FactEnergyMeterHourly.meter_id.in_(FACILITY_UTILITY_METERS))
    if e_conditions:
        q_util = q_util.where(and_(*e_conditions))
    q_util = q_util.group_by(FactEnergyMeterHourly.meter_id, FactEnergyMeterHourly.area)
    util_rows = session.execute(q_util).fetchall()

    facility_utilities = []
    total_utility_kwh = Decimal("0")
    for ur in util_rows:
        ukwh = Decimal(str(ur[2]))
        total_utility_kwh += ukwh
        facility_utilities.append({
            "meter_id": ur[0],
            "area": ur[1],
            "consumption_kwh": ukwh,
            "cost_inr": Decimal(str(ur[3])),
            "co2e_kg": Decimal(str(ur[4])),
            "percentage_of_plant_total": round(ukwh / total_plant_kwh * 100, 2) if total_plant_kwh > 0 else Decimal("0"),
        })

    utility_share_pct = round(total_utility_kwh / total_plant_kwh * 100, 2) if total_plant_kwh > 0 else Decimal("0")

    # 3. Final Assembly Output (Finished Goods Gate)
    p_conditions = [FactHourlyProduction.line_id.in_(["FAL-L1", "FAL-L2"])]
    if plant_id:
        p_conditions.append(FactHourlyProduction.plant_id == plant_id)
    if start_date:
        p_conditions.append(FactHourlyProduction.event_date >= start_date)
    if end_date:
        p_conditions.append(FactHourlyProduction.event_date <= end_date)

    q_fal = select(
        func.coalesce(func.sum(FactHourlyProduction.actual_qty), 0),
        func.coalesce(func.sum(FactHourlyProduction.good_qty), 0),
    ).where(and_(*p_conditions))
    row_fal = session.execute(q_fal).fetchone()

    fal_actual_qty = int(row_fal[0]) if row_fal else 0
    fal_good_qty = int(row_fal[1]) if row_fal else 0

    # 4. Factory SEC = Total Plant Energy / FAL Output
    factory_sec_actual = round(total_plant_kwh / fal_actual_qty, 4) if fal_actual_qty > 0 else None
    factory_sec_good = round(total_plant_kwh / fal_good_qty, 4) if fal_good_qty > 0 else None

    return {
        "plant_id": plant_id,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "total_plant_energy_kwh": total_plant_kwh,
        "total_plant_cost_inr": total_plant_cost,
        "total_plant_co2e_kg": total_plant_co2e,
        "final_assembly_actual_output": fal_actual_qty,
        "final_assembly_good_output": fal_good_qty,
        "factory_sec_kwh_per_finished_unit": factory_sec_actual,
        "factory_sec_good_kwh_per_finished_unit": factory_sec_good,
        "facility_utilities": {
            "total_utility_consumption_kwh": total_utility_kwh,
            "utility_share_percentage": utility_share_pct,
            "meters": facility_utilities,
        },
    }


def get_product_process_energy(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """
    Calculate direct process energy consumed while manufacturing each product SKU.
    Uses exact timestamp/plant/process-meter matching.
    Facility utilities are NOT allocated to products.
    """
    conditions = [
        FactHourlyProduction.event_ts == FactEnergyMeterHourly.timestamp,
        FactHourlyProduction.plant_id == FactEnergyMeterHourly.plant_id,
        _process_meter_condition(),
    ]
    if plant_id:
        conditions.append(FactHourlyProduction.plant_id == plant_id)
    if start_date:
        conditions.append(FactHourlyProduction.event_date >= start_date)
    if end_date:
        conditions.append(FactHourlyProduction.event_date <= end_date)

    q = select(
        FactHourlyProduction.product_id,
        DimProduct.product_name,
        DimProduct.product_family,
        DimProductionLine.line_type,
        func.sum(FactHourlyProduction.actual_qty).label("actual_qty"),
        func.sum(FactHourlyProduction.good_qty).label("good_qty"),
        func.sum(FactEnergyMeterHourly.consumption_kwh).label("process_kwh"),
        func.sum(FactEnergyMeterHourly.cost_inr).label("process_cost"),
    ).join(
        DimProduct,
        FactHourlyProduction.product_id == DimProduct.product_id,
    ).join(
        DimProductionLine,
        and_(
            FactHourlyProduction.line_id == DimProductionLine.line_id,
            FactHourlyProduction.plant_id == DimProductionLine.plant_id,
        ),
    ).join(
        FactEnergyMeterHourly,
        and_(*conditions),
    ).group_by(
        FactHourlyProduction.product_id,
        DimProduct.product_name,
        DimProduct.product_family,
        DimProductionLine.line_type,
    ).order_by(FactHourlyProduction.product_id.asc(), DimProductionLine.line_type.asc())

    rows = session.execute(q).fetchall()

    # Consolidate by SKU
    skus = {}
    for r in rows:
        pid = r[0]
        if pid not in skus:
            skus[pid] = {
                "product_id": pid,
                "product_name": r[1],
                "product_family": r[2],
                "smt_process_kwh": Decimal("0"),
                "smt_actual_qty": 0,
                "fal_process_kwh": Decimal("0"),
                "fal_actual_qty": 0,
                "total_direct_process_kwh": Decimal("0"),
                "total_process_cost_inr": Decimal("0"),
            }

        line_type = r[3]
        qty = int(r[4])
        kwh = Decimal(str(r[6]))
        cost = Decimal(str(r[7]))

        skus[pid]["total_direct_process_kwh"] += kwh
        skus[pid]["total_process_cost_inr"] += cost

        if line_type == "SMT":
            skus[pid]["smt_process_kwh"] += kwh
            skus[pid]["smt_actual_qty"] += qty
        elif line_type == "Final Assembly":
            skus[pid]["fal_process_kwh"] += kwh
            skus[pid]["fal_actual_qty"] += qty

    results = []
    for pid, data in sorted(skus.items()):
        fal_qty = data["fal_actual_qty"]
        smt_qty = data["smt_actual_qty"]
        tot_kwh = data["total_direct_process_kwh"]

        # SEC by stage: explicit stage-specific attribution
        smt_sec = round(data["smt_process_kwh"] / smt_qty, 4) if smt_qty > 0 else None
        fal_sec = round(data["fal_process_kwh"] / fal_qty, 4) if fal_qty > 0 else None
        # Finished-phone combined SEC across decoupled stages is unavailable without WIP tracking:
        # SMT produces boards, FAL produces phones, and lines process different products asynchronously.
        combined_process_sec = None

        results.append({
            "product_id": pid,
            "product_name": data["product_name"],
            "product_family": data["product_family"],
            "smt_actual_units": smt_qty,
            "fal_actual_units": fal_qty,
            "smt_process_kwh": data["smt_process_kwh"],
            "fal_process_kwh": data["fal_process_kwh"],
            "total_direct_process_kwh": tot_kwh,
            "total_process_cost_inr": data["total_process_cost_inr"],
            "smt_process_sec_kwh_per_board": smt_sec,
            "fal_process_sec_kwh_per_phone": fal_sec,
            "finished_phone_process_sec_kwh_per_unit": combined_process_sec,
            "finished_phone_sec_status": (
                "UNAVAILABLE: SMT and FAL lines operate asynchronously with intermediate inventory buffering; "
                "finished-unit SEC across decoupled process stages cannot be mathematically verified without WIP lot-tracking telemetry."
            ),
            "scope_note": (
                "Direct manufacturing process energy only. Stage-specific SEC is calculated separately for SMT (kWh/board) "
                "and FAL (kWh/phone). Combined finished-phone SEC is unavailable across decoupled stages without WIP lot-tracking telemetry."
            ),
        })

    return results


def get_zero_production_period_energy(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Identify energy consumed during hours with zero recorded production.
    Reported strictly as zero-production-period energy (standby/idle energy),
    without automatically labeling it avoidable waste.
    """
    validate_line_meter_topology(session, plant_id)
    conditions = [
        FactHourlyProduction.event_ts == FactEnergyMeterHourly.timestamp,
        FactHourlyProduction.plant_id == FactEnergyMeterHourly.plant_id,
        _process_meter_condition(),
        FactHourlyProduction.actual_qty == 0,
    ]
    if plant_id:
        conditions.append(FactHourlyProduction.plant_id == plant_id)
    if start_date:
        conditions.append(FactHourlyProduction.event_date >= start_date)
    if end_date:
        conditions.append(FactHourlyProduction.event_date <= end_date)

    q = select(
        FactHourlyProduction.line_id,
        FactHourlyProduction.plant_id,
        FactHourlyProduction.downtime_reason,
        FactEnergyMeterHourly.meter_id,
        func.count(FactHourlyProduction.event_id).label("zero_prod_hours"),
        func.sum(FactEnergyMeterHourly.consumption_kwh).label("standby_kwh"),
        func.sum(FactEnergyMeterHourly.cost_inr).label("standby_cost"),
        func.avg(FactEnergyMeterHourly.consumption_kwh).label("avg_standby_kwh_per_hr"),
    ).join(
        FactEnergyMeterHourly,
        and_(*conditions),
    ).group_by(
        FactHourlyProduction.line_id,
        FactHourlyProduction.plant_id,
        FactHourlyProduction.downtime_reason,
        FactEnergyMeterHourly.meter_id,
    ).order_by(FactHourlyProduction.line_id.asc(), func.sum(FactEnergyMeterHourly.consumption_kwh).desc())

    rows = session.execute(q).fetchall()

    by_reason = {}
    by_line = {}
    total_zero_hours = 0
    total_standby_kwh = Decimal("0")
    total_standby_cost = Decimal("0")

    for r in rows:
        line_id = r[0]
        plant = r[1]
        reason = r[2]
        meter_id = r[3]
        hours = int(r[4])
        kwh = Decimal(str(r[5]))
        cost = Decimal(str(r[6]))
        avg_hourly = round(Decimal(str(r[7])), 2)

        total_zero_hours += hours
        total_standby_kwh += kwh
        total_standby_cost += cost

        # Group by line
        by_line.setdefault(line_id, {
            "line_id": line_id,
            "plant_id": plant,
            "meter_id": meter_id,
            "zero_production_hours": 0,
            "standby_consumption_kwh": Decimal("0"),
            "standby_cost_inr": Decimal("0"),
        })
        by_line[line_id]["zero_production_hours"] += hours
        by_line[line_id]["standby_consumption_kwh"] += kwh
        by_line[line_id]["standby_cost_inr"] += cost

        # Group by reason
        by_reason.setdefault(reason, {
            "downtime_reason": reason,
            "hours": 0,
            "consumption_kwh": Decimal("0"),
            "cost_inr": Decimal("0"),
        })
        by_reason[reason]["hours"] += hours
        by_reason[reason]["consumption_kwh"] += kwh
        by_reason[reason]["cost_inr"] += cost

    line_summaries = []
    for lid, d in sorted(by_line.items()):
        hrs = d["zero_production_hours"]
        kwh = d["standby_consumption_kwh"]
        d["avg_standby_kwh_per_hr"] = round(kwh / hrs, 2) if hrs > 0 else Decimal("0")
        line_summaries.append(d)

    reason_summaries = sorted(by_reason.values(), key=lambda x: x["consumption_kwh"], reverse=True)

    return {
        "plant_id": plant_id,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "total_zero_production_hours": total_zero_hours,
        "total_zero_production_energy_kwh": total_standby_kwh,
        "total_zero_production_cost_inr": total_standby_cost,
        "overall_avg_standby_kwh_per_hr": round(total_standby_kwh / total_zero_hours, 2) if total_zero_hours > 0 else Decimal("0"),
        "by_line": line_summaries,
        "by_downtime_reason": reason_summaries,
        "classification_note": "Energy recorded during zero production represents fixed equipment standby/idle draw during downtime events, not automatically avoidable waste.",
    }

