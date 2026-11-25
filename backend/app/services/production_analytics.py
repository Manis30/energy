"""Deterministic production analytics service for Industrial Energy Intelligence Platform."""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.source_data import DimProduct, DimProductionLine, FactHourlyProduction


def _int_or_none(value) -> Optional[int]:
    return int(value) if value is not None else None


def _apply_production_filters(
    query,
    plant_id: Optional[str] = None,
    line_id: Optional[str] = None,
    product_id: Optional[str] = None,
    shift_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """Apply common optional filters to production fact query."""
    conditions = []
    if plant_id:
        conditions.append(FactHourlyProduction.plant_id == plant_id)
    if line_id:
        conditions.append(FactHourlyProduction.line_id == line_id)
    if product_id:
        conditions.append(FactHourlyProduction.product_id == product_id)
    if shift_id:
        conditions.append(FactHourlyProduction.shift_id == shift_id)
    if start_date:
        conditions.append(FactHourlyProduction.event_date >= start_date)
    if end_date:
        conditions.append(FactHourlyProduction.event_date <= end_date)
    if conditions:
        query = query.where(and_(*conditions))
    return query


def _compute_production_rates(
    target_qty: Optional[int],
    actual_qty: Optional[int],
    good_qty: Optional[int],
    reject_qty: Optional[int],
    rework_qty: Optional[int],
) -> Dict[str, Optional[Decimal]]:
    """
    Compute production operational rates with safe zero-division guards.
    - achievement_rate: actual_qty / target_qty * 100
    - good_rate (yield): good_qty / actual_qty * 100
    - reject_rate: reject_qty / actual_qty * 100
    - rework_rate: rework_qty / actual_qty * 100
    """
    achievement_rate = (
        Decimal(str(actual_qty)) / Decimal(str(target_qty)) * 100
        if actual_qty is not None and target_qty is not None and target_qty > 0
        else None
    )
    good_rate = (
        Decimal(str(good_qty)) / Decimal(str(actual_qty)) * 100
        if good_qty is not None and actual_qty is not None and actual_qty > 0
        else None
    )
    reject_rate = (
        Decimal(str(reject_qty)) / Decimal(str(actual_qty)) * 100
        if reject_qty is not None and actual_qty is not None and actual_qty > 0
        else None
    )
    rework_rate = (
        Decimal(str(rework_qty)) / Decimal(str(actual_qty)) * 100
        if rework_qty is not None and actual_qty is not None and actual_qty > 0
        else None
    )

    return {
        "achievement_rate": round(achievement_rate, 2) if achievement_rate is not None else None,
        "good_rate": round(good_rate, 2) if good_rate is not None else None,
        "reject_rate": round(reject_rate, 2) if reject_rate is not None else None,
        "rework_rate": round(rework_rate, 2) if rework_rate is not None else None,
    }


def get_production_summary(
    session: Session,
    plant_id: Optional[str] = None,
    line_id: Optional[str] = None,
    product_id: Optional[str] = None,
    shift_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Calculate overall factory production output, quality rates, and downtime."""
    q = select(
        func.sum(FactHourlyProduction.target_qty),
        func.sum(FactHourlyProduction.actual_qty),
        func.sum(FactHourlyProduction.good_qty),
        func.sum(FactHourlyProduction.reject_qty),
        func.sum(FactHourlyProduction.rework_qty),
        func.sum(FactHourlyProduction.downtime_min),
        func.count(FactHourlyProduction.event_id),
    )
    q = _apply_production_filters(q, plant_id, line_id, product_id, shift_id, start_date, end_date)
    row = session.execute(q).fetchone()

    target_qty = _int_or_none(row[0]) if row else None
    actual_qty = _int_or_none(row[1]) if row else None
    good_qty = _int_or_none(row[2]) if row else None
    reject_qty = _int_or_none(row[3]) if row else None
    rework_qty = _int_or_none(row[4]) if row else None
    downtime_min = _int_or_none(row[5]) if row else None
    event_count = int(row[6]) if row and row[6] is not None else 0

    rates = _compute_production_rates(target_qty, actual_qty, good_qty, reject_qty, rework_qty)
    quantity_balance_valid = (
        actual_qty == good_qty + reject_qty
        if event_count > 0 and actual_qty is not None and good_qty is not None and reject_qty is not None
        else None
    )

    return {
        "plant_id": plant_id,
        "line_id": line_id,
        "product_id": product_id,
        "shift_id": shift_id,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "target_qty": target_qty,
        "actual_qty": actual_qty,
        "good_qty": good_qty,
        "reject_qty": reject_qty,
        "rework_qty": rework_qty,
        "downtime_min": downtime_min,
        "event_count": event_count,
        "data_available": event_count > 0,
        "quantity_balance_valid": quantity_balance_valid,
        "oee": {
            "status": "unavailable",
            "quality_rate": rates["good_rate"],
            "availability": None,
            "performance": None,
            "overall_oee": None,
            "reason": (
                "Standard OEE (ISO 22400) cannot be reliably calculated from source datasets without unverified assumptions: "
                "Planned Production Time (planned vs unscheduled shifts) is not provided, and target_qty is an hourly gross quota "
                "rather than a net operating time target."
            ),
        },
        **rates,
    }


def get_production_by_line(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Calculate production performance and quality rates grouped by production line."""
    q = select(
        FactHourlyProduction.line_id,
        FactHourlyProduction.plant_id,
        DimProductionLine.line_type,
        DimProductionLine.area,
        func.sum(FactHourlyProduction.target_qty).label("target"),
        func.sum(FactHourlyProduction.actual_qty).label("actual"),
        func.sum(FactHourlyProduction.good_qty).label("good"),
        func.sum(FactHourlyProduction.reject_qty).label("reject"),
        func.sum(FactHourlyProduction.rework_qty).label("rework"),
        func.sum(FactHourlyProduction.downtime_min).label("downtime"),
        func.count(FactHourlyProduction.event_id).label("hours"),
    ).join(
        DimProductionLine,
        and_(
            FactHourlyProduction.line_id == DimProductionLine.line_id,
            FactHourlyProduction.plant_id == DimProductionLine.plant_id,
        ),
    ).group_by(
        FactHourlyProduction.line_id,
        FactHourlyProduction.plant_id,
        DimProductionLine.line_type,
        DimProductionLine.area,
    ).order_by(FactHourlyProduction.line_id.asc())

    q = _apply_production_filters(q, plant_id=plant_id, start_date=start_date, end_date=end_date)
    rows = session.execute(q).fetchall()

    results = []
    for r in rows:
        target = _int_or_none(r[4])
        actual = _int_or_none(r[5])
        good = _int_or_none(r[6])
        reject = _int_or_none(r[7])
        rework = _int_or_none(r[8])
        rates = _compute_production_rates(target, actual, good, reject, rework)
        results.append({
            "line_id": r[0],
            "plant_id": r[1],
            "line_type": r[2],
            "area": r[3],
            "target_qty": target,
            "actual_qty": actual,
            "good_qty": good,
            "reject_qty": reject,
            "rework_qty": rework,
            "downtime_min": _int_or_none(r[9]),
            "operating_hours": int(r[10]) if r[10] is not None else 0,
            **rates,
        })
    return results


def get_production_by_product(
    session: Session,
    plant_id: Optional[str] = None,
    line_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Calculate production performance and quality rates grouped by product SKU."""
    q = select(
        FactHourlyProduction.product_id,
        DimProduct.product_name,
        DimProduct.product_family,
        func.sum(FactHourlyProduction.target_qty).label("target"),
        func.sum(FactHourlyProduction.actual_qty).label("actual"),
        func.sum(FactHourlyProduction.good_qty).label("good"),
        func.sum(FactHourlyProduction.reject_qty).label("reject"),
        func.sum(FactHourlyProduction.rework_qty).label("rework"),
        func.count(FactHourlyProduction.event_id).label("hours"),
    ).join(
        DimProduct,
        FactHourlyProduction.product_id == DimProduct.product_id,
    ).group_by(
        FactHourlyProduction.product_id,
        DimProduct.product_name,
        DimProduct.product_family,
    ).order_by(func.sum(FactHourlyProduction.actual_qty).desc())

    q = _apply_production_filters(q, plant_id=plant_id, line_id=line_id, start_date=start_date, end_date=end_date)
    rows = session.execute(q).fetchall()

    results = []
    for r in rows:
        target = _int_or_none(r[3])
        actual = _int_or_none(r[4])
        good = _int_or_none(r[5])
        reject = _int_or_none(r[6])
        rework = _int_or_none(r[7])
        rates = _compute_production_rates(target, actual, good, reject, rework)
        results.append({
            "product_id": r[0],
            "product_name": r[1],
            "product_family": r[2],
            "target_qty": target,
            "actual_qty": actual,
            "good_qty": good,
            "reject_qty": reject,
            "rework_qty": rework,
            "operating_hours": int(r[8]) if r[8] is not None else 0,
            **rates,
        })
    return results


def get_production_by_shift(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Calculate production metrics by shift (A: Morning, B: Evening, C: Night)."""
    q = select(
        FactHourlyProduction.shift_id,
        func.sum(FactHourlyProduction.target_qty).label("target"),
        func.sum(FactHourlyProduction.actual_qty).label("actual"),
        func.sum(FactHourlyProduction.good_qty).label("good"),
        func.sum(FactHourlyProduction.reject_qty).label("reject"),
        func.sum(FactHourlyProduction.rework_qty).label("rework"),
        func.sum(FactHourlyProduction.downtime_min).label("downtime"),
        func.count(FactHourlyProduction.event_id).label("hours"),
    ).group_by(FactHourlyProduction.shift_id).order_by(FactHourlyProduction.shift_id.asc())

    q = _apply_production_filters(q, plant_id=plant_id, start_date=start_date, end_date=end_date)
    rows = session.execute(q).fetchall()

    results = []
    for r in rows:
        target = _int_or_none(r[1])
        actual = _int_or_none(r[2])
        good = _int_or_none(r[3])
        reject = _int_or_none(r[4])
        rework = _int_or_none(r[5])
        rates = _compute_production_rates(target, actual, good, reject, rework)
        results.append({
            "shift_id": r[0],
            "target_qty": target,
            "actual_qty": actual,
            "good_qty": good,
            "reject_qty": reject,
            "rework_qty": rework,
            "downtime_min": _int_or_none(r[6]),
            "operating_hours": int(r[7]) if r[7] is not None else 0,
            **rates,
        })
    return results


def get_downtime_by_reason(
    session: Session,
    plant_id: Optional[str] = None,
    line_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Calculate downtime breakdown by operational reason code."""
    q = select(
        FactHourlyProduction.downtime_reason,
        func.sum(FactHourlyProduction.downtime_min).label("total_downtime_min"),
        func.count(FactHourlyProduction.event_id).label("event_count"),
        func.sum(case((FactHourlyProduction.actual_qty == 0, 1), else_=0)).label("zero_output_events"),
    ).group_by(FactHourlyProduction.downtime_reason).order_by(func.sum(FactHourlyProduction.downtime_min).desc())

    q = _apply_production_filters(q, plant_id=plant_id, line_id=line_id, start_date=start_date, end_date=end_date)
    rows = session.execute(q).fetchall()

    return [
        {
            "downtime_reason": r[0],
            "total_downtime_min": _int_or_none(r[1]),
            "event_count": int(r[2]) if r[2] is not None else 0,
            "zero_output_events": int(r[3]) if r[3] is not None else 0,
        }
        for r in rows
    ]


def get_production_daily_trend(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    shift_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Calculate daily time series of production output, targets, and reject rates."""
    clean_shift = shift_id.replace("Shift ", "").strip().upper() if shift_id else None
    q = select(
        FactHourlyProduction.event_date,
        func.sum(FactHourlyProduction.target_qty).label("target"),
        func.sum(FactHourlyProduction.actual_qty).label("actual"),
        func.sum(FactHourlyProduction.good_qty).label("good"),
        func.sum(FactHourlyProduction.reject_qty).label("reject"),
        func.sum(FactHourlyProduction.rework_qty).label("rework"),
        func.sum(FactHourlyProduction.downtime_min).label("downtime"),
    ).group_by(FactHourlyProduction.event_date).order_by(FactHourlyProduction.event_date.asc())

    q = _apply_production_filters(q, plant_id=plant_id, shift_id=clean_shift, start_date=start_date, end_date=end_date)
    rows = session.execute(q).fetchall()

    results = []
    for r in rows:
        target = _int_or_none(r[1])
        actual = _int_or_none(r[2])
        good = _int_or_none(r[3])
        reject = _int_or_none(r[4])
        rework = _int_or_none(r[5])
        rates = _compute_production_rates(target, actual, good, reject, rework)
        results.append({
            "date": r[0].isoformat(),
            "target_qty": target,
            "actual_qty": actual,
            "good_qty": good,
            "reject_qty": reject,
            "rework_qty": rework,
            "downtime_min": _int_or_none(r[6]),
            **rates,
        })
    return results

