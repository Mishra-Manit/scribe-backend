"""
FastAPI dependency injection for database sessions.
Provides database session dependencies for API endpoints.
"""

from typing import Generator

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.base import SessionLocal
from database.retry_utils import retry_on_db_error


@retry_on_db_error
def _create_db_session() -> Session:
    """
    Create and validate a database session.
    Wrapped with retry logic for transient connection failures.
    """
    db = SessionLocal()
    db.execute(text("SELECT 1"))  # Validate connection
    return db


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.
    Uses shared retry logic for consistent error handling across the application.
    """
    db = _create_db_session()
    try:
        yield db
    finally:
        db.close()
