"""Deterministic energy intensity (SEC) and process-energy service."""

from datetime import date, datetime
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


def _decimal_or_none(value):
    return Decimal(str(value)) if value is not None else None


def _int_or_none(value):
    return int(value) if value is not None else None


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
    - Factory SEC uses total plant energy and Final Assembly output from matching plant-hour records.
    - Full requested-scope energy and production totals are reported separately.
    - Facility utility consumption (HVAC, Compressor, Chiller) is reported separately.
    """
    # 1. Full requested-scope energy totals, separate from the aligned SEC numerator.
    e_conditions = []
    if plant_id:
        e_conditions.append(FactEnergyMeterHourly.plant_id == plant_id)
    if start_date:
        e_conditions.append(FactEnergyMeterHourly.date >= start_date)
    if end_date:
        e_conditions.append(FactEnergyMeterHourly.date <= end_date)

    q_total = select(
        func.sum(FactEnergyMeterHourly.consumption_kwh),
        func.sum(FactEnergyMeterHourly.cost_inr),
        func.sum(FactEnergyMeterHourly.co2e_kg),
        func.count(FactEnergyMeterHourly.meter_reading_id),
    )
    if e_conditions:
        q_total = q_total.where(and_(*e_conditions))
    row_total = session.execute(q_total).fetchone()

    total_plant_kwh = _decimal_or_none(row_total[0]) if row_total else None
    total_plant_cost = _decimal_or_none(row_total[1]) if row_total else None
    total_plant_co2e = _decimal_or_none(row_total[2]) if row_total else None
    total_energy_readings = int(row_total[3]) if row_total and row_total[3] is not None else 0

    # 2. Facility Utilities Breakdown (MTR-HVAC, MTR-COMPRESSOR, MTR-CHILLER)
    q_util = select(
        FactEnergyMeterHourly.meter_id,
        FactEnergyMeterHourly.area,
        func.sum(FactEnergyMeterHourly.consumption_kwh).label("kwh"),
        func.sum(FactEnergyMeterHourly.cost_inr).label("cost"),
        func.sum(FactEnergyMeterHourly.co2e_kg).label("co2e"),
        func.count(FactEnergyMeterHourly.meter_reading_id).label("reading_count"),
    ).where(FactEnergyMeterHourly.meter_id.in_(FACILITY_UTILITY_METERS))
    if e_conditions:
        q_util = q_util.where(and_(*e_conditions))
    q_util = q_util.group_by(FactEnergyMeterHourly.meter_id, FactEnergyMeterHourly.area)
    util_rows = session.execute(q_util).fetchall()

    facility_utilities = []
    utility_kwh_values = []
    for ur in util_rows:
        ukwh = _decimal_or_none(ur[2])
        utility_cost = _decimal_or_none(ur[3])
        utility_co2e = _decimal_or_none(ur[4])
        facility_utilities.append({
            "meter_id": ur[0],
            "area": ur[1],
            "consumption_kwh": ukwh,
            "cost_inr": utility_cost,
            "co2e_kg": utility_co2e,
            "reading_count": int(ur[5]) if ur[5] is not None else 0,
            "percentage_of_plant_total": (
                round(ukwh / total_plant_kwh * 100, 2)
                if ukwh is not None and total_plant_kwh is not None and total_plant_kwh > 0
                else None
            ),
        })
        if ukwh is not None:
            utility_kwh_values.append(ukwh)

    total_utility_kwh = (
        sum(utility_kwh_values, Decimal("0"))
        if util_rows and len(utility_kwh_values) == len(util_rows)
        else None
    )
    utility_reading_count = sum(
        int(row[5]) for row in util_rows if row[5] is not None
    )
    utility_share_pct = (
        round(total_utility_kwh / total_plant_kwh * 100, 2)
        if total_utility_kwh is not None and total_plant_kwh is not None and total_plant_kwh > 0
        else None
    )

    # 3. Full requested-scope Final Assembly Output (Finished Goods Gate).
    p_conditions = [FactHourlyProduction.line_id.in_(["FAL-L1", "FAL-L2"])]
    if plant_id:
        p_conditions.append(FactHourlyProduction.plant_id == plant_id)
    if start_date:
        p_conditions.append(FactHourlyProduction.event_date >= start_date)
    if end_date:
        p_conditions.append(FactHourlyProduction.event_date <= end_date)

    q_fal = select(
        func.sum(FactHourlyProduction.actual_qty),
        func.sum(FactHourlyProduction.good_qty),
        func.count(FactHourlyProduction.event_id),
    ).where(and_(*p_conditions))
    row_fal = session.execute(q_fal).fetchone()

    fal_actual_qty = _int_or_none(row_fal[0]) if row_fal else None
    fal_good_qty = _int_or_none(row_fal[1]) if row_fal else None
    fal_event_count = int(row_fal[2]) if row_fal and row_fal[2] is not None else 0

    # 4. Align plant energy and Final Assembly output at exact plant-hour scope.
    energy_hourly_q = select(
        FactEnergyMeterHourly.plant_id.label("plant_id"),
        FactEnergyMeterHourly.timestamp.label("hour_ts"),
        func.sum(FactEnergyMeterHourly.consumption_kwh).label("energy_kwh"),
    ).group_by(
        FactEnergyMeterHourly.plant_id,
        FactEnergyMeterHourly.timestamp,
    )
    if e_conditions:
        energy_hourly_q = energy_hourly_q.where(and_(*e_conditions))
    energy_hourly = energy_hourly_q.subquery()

    fal_hourly_q = select(
        FactHourlyProduction.plant_id.label("plant_id"),
        FactHourlyProduction.event_ts.label("hour_ts"),
        func.sum(FactHourlyProduction.actual_qty).label("actual_qty"),
        func.sum(FactHourlyProduction.good_qty).label("good_qty"),
    ).where(and_(*p_conditions)).group_by(
        FactHourlyProduction.plant_id,
        FactHourlyProduction.event_ts,
    )
    fal_hourly = fal_hourly_q.subquery()
    aligned_q = select(
        energy_hourly.c.hour_ts,
        energy_hourly.c.energy_kwh,
        fal_hourly.c.actual_qty,
        fal_hourly.c.good_qty,
    ).select_from(
        energy_hourly.join(
            fal_hourly,
            and_(
                energy_hourly.c.plant_id == fal_hourly.c.plant_id,
                energy_hourly.c.hour_ts == fal_hourly.c.hour_ts,
            ),
        )
    ).order_by(energy_hourly.c.hour_ts.asc())
    aligned_rows = session.execute(aligned_q).fetchall()
    energy_hour_count = int(
        session.execute(select(func.count()).select_from(energy_hourly)).scalar_one()
    )
    fal_hour_count = int(
        session.execute(select(func.count()).select_from(fal_hourly)).scalar_one()
    )

    aligned_energy_values = [_decimal_or_none(row[1]) for row in aligned_rows]
    aligned_actual_values = [_int_or_none(row[2]) for row in aligned_rows]
    aligned_good_values = [_int_or_none(row[3]) for row in aligned_rows]
    aligned_energy_kwh = (
        sum((value for value in aligned_energy_values if value is not None), Decimal("0"))
        if aligned_rows and all(value is not None for value in aligned_energy_values)
        else None
    )
    aligned_actual_qty = (
        sum(value for value in aligned_actual_values if value is not None)
        if aligned_rows and all(value is not None for value in aligned_actual_values)
        else None
    )
    aligned_good_qty = (
        sum(value for value in aligned_good_values if value is not None)
        if aligned_rows and all(value is not None for value in aligned_good_values)
        else None
    )
    factory_sec_alignment_available = bool(aligned_rows)
    factory_sec_scope_complete = (
        energy_hour_count > 0
        and energy_hour_count == fal_hour_count == len(aligned_rows)
    )
    factory_sec_actual = (
        round(aligned_energy_kwh / aligned_actual_qty, 4)
        if factory_sec_scope_complete
        and aligned_energy_kwh is not None
        and aligned_actual_qty is not None
        and aligned_actual_qty > 0
        else None
    )
    factory_sec_good = (
        round(aligned_energy_kwh / aligned_good_qty, 4)
        if factory_sec_scope_complete
        and aligned_energy_kwh is not None
        and aligned_good_qty is not None
        and aligned_good_qty > 0
        else None
    )
    aligned_dates = [
        row[0].date() if isinstance(row[0], datetime) else row[0]
        for row in aligned_rows
        if row[0] is not None
    ]

    return {
        "plant_id": plant_id,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "data_available": total_energy_readings > 0,
        "total_plant_energy_kwh": total_plant_kwh,
        "total_plant_cost_inr": total_plant_cost,
        "total_plant_co2e_kg": total_plant_co2e,
        "final_assembly_data_available": fal_event_count > 0,
        "final_assembly_actual_output": fal_actual_qty,
        "final_assembly_good_output": fal_good_qty,
        "factory_sec_alignment_available": factory_sec_alignment_available,
        "factory_sec_scope_complete": factory_sec_scope_complete,
        "factory_sec_data_available": factory_sec_actual is not None,
        "factory_sec_good_data_available": factory_sec_good is not None,
        "factory_sec_aligned_energy_kwh": aligned_energy_kwh,
        "factory_sec_aligned_actual_output": aligned_actual_qty,
        "factory_sec_aligned_good_output": aligned_good_qty,
        "factory_sec_aligned_plant_hours": len(aligned_rows),
        "factory_sec_alignment_start_date": min(aligned_dates).isoformat() if aligned_dates else None,
        "factory_sec_alignment_end_date": max(aligned_dates).isoformat() if aligned_dates else None,
        "factory_sec_alignment_note": (
            "SEC uses energy-meter and Final Assembly records matched by plant and exact timestamp; "
            "SEC is unavailable unless all requested-scope plant-hour groups match. Aligned values are "
            "reported separately from full requested-scope totals."
        ),
        "factory_sec_kwh_per_finished_unit": factory_sec_actual,
        "factory_sec_good_kwh_per_finished_unit": factory_sec_good,
        "facility_utilities": {
            "total_utility_consumption_kwh": total_utility_kwh,
            "utility_share_percentage": utility_share_pct,
            "data_available": utility_reading_count > 0,
            "reading_count": utility_reading_count,
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

