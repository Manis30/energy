"""FastAPI main application entry point for Industrial Energy Intelligence Platform."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.anomalies import router as anomalies_router
from app.api.energy import router as energy_router
from app.api.energy_intensity import router as energy_intensity_router
from app.api.production import router as production_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Industrial Energy Intelligence Platform",
    description="Deterministic REST API for factory energy, production, SEC intensity, and anomaly detection.",
    version=settings.API_VERSION,
)

# CORS configuration for React + Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unexpected server errors."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected server error occurred.",
            "detail": str(exc) if settings.APP_ENV == "development" else None,
        },
    )


# Health check
@app.get("/api/health", tags=["System"])
async def health_check() -> dict:
    """Health check endpoint confirming backend status."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.API_VERSION,
        "environment": settings.APP_ENV,
    }


# Include analytical and anomaly routers
app.include_router(energy_router, prefix="/api/energy", tags=["Energy Analytics"])
app.include_router(production_router, prefix="/api/production", tags=["Production Analytics"])
app.include_router(energy_intensity_router, prefix="/api/energy-intensity", tags=["Energy Intensity & SEC"])
app.include_router(anomalies_router, prefix="/api/anomalies", tags=["Deterministic Anomaly Detection"])
