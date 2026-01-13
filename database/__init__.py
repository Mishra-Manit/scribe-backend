"""
Database module initialization.
Exports database components for use throughout the application.
"""

from database.base import Base, engine, SessionLocal
from database.session import get_db_context
from database.dependencies import get_db
from database.utils import (
    check_db_connection,
    get_db_info,
)
from database.retry_utils import (
    retry_on_db_error,
    retry_on_db_error_async,
)

__all__ = [
    # Base components
    "Base",
    "engine",
    "SessionLocal",
    # Session management
    "get_db_context",
    # FastAPI dependencies
    "get_db",
    # Utilities
    "check_db_connection",
    "get_db_info",
    # Retry utilities
    "retry_on_db_error",
    "retry_on_db_error_async",
]
