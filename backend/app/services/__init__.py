"""Analytics and data services package for Industrial Energy Intelligence Platform."""

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
]
