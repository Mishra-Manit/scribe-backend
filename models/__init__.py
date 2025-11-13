"""
Models module initialization.
Imports all SQLAlchemy models for Alembic autodiscovery.
"""

from models.user import User
from models.email import Email

__all__ = [
    "User",
    "Email",
]
