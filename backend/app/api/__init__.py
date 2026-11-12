"""API routers package for Industrial Energy Intelligence Platform."""

from app.api.anomalies import router as anomalies_router
from app.api.assistant import router as assistant_router
from app.api.energy import router as energy_router
from app.api.energy_intensity import router as energy_intensity_router
from app.api.production import router as production_router

__all__ = [
    "assistant_router",
    "energy_router",
    "production_router",
    "energy_intensity_router",
    "anomalies_router",
]
