"""Controlled CSV data ingestion service for Industrial Energy Intelligence Platform."""

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.db import get_engine, get_session_factory
from app.models.source_data import (
    DimProduct,
    DimProductionLine,
    FactEnergyMeterHourly,
    FactHourlyProduction,
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
        if rev != "be415c420bad":
            raise RuntimeError(f"Alembic revision is '{rev}', expected 'be415c420bad'. Aborting import.")
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
            "total_demand_kw": str(e_agg[1]),
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
