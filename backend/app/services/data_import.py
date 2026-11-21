"""Controlled CSV data ingestion service for Industrial Energy Intelligence Platform."""

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List
import zipfile

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.db import get_engine, get_session_factory
from app.models.source_data import (
    DimProduct,
    DimProductionLine,
    FactEnergyMeterHourly,
    FactHourlyProduction,
    DimMachine,
    DimShiftCalendar,
    FactMachineTelemetryHourly,
    FactUtilityTelemetryHourly,
    FactDowntimeEvent,
    FactMaintenanceWorkOrder,
)

DATASETS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "datasets"

EXPECTED_FILES = {
    "dim_product": DATASETS_DIR / "dim_product.csv",
    "dim_production_line": DATASETS_DIR / "dim_production_line.csv",
    "fact_energy_meter_hourly": DATASETS_DIR / "fact_energy_meter_hourly.csv",
    "fact_hourly_production": DATASETS_DIR / "fact_hourly_production.csv",
}

EXPECTED_COUNTS = {
    "dim_product": 3,
    "dim_production_line": 4,
    "fact_energy_meter_hourly": 22080,
    "fact_hourly_production": 8832,
}


def run_pre_import_checks(engine) -> Dict[str, Any]:
    """Execute pre-import safety validations against Neon database and CSV files."""
    results = {}

    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT current_database()")).scalar()
        if db_name != "neondb":
            raise RuntimeError(f"Target database is '{db_name}', expected 'neondb'. Aborting import.")
        results["database_name"] = db_name

        # Check Alembic revision
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if rev not in ("be415c420bad", "c7a19e28f01b"):
            raise RuntimeError(f"Alembic revision is '{rev}', expected 'be415c420bad' or 'c7a19e28f01b'. Aborting import.")
        results["alembic_revision"] = rev

        # Check tables existence and row counts
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names(schema="public"))
        target_tables = set(EXPECTED_COUNTS.keys())

        if not target_tables.issubset(existing_tables):
            missing = target_tables - existing_tables
            raise RuntimeError(f"Missing target tables in database: {missing}. Aborting import.")

        table_counts = {}
        for table in target_tables:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            table_counts[table] = cnt
            if cnt > 0:
                raise RuntimeError(
                    f"Table '{table}' contains {cnt} existing records. Expected 0. Aborting import."
                )
        results["table_counts"] = table_counts

    # Check source files existence and readability
    file_status = {}
    for name, path in EXPECTED_FILES.items():
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            file_status[name] = {"columns": len(header), "path": str(path)}
    results["source_files"] = file_status

    return results


def parse_dim_product_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse a single dim_product CSV row into typed model mapping."""
    return {
        "product_id": row["product_id"].strip(),
        "product_name": row["product_name"].strip(),
        "product_family": row["product_family"].strip(),
        "ram": row["ram"].strip(),
        "storage": row["storage"].strip(),
        "display": row["display"].strip(),
        "model_revision": row["model_revision"].strip(),
        "standard_cycle_sec": int(row["standard_cycle_sec"]),
        "standard_unit_cost_inr": Decimal(row["standard_unit_cost_inr"]),
        "active_from": date.fromisoformat(row["active_from"].strip()),
        "active_to": date.fromisoformat(row["active_to"].strip()),
    }


def parse_dim_production_line_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse a single dim_production_line CSV row into typed model mapping."""
    return {
        "line_id": row["line_id"].strip(),
        "plant_id": row["plant_id"].strip(),
        "line_type": row["line_type"].strip(),
        "nominal_capacity_per_hour": int(row["nominal_capacity_per_hour"]),
        "takt_time_sec": Decimal(row["takt_time_sec"]),
        "area": row["area"].strip(),
    }


