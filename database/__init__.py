"""
Database module initialization.
Exports database components for use throughout the application.
"""

from database.base import Base, engine, SessionLocal
from database.session import get_db_context, create_session
from database.dependencies import get_db
from database.utils import (
    check_db_connection,
    init_db,
    drop_db,
    reset_db,
    get_db_info,
)

__all__ = [
    # Base components
    "Base",
    "engine",
    "SessionLocal",
    # Session management
    "get_db_context",
    "create_session",
    # FastAPI dependencies
    "get_db",
    # Utilities
    "check_db_connection",
    "init_db",
    "drop_db",
    "reset_db",
    "get_db_info",
]
