"""
FastAPI dependency injection for database sessions.
Provides database session dependencies for API endpoints.
"""

from typing import Generator

from sqlalchemy.orm import Session

from database.base import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            users = db.query(User).all()
            return users

    Yields:
        Session: SQLAlchemy database session

    Ensures:
        - Session is automatically closed after the request
        - Exceptions are properly handled
        - Connection is returned to the pool
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
