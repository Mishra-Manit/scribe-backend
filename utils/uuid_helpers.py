"""Helper for converting string UUIDs to UUID objects."""

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
