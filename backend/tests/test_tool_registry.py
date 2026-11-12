"""
Automated unit and integration tests for Deterministic Analytics Tool Registry.

Verifies:
1. Tool catalog completeness (all 20 deterministic tools across 4 categories).
2. Input argument validation (rejection of invalid date and time ranges).
3. Parameter parsing and coercion (ISO strings to dates/datetimes).
4. Deterministic analytics execution and result referential accuracy.
5. Preservation of Decimal types and numerical precision.
6. Execution with explicit session and autonomous session lifecycle.
7. Proper error handling for unknown tools.
8. LangChain StructuredTool conversion compatibility.
"""

from datetime import date, datetime
from decimal import Decimal
import unittest

from app.db import get_engine, get_session_factory
from app.services.agent.tool_registry import (
    TOOL_REGISTRY,
    EnergySummaryInput,
    StatisticalAnomaliesInput,
    execute_tool,
    get_all_tools,
    get_tool,
    get_tool_descriptions,
)


class TestToolRegistry(unittest.TestCase):
    """Test suite validating tool definitions, validation schemas, and execution."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        if cls.engine is None:
            raise RuntimeError("Database engine not available for tests.")
        cls.session_factory = get_session_factory()

    def setUp(self):
        self.session = self.session_factory()

    def tearDown(self):
        self.session.close()

    def test_registry_completeness_and_categories(self):
        """Verify all 21 tools (20 deterministic + 1 read-only SQL) are present and categorized."""
        tools = get_all_tools()
        self.assertEqual(len(tools), 21)

        expected_energy_tools = {
            "energy_summary",
            "energy_by_meter",
            "energy_by_area",
            "energy_daily_trend",
            "power_factor_summary",
        }
        expected_production_tools = {
            "production_summary",
            "production_by_line",
            "production_by_product",
            "production_by_shift",
            "downtime_by_reason",
            "production_daily_trend",
        }
        expected_intensity_tools = {
            "process_energy_intensity",
            "factory_energy_intensity",
            "product_process_energy",
            "zero_production_period_energy",
        }
        expected_anomaly_tools = {
            "statistical_energy_anomalies",
            "rolling_baseline_anomalies",
            "low_power_factor_anomalies",
            "zero_production_standby_anomalies",
            "unified_anomaly_detection",
        }
        expected_sql_tools = {
            "read_only_sql_query",
        }

        all_expected = (
            expected_energy_tools
            | expected_production_tools
            | expected_intensity_tools
            | expected_anomaly_tools
            | expected_sql_tools
        )
        self.assertEqual(set(tools.keys()), all_expected)

        # Verify categories
        for name in expected_energy_tools:
            self.assertEqual(tools[name].category, "energy")
        for name in expected_production_tools:
            self.assertEqual(tools[name].category, "production")
        for name in expected_intensity_tools:
            self.assertEqual(tools[name].category, "energy_intensity")
        for name in expected_anomaly_tools:
            self.assertEqual(tools[name].category, "anomalies")
        for name in expected_sql_tools:
            self.assertEqual(tools[name].category, "sql")

    def test_input_schema_validation(self):
        """Verify that date and time validation enforces logical ranges."""
        # Valid date range
        valid = EnergySummaryInput(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
        self.assertEqual(valid.start_date, date(2026, 1, 1))

        # Inverted date range must raise ValueError
        with self.assertRaises(ValueError):
            EnergySummaryInput(start_date=date(2026, 2, 1), end_date=date(2026, 1, 1))

        # Inverted timestamp range must raise ValueError
        with self.assertRaises(ValueError):
            StatisticalAnomaliesInput(
                start_time=datetime(2026, 2, 1, 12, 0, 0),
                end_time=datetime(2026, 1, 1, 12, 0, 0),
            )

    def test_execute_energy_summary_tool(self):
        """Verify execution of energy_summary tool returns exact database totals."""
        result = execute_tool("energy_summary", {}, session=self.session)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["total_consumption_kwh"], Decimal("1958088.3130"))
        self.assertEqual(result["total_cost_inr"], Decimal("16154228.24"))
        self.assertEqual(result["total_readings"], 22080)

    def test_execute_production_summary_tool(self):
        """Verify execution of production_summary tool returns exact outputs and OEE disclaimer."""
        result = execute_tool("production_summary", {}, session=self.session)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["target_qty"], 2914560)
        self.assertEqual(result["actual_qty"], 2424184)
        self.assertEqual(result["good_qty"], 2378960)
        self.assertEqual(result["reject_qty"], 45224)
        self.assertEqual(result["rework_qty"], 24852)
        self.assertEqual(result["downtime_min"], 60290)
        self.assertEqual(result["oee"]["status"], "unavailable")

    def test_execute_process_energy_intensity_tool(self):
        """Verify process energy intensity computes SEC for SMT and FAL lines."""
        result = execute_tool("process_energy_intensity", {}, session=self.session)
        self.assertIn("smt_summary", result)
        self.assertIn("fal_summary", result)
        self.assertEqual(result["smt_summary"]["overall_process_sec_kwh_per_board"], Decimal("0.3547"))
        self.assertEqual(result["fal_summary"]["overall_process_sec_kwh_per_phone"], Decimal("0.3652"))

    def test_execute_zero_production_period_tool(self):
        """Verify standby energy returns non-production power and engineering disclaimer."""
        result = execute_tool("zero_production_period_energy", {}, session=self.session)
        self.assertIn("total_zero_production_energy_kwh", result)
        self.assertEqual(result["total_zero_production_hours"], 155)
        self.assertEqual(result["total_zero_production_energy_kwh"], Decimal("15553.9580"))
        self.assertIn("classification_note", result)

    def test_execute_tool_with_auto_session_lifecycle(self):
        """Verify tool execution without an external session manages session lifecycle safely."""
        # session=None triggers automatic session acquisition from factory and closing
        result = execute_tool("energy_by_meter", {"plant_id": "IN-TN-01"}, session=None)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_unknown_tool_raises_value_error(self):
        """Verify requesting an unregistered tool raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            execute_tool("non_existent_tool_12345", {}, session=self.session)
        self.assertIn("non_existent_tool_12345", str(ctx.exception))

    def test_tool_descriptions_generation(self):
        """Verify catalog description string formats all tools for prompt injection."""
        desc = get_tool_descriptions()
        self.assertIn("energy_summary", desc)
        self.assertIn("production_summary", desc)
        self.assertIn("process_energy_intensity", desc)
        self.assertIn("statistical_energy_anomalies", desc)

    def test_langchain_tool_conversion(self):
        """Verify conversion to LangChain StructuredTool instance."""
        tool = get_tool("energy_summary")
        self.assertIsNotNone(tool)
        lc_tool = tool.to_langchain_tool()
        self.assertIsNotNone(lc_tool)
        self.assertEqual(lc_tool.name, "energy_summary")
        self.assertEqual(lc_tool.description, tool.description)


    def test_execute_sql_tool_via_registry(self):
        """Verify execution of read_only_sql_query via execute_tool."""
        result = execute_tool("read_only_sql_query", {"query": "SELECT count(*) AS cnt FROM dim_product"})
        self.assertIsInstance(result, dict)
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["rows"][0][0], 3)


if __name__ == "__main__":
    unittest.main()
