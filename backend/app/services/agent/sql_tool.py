"""
Hardened Read-Only SQL Tool for Industrial Energy Intelligence Agent.

Executes validated analytical queries against the dedicated Neon reader role:
- Validates queries via AST-based sql_validator.
- Uses get_readonly_engine() (never owner engine).
- Enforces 5-second database statement timeout.
- Enforces 100-row maximum result limit.
- Preserves Decimal precision and timezone-naive ISO date/datetime values.
- Sanitizes all database errors to prevent credential or topology leakage.
"""

from datetime import date, datetime
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import get_readonly_engine
from app.services.agent.sql_validator import SQLValidationError, validate_sql

logger = logging.getLogger(__name__)


class SQLExecutionError(Exception):
    """Raised when query execution fails or is rejected by database policies."""
    pass


class ReadOnlySQLQueryInput(BaseModel):
    """Input argument schema for read-only SQL tool."""
    query: str = Field(
        ...,
        description=(
            "A single read-only PostgreSQL SELECT query against approved tables "
            "(dim_product, dim_production_line, fact_energy_meter_hourly, fact_hourly_production). "
            "Maximum 100 rows returned with a 5-second execution timeout."
        ),
    )


def _serialize_value(val: Any) -> Any:
    """Format row values preserving Decimal precision and ISO dates without inventing timezones."""
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, Decimal):
        # Keep as Decimal or float for JSON serialization
        return float(val) if val.is_finite() else str(val)
    return val


def execute_read_only_sql(
    query: str,
    timeout_seconds: int = 5,
    max_rows: int = 100,
) -> Dict[str, Any]:
    """
    Validate and execute a read-only SQL query against the dedicated database reader role.

    Args:
        query: Raw SQL query string.
        timeout_seconds: Statement timeout in seconds (default 5).
        max_rows: Maximum rows to return (default 100).

    Returns:
        Dictionary with columns, rows, row_count, truncated flag, and executed SQL.

    Raises:
        SQLValidationError: If query violates application-level AST security policies.
        SQLExecutionError: If query execution fails at the database level.
    """
    # 1. Application-level AST validation and LIMIT policy
    validated_sql = validate_sql(query)

    # 2. Acquire dedicated reader engine (enforces reader connection, never owner)
    engine = get_readonly_engine()

    timeout_ms = max(1, min(timeout_seconds, 10)) * 1000

    try:
        with engine.connect() as conn:
            # 3. Enforce session-level statement timeout
            conn.execute(text(f"SET statement_timeout = '{timeout_ms}';"))

            # 4. Enforce session-level read-only transaction state
            conn.execute(text("SET default_transaction_read_only = 'on';"))

            # 5. Execute query
            cursor = conn.execute(text(validated_sql))
            columns = list(cursor.keys())

            # Fetch up to max_rows + 1 to detect truncation
            raw_rows = cursor.fetchmany(max_rows + 1)

            truncated = len(raw_rows) > max_rows
            final_rows = raw_rows[:max_rows]

            serialized_rows: List[List[Any]] = [
                [_serialize_value(val) for val in row]
                for row in final_rows
            ]

            return {
                "columns": columns,
                "rows": serialized_rows,
                "row_count": len(serialized_rows),
                "truncated": truncated,
                "query": validated_sql,
            }

    except SQLValidationError:
        raise
    except Exception as e:
        err_msg = str(e)
        logger.warning("Read-only SQL query execution failed: %s", err_msg)

        # Sanitize error message to avoid credential or topology disclosure
        sanitized_msg = err_msg
        if "password" in sanitized_msg.lower() or "@" in sanitized_msg:
            sanitized_msg = "Database query failed due to a connection or authentication error."
        elif "canceling statement due to statement timeout" in sanitized_msg.lower():
            sanitized_msg = f"Query exceeded the {timeout_seconds}-second execution timeout limit."
        elif "permission denied" in sanitized_msg.lower():
            sanitized_msg = "Database permission denied: the requested operation or table is restricted."
        elif "must be owner of" in sanitized_msg.lower():
            sanitized_msg = "Database permission denied: DDL and schema modifications are not permitted."

        raise SQLExecutionError(f"SQL execution error: {sanitized_msg}") from e
