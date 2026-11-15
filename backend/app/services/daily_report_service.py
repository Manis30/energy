"""Service for daily energy and production report parsing, validation, and database ingestion."""

import csv
import io
import json
import math
import os
import re
import uuid
import zipfile
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple

import openpyxl
from sqlalchemy import delete, func, inspect, select, text, tuple_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.source_data import (
    DimProduct,
    DimProductionLine,
    FactEnergyMeterHourly,
    FactHourlyProduction,
)
from app.models.upload_history import UploadHistory
from app.schemas.daily_reports import (
    CompletenessInfo,
    InspectResponse,
    PreviewRow,
    RowValidationError,
    ValidationSummary,
)

# Operational & Security Constraints from Settings
_settings = get_settings()
MAX_FILE_SIZE_BYTES = getattr(_settings, "MAX_UPLOAD_SIZE_MB", 25) * 1024 * 1024
MAX_ROW_COUNT = getattr(_settings, "MAX_UPLOAD_ROWS", 50000)

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# Approved Schema Column Specifications
ENERGY_REQUIRED_COLUMNS = [
    "timestamp",
    "date",
    "plant_id",
    "meter_id",
    "area",
    "energy_source",
    "consumption_kwh",
    "demand_kw",
    "power_factor",
    "tariff_inr_per_kwh",
    "cost_inr",
    "co2e_kg",
    "reading_quality",
]

ENERGY_OPTIONAL_COLUMNS = ["meter_reading_id"]

PRODUCTION_REQUIRED_COLUMNS = [
    "event_ts",
    "event_date",
    "plant_id",
    "line_id",
    "shift_id",
    "product_id",
    "production_order_id",
    "target_qty",
    "actual_qty",
    "good_qty",
    "reject_qty",
    "rework_qty",
    "downtime_min",
    "downtime_reason",
    "operator_team",
    "source_system",
    "data_quality",
]

PRODUCTION_OPTIONAL_COLUMNS = [
    "event_id",
    "year",
    "month",
    "week",
    "day",
    "hour",
]

UNSUPPORTED_UNIT_PATTERNS = {
    r"^consumption_(?!kwh$)": "Unsupported energy consumption unit in '{col}': expected 'consumption_kwh'",
    r"^demand_(?!kw$)": "Unsupported power demand unit in '{col}': expected 'demand_kw'",
    r"^tariff_(?!inr_per_kwh$)": "Unsupported tariff currency/unit in '{col}': expected 'tariff_inr_per_kwh'",
    r"^cost_(?!inr$)": "Unsupported cost currency unit in '{col}': expected 'cost_inr'",
    r"^co2e_(?!kg$)": "Unsupported emissions unit in '{col}': expected 'co2e_kg'",
    r"^downtime_(?!min$|reason$)": "Unsupported downtime duration unit in '{col}': expected 'downtime_min'",
}

# Registered Master Submeter to Area Mappings
METER_AREA_MAPPING = {
    "MTR-SMT": "SMT",
    "MTR-FAL": "FAL",
    "MTR-HVAC": "HVAC",
    "MTR-COMPRESSOR": "COMPRESSOR",
    "MTR-CHILLER": "CHILLER",
}
VALID_METERS = frozenset(METER_AREA_MAPPING)
VALID_ENERGY_SOURCES = frozenset({"ELECTRICITY"})

NON_FINITE_STRINGS = {"nan", "infinity", "-infinity", "inf", "-inf", "null", "none"}



def check_header_schema(
    headers: List[str], report_type: str
) -> Tuple[List[str], List[str], List[str]]:
    """
    Validate headers against approved source schema.
    Returns (missing_required, unknown_columns, unsupported_unit_messages).
    """
    header_set = set(headers)
    missing_required = []
    unknown_cols = []
    unsupported_units = []

    approved_required = ENERGY_REQUIRED_COLUMNS if report_type == "ENERGY" else PRODUCTION_REQUIRED_COLUMNS
    approved_optional = ENERGY_OPTIONAL_COLUMNS if report_type == "ENERGY" else PRODUCTION_OPTIONAL_COLUMNS
    approved_all = set(approved_required + approved_optional)

    for req in approved_required:
        if req not in header_set:
            missing_required.append(req)

    for col in headers:
        if col not in approved_all:
            # Check if this matches a unit variant
            unit_flagged = False
            for pat, msg_template in UNSUPPORTED_UNIT_PATTERNS.items():
                if re.search(pat, col):
                    unsupported_units.append(msg_template.format(col=col))
                    unit_flagged = True
                    break
            if not unit_flagged:
                unknown_cols.append(col)

    return missing_required, unknown_cols, unsupported_units



def normalize_col_name(col: str) -> str:
    """Normalize column header: strip BOM, lowercase, strip spaces and underscores."""
    if not col:
        return ""
    cleaned = str(col).strip().lstrip("\ufeff").lower()
    # Normalize common variations
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned


def detect_file_format(filename: str, file_bytes: bytes) -> str:
    """Validate file extension and file signature/magic bytes."""
    lower_name = filename.lower()
    ext = None
    for s_ext in SUPPORTED_EXTENSIONS:
        if lower_name.endswith(s_ext):
            ext = s_ext
            break

    if not ext:
        raise ValueError(
            f"Unsupported file format for '{filename}'. Allowed formats: .csv, .xlsx, .xls"
        )

    # Magic byte verification
    if ext == ".xlsx":
        if not file_bytes.startswith(b"PK\x03\x04"):
            raise ValueError("Invalid XLSX file: missing standard ZIP/OpenXML signature.")
    elif ext == ".xls":
        if not file_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise ValueError("Invalid XLS file: missing standard OLE2 compound document signature.")
    elif ext == ".csv":
        # Check that CSV is not binary executable
        if file_bytes.startswith(b"MZ") or file_bytes.startswith(b"\x7fELF"):
            raise ValueError("Security violation: Binary executable detected instead of CSV text.")

    return ext.lstrip(".").upper()


def inspect_file(filename: str, file_bytes: bytes) -> InspectResponse:
    """Inspect file content, enumerate worksheets if Excel, and detect report types."""
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
        )

    file_format = detect_file_format(filename, file_bytes)
    sheet_names: List[str] = []
    estimated_rows = 0
    detected_report_type: Optional[str] = None

    if file_format == "CSV":
        sheet_names = ["Sheet1"]
        # Fast row count estimate
        try:
            text_sample = file_bytes.decode("utf-8-sig", errors="replace")
            lines = [line for line in text_sample.splitlines() if line.strip()]
            estimated_rows = max(0, len(lines) - 1)
            if lines:
                header = [normalize_col_name(h) for h in csv.reader([lines[0]]).__next__()]
                detected_report_type = classify_columns(header)
        except Exception:
            estimated_rows = 0
    elif file_format == "XLSX":
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
            sheet_names = wb.sheetnames
            # Check first sheet
            ws = wb[sheet_names[0]]
            rows_iter = ws.iter_rows(values_only=True)
            header_row = next(rows_iter, None)
            if header_row:
                header = [normalize_col_name(str(c)) for c in header_row if c is not None]
                detected_report_type = classify_columns(header)
            wb.close()
        except Exception as e:
            raise ValueError(f"Failed to parse XLSX workbook: {str(e)}")
    elif file_format == "XLS":
        try:
            import xlrd
            wb = xlrd.open_workbook(file_contents=file_bytes, on_demand=True)
            sheet_names = wb.sheet_names()
            if sheet_names:
                ws = wb.sheet_by_name(sheet_names[0])
                if ws.nrows > 0:
                    header = [normalize_col_name(str(ws.cell_value(0, c))) for c in range(ws.ncols)]
                    detected_report_type = classify_columns(header)
                    estimated_rows = ws.nrows - 1
            wb.release_resources()
        except Exception as e:
            raise ValueError(f"Failed to parse XLS workbook: {str(e)}")

    return InspectResponse(
        filename=filename,
        file_format=file_format,
        file_size_bytes=len(file_bytes),
        sheet_names=sheet_names,
        is_multi_sheet=len(sheet_names) > 1,
        detected_report_type=detected_report_type,
        estimated_rows=estimated_rows,
    )


def classify_columns(columns: List[str]) -> str:
    """Classify column set into ENERGY, PRODUCTION, or UNKNOWN."""
    col_set = set(columns)
    has_energy = "consumption_kwh" in col_set or "meter_id" in col_set or "power_factor" in col_set
    has_prod = "target_qty" in col_set or "actual_qty" in col_set or "line_id" in col_set

    if has_energy and has_prod:
        return "ENERGY_AND_PRODUCTION"
    if has_energy:
        return "ENERGY"
    if has_prod:
        return "PRODUCTION"
    return "UNKNOWN"


NUMERIC_COLUMNS = frozenset({
    # Energy schema numeric columns
    "consumption_kwh",
    "demand_kw",
    "power_factor",
    "tariff_inr_per_kwh",
    "cost_inr",
    "co2e_kg",
    # Production schema numeric columns
    "target_qty",
    "actual_qty",
    "good_qty",
    "reject_qty",
    "rework_qty",
    "downtime_min",
    "year",
    "month",
    "week",
    "day",
    "hour",
})


