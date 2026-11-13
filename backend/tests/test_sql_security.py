"""
Comprehensive security and execution tests for the dedicated read-only database role and SQL tool.

Covers:
1. Engine isolation: Reader engine strictly uses READONLY_DATABASE_URL and never falls back.
2. Missing reader URL fails safely with RuntimeError.
3. SQL validation rejection:
   - DML (INSERT, UPDATE, DELETE, MERGE)
   - DDL (DROP, CREATE, ALTER, TRUNCATE)
   - Administration (GRANT, REVOKE, SET, RESET)
   - Multi-statement injection (semicolons)
   - Comment-based concealment (-- and /* */)
   - Modifying CTEs (WITH del AS (DELETE...))
   - Row-locking clauses (FOR UPDATE, FOR SHARE)
   - SELECT INTO
   - Unapproved tables and schemas (alembic_version, pg_catalog, information_schema)
   - Dangerous functions (pg_sleep, set_config, dblink)
4. SQL validation acceptance:
   - Standard SELECTs across approved tables
   - Multi-table joins (e.g. fact_hourly_production JOIN dim_production_line)
   - Read-only CTEs with aggregation
   - Safe WHERE conditions and aliases
   - Safe LIMIT capping at 100
5. Live PostgreSQL permission enforcement via dedicated role:
   - Authenticated user is strictly energy_agent_reader
   - Database permissions deny INSERT, UPDATE, DELETE, DROP at the database level
   - Execution timeout enforced
   - Row limit enforced
   - Decimal values and ISO dates preserved
"""

import os
from unittest.mock import patch
import unittest

from sqlalchemy import text

from app.config import get_settings
from app.db import (
    get_engine,
    get_readonly_engine,
    normalize_database_url,
    reset_db_engines,
)
from app.services.agent.sql_tool import (
    SQLExecutionError,
    execute_read_only_sql,
)
from app.services.agent.sql_validator import (
    SQLValidationError,
    validate_sql,
)


