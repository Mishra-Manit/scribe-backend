"""
Models module initialization.
Imports all SQLAlchemy models for Alembic autodiscovery.
"""

from models.user import User
from models.email import Email
from models.template import Template
from models.queue_item import QueueItem, QueueStatus

__all__ = [
    "User",
    "Email",
    "Template",
    "QueueItem",
    "QueueStatus",
]
