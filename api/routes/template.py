"""Template management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session
from typing import List
import logfire

from models.user import User
from models.template import Template
from database import get_db
from api.dependencies import get_current_user, PaginationParams
from schemas.template import GenerateTemplateRequest, TemplateResponse
from services.template_generator import generate_template_from_resume
from utils.uuid_helpers import ensure_uuid
from utils.validators import validate_template_ownership
from config.settings import settings


router = APIRouter(prefix="/api/templates", tags=["Templates"])


@router.post("/", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    request: GenerateTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate template from resume PDF and user instructions (max 5 templates per user)."""
    with logfire.span("api.create_template", user_id=str(current_user.id)):
        # Check template generation limit
        if current_user.template_count >= settings.template_generation_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Template generation limit reached. Maximum {settings.template_generation_limit} templates allowed per user."
            )

        try:
            # Generate template (synchronous, 5-15 seconds)
            template_text = await generate_template_from_resume(
                pdf_url=str(request.pdf_url),
                user_instructions=request.user_instructions
            )

            # Create database record
            new_template = Template(
                user_id=current_user.id,
                pdf_url=str(request.pdf_url),
                template_text=template_text,
                user_instructions=request.user_instructions
            )

            db.add(new_template)
            db.flush()  # Get template ID before updating counter

            # Atomic counter increment (prevents race conditions)
            db.execute(
                update(User)
                .where(User.id == current_user.id)
                .values(template_count=User.template_count + 1)
            )

            db.commit()
            db.refresh(new_template)
            db.refresh(current_user)  # Refresh to get updated counter

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
    pagination: PaginationParams,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List user's templates, paginated and sorted by newest first."""
    limit = pagination["limit"]
    offset = pagination["offset"]

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

        return templates


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get specific template by ID, verifying user ownership."""
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
        # Validate ownership and retrieve template
        template = validate_template_ownership(
            db=db,
            template_id=template_uuid,
            user_id=current_user.id
        )

        return template