def parse_energy_meter_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse a single fact_energy_meter_hourly CSV row into typed model mapping."""
    return {
        "meter_reading_id": row["meter_reading_id"].strip(),
        "timestamp": datetime.fromisoformat(row["timestamp"].strip()),
        "date": date.fromisoformat(row["date"].strip()),
        "plant_id": row["plant_id"].strip(),
        "meter_id": row["meter_id"].strip(),
        "area": row["area"].strip(),
        "energy_source": row["energy_source"].strip(),
        "consumption_kwh": Decimal(row["consumption_kwh"]),
        "demand_kw": Decimal(row["demand_kw"]),
        "power_factor": Decimal(row["power_factor"]),
        "tariff_inr_per_kwh": Decimal(row["tariff_inr_per_kwh"]),
        "cost_inr": Decimal(row["cost_inr"]),
        "co2e_kg": Decimal(row["co2e_kg"]),
        "reading_quality": row["reading_quality"].strip(),
    }


def parse_production_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse a single fact_hourly_production CSV row into typed model mapping."""
    return {
        "event_id": row["event_id"].strip(),
        "event_ts": datetime.fromisoformat(row["event_ts"].strip()),
        "event_date": date.fromisoformat(row["event_date"].strip()),
        "year": int(row["year"]),
        "month": int(row["month"]),
        "week": int(row["week"]),
        "day": int(row["day"]),
        "hour": int(row["hour"]),
        "plant_id": row["plant_id"].strip(),
        "line_id": row["line_id"].strip(),
        "shift_id": row["shift_id"].strip(),
        "product_id": row["product_id"].strip(),
        "production_order_id": row["production_order_id"].strip(),
        "target_qty": int(row["target_qty"]),
        "actual_qty": int(row["actual_qty"]),
        "good_qty": int(row["good_qty"]),
        "reject_qty": int(row["reject_qty"]),
        "rework_qty": int(row["rework_qty"]),
        "downtime_min": int(row["downtime_min"]),
        "downtime_reason": row["downtime_reason"].strip(),
        "operator_team": row["operator_team"].strip(),
        "source_system": row["source_system"].strip(),
        "data_quality": row["data_quality"].strip(),
    }


def import_csv_in_batches(
    session: Session,
    model: Any,
    csv_path: Path,
    row_parser: Any,
    batch_size: int = 2000,
) -> int:
    """Stream and insert CSV records in transactional batches."""
    count = 0
    batch = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            batch.append(row_parser(row))
            count += 1
            if len(batch) >= batch_size:
                session.bulk_insert_mappings(model, batch)
                batch.clear()

        if batch:
            session.bulk_insert_mappings(model, batch)
            batch.clear()

    return count


def import_csv_from_reader(
    session: Session,
    model: Any,
    reader: csv.DictReader,
    row_parser: Any,
    batch_size: int = 2500,
) -> int:
    """Stream and insert records from an open DictReader in transactional batches."""
    count = 0
    batch = []
    for row in reader:
        batch.append(row_parser(row))
        count += 1
        if len(batch) >= batch_size:
            session.bulk_insert_mappings(model, batch)
            batch.clear()

    if batch:
        session.bulk_insert_mappings(model, batch)
        batch.clear()

    return count


def parse_dim_machine_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse a single dim_machine CSV row into typed model mapping."""
    return {
        "machine_id": row["machine_id"].strip(),
        "machine_name": row["machine_name"].strip(),
        "machine_type": row["machine_type"].strip(),
        "line_id": row["line_id"].strip(),
        "plant_id": row["plant_id"].strip(),
        "criticality": row["criticality"].strip(),
        "commissioned_date": date.fromisoformat(row["commissioned_date"].strip()),
        "planned_maintenance_interval_days": int(row["planned_maintenance_interval_days"]),
    }


def parse_dim_shift_calendar_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse a single dim_shift_calendar CSV row into typed model mapping."""
    return {
        "calendar_date": date.fromisoformat(row["calendar_date"].strip()),
        "shift_id": row["shift_id"].strip(),
        "shift_start": datetime.fromisoformat(row["shift_start"].strip()),
        "shift_end": datetime.fromisoformat(row["shift_end"].strip()),
        "planned_minutes": int(row["planned_minutes"]),
        "break_minutes": int(row["break_minutes"]),
        "is_working_day": row["is_working_day"].strip().lower() in ("true", "1", "t"),
    }


