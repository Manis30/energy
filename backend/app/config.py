"""Application configuration using Pydantic Settings."""

from decimal import Decimal
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Application-level engineering monitoring threshold for power factor
# This is an internal operational monitoring threshold, not a statutory or regulatory limit.
DEFAULT_POWER_FACTOR_THRESHOLD: Decimal = Decimal("0.90")


class Settings(BaseSettings):
    """Platform configuration settings loaded from environment variables."""

    # Application settings
    APP_ENV: str = "development"
    APP_NAME: str = "Industrial Energy Intelligence Platform"
    API_VERSION: str = "1.0.0"

    # Database settings (Neon PostgreSQL)
    DATABASE_URL: Optional[str] = None
    DATABASE_URL_POOLED: Optional[str] = None
    READONLY_DATABASE_URL: Optional[str] = None

    # AI Service settings (Domo AI Services)
    DOMO_BASE_URL: Optional[str] = None
    DOMO_DEVELOPER_TOKEN: Optional[str] = None
    MODEL_NAME: Optional[str] = None
    DOMO_TIMEOUT_SECONDS: float = 30.0
    DOMO_MAX_RETRIES: int = 3  # Maximum total request attempts (1 initial attempt + up to 2 retries = 3 total attempts)

    # Ingestion & Upload security limits
    MAX_UPLOAD_SIZE_MB: int = 25
    MAX_UPLOAD_ROWS: int = 50000

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
