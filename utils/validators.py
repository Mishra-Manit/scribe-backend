"""
Validation utility functions.
Provides reusable validation helpers for common database operations.
"""

from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import HTTPException, status


def validate_template_ownership(db: Session, template_id: UUID, user_id: UUID):
    """Verify user owns template, raise 404 if not found or unauthorized."""
    from models.template import Template

    # Query with authorization filter (returns 404 for both cases)
    template = db.query(Template).filter(
        Template.id == template_id,
        Template.user_id == user_id
    ).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    return template
