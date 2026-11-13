"""
SQL Security Validator for Industrial Energy Intelligence Agent.

Enforces strict AST-level security controls on agent-generated queries:
1. Exactly one SQL statement.
2. Read-only queries only (SELECT or WITH ... SELECT).
3. Whitelisted tables only:
   - dim_product
   - dim_production_line
   - fact_energy_meter_hourly
   - fact_hourly_production
4. Prohibits all DDL, DML, multiple statements, transaction controls, and system catalogs.
5. Rejects SQL comments (-- and /* */) to prevent statement concealment.
6. Caps row limit to a maximum of 100.
7. Blocks dangerous PostgreSQL functions (pg_sleep, set_config, dblink, etc.).
"""

from typing import List, Set
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


class SQLValidationError(Exception):
    """Raised when an SQL query violates agent security constraints."""
    pass


# Approved table relations in the public schema
APPROVED_TABLES: Set[str] = {
    "dim_product",
    "dim_production_line",
    "fact_energy_meter_hourly",
    "fact_hourly_production",
}

# Forbidden keywords / AST node types
DISALLOWED_NODE_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Merge,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Into,
    exp.Lock,
)

# Prohibited dangerous functions
DANGEROUS_FUNCTIONS: Set[str] = {
    "pg_sleep",
    "pg_read_file",
    "pg_write_file",
    "pg_read_binary_file",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "dblink",
    "dblink_exec",
    "query_to_xml",
    "lo_import",
    "lo_export",
    "set_config",
    "current_setting",
}

# Approved analytical SQL functions (allowlist)
ALLOWED_SQL_FUNCTIONS: Set[str] = {
    # Aggregates
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "stddev",
    "stddev_samp",
    "stddev_pop",
    "var_samp",
    "var_pop",
    "variance",
    # Math & Numeric
    "round",
    "trunc",
    "floor",
    "ceil",
    "ceiling",
    "abs",
    "power",
    "sqrt",
    "mod",
    "sign",
    "greatest",
    "least",
    # Date / Time
    "date_trunc",
    "timestamptrunc",
    "timestamp_trunc",
    "extract",
    "date_part",
    "to_char",
    "time_to_str",
    "to_date",
    "str_to_date",
    "to_timestamp",
    "str_to_time",
    "age",
    "now",
    "current_date",
    "current_time",
    "current_timestamp",
    "currentdate",
    "currenttime",
    "currenttimestamp",
    # String / Formatting
    "lower",
    "upper",
    "trim",
    "ltrim",
    "rtrim",
    "substr",
    "substring",
    "concat",
    "replace",
    "length",
    "left",
    "right",
    "coalesce",
    "nullif",
    # Window / Ranking
    "row_number",
    "rownumber",
    "rank",
    "dense_rank",
    "denserank",
    "ntile",
    "lag",
    "lead",
    "first_value",
    "firstvalue",
    "last_value",
    "lastvalue",
    # Type conversion
    "cast",
}

# Explicitly prohibited information disclosure functions
FORBIDDEN_INFO_FUNCTIONS: Set[str] = {
    "version",
    "currentversion",
    "current_version",
    "current_user",
    "currentuser",
    "session_user",
    "sessionuser",
    "current_database",
    "currentdatabase",
    "current_schema",
    "currentschema",
    "current_schemas",
    "inet_server_addr",
    "inet_client_addr",
    "inet_server_port",
    "inet_client_port",
    "txid_current",
    "txid_current_snapshot",
    "pg_backend_pid",
    "current_setting",
}

# Forbidden system columns / pseudo-columns
FORBIDDEN_SYSTEM_COLUMNS: Set[str] = {
    "user",
    "current_user",
    "session_user",
    "current_role",
    "current_schema",
}


