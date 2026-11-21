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
from datetime import date as dt_date, datetime as dt_datetime, date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.config import DEFAULT_POWER_FACTOR_THRESHOLD
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
    get_energy_intensity_trends,
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
        default=DEFAULT_POWER_FACTOR_THRESHOLD,
        description="Application monitoring threshold below which power factor readings are flagged (default 0.90)",
    )


class ProductionSummaryInput(BaseDateRangeInput):
    line_id: Optional[str] = Field(None, description="Optional line filter: 'SMT-L1', 'SMT-L2', 'FAL-L1', 'FAL-L2'")
    product_id: Optional[str] = Field(None, description="Optional product SKU filter: 'SPH-A15-128', 'SPH-A15-256', 'SPH-PRO-256'")
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
    line_id: Optional[str] = Field(None, description="Optional line filter (note: factory-wide intensity requires plant scope)")
    product_id: Optional[str] = Field(None, description="Optional product SKU filter")
    shift_id: Optional[str] = Field(None, description="Optional shift filter")


class EnergyIntensityTrendsInput(BaseDateRangeInput):
    grain: Optional[str] = Field("daily", description="Time aggregation grain: 'daily' or 'monthly'")
    group_by_plant: Optional[bool] = Field(False, description="When true, breaks out each plant separately in addition to combined total")


class ProductProcessEnergyInput(BaseDateRangeInput):
    pass


class ZeroProductionPeriodEnergyInput(BaseDateRangeInput):
    pass


class StatisticalAnomaliesInput(BaseTimeRangeInput):
    meter_id: Optional[str] = Field(None, description="Optional meter filter: 'MTR-SMT', 'MTR-FAL', 'MTR-HVAC', 'MTR-COMPRESSOR', 'MTR-CHILLER'")
    lookback_days: int = Field(default=30, ge=1, le=90, description="Historical baseline lookback in days (default 30, range 1-90)")
    threshold_z: float = Field(default=3.0, ge=1.0, le=10.0, description="Z-score deviation threshold (default 3.0)")
    min_observations: int = Field(default=10, ge=2, description="Minimum sample size required per group (default 10)")
    limit: Optional[int] = Field(None, ge=1, le=5000, description="Optional maximum number of anomalies to return")


class RollingBaselineAnomaliesInput(BaseTimeRangeInput):
    meter_id: Optional[str] = Field(None, description="Optional meter filter")
    window_size: int = Field(default=24, ge=2, le=720, description="Elapsed-time rolling historical window in hours (default 24)")
    min_observations: int = Field(default=12, ge=2, description="Minimum observations in rolling window (default 12)")
    threshold_z: float = Field(default=3.0, ge=1.0, le=10.0, description="Z-score deviation threshold (default 3.0)")
    limit: Optional[int] = Field(None, ge=1, le=5000, description="Optional maximum number of anomalies to return")


class LowPowerFactorAnomaliesInput(BaseTimeRangeInput):
    meter_id: Optional[str] = Field(None, description="Optional meter filter")
    threshold: Decimal = Field(default=Decimal("0.90"), description="Application power factor monitoring threshold (default 0.90)")
    limit: Optional[int] = Field(None, ge=1, le=5000, description="Optional maximum number of anomalies to return")


class ZeroProductionStandbyAnomaliesInput(BaseTimeRangeInput):
    line_id: Optional[str] = Field(None, description="Optional line filter: 'SMT-L1', 'SMT-L2', 'FAL-L1', 'FAL-L2'")
    limit: Optional[int] = Field(None, ge=1, le=5000, description="Optional maximum number of anomalies to return")


