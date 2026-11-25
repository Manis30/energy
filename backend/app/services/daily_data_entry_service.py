"""
Daily Operations Manual & Pasted Data Entry Service.
Supports end-to-end data entry for Energy Telemetry and Production records:
- Schema validation with plain-language row/field errors
- Preserves master data bindings (plant-specific lines, meters, areas, products)
- Idempotent upsert logic to prevent duplicate creation on retry
- Provenance tracking with UploadHistory and FactSourceRevision
- Pipeline stage status synchronization
"""

from datetime import date, datetime
from decimal import Decimal
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.pipeline_runs import DailyPipelineRun
from app.models.source_data import (
    DimProduct,
    DimProductionLine,
    FactEnergyMeterHourly,
    FactHourlyProduction,
    FactSourceRevision,
)
from app.models.upload_history import UploadHistory
from app.services.daily_report_service import (
    METER_AREA_MAPPING,
    VALID_ENERGY_SOURCES,
    VALID_METERS,
    parse_cell_date,
    parse_cell_datetime,
    parse_cell_decimal,
    parse_cell_int,
)
from app.services.daily_pipeline_service import record_pipeline_stage_state

logger = logging.getLogger(__name__)

DEFAULT_TARIFF_INR_PER_KWH = Decimal("8.2500")
DEFAULT_GRID_EMISSIONS_FACTOR = Decimal("0.7160")


def get_master_data_for_plant(session: Session, plant_id: str) -> Dict[str, Any]:
    """Retrieve plant-specific lines, meters, and registered product SKUs."""
    # Production lines registered to this plant
    lines = (
        session.execute(
            select(DimProductionLine.line_id, DimProductionLine.area)
            .where(DimProductionLine.plant_id == plant_id)
            .order_by(DimProductionLine.line_id)
        )
        .all()
    )
    line_ids = [r[0] for r in lines]

    # Registered products
    products = (
        session.execute(
            select(DimProduct.product_id, DimProduct.product_name)
            .order_by(DimProduct.product_id)
        )
        .all()
    )
    product_ids = [r[0] for r in products]

    # Registered meters (standard plant submeters)
    meter_ids = sorted(list(VALID_METERS))

    # All registered plants
    all_plants = (
        session.execute(
            select(DimProductionLine.plant_id)
            .distinct()
            .order_by(DimProductionLine.plant_id)
        )
        .scalars()
        .all()
    )

    return {
        "plants": all_plants or ["IN-TN-01", "IN-KA-01"],
        "lines": line_ids,
        "meters": meter_ids,
        "meter_areas": METER_AREA_MAPPING,
        "products": product_ids,
        "shifts": ["A", "B", "C"],
        "downtime_reasons": ["NONE", "BREAKDOWN", "CHANGEOVER", "MAINTENANCE", "SHORTAGE", "QUALITY_CHECK"],
        "default_tariff": float(DEFAULT_TARIFF_INR_PER_KWH),
        "default_grid_factor": float(DEFAULT_GRID_EMISSIONS_FACTOR),
    }


