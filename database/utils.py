"""
Database utility functions.
Provides helpers for database operations, health checks, and initialization.
"""

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database.base import engine, Base
from config import settings


def check_db_connection() -> bool:
    """
    Check if database connection is working.

    Returns:
        bool: True if connection is successful, False otherwise

    Usage:
        if check_db_connection():
            print("Database is connected")
        else:
            print("Database connection failed")
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


def init_db() -> None:
    """
    Initialize the database by creating all tables.

    Note:
        This creates tables based on SQLAlchemy models.
        In production, use Alembic migrations instead.
        This is useful for development and testing.

    Warning:
        Does not drop existing tables or modify schema.
        Use Alembic migrations for schema changes.
    """
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """
    Drop all tables from the database.

    Warning:
        This will delete ALL data in the database.
        Only use in development/testing environments.
        Never use in production!

    Raises:
        RuntimeError: If attempting to use in production environment
    """
    if settings.is_production:
        raise RuntimeError("Cannot drop database in production environment!")

    Base.metadata.drop_all(bind=engine)


def reset_db() -> None:
    """
    Drop and recreate all tables (complete reset).

    Warning:
        This will delete ALL data and recreate tables.
        Only use in development/testing environments.
        Never use in production!

    Raises:
        RuntimeError: If attempting to use in production environment
    """
    if settings.is_production:
        raise RuntimeError("Cannot reset database in production environment!")

    drop_db()
    init_db()


def sanitize_db_url(url: str) -> str:
    """
    Hide password in database URL for safe logging.

    Replaces the password portion of a database connection URL with "***"
    to prevent credentials from appearing in logs or error messages.
    """
    # No credentials present
    if "@" not in url:
        return url

    try:
        # Split protocol and rest of URL
        protocol, rest = url.split("://", 1)

        # Split credentials from host
        credentials, host = rest.split("@", 1)

        # Extract username (everything before first colon)
        username = credentials.split(":", 1)[0]

        # Rebuild URL with masked password
        return f"{protocol}://{username}:***@{host}"

    except ValueError:
        # Malformed URL - return as-is to avoid hiding errors
        return url


def get_db_info() -> dict:
    """
    Get database connection information and status.

    Returns:
        dict: Database information including connection status and URL (sanitized)

    Usage:
        info = get_db_info()
        print(f"Database: {info['status']}")
    """
    is_connected = check_db_connection()

    # Sanitize database URL (hide password)
    db_url_sanitized = sanitize_db_url(settings.database_url)

    return {
        "status": "connected" if is_connected else "disconnected",
        "url": db_url_sanitized,
        "environment": settings.environment,
    }
