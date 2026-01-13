"""
Email Composer Database Utilities

Database operations for writing composed emails.
"""

import asyncio
from typing import Optional
from uuid import UUID

import logfire
from sqlalchemy.exc import OperationalError

from database.base import engine
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
    metadata: dict,
    is_confident: bool = False
) -> Optional[UUID]:
    """Write composed email to database using thread pool to avoid blocking async event loop."""
    logfire.info(
        "Writing email to database",
        user_id=str(user_id),
        recipient_name=recipient_name,
        content_length=len(email_content),
        is_confident=is_confident
    )

    def _sync_write() -> UUID:
        """Synchronous database write operation executed in thread pool."""
        with get_db_context() as db:
            # Create and add email record
            email = Email(
                user_id=user_id,
                recipient_name=recipient_name,
                recipient_interest=recipient_interest,
                email_message=email_content,
                template_type=template_type,
                email_metadata=metadata,
                is_confident=is_confident
            )
            db.add(email)
            db.flush()  # Get the ID before commit

            email_id = email.id
            db.commit()  # Explicit commit

            return email_id

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            # Run blocking DB operation in thread pool to avoid blocking event loop
            email_id = await asyncio.to_thread(_sync_write)

            logfire.info(
                "Email written to database successfully",
                email_id=str(email_id),
                user_id=str(user_id),
                recipient_name=recipient_name
            )

            return email_id

        except OperationalError as e:
            logfire.warning(
                "Operational error writing email to database",
                error=str(e),
                error_type=type(e).__name__,
                user_id=str(user_id),
                attempt=attempt,
                max_attempts=max_attempts,
            )

            # Dispose pool to force fresh connections on retry
            engine.dispose()

            if attempt < max_attempts:
                await asyncio.sleep(1.0 * attempt)
                continue

            logfire.error(
                "Error writing email to database",
                error=str(e),
                error_type=type(e).__name__,
                user_id=str(user_id)
            )
            return None

        except Exception as e:
            logfire.error(
                "Error writing email to database",
                error=str(e),
                error_type=type(e).__name__,
                user_id=str(user_id)
            )
            return None


async def increment_user_generation_count(user_id: UUID) -> bool:
    """Increment user's generation count using thread pool (optional operation, doesn't fail pipeline)."""
    def _sync_increment() -> bool:
        """Synchronous database operation executed in thread pool."""
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
            db.commit()  # Explicit commit

            logfire.info(
                "User generation count incremented",
                user_id=str(user_id),
                new_count=user.generation_count
            )

            return True

    try:
        # Run blocking DB operation in thread pool to avoid blocking event loop
        return await asyncio.to_thread(_sync_increment)

    except Exception as e:
        logfire.error(
            "Error incrementing user generation count",
            error=str(e),
            error_type=type(e).__name__,
            user_id=str(user_id)
        )
        return False
