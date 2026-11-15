"""Deterministic energy analytics service for Industrial Energy Intelligence Platform."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.config import DEFAULT_POWER_FACTOR_THRESHOLD
from app.models.source_data import FactEnergyMeterHourly


def _decimal_or_none(value) -> Optional[Decimal]:
    return Decimal(str(value)) if value is not None else None


def _round_or_none(value: Optional[Decimal], places: int) -> Optional[Decimal]:
    return round(value, places) if value is not None else None


def _apply_energy_filters(query, plant_id: Optional[str] = None, start_date: Optional[date] = None, end_date: Optional[date] = None):
    """Apply common optional filters for plant and date range to an energy query."""
    conditions = []
    if plant_id:
        conditions.append(FactEnergyMeterHourly.plant_id == plant_id)
    if start_date:
        conditions.append(FactEnergyMeterHourly.date >= start_date)
    if end_date:
        conditions.append(FactEnergyMeterHourly.date <= end_date)
    if conditions:
        query = query.where(and_(*conditions))
    return query


def get_energy_summary(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Calculate overall energy consumption, cost, emissions, and peak metrics."""
    weighted_pf_expr = func.sum(FactEnergyMeterHourly.power_factor * FactEnergyMeterHourly.consumption_kwh) / func.nullif(
        func.sum(FactEnergyMeterHourly.consumption_kwh), Decimal("0")
    )
    base_q = select(
        func.sum(FactEnergyMeterHourly.consumption_kwh),
        func.sum(FactEnergyMeterHourly.cost_inr),
        func.sum(FactEnergyMeterHourly.co2e_kg),
        func.coalesce(weighted_pf_expr, func.avg(FactEnergyMeterHourly.power_factor)),
        func.count(FactEnergyMeterHourly.meter_reading_id),
        func.count(func.distinct(FactEnergyMeterHourly.timestamp)),
        func.avg(FactEnergyMeterHourly.power_factor),
        func.count(FactEnergyMeterHourly.power_factor),
    )
    base_q = _apply_energy_filters(base_q, plant_id, start_date, end_date)
    row = session.execute(base_q).fetchone()

    total_kwh = _decimal_or_none(row[0]) if row else None
    total_cost = _decimal_or_none(row[1]) if row else None
    total_co2e = _decimal_or_none(row[2]) if row else None
    avg_pf = _decimal_or_none(row[3]) if row else None
    total_readings = int(row[4]) if row else 0
    distinct_hours = int(row[5]) if row else 0
    arithmetic_pf = _decimal_or_none(row[6]) if row else None
    power_factor_readings = int(row[7]) if row else 0

    # Calculate average hourly consumption per distinct hour
    avg_hourly_kwh = (
        total_kwh / distinct_hours
        if total_kwh is not None and distinct_hours > 0
        else None
    )

    # Find peak hourly reading
    peak_q = select(
        FactEnergyMeterHourly.timestamp,
        FactEnergyMeterHourly.meter_id,
        FactEnergyMeterHourly.plant_id,
        FactEnergyMeterHourly.consumption_kwh,
    ).where(
        FactEnergyMeterHourly.consumption_kwh.is_not(None)
    ).order_by(FactEnergyMeterHourly.consumption_kwh.desc()).limit(1)
    peak_q = _apply_energy_filters(peak_q, plant_id, start_date, end_date)
    peak_row = session.execute(peak_q).fetchone()

    peak_reading = None
    if peak_row:
        peak_reading = {
            "timestamp": peak_row[0].isoformat(),
            "meter_id": peak_row[1],
            "plant_id": peak_row[2],
            "consumption_kwh": Decimal(str(peak_row[3])),
        }

    return {
        "plant_id": plant_id,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "data_available": total_readings > 0,
        "consumption_data_available": total_kwh is not None,
        "cost_data_available": total_cost is not None,
        "emissions_data_available": total_co2e is not None,
        "power_factor_data_available": power_factor_readings > 0,
        "total_consumption_kwh": total_kwh,
        "total_cost_inr": total_cost,
        "total_co2e_kg": total_co2e,
        "avg_power_factor": _round_or_none(avg_pf, 4),
        "arithmetic_avg_power_factor": _round_or_none(arithmetic_pf, 4),
        "total_readings": total_readings,
        "distinct_hours": distinct_hours,
        "avg_hourly_consumption_kwh": _round_or_none(avg_hourly_kwh, 4),
        "peak_reading": peak_reading,
    }


