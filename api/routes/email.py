"""
Email generation API endpoints.

This module provides endpoints for asynchronous email generation using
Celery workers and the multi-step pipeline system.

All endpoints require valid Supabase JWT authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from celery.result import AsyncResult
from typing import List
import logfire

from models.user import User
from models.email import Email
from database import get_db
from api.dependencies import get_current_user, PaginationParams
from schemas.pipeline import (
    GenerateEmailRequest,
    GenerateEmailResponse,
    TaskStatusResponse,
    EmailResponse
)
from tasks.email_tasks import generate_email_task
from celery_config import celery_app
from utils.uuid_helpers import ensure_uuid


router = APIRouter(prefix="/api/email", tags=["Email Generation"])


@router.post("/generate", response_model=GenerateEmailResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_email(
    request: GenerateEmailRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Enqueue an email generation job.

    This endpoint dispatches an asynchronous Celery task to generate a personalized
    email using the multi-step pipeline (TemplateParser → WebScraper → ArxivEnricher
    → EmailComposer). The task executes in the background, allowing the client to
    poll for status updates.

    **Authentication**: Requires valid Supabase JWT token in Authorization header.

    **Pipeline Flow**:
    1. Template analysis to extract search terms
    2. Web scraping for recipient information
    3. ArXiv paper enrichment (if template_type=RESEARCH)
    4. Email composition using Anthropic Claude API

    Args:
        request: Email generation request with template and recipient info
        current_user: Authenticated user from database (injected by dependency)

    Returns:
        GenerateEmailResponse: Contains task_id for status polling

    Raises:
        HTTPException 401: If JWT token is invalid (handled by dependency)
        HTTPException 403: If user is not initialized (handled by dependency)
        HTTPException 422: If request validation fails
    """
    with logfire.span(
        "api.generate_email",
        user_id=str(current_user.id),
        recipient_name=request.recipient_name
    ):
        # Dispatch Celery task to background worker
        task = generate_email_task.apply_async(
            kwargs={
                "user_id": str(current_user.id),
                "email_template": request.email_template,
                "recipient_name": request.recipient_name,
                "recipient_interest": request.recipient_interest
            },
            queue="email_default"  # Use default queue (could route to email_high for premium users)
        )

        return GenerateEmailResponse(task_id=task.id)


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Check the status of an email generation task.

    Queries the Celery result backend (Redis) to get the current state of a task.
    Returns different data depending on task state:

    - **PENDING**: Task queued but not started
    - **STARTED**: Task executing (includes current step info)
    - **SUCCESS**: Task completed (includes email_id)
    - **FAILURE**: Task failed (includes error message)

    **Authentication**: Requires valid Supabase JWT token in Authorization header.

    **Note**: Task results expire after 1 hour (configurable in celery_config.py).
    After expiration, status will return PENDING even if task completed.

    Args:
        task_id: Celery task ID returned from /generate endpoint
        current_user: Authenticated user from database (injected by dependency)

    Returns:
        TaskStatusResponse: Current task state and result/error if applicable

    Raises:
        HTTPException 401: If JWT token is invalid (handled by dependency)
        HTTPException 403: If user is not initialized (handled by dependency)
    """
    with logfire.span(
        "api.task_status",
        task_id=task_id,
        user_id=str(current_user.id)
    ):
        # Query Celery result backend
        result = AsyncResult(task_id, app=celery_app)

        # Prepare response data
        response_data = {
            "task_id": task_id,
            "status": result.state,
            "result": None,
            "error": None
        }

        if result.state == "SUCCESS":
            # Task completed successfully
            response_data["result"] = result.result

        elif result.state == "FAILURE":
            # Task failed - extract error message from metadata
            if not isinstance(result.info, dict):
                response_data["error"] = str(result.info) if result.info else "Unknown error"
            else:
                response_data["error"] = {
                    "message": result.info.get("exc_message", "Unknown error"),
                    "type": result.info.get("exc_type", "Error"),
                    "failed_step": result.info.get("failed_step")
                }

        elif result.state == "STARTED":
            # Task is running - include progress information
            if result.info:
                response_data["result"] = {
                    "current_step": result.info.get("current_step"),
                    "step_status": result.info.get("step_status"),
                    "step_timings": result.info.get("step_timings", {})
                }

        elif result.state == "PENDING":
            # Task queued or result expired
            pass

        return TaskStatusResponse(**response_data)


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve a generated email by ID.

    Fetches a complete email record from the database. Only returns emails
    owned by the authenticated user (enforces authorization).

    **Authentication**: Requires valid Supabase JWT token in Authorization header.

    **Authorization**: Users can only access their own emails. Attempting to
    access another user's email returns 404 (not 403 to avoid information leakage).

    Args:
        email_id: UUID of the email record
        current_user: Authenticated user from database (injected by dependency)
        db: Database session (injected by dependency)

    Returns:
        EmailResponse: Complete email record with metadata

    Raises:
        HTTPException 401: If JWT token is invalid (handled by dependency)
        HTTPException 403: If user is not initialized (handled by dependency)
        HTTPException 404: If email doesn't exist or user doesn't own it
    """
    # Validate UUID format early
    try:
        email_uuid = ensure_uuid(email_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid email ID format: {str(e)}"
        )

    with logfire.span(
        "api.get_email",
        email_id=email_id,
        user_id=str(current_user.id)
    ):
        # Query database for email with user_id filter (authorization)
        email = db.query(Email).filter(
            Email.id == email_uuid,
            Email.user_id == current_user.id
        ).first()

        if not email:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email not found or you don't have permission to access it"
            )

        return email


@router.get("/", response_model=List[EmailResponse])
async def get_email_history(
    pagination: PaginationParams,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the authenticated user's email generation history.

    Returns a paginated list of all emails generated by the current user,
    ordered by creation date (newest first).

    **Authentication**: Requires valid Supabase JWT token in Authorization header.

    **Pagination**: Use limit and offset query parameters for pagination.
    Default limit is 20 emails per page.

    Args:
        pagination: Pagination parameters (limit and offset, injected by dependency)
        current_user: Authenticated user from database (injected by dependency)
        db: Database session (injected by dependency)

    Returns:
        List[EmailResponse]: List of email records owned by the user

    Raises:
        HTTPException 401: If JWT token is invalid (handled by dependency)
        HTTPException 403: If user is not initialized (handled by dependency)
        HTTPException 422: If limit/offset validation fails
    """
    limit = pagination["limit"]
    offset = pagination["offset"]

    with logfire.span(
        "api.email_history",
        user_id=str(current_user.id),
        limit=limit,
        offset=offset
    ):
        # Query emails with pagination
        emails = db.query(Email).filter(
            Email.user_id == current_user.id
        ).order_by(
            Email.created_at.desc()
        ).limit(limit).offset(offset).all()

        return emails
