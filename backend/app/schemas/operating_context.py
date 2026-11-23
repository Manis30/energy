"""Pydantic schemas for Phase 3 and Phase 4 Operating Context and Energy Analysis."""

from datetime import date as dt_date, datetime as dt_datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IntervalSnapshot(BaseModel):
    """Snapshot of production and energy metrics for a single boundary hour (prior or restart)."""
    timestamp: dt_datetime = Field(..., description="Timestamp of the interval (start of hour)")
    hour: int = Field(..., description="Hour of the day (0-23)")
    interval_window: str = Field(..., description="Exact hour boundary notation, e.g. '[01:00, 02:00)'")
    shift_id: Optional[str] = Field(None, description="Shift identifier")
    product_id: Optional[str] = Field(None, description="Product identifier")
    target_qty: int = Field(0, description="Target production quantity")
    actual_qty: int = Field(0, description="Actual output units")
    good_qty: int = Field(0, description="Good finished units")
    reject_qty: int = Field(0, description="Reject units")
    rework_qty: int = Field(0, description="Rework units")
    downtime_min: int = Field(0, description="Recorded downtime minutes")
    downtime_reason: Optional[str] = Field(None, description="Raw downtime reason from source record")
    downtime_reason_display: str = Field("Reason unspecified", description="Human-readable downtime reason ('Reason unspecified' if NONE)")
    consumption_kwh: Optional[float] = Field(None, description="Electricity consumed in kWh (process meter)")
    cost_inr: Optional[float] = Field(None, description="Dataset-derived electricity cost in INR")
    source_reading_id: Optional[str] = Field(None, description="Source meter reading ID")
    source_event_id: Optional[str] = Field(None, description="Source production event ID")
    source_revision_id: Optional[str] = Field(None, description="Immutable source revision ID if pinned")


class HourlyOperatingObservation(BaseModel):
    """Single hour operational observation joining plant, line, process meter, production, and telemetry."""
    plant_id: str = Field(..., description="Plant identifier")
    line_id: str = Field(..., description="Production line identifier")
    process: str = Field(..., description="Process name (SMT or FAL)")
    timestamp: dt_datetime = Field(..., description="Observation timestamp (interval start)")
    interval_start: dt_datetime = Field(..., description="Interval start timestamp")
    interval_end: dt_datetime = Field(..., description="Interval end timestamp (exclusive)")
    interval_window: str = Field(..., description="Explicit interval notation, e.g. '[02:00, 03:00)'")
    date: dt_date = Field(..., description="Calendar date")
    hour: int = Field(..., description="Hour of day (0-23)")
    shift_id: str = Field(..., description="Shift identifier")
    product_id: Optional[str] = Field(None, description="Product identifier")
    process_meter_id: Optional[str] = Field(None, description="Process meter identifier (e.g. MTR-SMT, MTR-FAL)")
    consumption_kwh: Optional[float] = Field(None, description="Process meter electricity consumption in kWh")
    cost_inr: Optional[float] = Field(None, description="Dataset-derived electricity cost in INR")
    target_qty: Optional[int] = Field(None, description="Target production quantity")
    actual_qty: Optional[int] = Field(None, description="Actual output units")
    good_qty: Optional[int] = Field(None, description="Good finished units")
    reject_qty: Optional[int] = Field(None, description="Reject units")
    rework_qty: Optional[int] = Field(None, description="Rework units")
    target_shortfall: Optional[int] = Field(
        None,
        description="Target shortfall during observed hours (target_qty - actual_qty)"
    )
    downtime_min: Optional[int] = Field(None, description="Recorded downtime in minutes")
    downtime_reason: Optional[str] = Field(None, description="Raw recorded downtime reason (NONE preserved in provenance)")
    downtime_reason_display: str = Field("Reason unspecified", description="Display downtime reason ('Reason unspecified' for NONE)")
    match_status: str = Field(
        ...,
        description="Data match status: MATCHED, MISSING_ENERGY, MISSING_PRODUCTION, TOPOLOGY_CONFLICT"
    )
    missing_fields: List[str] = Field(default_factory=list, description="List of missing fields")
    mapping_issues: List[str] = Field(default_factory=list, description="Any topology or line mapping warnings")
    source_reading_id: Optional[str] = Field(None, description="Meter reading ID")
    source_event_id: Optional[str] = Field(None, description="Production event ID")
    source_revisions: List[str] = Field(default_factory=list, description="Source revision IDs")
    machine_states: List[str] = Field(default_factory=list, description="Machine states recorded on line")
    alarm_codes: List[str] = Field(default_factory=list, description="Active machine alarm codes")
    shift_name: Optional[str] = Field(None, description="Shift name from calendar")
    is_working_day: Optional[bool] = Field(None, description="Working day flag from calendar")
    shift_planned_minutes: Optional[int] = Field(None, description="Planned shift duration in minutes")


