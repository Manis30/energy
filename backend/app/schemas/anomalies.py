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


class StatisticalAnomaliesResponse(BaseModel):
    """Global/period Z-score anomaly response."""
    analysis_type: str
    threshold_z: float
    min_observations: int
    total_anomalies_detected: int
    eligible_groups_count: int
    zero_variance_groups: List[str]
    insufficient_observations_groups: List[str]
    meter_baselines: Dict[str, Any]
    anomalies: List[AnomalyRecord]


class RollingAnomaliesResponse(BaseModel):
    """Rolling historical baseline anomaly response."""
    analysis_type: str
    window_size_hours: int
    min_observations: int
    threshold_z: float
    total_anomalies_detected: int
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
