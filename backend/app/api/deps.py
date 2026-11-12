"""Dependencies for FastAPI analytical routes."""

from typing import Optional
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.agent import IndustrialEnergyAgent


def get_db_session(session: Optional[Session] = Depends(get_db)) -> Session:
    """
    Ensure an active database session is available.
    Raises HTTP 503 if the database connection cannot be established.
    """
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable. Please verify database connectivity.",
        )
    return session


def get_agent() -> IndustrialEnergyAgent:
    """
    Dependency provider returning an IndustrialEnergyAgent instance.
    Reuses the global DomoClient singleton.
    """
    return IndustrialEnergyAgent()

