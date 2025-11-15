"""
Email Composer Step Models

Pydantic models for email generation and validation.
"""

from typing import List
from pydantic import BaseModel, Field, field_validator


class EmailValidationResult(BaseModel):
    """Result of email quality validation."""

    is_valid: bool = Field(
        description="True if email passes all validation checks"
    )

    issues: List[str] = Field(
        description="List of validation issues found",
        default_factory=list
    )

    warnings: List[str] = Field(
        description="Non-fatal warnings",
        default_factory=list
    )

    mentions_publications: bool = Field(
        description="True if email mentions specific publications",
        default=False
    )

    has_placeholders: bool = Field(
        description="True if unfilled placeholders remain",
        default=False
    )

    word_count: int = Field(
        description="Word count of email",
        ge=0
    )

    tone_matches_template: bool = Field(
        description="True if tone matches original template",
        default=True
    )


class ComposedEmail(BaseModel):
    """Final composed email ready for database storage."""

    email_content: str = Field(
        description="Final email text",
        min_length=50,
        max_length=10000
    )

    validation_result: EmailValidationResult = Field(
        description="Validation result"
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