def is_numeric_column(col_name: str) -> bool:
    """Determine if a column is a numeric measurement or count field."""
    norm = normalize_col_name(col_name)
    if norm in NUMERIC_COLUMNS:
        return True
    if any(norm.startswith(p) for p in ("consumption_", "demand_", "tariff_", "cost_", "co2e_")):
        return True
    if any(norm.endswith(s) for s in ("_qty", "_min", "_kwh", "_kw", "_inr", "_kg")):
        return True
    return False


def sanitize_cell_value(val: Any, col_name: str) -> Any:
    """
    Column-aware cell sanitization protecting against formula injection while
    strictly preserving negative and positive numeric values for validation.

    Rules:
    1. Numeric objects (int, float, Decimal) are preserved untouched.
    2. In numeric columns:
       - Legitimate numbers with optional sign (e.g., -50, +50, 50, -0.92) are preserved
         for subsequent Decimal/int and range validation.
       - Never strip leading minus '-' or plus '+' signs.
       - Dangerous formula prefixes ('=', '@') are safely neutralized by prepending a single quote
         so they cannot execute as formulas and will fail numeric parsing cleanly.
    3. In text columns:
       - Ordinary text is preserved unchanged (including legitimate '+' or '-' characters).
       - Dangerous formula-like text beginning with '=' or '@' is safely neutralized by
         prepending a single quote "'".
    """
    if val is None:
        return None

    # Already numeric type from Excel parser (int, float, Decimal)
    if isinstance(val, (int, float, Decimal)) and not isinstance(val, bool):
        return val

    # Non-string types (datetime, date, bool) are preserved
    if not isinstance(val, str):
        return val

    s = val.strip()
    if not s:
        return ""

    if is_numeric_column(col_name):
        # Numeric column:
        # Check if it begins with dangerous formula prefix '=' or '@'
        if s.startswith(("=", "@")):
            return f"'{s}"
        # Legitimate numeric strings (including -50, +50, 50.5, etc.) are preserved exactly
        return s
    else:
        # Text / Non-numeric column:
        # Ordinary text preserved unchanged; never strip '+' or '-'
        if s.startswith(("=", "@")):
            # Dangerous formula-like text: safely neutralize with leading single quote
            return f"'{s}"
        return s


def check_cell_formula_injection(val: Any) -> bool:
    """Check if a cell value contains a formula injection attempt starting with '=' or '@'."""
    if isinstance(val, str):
        s = val.strip()
        if s.startswith(("=", "@")) or s.startswith(("'=", "'@")):
            return True
    return False