def validate_sql(sql: str) -> str:
    """
    Validate and sanitize an SQL query string for secure read-only execution.

    Args:
        sql: Raw SQL query string.

    Returns:
        Validated, normalized SQL string with safe LIMIT policy applied.

    Raises:
        SQLValidationError: If query violates any security policy.
    """
    if not sql or not sql.strip():
        raise SQLValidationError("Query string cannot be empty.")

    cleaned_raw = sql.strip()

    # 1. Prohibit SQL comments used for statement concealment or obfuscation
    if "--" in cleaned_raw or "/*" in cleaned_raw or "*/" in cleaned_raw:
        raise SQLValidationError("SQL comments (-- or /* */) are strictly prohibited.")

    # 2. Parse query into AST using PostgreSQL dialect
    try:
        trees: List[exp.Expression] = sqlglot.parse(cleaned_raw, read="postgres")
    except ParseError as e:
        raise SQLValidationError(f"Invalid SQL syntax: {str(e)}") from e
    except Exception as e:
        raise SQLValidationError(f"Failed to parse SQL: {str(e)}") from e

    # 3. Enforce exactly one statement
    if not trees or len(trees) == 0:
        raise SQLValidationError("No valid SQL expression found.")
    if len(trees) > 1:
        raise SQLValidationError(f"Multiple SQL statements are strictly prohibited. Found {len(trees)} statements.")

    root = trees[0]

    # 4. Enforce root expression is a SELECT or UNION query
    if not isinstance(root, (exp.Select, exp.Union)):
        op_name = type(root).__name__.replace("exp.", "")
        raise SQLValidationError(f"Statement type '{op_name}' is not allowed. Only read-only SELECT queries are permitted.")

    # 5. Check for disallowed operation types anywhere in the tree
    for node in root.walk():
        if isinstance(node, DISALLOWED_NODE_TYPES):
            node_name = type(node).__name__
            raise SQLValidationError(f"Operation '{node_name}' is strictly prohibited.")

    # 6. Specific checks for SELECT INTO and row locking
    if root.find(exp.Into):
        raise SQLValidationError("SELECT INTO is strictly prohibited.")
    if root.find(exp.Lock):
        raise SQLValidationError("Row locking clauses (FOR UPDATE / FOR SHARE) are strictly prohibited.")

    # 7. Validate Common Table Expressions (CTEs)
    cte_names: Set[str] = set()
    for cte in root.find_all(exp.CTE):
        alias_name = (cte.alias or "").lower()
        if alias_name:
            cte_names.add(alias_name)
        # Ensure CTE body is strictly a read-only query
        cte_query = cte.this
        if not isinstance(cte_query, (exp.Select, exp.Union)):
            raise SQLValidationError("All Common Table Expressions (CTEs) must be read-only SELECT queries.")

    # 8. Function Call and System Information Validation (Allowlist Enforcement)
    for func in root.find_all(exp.Func):
        # Ignore syntactic AST structures like AND/OR connectors and CASE/IF clauses
        if isinstance(func, (exp.Connector, exp.Case, exp.If)):
            continue

        raw_name = str(func.this).lower() if isinstance(func, exp.Anonymous) else ""
        sql_name = func.sql_name().lower() if hasattr(func, "sql_name") else ""
        key = getattr(func, "key", "").lower()
        cls_name = type(func).__name__.lower()

        candidate_names = {c for c in (raw_name, sql_name, key, cls_name) if c}

        # Check dangerous functions and pg_ prefixes
        for name in candidate_names:
            if name in DANGEROUS_FUNCTIONS or name.startswith("pg_"):
                display_name = raw_name or sql_name or name
                raise SQLValidationError(f"Function call '{display_name}()' is strictly prohibited.")

        # Check forbidden information disclosure functions
        if candidate_names & FORBIDDEN_INFO_FUNCTIONS:
            prohibited_func = raw_name or sql_name or next(iter(candidate_names & FORBIDDEN_INFO_FUNCTIONS))
            raise SQLValidationError(
                f"Information disclosure function '{prohibited_func}()' is strictly prohibited."
            )

        # Allowlist enforcement: at least one candidate must be in ALLOWED_SQL_FUNCTIONS
        if not (candidate_names & ALLOWED_SQL_FUNCTIONS):
            display_name = raw_name or sql_name or cls_name or "unknown"
            raise SQLValidationError(
                f"Function '{display_name}()' is not in the approved analytical function allowlist."
            )

    # Check forbidden system column / variable references
    for col in root.find_all(exp.Column):
        col_name = (col.name or "").lower()
        if col_name in FORBIDDEN_SYSTEM_COLUMNS:
            raise SQLValidationError(
                f"Reference to system variable '{col_name}' is strictly prohibited."
            )

    # 9. Table Whitelist Enforcement
    tables_found = list(root.find_all(exp.Table))
    if not tables_found and not root.find(exp.Literal):
        raise SQLValidationError("Query does not reference any valid table.")

    for tbl in tables_found:
        tbl_name = (tbl.name or "").lower()
        schema = (tbl.db or "").lower()

        # If it refers to an internal CTE defined in the query, permit it
        if tbl_name in cte_names:
            if schema and schema != "public":
                raise SQLValidationError(f"CTE reference '{tbl_name}' cannot specify external schema '{schema}'.")
            continue

        # Reject system catalog and information_schema access
        if schema and schema != "public":
            raise SQLValidationError(
                f"Access to schema '{schema}' is prohibited. Only approved 'public' schema tables are permitted."
            )

        if tbl_name not in APPROVED_TABLES:
            raise SQLValidationError(
                f"Access to table '{tbl_name}' is not permitted. "
                f"Approved tables: {', '.join(sorted(APPROVED_TABLES))}."
            )

    # 10. Enforce safe LIMIT policy (maximum 100 rows)
    existing_limit = root.args.get("limit")
    if existing_limit and existing_limit.expression:
        try:
            limit_val = int(existing_limit.expression.this)
            if limit_val > 100:
                root.args["limit"] = exp.Limit(expression=exp.Literal.number(100))
        except Exception:
            root.args["limit"] = exp.Limit(expression=exp.Literal.number(100))
    else:
        root.args["limit"] = exp.Limit(expression=exp.Literal.number(100))

    # Return normalized SQL
    return root.sql(dialect="postgres")