class UnifiedAnomalyDetectionInput(BaseTimeRangeInput):
    meter_id: Optional[str] = Field(None, description="Optional meter filter")
    z_threshold: float = Field(default=3.0, description="Z-score threshold for statistical anomalies (default 3.0)")
    lookback_days: int = Field(default=30, ge=1, le=90, description="Historical baseline lookback in days for statistical anomalies (default 30, range 1-90)")
    rolling_window_hours: int = Field(default=24, ge=2, le=720, description="Elapsed-time window for rolling baseline (default 24)")
    pf_threshold: Decimal = Field(default=Decimal("0.90"), description="Power factor threshold (default 0.90)")
    limit: Optional[int] = Field(None, ge=1, le=5000, description="Optional maximum number of anomalies to return")


class ExplainOperatingStoppageInput(BaseModel):
    """Input parameters for explain_operating_stoppage tool."""
    plant_id: Optional[str] = Field(None, description="Optional plant filter: 'IN-TN-01' or 'IN-KA-01'")
    line_id: Optional[str] = Field(None, description="Production line identifier, e.g. 'FAL-L2' or 'SMT-L1'")
    date: Optional[dt_date] = Field(None, description="Date of the stoppage episode (YYYY-MM-DD)")
    hour: Optional[int] = Field(None, ge=0, le=23, description="Hour of the stoppage episode (0-23)")
    episode_id: Optional[str] = Field(None, description="Optional explicit episode ID, e.g. 'STP-IN-KA-01-FAL-L2-2026110402'")


class ExplainInterventionAssessmentInput(BaseModel):
    """Input parameters for explain_intervention_assessment tool."""
    action_id: Optional[str] = Field(None, description="Corrective action identifier, e.g. 'ACT-...'")
    plan_id: Optional[str] = Field(None, description="Measurement plan identifier, e.g. 'PLAN-...'")


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
        "dataset-calculated cost (INR), estimated CO2e emissions (kg), average power factor, distinct hours, "
        "and peak hourly consumption. Cost is a deterministic analytics result, not a verified utility bill; "
        "the power-factor aggregate may be null when no readings are available. "
        "Use when asked for overall energy usage or costs."
    ),
    category="energy",
    args_schema=EnergySummaryInput,
    func=get_energy_summary,
)

register_tool(
    name="energy_by_meter",
    description=(
        "Retrieve energy consumption breakdown ranked by individual electrical meter (MTR-HVAC, "
        "MTR-SMT, MTR-FAL, MTR-COMPRESSOR, MTR-CHILLER). Provides total kWh, dataset-calculated cost, "
        "estimated emissions, peak hourly consumption, and percentage of returned plant energy. "
        "Cost is not a verified utility bill. Use when analyzing meter-level distribution."
    ),
    category="energy",
    args_schema=EnergyByMeterInput,
    func=get_energy_by_meter,
)

register_tool(
    name="energy_by_area",
    description=(
        "Retrieve energy consumption grouped by operational factory area (HVAC, SMT, FAL, Utilities). "
        "Shows total kWh, dataset-calculated cost, estimated emissions, and area share of returned energy. "
        "Cost is not a verified utility bill."
    ),
    category="energy",
    args_schema=EnergyByAreaInput,
    func=get_energy_by_area,
)

register_tool(
    name="energy_daily_trend",
    description=(
        "Retrieve daily time series of factory energy consumption, dataset-calculated cost, estimated CO2e, "
        "average power factor, and peak hourly energy consumption (kWh). Cost is not a verified bill, and "
        "peak hourly energy consumption is not a demand measurement. "
        "Use when asked about daily energy trends over time."
    ),
    category="energy",
    args_schema=EnergyDailyTrendInput,
    func=get_energy_daily_trend,
)

register_tool(
    name="power_factor_summary",
    description=(
        "Analyze electrical power factor distribution, minimum/maximum readings, and readings falling below "
        "the configured detection cutoff (default 0.90). Aggregate averages use energy-weighted averaging "
        "where applicable; summary metrics may be null when no readings are available. Low readings reflect "
        "an application monitoring threshold, not a billing penalty; billing requires site-specific utility contracts."
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
        "Aster 15 256GB, Aster Pro 256GB). Reports units manufactured, good count, and quality yield."
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
        "Calculate plant-wide energy intensity per good finished unit (Total eligible plant kWh across all 5 meters, "
        "estimated cost in INR, and CO2e emissions divided by Final Assembly good output). Reports telemetry coverage "
        "(expected vs matched hours), production quality context (yield, rejects, downtime), and facility "
        "infrastructure utilities (HVAC, Compressor, Chiller) separately to preserve technical boundaries."
    ),
    category="energy_intensity",
    args_schema=FactoryEnergyIntensityInput,
    func=get_factory_energy_analytics,
)

