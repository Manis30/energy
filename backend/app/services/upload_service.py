"""Utility upload and batch ingestion service."""

import csv
import io
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.models.source_data import FactUtilityTelemetryHourly
from app.models.upload_history import UploadHistory
from sqlalchemy.orm import Session
from sqlalchemy import select, delete


class DailyReportParser:
    """Parser for utility and telemetry CSV datasets."""

    @staticmethod
    def parse_utility_telemetry_csv(file_bytes: bytes) -> List[Dict[str, Any]]:
        """Parse raw CSV bytes into typed dictionary records for FactUtilityTelemetryHourly."""
        text_stream = io.StringIO(file_bytes.decode("utf-8-sig", errors="replace"))
        reader = csv.DictReader(text_stream)
        records = []
        for row in reader:
            if not row or not any(row.values()):
                continue
            reading_id = row.get("utility_reading_id", "").strip()
            if not reading_id:
                # If reading id is missing, generate one
                reading_id = f"UT-{uuid.uuid4().hex[:9].upper()}"

            ts_str = row.get("timestamp", "").strip()
            try:
                ts = datetime.fromisoformat(ts_str) if ts_str else datetime.utcnow()
            except ValueError:
                ts = datetime.utcnow()

            flow_val = row.get("flow_rate", "").strip()
            pres_val = row.get("pressure_bar", "").strip()
            temp_val = row.get("temperature_c", "").strip()

            records.append({
                "utility_reading_id": reading_id,
                "timestamp": ts,
                "plant_id": row.get("plant_id", "IN-TN-01").strip(),
                "utility_type": row.get("utility_type", "COMPRESSED_AIR").strip().upper(),
                "zone": row.get("zone", "MAIN_UTILITY_BAY").strip(),
                "flow_rate": Decimal(flow_val) if flow_val else None,
                "pressure_bar": Decimal(pres_val) if pres_val else None,
                "temperature_c": Decimal(temp_val) if temp_val else None,
                "consumption_unit": row.get("consumption_unit", "kWh").strip(),
                "equipment_id": row.get("equipment_id", "UTL-01").strip(),
                "operating_status": row.get("operating_status", "NORMAL").strip().upper(),
                "alarm_code": row.get("alarm_code", "NONE").strip(),
                "upload_id": row.get("upload_id") or None,
                "source_revision_id": row.get("source_revision_id") or f"REV_{reading_id}_V1",
                "is_corrected": False,
                "created_at": datetime.utcnow(),
            })
        return records


def ingest_utility_telemetry_file(
    session: Session,
    filename: str,
    file_bytes: bytes,
    plant_id: Optional[str] = "IN-TN-01",
    upload_id: Optional[str] = None,
    mode: str = "INCREMENTAL",
) -> Dict[str, Any]:
    """Ingest utility telemetry CSV transactionally into PostgreSQL."""
    parsed_rows = DailyReportParser.parse_utility_telemetry_csv(file_bytes)
    if not parsed_rows:
        raise ValueError("Uploaded utility CSV contains no valid data rows.")

    target_date = parsed_rows[0]["timestamp"].date()
    gen_upload_id = upload_id or f"UPL-UTIL-{target_date.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    if mode.upper() == "OVERWRITE_CORRECTION":
        reading_ids = [r["utility_reading_id"] for r in parsed_rows]
        session.execute(
            delete(FactUtilityTelemetryHourly).where(
                FactUtilityTelemetryHourly.utility_reading_id.in_(reading_ids)
            )
        )

    ingested_count = 0
    first_rev_id = None
    first_reading_id = parsed_rows[0]["utility_reading_id"]

    for row_dict in parsed_rows:
        row_dict["upload_id"] = gen_upload_id
        if plant_id:
            row_dict["plant_id"] = plant_id
        if not first_rev_id:
            first_rev_id = row_dict["source_revision_id"]

        # Check existing if incremental
        existing = session.execute(
            select(FactUtilityTelemetryHourly).where(
                FactUtilityTelemetryHourly.utility_reading_id == row_dict["utility_reading_id"]
            )
        ).scalar_one_or_none()

        if existing:
            if mode.upper() == "OVERWRITE_CORRECTION":
                for k, v in row_dict.items():
                    setattr(existing, k, v)
                ingested_count += 1
        else:
            obj = FactUtilityTelemetryHourly(**row_dict)
            session.add(obj)
            ingested_count += 1

    # Record in UploadHistory audit log
    history = UploadHistory(
        upload_id=gen_upload_id,
        uploaded_at=datetime.utcnow(),
        report_type="UTILITY",
        filename=filename,
        file_format="CSV",
        reporting_date=target_date,
        file_size_bytes=len(file_bytes),
        total_rows=len(parsed_rows),
        valid_rows=ingested_count,
        rejected_rows=0,
        duplicate_rows=len(parsed_rows) - ingested_count,
        status="COMPLETED",
        mode=mode.upper(),
        audit_details=f"Utility intake via /api/daily-reports/upload. First reading: {first_reading_id}, source revision: {first_rev_id}.",
    )
    session.add(history)
    session.commit()

    return {
        "status": "success",
        "upload_id": gen_upload_id,
        "report_type": "UTILITY",
        "rows_ingested": ingested_count,
        "source_revision_id": first_rev_id,
        "first_reading_id": first_reading_id,
        "reporting_date": target_date.isoformat(),
    }
