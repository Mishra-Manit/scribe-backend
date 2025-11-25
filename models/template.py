"""
Template model for SQLAlchemy ORM.
Represents the templates table in the database.
"""

from uuid import uuid4

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.base import Base


class Template(Base):
    """
    Template model representing user-generated cold email templates.

    Attributes:
        id (UUID): Primary key, auto-generated
        user_id (UUID): Foreign key to users table
        pdf_url (str): Supabase Storage URL for resume PDF
        template_text (str): Generated template content
        user_instructions (str): User guidance for template generation
        created_at (datetime): Timestamp when template was generated

    Relationships:
        user: Many-to-one relationship with User model
    """

    __tablename__ = "templates"

    # Primary Key
    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
        comment="Unique template ID"
    )

    # Foreign Key to User
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who generated this template"
    )

    # Template Content
    pdf_url = Column(
        String(500),
        nullable=False,
        comment="Supabase Storage URL for resume PDF"
    )

    template_text = Column(
        Text,
        nullable=False,
        comment="Generated template content"
    )

    user_instructions = Column(
        Text,
        nullable=False,
        comment="User guidance for template generation"
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="When the template was generated"
    )

    # Relationships
    user = relationship(
        "User",
        back_populates="templates"
    )

    # Indexes for efficient queries
    __table_args__ = (
        Index('ix_templates_user_id', 'user_id'),
        Index('ix_templates_created_at', 'created_at', postgresql_using='btree'),
        Index('ix_templates_user_created', 'user_id', 'created_at'),
    )

    def __repr__(self) -> str:
        """String representation of Template model."""
        return (
            f"<Template(id={self.id}, user_id={self.user_id}, "
            f"created_at={self.created_at})>"
        )

    def to_dict(self) -> dict:
        """
        Convert template model to dictionary.

        Returns:
            dict: Template data as dictionary
        """
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "pdf_url": self.pdf_url,
            "template_text": self.template_text,
            "user_instructions": self.user_instructions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
