"""Admin API endpoints — access restricted to the platform owner."""

from datetime import datetime, timedelta, timezone
from typing import List

import logfire
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, text
from sqlalchemy.orm import Session

from api.dependencies import get_supabase_user
from database import get_db
from models.email import Email
from models.queue_item import QueueItem, QueueStatus
from models.template import Template
from models.user import User
from schemas.admin import (
    AdminActivity,
    AdminEmail,
    AdminError,
    AdminOverview,
    AdminQueueItem,
    AdminTemplate,
    AdminUser,
    PaginatedEmails,
)
from schemas.auth import SupabaseUser
from utils.uuid_helpers import ensure_uuid


router = APIRouter(prefix="/api/admin", tags=["Admin"])

_ADMIN_EMAIL = "mshmanit@gmail.com"


async def get_admin_user(
    supabase_user: SupabaseUser = Depends(get_supabase_user),
) -> SupabaseUser:
    incoming_email = str(supabase_user.email).lower().strip()
    logfire.info(
        "admin.access_check",
        incoming_email=incoming_email,
        expected_email=_ADMIN_EMAIL,
        match=incoming_email == _ADMIN_EMAIL,
    )
    if incoming_email != _ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return supabase_user


@router.get("/overview", response_model=AdminOverview)
async def get_overview(
    _: SupabaseUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Aggregate platform statistics."""
    with logfire.span("admin.overview"):
        total_users: int = db.query(func.count(User.id)).scalar() or 0
        total_emails: int = db.query(func.count(Email.id)).scalar() or 0
        total_templates: int = db.query(func.count(Template.id)).scalar() or 0

        non_pending = (
            db.query(func.count(QueueItem.id))
            .filter(QueueItem.status != QueueStatus.PENDING)
            .scalar()
            or 0
        )
        completed = (
            db.query(func.count(QueueItem.id))
            .filter(QueueItem.status == QueueStatus.COMPLETED)
            .scalar()
            or 0
        )
        success_rate = (completed / non_pending * 100) if non_pending else 0.0

        avg_seconds_row = (
            db.query(
                func.avg(
                    func.extract(
                        "epoch",
                        QueueItem.completed_at - QueueItem.started_at,
                    )
                )
            )
            .filter(
                QueueItem.status == QueueStatus.COMPLETED,
                QueueItem.started_at.isnot(None),
                QueueItem.completed_at.isnot(None),
            )
            .scalar()
        )
        avg_gen_time = float(avg_seconds_row) if avg_seconds_row is not None else 0.0

        confident = (
            db.query(func.count(Email.id))
            .filter(Email.is_confident.is_(True))
            .scalar()
            or 0
        )
        confidence_rate = (confident / total_emails * 100) if total_emails else 0.0

        error_count: int = (
            db.query(func.count(QueueItem.id))
            .filter(QueueItem.status == QueueStatus.FAILED)
            .scalar()
            or 0
        )

        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        emails_this_week: int = (
            db.query(func.count(Email.id))
            .filter(Email.created_at >= week_ago)
            .scalar()
            or 0
        )
        active_users_this_week: int = (
            db.query(func.count(distinct(Email.user_id)))
            .filter(Email.created_at >= week_ago)
            .scalar()
            or 0
        )

        return AdminOverview(
            total_users=total_users,
            total_emails=total_emails,
            success_rate=round(success_rate, 2),
            avg_gen_time_seconds=round(avg_gen_time, 2),
            total_templates=total_templates,
            confidence_rate=round(confidence_rate, 2),
            error_count=error_count,
            emails_this_week=emails_this_week,
            active_users_this_week=active_users_this_week,
        )


@router.get("/users", response_model=List[AdminUser])
async def list_users(
    _: SupabaseUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """All users ordered by generation_count descending, with activity metrics."""
    with logfire.span("admin.list_users"):
        email_count_sq = (
            db.query(
                Email.user_id.label("user_id"),
                func.count(Email.id).label("actual_email_count"),
            )
            .group_by(Email.user_id)
            .subquery()
        )

        queue_sub_sq = (
            db.query(
                QueueItem.user_id.label("user_id"),
                func.count(QueueItem.id).label("queue_submissions"),
            )
            .group_by(QueueItem.user_id)
            .subquery()
        )

        failed_sq = (
            db.query(
                QueueItem.user_id.label("user_id"),
                func.count(QueueItem.id).label("failed_count"),
            )
            .filter(QueueItem.status == QueueStatus.FAILED)
            .group_by(QueueItem.user_id)
            .subquery()
        )

        rows = (
            db.query(
                User,
                func.coalesce(email_count_sq.c.actual_email_count, 0).label("actual_email_count"),
                func.coalesce(queue_sub_sq.c.queue_submissions, 0).label("queue_submissions"),
                func.coalesce(failed_sq.c.failed_count, 0).label("failed_count"),
            )
            .outerjoin(email_count_sq, User.id == email_count_sq.c.user_id)
            .outerjoin(queue_sub_sq, User.id == queue_sub_sq.c.user_id)
            .outerjoin(failed_sq, User.id == failed_sq.c.user_id)
            .order_by(User.generation_count.desc())
            .all()
        )

        return [
            AdminUser(
                id=str(user.id),
                email=user.email,
                display_name=user.display_name,
                generation_count=user.generation_count,
                template_count=user.template_count,
                onboarded=user.onboarded,
                created_at=user.created_at,
                actual_email_count=actual_email_count,
                queue_submissions=queue_submissions,
                failed_count=failed_count,
                email_template=user.email_template,
            )
            for user, actual_email_count, queue_submissions, failed_count in rows
        ]


@router.get("/users/{user_id}/emails", response_model=PaginatedEmails)
async def get_user_emails(
    user_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    _: SupabaseUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Paginated email history for a specific user."""
    try:
        user_uuid = ensure_uuid(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user_id format: {exc}",
        )

    with logfire.span("admin.get_user_emails", user_id=user_id, page=page):
        base_query = db.query(Email).filter(Email.user_id == user_uuid)
        total: int = base_query.count()
        pages = max(1, -(-total // per_page))  # ceiling division

        emails = (
            base_query
            .order_by(Email.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        items = [
            AdminEmail(
                id=str(e.id),
                recipient_name=e.recipient_name,
                recipient_interest=e.recipient_interest,
                email_message=e.email_message,
                template_type=e.template_type.value if e.template_type else None,
                is_confident=e.is_confident,
                metadata=e.email_metadata,
                created_at=e.created_at,
            )
            for e in emails
        ]

        return PaginatedEmails(items=items, total=total, page=page, per_page=per_page, pages=pages)


@router.get("/users/{user_id}/templates", response_model=List[AdminTemplate])
async def get_user_templates(
    user_id: str,
    _: SupabaseUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """All templates belonging to a specific user."""
    try:
        user_uuid = ensure_uuid(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user_id format: {exc}",
        )

    with logfire.span("admin.get_user_templates", user_id=user_id):
        templates = (
            db.query(Template)
            .filter(Template.user_id == user_uuid)
            .order_by(Template.created_at.desc())
            .all()
        )

        return [
            AdminTemplate(
                id=str(t.id),
                template_text=t.template_text,
                user_instructions=t.user_instructions,
                pdf_url=t.pdf_url,
                created_at=t.created_at,
            )
            for t in templates
        ]


@router.get("/users/{user_id}/queue", response_model=List[AdminQueueItem])
async def get_user_queue(
    user_id: str,
    _: SupabaseUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """All queue items belonging to a specific user, newest first."""
    try:
        user_uuid = ensure_uuid(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user_id format: {exc}",
        )

    with logfire.span("admin.get_user_queue", user_id=user_id):
        items = (
            db.query(QueueItem)
            .filter(QueueItem.user_id == user_uuid)
            .order_by(QueueItem.created_at.desc())
            .all()
        )

        return [
            AdminQueueItem(
                id=str(qi.id),
                recipient_name=qi.recipient_name,
                recipient_interest=qi.recipient_interest,
                status=qi.status,
                current_step=qi.current_step,
                error_message=qi.error_message,
                started_at=qi.started_at,
                completed_at=qi.completed_at,
                created_at=qi.created_at,
            )
            for qi in items
        ]


@router.get("/activity", response_model=List[AdminActivity])
async def get_activity(
    _: SupabaseUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Weekly email volume and distinct active users for the last 12 weeks."""
    with logfire.span("admin.activity"):
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=12)

        rows = (
            db.query(
                func.date_trunc("week", Email.created_at).label("week"),
                func.count(Email.id).label("emails_generated"),
                func.count(distinct(Email.user_id)).label("active_users"),
            )
            .filter(Email.created_at >= cutoff)
            .group_by(text("week"))
            .order_by(text("week DESC"))
            .all()
        )

        return [
            AdminActivity(
                week=row.week.date().isoformat(),
                emails_generated=row.emails_generated,
                active_users=row.active_users,
            )
            for row in rows
        ]


@router.get("/errors", response_model=List[AdminError])
async def get_errors(
    _: SupabaseUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """All failed queue items joined with user information, newest first."""
    with logfire.span("admin.errors"):
        rows = (
            db.query(QueueItem, User.email, User.display_name)
            .join(User, QueueItem.user_id == User.id)
            .filter(QueueItem.status == QueueStatus.FAILED)
            .order_by(QueueItem.created_at.desc())
            .all()
        )

        return [
            AdminError(
                id=str(qi.id),
                user_email=user_email,
                user_display_name=user_display_name,
                recipient_name=qi.recipient_name,
                current_step=qi.current_step,
                error_message=qi.error_message,
                created_at=qi.created_at,
                started_at=qi.started_at,
            )
            for qi, user_email, user_display_name in rows
        ]
