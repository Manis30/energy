"""Analytics and data services package for Industrial Energy Intelligence Platform."""

from app.services.anomaly_detection import (
    detect_all_anomalies,
    detect_energy_statistical_anomalies,
    detect_low_power_factor_anomalies,
    detect_persistent_baseload_anomalies,
    detect_rolling_baseline_anomalies,
    detect_zero_output_and_restart_anomalies,
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
from app.services.intervention_service import (
    amend_measurement_plan,
    approve_measurement_plan,
    create_measurement_plan,
    evaluate_and_record_assessment,
    get_measurement_plan_for_action,
    list_savings_ledger,
    record_action_implementation,
    review_corrective_action,
    sign_off_assessment,
)
from app.services.production_analytics import (
    get_downtime_by_reason,
    get_production_by_line,
    get_production_by_product,
    get_production_by_shift,
    get_production_daily_trend,
    get_production_summary,
)

__all__ = [
    # Energy
    "get_energy_summary",
    "get_energy_by_meter",
    "get_energy_by_area",
    "get_energy_daily_trend",
    "get_power_factor_summary",
    # Production
    "get_production_summary",
    "get_production_by_line",
    "get_production_by_product",
    "get_production_by_shift",
    "get_production_daily_trend",
    "get_downtime_by_reason",
    # Energy Intensity & Process / Factory
    "get_process_energy_analytics",
    "get_factory_energy_analytics",
    "get_product_process_energy",
    "get_zero_production_period_energy",
    # Anomaly Detection
    "detect_energy_statistical_anomalies",
    "detect_rolling_baseline_anomalies",
    "detect_low_power_factor_anomalies",
    "detect_persistent_baseload_anomalies",
    "detect_zero_production_standby_anomalies",
    "detect_zero_output_and_restart_anomalies",
    "detect_all_anomalies",
]