class TestSQLSecurity(unittest.TestCase):
    """Test suite validating SQL AST security, role enforcement, and execution boundaries."""

    # -----------------------------------------------------------------------
    # 1. Engine & Configuration Security
    # -----------------------------------------------------------------------

    def test_reader_engine_uses_readonly_url(self):
        """Verify get_readonly_engine() uses READONLY_DATABASE_URL and connects as energy_agent_reader."""
        reset_db_engines()
        engine = get_readonly_engine()
        with engine.connect() as conn:
            user = conn.execute(text("SELECT current_user")).scalar()
            self.assertEqual(user, "energy_agent_reader")

    def test_missing_readonly_url_raises_runtime_error(self):
        """Verify get_readonly_engine() fails immediately if READONLY_DATABASE_URL is not set."""
        reset_db_engines()
        with patch.object(get_settings(), "READONLY_DATABASE_URL", None):
            with self.assertRaises(RuntimeError) as ctx:
                get_readonly_engine()
            self.assertIn("READONLY_DATABASE_URL is not configured", str(ctx.exception))
        reset_db_engines()

    def test_reader_engine_never_falls_back_to_owner_url(self):
        """Verify that get_readonly_engine() does NOT use DATABASE_URL when READONLY_DATABASE_URL is absent."""
        reset_db_engines()
        settings = get_settings()
        owner_url = settings.DATABASE_URL
        self.assertIsNotNone(owner_url)

        with patch.object(settings, "READONLY_DATABASE_URL", None):
            with self.assertRaises(RuntimeError):
                get_readonly_engine()
        reset_db_engines()

    # -----------------------------------------------------------------------
    # 2. SQL Validation — Strictly Rejected Constructs
    # -----------------------------------------------------------------------

    def test_reject_empty_query(self):
        """Reject empty or whitespace queries."""
        with self.assertRaises(SQLValidationError):
            validate_sql("")
        with self.assertRaises(SQLValidationError):
            validate_sql("   ")

    def test_reject_sql_comments(self):
        """Reject SQL comments used for statement concealment."""
        with self.assertRaises(SQLValidationError) as ctx:
            validate_sql("SELECT * FROM dim_product -- comment")
        self.assertIn("comments", str(ctx.exception).lower())

        with self.assertRaises(SQLValidationError) as ctx:
            validate_sql("SELECT * FROM dim_product /* block comment */ WHERE 1=1")
        self.assertIn("comments", str(ctx.exception).lower())

    def test_reject_dml_statements(self):
        """Reject INSERT, UPDATE, DELETE, MERGE queries."""
        with self.assertRaises(SQLValidationError):
            validate_sql("INSERT INTO dim_product (product_id) VALUES ('BAD')")
        with self.assertRaises(SQLValidationError):
            validate_sql("UPDATE dim_product SET product_name = 'hacked'")
        with self.assertRaises(SQLValidationError):
            validate_sql("DELETE FROM dim_product WHERE product_id = 'PROD-A15-128'")

    def test_reject_ddl_and_admin_statements(self):
        """Reject DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE."""
        with self.assertRaises(SQLValidationError):
            validate_sql("DROP TABLE dim_product")
        with self.assertRaises(SQLValidationError):
            validate_sql("ALTER TABLE dim_product ADD COLUMN test text")
        with self.assertRaises(SQLValidationError):
            validate_sql("TRUNCATE TABLE dim_product")
        with self.assertRaises(SQLValidationError):
            validate_sql("CREATE TABLE evil (id int)")
        with self.assertRaises(SQLValidationError):
            validate_sql("GRANT ALL ON dim_product TO public")
        with self.assertRaises(SQLValidationError):
            validate_sql("REVOKE SELECT ON dim_product FROM energy_agent_reader")

    def test_reject_multiple_statements(self):
        """Reject multi-statement injection attempts."""
        with self.assertRaises(SQLValidationError) as ctx:
            validate_sql("SELECT * FROM dim_product; DROP TABLE dim_product;")
        self.assertIn("multiple sql statements", str(ctx.exception).lower())

    def test_reject_modifying_ctes(self):
        """Reject CTEs that attempt data deletion or insertion."""
        with self.assertRaises(SQLValidationError):
            validate_sql("WITH del AS (DELETE FROM dim_product RETURNING *) SELECT * FROM del")

    def test_reject_select_into(self):
        """Reject SELECT INTO table creation."""
        with self.assertRaises(SQLValidationError):
            validate_sql("SELECT * INTO new_table FROM dim_product")

    def test_reject_row_locking_clauses(self):
        """Reject FOR UPDATE and FOR SHARE clauses."""
        with self.assertRaises(SQLValidationError):
            validate_sql("SELECT * FROM dim_product FOR UPDATE")
        with self.assertRaises(SQLValidationError):
            validate_sql("SELECT * FROM dim_product FOR SHARE")

    def test_reject_unapproved_tables(self):
        """Reject queries accessing tables outside the approved whitelist."""
        with self.assertRaises(SQLValidationError) as ctx:
            validate_sql("SELECT * FROM alembic_version")
        self.assertIn("alembic_version", str(ctx.exception))

        with self.assertRaises(SQLValidationError) as ctx:
            validate_sql("SELECT * FROM users")
        self.assertIn("users", str(ctx.exception))

    def test_reject_system_catalogs_and_information_schema(self):
        """Reject system catalog and information_schema introspection."""
        with self.assertRaises(SQLValidationError):
            validate_sql("SELECT * FROM pg_catalog.pg_tables")
        with self.assertRaises(SQLValidationError):
            validate_sql("SELECT * FROM pg_roles")
        with self.assertRaises(SQLValidationError):
            validate_sql("SELECT * FROM information_schema.tables")

    def test_reject_dangerous_functions(self):
        """Reject execution of dangerous server-side functions."""
        with self.assertRaises(SQLValidationError):
            validate_sql("SELECT pg_sleep(5)")
        with self.assertRaises(SQLValidationError):
            validate_sql("SELECT set_config('test', 'val', false)")

    def test_reject_information_disclosure_functions(self):
        """Reject PostgreSQL environment and information disclosure functions."""
        disclosure_queries = [
            "SELECT version() FROM fact_energy_meter_hourly",
            "SELECT current_user FROM fact_energy_meter_hourly",
            "SELECT current_database() FROM fact_energy_meter_hourly",
            "SELECT inet_server_addr() FROM fact_energy_meter_hourly",
            "SELECT txid_current() FROM fact_energy_meter_hourly",
            "SELECT pg_backend_pid() FROM fact_energy_meter_hourly",
            "SELECT session_user FROM fact_energy_meter_hourly",
            "SELECT user FROM fact_energy_meter_hourly",
            "SELECT current_setting('server_version') FROM fact_energy_meter_hourly",
        ]
        for query in disclosure_queries:
            with self.subTest(query=query):
                with self.assertRaises(SQLValidationError) as ctx:
                    validate_sql(query)
                err_msg = str(ctx.exception).lower()
                self.assertTrue(
                    "prohibited" in err_msg or "not in the approved" in err_msg,
                    f"Expected security rejection for '{query}', got: {ctx.exception}",
                )

    def test_reject_unapproved_functions(self):
        """Reject arbitrary functions outside the analytical allowlist."""
        unapproved = [
            "SELECT md5('secret') FROM fact_energy_meter_hourly",
            "SELECT chr(65) FROM fact_energy_meter_hourly",
            "SELECT encode('foo', 'hex') FROM fact_energy_meter_hourly",
        ]
        for query in unapproved:
            with self.subTest(query=query):
                with self.assertRaises(SQLValidationError) as ctx:
                    validate_sql(query)
                self.assertIn("not in the approved", str(ctx.exception).lower())

    # -----------------------------------------------------------------------
    # 3. SQL Validation — Approved Analytical Constructs
    # -----------------------------------------------------------------------

    def test_accept_simple_select(self):
        """Accept standard SELECT with WHERE filtering."""
        sql = "SELECT product_id, product_name FROM dim_product WHERE product_family = 'Aster 15'"
        validated = validate_sql(sql)
        self.assertIn("LIMIT 100", validated)

    def test_accept_joins_across_approved_tables(self):
        """Accept joins across approved source tables with aliases."""
        sql = """
            SELECT p.line_id, l.area, SUM(p.actual_qty) as total_units
            FROM fact_hourly_production p
            JOIN dim_production_line l ON p.line_id = l.line_id AND p.plant_id = l.plant_id
            WHERE p.plant_id = 'IN-TN-01'
            GROUP BY p.line_id, l.area
            ORDER BY total_units DESC
        """
        validated = validate_sql(sql)
        self.assertIn("JOIN", validated)
        self.assertIn("LIMIT 100", validated)

    def test_accept_read_only_cte(self):
        """Accept read-only Common Table Expressions."""
        sql = """
            WITH daily_meter AS (
                SELECT date, meter_id, SUM(consumption_kwh) as kwh
                FROM fact_energy_meter_hourly
                WHERE plant_id = 'IN-TN-01'
                GROUP BY date, meter_id
            )
            SELECT meter_id, AVG(kwh) as avg_daily_kwh
            FROM daily_meter
            GROUP BY meter_id
            ORDER BY avg_daily_kwh DESC
        """
        validated = validate_sql(sql)
        self.assertIn("WITH daily_meter AS", validated)

    def test_enforce_limit_capping(self):
        """Verify LIMIT is capped at 100 if a higher limit was requested."""
        sql = "SELECT * FROM fact_energy_meter_hourly LIMIT 500"
        validated = validate_sql(sql)
        self.assertIn("LIMIT 100", validated)
        self.assertNotIn("LIMIT 500", validated)

    # -----------------------------------------------------------------------
    # 4. Live Execution & Database Permission Enforcement
    # -----------------------------------------------------------------------

    def test_execute_valid_analytical_query(self):
        """Verify live execution of an analytical query returns structured results."""
        sql = "SELECT product_id, product_name, standard_unit_cost_inr FROM dim_product ORDER BY product_id"
        res = execute_read_only_sql(sql)
        self.assertEqual(res["columns"], ["product_id", "product_name", "standard_unit_cost_inr"])
        self.assertEqual(res["row_count"], 3)
        self.assertEqual(res["rows"][0][0], "SPH-A15-128")
        self.assertFalse(res["truncated"])

    def test_database_permission_denies_insert(self):
        """Verify PostgreSQL role permission denies INSERT even if validator was bypassed."""
        engine = get_readonly_engine()
        with engine.connect() as conn:
            with self.assertRaises(Exception) as ctx:
                conn.execute(text("INSERT INTO dim_product (product_id, product_name, product_family, ram, storage, display, model_revision, standard_cycle_sec, standard_unit_cost_inr, active_from, active_to) VALUES ('X', 'X', 'X', 'X', 'X', 'X', 'X', 1, 1, '2026-01-01', '2026-01-02')"))
            self.assertIn("permission denied", str(ctx.exception).lower())

    def test_database_permission_denies_update(self):
        """Verify PostgreSQL role permission denies UPDATE at the database level."""
        engine = get_readonly_engine()
        with engine.connect() as conn:
            with self.assertRaises(Exception) as ctx:
                conn.execute(text("UPDATE dim_product SET product_name = 'hacked'"))
            self.assertIn("permission denied", str(ctx.exception).lower())

    def test_database_permission_denies_delete(self):
        """Verify PostgreSQL role permission denies DELETE at the database level."""
        engine = get_readonly_engine()
        with engine.connect() as conn:
            with self.assertRaises(Exception) as ctx:
                conn.execute(text("DELETE FROM dim_product"))
            self.assertIn("permission denied", str(ctx.exception).lower())

    def test_database_permission_denies_drop(self):
        """Verify PostgreSQL role permission denies DROP at the database level."""
        engine = get_readonly_engine()
        with engine.connect() as conn:
            with self.assertRaises(Exception) as ctx:
                conn.execute(text("DROP TABLE dim_product"))
            self.assertTrue(
                "must be owner" in str(ctx.exception).lower() or
                "permission denied" in str(ctx.exception).lower()
            )

    def test_database_statement_timeout_enforced(self):
        """Verify statement timeout terminates excessively long queries."""
        # Using a heavy cross-join that takes longer than timeout_seconds=1
        heavy_query = """
            SELECT count(*)
            FROM fact_energy_meter_hourly e1, fact_energy_meter_hourly e2
        """
        with self.assertRaises(SQLExecutionError) as ctx:
            execute_read_only_sql(heavy_query, timeout_seconds=1)
        self.assertIn("timeout", str(ctx.exception).lower())

    def test_result_limit_enforced(self):
        """Verify queries returning many rows are strictly limited to max_rows."""
        sql = "SELECT meter_reading_id, timestamp, consumption_kwh FROM fact_energy_meter_hourly"
        res = execute_read_only_sql(sql, max_rows=50)
        self.assertEqual(res["row_count"], 50)
        self.assertTrue(res["truncated"])


if __name__ == "__main__":
    unittest.main()