def get_energy_by_meter(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Calculate energy consumption breakdown ranked by meter."""
    # First get total for percentage calculation
    total_summary = get_energy_summary(session, plant_id, start_date, end_date)
    overall_total_kwh = total_summary["total_consumption_kwh"]

    weighted_pf_expr = func.sum(FactEnergyMeterHourly.power_factor * FactEnergyMeterHourly.consumption_kwh) / func.nullif(
        func.sum(FactEnergyMeterHourly.consumption_kwh), Decimal("0")
    )

    q = select(
        FactEnergyMeterHourly.meter_id,
        FactEnergyMeterHourly.area,
        func.sum(FactEnergyMeterHourly.consumption_kwh).label("meter_kwh"),
        func.sum(FactEnergyMeterHourly.cost_inr).label("meter_cost"),
        func.sum(FactEnergyMeterHourly.co2e_kg).label("meter_co2e"),
        func.coalesce(weighted_pf_expr, func.avg(FactEnergyMeterHourly.power_factor)).label("meter_avg_pf"),
        func.max(FactEnergyMeterHourly.consumption_kwh).label("peak_kwh"),
        func.count(FactEnergyMeterHourly.meter_reading_id).label("reading_count"),
        func.avg(FactEnergyMeterHourly.power_factor).label("meter_arithmetic_pf"),
        func.count(FactEnergyMeterHourly.power_factor).label("power_factor_reading_count"),
    ).group_by(
        FactEnergyMeterHourly.meter_id,
        FactEnergyMeterHourly.area,
    ).order_by(func.sum(FactEnergyMeterHourly.consumption_kwh).desc())

    q = _apply_energy_filters(q, plant_id, start_date, end_date)
    rows = session.execute(q).fetchall()

    results = []
    for r in rows:
        meter_kwh = _decimal_or_none(r[2])
        meter_cost = _decimal_or_none(r[3])
        meter_co2e = _decimal_or_none(r[4])
        pct = (
            meter_kwh / overall_total_kwh * 100
            if meter_kwh is not None and overall_total_kwh is not None and overall_total_kwh > 0
            else None
        )
        results.append({
            "meter_id": r[0],
            "area": r[1],
            "consumption_kwh": meter_kwh,
            "cost_inr": meter_cost,
            "co2e_kg": meter_co2e,
            "avg_power_factor": _round_or_none(_decimal_or_none(r[5]), 4),
            "arithmetic_avg_power_factor": _round_or_none(_decimal_or_none(r[8]), 4),
            "power_factor_data_available": int(r[9]) > 0,
            "peak_kwh": _decimal_or_none(r[6]),
            "reading_count": int(r[7]),
            "percentage_of_total": _round_or_none(pct, 2),
        })

    return results


def get_energy_by_area(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Calculate energy consumption breakdown grouped by factory operational area."""
    total_summary = get_energy_summary(session, plant_id, start_date, end_date)
    overall_total_kwh = total_summary["total_consumption_kwh"]

    weighted_pf_expr = func.sum(FactEnergyMeterHourly.power_factor * FactEnergyMeterHourly.consumption_kwh) / func.nullif(
        func.sum(FactEnergyMeterHourly.consumption_kwh), Decimal("0")
    )

    q = select(
        FactEnergyMeterHourly.area,
        func.sum(FactEnergyMeterHourly.consumption_kwh).label("area_kwh"),
        func.sum(FactEnergyMeterHourly.cost_inr).label("area_cost"),
        func.sum(FactEnergyMeterHourly.co2e_kg).label("area_co2e"),
        func.coalesce(weighted_pf_expr, func.avg(FactEnergyMeterHourly.power_factor)).label("area_avg_pf"),
        func.avg(FactEnergyMeterHourly.power_factor).label("area_arithmetic_pf"),
        func.count(FactEnergyMeterHourly.power_factor).label("power_factor_reading_count"),
    ).group_by(FactEnergyMeterHourly.area).order_by(func.sum(FactEnergyMeterHourly.consumption_kwh).desc())

    q = _apply_energy_filters(q, plant_id, start_date, end_date)
    rows = session.execute(q).fetchall()

    results = []
    for r in rows:
        area_kwh = _decimal_or_none(r[1])
        area_cost = _decimal_or_none(r[2])
        area_co2e = _decimal_or_none(r[3])
        pct = (
            area_kwh / overall_total_kwh * 100
            if area_kwh is not None and overall_total_kwh is not None and overall_total_kwh > 0
            else None
        )
        results.append({
            "area": r[0],
            "consumption_kwh": area_kwh,
            "cost_inr": area_cost,
            "co2e_kg": area_co2e,
            "avg_power_factor": _round_or_none(_decimal_or_none(r[4]), 4),
            "arithmetic_avg_power_factor": _round_or_none(_decimal_or_none(r[5]), 4),
            "power_factor_data_available": int(r[6]) > 0,
            "percentage_of_total": _round_or_none(pct, 2),
        })

    return results


def get_energy_daily_trend(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Calculate daily time series of energy consumption, cost, and peak hourly energy consumption."""
    weighted_pf_expr = func.sum(FactEnergyMeterHourly.power_factor * FactEnergyMeterHourly.consumption_kwh) / func.nullif(
        func.sum(FactEnergyMeterHourly.consumption_kwh), Decimal("0")
    )

    q = select(
        FactEnergyMeterHourly.date,
        func.sum(FactEnergyMeterHourly.consumption_kwh).label("daily_kwh"),
        func.sum(FactEnergyMeterHourly.cost_inr).label("daily_cost"),
        func.sum(FactEnergyMeterHourly.co2e_kg).label("daily_co2e"),
        func.coalesce(weighted_pf_expr, func.avg(FactEnergyMeterHourly.power_factor)).label("daily_avg_pf"),
        func.max(FactEnergyMeterHourly.consumption_kwh).label("daily_peak_kwh"),
        func.count(FactEnergyMeterHourly.meter_reading_id).label("readings"),
        func.avg(FactEnergyMeterHourly.power_factor).label("daily_arithmetic_pf"),
        func.count(FactEnergyMeterHourly.power_factor).label("power_factor_readings"),
    ).group_by(FactEnergyMeterHourly.date).order_by(FactEnergyMeterHourly.date.asc())

    q = _apply_energy_filters(q, plant_id, start_date, end_date)
    rows = session.execute(q).fetchall()

    return [
        {
            "date": r[0].isoformat(),
            "consumption_kwh": _decimal_or_none(r[1]),
            "cost_inr": _decimal_or_none(r[2]),
            "co2e_kg": _decimal_or_none(r[3]),
            "avg_power_factor": _round_or_none(_decimal_or_none(r[4]), 4),
            "arithmetic_avg_power_factor": _round_or_none(_decimal_or_none(r[7]), 4),
            "power_factor_data_available": int(r[8]) > 0,
            "peak_hourly_kwh": _decimal_or_none(r[5]),
            "reading_count": int(r[6]),
        }
        for r in rows
    ]


def get_power_factor_summary(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    low_pf_threshold: Decimal = DEFAULT_POWER_FACTOR_THRESHOLD,
) -> Dict[str, Any]:
    """Calculate power factor distribution and flag low power factor monitoring events."""
    weighted_pf_expr = func.sum(FactEnergyMeterHourly.power_factor * FactEnergyMeterHourly.consumption_kwh) / func.nullif(
        func.sum(FactEnergyMeterHourly.consumption_kwh), Decimal("0")
    )
    q_all = select(
        func.coalesce(weighted_pf_expr, func.avg(FactEnergyMeterHourly.power_factor)),
        func.min(FactEnergyMeterHourly.power_factor),
        func.max(FactEnergyMeterHourly.power_factor),
        func.count(FactEnergyMeterHourly.meter_reading_id),
        func.avg(FactEnergyMeterHourly.power_factor),
        func.count(FactEnergyMeterHourly.power_factor),
    )
    q_all = _apply_energy_filters(q_all, plant_id, start_date, end_date)
    row_all = session.execute(q_all).fetchone()

    total_count = int(row_all[3]) if row_all else 0
    avg_pf = _decimal_or_none(row_all[0]) if row_all else None
    min_pf = _decimal_or_none(row_all[1]) if row_all else None
    max_pf = _decimal_or_none(row_all[2]) if row_all else None
    arithmetic_pf = _decimal_or_none(row_all[4]) if row_all else None
    power_factor_readings = int(row_all[5]) if row_all else 0

    # Count readings below threshold
    q_low = select(
        FactEnergyMeterHourly.meter_id,
        func.count(FactEnergyMeterHourly.meter_reading_id).label("low_count"),
        func.min(FactEnergyMeterHourly.power_factor).label("min_low_pf"),
    ).where(FactEnergyMeterHourly.power_factor < low_pf_threshold).group_by(FactEnergyMeterHourly.meter_id)
    q_low = _apply_energy_filters(q_low, plant_id, start_date, end_date)
    low_rows = session.execute(q_low).fetchall()

    total_low = sum(int(r[1]) for r in low_rows)
    low_pct = (
        Decimal(str(total_low)) / total_count * 100
        if total_count > 0 and power_factor_readings > 0
        else None
    )

    meter_breakdown = [
        {
            "meter_id": r[0],
            "low_pf_events": int(r[1]),
            "min_power_factor": Decimal(str(r[2])),
        }
        for r in low_rows
    ]

    return {
        "threshold": low_pf_threshold,
        "power_factor_data_available": power_factor_readings > 0,
        "power_factor_readings_count": power_factor_readings,
        "avg_power_factor": _round_or_none(avg_pf, 4),
        "arithmetic_avg_power_factor": _round_or_none(arithmetic_pf, 4),
        "min_power_factor": min_pf,
        "max_power_factor": max_pf,
        "total_readings": total_count,
        "low_pf_events_count": total_low,
        "low_pf_percentage": _round_or_none(low_pct, 2),
        "low_pf_by_meter": meter_breakdown,
    }