def parse_raw_sheet_rows(
    file_bytes: bytes, file_format: str, sheet_name: Optional[str] = None
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Parse the target worksheet or CSV into header names and a list of row dictionaries.
    Protects against formula execution, spreadsheet macros, and malformed files.
    """
    headers: List[str] = []
    rows: List[Dict[str, Any]] = []

    if file_format == "CSV":
        # Check for binary NUL bytes
        if b"\x00" in file_bytes:
            raise ValueError("Malformed CSV: Binary NUL byte detected in file.")

        try:
            content = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                content = file_bytes.decode("latin-1")
            except Exception as e:
                raise ValueError(f"Unable to decode CSV text: {str(e)}")

        reader = csv.reader(content.splitlines())
        raw_header = None
        for r in reader:
            if not r or all(c.strip() == "" for c in r):
                continue
            if raw_header is None:
                raw_header = [normalize_col_name(c) for c in r]
                headers = raw_header
            else:
                row_dict = {}
                for idx, col_name in enumerate(headers):
                    val = r[idx].strip() if idx < len(r) else ""
                    row_dict[col_name] = sanitize_cell_value(val, col_name)
                rows.append(row_dict)

    elif file_format == "XLSX":
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        except zipfile.BadZipFile:
            raise ValueError("Invalid XLSX file: Corrupted or incomplete ZIP container.")
        except Exception as e:
            raise ValueError(f"Failed to open XLSX workbook: {str(e)}")

        target_sheet = sheet_name if (sheet_name and sheet_name in wb.sheetnames) else wb.sheetnames[0]
        ws = wb[target_sheet]

        raw_header = None
        consecutive_empty = 0
        for row in ws.iter_rows(values_only=True):
            if not row or all(c is None or str(c).strip() == "" for c in row):
                if raw_header is not None:
                    consecutive_empty += 1
                    if consecutive_empty >= 30:
                        break
                continue
            consecutive_empty = 0

            if raw_header is None:
                raw_header = [normalize_col_name(str(c)) for c in row if c is not None]
                headers = raw_header
            else:
                row_dict = {}
                for idx, col_name in enumerate(headers):
                    val = row[idx] if idx < len(row) else None
                    row_dict[col_name] = sanitize_cell_value(val, col_name)
                rows.append(row_dict)
        wb.close()

    elif file_format == "XLS":
        try:
            import xlrd
            wb = xlrd.open_workbook(file_contents=file_bytes, on_demand=True)
        except Exception as e:
            raise ValueError(f"Failed to open XLS spreadsheet: {str(e)}")

        target_sheet = sheet_name if (sheet_name and sheet_name in wb.sheet_names()) else wb.sheet_names()[0]
        ws = wb.sheet_by_name(target_sheet)

        if ws.nrows > 0:
            headers = [normalize_col_name(str(ws.cell_value(0, c))) for c in range(ws.ncols)]
            for r_idx in range(1, ws.nrows):
                row_dict = {}
                is_empty = True
                for c_idx, col_name in enumerate(headers):
                    cell = ws.cell(r_idx, c_idx)
                    val = cell.value
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        # Convert date tuple to datetime
                        date_tuple = xlrd.xldate_as_tuple(val, wb.datemode)
                        val = datetime(*date_tuple)
                    else:
                        val = sanitize_cell_value(val, col_name)
                    if val is not None and str(val).strip() != "":
                        is_empty = False
                    row_dict[col_name] = val
                if not is_empty:
                    rows.append(row_dict)
        wb.release_resources()

    if len(rows) > MAX_ROW_COUNT:
        raise ValueError(
            f"File row count ({len(rows)}) exceeds maximum limit of {MAX_ROW_COUNT} records."
        )

    return headers, rows


def parse_cell_datetime(val: Any) -> Optional[datetime]:
    """Parse various datetime representations into Python datetime."""
    if val is None or str(val).strip() == "":
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, time.min)

    s = str(val).strip()
    if s.lower() in NON_FINITE_STRINGS:
        return None

    # Try ISO format
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass

    # Try common formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def parse_cell_date(val: Any) -> Optional[date]:
    """Parse various date representations into Python date."""
    if val is None or str(val).strip() == "":
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val

    s = str(val).strip().split("T")[0].split(" ")[0]
    if s.lower() in NON_FINITE_STRINGS:
        return None

    try:
        return date.fromisoformat(s)
    except Exception:
        pass

    formats = ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def parse_cell_decimal(val: Any) -> Optional[Decimal]:
    """Parse numeric cell safely into finite Decimal, rejecting NaN, Inf, and non-numbers."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val if val.is_finite() else None
    if isinstance(val, int) and not isinstance(val, bool):
        return Decimal(val)
    if isinstance(val, float):
        if not math.isfinite(val):
            return None
        return Decimal(str(val))
    s = str(val).strip()
    if not s or s.lower() in NON_FINITE_STRINGS:
        return None
    try:
        cleaned = s.replace(",", "")
        d = Decimal(cleaned)
        if not d.is_finite():
            return None
        return d
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_cell_int(val: Any) -> Optional[int]:
    """Parse numeric cell safely into Integer, rejecting non-finite, fractions, or overflow."""
    if val is None:
        return None
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        if not math.isfinite(val) or val != math.floor(val):
            return None
        return int(val)
    if isinstance(val, Decimal):
        if not val.is_finite() or val != val.to_integral_value():
            return None
        return int(val)
    s = str(val).strip()
    if not s or s.lower() in NON_FINITE_STRINGS:
        return None
    try:
        cleaned = s.replace(",", "")
        f = float(cleaned)
        if not math.isfinite(f):
            return None
        if f != math.floor(f) and f != math.ceil(f):
            return None
        return int(f)
    except (ValueError, TypeError, OverflowError):
        return None



class MasterDataCache:
    """Cached master dimension references for fast foreign key validation."""

    def __init__(self, session: Session):
        self.products: Set[str] = set()
        self.lines_by_plant: Set[Tuple[str, str]] = set()
        self.plants: Set[str] = set()
        self.lines_for_plant: Dict[str, List[str]] = {}

        # Load dim_product
        prods = session.execute(select(DimProduct.product_id)).scalars().all()
        self.products = set(prods)

        # Load dim_production_line
        lines = session.execute(
            select(DimProductionLine.line_id, DimProductionLine.plant_id)
        ).all()
        for l_id, p_id in lines:
            self.lines_by_plant.add((l_id, p_id))
            self.plants.add(p_id)
            self.lines_for_plant.setdefault(p_id, []).append(l_id)


def detect_reporting_dates_from_rows(
    rows: List[Dict[str, Any]], report_type: str
) -> List[date]:
    """Detect all unique dates present across data rows."""
    found_dates = set()
    date_col = "date" if report_type == "ENERGY" else "event_date"
    ts_col = "timestamp" if report_type == "ENERGY" else "event_ts"

    for r in rows:
        d_val = r.get(date_col)
        parsed_d = parse_cell_date(d_val)
        if not parsed_d:
            ts_val = r.get(ts_col)
            parsed_ts = parse_cell_datetime(ts_val)
            if parsed_ts:
                parsed_d = parsed_ts.date()

        if parsed_d:
            found_dates.add(parsed_d)

    return sorted(list(found_dates))


def assess_report_completeness(
    report_type: str,
    valid_records: List[Dict[str, Any]],
    master_cache: MasterDataCache,
) -> CompletenessInfo:
    """
    Assess whether the validated records provide complete operational coverage.
    Checks:
    1. 24 hourly intervals (hours 0..23). Zero-consumption or zero-production records
       still count as reported intervals (distinguishing missing intervals from reported zeros).
    2. All expected meters per plant for energy reports (5 submeters).
    3. All expected production lines per plant for production reports from dim_production_line.
    """
    if not valid_records:
        return CompletenessInfo(
            is_complete=False,
            coverage_status="PARTIAL",
            hours_reported=0,
            missing_hours=list(range(24)),
            found_entities=[],
            missing_entities=[],
            plant_scopes={},
            limitations=["No valid records to evaluate coverage."],
        )

    plant_scopes: Dict[str, Any] = {}
    limitations: List[str] = []

    if report_type == "ENERGY":
        expected_meters = sorted(list(VALID_METERS))
        # Group records by plant
        by_plant: Dict[str, List[Dict[str, Any]]] = {}
        for r in valid_records:
            pid = r.get("plant_id", "UNKNOWN")
            by_plant.setdefault(pid, []).append(r)

        all_found_hours: Set[int] = set()
        all_found_meters: Set[str] = set()

        for pid, precs in by_plant.items():
            hours = {r["timestamp"].hour for r in precs if r.get("timestamp")}
            all_found_hours.update(hours)
            meters = {r["meter_id"] for r in precs if r.get("meter_id")}
            all_found_meters.update(meters)

            missing_hrs = sorted(list(set(range(24)) - hours))
            missing_mtrs = sorted(list(set(expected_meters) - meters))
            p_complete = len(missing_hrs) == 0 and len(missing_mtrs) == 0

            plant_scopes[pid] = {
                "hours_reported": len(hours),
                "missing_hours": missing_hrs,
                "meters_reported": len(meters),
                "found_meters": sorted(list(meters)),
                "expected_meters": expected_meters,
                "missing_meters": missing_mtrs,
                "is_complete": p_complete,
            }

            if missing_hrs:
                limitations.append(
                    f"Plant '{pid}': {len(hours)}/24 hourly intervals reported. Missing hours: {missing_hrs}. "
                    f"Daily total energy will reflect partial operating hours and underestimate 24-hour consumption."
                )
            if missing_mtrs:
                limitations.append(
                    f"Plant '{pid}': {len(meters)}/5 submeters reported. Missing meters: {', '.join(missing_mtrs)}. "
                    f"Utility segregation and Factory SEC will be unavailable or incomplete."
                )

        overall_missing_hours = sorted(list(set(range(24)) - all_found_hours))
        overall_missing_meters = sorted(list(set(expected_meters) - all_found_meters))
        is_complete = all(ps["is_complete"] for ps in plant_scopes.values())

        return CompletenessInfo(
            is_complete=is_complete,
            coverage_status="COMPLETE" if is_complete else "PARTIAL",
            hours_reported=len(all_found_hours),
            missing_hours=overall_missing_hours,
            found_entities=sorted(list(all_found_meters)),
            missing_entities=overall_missing_meters,
            plant_scopes=plant_scopes,
            limitations=limitations,
        )

    elif report_type == "PRODUCTION":
        by_plant: Dict[str, List[Dict[str, Any]]] = {}
        for r in valid_records:
            pid = r.get("plant_id", "UNKNOWN")
            by_plant.setdefault(pid, []).append(r)

        all_found_hours = set()
        all_found_lines = set()
        all_expected_lines = set()

        for pid, precs in by_plant.items():
            hours = {r["event_ts"].hour for r in precs if r.get("event_ts")}
            all_found_hours.update(hours)
            lines = {r["line_id"] for r in precs if r.get("line_id")}
            all_found_lines.update(lines)

            expected_lines_plant = sorted(master_cache.lines_for_plant.get(pid, []))
            all_expected_lines.update(expected_lines_plant)

            missing_hrs = sorted(list(set(range(24)) - hours))
            missing_lns = sorted(list(set(expected_lines_plant) - lines)) if expected_lines_plant else []
            p_complete = len(missing_hrs) == 0 and len(missing_lns) == 0

            plant_scopes[pid] = {
                "hours_reported": len(hours),
                "missing_hours": missing_hrs,
                "lines_reported": len(lines),
                "found_lines": sorted(list(lines)),
                "expected_lines": expected_lines_plant,
                "missing_lines": missing_lns,
                "is_complete": p_complete,
            }

            if missing_hrs:
                limitations.append(
                    f"Plant '{pid}': {len(hours)}/24 hourly intervals reported. Missing hours: {missing_hrs}. "
                    f"Reported production output and downtime reflect partial operating intervals."
                )
            if missing_lns:
                limitations.append(
                    f"Plant '{pid}': {len(lines)}/{len(expected_lines_plant)} lines reported. Missing lines: {', '.join(missing_lns)}. "
                    f"Production output does not represent full facility output."
                )

        overall_missing_hours = sorted(list(set(range(24)) - all_found_hours))
        overall_missing_lines = sorted(list(all_expected_lines - all_found_lines))
        is_complete = all(ps["is_complete"] for ps in plant_scopes.values())

        return CompletenessInfo(
            is_complete=is_complete,
            coverage_status="COMPLETE" if is_complete else "PARTIAL",
            hours_reported=len(all_found_hours),
            missing_hours=overall_missing_hours,
            found_entities=sorted(list(all_found_lines)),
            missing_entities=overall_missing_lines,
            plant_scopes=plant_scopes,
            limitations=limitations,
        )

    return CompletenessInfo(
        is_complete=True,
        coverage_status="COMPLETE",
        hours_reported=24,
        missing_hours=[],
        found_entities=[],
        missing_entities=[],
        plant_scopes={},
        limitations=[],
    )


def get_daily_report_coverage(
    session: Session,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """Report persisted daily energy and production coverage without assuming schedules."""
    energy_daily_rows = session.execute(
        select(
            FactEnergyMeterHourly.plant_id,
            FactEnergyMeterHourly.date,
            func.count(FactEnergyMeterHourly.meter_reading_id),
            func.count(func.distinct(FactEnergyMeterHourly.timestamp)),
            func.min(FactEnergyMeterHourly.timestamp),
            func.max(FactEnergyMeterHourly.timestamp),
        )
        .where(
            FactEnergyMeterHourly.date >= start_date,
            FactEnergyMeterHourly.date <= end_date,
        )
        .group_by(FactEnergyMeterHourly.plant_id, FactEnergyMeterHourly.date)
    ).all()
    energy_entities_rows = session.execute(
        select(
            FactEnergyMeterHourly.plant_id,
            FactEnergyMeterHourly.date,
            FactEnergyMeterHourly.meter_id,
        )
        .where(
            FactEnergyMeterHourly.date >= start_date,
            FactEnergyMeterHourly.date <= end_date,
        )
        .group_by(
            FactEnergyMeterHourly.plant_id,
            FactEnergyMeterHourly.date,
            FactEnergyMeterHourly.meter_id,
        )
    ).all()

    production_daily_rows = session.execute(
        select(
            FactHourlyProduction.plant_id,
            FactHourlyProduction.event_date,
            func.count(FactHourlyProduction.event_id),
            func.count(func.distinct(FactHourlyProduction.event_ts)),
            func.min(FactHourlyProduction.event_ts),
            func.max(FactHourlyProduction.event_ts),
        )
        .where(
            FactHourlyProduction.event_date >= start_date,
            FactHourlyProduction.event_date <= end_date,
        )
        .group_by(FactHourlyProduction.plant_id, FactHourlyProduction.event_date)
    ).all()
    production_entities_rows = session.execute(
        select(
            FactHourlyProduction.plant_id,
            FactHourlyProduction.event_date,
            FactHourlyProduction.line_id,
        )
        .where(
            FactHourlyProduction.event_date >= start_date,
            FactHourlyProduction.event_date <= end_date,
        )
        .group_by(
            FactHourlyProduction.plant_id,
            FactHourlyProduction.event_date,
            FactHourlyProduction.line_id,
        )
    ).all()

    energy_by_day = {
        (plant_id, reporting_date): {
            "record_count": int(record_count),
            "observed_hours": int(observed_hours),
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
        }
        for plant_id, reporting_date, record_count, observed_hours, first_timestamp, last_timestamp in energy_daily_rows
    }
    energy_entities_by_day: Dict[Tuple[str, date], Set[str]] = {}
    for plant_id, reporting_date, meter_id in energy_entities_rows:
        energy_entities_by_day.setdefault((plant_id, reporting_date), set()).add(meter_id)

    production_by_day = {
        (plant_id, reporting_date): {
            "record_count": int(record_count),
            "observed_hours": int(observed_hours),
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
        }
        for plant_id, reporting_date, record_count, observed_hours, first_timestamp, last_timestamp in production_daily_rows
    }
    production_entities_by_day: Dict[Tuple[str, date], Set[str]] = {}
    for plant_id, reporting_date, line_id in production_entities_rows:
        production_entities_by_day.setdefault((plant_id, reporting_date), set()).add(line_id)

    observed_plants = {
        plant_id
        for plant_id, _ in set(energy_by_day) | set(production_by_day)
    }
    lines_by_plant: Dict[str, Set[str]] = {}
    registered_line_rows = session.execute(
        select(DimProductionLine.plant_id, DimProductionLine.line_id)
    ).all()
    for plant_id, line_id in registered_line_rows:
        lines_by_plant.setdefault(plant_id, set()).add(line_id)
    coverage_plant_ids = observed_plants | set(lines_by_plant)

    reporting_dates = [
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    ]
    energy_coverage = []
    production_coverage = []
    energy_limitations = [
        "The configured energy meter catalog is global and has no plant-to-meter mapping; "
        "plant-specific expected meters and unobserved registered meters cannot be determined.",
        "No approved operating calendar or expected-hour schedule is available; missing hours are not inferred.",
        "Entity observation is summarized across the date and does not imply that every entity should report each hour.",
    ]
    production_limitations = [
        "Production lines are compared with the current plant-to-line registry; the registry has no effective dates "
        "to establish which lines were active historically.",
        "No approved operating calendar or expected-hour schedule is available; missing hours are not inferred.",
        "Entity observation is summarized across the date and does not imply that every line should report each hour.",
    ]

    for plant_id in sorted(coverage_plant_ids):
        registered_lines = lines_by_plant.get(plant_id)
        for reporting_date in reporting_dates:
            key = (plant_id, reporting_date)

            energy_day = energy_by_day.get(key)
            observed_meters = sorted(energy_entities_by_day.get(key, set()))
            energy_record_count = energy_day["record_count"] if energy_day else 0
            energy_coverage.append({
                "plant_id": plant_id,
                "reporting_date": reporting_date,
                "record_status": "OBSERVED" if energy_record_count else "NO_RECORDS",
                "coverage_status": "UNDETERMINED" if energy_record_count else "NO_RECORDS",
                "record_count": energy_record_count,
                "observed_hours": energy_day["observed_hours"] if energy_day else 0,
                "expected_entity_count": None,
                "expected_entities": None,
                "observed_entity_count": len(observed_meters),
                "observed_entities": observed_meters,
                "unobserved_registered_entities": None,
                "unregistered_observed_entities": sorted(set(observed_meters) - VALID_METERS),
                "all_registered_entities_observed_for_date": None,
                "missing_hours": None,
                "first_observed_timestamp": energy_day["first_timestamp"] if energy_day else None,
                "last_observed_timestamp": energy_day["last_timestamp"] if energy_day else None,
                "limitations": energy_limitations,
            })

            production_day = production_by_day.get(key)
            observed_lines = sorted(production_entities_by_day.get(key, set()))
            production_record_count = production_day["record_count"] if production_day else 0
            expected_lines = sorted(registered_lines) if registered_lines else None
            unobserved_lines = (
                sorted(set(expected_lines) - set(observed_lines))
                if expected_lines is not None
                else None
            )
            all_registered_lines_observed = (
                set(expected_lines).issubset(observed_lines)
                if expected_lines is not None
                else None
            )
            if not production_record_count:
                production_status = "NO_RECORDS"
            elif expected_lines is None:
                production_status = "UNDETERMINED"
            elif all_registered_lines_observed:
                production_status = "ALL_REGISTERED_OBSERVED"
            else:
                production_status = "PARTIAL_OBSERVED"

            production_coverage.append({
                "plant_id": plant_id,
                "reporting_date": reporting_date,
                "record_status": "OBSERVED" if production_record_count else "NO_RECORDS",
                "coverage_status": production_status,
                "record_count": production_record_count,
                "observed_hours": production_day["observed_hours"] if production_day else 0,
                "expected_entity_count": len(expected_lines) if expected_lines is not None else None,
                "expected_entities": expected_lines,
                "observed_entity_count": len(observed_lines),
                "observed_entities": observed_lines,
                "unobserved_registered_entities": unobserved_lines,
                "unregistered_observed_entities": (
                    sorted(set(observed_lines) - set(expected_lines))
                    if expected_lines is not None
                    else observed_lines
                ),
                "all_registered_entities_observed_for_date": all_registered_lines_observed,
                "missing_hours": None,
                "first_observed_timestamp": production_day["first_timestamp"] if production_day else None,
                "last_observed_timestamp": production_day["last_timestamp"] if production_day else None,
                "limitations": production_limitations,
            })

    return {
        "start_date": start_date,
        "end_date": end_date,
        "registered_energy_meters": sorted(VALID_METERS),
        "energy_coverage": energy_coverage,
        "production_coverage": production_coverage,
        "limitations": [
            "Plants are discovered from requested-range energy or production records and the current production-line registry. "
            "A plant with no records and no registered production line cannot be enumerated.",
            "Missing hours are null because no approved operating calendar or expected-hour schedule is available.",
            "Registered entity coverage is date-level observation only; no per-hour reporting requirement is assumed.",
        ],
    }


def validate_energy_rows(
    rows: List[Dict[str, Any]],
    confirmed_date: Optional[date],
    master_cache: MasterDataCache,
    existing_db_keys: Set[Tuple[datetime, str, str]],
    mode: str = "INCREMENTAL",
) -> Tuple[List[Dict[str, Any]], List[RowValidationError], List[PreviewRow], ValidationSummary]:
    """Validate all rows against fact_energy_meter_hourly schema and domain rules."""
    valid_records: List[Dict[str, Any]] = []
    errors: List[RowValidationError] = []
    preview: List[PreviewRow] = []

    seen_file_keys: Set[Tuple[datetime, str, str]] = set()
    duplicate_count = 0
    rejected_count = 0

    plants_found: Set[str] = set()
    meters_found: Set[str] = set()

    for idx, row in enumerate(rows, start=1):
        row_errors: List[str] = []
        is_duplicate = False

        # Security: Formula injection detection
        for col_k, col_v in row.items():
            if check_cell_formula_injection(col_v):
                row_errors.append(f"Dangerous formula-like expression detected in '{col_k}'")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column=col_k,
                        error_type="SECURITY_VIOLATION",
                        message=f"Formula injection detected: cell in '{col_k}' contains dangerous formula prefix '=' or '@'",
                        value=str(col_v),
                    )
                )

        # 1. Required fields presence check
        for req in ENERGY_REQUIRED_COLUMNS:
            val = row.get(req)
            if val is None or str(val).strip() == "":
                row_errors.append(f"Missing required field: '{req}'")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column=req,
                        error_type="MISSING_FIELD",
                        message=f"Missing required value for '{req}'",
                    )
                )

        # 2. Timestamp & Date validation
        ts = parse_cell_datetime(row.get("timestamp"))
        if not ts:
            row_errors.append("Invalid or unparseable timestamp")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="timestamp",
                    error_type="INVALID_TIMESTAMP",
                    message=f"Cannot parse timestamp: '{row.get('timestamp')}'",
                    value=str(row.get("timestamp")),
                )
            )

        row_date = parse_cell_date(row.get("date"))
        if not row_date and ts:
            row_date = ts.date()

        if row_date and ts and row_date != ts.date():
            row_errors.append(f"Date '{row_date}' does not match timestamp date '{ts.date()}'")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="date",
                    error_type="DATE_MISMATCH",
                    message="Date column does not align with timestamp",
                    value=str(row_date),
                )
            )

        if confirmed_date and row_date and row_date != confirmed_date:
            row_errors.append(f"Row date '{row_date}' does not match confirmed reporting date '{confirmed_date}'")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="date",
                    error_type="REPORTING_DATE_MISMATCH",
                    message=f"Row date '{row_date}' differs from reporting date '{confirmed_date}'",
                    value=str(row_date),
                )
            )

        # 3. Plant ID
        plant_id = str(row.get("plant_id", "")).strip()
        if plant_id:
            plants_found.add(plant_id)
            if master_cache.plants and plant_id not in master_cache.plants:
                row_errors.append(f"Unknown plant reference: '{plant_id}'")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column="plant_id",
                        error_type="INVALID_PLANT",
                        message=f"Plant '{plant_id}' not found in registered plant master",
                        value=plant_id,
                    )
                )

        # 4. Meter ID & Area
        meter_id = str(row.get("meter_id", "")).strip()
        if meter_id:
            meters_found.add(meter_id)
            if meter_id not in VALID_METERS:
                row_errors.append(f"Unapproved meter ID: '{meter_id}'")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column="meter_id",
                        error_type="INVALID_METER",
                        message=f"Meter '{meter_id}' not in approved factory submeters",
                        value=meter_id,
                    )
                )

        area = str(row.get("area", "")).strip().upper()
        if meter_id in METER_AREA_MAPPING:
            expected_area = METER_AREA_MAPPING[meter_id]
            if area != expected_area:
                row_errors.append(f"Area '{area}' does not match expected area '{expected_area}' for meter '{meter_id}'")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column="area",
                        error_type="AREA_MISMATCH",
                        message=f"Submeter '{meter_id}' is registered to area '{expected_area}', but report provided '{area}'",
                        value=area,
                    )
                )

        energy_source = str(row.get("energy_source", "")).strip().upper()
        if energy_source and energy_source not in VALID_ENERGY_SOURCES:
            row_errors.append(f"Unsupported energy source: '{energy_source}'")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="energy_source",
                    error_type="INVALID_ENERGY_SOURCE",
                    message=f"Energy source '{energy_source}' unsupported. Expected 'ELECTRICITY'.",
                    value=energy_source,
                )
            )

        # 5. Numerics & Range Checks
        consumption_kwh = parse_cell_decimal(row.get("consumption_kwh"))
        if consumption_kwh is None or consumption_kwh < Decimal("0"):
            row_errors.append("consumption_kwh must be a non-negative decimal")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="consumption_kwh",
                    error_type="RANGE_VIOLATION",
                    message="consumption_kwh must be non-negative",
                    value=str(row.get("consumption_kwh")),
                )
            )

        demand_kw = parse_cell_decimal(row.get("demand_kw"))
        if demand_kw is None or demand_kw < Decimal("0"):
            row_errors.append("demand_kw must be a non-negative decimal")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="demand_kw",
                    error_type="RANGE_VIOLATION",
                    message="demand_kw must be non-negative",
                    value=str(row.get("demand_kw")),
                )
            )

        power_factor = parse_cell_decimal(row.get("power_factor"))
        if power_factor is None or power_factor < Decimal("0.0") or power_factor > Decimal("1.0"):
            row_errors.append("power_factor must be between 0.0 and 1.0")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="power_factor",
                    error_type="RANGE_VIOLATION",
                    message="power_factor must be in range [0.0, 1.0]",
                    value=str(row.get("power_factor")),
                )
            )

        tariff_inr = parse_cell_decimal(row.get("tariff_inr_per_kwh"))
        if tariff_inr is None or tariff_inr < Decimal("0"):
            row_errors.append("tariff_inr_per_kwh must be non-negative")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="tariff_inr_per_kwh",
                    error_type="RANGE_VIOLATION",
                    message="tariff_inr_per_kwh must be non-negative",
                    value=str(row.get("tariff_inr_per_kwh")),
                )
            )

        cost_inr = parse_cell_decimal(row.get("cost_inr"))
        if cost_inr is None or cost_inr < Decimal("0"):
            row_errors.append("cost_inr must be non-negative")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="cost_inr",
                    error_type="RANGE_VIOLATION",
                    message="cost_inr must be non-negative",
                    value=str(row.get("cost_inr")),
                )
            )

        co2e_kg = parse_cell_decimal(row.get("co2e_kg"))
        if co2e_kg is None or co2e_kg < Decimal("0"):
            row_errors.append("co2e_kg must be non-negative")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="co2e_kg",
                    error_type="RANGE_VIOLATION",
                    message="co2e_kg must be non-negative",
                    value=str(row.get("co2e_kg")),
                )
            )

        reading_quality = str(row.get("reading_quality", "VALID")).strip() or "VALID"

        # 6. Business Key & Duplicate Verification: (timestamp, plant_id, meter_id)
        b_key = None
        if ts and plant_id and meter_id:
            b_key = (ts, plant_id, meter_id)
            if b_key in seen_file_keys:
                is_duplicate = True
                row_errors.append("Duplicate business key in uploaded file")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column="business_key",
                        error_type="DUPLICATE_IN_FILE",
                        message=f"Duplicate entry for plant '{plant_id}', meter '{meter_id}' at timestamp '{ts.isoformat()}'",
                    )
                )
            else:
                seen_file_keys.add(b_key)

            if b_key in existing_db_keys:
                if mode == "OVERWRITE_CORRECTION":
                    duplicate_count += 1
                else:
                    is_duplicate = True
                    row_errors.append("Record already exists in Neon database")
                    errors.append(
                        RowValidationError(
                            row_number=idx,
                            column="business_key",
                            error_type="DUPLICATE_IN_DATABASE",
                            message=f"Existing record in database for plant '{plant_id}', meter '{meter_id}', timestamp '{ts.isoformat()}'",
                        )
                    )

        # Status determination
        if row_errors:
            if is_duplicate and len(row_errors) == 1:
                status = "DUPLICATE"
                duplicate_count += 1
            else:
                status = "REJECTED"
                rejected_count += 1
        else:
            status = "VALID"
            # Format clean record for insertion
            meter_reading_id = str(row.get("meter_reading_id", "")).strip()
            if not meter_reading_id:
                meter_reading_id = f"EN-{uuid.uuid4().hex[:12].upper()}"

            valid_records.append(
                {
                    "meter_reading_id": meter_reading_id,
                    "timestamp": ts,
                    "date": row_date,
                    "plant_id": plant_id,
                    "meter_id": meter_id,
                    "area": area,
                    "energy_source": energy_source,
                    "consumption_kwh": consumption_kwh,
                    "demand_kw": demand_kw,
                    "power_factor": power_factor,
                    "tariff_inr_per_kwh": tariff_inr,
                    "cost_inr": cost_inr,
                    "co2e_kg": co2e_kg,
                    "reading_quality": reading_quality,
                }
            )

        # Preview generation (first 15 rows)
        if len(preview) < 15:
            preview.append(
                PreviewRow(
                    row_number=idx,
                    status=status,
                    data={
                        "timestamp": str(ts) if ts else str(row.get("timestamp")),
                        "date": str(row_date) if row_date else str(row.get("date")),
                        "plant_id": plant_id,
                        "meter_id": meter_id,
                        "area": area,
                        "consumption_kwh": str(consumption_kwh) if consumption_kwh is not None else str(row.get("consumption_kwh")),
                        "demand_kw": str(demand_kw) if demand_kw is not None else str(row.get("demand_kw")),
                        "power_factor": str(power_factor) if power_factor is not None else str(row.get("power_factor")),
                        "cost_inr": str(cost_inr) if cost_inr is not None else str(row.get("cost_inr")),
                    },
                    errors=row_errors,
                )
            )

    total_rows = len(rows)
    valid_rows = len(valid_records)

    completeness = assess_report_completeness("ENERGY", valid_records, master_cache)

    summary = ValidationSummary(
        report_type="ENERGY",
        total_rows=total_rows,
        valid_rows=valid_rows,
        rejected_rows=rejected_count,
        duplicate_rows=duplicate_count,
        detected_date=confirmed_date,
        confirmed_date=confirmed_date,
        plants_found=sorted(list(plants_found)),
        meters_found=sorted(list(meters_found)),
        is_ready_for_ingest=(valid_rows > 0),
        is_complete=completeness.is_complete,
        coverage_status=completeness.coverage_status,
        missing_hours=completeness.missing_hours,
        missing_entities=completeness.missing_entities,
        limitations=completeness.limitations,
        completeness=completeness,
    )

    return valid_records, errors, preview, summary