class StoppageEpisode(BaseModel):
    """
    Consecutive observed zero-output hours for the same plant and line.
    Captures lost expected output, energy consumed during stoppage, and restart conditions.
    """
    episode_id: str = Field(..., description="Unique episode identifier")
    plant_id: str = Field(..., description="Plant identifier")
    line_id: str = Field(..., description="Line identifier")
    process: str = Field(..., description="Process name (SMT or FAL)")
    first_interval: dt_datetime = Field(..., description="Start timestamp of first stoppage hour")
    last_interval: dt_datetime = Field(..., description="Timestamp of last stoppage hour")
    interval_start: dt_datetime = Field(..., description="Interval start timestamp")
    interval_end: dt_datetime = Field(..., description="Interval end timestamp (exclusive boundary)")
    interval_window: str = Field(..., description="Explicit hour boundaries, e.g. '[02:00, 04:00)'")
    observed_duration_hours: int = Field(..., description="Consecutive hours with 0 output")
    target_qty_lost: int = Field(..., description="Sum of target_qty during the stoppage episode")
    target_shortfall: int = Field(..., description="Target shortfall during observed hours (target_qty - actual_qty)")
    actual_qty: int = Field(0, description="Actual output during stoppage (must be 0)")
    good_qty: int = Field(0, description="Good units during stoppage (must be 0)")
    recorded_downtime_minutes: int = Field(..., description="Sum of recorded downtime minutes across episode")
    downtime_reasons: List[str] = Field(default_factory=list, description="Raw downtime reasons recorded (e.g. ['NONE'])")
    downtime_reasons_display: List[str] = Field(
        default_factory=list,
        description="Display downtime reasons ('Reason unspecified' replacing raw 'NONE')"
    )
    process_kwh: Optional[float] = Field(None, description="Sum of electricity consumed (kWh) during stoppage")
    process_cost_inr: Optional[float] = Field(None, description="Dataset-derived electricity cost (INR) during stoppage")
    cost_label: str = Field("dataset-derived", description="Cost derivation label")
    process_electricity_label: str = Field(
        "Process electricity during zero-output hours",
        description="Official label for process electricity during stoppage"
    )
    energy_coverage_pct: float = Field(..., description="Percentage of episode hours with complete meter readings")
    prior_productive_interval: Optional[IntervalSnapshot] = Field(
        None, description="Last non-zero productive interval immediately preceding the stoppage"
    )
    next_restart_interval: Optional[IntervalSnapshot] = Field(
        None, description="First productive interval immediately following the stoppage"
    )
    machine_states: List[str] = Field(default_factory=list, description="Machine states observed across episode")
    alarm_codes: List[str] = Field(default_factory=list, description="Machine alarms logged during episode")
    has_machine_telemetry: bool = Field(False, description="Whether machine telemetry was available for this episode")
    source_record_ids: List[str] = Field(default_factory=list, description="Constituent meter and event IDs")
    source_revision_ids: List[str] = Field(default_factory=list, description="Constituent source revision IDs")


