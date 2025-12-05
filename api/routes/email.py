"""Email generation API endpoints with async Celery pipeline."""

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
    Enqueue background task to generate personalized email via multi-step pipeline.

    Returns task_id for polling via /status endpoint.
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
    Check task status from Celery backend.

    Returns PENDING/STARTED/SUCCESS/FAILURE with step info, result, or error.
    Note: Results expire after 1 hour (see celery_config.py).
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
    Retrieve generated email by ID. Users can only access their own emails.

    Returns 404 if email doesn't exist or belongs to another user.
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
    """Get user's email generation history, paginated and ordered by newest first."""
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
