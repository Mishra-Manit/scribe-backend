"""
Email model for SQLAlchemy ORM.
Represents the emails table in the database.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, Enum, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.base import Base
from pipeline.models.core import TemplateType

class Email(Base):
    """
    Email model representing generated emails in the system.

    Attributes:
        id (UUID): Primary key, auto-generated
        user_id (UUID): Foreign key to users table
        recipient_name (str): Name of the email recipient (professor)
        recipient_interest (str): Research interest/topic for personalization
        email_message (str): The generated email content
        created_at (datetime): Timestamp when email was generated

    Relationships:
        user: Many-to-one relationship with User model
    """

    __tablename__ = "emails"

    # Primary Key
    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
        comment="Unique email ID"
    )

    # Foreign Key to User
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who generated this email"
    )

    # Email Content
    recipient_name = Column(
        String(255),
        nullable=False,
        comment="Name of the email recipient"
    )

    recipient_interest = Column(
        String(500),
        nullable=False,
        comment="Research interest or topic for personalization"
    )

    email_message = Column(
        Text,
        nullable=False,
        comment="The generated email content"
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="When the email was generated"
    )

    template_type = Column(
        Enum(TemplateType, name="template_type_enum", native_enum=True),
        nullable=False,
        index=True,
        comment="Pipeline template classification"
    )

    email_metadata = Column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Structured generation metadata (papers, sources, timings)"
    )

    # Relationships
    user = relationship(
        "User",
        back_populates="emails"
    )

    # Indexes for efficient queries
    __table_args__ = (
        Index('ix_emails_user_id', 'user_id'),
        Index('ix_emails_created_at', 'created_at', postgresql_using='btree'),
        Index('ix_emails_user_created', 'user_id', 'created_at'),
    )

    def __repr__(self) -> str:
        """String representation of Email model."""
        return (
            f"<Email(id={self.id}, user_id={self.user_id}, "
            f"recipient='{self.recipient_name}', created_at={self.created_at})>"
        )

    def to_dict(self) -> dict:
        """
        Convert email model to dictionary.

        Returns:
            dict: Email data as dictionary
        """
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "recipient_name": self.recipient_name,
            "recipient_interest": self.recipient_interest,
            "email_message": self.email_message,
            "template_type": self.template_type.value if self.template_type else None,
            "metadata": self.email_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