def get_saved_records_for_date_and_plant(
    session: Session, reporting_date: date, plant_id: str
) -> Dict[str, Any]:
    """
    Fetch confirmed records from fact tables for the selected plant and date.
    Serializes numbers and datetimes cleanly for frontend data grid consumption.
    """
    # 1. Fetch Energy records
    energy_query = (
        select(FactEnergyMeterHourly)
        .where(
            FactEnergyMeterHourly.date == reporting_date,
            FactEnergyMeterHourly.plant_id == plant_id,
        )
        .order_by(FactEnergyMeterHourly.timestamp.asc(), FactEnergyMeterHourly.meter_id.asc())
    )
    energy_models = session.execute(energy_query).scalars().all()

    energy_records = []
    for em in energy_models:
        energy_records.append({
            "meter_reading_id": em.meter_reading_id,
            "timestamp": em.timestamp.strftime("%Y-%m-%d %H:%M") if em.timestamp else "",
            "date": em.date.isoformat() if em.date else "",
            "plant_id": em.plant_id,
            "meter_id": em.meter_id,
            "area": em.area,
            "energy_source": em.energy_source,
            "consumption_kwh": float(em.consumption_kwh) if em.consumption_kwh is not None else 0.0,
            "demand_kw": float(em.demand_kw) if em.demand_kw is not None else None,
            "power_factor": float(em.power_factor) if em.power_factor is not None else None,
            "tariff_inr_per_kwh": float(em.tariff_inr_per_kwh) if em.tariff_inr_per_kwh is not None else float(DEFAULT_TARIFF_INR_PER_KWH),
            "cost_inr": float(em.cost_inr) if em.cost_inr is not None else 0.0,
            "co2e_kg": float(em.co2e_kg) if em.co2e_kg is not None else 0.0,
            "reading_quality": em.reading_quality or "VALID",
            "upload_id": em.upload_id,
        })

    # 2. Fetch Production records
    prod_query = (
        select(FactHourlyProduction)
        .where(
            FactHourlyProduction.event_date == reporting_date,
            FactHourlyProduction.plant_id == plant_id,
        )
        .order_by(FactHourlyProduction.event_ts.asc(), FactHourlyProduction.line_id.asc())
    )
    prod_models = session.execute(prod_query).scalars().all()

    production_records = []
    for pm in prod_models:
        production_records.append({
            "event_id": pm.event_id,
            "event_ts": pm.event_ts.strftime("%Y-%m-%d %H:%M") if pm.event_ts else "",
            "event_date": pm.event_date.isoformat() if pm.event_date else "",
            "hour": pm.hour,
            "plant_id": pm.plant_id,
            "line_id": pm.line_id,
            "shift_id": pm.shift_id,
            "product_id": pm.product_id,
            "production_order_id": pm.production_order_id,
            "target_qty": pm.target_qty,
            "actual_qty": pm.actual_qty,
            "good_qty": pm.good_qty,
            "reject_qty": pm.reject_qty,
            "rework_qty": pm.rework_qty,
            "downtime_min": pm.downtime_min,
            "downtime_reason": pm.downtime_reason or "NONE",
            "operator_team": pm.operator_team or "TEAM-01",
            "source_system": pm.source_system or "MES",
            "data_quality": pm.data_quality or "VALID",
            "upload_id": pm.upload_id,
        })

    master = get_master_data_for_plant(session, plant_id)

    return {
        "reporting_date": reporting_date.isoformat(),
        "plant_id": plant_id,
        "energy_records": energy_records,
        "production_records": production_records,
        "energy_count": len(energy_records),
        "production_count": len(production_records),
        "energy_records_count": len(energy_records),
        "production_records_count": len(production_records),
        "master_data": master,
    }


