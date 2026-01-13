"""Database configuration and SQLAlchemy setup.

This module provides the core database infrastructure:
- SQLAlchemy engine for connection pooling
- Session factory for database transactions
- Declarative base for ORM models
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from config import settings


def _create_engine():
    """
    Create SQLAlchemy engine with NullPool for Supabase Transaction Pooler.
    - Eliminates double-pooling (app-side + server-side)
    - Prevents stale connection accumulation
    - Optimizes for auto-scaling deployments (Render.com)
    - Connections are created per-request and immediately discarded
    - Connection pre-ping adds safety for Cloudflare tunnel stability
    """
    return create_engine(
        settings.database_url,
        poolclass=NullPool,
        pool_pre_ping=True,  # Test connection health before use (Cloudflare tunnel safety)
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