class SimilarPeriodsComparison(BaseModel):
    """
    Strictly descriptive comparison of an inspected episode against earlier stoppage episodes
    on the same line and process.
    """
    target_episode_id: str = Field(..., description="Inspected episode identifier")
    comparison_cutoff: dt_datetime = Field(
        ...,
        description="Comparison cutoff timestamp; only completed episodes ending before this cutoff are eligible"
    )
    comparison_pool_definition: str = Field(
        "Completed stoppage episodes on same line and plant that ended before the selected episode began",
        description="Definition of the eligible comparison pool"
    )
    historical_window: str = Field(..., description="Date range of historical comparison baseline")
    matching_criteria: str = Field(..., description="Descriptive criteria used to select comparable episodes")
    eligible_count: int = Field(..., description="Number of historical episodes meeting comparison criteria")
    excluded_count: int = Field(..., description="Number of historical episodes excluded")
    excluded_reasons: Dict[str, int] = Field(default_factory=dict, description="Count of exclusions by reason")
    median_kwh_per_hour: Optional[float] = Field(None, description="Median energy consumption (kWh/hr) across similar stoppages")
    min_kwh_per_hour: Optional[float] = Field(None, description="Minimum energy consumption (kWh/hr)")
    max_kwh_per_hour: Optional[float] = Field(None, description="Maximum energy consumption (kWh/hr)")
    duration_min_hours: Optional[int] = Field(None, description="Shortest comparable stoppage duration")
    duration_max_hours: Optional[int] = Field(None, description="Longest comparable stoppage duration")
    typical_downtime_reasons: List[str] = Field(default_factory=list, description="Most frequent downtime reasons")
    typical_downtime_reasons_display: List[str] = Field(default_factory=list, description="Display reasons ('Reason unspecified' for NONE)")
    comparable_episodes: List[Dict[str, Any]] = Field(default_factory=list, description="Summary of comparable episodes")


class OperatingContextSummaryResponse(BaseModel):
    """Summary metrics of operating observations and stoppages for selected scope."""
    plant_id: Optional[str] = None
    line_id: Optional[str] = None
    start_date: Optional[dt_date] = None
    end_date: Optional[dt_date] = None
    total_observed_hours: int = 0
    matched_hours: int = 0
    missing_energy_hours: int = 0
    missing_production_hours: int = 0
    stoppage_episode_count: int = 0
    total_stoppage_hours: int = 0
    total_stoppage_kwh: float = 0.0
    total_target_lost: int = 0
    total_target_shortfall: int = 0
    influencing_inputs_and_context_gaps: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Disclosure of operational inputs influencing comparisons and missing operating context",
    )


class StoppageEpisodesResponse(BaseModel):
    """List response for detected stoppage episodes."""
    total_count: int
    episodes: List[StoppageEpisode]


class ActionableInvestigationSection(BaseModel):
    """Four actionable sections for Facilities and Production investigations."""
    observed_condition: str = Field(..., description="Plant, line or meter, interval notation [start, end), and units")
    comparison_and_evidence: str = Field(..., description="Reference population, baseline comparison stats, and links to underlying readings")
    possible_causes_and_limitations: List[str] = Field(default_factory=list, description="Labeled hypotheses and explicit evidence limitations")
    suggested_investigation: Dict[str, Any] = Field(
        default_factory=dict,
        description="Responsible team (Facilities vs Production) and production condition to check before modifying state"
    )
    production_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Target, actual output, good units, rejects, downtime, and restart context"
    )


class StoppageEpisodeDetailResponse(BaseModel):
    """Detailed view of a single stoppage episode including similar periods comparison and investigation."""
    episode: StoppageEpisode
    similar_periods: SimilarPeriodsComparison
    constituent_hours: List[HourlyOperatingObservation]
    actionable_investigation: Optional[ActionableInvestigationSection] = None