def validate_manual_entries(
    session: Session,
    reporting_date: date,
    plant_id: str,
    energy_rows: List[Dict[str, Any]],
    production_rows: List[Dict[str, Any]],
    mode: str = "INCREMENTAL",
) -> Dict[str, Any]:
    """
    Validates entered/pasted Energy and Production rows against database constraints,
    master data references, and mathematical balance rules.
    Returns clear, user-friendly field-level error messages.
    """
    master = get_master_data_for_plant(session, plant_id)
    valid_lines_set = set(master["lines"])
    valid_products_set = set(master["products"])
    valid_meters_set = set(master["meters"])

    errors: List[Dict[str, Any]] = []
    seen_energy_keys: Set[Tuple[datetime, str, str]] = set()
    seen_prod_keys: Set[Tuple[datetime, str, str]] = set()

    # 1. Validate Energy Rows
    energy_valid_count = 0
    energy_rejected_count = 0

    for idx, row in enumerate(energy_rows, start=1):
        row_has_err = False

        # Timestamp / Hour
        raw_ts = row.get("timestamp")
        parsed_ts = parse_cell_datetime(raw_ts)
        if not parsed_ts:
            # Try parsing simple "HH:MM" or "H"
            raw_str = str(raw_ts or "").strip()
            if ":" in raw_str and len(raw_str) <= 5:
                try:
                    parts = raw_str.split(":")
                    parsed_ts = datetime(reporting_date.year, reporting_date.month, reporting_date.day, int(parts[0]), int(parts[1]))
                except Exception:
                    parsed_ts = None
            elif raw_str.isdigit() and 0 <= int(raw_str) <= 23:
                parsed_ts = datetime(reporting_date.year, reporting_date.month, reporting_date.day, int(raw_str), 0)

        if not parsed_ts:
            errors.append({
                "tab": "Energy",
                "row": idx,
                "field": "timestamp",
                "message": f"Energy · Row {idx} · Provide a valid hourly timestamp (e.g. {reporting_date.isoformat()} 00:00).",
            })
            row_has_err = True
        elif parsed_ts.date() != reporting_date:
            errors.append({
                "tab": "Energy",
                "row": idx,
                "field": "timestamp",
                "message": f"Energy · Row {idx} · Date {parsed_ts.date()} conflicts with selected date {reporting_date}.",
            })
            row_has_err = True

        # Plant Scope Check
        row_plant = str(row.get("plant_id") or plant_id).strip()
        if row_plant and row_plant != plant_id:
            errors.append({
                "tab": "Energy",
                "row": idx,
                "field": "plant_id",
                "message": f"Energy · Row {idx} · Plant '{row_plant}' conflicts with selected plant '{plant_id}'.",
            })
            row_has_err = True

        # Meter ID Check
        meter_id = str(row.get("meter_id") or "").strip()
        if not meter_id:
            errors.append({
                "tab": "Energy",
                "row": idx,
                "field": "meter_id",
                "message": f"Energy · Row {idx} · Choose a meter.",
            })
            row_has_err = True
        elif meter_id not in valid_meters_set:
            errors.append({
                "tab": "Energy",
                "row": idx,
                "field": "meter_id",
                "message": f"Energy · Row {idx} · Meter '{meter_id}' is not in approved factory submeters ({', '.join(sorted(valid_meters_set))}).",
            })
            row_has_err = True

        # Numeric bounds
        kwh = parse_cell_decimal(row.get("consumption_kwh"))
        if kwh is None or kwh < Decimal("0"):
            errors.append({
                "tab": "Energy",
                "row": idx,
                "field": "consumption_kwh",
                "message": f"Energy · Row {idx} · Consumption (kWh) must be a non-negative number.",
            })
            row_has_err = True

        demand = parse_cell_decimal(row.get("demand_kw"))
        if demand is not None and demand < Decimal("0"):
            errors.append({
                "tab": "Energy",
                "row": idx,
                "field": "demand_kw",
                "message": f"Energy · Row {idx} · Peak demand (kW) must be non-negative.",
            })
            row_has_err = True

        pf = parse_cell_decimal(row.get("power_factor"))
        if pf is not None and (pf < Decimal("0.0") or pf > Decimal("1.0")):
            errors.append({
                "tab": "Energy",
                "row": idx,
                "field": "power_factor",
                "message": f"Energy · Row {idx} · Power factor must be between 0.0 and 1.0.",
            })
            row_has_err = True

        # Business key uniqueness in batch
        if parsed_ts and plant_id and meter_id:
            e_key = (parsed_ts, plant_id, meter_id)
            if e_key in seen_energy_keys:
                errors.append({
                    "tab": "Energy",
                    "row": idx,
                    "field": "meter_id",
                    "message": f"Energy · Row {idx} · Duplicate entry for meter '{meter_id}' at {parsed_ts.strftime('%H:%M')}.",
                })
                row_has_err = True
            else:
                seen_energy_keys.add(e_key)

        if row_has_err:
            energy_rejected_count += 1
        else:
            energy_valid_count += 1

    # 2. Validate Production Rows
    prod_valid_count = 0
    prod_rejected_count = 0

    for idx, row in enumerate(production_rows, start=1):
        row_has_err = False

        # Event Timestamp
        raw_ts = row.get("event_ts")
        parsed_ts = parse_cell_datetime(raw_ts)
        if not parsed_ts:
            raw_str = str(raw_ts or "").strip()
            if ":" in raw_str and len(raw_str) <= 5:
                try:
                    parts = raw_str.split(":")
                    parsed_ts = datetime(reporting_date.year, reporting_date.month, reporting_date.day, int(parts[0]), int(parts[1]))
                except Exception:
                    parsed_ts = None
            elif raw_str.isdigit() and 0 <= int(raw_str) <= 23:
                parsed_ts = datetime(reporting_date.year, reporting_date.month, reporting_date.day, int(raw_str), 0)

        if not parsed_ts:
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "event_ts",
                "message": f"Production · Row {idx} · Provide a valid hourly event timestamp (e.g. {reporting_date.isoformat()} 00:00).",
            })
            row_has_err = True
        elif parsed_ts.date() != reporting_date:
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "event_ts",
                "message": f"Production · Row {idx} · Date {parsed_ts.date()} conflicts with selected date {reporting_date}.",
            })
            row_has_err = True

        # Plant Scope Check
        row_plant = str(row.get("plant_id") or plant_id).strip()
        if row_plant and row_plant != plant_id:
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "plant_id",
                "message": f"Production · Row {idx} · Plant '{row_plant}' conflicts with selected plant '{plant_id}'.",
            })
            row_has_err = True

        # Line ID Check
        line_id = str(row.get("line_id") or "").strip()
        if not line_id:
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "line_id",
                "message": f"Production · Row {idx} · Choose a production line.",
            })
            row_has_err = True
        elif line_id not in valid_lines_set:
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "line_id",
                "message": f"Production · Row {idx} · Line '{line_id}' is not registered to plant '{plant_id}'. Choices: {', '.join(sorted(valid_lines_set))}.",
            })
            row_has_err = True

        # Product ID Check
        product_id = str(row.get("product_id") or "").strip()
        if not product_id:
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "product_id",
                "message": f"Production · Row {idx} · Choose a product SKU.",
            })
            row_has_err = True
        elif product_id not in valid_products_set:
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "product_id",
                "message": f"Production · Row {idx} · Product SKU '{product_id}' not found in catalog ({', '.join(sorted(valid_products_set))}).",
            })
            row_has_err = True

        # Quantities
        actual_qty = parse_cell_int(row.get("actual_qty"))
        good_qty = parse_cell_int(row.get("good_qty"))
        reject_qty = parse_cell_int(row.get("reject_qty"))

        if actual_qty is None or actual_qty < 0:
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "actual_qty",
                "message": f"Production · Row {idx} · Actual quantity must be a non-negative integer.",
            })
            row_has_err = True

        if good_qty is None or good_qty < 0:
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "good_qty",
                "message": f"Production · Row {idx} · Good quantity must be a non-negative integer.",
            })
            row_has_err = True

        if reject_qty is None or reject_qty < 0:
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "reject_qty",
                "message": f"Production · Row {idx} · Reject quantity must be a non-negative integer.",
            })
            row_has_err = True

        # Balance check: actual_qty = good_qty + reject_qty
        if actual_qty is not None and good_qty is not None and reject_qty is not None:
            if actual_qty != (good_qty + reject_qty):
                errors.append({
                    "tab": "Production",
                    "row": idx,
                    "field": "actual_qty",
                    "message": f"Production · Row {idx} · Actual quantity ({actual_qty}) must equal good ({good_qty}) + reject ({reject_qty}).",
                })
                row_has_err = True

        # Downtime Check: 0 <= downtime_min <= 60
        downtime_min = parse_cell_int(row.get("downtime_min"))
        if downtime_min is not None and (downtime_min < 0 or downtime_min > 60):
            errors.append({
                "tab": "Production",
                "row": idx,
                "field": "downtime_min",
                "message": f"Production · Row {idx} · Downtime must be between 0 and 60 minutes.",
            })
            row_has_err = True

        # Unique key in batch
        if parsed_ts and plant_id and line_id:
            p_key = (parsed_ts, plant_id, line_id)
            if p_key in seen_prod_keys:
                errors.append({
                    "tab": "Production",
                    "row": idx,
                    "field": "line_id",
                    "message": f"Production · Row {idx} · Duplicate production event for line '{line_id}' at {parsed_ts.strftime('%H:%M')}.",
                })
                row_has_err = True
            else:
                seen_prod_keys.add(p_key)

        if row_has_err:
            prod_rejected_count += 1
        else:
            prod_valid_count += 1

    is_valid = len(errors) == 0

    return {
        "is_valid": is_valid,
        "valid": is_valid,
        "total_valid": energy_valid_count + prod_valid_count,
        "total_errors": len(errors),
        "errors": errors,
        "energy_summary": {
            "total_rows": len(energy_rows),
            "valid_rows": energy_valid_count,
            "rejected_rows": energy_rejected_count,
        },
        "production_summary": {
            "total_rows": len(production_rows),
            "valid_rows": prod_valid_count,
            "rejected_rows": prod_rejected_count,
        },
    }


