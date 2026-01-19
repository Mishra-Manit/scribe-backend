"""
Pydantic schemas for queue API endpoints.

These models validate API requests and responses for the
database-backed email generation queue system.
"""

from datetime import datetime
from typing import List
from pydantic import BaseModel, Field, ConfigDict


# ===================================================================
# REQUEST SCHEMAS
# ===================================================================

class BatchItem(BaseModel):
    """Single item in a batch submission."""

    recipient_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Full name of recipient"
    )

    recipient_interest: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Research area or interest for personalization"
    )


class BatchSubmitRequest(BaseModel):
    """
    Request body for POST /api/queue/batch

    Submit multiple items to the email generation queue.
    """

    items: List[BatchItem] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of items to queue (max 100)"
    )

    email_template: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Email template with placeholders"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {"recipient_name": "Dr. Jane Smith", "recipient_interest": "machine learning"},
                    {"recipient_name": "Prof. John Doe", "recipient_interest": "computer vision"}
                ],
                "email_template": "Hey {{name}}, I loved your work on {{research}}!"
            }
        }
    )


# ===================================================================
# RESPONSE SCHEMAS
# ===================================================================

class BatchSubmitResponse(BaseModel):
    """
    Response from POST /api/queue/batch

    Returns list of created queue item IDs.
    """

    queue_item_ids: List[str] = Field(
        ...,
        description="UUIDs of created queue items"
    )

    message: str = Field(
        ...,
        description="Success message"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "queue_item_ids": ["abc-123", "def-456"],
                "message": "Successfully queued 2 items"
            }
        }
    )


class QueueItemResponse(BaseModel):
    """
    Response item for GET /api/queue/

    Represents a single queue item with its current status.
    """

    id: str = Field(..., description="Queue item UUID")

    recipient_name: str = Field(..., description="Recipient name")

    status: str = Field(
        ...,
        description="Status: pending, processing, completed, failed"
    )

    position: int | None = Field(
        None,
        description="Position in queue (1-indexed, None if not pending)"
    )

    email_id: str | None = Field(
        None,
        description="Generated email UUID (if completed)"
    )

    error_message: str | None = Field(
        None,
        description="Error details (if failed)"
    )

    current_step: str | None = Field(
        None,
        description="Current pipeline step (if processing)"
    )

    created_at: datetime = Field(..., description="When item was queued")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "recipient_name": "Dr. Jane Smith",
                "status": "processing",
                "position": None,
                "email_id": None,
                "error_message": None,
                "current_step": "web_scraper",
                "created_at": "2025-01-13T10:30:00Z"
            }
        }
    )


class CancelQueueItemResponse(BaseModel):
    """Response from DELETE /api/queue/{id}"""

    message: str = Field(..., description="Confirmation message")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Queue item cancelled"
            }
        }
    )
