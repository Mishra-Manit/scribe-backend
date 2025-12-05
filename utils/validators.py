"""
Validation utility functions.
Provides reusable validation helpers for common database operations.
"""

from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import HTTPException, status


def validate_template_ownership(db: Session, template_id: UUID, user_id: UUID):
    """
    Validate that a template exists and belongs to the specified user.

    Args:
        db: Database session
        template_id: Template UUID to validate
        user_id: User UUID who should own the template

    Returns:
        Template object if found and owned by user

    Raises:
        HTTPException: 404 if template not found or not owned by user
    """
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
