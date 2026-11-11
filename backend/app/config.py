"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    DOMO_MAX_RETRIES: int = 3

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
