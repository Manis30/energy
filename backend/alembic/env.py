"""Alembic environment configuration for Industrial Energy Intelligence Platform."""

import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.config import get_settings
from app.db import Base, normalize_database_url
import app.models  # Ensure models are loaded into Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for 'autogenerate' support
target_metadata = Base.metadata


def get_configured_url() -> str:
    """Retrieve and normalize database URL from Pydantic Settings."""
    settings = get_settings()
    url = settings.DATABASE_URL or settings.DATABASE_URL_POOLED
    if not url:
        return "postgresql+psycopg://user:pass@localhost/neondb"
    return normalize_database_url(url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    """
    url = get_configured_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    url = get_configured_url()
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
