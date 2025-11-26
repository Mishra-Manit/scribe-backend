"""
Validation utility functions.
Provides reusable validation helpers for common database operations.
"""

from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from models.user import User
from models.email import Email


def validate_user_exists(db: Session, user_id: UUID) -> User:
    """
    Validate that a user exists in the database.

    This is a common pattern used across API endpoints and pipeline steps
    to ensure a user exists before performing operations on their behalf.

    Args:
        db: Database session
        user_id: User UUID to validate

    Returns:
        User object if found

    Raises:
        HTTPException: 404 if user not found

    Example:
        >>> from database import get_db
        >>> from uuid import UUID
        >>>
        >>> with get_db() as db:
        >>>     user = validate_user_exists(db, UUID("..."))
        >>>     # Proceed with operations on user
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}"
        )

    return user


def validate_email_ownership(db: Session, email_id: UUID, user_id: UUID) -> Email:
    """
    Validate that an email exists and belongs to the specified user.

    This combines two common checks:
    1. Does the email exist?
    2. Does the user have permission to access it?

    Args:
        db: Database session
        email_id: Email UUID to validate
        user_id: User UUID who should own the email

    Returns:
        Email object if found and owned by user

    Raises:
        HTTPException: 404 if email not found, 403 if not owned by user

    Example:
        >>> from database import get_db
        >>> from uuid import UUID
        >>>
        >>> with get_db() as db:
        >>>     email = validate_email_ownership(
        >>>         db,
        >>>         email_id=UUID("..."),
        >>>         user_id=UUID("...")
        >>>     )
        >>>     # Email exists and user has permission
    """
    # First check if email exists
    email = db.query(Email).filter(Email.id == email_id).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email not found: {email_id}"
        )

    # Then check ownership
    if email.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this email"
        )

    return email


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


def validate_user_exists_soft(db: Session, user_id: UUID) -> bool:
    """
    Soft validation that returns boolean instead of raising exception.

    Useful for optional operations where you want to check user existence
    without failing the entire operation.

    Args:
        db: Database session
        user_id: User UUID to validate

    Returns:
        True if user exists, False otherwise

    Example:
        >>> from database import get_db
        >>> from uuid import UUID
        >>>
        >>> with get_db() as db:
        >>>     if validate_user_exists_soft(db, UUID("...")):
        >>>         # User exists, proceed with optional operation
        >>>         pass
        >>>     else:
        >>>         # User doesn't exist, skip optional operation
        >>>         pass
    """
    user = db.query(User).filter(User.id == user_id).first()
    return user is not None