def parse_machine_telemetry_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse a single fact_machine_telemetry_hourly CSV row into typed model mapping."""
    temp_val = row.get("temperature_c", "").strip()
    vib_val = row.get("vibration_mm_s", "").strip()
    cur_val = row.get("motor_current_a", "").strip()
    pres_val = row.get("pressure_bar", "").strip()
    rpm_val = row.get("rpm", "").strip()

    return {
        "telemetry_id": row["telemetry_id"].strip(),
        "timestamp": datetime.fromisoformat(row["timestamp"].strip()),
        "date": date.fromisoformat(row["date"].strip()),
        "machine_id": row["machine_id"].strip(),
        "plant_id": row["plant_id"].strip(),
        "line_id": row["line_id"].strip(),
        "shift_id": row["shift_id"].strip(),
        "temperature_c": Decimal(temp_val) if temp_val else None,
        "vibration_mm_s": Decimal(vib_val) if vib_val else None,
        "motor_current_a": Decimal(cur_val) if cur_val else None,
        "pressure_bar": Decimal(pres_val) if pres_val else None,
        "rpm": Decimal(rpm_val) if rpm_val else None,
        "machine_state": row["machine_state"].strip(),
        "alarm_code": row["alarm_code"].strip(),
        "sensor_health": row["sensor_health"].strip(),
        "is_anomaly": row["is_anomaly"].strip().lower() in ("true", "1", "t"),
    }


def parse_utility_telemetry_row(row: Dict[str, str]) -> Dict[str, Any]:
    """
    Parse a single fact_utility_telemetry_hourly CSV row into typed model mapping.
    Preserves raw consumption_unit (e.g. 'm3', 'L', 'kWh') without assuming it defines
    the unit or time basis of flow_rate.
    """
    flow_val = row.get("flow_rate", "").strip()
    pres_val = row.get("pressure_bar", "").strip()
    temp_val = row.get("temperature_c", "").strip()

    return {
        "utility_reading_id": row["utility_reading_id"].strip(),
        "timestamp": datetime.fromisoformat(row["timestamp"].strip()),
        "plant_id": row["plant_id"].strip(),
        "utility_type": row["utility_type"].strip(),
        "zone": row["zone"].strip(),
        "flow_rate": Decimal(flow_val) if flow_val else None,
        "pressure_bar": Decimal(pres_val) if pres_val else None,
        "temperature_c": Decimal(temp_val) if temp_val else None,
        "consumption_unit": row["consumption_unit"].strip(),
        "equipment_id": row["equipment_id"].strip(),
        "operating_status": row["operating_status"].strip(),
        "alarm_code": row["alarm_code"].strip(),
        "upload_id": "UPLOAD_DATASET_INITIAL",
        "source_revision_id": f"REV_{row['utility_reading_id'].strip()}_V1",
        "is_corrected": False,
        "created_at": datetime.utcnow(),
    }


def parse_downtime_event_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse a single fact_downtime_event CSV row into typed model mapping."""
    impact_val = row.get("impact_units", "").strip()
    return {
        "downtime_id": row["downtime_id"].strip(),
        "machine_id": row["machine_id"].strip(),
        "plant_id": row["plant_id"].strip(),
        "line_id": row["line_id"].strip(),
        "start_ts": datetime.fromisoformat(row["start_ts"].strip()),
        "duration_min": int(row["duration_min"].strip()),
        "reason_code": row["reason_code"].strip(),
        "impact_units": int(impact_val) if impact_val else None,
        "maintenance_required": row["maintenance_required"].strip().lower() in ("true", "1", "t"),
        "acknowledged_by": row.get("acknowledged_by", "").strip() or None,
        "closure_status": row["closure_status"].strip(),
        "upload_id": "UPLOAD_DATASET_INITIAL",
    }


