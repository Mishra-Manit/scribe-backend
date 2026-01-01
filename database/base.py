"""
Database configuration and SQLAlchemy setup.

This module provides the core database infrastructure:
- SQLAlchemy engine for connection pooling
- Session factory for database transactions
- Declarative base for ORM models
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from config import settings

# Create SQLAlchemy engine with connection pooling
# Optimized for Render + Supabase connection pooler
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=10,         # Increased for production load
    max_overflow=20,      # Increased overflow for burst traffic
    pool_pre_ping=False,  # Disabled - pooler handles connection health
    pool_recycle=300,     # Recycle connections every 5 minutes (pooler requirement)
    connect_args={
        "connect_timeout": 10,      # Fail fast if connection unavailable
        "options": "-c statement_timeout=30000"  # 30 second query timeout
    },
    echo=settings.is_development,  # Log SQL in development
)

# Create SessionLocal class for database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Create declarative base for ORM models
Base = declarative_base()
