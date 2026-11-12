"""
Deterministic Analytics Tool Registry for Industrial Energy Intelligence Agent.

Provides typed, validated tool definitions wrapping existing, verified backend analytics:
- 5 Energy analytics tools
- 6 Production analytics tools
- 4 Energy intensity / SEC tools
- 5 Anomaly detection tools

All calculations are mathematically deterministic, executed against Neon PostgreSQL.
No calculations are simulated or hallucinated inside the LLM.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.services.anomaly_detection import (
    detect_all_anomalies,
    detect_energy_statistical_anomalies,
    detect_low_power_factor_anomalies,
    detect_rolling_baseline_anomalies,
    detect_zero_production_standby_anomalies,
)
from app.services.energy_analytics import (
    get_energy_by_area,
    get_energy_by_meter,
    get_energy_daily_trend,
    get_energy_summary,
    get_power_factor_summary,
)
from app.services.energy_intensity import (
    get_factory_energy_analytics,
    get_process_energy_analytics,
    get_product_process_energy,
    get_zero_production_period_energy,
)
from app.services.production_analytics import (
    get_downtime_by_reason,
    get_production_by_line,
    get_production_by_product,
    get_production_by_shift,
    get_production_daily_trend,
    get_production_summary,
)
from app.services.agent.sql_tool import (
    ReadOnlySQLQueryInput,
    execute_read_only_sql,
)

try:
    from langchain_core.tools import StructuredTool
    _HAS_LANGCHAIN = True
except ImportError:
    StructuredTool = None
    _HAS_LANGCHAIN = False


# ---------------------------------------------------------------------------
# Base & Common Input Schemas
# ---------------------------------------------------------------------------

class BaseDateRangeInput(BaseModel):
    """Common date range filter arguments."""
    plant_id: Optional[str] = Field(None, description="Optional plant filter: 'IN-TN-01' or 'IN-KA-01'")
    start_date: Optional[date] = Field(None, description="Optional start date (inclusive, YYYY-MM-DD)")
    end_date: Optional[date] = Field(None, description="Optional end date (inclusive, YYYY-MM-DD)")

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError(f"start_date ({self.start_date}) cannot be after end_date ({self.end_date})")
        return self


class BaseTimeRangeInput(BaseModel):
    """Common timestamp range filter arguments for telemetry-level queries."""
    plant_id: Optional[str] = Field(None, description="Optional plant filter: 'IN-TN-01' or 'IN-KA-01'")
    start_time: Optional[datetime] = Field(None, description="Optional start datetime (YYYY-MM-DDTHH:MM:SS, timezone-naive)")
    end_time: Optional[datetime] = Field(None, description="Optional end datetime (YYYY-MM-DDTHH:MM:SS, timezone-naive)")

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError(f"start_time ({self.start_time}) cannot be after end_time ({self.end_time})")
        return self


# ---------------------------------------------------------------------------
# Specific Tool Input Schemas
# ---------------------------------------------------------------------------

class EnergySummaryInput(BaseDateRangeInput):
    pass


class EnergyByMeterInput(BaseDateRangeInput):
    pass


class EnergyByAreaInput(BaseDateRangeInput):
    pass


class EnergyDailyTrendInput(BaseDateRangeInput):
    pass


class PowerFactorSummaryInput(BaseDateRangeInput):
    low_pf_threshold: Optional[Decimal] = Field(
        default=Decimal("0.9200"),
        description="Threshold below which power factor readings are flagged (default 0.92)",
    )


class ProductionSummaryInput(BaseDateRangeInput):
    line_id: Optional[str] = Field(None, description="Optional line filter: 'SMT-L1', 'SMT-L2', 'FAL-L1', 'FAL-L2'")
    product_id: Optional[str] = Field(None, description="Optional product SKU filter: 'PROD-A15-128', 'PROD-APRO-256', 'PROD-APRO-512'")
    shift_id: Optional[str] = Field(None, description="Optional manufacturing shift filter: 'A', 'B', or 'C'")


class ProductionByLineInput(BaseDateRangeInput):
    pass


class ProductionByProductInput(BaseDateRangeInput):
    line_id: Optional[str] = Field(None, description="Optional line filter: 'SMT-L1', 'SMT-L2', 'FAL-L1', 'FAL-L2'")


class ProductionByShiftInput(BaseDateRangeInput):
    pass


class DowntimeByReasonInput(BaseDateRangeInput):
    line_id: Optional[str] = Field(None, description="Optional line filter: 'SMT-L1', 'SMT-L2', 'FAL-L1', 'FAL-L2'")


class ProductionDailyTrendInput(BaseDateRangeInput):
    pass


class ProcessEnergyIntensityInput(BaseDateRangeInput):
    pass


class FactoryEnergyIntensityInput(BaseDateRangeInput):
    pass


class ProductProcessEnergyInput(BaseDateRangeInput):
    pass


class ZeroProductionPeriodEnergyInput(BaseDateRangeInput):
    pass


class StatisticalAnomaliesInput(BaseTimeRangeInput):
    meter_id: Optional[str] = Field(None, description="Optional meter filter: 'MTR-SMT', 'MTR-FAL', 'MTR-HVAC', 'MTR-COMPRESSOR', 'MTR-CHILLER'")
    threshold_z: float = Field(default=3.0, ge=1.0, le=10.0, description="Z-score deviation threshold (default 3.0)")
    min_observations: int = Field(default=10, ge=2, description="Minimum sample size required per group (default 10)")


class RollingBaselineAnomaliesInput(BaseTimeRangeInput):
    meter_id: Optional[str] = Field(None, description="Optional meter filter")
    window_size: int = Field(default=24, ge=2, le=720, description="Rolling historical window size in hours (default 24)")
    min_observations: int = Field(default=12, ge=2, description="Minimum observations in rolling window (default 12)")
    threshold_z: float = Field(default=3.0, ge=1.0, le=10.0, description="Z-score deviation threshold (default 3.0)")


class LowPowerFactorAnomaliesInput(BaseTimeRangeInput):
    meter_id: Optional[str] = Field(None, description="Optional meter filter")
    threshold: Decimal = Field(default=Decimal("0.90"), description="Power factor compliance cutoff (default 0.90)")


class ZeroProductionStandbyAnomaliesInput(BaseTimeRangeInput):
    line_id: Optional[str] = Field(None, description="Optional line filter: 'SMT-L1', 'SMT-L2', 'FAL-L1', 'FAL-L2'")


class UnifiedAnomalyDetectionInput(BaseTimeRangeInput):
    z_threshold: float = Field(default=3.0, description="Z-score threshold for statistical anomalies (default 3.0)")
    rolling_window_hours: int = Field(default=24, description="Window size for rolling baseline (default 24)")
    pf_threshold: Decimal = Field(default=Decimal("0.90"), description="Power factor threshold (default 0.90)")


# ---------------------------------------------------------------------------
# Tool Class Definition
# ---------------------------------------------------------------------------

@dataclass
class DeterministicTool:
    """Encapsulates a verified analytical tool with schemas, metadata, and runner."""
    name: str
    description: str
    category: str
    args_schema: Type[BaseModel]
    func: Callable[..., Any]

    def run(self, session: Session, **kwargs: Any) -> Any:
        """Validate input arguments against schema and execute the underlying service function."""
        # Validate through Pydantic schema
        validated_args = self.args_schema(**kwargs)
        clean_kwargs = validated_args.model_dump()
        return self.func(session, **clean_kwargs)

    def to_langchain_tool(self) -> Optional[Any]:
        """Convert to a LangChain StructuredTool instance if langchain-core is installed."""
        if not _HAS_LANGCHAIN:
            return None

        # Build execution wrapper that receives explicit session from external injector or fallback factory
        def _wrapper(**kwargs: Any) -> Any:
            with get_session_factory()() as session:
                return self.run(session=session, **kwargs)

        return StructuredTool.from_function(
            func=_wrapper,
            name=self.name,
            description=self.description,
            args_schema=self.args_schema,
        )


# ---------------------------------------------------------------------------
# Tool Definitions Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, DeterministicTool] = {}


def register_tool(
    name: str,
    description: str,
    category: str,
    args_schema: Type[BaseModel],
    func: Callable[..., Any],
) -> DeterministicTool:
    """Register a deterministic tool into the central registry."""
    tool = DeterministicTool(
        name=name,
        description=description.strip(),
        category=category,
        args_schema=args_schema,
        func=func,
    )
    TOOL_REGISTRY[name] = tool
    return tool


# ===========================================================================
# 1. Energy Analytics Tools
# ===========================================================================

register_tool(
    name="energy_summary",
    description=(
        "Retrieve aggregated factory energy consumption metrics including total kWh, "
        "utility electricity cost (INR), CO2e emissions (kg), average power factor, distinct hours, "
        "and peak hourly consumption reading. Use when asked for overall energy usage or costs."
    ),
    category="energy",
    args_schema=EnergySummaryInput,
    func=get_energy_summary,
)

register_tool(
    name="energy_by_meter",
    description=(
        "Retrieve energy consumption breakdown ranked by individual electrical meter (MTR-HVAC, "
        "MTR-SMT, MTR-FAL, MTR-COMPRESSOR, MTR-CHILLER). Provides total kWh, cost, emissions, "
        "peak draw, and percentage of total plant energy. Use when analyzing meter-level distribution."
    ),
    category="energy",
    args_schema=EnergyByMeterInput,
    func=get_energy_by_meter,
)

register_tool(
    name="energy_by_area",
    description=(
        "Retrieve energy consumption grouped by operational factory area (HVAC, SMT, FAL, Utilities). "
        "Shows total kWh, electricity cost, emissions, and area percentage of plant consumption."
    ),
    category="energy",
    args_schema=EnergyByAreaInput,
    func=get_energy_by_area,
)

register_tool(
    name="energy_daily_trend",
    description=(
        "Retrieve daily time series of factory energy consumption, electricity cost, CO2e emissions, "
        "average power factor, and peak hourly demand. Use when asked about daily energy trends over time."
    ),
    category="energy",
    args_schema=EnergyDailyTrendInput,
    func=get_energy_daily_trend,
)

register_tool(
    name="power_factor_summary",
    description=(
        "Analyze electrical power factor distribution, minimum/maximum readings, and identify readings "
        "falling below configured detection cutoff (default 0.92). Note: Low readings reflect configured "
        "technical benchmarks; billing penalties require site-specific utility contracts."
    ),
    category="energy",
    args_schema=PowerFactorSummaryInput,
    func=get_power_factor_summary,
)


# ===========================================================================
# 2. Production Analytics Tools
# ===========================================================================

register_tool(
    name="production_summary",
    description=(
        "Retrieve factory manufacturing output metrics including target quantity, actual production, "
        "good units, reject count, rework count, and total stoppage downtime minutes. Note: Standard OEE "
        "is unavailable because planned production hours are not defined in source telemetry."
    ),
    category="production",
    args_schema=ProductionSummaryInput,
    func=get_production_summary,
)

register_tool(
    name="production_by_line",
    description=(
        "Retrieve manufacturing performance grouped by production line (SMT-L1, SMT-L2, FAL-L1, FAL-L2). "
        "Reports actual vs target output, yield rate, reject rate, and operating downtime."
    ),
    category="production",
    args_schema=ProductionByLineInput,
    func=get_production_by_line,
)

register_tool(
    name="production_by_product",
    description=(
        "Retrieve production output and quality metrics grouped by product SKU (Aster 15 128GB, "
        "Aster Pro 256GB, Aster Pro 512GB). Reports units manufactured, good count, and quality yield."
    ),
    category="production",
    args_schema=ProductionByProductInput,
    func=get_production_by_product,
)

register_tool(
    name="production_by_shift",
    description=(
        "Retrieve manufacturing performance grouped by work shift (Shift A: Morning, Shift B: Evening, "
        "Shift C: Night). Reports target vs actual output, quality rates, and downtime."
    ),
    category="production",
    args_schema=ProductionByShiftInput,
    func=get_production_by_shift,
)

register_tool(
    name="downtime_by_reason",
    description=(
        "Retrieve equipment downtime breakdown ranked by operational reason code (e.g. Component Shortage, "
        "Setup and Changeover, Unplanned Maintenance). Reports stoppage duration and zero-output events."
    ),
    category="production",
    args_schema=DowntimeByReasonInput,
    func=get_downtime_by_reason,
)

register_tool(
    name="production_daily_trend",
    description=(
        "Retrieve daily time series of factory manufacturing output, target adherence, good units, "
        "reject rates, and downtime minutes over time."
    ),
    category="production",
    args_schema=ProductionDailyTrendInput,
    func=get_production_daily_trend,
)


# ===========================================================================
# 3. Energy Intensity & SEC Tools
# ===========================================================================

register_tool(
    name="process_energy_intensity",
    description=(
        "Calculate Specific Energy Consumption (SEC in kWh/unit) for direct manufacturing processes. "
        "Strictly maps SMT lines to MTR-SMT and FAL lines to MTR-FAL. Returns SEC per board for SMT "
        "and SEC per phone for Final Assembly. Safely guards zero-output hours."
    ),
    category="energy_intensity",
    args_schema=ProcessEnergyIntensityInput,
    func=get_process_energy_analytics,
)

register_tool(
    name="factory_energy_intensity",
    description=(
        "Calculate plant-wide Factory SEC (Total plant kWh across all 5 meters divided by Final Assembly "
        "finished goods output). Reports facility infrastructure utilities (HVAC, Compressor, Chiller) "
        "separately to preserve technical boundaries."
    ),
    category="energy_intensity",
    args_schema=FactoryEnergyIntensityInput,
    func=get_factory_energy_analytics,
)

register_tool(
    name="product_process_energy",
    description=(
        "Calculate direct process energy consumed per product SKU using exact timestamp, plant, and "
        "process meter matching. Facility utilities (HVAC, Chiller, Compressor) are explicitly excluded."
    ),
    category="energy_intensity",
    args_schema=ProductProcessEnergyInput,
    func=get_product_process_energy,
)

register_tool(
    name="zero_production_period_energy",
    description=(
        "Analyze energy consumed by dedicated process meters during hours where line output was 0. "
        "Classified strictly as standby/idle equipment consumption during downtime events, not automatically "
        "avoidable waste."
    ),
    category="energy_intensity",
    args_schema=ZeroProductionPeriodEnergyInput,
    func=get_zero_production_period_energy,
)


# ===========================================================================
# 4. Deterministic Anomaly Detection Tools
# ===========================================================================

register_tool(
    name="statistical_energy_anomalies",
    description=(
        "Detect hourly energy consumption spikes and drops using sample Z-score relative to each meter's "
        "historical baseline. Handles zero variance safely and never compares unrelated meters or plants."
    ),
    category="anomalies",
    args_schema=StatisticalAnomaliesInput,
    func=detect_energy_statistical_anomalies,
)

register_tool(
    name="rolling_baseline_anomalies",
    description=(
        "Detect dynamic anomalies using a rolling historical baseline window (default 24h). Enforces strict "
        "exclusion of the current observation from its own baseline to prevent statistical masking."
    ),
    category="anomalies",
    args_schema=RollingBaselineAnomaliesInput,
    func=detect_rolling_baseline_anomalies,
)

register_tool(
    name="low_power_factor_anomalies",
    description=(
        "Identify meter readings where measured power factor falls below the configured 0.90 threshold. "
        "Reports deficit magnitude and timestamps without asserting unverified financial billing penalties."
    ),
    category="anomalies",
    args_schema=LowPowerFactorAnomaliesInput,
    func=detect_low_power_factor_anomalies,
)

register_tool(
    name="zero_production_standby_anomalies",
    description=(
        "Detect process meter standby power drawn during line stoppages (actual_qty = 0). Tracks standby "
        "kWh and stoppage reasons. Preserves facility utility segregation."
    ),
    category="anomalies",
    args_schema=ZeroProductionStandbyAnomaliesInput,
    func=detect_zero_production_standby_anomalies,
)

register_tool(
    name="unified_anomaly_detection",
    description=(
        "Run the complete unified anomaly detection suite combining statistical Z-score, rolling baseline, "
        "power factor, and standby energy surveillance across plants and meters."
    ),
    category="anomalies",
    args_schema=UnifiedAnomalyDetectionInput,
    func=detect_all_anomalies,
)


# ===========================================================================
# 5. Read-Only SQL Tool
# ===========================================================================

def _run_sql_query_tool(session: Optional[Session] = None, query: str = "") -> Dict[str, Any]:
    """Execute validated read-only SQL query against dedicated reader role."""
    return execute_read_only_sql(query=query)


register_tool(
    name="read_only_sql_query",
    description=(
        "Execute a single validated, read-only SQL SELECT query against the 4 approved factory tables "
        "(dim_product, dim_production_line, fact_energy_meter_hourly, fact_hourly_production). "
        "Enforces a 5-second database execution timeout and caps output at a maximum of 100 rows. "
        "Strictly rejects data modification (INSERT/UPDATE/DELETE), DDL, multiple statements, and system catalogs."
    ),
    category="sql",
    args_schema=ReadOnlySQLQueryInput,
    func=_run_sql_query_tool,
)


# ---------------------------------------------------------------------------
# Registry Access Functions
# ---------------------------------------------------------------------------

def get_all_tools() -> Dict[str, DeterministicTool]:
    """Return dictionary of all registered deterministic tools."""
    return TOOL_REGISTRY


def get_tool(name: str) -> Optional[DeterministicTool]:
    """Retrieve a tool by name."""
    return TOOL_REGISTRY.get(name)


def execute_tool(name: str, args: Dict[str, Any], session: Optional[Session] = None) -> Any:
    """
    Execute a registered tool by name with provided arguments.

    If session is provided, it is used. Otherwise, a fresh session is acquired
    from the session factory and closed cleanly in a finally block.
    """
    tool = get_tool(name)
    if not tool:
        raise ValueError(f"Tool '{name}' is not registered. Available tools: {list(TOOL_REGISTRY.keys())}")

    if session is not None:
        return tool.run(session=session, **args)

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("Database engine/session factory is not available.")

    with factory() as sess:
        return tool.run(session=sess, **args)


def get_tool_descriptions() -> str:
    """Format human-readable catalog of registered tools for LLM system prompt injection."""
    lines = []
    for tool in TOOL_REGISTRY.values():
        lines.append(f"- **{tool.name}** ({tool.category}): {tool.description}")
    return "\n".join(lines)

