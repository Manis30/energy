"""FastAPI main application entry point for Industrial Energy Intelligence Platform."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.anomalies import router as anomalies_router
from app.api.assistant import router as assistant_router
from app.api.daily_reports import router as daily_reports_router
from app.api.energy import router as energy_router
from app.api.energy_intensity import router as energy_intensity_router
from app.api.findings import router as findings_router
from app.api.operating_context import router as operating_context_router
from app.api.production import router as production_router
from app.api.reconciliation import router as reconciliation_router
from app.api.connectors import router as connectors_router
from app.api.recommendations import (
    actions_router,
    recommendations_router,
)
from app.config import get_settings
from app.db import get_engine
from app.models.findings import FindingAuditLog, FindingOccurrence, OperationalFinding
from app.models.upload_history import UploadHistory
from app.services.agent.domo_client import close_domo_client

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager handling resource initialization and cleanup.
    
    Schema Management Policy:
    - Alembic migrations ('alembic upgrade head') are the authoritative schema deployment path.
    - Startup table creation below acts as a development fallback only (using checkfirst=True)
      and never replaces or bypasses formal Alembic migrations in deployed environments.
    """
    engine = get_engine()
    if engine is not None:
        try:
            if settings.APP_ENV == "development":
                UploadHistory.__table__.create(engine, checkfirst=True)
                OperationalFinding.__table__.create(engine, checkfirst=True)
                FindingOccurrence.__table__.create(engine, checkfirst=True)
                FindingAuditLog.__table__.create(engine, checkfirst=True)
        except Exception:
            pass

    yield
    # Clean up global asynchronous clients on shutdown
    await close_domo_client()


app = FastAPI(
    title="Industrial Energy Intelligence Platform",
    description="Deterministic REST API for factory energy, production, SEC intensity, and anomaly detection.",
    version=settings.API_VERSION,
    lifespan=lifespan,
)

# CORS configuration for React + Vite frontend loaded dynamically from environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if settings.cors_origins else ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app",
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


# Health check endpoint
@app.get("/api/health", tags=["System"])
async def health_check() -> dict:
    """Health check endpoint confirming backend status."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.API_VERSION,
        "environment": settings.APP_ENV,
    }


# Include analytical, anomaly, assistant, daily report ingestion, and findings routers
app.include_router(daily_reports_router, prefix="/api/daily-reports", tags=["Daily Reports Ingestion"])
app.include_router(assistant_router, prefix="/api/assistant", tags=["AI Assistant"])
app.include_router(energy_router, prefix="/api/energy", tags=["Energy Analytics"])
app.include_router(production_router, prefix="/api/production", tags=["Production Analytics"])
app.include_router(energy_intensity_router, prefix="/api/energy-intensity", tags=["Energy Intensity & SEC"])
app.include_router(anomalies_router, prefix="/api/anomalies", tags=["Deterministic Anomaly Detection"])
app.include_router(findings_router, prefix="/api/findings", tags=["Operational Findings Lifecycle"])
app.include_router(findings_router, prefix="/api/v1/findings", tags=["Operational Findings Lifecycle"])
app.include_router(recommendations_router, prefix="/api/recommendations", tags=["Operational Recommendations"])
app.include_router(recommendations_router, prefix="/api/v1/recommendations", tags=["Operational Recommendations"])
app.include_router(actions_router, prefix="/api/actions", tags=["Corrective Actions"])
app.include_router(actions_router, prefix="/api/v1/actions", tags=["Corrective Actions"])
app.include_router(reconciliation_router, prefix="/api/reconciliation", tags=["Cross-Source Data Reconciliation"])
app.include_router(connectors_router, prefix="/api/connectors", tags=["Data Connectors"])
app.include_router(operating_context_router, prefix="/api/operating-context", tags=["Operating Context"])
