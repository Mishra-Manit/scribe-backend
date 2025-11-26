"""Template-related Pydantic schemas for the template generation API."""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, HttpUrl


class GenerateTemplateRequest(BaseModel):
    """Request schema for POST /api/templates/"""

    pdf_url: HttpUrl = Field(
        ...,
        description="Public URL to resume PDF in Supabase Storage"
    )

    user_instructions: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="User guidance for template generation (tone, style, focus)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "pdf_url": "https://example.supabase.co/storage/v1/object/public/resumes/user-id/resume.pdf",
                "user_instructions": "Create a warm, enthusiastic template highlighting my ML research experience. Keep it under 200 words."
            }
        }
    )


class TemplateResponse(BaseModel):
    """Response schema for template data."""

    id: uuid.UUID
    user_id: uuid.UUID
    pdf_url: str
    template_text: str
    user_instructions: str
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "660e8400-e29b-41d4-a716-446655440001",
                "pdf_url": "https://example.supabase.co/storage/v1/object/public/resumes/user-id/resume.pdf",
                "template_text": "Dear {{professor_name}},\n\nI hope this email finds you well...",
                "user_instructions": "Warm and enthusiastic tone",
                "created_at": "2025-01-13T10:30:00Z"
            }
        }
    )