def validate_production_rows(
    rows: List[Dict[str, Any]],
    confirmed_date: Optional[date],
    master_cache: MasterDataCache,
    existing_db_keys: Set[Tuple[datetime, str, str]],
    mode: str = "INCREMENTAL",
) -> Tuple[List[Dict[str, Any]], List[RowValidationError], List[PreviewRow], ValidationSummary]:
    """Validate all rows against fact_hourly_production schema and constraints."""
    valid_records: List[Dict[str, Any]] = []
    errors: List[RowValidationError] = []
    preview: List[PreviewRow] = []

    seen_file_keys: Set[Tuple[datetime, str, str]] = set()
    duplicate_count = 0
    rejected_count = 0

    plants_found: Set[str] = set()
    lines_found: Set[str] = set()

    for idx, row in enumerate(rows, start=1):
        row_errors: List[str] = []
        is_duplicate = False

        # Security: Formula injection detection
        for col_k, col_v in row.items():
            if check_cell_formula_injection(col_v):
                row_errors.append(f"Dangerous formula-like expression detected in '{col_k}'")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column=col_k,
                        error_type="SECURITY_VIOLATION",
                        message=f"Formula injection detected: cell in '{col_k}' contains dangerous formula prefix '=' or '@'",
                        value=str(col_v),
                    )
                )

        # 1. Required fields presence check
        for req in PRODUCTION_REQUIRED_COLUMNS:
            val = row.get(req)
            if val is None or str(val).strip() == "":
                row_errors.append(f"Missing required field: '{req}'")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column=req,
                        error_type="MISSING_FIELD",
                        message=f"Missing required value for '{req}'",
                    )
                )

        # 2. Timestamp & Date validation
        event_ts = parse_cell_datetime(row.get("event_ts"))
        if not event_ts:
            row_errors.append("Invalid or unparseable event_ts")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="event_ts",
                    error_type="INVALID_TIMESTAMP",
                    message=f"Cannot parse event timestamp: '{row.get('event_ts')}'",
                    value=str(row.get("event_ts")),
                )
            )

        event_date = parse_cell_date(row.get("event_date"))
        if not event_date and event_ts:
            event_date = event_ts.date()

        if event_date and event_ts and event_date != event_ts.date():
            row_errors.append(f"event_date '{event_date}' differs from event_ts date '{event_ts.date()}'")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="event_date",
                    error_type="DATE_MISMATCH",
                    message="event_date does not align with event_ts",
                    value=str(event_date),
                )
            )

        if confirmed_date and event_date and event_date != confirmed_date:
            row_errors.append(f"Row date '{event_date}' does not match confirmed reporting date '{confirmed_date}'")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="event_date",
                    error_type="REPORTING_DATE_MISMATCH",
                    message=f"Row date '{event_date}' differs from reporting date '{confirmed_date}'",
                    value=str(event_date),
                )
            )

        # 3. Derived or provided date components
        raw_hour = parse_cell_int(row.get("hour"))
        if raw_hour is not None and event_ts and raw_hour != event_ts.hour:
            row_errors.append(f"Hour ({raw_hour}) does not match event_ts hour ({event_ts.hour})")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="hour",
                    error_type="HOUR_MISMATCH",
                    message=f"Provided hour ({raw_hour}) contradicts event_ts hour ({event_ts.hour})",
                    value=str(raw_hour),
                )
            )

        hour = raw_hour if raw_hour is not None else (event_ts.hour if event_ts else None)
        if hour is None or hour < 0 or hour > 23:
            row_errors.append(f"Hour must be between 0 and 23, got {hour}")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="hour",
                    error_type="RANGE_VIOLATION",
                    message="Production hour must be in range [0, 23]",
                    value=str(row.get("hour")),
                )
            )

        year = parse_cell_int(row.get("year")) or (event_ts.year if event_ts else None)
        month = parse_cell_int(row.get("month")) or (event_ts.month if event_ts else None)
        week = parse_cell_int(row.get("week")) or (event_ts.isocalendar()[1] if event_ts else None)
        day = parse_cell_int(row.get("day")) or (event_ts.day if event_ts else None)

        # 4. Plant ID & Line ID Foreign Key validation
        plant_id = str(row.get("plant_id", "")).strip()
        line_id = str(row.get("line_id", "")).strip()
        if plant_id:
            plants_found.add(plant_id)
        if line_id:
            lines_found.add(line_id)

        if plant_id and line_id:
            if (line_id, plant_id) not in master_cache.lines_by_plant:
                row_errors.append(f"Foreign key violation: Line '{line_id}' in Plant '{plant_id}' not found in dim_production_line")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column="line_id",
                        error_type="FOREIGN_KEY_VIOLATION",
                        message=f"Line '{line_id}' is not linked to plant '{plant_id}' in dim_production_line master",
                        value=f"{line_id}@{plant_id}",
                    )
                )

        # 5. Product ID Foreign Key validation
        product_id = str(row.get("product_id", "")).strip()
        if product_id:
            if product_id not in master_cache.products:
                row_errors.append(f"Foreign key violation: Product '{product_id}' not found in dim_product master")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column="product_id",
                        error_type="FOREIGN_KEY_VIOLATION",
                        message=f"Product '{product_id}' does not exist in dim_product catalog",
                        value=product_id,
                    )
                )

        # 6. Quantities and Balance Check: actual_qty = good_qty + reject_qty
        target_qty = parse_cell_int(row.get("target_qty"))
        actual_qty = parse_cell_int(row.get("actual_qty"))
        good_qty = parse_cell_int(row.get("good_qty"))
        reject_qty = parse_cell_int(row.get("reject_qty"))
        rework_qty = parse_cell_int(row.get("rework_qty"))

        for q_name, q_val in [
            ("target_qty", target_qty),
            ("actual_qty", actual_qty),
            ("good_qty", good_qty),
            ("reject_qty", reject_qty),
            ("rework_qty", rework_qty),
        ]:
            if q_val is None or q_val < 0:
                row_errors.append(f"{q_name} must be a non-negative integer")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column=q_name,
                        error_type="RANGE_VIOLATION",
                        message=f"{q_name} must be non-negative integer",
                        value=str(row.get(q_name)),
                    )
                )

        if actual_qty is not None and good_qty is not None and reject_qty is not None:
            if actual_qty != (good_qty + reject_qty):
                msg = f"Quantity balance violation: actual_qty ({actual_qty}) must equal good_qty ({good_qty}) + reject_qty ({reject_qty})"
                row_errors.append(msg)
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column="actual_qty",
                        error_type="BALANCE_VIOLATION",
                        message=msg,
                        value=str(actual_qty),
                    )
                )

        # 7. Downtime validation: 0 <= downtime_min <= 60
        downtime_min = parse_cell_int(row.get("downtime_min"))
        if downtime_min is None or downtime_min < 0 or downtime_min > 60:
            row_errors.append(f"downtime_min must be between 0 and 60, got {downtime_min}")
            errors.append(
                RowValidationError(
                    row_number=idx,
                    column="downtime_min",
                    error_type="RANGE_VIOLATION",
                    message="downtime_min must be in range [0, 60]",
                    value=str(row.get("downtime_min")),
                )
            )

        shift_id = str(row.get("shift_id", "")).strip()
        production_order_id = str(row.get("production_order_id", "")).strip()
        downtime_reason = str(row.get("downtime_reason", "NONE")).strip() or "NONE"
        operator_team = str(row.get("operator_team", "")).strip()
        source_system = str(row.get("source_system", "MES")).strip() or "MES"
        data_quality = str(row.get("data_quality", "VALID")).strip() or "VALID"

        # 8. Business Key & Duplicate Verification: (event_ts, plant_id, line_id)
        b_key = None
        if event_ts and plant_id and line_id:
            b_key = (event_ts, plant_id, line_id)
            if b_key in seen_file_keys:
                is_duplicate = True
                row_errors.append("Duplicate production event key in uploaded file")
                errors.append(
                    RowValidationError(
                        row_number=idx,
                        column="business_key",
                        error_type="DUPLICATE_IN_FILE",
                        message=f"Duplicate entry for plant '{plant_id}', line '{line_id}' at timestamp '{event_ts.isoformat()}'",
                    )
                )
            else:
                seen_file_keys.add(b_key)

            if b_key in existing_db_keys:
                if mode == "OVERWRITE_CORRECTION":
                    duplicate_count += 1
                else:
                    is_duplicate = True
                    row_errors.append("Record already exists in Neon database")
                    errors.append(
                        RowValidationError(
                            row_number=idx,
                            column="business_key",
                            error_type="DUPLICATE_IN_DATABASE",
                            message=f"Existing record in database for plant '{plant_id}', line '{line_id}', timestamp '{event_ts.isoformat()}'",
                        )
                    )

        # Status determination
        if row_errors:
            if is_duplicate and len(row_errors) == 1:
                status = "DUPLICATE"
                duplicate_count += 1
            else:
                status = "REJECTED"
                rejected_count += 1
        else:
            status = "VALID"
            event_id = str(row.get("event_id", "")).strip()
            if not event_id:
                event_id = f"PRD-{uuid.uuid4().hex[:12].upper()}"

            valid_records.append(
                {
                    "event_id": event_id,
                    "event_ts": event_ts,
                    "event_date": event_date,
                    "year": year,
                    "month": month,
                    "week": week,
                    "day": day,
                    "hour": hour,
                    "plant_id": plant_id,
                    "line_id": line_id,
                    "shift_id": shift_id,
                    "product_id": product_id,
                    "production_order_id": production_order_id,
                    "target_qty": target_qty,
                    "actual_qty": actual_qty,
                    "good_qty": good_qty,
                    "reject_qty": reject_qty,
                    "rework_qty": rework_qty,
                    "downtime_min": downtime_min,
                    "downtime_reason": downtime_reason,
                    "operator_team": operator_team,
                    "source_system": source_system,
                    "data_quality": data_quality,
                }
            )

        # Preview generation (first 15 rows)
        if len(preview) < 15:
            preview.append(
                PreviewRow(
                    row_number=idx,
                    status=status,
                    data={
                        "event_ts": str(event_ts) if event_ts else str(row.get("event_ts")),
                        "event_date": str(event_date) if event_date else str(row.get("event_date")),
                        "plant_id": plant_id,
                        "line_id": line_id,
                        "product_id": product_id,
                        "shift_id": shift_id,
                        "target_qty": str(target_qty) if target_qty is not None else str(row.get("target_qty")),
                        "actual_qty": str(actual_qty) if actual_qty is not None else str(row.get("actual_qty")),
                        "good_qty": str(good_qty) if good_qty is not None else str(row.get("good_qty")),
                        "downtime_min": str(downtime_min) if downtime_min is not None else str(row.get("downtime_min")),
                    },
                    errors=row_errors,
                )
            )

    total_rows = len(rows)
    valid_rows = len(valid_records)

    completeness = assess_report_completeness("PRODUCTION", valid_records, master_cache)

    summary = ValidationSummary(
        report_type="PRODUCTION",
        total_rows=total_rows,
        valid_rows=valid_rows,
        rejected_rows=rejected_count,
        duplicate_rows=duplicate_count,
        detected_date=confirmed_date,
        confirmed_date=confirmed_date,
        plants_found=sorted(list(plants_found)),
        lines_found=sorted(list(lines_found)),
        is_ready_for_ingest=(valid_rows > 0),
        is_complete=completeness.is_complete,
        coverage_status=completeness.coverage_status,
        missing_hours=completeness.missing_hours,
        missing_entities=completeness.missing_entities,
        limitations=completeness.limitations,
        completeness=completeness,
    )

    return valid_records, errors, preview, summary


