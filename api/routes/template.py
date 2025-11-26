"""Template management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logfire

from models.user import User
from models.template import Template
from database import get_db
from api.dependencies import get_current_user
from schemas.template import GenerateTemplateRequest, TemplateResponse
from services.template_generator import generate_template_from_resume
from utils.uuid_helpers import ensure_uuid


router = APIRouter(prefix="/api/templates", tags=["Templates"])


@router.post("/", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    request: GenerateTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate template from resume and user instructions.

    Args:
        request: Template generation request with pdf_url and instructions
        current_user: Authenticated user (injected by dependency)
        db: Database session (injected by dependency)

    Returns:
        TemplateResponse: Generated template with metadata

    Raises:
        HTTPException 429: If user has reached 5 template limit
        HTTPException 400: If PDF parsing fails or generation fails
        HTTPException 500: If database operation fails
    """
    with logfire.span("api.create_template", user_id=str(current_user.id)):
        # Check template generation limit
        if current_user.template_count >= 5:
            logfire.warning(
                "Template generation limit reached",
                user_id=str(current_user.id),
                template_count=current_user.template_count
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Template generation limit reached. Maximum 5 templates allowed per user."
            )

        try:
            # Generate template (synchronous, 5-15 seconds)
            logfire.info(
                "Starting template generation",
                user_id=str(current_user.id),
                pdf_url=request.pdf_url
            )

            template_text = await generate_template_from_resume(
                pdf_url=request.pdf_url,
                user_instructions=request.user_instructions
            )

            # Create database record
            new_template = Template(
                user_id=current_user.id,
                pdf_url=request.pdf_url,
                template_text=template_text,
                user_instructions=request.user_instructions
            )

            db.add(new_template)
            current_user.template_count += 1
            db.commit()
            db.refresh(new_template)

            logfire.info(
                "Template created successfully",
                template_id=str(new_template.id),
                user_id=str(current_user.id),
                new_template_count=current_user.template_count
            )

            return new_template

        except ValueError as e:
            # PDF parsing errors from template_generator
            db.rollback()
            logfire.error(
                "Template generation failed - PDF error",
                user_id=str(current_user.id),
                error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Template generation failed: {str(e)}"
            )
        except Exception as e:
            # LLM or other errors
            db.rollback()
            logfire.error(
                "Template creation failed",
                user_id=str(current_user.id),
                error=str(e),
                error_type=type(e).__name__
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create template"
            )


@router.get("/", response_model=List[TemplateResponse])
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0
):
    """
    List user's templates (paginated, newest first).

    Args:
        current_user: Authenticated user (injected by dependency)
        db: Database session (injected by dependency)
        limit: Maximum number of templates to return (default: 20, max: 100)
        offset: Number of templates to skip (default: 0)

    Returns:
        List[TemplateResponse]: List of user's templates

    Raises:
        HTTPException 401: If JWT token is invalid
        HTTPException 403: If user is not initialized
    """
    if limit > 100:
        limit = 100

    with logfire.span(
        "api.list_templates",
        user_id=str(current_user.id),
        limit=limit,
        offset=offset
    ):
        templates = db.query(Template).filter(
            Template.user_id == current_user.id
        ).order_by(
            Template.created_at.desc()
        ).limit(limit).offset(offset).all()

        logfire.info(
            "Templates retrieved",
            user_id=str(current_user.id),
            count=len(templates),
            limit=limit,
            offset=offset
        )

        return templates


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get specific template by ID.

    Args:
        template_id: UUID of the template
        current_user: Authenticated user (injected by dependency)
        db: Database session (injected by dependency)

    Returns:
        TemplateResponse: Template data

    Raises:
        HTTPException 400: If template_id is not a valid UUID
        HTTPException 404: If template doesn't exist or user doesn't own it
    """
    # Validate UUID format
    try:
        template_uuid = ensure_uuid(template_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid template ID format: {str(e)}"
        )

    with logfire.span(
        "api.get_template",
        template_id=template_id,
        user_id=str(current_user.id)
    ):
        # Query with authorization filter
        template = db.query(Template).filter(
            Template.id == template_uuid,
            Template.user_id == current_user.id
        ).first()

        if not template:
            logfire.warning(
                "Template not found or unauthorized",
                template_id=template_id,
                user_id=str(current_user.id)
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )

        logfire.info(
            "Template retrieved",
            template_id=template_id,
            user_id=str(current_user.id)
        )

        return template
