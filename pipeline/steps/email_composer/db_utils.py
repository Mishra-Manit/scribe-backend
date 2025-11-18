"""
Email Composer Database Utilities

Database operations for writing composed emails.
"""

import logfire
from typing import Optional
from uuid import UUID

from models.email import Email
from models.user import User
from database.session import get_db_context
from pipeline.models.core import TemplateType


async def write_email_to_db(
    user_id: UUID,
    recipient_name: str,
    recipient_interest: str,
    email_content: str,
    template_type: TemplateType,
    metadata: dict
) -> Optional[UUID]:
    """
    Write composed email to database.

    Args:
        user_id: User who generated the email
        recipient_name: Recipient's name
        recipient_interest: Recipient's research interest
        email_content: Final composed email text
        template_type: Type of template used (RESEARCH, BOOK, GENERAL)
        metadata: Structured generation metadata (papers, sources, timings)

    Returns:
        Email UUID if successful, None if failed
    """
    logfire.info(
        "Writing email to database",
        user_id=str(user_id),
        recipient_name=recipient_name,
        content_length=len(email_content)
    )

    try:
        with get_db_context() as db:
            # Create and add email record
            email = Email(
                user_id=user_id,
                recipient_name=recipient_name,
                recipient_interest=recipient_interest,
                email_message=email_content,
                template_type=template_type,
                email_metadata=metadata
            )
            db.add(email)
            db.flush()  # Get the ID before commit

            email_id = email.id

            logfire.info(
                "Email written to database successfully",
                email_id=str(email_id),
                user_id=str(user_id),
                recipient_name=recipient_name
            )

            return email_id

    except Exception as e:
        logfire.error(
            "Error writing email to database",
            error=str(e),
            error_type=type(e).__name__,
            user_id=str(user_id)
        )
        return None


async def increment_user_generation_count(user_id: UUID) -> bool:
    """
    Increment user's generation count.

    Optional operation - doesn't fail pipeline if unsuccessful.

    Args:
        user_id: User UUID

    Returns:
        True if successful, False otherwise
    """
    try:
        with get_db_context() as db:
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
            error_type=type(e).__name__,
            user_id=str(user_id)
        )
        return False
