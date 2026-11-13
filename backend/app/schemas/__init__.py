"""API schemas package for Industrial Energy Intelligence Platform."""

from app.schemas.anomalies import (
    AnomalyRecord,
    LowPowerFactorResponse,
    RollingAnomaliesResponse,
    StatisticalAnomaliesResponse,
    UnifiedAnomaliesResponse,
    ZeroProductionStandbyResponse,
)
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    ChatMessage,
    ToolEvidenceItem,
)
from app.schemas.common import (
    ErrorResponse,
    validate_date_range,
    validate_time_range,
)
from app.schemas.energy import (
    AreaEnergyItem,
    DailyEnergyItem,
    EnergyPeakReading,
    EnergySummaryResponse,
    MeterEnergyItem,
    PowerFactorSummaryResponse,
)
from app.schemas.energy_intensity import (
    FactoryEnergyResponse,
    ProcessEnergyLineItem,
    ProcessEnergySummaryResponse,
    ProductProcessEnergyItem,
    ZeroProductionEnergyResponse,
)
from app.schemas.production import (
    DailyProductionItem,
    DowntimeReasonItem,
    OeeAssessment,
    ProductionLineItem,
    ProductionProductItem,
    ProductionShiftItem,
    ProductionSummaryResponse,
)
from app.schemas.daily_reports import (
    InspectResponse,
    RowValidationError,
    PreviewRow,
    ValidationSummary,
    ValidateReportResponse,
    IngestReportResponse,
    UploadHistoryItem,
)


__all__ = [
    # Assistant
    "ChatMessage",
    "AssistantChatRequest",
    "ToolEvidenceItem",
    "AssistantChatResponse",
    # Common
    "ErrorResponse",
    "validate_date_range",
    "validate_time_range",
    # Energy
    "EnergyPeakReading",
    "EnergySummaryResponse",
    "MeterEnergyItem",
    "AreaEnergyItem",
    "DailyEnergyItem",
    "PowerFactorSummaryResponse",
    # Production
    "OeeAssessment",
    "ProductionSummaryResponse",
    "ProductionLineItem",
    "ProductionProductItem",
    "ProductionShiftItem",
    "DowntimeReasonItem",
    "DailyProductionItem",
    # Intensity & SEC
    "ProcessEnergyLineItem",
    "ProcessEnergySummaryResponse",
    "FactoryEnergyResponse",
    "ProductProcessEnergyItem",
    "ZeroProductionEnergyResponse",
    # Anomalies
    "AnomalyRecord",
    "StatisticalAnomaliesResponse",
    "RollingAnomaliesResponse",
    "LowPowerFactorResponse",
    "ZeroProductionStandbyResponse",
    "UnifiedAnomaliesResponse",
]