def get_existing_energy_keys(
    session: Session, target_date: Optional[date]
) -> Set[Tuple[datetime, str, str]]:
    """Query existing business keys for fact_energy_meter_hourly on given date."""
    if not target_date:
        return set()
    query = select(
        FactEnergyMeterHourly.timestamp,
        FactEnergyMeterHourly.plant_id,
        FactEnergyMeterHourly.meter_id,
    ).where(FactEnergyMeterHourly.date == target_date)
    res = session.execute(query).all()
    return set(res)


def get_existing_production_keys(
    session: Session, target_date: Optional[date]
) -> Set[Tuple[datetime, str, str]]:
    """Query existing business keys for fact_hourly_production on given date."""
    if not target_date:
        return set()
    query = select(
        FactHourlyProduction.event_ts,
        FactHourlyProduction.plant_id,
        FactHourlyProduction.line_id,
    ).where(FactHourlyProduction.event_date == target_date)
    res = session.execute(query).all()
    return set(res)


def validate_report_file(
    session: Session,
    filename: str,
    file_bytes: bytes,
    report_type: Optional[str] = None,
    sheet_name: Optional[str] = None,
    confirmed_date: Optional[date] = None,
    mode: str = "INCREMENTAL",
) -> Dict[str, Any]:
    """Inspect, parse, and validate an energy or production daily report."""
    inspect_meta = inspect_file(filename, file_bytes)
    file_format = inspect_meta.file_format

    headers, rows = parse_raw_sheet_rows(file_bytes, file_format, sheet_name=sheet_name)
    if not rows:
        raise ValueError("Uploaded file contains no data rows.")

    # Determine report type if not explicitly passed
    resolved_type = report_type
    if not resolved_type or resolved_type == "AUTO":
        resolved_type = classify_columns(headers)
        if resolved_type == "UNKNOWN":
            raise ValueError(
                "Unable to identify report type from column headers. Expected energy or production columns."
            )

    # Detect dates present in rows
    detected_dates = detect_reporting_dates_from_rows(rows, resolved_type)
    effective_date = confirmed_date
    if not effective_date and detected_dates:
        # Use first or predominant detected date
        effective_date = detected_dates[0]

    # Check header schema integrity: missing columns, unknown columns, and measurement units
    missing_required, unknown_cols, unsupported_units = check_header_schema(headers, resolved_type)
    header_errors: List[RowValidationError] = []
    for m in missing_required:
        header_errors.append(
            RowValidationError(
                row_number=0,
                column=m,
                error_type="MISSING_REQUIRED_COLUMN",
                message=f"Approved source schema requires column '{m}', but it is missing from the file.",
            )
        )
    for u in unknown_cols:
        header_errors.append(
            RowValidationError(
                row_number=0,
                column=u,
                error_type="UNKNOWN_COLUMN",
                message=f"Unknown column '{u}' not recognized in approved source schema. Automatic mapping is disabled.",
            )
        )
    for un in unsupported_units:
        header_errors.append(
            RowValidationError(
                row_number=0,
                column="units",
                error_type="UNSUPPORTED_UNIT",
                message=un,
            )
        )

    master_cache = MasterDataCache(session)

    if resolved_type == "ENERGY":
        existing_keys = get_existing_energy_keys(session, effective_date)
        valid_records, row_errors, preview, summary = validate_energy_rows(
            rows, effective_date, master_cache, existing_keys, mode=mode
        )
    elif resolved_type == "PRODUCTION":
        existing_keys = get_existing_production_keys(session, effective_date)
        valid_records, row_errors, preview, summary = validate_production_rows(
            rows, effective_date, master_cache, existing_keys, mode=mode
        )
    else:
        raise ValueError(f"Report type '{resolved_type}' is not supported for single-sheet validation.")

    all_errors = header_errors + row_errors

    # If critical schema errors (missing required columns or unknown columns), invalidate all records
    if missing_required or unknown_cols or unsupported_units:
        valid_records = []
        summary.valid_rows = 0
        summary.rejected_rows = len(rows)
        summary.is_ready_for_ingest = False
        summary.is_complete = False
        summary.coverage_status = "PARTIAL"
        summary.limitations = ["Report rejected due to source schema mismatches."]

    return {
        "filename": filename,
        "file_format": file_format,
        "sheet_name": sheet_name,
        "sheet_names": inspect_meta.sheet_names,
        "detected_dates": [d.isoformat() for d in detected_dates],
        "confirmed_date": effective_date.isoformat() if effective_date else None,
        "summary": summary,
        "errors": all_errors[:200],  # Return up to 200 specific validation issues
        "preview": preview,
        "valid_records": valid_records,
    }


