"""
Email Composer Database Utilities

Database operations for writing composed emails.
"""

import logfire
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from models.email import Email
from database.session import create_session


async def write_email_to_db(
    user_id: UUID,
    recipient_name: str,
    recipient_interest: str,
    email_content: str
) -> Optional[UUID]:
    """
    Write composed email to database.

    CRITICAL: This is the ONLY database write in the pipeline.
    The email_id must be returned and set in pipeline_data.metadata["email_id"]
    for the PipelineRunner to track the job completion.

    Args:
        user_id: User who generated the email
        recipient_name: Recipient's name
        recipient_interest: Recipient's research interest
        email_content: Final composed email text

    Returns:
        Email UUID if successful, None if failed

    Raises:
        SQLAlchemyError: Database errors are logged and re-raised
    """
    logfire.info(
        "Writing email to database",
        user_id=str(user_id),
        recipient_name=recipient_name,
        content_length=len(email_content)
    )

    try:
        # Get database session
        db: Session = create_session()

        try:
            # Create email record
            email = Email(
                user_id=user_id,
                recipient_name=recipient_name,
                recipient_interest=recipient_interest,
                email_message=email_content
            )

            # Add and commit
            db.add(email)
            db.commit()
            db.refresh(email)

            email_id = email.id

            logfire.info(
                "Email written to database successfully",
                email_id=str(email_id),
                user_id=str(user_id),
                recipient_name=recipient_name
            )

            return email_id

        except SQLAlchemyError as e:
            # Rollback on error
            db.rollback()

            logfire.error(
                "Database error writing email",
                error=str(e),
                error_type=type(e).__name__,
                user_id=str(user_id)
            )

            raise

        finally:
            # Close session
            db.close()

    except Exception as e:
        logfire.error(
            "Unexpected error writing email to database",
            error=str(e),
            error_type=type(e).__name__,
            user_id=str(user_id)
        )

        # Return None on failure
        return None


async def increment_user_generation_count(
    user_id: UUID,
    db: Optional[Session] = None
) -> bool:
    """
    Increment user's generation count.

    Optional operation - doesn't fail pipeline if unsuccessful.

    Args:
        user_id: User UUID
        db: Optional existing database session

    Returns:
        True if successful, False otherwise
    """
    close_session = False

    try:
        # Get or use provided session
        if db is None:
            db = create_session()
            close_session = True

        # Import User model here to avoid circular dependency
        from models.user import User

        # Fetch user
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            logfire.warning(
                "User not found for generation count increment",
                user_id=str(user_id)
            )
            return False

        # Increment count
        user.generation_count = (user.generation_count or 0) + 1

        db.commit()

        logfire.info(
            "User generation count incremented",
            user_id=str(user_id),
            new_count=user.generation_count
        )

        return True

    except Exception as e:
        logfire.error(
            "Error incrementing user generation count",
            error=str(e),
            user_id=str(user_id)
        )

        if db:
            db.rollback()

        return False

    finally:
        if close_session and db:
            db.close()
