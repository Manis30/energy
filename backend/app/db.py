"""Database foundation and connection management for Neon PostgreSQL."""

from typing import Generator, Optional
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import get_settings

# SQLAlchemy declarative base for model definitions
Base = declarative_base()

# Engine references initialized on demand
_engine: Optional[Engine] = None
_readonly_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None
_readonly_session_factory: Optional[sessionmaker] = None


def normalize_database_url(url: str) -> str:
    """Normalize database connection string for psycopg3 driver."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_engine() -> Optional[Engine]:
    """
    Get or create primary SQLAlchemy engine with Neon-compatible pooling.
    Used for application ingestion, migrations, and primary writes.
    Returns None if DATABASE_URL is not configured.
    """
    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    db_url = settings.DATABASE_URL_POOLED or settings.DATABASE_URL
    if not db_url:
        return None

    normalized_url = normalize_database_url(db_url)
    _engine = create_engine(
        normalized_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        echo=False,
    )
    return _engine


def get_readonly_engine() -> Engine:
    """
    Get or create read-only SQLAlchemy engine for analytical queries.
    Strictly uses READONLY_DATABASE_URL.
    Raises RuntimeError if READONLY_DATABASE_URL is not configured.
    Never falls back to owner DATABASE_URL.
    """
    global _readonly_engine
    if _readonly_engine is not None:
        return _readonly_engine

    settings = get_settings()
    readonly_url = settings.READONLY_DATABASE_URL
    if not readonly_url:
        raise RuntimeError(
            "READONLY_DATABASE_URL is not configured. "
            "A dedicated read-only database connection is strictly required for analytical queries."
        )

    normalized_url = normalize_database_url(readonly_url)
    _readonly_engine = create_engine(
        normalized_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
        pool_timeout=15,
        echo=False,
    )
    return _readonly_engine


def get_session_factory() -> Optional[sessionmaker]:
    """Get or create sessionmaker bound to primary engine."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory

    engine = get_engine()
    if engine is None:
        return None

    _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _session_factory


def get_readonly_session_factory() -> sessionmaker:
    """Get or create sessionmaker bound to read-only engine."""
    global _readonly_session_factory
    if _readonly_session_factory is not None:
        return _readonly_session_factory

    engine = get_readonly_engine()
    _readonly_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _readonly_session_factory


def reset_db_engines() -> None:
    """Dispose and reset all cached database engines (used in test teardown/isolation)."""
    global _engine, _readonly_engine, _session_factory, _readonly_session_factory
    if _engine is not None:
        _engine.dispose()
        _engine = None
    if _readonly_engine is not None:
        _readonly_engine.dispose()
        _readonly_engine = None
    _session_factory = None
    _readonly_session_factory = None


def get_db() -> Generator[Optional[Session], None, None]:
    """
    FastAPI dependency yielding primary database sessions.
    Yields None if database is not configured.
    """
    factory = get_session_factory()
    if factory is None:
        yield None
        return

    session = factory()
    try:
        yield session
    finally:
        session.close()
