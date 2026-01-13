"""
Authentication and user-related Pydantic schemas.

These schemas define the structure for authentication requests/responses
and user profile data using Pydantic v2.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator


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
    Request body for user initialization.

    The user ID and email come from the JWT token. The display name
    is auto-derived by the frontend from OAuth provider data (e.g.,
    Google full name) or falls back to the email username.
    """

    display_name: str

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
    application-specific fields like generation_count and template_count.
    """

    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    generation_count: int
    template_count: int
    onboarded: bool
    email_template: str | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,  # Allows creating from SQLAlchemy models
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "display_name": "John Doe",
                "generation_count": 5,
                "template_count": 3,
                "onboarded": False,
                "email_template": "Dear {{professor_name}}, ...",
                "created_at": "2024-01-13T10:30:00Z",
            }
        },
    )


class TemplateUpdate(BaseModel):
    """
    Request body for updating email template.

    Validates template content to prevent:
    - Extremely large templates that could cause storage/performance issues
    - Empty or whitespace-only templates
    - Malicious content injection
    """

    template: str = Field(
        ...,
        min_length=1,
        max_length=10000,  # Reasonable limit for email template (PostgreSQL text fields can be gigabytes)
        description="Email template with variable placeholders (e.g., {{professor_name}})",
    )

    @field_validator("template")
    @classmethod
    def validate_template_not_empty(cls, v: str) -> str:
        """Ensure template contains actual content, not just whitespace."""
        if not v.strip():
            raise ValueError("Template cannot be empty or whitespace only")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "template": "Dear {{professor_name}},\n\nI am writing to express my interest in {{research_area}}...",
            }
        }
    )
