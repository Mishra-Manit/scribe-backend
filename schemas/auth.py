"""
Authentication and user-related Pydantic schemas.

These schemas define the structure for authentication requests/responses
and user profile data using Pydantic v2.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict


class SupabaseUser(BaseModel):
    """
    User data extracted from validated Supabase JWT token.

    This represents the authenticated user from Supabase Auth,
    not necessarily a user in our local database.
    """

    id: uuid.UUID
    email: EmailStr

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
            }
        },
    )


class UserInit(BaseModel):
    """
    Optional request body for user initialization.

    The user ID and email come from the JWT token, but the user
    can optionally provide a display name during initialization.
    """

    display_name: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "John Doe",
            }
        }
    )


class UserResponse(BaseModel):
    """
    User profile response schema.

    This is returned from our local database and includes
    application-specific fields like generation_count.
    """

    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    generation_count: int
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,  # Allows creating from SQLAlchemy models
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "display_name": "John Doe",
                "generation_count": 5,
                "created_at": "2024-01-13T10:30:00Z",
            }
        },
    )


class AuthError(BaseModel):
    """
    Standardized error response for authentication failures.
    """

    detail: str
    error_code: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Invalid or expired token",
                "error_code": "TOKEN_EXPIRED",
            }
        }
    )
