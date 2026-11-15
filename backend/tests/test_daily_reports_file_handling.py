"""
Automated unit tests for Daily Reports file handling and format ingestion.

Tests file format detection, magic byte verification, file size and row limits,
empty files, worksheet selection, encoding fallbacks, and header normalization.
Completely database-free and isolated.
"""

import csv
import io
import unittest
from unittest.mock import patch
import openpyxl

from app.services.daily_report_service import (
    MAX_FILE_SIZE_BYTES,
    MAX_ROW_COUNT,
    check_header_schema,
    detect_file_format,
    inspect_file,
    normalize_col_name,
    parse_raw_sheet_rows,
)


class TestDailyReportsFileHandling(unittest.TestCase):
    """File handling, format validation, sheet parsing, and limits."""

    def test_detect_file_format_valid_extensions(self):
        """Supported extensions .csv, .xlsx, and .xls are properly detected."""
        csv_bytes = b"timestamp,date,plant_id\n2026-04-01 00:00:00,2026-04-01,PLANT-A"
        self.assertEqual(detect_file_format("report.csv", csv_bytes), "CSV")

        xlsx_bytes = b"PK\x03\x04\x14\x00\x06\x00" + b"\x00" * 20
        self.assertEqual(detect_file_format("report.xlsx", xlsx_bytes), "XLSX")

        xls_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 20
        self.assertEqual(detect_file_format("report.xls", xls_bytes), "XLS")

    def test_detect_file_format_unsupported_extensions(self):
        """Unsupported extensions raise ValueError with explicit allowed formats."""
        for filename in ["report.pdf", "data.json", "dump.parquet", "notes.txt", "archive.zip"]:
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError) as ctx:
                    detect_file_format(filename, b"dummy content")
                self.assertIn("Allowed formats: .csv, .xlsx, .xls", str(ctx.exception))

    def test_detect_file_format_magic_byte_mismatch_xlsx(self):
        """An XLSX file without PK zip magic bytes is rejected."""
        corrupted_xlsx = b"NOT_A_ZIP_HEADER" + b"\x00" * 50
        with self.assertRaises(ValueError) as ctx:
            detect_file_format("corrupted.xlsx", corrupted_xlsx)
        self.assertIn("missing standard ZIP/OpenXML signature", str(ctx.exception))

    def test_detect_file_format_magic_byte_mismatch_xls(self):
        """An XLS file without OLE2 compound document magic bytes is rejected."""
        corrupted_xls = b"NOT_AN_OLE2_FILE" + b"\x00" * 50
        with self.assertRaises(ValueError) as ctx:
            detect_file_format("corrupted.xls", corrupted_xls)
        self.assertIn("missing standard OLE2 compound document signature", str(ctx.exception))

    def test_detect_file_format_rejects_binary_executable_as_csv(self):
        """Security guard: Windows PE or Linux ELF executables masquerading as CSV are rejected."""
        mz_binary = b"MZ\x90\x00\x03\x00\x00\x00"
        with self.assertRaises(ValueError) as ctx:
            detect_file_format("malicious.csv", mz_binary)
        self.assertIn("Binary executable detected", str(ctx.exception))

        elf_binary = b"\x7fELF\x02\x01\x01\x00"
        with self.assertRaises(ValueError) as ctx:
            detect_file_format("malicious_elf.csv", elf_binary)
        self.assertIn("Binary executable detected", str(ctx.exception))

    def test_file_size_limit_enforcement(self):
        """Files exceeding MAX_FILE_SIZE_BYTES are rejected during inspection."""
        oversized_bytes = b"A" * (MAX_FILE_SIZE_BYTES + 1024)
        with self.assertRaises(ValueError) as ctx:
            inspect_file("oversized.csv", oversized_bytes)
        self.assertIn("exceeds maximum allowed size", str(ctx.exception))

    def test_inspect_csv_file(self):
        """Inspecting a valid CSV returns metadata, single sheet name, and estimated rows."""
        csv_content = (
            "timestamp,date,plant_id,meter_id,area,energy_source,consumption_kwh,demand_kw,"
            "power_factor,tariff_inr_per_kwh,cost_inr,co2e_kg,reading_quality\n"
            "2026-04-01 00:00:00,2026-04-01,PLANT-A,MTR-SMT,SMT,ELECTRICITY,100,25,0.95,7.5,750,82,VALID\n"
            "2026-04-01 01:00:00,2026-04-01,PLANT-A,MTR-SMT,SMT,ELECTRICITY,105,26,0.96,7.5,787.5,86,VALID\n"
        ).encode("utf-8")

        res = inspect_file("energy_daily.csv", csv_content)
        self.assertEqual(res.filename, "energy_daily.csv")
        self.assertEqual(res.file_format, "CSV")
        self.assertEqual(res.sheet_names, ["Sheet1"])
        self.assertFalse(res.is_multi_sheet)
        self.assertEqual(res.detected_report_type, "ENERGY")
        self.assertEqual(res.estimated_rows, 2)

    def test_inspect_xlsx_multi_sheet(self):
        """Inspecting a multi-sheet XLSX enumerates all sheet names and identifies report type."""
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "EnergyReadings"
        ws1.append(["timestamp", "date", "plant_id", "meter_id", "consumption_kwh"])
        ws1.append(["2026-04-01 00:00:00", "2026-04-01", "PLANT-A", "MTR-SMT", 120])

        ws2 = wb.create_sheet(title="ProductionLogs")
        ws2.append(["event_ts", "event_date", "plant_id", "line_id", "actual_qty"])
        ws2.append(["2026-04-01 00:00:00", "2026-04-01", "PLANT-A", "LINE-SMT-1", 450])

        buf = io.BytesIO()
        wb.save(buf)
        xlsx_bytes = buf.getvalue()

        res = inspect_file("daily_data.xlsx", xlsx_bytes)
        self.assertEqual(res.file_format, "XLSX")
        self.assertEqual(res.sheet_names, ["EnergyReadings", "ProductionLogs"])
        self.assertTrue(res.is_multi_sheet)
        self.assertEqual(res.detected_report_type, "ENERGY")

    def test_parse_csv_utf8_with_bom(self):
        """CSV with UTF-8 BOM is cleanly parsed and BOM stripped from the first header."""
        bom_csv = (
            "\ufefftimestamp,date,plant_id,meter_id,consumption_kwh\n"
            "2026-04-01 00:00:00,2026-04-01,PLANT-A,MTR-SMT,150.0\n"
        ).encode("utf-8")

        headers, rows = parse_raw_sheet_rows(bom_csv, "CSV")
        self.assertEqual(headers[0], "timestamp")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["plant_id"], "PLANT-A")
        self.assertEqual(rows[0]["consumption_kwh"], "150.0")

    def test_parse_csv_latin1_fallback(self):
        """CSV encoded with Latin-1 (special characters) falls back cleanly without decoding failure."""
        latin1_csv = (
            "timestamp,date,plant_id,meter_id,area\n"
            "2026-04-01 00:00:00,2026-04-01,PLANT-A,MTR-SMT,FAL-Chambéry\n"
        ).encode("latin-1")

        headers, rows = parse_raw_sheet_rows(latin1_csv, "CSV")
        self.assertEqual(headers, ["timestamp", "date", "plant_id", "meter_id", "area"])
        self.assertEqual(len(rows), 1)
        self.assertIn("Chamb", rows[0]["area"])

    def test_parse_csv_binary_nul_byte_rejection(self):
        """CSV containing binary NUL bytes raises ValueError immediately."""
        malformed_csv = b"timestamp,date,plant_id\x00\x00,meter_id\n"
        with self.assertRaises(ValueError) as ctx:
            parse_raw_sheet_rows(malformed_csv, "CSV")
        self.assertIn("Binary NUL byte detected", str(ctx.exception))

    def test_parse_xlsx_sheet_selection(self):
        """Explicitly targeting a specific sheet extracts rows from that sheet."""
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "SummarySheet"
        ws1.append(["notes", "author"])
        ws1.append(["Weekly overview", "Lead Tech"])

        ws2 = wb.create_sheet(title="FactData")
        ws2.append(["timestamp", "date", "plant_id", "meter_id"])
        ws2.append(["2026-04-01 00:00:00", "2026-04-01", "PLANT-A", "MTR-SMT"])

        buf = io.BytesIO()
        wb.save(buf)
        xlsx_bytes = buf.getvalue()

        # Target second sheet explicitly
        headers, rows = parse_raw_sheet_rows(xlsx_bytes, "XLSX", sheet_name="FactData")
        self.assertEqual(headers, ["timestamp", "date", "plant_id", "meter_id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["meter_id"], "MTR-SMT")

    def test_parse_xlsx_corrupted_container(self):
        """Corrupted ZIP archive masquerading as XLSX raises ValueError."""
        corrupted_zip = b"PK\x03\x04" + b"random_corrupted_payload_bytes_that_are_not_a_valid_zip"
        with self.assertRaises(ValueError) as ctx:
            parse_raw_sheet_rows(corrupted_zip, "XLSX")
        self.assertIn("Corrupted or incomplete ZIP container", str(ctx.exception))

    def test_empty_csv_and_empty_sheet(self):
        """Empty file or sheet with only empty lines returns empty rows list."""
        empty_csv = b"\n   \n\r\n"
        headers, rows = parse_raw_sheet_rows(empty_csv, "CSV")
        self.assertEqual(headers, [])
        self.assertEqual(rows, [])

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "EmptySheet"
        buf = io.BytesIO()
        wb.save(buf)

        headers_x, rows_x = parse_raw_sheet_rows(buf.getvalue(), "XLSX")
        self.assertEqual(headers_x, [])
        self.assertEqual(rows_x, [])

    def test_header_whitespace_normalization(self):
        """Headers with arbitrary whitespace, capitals, and punctuation are normalized."""
        self.assertEqual(normalize_col_name("  Consumption_KWh  "), "consumption_kwh")
        self.assertEqual(normalize_col_name("Plant ID"), "plant_id")
        self.assertEqual(normalize_col_name("\ufeffTIMESTAMP"), "timestamp")
        self.assertEqual(normalize_col_name("  TARiFF  INR  PER  KWH  "), "tariff_inr_per_kwh")
        self.assertEqual(normalize_col_name(""), "")
        self.assertEqual(normalize_col_name(None), "")

    def test_column_order_independence(self):
        """Required columns appearing in arbitrary order are properly validated."""
        shuffled_headers = [
            "reading_quality",
            "meter_id",
            "plant_id",
            "co2e_kg",
            "date",
            "consumption_kwh",
            "area",
            "timestamp",
            "cost_inr",
            "tariff_inr_per_kwh",
            "demand_kw",
            "power_factor",
            "energy_source",
        ]
        missing, unknown, unsupp = check_header_schema(shuffled_headers, "ENERGY")
        self.assertEqual(missing, [])
        self.assertEqual(unknown, [])
        self.assertEqual(unsupp, [])


if __name__ == "__main__":
    unittest.main()

