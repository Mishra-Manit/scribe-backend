from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AdminOverview(BaseModel):
    total_users: int
    total_emails: int
    success_rate: float
    avg_gen_time_seconds: float
    total_templates: int
    confidence_rate: float
    error_count: int
    emails_this_week: int
    active_users_this_week: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_users": 142,
                "total_emails": 3801,
                "success_rate": 98.7,
                "avg_gen_time_seconds": 12.4,
                "total_templates": 89,
                "confidence_rate": 76.3,
                "error_count": 49,
                "emails_this_week": 312,
                "active_users_this_week": 28,
            }
        }
    )


class AdminUser(BaseModel):
    id: str
    email: str
    display_name: str | None
    generation_count: int
    template_count: int
    onboarded: bool
    created_at: datetime
    actual_email_count: int
    queue_submissions: int
    failed_count: int
    email_template: str | None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "display_name": "Jane Doe",
                "generation_count": 42,
                "template_count": 3,
                "onboarded": True,
                "created_at": "2025-01-13T10:30:00Z",
                "actual_email_count": 38,
                "queue_submissions": 45,
                "failed_count": 7,
            }
        },
    )


class AdminEmail(BaseModel):
    id: str
    recipient_name: str
    recipient_interest: str
    email_message: str
    template_type: str | None
    is_confident: bool
    metadata: dict | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "recipient_name": "Dr. Jane Smith",
                "recipient_interest": "reinforcement learning",
                "email_message": "Dear Dr. Smith, ...",
                "template_type": "research",
                "is_confident": True,
                "metadata": {"papers": ["paper1"]},
                "created_at": "2025-01-13T10:30:00Z",
            }
        },
    )


class PaginatedEmails(BaseModel):
    items: list[AdminEmail]
    total: int
    page: int
    per_page: int
    pages: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [],
                "total": 100,
                "page": 1,
                "per_page": 20,
                "pages": 5,
            }
        }
    )


class AdminTemplate(BaseModel):
    id: str
    template_text: str
    user_instructions: str | None
    pdf_url: str | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440002",
                "template_text": "Dear {{professor_name}}, ...",
                "user_instructions": "Professional academic tone",
                "pdf_url": "https://storage.example.com/resume.pdf",
                "created_at": "2025-01-13T10:30:00Z",
            }
        },
    )


class AdminQueueItem(BaseModel):
    id: str
    recipient_name: str
    recipient_interest: str
    status: str
    current_step: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440003",
                "recipient_name": "Dr. Jane Smith",
                "recipient_interest": "machine learning",
                "status": "completed",
                "current_step": None,
                "error_message": None,
                "started_at": "2025-01-13T10:30:00Z",
                "completed_at": "2025-01-13T10:30:14Z",
                "created_at": "2025-01-13T10:29:58Z",
            }
        },
    )


class AdminActivity(BaseModel):
    week: str
    emails_generated: int
    active_users: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "week": "2025-01-06",
                "emails_generated": 312,
                "active_users": 28,
            }
        }
    )


class AdminError(BaseModel):
    id: str
    user_email: str
    user_display_name: str | None
    recipient_name: str
    current_step: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440004",
                "user_email": "user@example.com",
                "user_display_name": "Jane Doe",
                "recipient_name": "Dr. Smith",
                "current_step": "web_scraper",
                "error_message": "Playwright timeout after 30s",
                "created_at": "2025-01-13T10:30:00Z",
                "started_at": "2025-01-13T10:29:58Z",
            }
        }
    )
