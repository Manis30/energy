"""Deterministic production analytics service for Industrial Energy Intelligence Platform."""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.source_data import DimProduct, DimProductionLine, FactHourlyProduction


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
    target_qty: int,
    actual_qty: int,
    good_qty: int,
    reject_qty: int,
    rework_qty: int,
) -> Dict[str, Decimal]:
    """
    Compute production operational rates with safe zero-division guards.
    - achievement_rate: actual_qty / target_qty * 100
    - good_rate (yield): good_qty / actual_qty * 100
    - reject_rate: reject_qty / actual_qty * 100
    - rework_rate: rework_qty / actual_qty * 100
    """
    actual_d = Decimal(str(actual_qty))
    target_d = Decimal(str(target_qty))
    good_d = Decimal(str(good_qty))
    reject_d = Decimal(str(reject_qty))
    rework_d = Decimal(str(rework_qty))

    achievement_rate = (actual_d / target_d * 100) if target_d > 0 else Decimal("0")
    good_rate = (good_d / actual_d * 100) if actual_d > 0 else Decimal("0")
    reject_rate = (reject_d / actual_d * 100) if actual_d > 0 else Decimal("0")
    rework_rate = (rework_d / actual_d * 100) if actual_d > 0 else Decimal("0")

    return {
        "achievement_rate": round(achievement_rate, 2),
        "good_rate": round(good_rate, 2),
        "reject_rate": round(reject_rate, 2),
        "rework_rate": round(rework_rate, 2),
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
        func.coalesce(func.sum(FactHourlyProduction.target_qty), 0),
        func.coalesce(func.sum(FactHourlyProduction.actual_qty), 0),
        func.coalesce(func.sum(FactHourlyProduction.good_qty), 0),
        func.coalesce(func.sum(FactHourlyProduction.reject_qty), 0),
        func.coalesce(func.sum(FactHourlyProduction.rework_qty), 0),
        func.coalesce(func.sum(FactHourlyProduction.downtime_min), 0),
        func.count(FactHourlyProduction.event_id),
    )
    q = _apply_production_filters(q, plant_id, line_id, product_id, shift_id, start_date, end_date)
    row = session.execute(q).fetchone()

    target_qty = int(row[0]) if row else 0
    actual_qty = int(row[1]) if row else 0
    good_qty = int(row[2]) if row else 0
    reject_qty = int(row[3]) if row else 0
    rework_qty = int(row[4]) if row else 0
    downtime_min = int(row[5]) if row else 0
    event_count = int(row[6]) if row else 0

    rates = _compute_production_rates(target_qty, actual_qty, good_qty, reject_qty, rework_qty)

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
        "quantity_balance_valid": actual_qty == good_qty + reject_qty,
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
        target = int(r[4])
        actual = int(r[5])
        good = int(r[6])
        reject = int(r[7])
        rework = int(r[8])
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
            "downtime_min": int(r[9]),
            "operating_hours": int(r[10]),
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
        target = int(r[3])
        actual = int(r[4])
        good = int(r[5])
        reject = int(r[6])
        rework = int(r[7])
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
            "operating_hours": int(r[8]),
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
        func.sum(FactHourlyProduction.downtime_min).label("downtime"),
        func.count(FactHourlyProduction.event_id).label("hours"),
    ).group_by(FactHourlyProduction.shift_id).order_by(FactHourlyProduction.shift_id.asc())

    q = _apply_production_filters(q, plant_id=plant_id, start_date=start_date, end_date=end_date)
    rows = session.execute(q).fetchall()

    results = []
    for r in rows:
        target = int(r[1])
        actual = int(r[2])
        good = int(r[3])
        reject = int(r[4])
        rates = _compute_production_rates(target, actual, good, reject, 0)
        results.append({
            "shift_id": r[0],
            "target_qty": target,
            "actual_qty": actual,
            "good_qty": good,
            "reject_qty": reject,
            "downtime_min": int(r[5]),
            "operating_hours": int(r[6]),
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
            "total_downtime_min": int(r[1]),
            "event_count": int(r[2]),
            "zero_output_events": int(r[3]),
        }
        for r in rows
    ]


def get_production_daily_trend(
    session: Session,
    plant_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Calculate daily time series of production output, targets, and reject rates."""
    q = select(
        FactHourlyProduction.event_date,
        func.sum(FactHourlyProduction.target_qty).label("target"),
        func.sum(FactHourlyProduction.actual_qty).label("actual"),
        func.sum(FactHourlyProduction.good_qty).label("good"),
        func.sum(FactHourlyProduction.reject_qty).label("reject"),
        func.sum(FactHourlyProduction.downtime_min).label("downtime"),
    ).group_by(FactHourlyProduction.event_date).order_by(FactHourlyProduction.event_date.asc())

    q = _apply_production_filters(q, plant_id=plant_id, start_date=start_date, end_date=end_date)
    rows = session.execute(q).fetchall()

    results = []
    for r in rows:
        target = int(r[1])
        actual = int(r[2])
        good = int(r[3])
        reject = int(r[4])
        rates = _compute_production_rates(target, actual, good, reject, 0)
        results.append({
            "date": r[0].isoformat(),
            "target_qty": target,
            "actual_qty": actual,
            "good_qty": good,
            "reject_qty": reject,
            "downtime_min": int(r[5]),
            **rates,
        })
    return results