def parse_maintenance_work_order_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse a single fact_maintenance_work_order CSV row into typed model mapping."""
    p_start = row.get("planned_start", "").strip()
    a_start = row.get("actual_start", "").strip()
    avoid_val = row.get("downtime_avoided_estimate_min", "").strip()
    return {
        "work_order_id": row["work_order_id"].strip(),
        "machine_id": row["machine_id"].strip(),
        "plant_id": row["plant_id"].strip(),
        "created_ts": datetime.fromisoformat(row["created_ts"].strip()),
        "maintenance_type": row["maintenance_type"].strip(),
        "failure_mode": row.get("failure_mode", "").strip() or None,
        "priority": row["priority"].strip(),
        "planned_start": datetime.fromisoformat(p_start) if p_start else None,
        "actual_start": datetime.fromisoformat(a_start) if a_start else None,
        "downtime_avoided_estimate_min": int(avoid_val) if avoid_val else None,
        "status": row["status"].strip(),
        "technician_id": row.get("technician_id", "").strip() or None,
        "upload_id": "UPLOAD_DATASET_INITIAL",
    }


def import_operating_context_datasets() -> Dict[str, Any]:
    """
    Import optional operating context datasets (dim_machine, dim_shift_calendar,
    fact_machine_telemetry_hourly, fact_utility_telemetry_hourly, fact_downtime_event,
    fact_maintenance_work_order) from datasets/data.zip idempotently.
    """
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")

    zip_path = DATASETS_DIR / "data.zip"
    if not zip_path.exists():
        raise FileNotFoundError(f"data.zip not found at {zip_path}")

    with engine.connect() as conn:
        m_count = conn.execute(text("SELECT COUNT(*) FROM dim_machine")).scalar()
        s_count = conn.execute(text("SELECT COUNT(*) FROM dim_shift_calendar")).scalar()
        t_count = conn.execute(text("SELECT COUNT(*) FROM fact_machine_telemetry_hourly")).scalar()
        u_count = conn.execute(text("SELECT COUNT(*) FROM fact_utility_telemetry_hourly")).scalar()
        dt_count = conn.execute(text("SELECT COUNT(*) FROM fact_downtime_event")).scalar()
        mwo_count = conn.execute(text("SELECT COUNT(*) FROM fact_maintenance_work_order")).scalar()

        if (
            m_count >= 15
            and s_count >= 276
            and t_count >= 33120
            and u_count >= 22080
            and dt_count >= 1000
            and mwo_count >= 400
        ):
            return {
                "status": "already_imported",
                "counts": {
                    "dim_machine": m_count,
                    "dim_shift_calendar": s_count,
                    "fact_machine_telemetry_hourly": t_count,
                    "fact_utility_telemetry_hourly": u_count,
                    "fact_downtime_event": dt_count,
                    "fact_maintenance_work_order": mwo_count,
                },
            }

    session_factory = get_session_factory()
    counts = {}

    with zipfile.ZipFile(zip_path, "r") as z:
        with session_factory() as session:
            try:
                # 1. dim_machine
                if m_count == 0:
                    with z.open("data/dim_machine.csv") as f:
                        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                        m_imported = import_csv_from_reader(
                            session, DimMachine, reader, parse_dim_machine_row, batch_size=100
                        )
                        counts["dim_machine"] = m_imported
                else:
                    counts["dim_machine"] = m_count

                # 2. dim_shift_calendar
                if s_count == 0:
                    with z.open("data/dim_shift_calendar.csv") as f:
                        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                        s_imported = import_csv_from_reader(
                            session, DimShiftCalendar, reader, parse_dim_shift_calendar_row, batch_size=500
                        )
                        counts["dim_shift_calendar"] = s_imported
                else:
                    counts["dim_shift_calendar"] = s_count

                # 3. fact_machine_telemetry_hourly
                if t_count == 0:
                    with z.open("data/fact_machine_telemetry_hourly.csv") as f:
                        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                        t_imported = import_csv_from_reader(
                            session, FactMachineTelemetryHourly, reader, parse_machine_telemetry_row, batch_size=2500
                        )
                        counts["fact_machine_telemetry_hourly"] = t_imported
                else:
                    counts["fact_machine_telemetry_hourly"] = t_count

                # 4. fact_utility_telemetry_hourly
                if u_count == 0:
                    with z.open("data/fact_utility_telemetry_hourly.csv") as f:
                        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                        u_imported = import_csv_from_reader(
                            session, FactUtilityTelemetryHourly, reader, parse_utility_telemetry_row, batch_size=2500
                        )
                        counts["fact_utility_telemetry_hourly"] = u_imported
                else:
                    counts["fact_utility_telemetry_hourly"] = u_count

                # 5. fact_downtime_event
                if dt_count == 0:
                    with z.open("data/fact_downtime_event.csv") as f:
                        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                        dt_imported = import_csv_from_reader(
                            session, FactDowntimeEvent, reader, parse_downtime_event_row, batch_size=1000
                        )
                        counts["fact_downtime_event"] = dt_imported
                else:
                    counts["fact_downtime_event"] = dt_count

                # 6. fact_maintenance_work_order
                if mwo_count == 0:
                    with z.open("data/fact_maintenance_work_order.csv") as f:
                        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                        mwo_imported = import_csv_from_reader(
                            session, FactMaintenanceWorkOrder, reader, parse_maintenance_work_order_row, batch_size=500
                        )
                        counts["fact_maintenance_work_order"] = mwo_imported
                else:
                    counts["fact_maintenance_work_order"] = mwo_count

                session.commit()
            except Exception as exc:
                session.rollback()
                raise RuntimeError(f"Operating context import failed, rolled back: {exc}") from exc

    return {"status": "success", "counts": counts}


def execute_full_import() -> Dict[str, Any]:
    """Execute complete controlled import of the 4 CSV files into Neon."""
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")

    print("Executing pre-import safety checks...")
    pre_checks = run_pre_import_checks(engine)
    print("Pre-import checks passed successfully.")

    session_factory = get_session_factory()
    import_counts = {}

    with session_factory() as session:
        try:
            print("Importing 1/4: dim_product.csv ...")
            p_count = import_csv_in_batches(
                session,
                DimProduct,
                EXPECTED_FILES["dim_product"],
                parse_dim_product_row,
            )
            import_counts["dim_product"] = p_count
            print(f"  dim_product: {p_count} records inserted.")

            print("Importing 2/4: dim_production_line.csv ...")
            l_count = import_csv_in_batches(
                session,
                DimProductionLine,
                EXPECTED_FILES["dim_production_line"],
                parse_dim_production_line_row,
            )
            import_counts["dim_production_line"] = l_count
            print(f"  dim_production_line: {l_count} records inserted.")

            print("Importing 3/4: fact_energy_meter_hourly.csv ...")
            e_count = import_csv_in_batches(
                session,
                FactEnergyMeterHourly,
                EXPECTED_FILES["fact_energy_meter_hourly"],
                parse_energy_meter_row,
                batch_size=2500,
            )
            import_counts["fact_energy_meter_hourly"] = e_count
            print(f"  fact_energy_meter_hourly: {e_count} records inserted.")

            print("Importing 4/4: fact_hourly_production.csv ...")
            prd_count = import_csv_in_batches(
                session,
                FactHourlyProduction,
                EXPECTED_FILES["fact_hourly_production"],
                parse_production_row,
                batch_size=2500,
            )
            import_counts["fact_hourly_production"] = prd_count
            print(f"  fact_hourly_production: {prd_count} records inserted.")

            print("Committing transaction to Neon PostgreSQL...")
            session.commit()
            print("Transaction committed successfully.")

        except Exception as exc:
            session.rollback()
            print(f"Import failed, transaction rolled back: {exc}")
            raise

    # Post-import validation
    print("Running post-import database validations...")
    validation = run_post_import_validation(engine, import_counts)
    return {"import_counts": import_counts, "validation": validation}


def run_post_import_validation(engine, import_counts: Dict[str, int]) -> Dict[str, Any]:
    """Execute post-import verification of row counts, aggregates, and integrity."""
    validation = {}

    with engine.connect() as conn:
        # 1. Exact Row Counts
        counts = {}
        for table, expected in EXPECTED_COUNTS.items():
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            counts[table] = {"actual": cnt, "expected": expected, "match": cnt == expected}
        validation["row_counts"] = counts

        total_records = sum(c["actual"] for c in counts.values())
        validation["total_records"] = total_records

        # 2. Key Uniqueness Checks
        pk_checks = {
            "dim_product": conn.execute(text("SELECT COUNT(DISTINCT product_id) FROM dim_product")).scalar() == 3,
            "dim_production_line": conn.execute(text("SELECT COUNT(DISTINCT line_id) FROM dim_production_line")).scalar() == 4,
            "fact_energy": conn.execute(text("SELECT COUNT(DISTINCT meter_reading_id) FROM fact_energy_meter_hourly")).scalar() == 22080,
            "fact_production": conn.execute(text("SELECT COUNT(DISTINCT event_id) FROM fact_hourly_production")).scalar() == 8832,
        }
        validation["primary_keys_unique"] = all(pk_checks.values())

        # 3. Composite Uniqueness Checks
        uq_checks = {
            "energy_composite_unique": conn.execute(
                text("SELECT COUNT(*) FROM (SELECT DISTINCT timestamp, plant_id, meter_id FROM fact_energy_meter_hourly) s")
            ).scalar() == 22080,
            "production_composite_unique": conn.execute(
                text("SELECT COUNT(*) FROM (SELECT DISTINCT event_ts, plant_id, line_id FROM fact_hourly_production) s")
            ).scalar() == 8832,
        }
        validation["composite_uniqueness"] = uq_checks

        # 4. Foreign Key and Plant Integrity
        fk_checks = {
            "orphaned_products": conn.execute(
                text("SELECT COUNT(*) FROM fact_hourly_production WHERE product_id NOT IN (SELECT product_id FROM dim_product)")
            ).scalar() == 0,
            "orphaned_lines": conn.execute(
                text("SELECT COUNT(*) FROM fact_hourly_production WHERE (line_id, plant_id) NOT IN (SELECT line_id, plant_id FROM dim_production_line)")
            ).scalar() == 0,
        }
        validation["foreign_keys_and_plant_integrity"] = fk_checks

        # 5. Timestamp Coverage
        e_ts = conn.execute(text("SELECT MIN(timestamp), MAX(timestamp), COUNT(DISTINCT timestamp) FROM fact_energy_meter_hourly")).fetchone()
        p_ts = conn.execute(text("SELECT MIN(event_ts), MAX(event_ts), COUNT(DISTINCT event_ts) FROM fact_hourly_production")).fetchone()

        validation["timestamp_coverage"] = {
            "energy_min": str(e_ts[0]),
            "energy_max": str(e_ts[1]),
            "energy_distinct_hours": e_ts[2],
            "production_min": str(p_ts[0]),
            "production_max": str(p_ts[1]),
            "production_distinct_hours": p_ts[2],
            "aligned": str(e_ts[0]) == str(p_ts[0]) and str(e_ts[1]) == str(p_ts[1]) and e_ts[2] == p_ts[2] == 2208,
        }

        # 6. Numeric Aggregates Comparison (Database vs CSV)
        e_agg = conn.execute(
            text("""
                SELECT 
                    SUM(consumption_kwh),
                    SUM(demand_kw),
                    SUM(cost_inr),
                    SUM(co2e_kg)
                FROM fact_energy_meter_hourly
            """)
        ).fetchone()

        p_agg = conn.execute(
            text("""
                SELECT 
                    SUM(target_qty),
                    SUM(actual_qty),
                    SUM(good_qty),
                    SUM(reject_qty),
                    SUM(rework_qty),
                    SUM(downtime_min)
                FROM fact_hourly_production
            """)
        ).fetchone()

        validation["database_aggregates"] = {
            "total_consumption_kwh": str(e_agg[0]),
            "total_demand_kw": str(e_agg[1]),  # DEPRECATED: summing kW across hours is physically derived/meaningless
            "total_demand_kw_deprecated": str(e_agg[1]),
            "demand_kw_note": "Deprecated diagnostic: summing instantaneous demand kW across time intervals does not represent total or peak demand. In the supplied dataset, demand_kw tracks 0.92 x consumption_kwh.",
            "total_cost_inr": str(e_agg[2]),
            "total_co2e_kg": str(e_agg[3]),
            "total_target_qty": int(p_agg[0]),
            "total_actual_qty": int(p_agg[1]),
            "total_good_qty": int(p_agg[2]),
            "total_reject_qty": int(p_agg[3]),
            "total_rework_qty": int(p_agg[4]),
            "total_downtime_min": int(p_agg[5]),
            "qty_balance_verified": int(p_agg[1]) == int(p_agg[2]) + int(p_agg[3]),
        }

        # 7. Plant-Hour 5-Meter Check
        meter_counts_per_hour = conn.execute(
            text("""
                SELECT MIN(meter_cnt), MAX(meter_cnt) FROM (
                    SELECT timestamp, plant_id, COUNT(DISTINCT meter_id) as meter_cnt
                    FROM fact_energy_meter_hourly
                    GROUP BY timestamp, plant_id
                ) sub
            """)
        ).fetchone()
        validation["meters_per_plant_hour"] = {
            "min_meters": meter_counts_per_hour[0],
            "max_meters": meter_counts_per_hour[1],
            "exactly_5_meters": meter_counts_per_hour[0] == meter_counts_per_hour[1] == 5,
        }

    return validation


if __name__ == "__main__":
    result = execute_full_import()
    print("Full import completed successfully.")
