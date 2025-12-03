"""
Email Composer Step Models

Pydantic models for email generation.
"""

from pydantic import BaseModel, Field, field_validator

class ComposedEmail(BaseModel):
    """Final composed email ready for database storage."""

    email_content: str = Field(
        description="Final email text",
        min_length=1
    )

    is_confident: bool = Field(
        default=False,
        description="True if sufficient context was available for personalization"
    )

    generation_metadata: dict = Field(
        description="Metadata about generation process",
        default_factory=dict
    )

    @field_validator("email_content")
    @classmethod
    def validate_email_content(cls, v: str) -> str:
        """Ensure email is non-empty after stripping"""
        if not v.strip():
            raise ValueError("Email content cannot be empty")
        return v.strip()
