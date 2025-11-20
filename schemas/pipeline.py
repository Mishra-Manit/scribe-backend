"""
Pydantic schemas for pipeline API endpoints.

These models validate API requests and responses for the email
generation pipeline system.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any



# ===================================================================
# REQUEST SCHEMAS
# ===================================================================

class GenerateEmailRequest(BaseModel):
    """
    Request body for POST /api/email/generate

    Initiates asynchronous email generation pipeline.
    """

    email_template: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Email template with placeholders like {{name}}, {{research}}"
    )

    recipient_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Full name of recipient (e.g., 'Dr. Jane Smith')"
    )

    recipient_interest: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Research area or interest (e.g., 'machine learning')"
    )


    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email_template": "Hey {{name}}, I loved your work on {{research}}!",
                "recipient_name": "Dr. Jane Smith",
                "recipient_interest": "machine learning"
            }
        }
    )


# ===================================================================
# RESPONSE SCHEMAS
# ===================================================================

class GenerateEmailResponse(BaseModel):
    """
    Response from POST /api/email/generate

    Returns Celery task_id for status polling.
    """

    task_id: str = Field(
        ...,
        description="Celery task ID for polling status"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "abc-123-def-456"
            }
        }
    )


class TaskStatusResponse(BaseModel):
    """
    Response from GET /api/email/status/{task_id}

    Returns current Celery task state and result if complete.
    """

    task_id: str = Field(..., description="Celery task ID")

    status: str = Field(
        ...,
        description="Task status: PENDING, STARTED, SUCCESS, FAILURE"
    )

    result: Dict[str, Any] | None = Field(
        None,
        description="Result data when status=SUCCESS (contains email_id)"
    )

    error: str | None = Field(
        None,
        description="Error message when status=FAILURE"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "abc-123",
                "status": "SUCCESS",
                "result": {
                    "email_id": "email-789",
                    "status": "completed"
                },
                "error": None
            }
        }
    )


class EmailResponse(BaseModel):
    """
    Response from GET /api/email/{email_id}

    Returns complete email record from database.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    recipient_name: str
    recipient_interest: str
    email_message: str
    template_type: str
    email_metadata: Dict[str, Any] | None = Field(
        serialization_alias="metadata",
        description="Structured generation metadata (papers, sources, timings)"
    )
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy models
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "660e8400-e29b-41d4-a716-446655440001",
                "recipient_name": "Dr. Jane Smith",
                "recipient_interest": "machine learning",
                "email_message": "Hey Dr. Smith, I loved your paper on neural networks...",
                "template_type": "research",
                "metadata": {
                    "papers_used": ["Neural Networks for Computer Vision"],
                    "sources": ["https://university.edu/faculty/smith"],
                    "generation_time": 4.2
                },
                "created_at": "2025-01-13T10:30:00Z"
            }
        }
    )
