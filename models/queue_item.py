"""QueueItem model for database-backed email generation queue."""

from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.base import Base


class QueueStatus(str, Enum):
    """Queue item status enum. Inherits from str for JSON serialization."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class QueueItem(Base):
    """Queue item for sequential email generation. Owned by User, produces Email on completion."""

    __tablename__ = "queue_items"

    # Primary Key
    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
        comment="Unique queue item ID"
    )

    # Foreign Key to User
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who submitted this queue item"
    )

    # Request data (snapshot at submission time)
    recipient_name = Column(
        String(255),
        nullable=False,
        comment="Name of the email recipient"
    )

    recipient_interest = Column(
        Text,
        nullable=False,
        comment="Research interest for personalization"
    )

    email_template = Column(
        Text,
        nullable=False,
        comment="Email template snapshot at submission time"
    )

    # Status tracking
    status = Column(
        String(20),
        nullable=False,
        default=QueueStatus.PENDING,
        comment="Current status: pending, processing, completed, failed"
    )

    celery_task_id = Column(
        String(255),
        nullable=True,
        comment="Celery task ID for status polling fallback"
    )

    # Result data
    email_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("emails.id", ondelete="SET NULL"),
        nullable=True,
        comment="Generated email ID on successful completion"
    )

    error_message = Column(
        Text,
        nullable=True,
        comment="Error details if status is failed"
    )

    # Pipeline progress (for detailed UI updates)
    current_step = Column(
        String(50),
        nullable=True,
        comment="Current pipeline step: template_parser, web_scraper, arxiv_helper, email_composer"
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the item was submitted to queue"
    )

    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When processing started"
    )

    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When processing completed or failed"
    )

    # Relationships
    user = relationship(
        "User",
        back_populates="queue_items"
    )

    email = relationship(
        "Email",
        back_populates="queue_item",
        uselist=False
    )

    # Indexes for efficient queries
    __table_args__ = (
        Index('ix_queue_items_user_id', 'user_id'),
        Index('ix_queue_items_status', 'status'),
        Index('ix_queue_items_created_at', 'created_at', postgresql_using='btree'),
        Index('ix_queue_items_user_status', 'user_id', 'status'),
    )

    def __repr__(self) -> str:
        """String representation of QueueItem model."""
        return (
            f"<QueueItem(id={self.id}, user_id={self.user_id}, "
            f"recipient='{self.recipient_name}', status='{self.status}')>"
        )
