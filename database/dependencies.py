"""
FastAPI dependency injection for database sessions.
Provides database session dependencies for API endpoints with retry logic.
"""

import time
from typing import Generator

import logfire
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from database.base import SessionLocal, engine


MAX_RETRIES = 3
RETRY_DELAY_BASE = 0.5


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session with retry logic.
    Implements exponential backoff for transient connection failures.
    """
    last_exception: OperationalError | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            try:
                yield db
                return
            finally:
                db.close()

        except OperationalError as e:
            last_exception = e
            error_msg = str(e)

            is_retryable = any(
                keyword in error_msg.lower()
                for keyword in ["timeout", "connection refused", "could not connect", "connection reset"]
            )

            if not is_retryable:
                logfire.error(
                    "Database error (non-retryable)",
                    error=error_msg,
                    attempt=attempt,
                )
                raise

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
                logfire.warning(
                    "Database connection failed, retrying",
                    error=error_msg[:200],
                    attempt=attempt,
                    max_attempts=MAX_RETRIES,
                    retry_delay=delay,
                )
                engine.dispose()
                time.sleep(delay)
            else:
                logfire.error(
                    "Database connection failed after all retries",
                    error=error_msg[:200],
                    attempts=MAX_RETRIES,
                )

    if last_exception is not None:
        raise last_exception