def ingest_validated_report(
    session: Session,
    filename: str,
    file_bytes: bytes,
    report_type: str,
    reporting_date: date,
    mode: str = "INCREMENTAL",
    sheet_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ingest approved daily report into fact tables transactionally and update audit log.
    Supports INCREMENTAL (skip existing duplicates) and OVERWRITE_CORRECTION (replace existing for date).
    """
    if mode not in {"INCREMENTAL", "OVERWRITE_CORRECTION"}:
        raise ValueError(f"Invalid ingestion mode: '{mode}'. Must be INCREMENTAL or OVERWRITE_CORRECTION.")

    # Re-validate with confirmed date and mode to ensure zero bypass
    val_result = validate_report_file(
        session=session,
        filename=filename,
        file_bytes=file_bytes,
        report_type=report_type,
        sheet_name=sheet_name,
        confirmed_date=reporting_date,
        mode=mode,
    )

    valid_records = val_result["valid_records"]
    summary: ValidationSummary = val_result["summary"]

    if not valid_records:
        raise ValueError("Cannot ingest report: 0 valid records found to import.")

    upload_id = f"UPL-{reporting_date.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    file_format = val_result["file_format"]
    imported_count = len(valid_records)
    overwritten_count = 0
    ingested_at = datetime.utcnow()

    # Exact batch attribution: stamp every valid record with current upload_id and ingestion timestamp
    for r in valid_records:
        r["upload_id"] = upload_id
        r["ingested_at"] = ingested_at

    try:
        # Insert parent UploadHistory entry and flush to satisfy foreign key constraints transactionally
        history_entry = UploadHistory(
            upload_id=upload_id,
            uploaded_at=ingested_at,
            report_type=report_type,
            filename=os.path.basename(filename),
            file_format=file_format,
            sheet_name=sheet_name,
            reporting_date=reporting_date,
            file_size_bytes=len(file_bytes),
            total_rows=summary.total_rows,
            valid_rows=imported_count,
            rejected_rows=summary.rejected_rows,
            duplicate_rows=summary.duplicate_rows,
            status="PROCESSING",
            mode=mode,
            audit_details=None,
        )
        session.add(history_entry)
        session.flush()

        energy_superseded: Dict[str, int] = {}
        prod_superseded: Dict[str, int] = {}

        # Atomic database transaction with strictly scoped key deletion for historical corrections
        if report_type == "ENERGY":
            if mode == "OVERWRITE_CORRECTION":
                # Replacement scope strictly restricted to incoming (timestamp, plant_id, meter_id) keys
                replacement_keys = [
                    (r["timestamp"], r["plant_id"], r["meter_id"])
                    for r in valid_records
                    if r.get("timestamp") and r.get("plant_id") and r.get("meter_id")
                ]
                if replacement_keys:
                    chunk_size = 500
                    for i in range(0, len(replacement_keys), chunk_size):
                        chunk = replacement_keys[i : i + chunk_size]
                        del_stmt = (
                            delete(FactEnergyMeterHourly)
                            .where(
                                FactEnergyMeterHourly.date == reporting_date,
                                tuple_(
                                    FactEnergyMeterHourly.timestamp,
                                    FactEnergyMeterHourly.plant_id,
                                    FactEnergyMeterHourly.meter_id,
                                ).in_(chunk),
                            )
                            .returning(FactEnergyMeterHourly.upload_id)
                        )
                        del_rows = session.execute(del_stmt).scalars().all()
                        overwritten_count += len(del_rows)
                        for orig_uid in del_rows:
                            key = orig_uid if orig_uid is not None else "__LEGACY__"
                            energy_superseded[key] = energy_superseded.get(key, 0) + 1

            # Bulk insert valid mappings
            session.bulk_insert_mappings(FactEnergyMeterHourly, valid_records)

        elif report_type == "PRODUCTION":
            if mode == "OVERWRITE_CORRECTION":
                # Replacement scope strictly restricted to incoming (event_ts, plant_id, line_id) keys
                replacement_keys = [
                    (r["event_ts"], r["plant_id"], r["line_id"])
                    for r in valid_records
                    if r.get("event_ts") and r.get("plant_id") and r.get("line_id")
                ]
                if replacement_keys:
                    chunk_size = 500
                    for i in range(0, len(replacement_keys), chunk_size):
                        chunk = replacement_keys[i : i + chunk_size]
                        del_stmt = (
                            delete(FactHourlyProduction)
                            .where(
                                FactHourlyProduction.event_date == reporting_date,
                                tuple_(
                                    FactHourlyProduction.event_ts,
                                    FactHourlyProduction.plant_id,
                                    FactHourlyProduction.line_id,
                                ).in_(chunk),
                            )
                            .returning(FactHourlyProduction.upload_id)
                        )
                        del_rows = session.execute(del_stmt).scalars().all()
                        overwritten_count += len(del_rows)
                        for orig_uid in del_rows:
                            key = orig_uid if orig_uid is not None else "__LEGACY__"
                            prod_superseded[key] = prod_superseded.get(key, 0) + 1

            session.bulk_insert_mappings(FactHourlyProduction, valid_records)

        # Structure exact supersession attribution metadata
        superseded_batches: Dict[str, int] = {}
        superseded_by_type: Dict[str, Dict[str, int]] = {}

        if energy_superseded:
            superseded_by_type["ENERGY"] = energy_superseded
            for k, v in energy_superseded.items():
                superseded_batches[k] = superseded_batches.get(k, 0) + v

        if prod_superseded:
            superseded_by_type["PRODUCTION"] = prod_superseded
            for k, v in prod_superseded.items():
                superseded_batches[k] = superseded_batches.get(k, 0) + v

        status = "COMPLETED"
        if summary.rejected_rows > 0:
            status = "PARTIAL"

        # Build affected scope summary
        if report_type == "ENERGY":
            affected_scope = {
                "report_type": "ENERGY",
                "reporting_date": reporting_date.isoformat(),
                "plants": summary.plants_found,
                "meters": summary.meters_found,
                "hours_covered": sorted(list({r["timestamp"].hour for r in valid_records if r.get("timestamp")})),
                "timestamps_count": len({r["timestamp"] for r in valid_records if r.get("timestamp")}),
                "overwritten_records": overwritten_count,
                "superseded_batches": superseded_batches,
                "superseded_by_type": superseded_by_type,
                "coverage_status": summary.coverage_status,
                "upload_id": upload_id,
            }
        else:
            affected_scope = {
                "report_type": "PRODUCTION",
                "reporting_date": reporting_date.isoformat(),
                "plants": summary.plants_found,
                "lines": summary.lines_found,
                "hours_covered": sorted(list({r["event_ts"].hour for r in valid_records if r.get("event_ts")})),
                "timestamps_count": len({r["event_ts"] for r in valid_records if r.get("event_ts")}),
                "overwritten_records": overwritten_count,
                "superseded_batches": superseded_batches,
                "superseded_by_type": superseded_by_type,
                "coverage_status": summary.coverage_status,
                "upload_id": upload_id,
            }

        # Audit details
        audit_details = json.dumps(
            {
                "upload_id": upload_id,
                "ingested_at": ingested_at.isoformat(),
                "imported_records": imported_count,
                "overwritten_records": overwritten_count,
                "superseded_batches": superseded_batches,
                "superseded_by_type": superseded_by_type,
                "plants_affected": summary.plants_found,
                "meters_affected": summary.meters_found,
                "lines_affected": summary.lines_found,
                "rejected_count": summary.rejected_rows,
                "duplicate_count": summary.duplicate_rows,
                "coverage_status": summary.coverage_status,
                "missing_hours": summary.missing_hours,
                "missing_entities": summary.missing_entities,
                "mode": mode,
                "affected_scope": affected_scope,
            }
        )

        # Finalize upload history audit entry
        history_entry.status = status
        history_entry.valid_rows = imported_count
        history_entry.audit_details = audit_details
        session.commit()

        message = (
            f"Successfully ingested {imported_count} records into {report_type.lower()} facts "
            f"for reporting date {reporting_date.isoformat()} (mode: {mode})."
        )
        if mode == "OVERWRITE_CORRECTION":
            message += f" Historical correction replaced {overwritten_count} existing records matching exact incoming keys."
        if summary.coverage_status == "PARTIAL":
            message += f" Note: Report coverage is partial ({summary.completeness.hours_reported if summary.completeness else 'N/A'}/24 hours reported)."

        return {
            "upload_id": upload_id,
            "status": status,
            "report_type": report_type,
            "reporting_date": reporting_date,
            "total_rows": summary.total_rows,
            "imported_rows": imported_count,
            "duplicate_rows": summary.duplicate_rows,
            "rejected_rows": summary.rejected_rows,
            "mode": mode,
            "message": message,
            "replaced_rows": overwritten_count,
            "affected_scope": affected_scope,
        }

    except Exception as exc:
        session.rollback()
        # Record failure entry in history if possible
        try:
            fail_entry = UploadHistory(
                upload_id=upload_id,
                uploaded_at=datetime.utcnow(),
                report_type=report_type,
                filename=os.path.basename(filename),
                file_format=file_format,
                sheet_name=sheet_name,
                reporting_date=reporting_date,
                file_size_bytes=len(file_bytes),
                total_rows=summary.total_rows if 'summary' in locals() else 0,
                valid_rows=0,
                rejected_rows=summary.total_rows if 'summary' in locals() else 0,
                duplicate_rows=0,
                status="FAILED",
                mode=mode,
                audit_details=json.dumps({"error": str(exc)}),
            )
            session.add(fail_entry)
            session.commit()
        except Exception:
            session.rollback()

        raise RuntimeError(f"Database ingestion failed transactionally: {str(exc)}")


def generate_template_csv(report_type: str) -> str:
    """Generate sample CSV template with approved headers and reference rows."""
    out = io.StringIO()
    writer = csv.writer(out)

    if report_type.upper() == "ENERGY":
        headers = [
            "meter_reading_id",
            "timestamp",
            "date",
            "plant_id",
            "meter_id",
            "area",
            "energy_source",
            "consumption_kwh",
            "demand_kw",
            "power_factor",
            "tariff_inr_per_kwh",
            "cost_inr",
            "co2e_kg",
            "reading_quality",
        ]
        sample = [
            "EN-20261112-0001",
            "2026-11-12T00:00:00",
            "2026-11-12",
            "IN-TN-01",
            "MTR-SMT",
            "SMT",
            "ELECTRICITY",
            "120.500",
            "110.200",
            "0.965",
            "8.25",
            "994.13",
            "86.278",
            "VALID",
        ]
        writer.writerow(headers)
        writer.writerow(sample)

    elif report_type.upper() == "PRODUCTION":
        headers = [
            "event_id",
            "event_ts",
            "event_date",
            "year",
            "month",
            "week",
            "day",
            "hour",
            "plant_id",
            "line_id",
            "shift_id",
            "product_id",
            "production_order_id",
            "target_qty",
            "actual_qty",
            "good_qty",
            "reject_qty",
            "rework_qty",
            "downtime_min",
            "downtime_reason",
            "operator_team",
            "source_system",
            "data_quality",
        ]
        sample = [
            "PRD-20261112-0001",
            "2026-11-12T00:00:00",
            "2026-11-12",
            "2026",
            "11",
            "46",
            "12",
            "0",
            "IN-TN-01",
            "SMT-L1",
            "A",
            "SPH-A15-128",
            "PO-000999",
            "390",
            "375",
            "370",
            "5",
            "2",
            "0",
            "NONE",
            "TEAM-01",
            "MES",
            "VALID",
        ]
        writer.writerow(headers)
        writer.writerow(sample)

    return out.getvalue()
