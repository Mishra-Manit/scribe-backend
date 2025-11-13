"""
Database session management utilities.
Provides context managers and helpers for database sessions.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from database.base import SessionLocal


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_db_context() as db:
            user = db.query(User).first()

    Yields:
        Session: SQLAlchemy database session

    Ensures:
        - Session is properly closed after use
        - Exceptions trigger rollback
        - Commits on successful completion
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_session() -> Session:
    """
    Create a new database session.

    Returns:
        Session: A new SQLAlchemy session

    Note:
        Caller is responsible for closing the session.
        Consider using get_db_context() instead for automatic cleanup.
    """
    return SessionLocal()
