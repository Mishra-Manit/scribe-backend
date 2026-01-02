"""Database configuration and SQLAlchemy setup.

This module provides the core database infrastructure:
- SQLAlchemy engine for connection pooling
- Session factory for database transactions
- Declarative base for ORM models
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from config import settings


def _create_engine():
    """
    Create SQLAlchemy engine with environment-aware pool configuration.

    For Celery workers: Smaller pools to reduce stale connections during idle periods.
    For API servers: Larger pools for concurrent request handling.

    Connection validation (pool_pre_ping=True) ensures stale connections are
    detected and refreshed before use—critical for long-running workers that may
    lose network connectivity during idle periods.
    """
    return create_engine(
        settings.database_url,
        poolclass=QueuePool,
        pool_size=settings.effective_db_pool_size,
        max_overflow=settings.effective_db_pool_max_overflow,
        pool_pre_ping=True,  # Validate connections before use (catches stale pooler connections)
        pool_recycle=settings.db_pool_recycle,  # Recycle connections to work around pooler limits
        connect_args={
            "connect_timeout": settings.db_connect_timeout,
            "options": f"-c statement_timeout={settings.db_statement_timeout}",
        },
        echo=settings.is_development,
    )


# Create engine with configuration
engine = _create_engine()

# Create SessionLocal factory for database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Create declarative base for ORM models
Base = declarative_base()