register_tool(
    name="energy_intensity_trends",
    description=(
        "Calculate time-series trends of electricity intensity (kWh/good unit), cost intensity (₹/good unit), "
        "and emissions intensity (kg CO2e/good unit) grouped by day or month. Strictly sums numerators and "
        "denominators within each bucket before dividing (ratio of sums). Delivers coverage and production context."
    ),
    category="energy_intensity",
    args_schema=EnergyIntensityTrendsInput,
    func=get_energy_intensity_trends,
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
        "Analyze positive energy consumption from the corresponding dedicated process meter during matched "
        "zero-output intervals (SMT with MTR-SMT, FAL with MTR-FAL). This finding does not include facility "
        "utility consumption, which must be queried independently. It is observed zero-output consumption, "
        "not automatically avoidable waste or an expected-energy baseline."
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
        "Flag hourly energy readings that are statistical outliers relative to a strictly segregated "
        "historical baseline window (default 30 days) partitioned per meter and plant. Evaluates deterministic "
        "baseline qualification (QUALIFIED, INCONCLUSIVE, NOT_QUALIFIED) before computing Z-scores. Untrusted baselines "
        "(NOT_QUALIFIED) are excluded from anomaly evaluation, preventing invalid comparisons. "
        "Inconclusive baselines attach explicit confidence limitations. Distinguishes verified anomalies from untrusted or missing baseline data."
    ),
    category="anomalies",
    args_schema=StatisticalAnomaliesInput,
    func=detect_energy_statistical_anomalies,
)

register_tool(
    name="rolling_baseline_anomalies",
    description=(
        "Detect dynamic anomalies using an elapsed-time rolling historical baseline window (default 24h). "
        "Excludes the current observation from its own baseline to prevent statistical masking."
    ),
    category="anomalies",
    args_schema=RollingBaselineAnomaliesInput,
    func=detect_rolling_baseline_anomalies,
)

register_tool(
    name="low_power_factor_anomalies",
    description=(
        "Identify meter readings where measured power factor falls below the configured application threshold "
        "(default 0.90). Reports deficit magnitude and timestamps without asserting unverified financial billing penalties."
    ),
    category="anomalies",
    args_schema=LowPowerFactorAnomaliesInput,
    func=detect_low_power_factor_anomalies,
)

register_tool(
    name="zero_production_standby_anomalies",
    description=(
        "Report positive process-meter energy (kWh) during matched zero-output intervals (actual_qty = 0), "
        "with reported downtime and reason where available. Facility utility consumption is queried separately "
        "and is not part of this finding. This is not proof of avoidable waste and has no validated expected-energy baseline."
    ),
    category="anomalies",
    args_schema=ZeroProductionStandbyAnomaliesInput,
    func=detect_zero_production_standby_anomalies,
)

