"""
Pydantic schemas for request/response validation.
"""

from schemas.auth import SupabaseUser, UserResponse, UserInit, AuthError
from schemas.pipeline import (
    GenerateEmailRequest,
    GenerateEmailResponse,
    TaskStatusResponse,
    EmailResponse,
)
from schemas.template import (
    GenerateTemplateRequest,
    TemplateResponse,
    ResumeUrlResponse,
)

__all__ = [
    # Auth schemas
    "SupabaseUser",
    "UserResponse",
    "UserInit",
    "AuthError",

    # Pipeline schemas
    "GenerateEmailRequest",
    "GenerateEmailResponse",
    "TaskStatusResponse",
    "EmailResponse",

    # Template schemas
    "GenerateTemplateRequest",
    "TemplateResponse",
    "ResumeUrlResponse",
]
