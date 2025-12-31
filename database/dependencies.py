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
    import logfire

    logfire.info("Creating database session")
    db = SessionLocal()
    logfire.info("Database session created successfully")
    try:
        yield db
    finally:
        logfire.info("Closing database session")
        db.close()
        logfire.info("Database session closed")
