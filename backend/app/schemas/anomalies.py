"""Pydantic schemas for Deterministic Anomaly Detection API."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AnomalyRecord(BaseModel):
    """Standard unified anomaly item contract."""
    anomaly_type: str = Field(..., description="Stable identifier for the anomaly category")
    plant_id: str
    meter_id: Optional[str] = None
    line_id: Optional[str] = None
    timestamp: str = Field(..., description="ISO 8601 timestamp of occurrence")
    actual_value: Decimal = Field(..., description="Observed measurement (kWh, power factor, etc.)")
    baseline_value: Optional[Decimal] = Field(
        None,
        description="Energy baseline reference or monitoring threshold; null when no comparable energy baseline exists",
    )
    deviation_score: float = Field(..., description="Z-score deviation or deficit magnitude")
    severity: str = Field(..., description="'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', or 'INFORMATIONAL'")
    explanation: str = Field(..., description="Deterministic human-readable explanation")
    context_flags: Dict[str, Any] = Field(default_factory=dict, description="Metadata flags, bounds, notes")
    source_table: Optional[str] = Field(None, description="Originating database table for the anomaly observation")
    source_record_id: Optional[str] = Field(None, description="Primary key identifier of the originating source record")
    upload_id: Optional[str] = Field(None, description="Upload batch identifier that introduced the originating record")
    detector_version: Optional[str] = Field(None, description="Deterministic detector algorithm version that identified the anomaly")


class StatisticalAnomaliesResponse(BaseModel):
    """Global/period Z-score anomaly response."""
    analysis_type: str
    threshold_z: float
    min_observations: int
    lookback_days: int = Field(default=30, description="Historical baseline lookback duration in days")
    total_anomalies_detected: int
    eligible_groups_count: int
    qualified_groups_count: int = Field(default=0, description="Count of meter groups whose baselines are fully QUALIFIED")
    inconclusive_groups_count: int = Field(default=0, description="Count of meter groups whose baselines are INCONCLUSIVE")
    disqualified_groups_count: int = Field(default=0, description="Count of meter groups whose baselines are NOT_QUALIFIED")
    zero_variance_groups: List[str]
    insufficient_observations_groups: List[str]
    disqualified_groups: List[str] = Field(default_factory=list, description="Meter groups excluded due to baseline qualification failure")
    baseline_period: Dict[str, Any] = Field(default_factory=dict, description="Historical baseline period boundaries")
    evaluation_period: Dict[str, Any] = Field(default_factory=dict, description="Evaluation period boundaries")
    meter_baselines: Dict[str, Any]
    anomalies: List[AnomalyRecord]


class RollingAnomaliesResponse(BaseModel):
    """Rolling historical baseline anomaly response."""
    analysis_type: str
    window_size_hours: int
    min_observations: int
    threshold_z: float
    total_anomalies_detected: int
    total_evaluated_observations: int = Field(default=0, description="Total observations from eligible groups evaluated in the evaluation period")
    insufficient_history_count: int = Field(default=0, description="Observations with fewer historical readings than min_observations")
    zero_variance_count: int = Field(default=0, description="Observations where preceding window standard deviation was zero")
    insufficient_history_meters: List[str] = Field(default_factory=list, description="Meter IDs affected by insufficient history")
    zero_variance_meters: List[str] = Field(default_factory=list, description="Meter IDs affected by zero variance in rolling window")
    eligible_groups_count: int = Field(default=0, description="Count of meter groups whose baselines are QUALIFIED or INCONCLUSIVE")
    qualified_groups_count: int = Field(default=0, description="Count of meter groups whose baselines are fully QUALIFIED")
    inconclusive_groups_count: int = Field(default=0, description="Count of meter groups whose baselines are INCONCLUSIVE")
    disqualified_groups_count: int = Field(default=0, description="Count of meter groups whose baselines are NOT_QUALIFIED")
    disqualified_groups: List[str] = Field(default_factory=list, description="Meter groups excluded due to baseline qualification failure")
    zero_variance_groups: List[str] = Field(default_factory=list, description="Meter groups with zero variance in historical baseline window")
    insufficient_observations_groups: List[str] = Field(default_factory=list, description="Meter groups with fewer historical observations than min_observations")
    baseline_period: Dict[str, Any] = Field(default_factory=dict, description="Historical baseline period boundaries")
    evaluation_period: Dict[str, Any] = Field(default_factory=dict, description="Evaluation period boundaries")
    meter_baselines: Dict[str, Any] = Field(default_factory=dict, description="Detailed qualification status per meter group")
    anomalies: List[AnomalyRecord]


class LowPowerFactorResponse(BaseModel):
    """Low power factor application-monitoring response."""
    analysis_type: str
    threshold: float
    total_anomalies_detected: int
    anomalies: List[AnomalyRecord]


class ZeroProductionStandbyResponse(BaseModel):
    """Zero-production standby energy response."""
    analysis_type: str
    total_events_detected: int
    total_standby_energy_kwh: Decimal
    total_stoppage_minutes: int
    smt_standby_energy_kwh: Decimal
    fal_standby_energy_kwh: Decimal
    downtime_reasons_breakdown: Dict[str, int]
    facility_utilities_status: Dict[str, Any]
    anomalies: List[AnomalyRecord]


class UnifiedAnomaliesResponse(BaseModel):
    """Unified response containing results from all anomaly detectors."""
    plant_id: Optional[str] = None
    analysis_period: Dict[str, Optional[str]]
    total_anomalies_detected: int = Field(
        ...,
        description="Sum of detector findings; overlapping findings are not deduplicated into unique observations",
    )
    statistical_zscore: StatisticalAnomaliesResponse
    rolling_baseline: RollingAnomaliesResponse
    low_power_factor: LowPowerFactorResponse
    zero_production_standby: ZeroProductionStandbyResponse
