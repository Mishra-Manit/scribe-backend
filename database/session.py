"""
Database session management utilities.
Provides context managers for database sessions.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from database.base import SessionLocal


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Database session context manager.

    Usage (read-only):
        with get_db_context() as db:
            user = db.query(User).first()

    Usage (with write):
        with get_db_context() as db:
            db.add(user)
            db.commit()
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
