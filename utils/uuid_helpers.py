"""Helpers for converting between UUID objects and strings."""

from uuid import UUID
from typing import Union


def ensure_uuid(value: Union[str, UUID]) -> UUID:
    """Return a UUID object, coercing from string when needed."""
    if isinstance(value, UUID):
        return value

    try:
        return UUID(value)
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid UUID format: {value}") from e


def ensure_str(value: Union[str, UUID]) -> str:
    """Return the string form of a UUID value."""
    return str(value)


def validate_uuid_format(value: str) -> bool:
    """Return True when value is a valid UUID string."""
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
