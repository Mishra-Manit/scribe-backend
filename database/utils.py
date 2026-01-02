"""
Database utility functions.
Provides helpers for database operations and health checks.
"""

from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database.base import engine
from config import settings


def _test_db_connection() -> Tuple[bool, Optional[str]]:
    """
    Attempt a simple database connection and return success plus error details.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, None
    except OperationalError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def check_db_connection() -> bool:
    """
    Check if database connection is working.

    Returns:
        bool: True if connection is successful, False otherwise
    """
    is_connected, _ = _test_db_connection()
    return is_connected


def sanitize_db_url(url: str) -> str:
    """
    Hide password in database URL for safe logging.

    Replaces the password portion of a database connection URL with "***"
    to prevent credentials from appearing in logs or error messages.
    """
    if "@" not in url:
        return url

    try:
        protocol, rest = url.split("://", 1)
        credentials, host = rest.split("@", 1)
        username = credentials.split(":", 1)[0]
        return f"{protocol}://{username}:***@{host}"
    except ValueError:
        return url


def get_db_info() -> dict:
    """
    Get database connection information and status.

    Returns:
        dict: Database information including connection status and URL (sanitized)
    """
    is_connected, error = _test_db_connection()
    db_url_sanitized = sanitize_db_url(settings.database_url)

    info = {
        "status": "connected" if is_connected else "disconnected",
        "url": db_url_sanitized,
        "environment": settings.environment,
    }
    if not is_connected:
        info["error"] = error
    return info
