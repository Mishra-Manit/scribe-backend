"""Database retry helpers for transient SQLAlchemy OperationalError failures."""

import asyncio
import time
from typing import Awaitable, Callable, TypeVar
from functools import wraps

import logfire
from sqlalchemy.exc import OperationalError

from database.base import engine

T = TypeVar("T")

# Centralized retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 0.5  # Fixed delay between attempts


def retry_on_db_error(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator: retry sync DB operations on OperationalError with a fixed delay."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)

            except OperationalError as e:
                error_msg = str(e)

                if attempt < MAX_RETRIES:
                    logfire.warning(
                        "Database operation failed, retrying",
                        function=func.__name__,
                        error=error_msg[:200],
                        attempt=attempt,
                        max_attempts=MAX_RETRIES,
                        retry_delay=RETRY_DELAY_SECONDS,
                    )
                    engine.dispose()  # Clear stale connections
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    logfire.error(
                        "Database operation failed after all retries",
                        function=func.__name__,
                        error=error_msg[:200],
                        attempts=MAX_RETRIES,
                    )
                    raise

        raise RuntimeError("Unreachable: retry loop must return or raise")  # pragma: no cover

    return wrapper


async def retry_on_db_error_async(func: Callable[[], Awaitable[T]]) -> T:
    """Run an async DB operation with retries on OperationalError and a fixed delay."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await func()

        except OperationalError as e:
            error_msg = str(e)

            if attempt < MAX_RETRIES:
                logfire.warning(
                    "Async database operation failed, retrying",
                    error=error_msg[:200],
                    attempt=attempt,
                    max_attempts=MAX_RETRIES,
                    retry_delay=RETRY_DELAY_SECONDS,
                )
                engine.dispose()  # Clear stale connections
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            else:
                logfire.error(
                    "Async database operation failed after all retries",
                    error=error_msg[:200],
                    attempts=MAX_RETRIES,
                )
                raise

    raise RuntimeError("Unreachable: retry loop must return or raise")  # pragma: no cover