def save_manual_entries(
    session: Session,
    reporting_date: date,
    plant_id: str,
    energy_rows: List[Dict[str, Any]],
    production_rows: List[Dict[str, Any]],
    entry_type: str = "MANUAL",
    mode: str = "INCREMENTAL",
) -> Dict[str, Any]:
    """
    Validates and idempotently commits Energy and Production records into Neon PostgreSQL.
    Re-validates on the server before committing.
    Preserves record identity and source revisions for complete lineage auditability.
    """
    # 1. Server-side revalidation
    validation = validate_manual_entries(
        session=session,
        reporting_date=reporting_date,
        plant_id=plant_id,
        energy_rows=energy_rows,
        production_rows=production_rows,
        mode=mode,
    )

    if not validation["is_valid"]:
        raise ValueError(
            f"Validation failed with {len(validation['errors'])} error(s): "
            + "; ".join([e["message"] for e in validation["errors"][:3]])
        )

    now_ts = datetime.utcnow()
    energy_upload_id = None
    prod_upload_id = None
    energy_saved_count = 0
    prod_saved_count = 0

    source_system_val = "MANUAL_ENTRY" if entry_type.upper() == "MANUAL" else "CLIPBOARD_PASTE"

    # 2. Persist Energy records
    if energy_rows:
        energy_upload_id = f"ENTRY-{reporting_date.strftime('%Y%m%d')}-{entry_type[:6].upper()}-E{uuid.uuid4().hex[:6].upper()}"

        # Register UploadHistory record
        energy_upload = UploadHistory(
            upload_id=energy_upload_id,
            uploaded_at=now_ts,
            filename=f"{entry_type.lower()}_energy_{reporting_date.isoformat()}.json",
            file_format=source_system_val,
            report_type="ENERGY",
            reporting_date=reporting_date,
            file_size_bytes=len(json.dumps(energy_rows)),
            total_rows=len(energy_rows),
            valid_rows=len(energy_rows),
            rejected_rows=0,
            duplicate_rows=0,
            status="COMPLETED",
            mode=mode,
            audit_details=json.dumps({"source_system": source_system_val, "entry_type": entry_type}),
        )
        session.add(energy_upload)
        session.flush()

        for idx, row in enumerate(energy_rows, start=1):
            raw_ts = row.get("timestamp")
            parsed_ts = parse_cell_datetime(raw_ts)
            if not parsed_ts:
                raw_str = str(raw_ts or "").strip()
                if ":" in raw_str and len(raw_str) <= 5:
                    parts = raw_str.split(":")
                    parsed_ts = datetime(reporting_date.year, reporting_date.month, reporting_date.day, int(parts[0]), int(parts[1]))
                elif raw_str.isdigit():
                    parsed_ts = datetime(reporting_date.year, reporting_date.month, reporting_date.day, int(raw_str), 0)

            meter_id = str(row["meter_id"]).strip()
            area = str(row.get("area") or METER_AREA_MAPPING.get(meter_id, "SMT")).strip()
            energy_source = str(row.get("energy_source") or "ELECTRICITY").strip()
            raw_kwh = parse_cell_decimal(row.get("consumption_kwh"))
            kwh = raw_kwh if raw_kwh is not None else Decimal("0")
            demand = parse_cell_decimal(row.get("demand_kw"))
            pf = parse_cell_decimal(row.get("power_factor"))
            tariff = parse_cell_decimal(row.get("tariff_inr_per_kwh")) or DEFAULT_TARIFF_INR_PER_KWH
            raw_cost = parse_cell_decimal(row.get("cost_inr"))
            cost = raw_cost if raw_cost is not None else Decimal(str(round(float(kwh) * float(tariff), 2)))
            raw_co2 = parse_cell_decimal(row.get("co2e_kg"))
            co2e = raw_co2 if raw_co2 is not None else Decimal(str(round(float(kwh) * float(DEFAULT_GRID_EMISSIONS_FACTOR), 4)))
            quality = str(row.get("reading_quality") or "VALID").strip()

            # Check existing record for business key: (timestamp, plant_id, meter_id)
            existing = (
                session.execute(
                    select(FactEnergyMeterHourly).where(
                        FactEnergyMeterHourly.timestamp == parsed_ts,
                        FactEnergyMeterHourly.plant_id == plant_id,
                        FactEnergyMeterHourly.meter_id == meter_id,
                    )
                )
                .scalars()
                .first()
            )

            if existing:
                reading_id = existing.meter_reading_id

                # Detect if any values actually changed
                is_changed = (
                    existing.date != reporting_date or
                    existing.area != area or
                    existing.energy_source != energy_source or
                    (existing.consumption_kwh is None) != (kwh is None) or
                    (existing.consumption_kwh is not None and kwh is not None and abs(Decimal(str(existing.consumption_kwh)) - kwh) > Decimal("0.00001")) or
                    (existing.demand_kw is None) != (demand is None) or
                    (existing.demand_kw is not None and demand is not None and abs(Decimal(str(existing.demand_kw)) - demand) > Decimal("0.00001")) or
                    (existing.power_factor is None) != (pf is None) or
                    (existing.power_factor is not None and pf is not None and abs(Decimal(str(existing.power_factor)) - pf) > Decimal("0.00001")) or
                    (existing.tariff_inr_per_kwh is None) != (tariff is None) or
                    (existing.tariff_inr_per_kwh is not None and tariff is not None and abs(Decimal(str(existing.tariff_inr_per_kwh)) - tariff) > Decimal("0.00001")) or
                    (existing.cost_inr is None) != (cost is None) or
                    (existing.cost_inr is not None and cost is not None and abs(Decimal(str(existing.cost_inr)) - cost) > Decimal("0.00001")) or
                    (existing.co2e_kg is None) != (co2e is None) or
                    (existing.co2e_kg is not None and co2e is not None and abs(Decimal(str(existing.co2e_kg)) - co2e) > Decimal("0.00001")) or
                    (existing.reading_quality or "VALID") != quality
                )

                if is_changed:
                    existing.date = reporting_date
                    existing.area = area
                    existing.energy_source = energy_source
                    existing.consumption_kwh = kwh
                    existing.demand_kw = demand
                    existing.power_factor = pf
                    existing.tariff_inr_per_kwh = tariff
                    existing.cost_inr = cost
                    existing.co2e_kg = co2e
                    existing.reading_quality = quality
                    existing.upload_id = energy_upload_id
                    existing.ingested_at = now_ts

                    # Write audit revision only when values changed
                    b_key = f"{parsed_ts.isoformat()}|{plant_id}|{meter_id}"
                    rev = FactSourceRevision(
                        revision_id=f"REV-EN-{uuid.uuid4().hex[:12].upper()}",
                        source_table="fact_energy_meter_hourly",
                        source_record_id=reading_id,
                        business_key=b_key,
                        plant_id=plant_id,
                        upload_id=energy_upload_id,
                        revision_timestamp=now_ts,
                        source_values_json=json.dumps({
                            "consumption_kwh": str(kwh) if kwh is not None else None,
                            "demand_kw": str(demand) if demand is not None else None,
                            "power_factor": str(pf) if pf is not None else None,
                            "tariff_inr_per_kwh": str(tariff) if tariff is not None else None,
                            "cost_inr": str(cost) if cost is not None else None,
                            "co2e_kg": str(co2e) if co2e is not None else None,
                            "reading_quality": quality,
                            "entry_type": entry_type,
                        }),
                        is_current=True,
                    )
                    session.add(rev)
                # If not is_changed: identical retry preserves timestamps and audit history!
                energy_saved_count += 1
            else:
                reading_id = str(row.get("meter_reading_id") or "").strip()
                if not reading_id:
                    reading_id = f"EN-{int(time.time() * 1000) % 100000000:08d}-{idx}"

                new_record = FactEnergyMeterHourly(
                    meter_reading_id=reading_id,
                    timestamp=parsed_ts,
                    date=reporting_date,
                    plant_id=plant_id,
                    meter_id=meter_id,
                    area=area,
                    energy_source=energy_source,
                    consumption_kwh=kwh,
                    demand_kw=demand,
                    power_factor=pf,
                    tariff_inr_per_kwh=tariff,
                    cost_inr=cost,
                    co2e_kg=co2e,
                    reading_quality=quality,
                    upload_id=energy_upload_id,
                    ingested_at=now_ts,
                )
                session.add(new_record)

                # Record source revision for new record
                b_key = f"{parsed_ts.isoformat()}|{plant_id}|{meter_id}"
                rev = FactSourceRevision(
                    revision_id=f"REV-EN-{uuid.uuid4().hex[:12].upper()}",
                    source_table="fact_energy_meter_hourly",
                    source_record_id=reading_id,
                    business_key=b_key,
                    plant_id=plant_id,
                    upload_id=energy_upload_id,
                    revision_timestamp=now_ts,
                    source_values_json=json.dumps({
                        "consumption_kwh": str(kwh) if kwh is not None else None,
                        "demand_kw": str(demand) if demand is not None else None,
                        "power_factor": str(pf) if pf is not None else None,
                        "tariff_inr_per_kwh": str(tariff) if tariff is not None else None,
                        "cost_inr": str(cost) if cost is not None else None,
                        "co2e_kg": str(co2e) if co2e is not None else None,
                        "reading_quality": quality,
                        "entry_type": entry_type,
                    }),
                    is_current=True,
                )
                session.add(rev)
                energy_saved_count += 1

    # 3. Persist Production records
    if production_rows:
        prod_upload_id = f"ENTRY-{reporting_date.strftime('%Y%m%d')}-{entry_type[:6].upper()}-P{uuid.uuid4().hex[:6].upper()}"

        prod_upload = UploadHistory(
            upload_id=prod_upload_id,
            uploaded_at=now_ts,
            filename=f"{entry_type.lower()}_production_{reporting_date.isoformat()}.json",
            file_format=source_system_val,
            report_type="PRODUCTION",
            reporting_date=reporting_date,
            file_size_bytes=len(json.dumps(production_rows)),
            total_rows=len(production_rows),
            valid_rows=len(production_rows),
            rejected_rows=0,
            duplicate_rows=0,
            status="COMPLETED",
            mode=mode,
            audit_details=json.dumps({"source_system": source_system_val, "entry_type": entry_type}),
        )
        session.add(prod_upload)
        session.flush()

        for idx, row in enumerate(production_rows, start=1):
            raw_ts = row.get("event_ts")
            parsed_ts = parse_cell_datetime(raw_ts)
            if not parsed_ts:
                raw_str = str(raw_ts or "").strip()
                if ":" in raw_str and len(raw_str) <= 5:
                    parts = raw_str.split(":")
                    parsed_ts = datetime(reporting_date.year, reporting_date.month, reporting_date.day, int(parts[0]), int(parts[1]))
                elif raw_str.isdigit():
                    parsed_ts = datetime(reporting_date.year, reporting_date.month, reporting_date.day, int(raw_str), 0)

            line_id = str(row["line_id"]).strip()
            shift_id = str(row.get("shift_id") or "A").strip()
            product_id = str(row["product_id"]).strip()
            po_id = str(row.get("production_order_id") or f"PO-{reporting_date.strftime('%Y%m%d')}-{idx:02d}").strip()
            target_qty = parse_cell_int(row.get("target_qty")) or 0
            actual_qty = parse_cell_int(row["actual_qty"]) or 0
            good_qty = parse_cell_int(row["good_qty"]) or 0
            reject_qty = parse_cell_int(row["reject_qty"]) or 0
            rework_qty = parse_cell_int(row.get("rework_qty")) or 0
            downtime_min = parse_cell_int(row.get("downtime_min")) or 0
            downtime_reason = str(row.get("downtime_reason") or "NONE").strip()
            operator_team = str(row.get("operator_team") or "TEAM-01").strip()
            data_quality = str(row.get("data_quality") or "VALID").strip()

            existing = (
                session.execute(
                    select(FactHourlyProduction).where(
                        FactHourlyProduction.event_ts == parsed_ts,
                        FactHourlyProduction.plant_id == plant_id,
                        FactHourlyProduction.line_id == line_id,
                    )
                )
                .scalars()
                .first()
            )

            if existing:
                event_id = existing.event_id

                # Detect if any values actually changed
                is_changed = (
                    existing.event_date != reporting_date or
                    existing.shift_id != shift_id or
                    existing.product_id != product_id or
                    existing.production_order_id != po_id or
                    existing.target_qty != target_qty or
                    existing.actual_qty != actual_qty or
                    existing.good_qty != good_qty or
                    existing.reject_qty != reject_qty or
                    existing.rework_qty != rework_qty or
                    existing.downtime_min != downtime_min or
                    (existing.downtime_reason or "NONE") != downtime_reason or
                    (existing.operator_team or "TEAM-01") != operator_team or
                    (existing.data_quality or "VALID") != data_quality
                )

                if is_changed:
                    existing.event_date = reporting_date
                    existing.year = parsed_ts.year
                    existing.month = parsed_ts.month
                    existing.week = parsed_ts.isocalendar()[1]
                    existing.day = parsed_ts.day
                    existing.hour = parsed_ts.hour
                    existing.shift_id = shift_id
                    existing.product_id = product_id
                    existing.production_order_id = po_id
                    existing.target_qty = target_qty
                    existing.actual_qty = actual_qty
                    existing.good_qty = good_qty
                    existing.reject_qty = reject_qty
                    existing.rework_qty = rework_qty
                    existing.downtime_min = downtime_min
                    existing.downtime_reason = downtime_reason
                    existing.operator_team = operator_team
                    existing.source_system = source_system_val
                    existing.data_quality = data_quality
                    existing.upload_id = prod_upload_id
                    existing.ingested_at = now_ts

                    # Write audit revision only when values changed
                    b_key = f"{parsed_ts.isoformat()}|{plant_id}|{line_id}"
                    rev = FactSourceRevision(
                        revision_id=f"REV-PRD-{uuid.uuid4().hex[:12].upper()}",
                        source_table="fact_hourly_production",
                        source_record_id=event_id,
                        business_key=b_key,
                        plant_id=plant_id,
                        upload_id=prod_upload_id,
                        revision_timestamp=now_ts,
                        source_values_json=json.dumps({
                            "product_id": product_id,
                            "target_qty": target_qty,
                            "actual_qty": actual_qty,
                            "good_qty": good_qty,
                            "reject_qty": reject_qty,
                            "rework_qty": rework_qty,
                            "downtime_min": downtime_min,
                            "entry_type": entry_type,
                        }),
                        is_current=True,
                    )
                    session.add(rev)
                # If not is_changed: identical retry preserves timestamps and audit history!
                prod_saved_count += 1
            else:
                event_id = str(row.get("event_id") or "").strip()
                if not event_id:
                    event_id = f"PRD-{uuid.uuid4().hex[:10].upper()}"

                new_record = FactHourlyProduction(
                    event_id=event_id,
                    event_ts=parsed_ts,
                    event_date=reporting_date,
                    year=parsed_ts.year,
                    month=parsed_ts.month,
                    week=parsed_ts.isocalendar()[1],
                    day=parsed_ts.day,
                    hour=parsed_ts.hour,
                    plant_id=plant_id,
                    line_id=line_id,
                    shift_id=shift_id,
                    product_id=product_id,
                    production_order_id=po_id,
                    target_qty=target_qty,
                    actual_qty=actual_qty,
                    good_qty=good_qty,
                    reject_qty=reject_qty,
                    rework_qty=rework_qty,
                    downtime_min=downtime_min,
                    downtime_reason=downtime_reason,
                    operator_team=operator_team,
                    source_system=source_system_val,
                    data_quality=data_quality,
                    upload_id=prod_upload_id,
                    ingested_at=now_ts,
                )
                session.add(new_record)

                # Record source revision for new record
                b_key = f"{parsed_ts.isoformat()}|{plant_id}|{line_id}"
                rev = FactSourceRevision(
                    revision_id=f"REV-PRD-{uuid.uuid4().hex[:12].upper()}",
                    source_table="fact_hourly_production",
                    source_record_id=event_id,
                    business_key=b_key,
                    plant_id=plant_id,
                    upload_id=prod_upload_id,
                    revision_timestamp=now_ts,
                    source_values_json=json.dumps({
                        "product_id": product_id,
                        "target_qty": target_qty,
                        "actual_qty": actual_qty,
                        "good_qty": good_qty,
                        "reject_qty": reject_qty,
                        "rework_qty": rework_qty,
                        "downtime_min": downtime_min,
                        "entry_type": entry_type,
                    }),
                    is_current=True,
                )
                session.add(rev)
                prod_saved_count += 1

    session.commit()

    # Query confirmed database counts for this plant and reporting date
    total_energy_query = (
        select(func.count(FactEnergyMeterHourly.meter_reading_id))
        .where(
            FactEnergyMeterHourly.date == reporting_date,
            FactEnergyMeterHourly.plant_id == plant_id,
        )
    )
    total_prod_query = (
        select(func.count(FactHourlyProduction.event_id))
        .where(
            FactHourlyProduction.event_date == reporting_date,
            FactHourlyProduction.plant_id == plant_id,
        )
    )
    db_energy_count = session.execute(total_energy_query).scalar() or 0
    db_prod_count = session.execute(total_prod_query).scalar() or 0

    # 4. Synchronize Daily Pipeline Run status for Stages 1, 2, and 3
    total_saved = energy_saved_count + prod_saved_count
    entry_summary = f"{db_energy_count} Energy entries · {db_prod_count} Production entries"

    record_pipeline_stage_state(
        reporting_date=reporting_date,
        stage_id="data_upload",
        status="COMPLETED",
        summary=entry_summary,
        details={
            "entry_type": entry_type,
            "energy_saved": energy_saved_count,
            "production_saved": prod_saved_count,
            "total_energy_count": db_energy_count,
            "total_production_count": db_prod_count,
            "energy_upload_id": energy_upload_id,
            "production_upload_id": prod_upload_id,
        },
    )

    record_pipeline_stage_state(
        reporting_date=reporting_date,
        stage_id="validation",
        status="COMPLETED",
        summary=f"All {total_saved} records verified against schema, foreign keys, and balance constraints.",
        details={
            "total_valid_rows": total_saved,
            "total_rejected_rows": 0,
            "energy_valid_rows": energy_saved_count,
            "production_valid_rows": prod_saved_count,
        },
    )

    record_pipeline_stage_state(
        reporting_date=reporting_date,
        stage_id="database_ingestion",
        status="COMPLETED",
        summary=f"Committed {energy_saved_count} energy and {prod_saved_count} production records into PostgreSQL fact tables.",
        details={
            "committed_energy_rows": energy_saved_count,
            "committed_production_rows": prod_saved_count,
            "energy_records": energy_saved_count,
            "production_records": prod_saved_count,
            "energy_upload_id": energy_upload_id,
            "production_upload_id": prod_upload_id,
            "entry_mode": mode,
        },
    )

    return {
        "success": True,
        "energy_saved": energy_saved_count,
        "production_saved": prod_saved_count,
        "energy_records_written": energy_saved_count,
        "production_records_written": prod_saved_count,
        "energy_upload_id": energy_upload_id,
        "production_upload_id": prod_upload_id,
        "message": f"Successfully validated and saved {energy_saved_count} energy and {prod_saved_count} production records to Neon PostgreSQL.",
    }