register_tool(
    name="unified_anomaly_detection",
    description=(
        "Run the complete unified anomaly detection suite combining statistical Z-score (with deterministic baseline "
        "qualification), rolling baseline, power factor, and zero-output energy findings. Untrusted statistical baselines "
        "are disqualified from comparison. Aggregate counts sum detector findings."
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


# ===========================================================================
# 6. Operating Context & Stoppage Analysis Tools
# ===========================================================================

def _explain_operating_stoppage_tool(
    session: Session,
    plant_id: Optional[str] = None,
    line_id: Optional[str] = None,
    date: Optional[date] = None,
    hour: Optional[int] = None,
    episode_id: Optional[str] = None,
) -> Dict[str, Any]:
    from app.services.operating_context import (
        detect_stoppage_episodes,
        get_operating_context_observations,
        get_stoppage_episode_detail,
    )

    if episode_id:
        detail = get_stoppage_episode_detail(session=session, episode_id=episode_id)
        if detail:
            kwh_rate = round(detail.episode.process_kwh / detail.episode.observed_duration_hours, 4) if (detail.episode.process_kwh and detail.episode.observed_duration_hours > 0) else None
            return {
                "episode_id": detail.episode.episode_id,
                "plant_id": detail.episode.plant_id,
                "line_id": detail.episode.line_id,
                "process": detail.episode.process,
                "interval_window": detail.episode.interval_window,
                "first_interval": detail.episode.first_interval.isoformat(),
                "last_interval": detail.episode.last_interval.isoformat(),
                "observed_duration_hours": detail.episode.observed_duration_hours,
                "stoppage_output": {
                    "target_qty_lost": detail.episode.target_qty_lost,
                    "target_shortfall": detail.episode.target_shortfall,
                    "target_shortfall_label": "Target shortfall during observed hours",
                    "actual_qty": detail.episode.actual_qty,
                    "good_qty": detail.episode.good_qty,
                    "recorded_downtime_minutes": detail.episode.recorded_downtime_minutes,
                    "downtime_reasons": detail.episode.downtime_reasons,
                    "downtime_reasons_display": detail.episode.downtime_reasons_display,
                },
                "stoppage_energy": {
                    "process_kwh": detail.episode.process_kwh,
                    "process_electricity_label": detail.episode.process_electricity_label,
                    "kwh_per_hour": kwh_rate,
                    "process_cost_inr": detail.episode.process_cost_inr,
                    "cost_label": detail.episode.cost_label,
                    "energy_coverage_pct": detail.episode.energy_coverage_pct,
                },
                "prior_productive_interval": detail.episode.prior_productive_interval.model_dump() if detail.episode.prior_productive_interval else None,
                "restart_behavior": detail.episode.next_restart_interval.model_dump() if detail.episode.next_restart_interval else None,
                "machine_context": {
                    "machine_states": detail.episode.machine_states,
                    "alarm_codes": detail.episode.alarm_codes,
                    "has_machine_telemetry": detail.episode.has_machine_telemetry,
                },
                "historical_comparison": detail.similar_periods.model_dump(),
                "actionable_investigation": detail.actionable_investigation.model_dump() if detail.actionable_investigation else None,
                "source_provenance": {
                    "source_record_ids": detail.episode.source_record_ids,
                    "source_revision_ids": detail.episode.source_revision_ids,
                },
            }

    # If episode_id not provided, look up by line_id, plant_id, date, hour
    obs = get_operating_context_observations(
        session=session,
        plant_id=plant_id,
        line_id=line_id,
        start_date=date,
        end_date=date,
        limit=1000,
    )
    episodes = detect_stoppage_episodes(obs, min_duration_hours=1)

    matched_ep = None
    if hour is not None:
        for ep in episodes:
            if ep.first_interval.hour <= hour <= ep.last_interval.hour:
                matched_ep = ep
                break
    elif episodes:
        matched_ep = episodes[0]

    if matched_ep:
        return _explain_operating_stoppage_tool(
            session=session,
            episode_id=matched_ep.episode_id,
        )

    return {
        "status": "NO_STOPPAGE_FOUND",
        "message": f"No stoppage episode found matching plant={plant_id}, line={line_id}, date={date}, hour={hour}.",
        "searched_scope": {
            "plant_id": plant_id,
            "line_id": line_id,
            "date": str(date) if date else None,
            "hour": hour,
        },
    }


register_tool(
    name="explain_operating_stoppage",
    description=(
        "Explain an operational stoppage episode on a manufacturing line: returns lost target output, "
        "observed zero production, process electricity consumed during the stoppage, dataset-derived cost, "
        "machine alarms/states, restart behavior in the following hour, descriptive comparison against "
        "similar historical stoppages on that line, and linked source record/revision IDs."
    ),
    category="operating_context",
    args_schema=ExplainOperatingStoppageInput,
    func=_explain_operating_stoppage_tool,
)


def _explain_intervention_assessment_tool(
    session: Session,
    action_id: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> Dict[str, Any]:
    from app.services.intervention_service import (
        get_corrective_action,
        get_measurement_plan_for_action,
        evaluate_and_record_assessment,
    )
    from app.models.recommendations import InterventionPlan, InterventionAssessment
    from sqlalchemy import select

    target_action_id = action_id
    if not target_action_id and plan_id:
        stmt = select(InterventionPlan.action_id).where(InterventionPlan.plan_id == plan_id).limit(1)
        target_action_id = session.execute(stmt).scalar_one_or_none()

    if not target_action_id:
        return {
            "error": "No action_id or plan_id provided.",
            "status": "UNAVAILABLE",
        }

    action = get_corrective_action(session, target_action_id)
    if not action:
        return {
            "error": f"Corrective action '{target_action_id}' not found.",
            "status": "UNAVAILABLE",
        }

    plan = get_measurement_plan_for_action(session, target_action_id)
    if not plan:
        return {
            "action_id": target_action_id,
            "status": "NO_MEASUREMENT_PLAN",
            "message": "A measurement & verification plan has not yet been defined for this action.",
            "review_status": action.review_status,
            "implemented_at": action.implemented_at.isoformat() if action.implemented_at else None,
        }

    try:
        comp, asm = evaluate_and_record_assessment(session, target_action_id)
        return {
            "action_id": target_action_id,
            "plan_id": plan.plan_id,
            "plan_version": plan.version,
            "is_frozen": plan.is_frozen,
            "is_retrospective": plan.is_retrospective,
            "boundary": comp.measurement_boundary,
            "baseline_metrics": {
                "kwh": comp.baseline.kwh,
                "cost_inr": comp.baseline.cost_inr,
                "actual_units": comp.baseline.actual_units,
                "good_units": comp.baseline.good_units,
                "reject_units": comp.baseline.reject_units,
                "downtime_minutes": comp.baseline.downtime_minutes,
                "coverage_pct": comp.baseline.coverage_pct,
                "kwh_per_good_unit": comp.baseline.kwh_per_good_unit,
                "cost_per_good_unit": comp.baseline.cost_per_good_unit,
            },
            "post_metrics": {
                "kwh": comp.post.kwh,
                "cost_inr": comp.post.cost_inr,
                "actual_units": comp.post.actual_units,
                "good_units": comp.post.good_units,
                "reject_units": comp.post.reject_units,
                "downtime_minutes": comp.post.downtime_minutes,
                "coverage_pct": comp.post.coverage_pct,
                "kwh_per_good_unit": comp.post.kwh_per_good_unit,
                "cost_per_good_unit": comp.post.cost_per_good_unit,
            },
            "comparison_changes": {
                "kwh_change_abs": comp.kwh_change_abs,
                "kwh_change_pct": comp.kwh_change_pct,
                "intensity_change_pct": comp.intensity_change_pct,
                "cost_intensity_change_pct": comp.cost_intensity_change_pct,
                "sign_convention": comp.sign_convention,
            },
            "common_rate_comparison": {
                "baseline_cost_inr": comp.common_rate_baseline_cost_inr,
                "post_cost_inr": comp.common_rate_post_cost_inr,
                "cost_change_inr": comp.common_rate_cost_change_inr,
                "tariff_inr_per_kwh": comp.common_rate_factor_inr_per_kwh,
                "tariff_version": comp.common_rate_factor_version,
            },
            "guardrails": [g.dict() for g in comp.guardrails],
            "guardrails_passed": comp.guardrails_passed,
            "production_protection_status": comp.production_protection_status,
            "objective_outcome": comp.objective_outcome,
            "management_outcome": comp.management_outcome,
            "management_outcome_detail": comp.management_outcome_detail,
            "next_step": comp.next_step,
            "is_awaiting_data": comp.is_awaiting_data,
            "remaining_time_minutes": comp.remaining_time_minutes,
            "comparison_method": comp.comparison_method,
            "work_order_link": comp.work_order_link,
            "downtime_event_link": comp.downtime_event_link,
            "electricity_savings_kwh": comp.electricity_savings_kwh,
            "monetary_savings_basis": comp.monetary_savings_basis,
            "avoided_cost_inr": comp.avoided_cost_inr,
            "savings_claim_status": comp.savings_claim_status,
            "status_reason": comp.status_reason,
            "overlap_flag": comp.overlap_flag,
            "overlap_details": comp.overlap_details,
            "three_separate_answers": comp.three_separate_answers,
            "human_governance": {
                "review_status": action.review_status,
                "reviewed_by": action.reviewed_by,
                "implemented_at": action.implemented_at.isoformat() if action.implemented_at else None,
                "implemented_by": action.implemented_by,
                "signed_off_by": asm.signed_off_by if asm else None,
                "signed_off_at": asm.signed_off_at.isoformat() if asm and asm.signed_off_at else None,
                "review_decision": asm.review_decision if asm else None,
            },
        }
    except Exception as e:
        return {
            "action_id": target_action_id,
            "error": str(e),
            "status": "EVALUATION_ERROR",
        }


register_tool(
    name="explain_intervention_assessment",
    description=(
        "Explain an operational intervention savings verification assessment: returns deterministic before/after "
        "energy and production metrics, guardrail outcomes (output, quality yield, downtime), objective business outcome, "
        "avoided electricity quantity (if defensibly quantified), monetary savings basis, and authorized human governance sign-off status."
    ),
    category="interventions",
    args_schema=ExplainInterventionAssessmentInput,
    func=_explain_intervention_assessment_tool,
)


class UtilityTelemetryObservationsInput(BaseModel):
    """Input parameters for utility_telemetry_observations tool."""
    plant_id: str = Field("IN-TN-01", description="Plant identifier, e.g. 'IN-TN-01' or 'IN-KA-01'")
    utility_type: Optional[str] = Field(None, description="Utility type, e.g. 'COMPRESSED_AIR', 'CHILLED_WATER', 'HVAC', 'NITROGEN', 'PROCESS_WATER'")
    start_time: Optional[datetime] = Field(None, description="Start timestamp")
    end_time: Optional[datetime] = Field(None, description="End timestamp")
    equipment_id: Optional[str] = Field(None, description="Specific utility equipment ID, e.g. 'UTL-01'")
    limit: int = Field(50, description="Max observations to return")


def _utility_telemetry_observations_tool(
    session: Session,
    plant_id: str = "IN-TN-01",
    utility_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    equipment_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    from app.services.operating_context import get_utility_telemetry_observations
    return get_utility_telemetry_observations(
        session=session,
        plant_id=plant_id,
        utility_type=utility_type,
        start_time=start_time,
        end_time=end_time,
        equipment_id=equipment_id,
        limit=limit,
    )


register_tool(
    name="utility_telemetry_observations",
    description=(
        "Query utility telemetry observations (compressed air, chilled water, HVAC, nitrogen, process water). "
        "Distinguishes compressor electrical consumption ('Compressor electricity consumption (kWh)' at meter MTR-COMPRESSOR in fact_energy_meter_hourly) "
        "from compressed air delivery (flow and pressure in fact_utility_telemetry_hourly). "
        "Preserves raw flow readings with 'Flow-rate unit unverified', keeps derived volume, leak rate, and monetary savings null with reasons, "
        "and generates ultrasonic acoustic inspection leak-check recommendations when qualified alarm or pressure evidence warrants investigation."
    ),
    category="operating_context",
    args_schema=UtilityTelemetryObservationsInput,
    func=_utility_telemetry_observations_tool,
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

