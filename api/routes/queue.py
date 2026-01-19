"""Queue management API endpoints for database-backed email generation queue."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, over
from typing import List
from datetime import datetime, timedelta, timezone
import logfire

from models.user import User
from models.queue_item import QueueItem, QueueStatus
from database import get_db
from api.dependencies import get_current_user
from schemas.queue import (
    BatchSubmitRequest,
    BatchSubmitResponse,
    QueueItemResponse,
    CancelQueueItemResponse,
)
from tasks.email_tasks import generate_email_task
from celery_config import celery_app
from utils.uuid_helpers import ensure_uuid


router = APIRouter(prefix="/api/queue", tags=["Queue"])


@router.post("/batch", response_model=BatchSubmitResponse, status_code=status.HTTP_201_CREATED)
async def submit_batch(
    batch_request: BatchSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit multiple items to the queue. All items will be processed sequentially.
    """
    with logfire.span(
        "api.queue_batch_submit",
        user_id=str(current_user.id),
        item_count=len(batch_request.items)
    ):
        if len(batch_request.items) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 100 items per batch"
            )

        queue_item_ids = []

        for item in batch_request.items:
            # 1. Create QueueItem in database
            queue_item = QueueItem(
                user_id=current_user.id,
                recipient_name=item.recipient_name,
                recipient_interest=item.recipient_interest,
                email_template=batch_request.email_template,
                status=QueueStatus.PENDING,
            )
            db.add(queue_item)
            db.flush()  # Get the ID before committing

            # 2. Dispatch Celery task
            task = generate_email_task.apply_async(
                kwargs={
                    "queue_item_id": str(queue_item.id),
                    "user_id": str(current_user.id),
                    "email_template": batch_request.email_template,
                    "recipient_name": item.recipient_name,
                    "recipient_interest": item.recipient_interest,
                },
                queue="email_default"
            )

            # 3. Store Celery task ID for potential fallback polling
            queue_item.celery_task_id = task.id
            queue_item_ids.append(str(queue_item.id))

        db.commit()

        logfire.info(
            "Batch submitted to queue",
            user_id=str(current_user.id),
            item_count=len(batch_request.items),
            queue_item_ids=queue_item_ids
        )

        return BatchSubmitResponse(
            queue_item_ids=queue_item_ids,
            message=f"Successfully queued {len(batch_request.items)} items"
        )


@router.get("/", response_model=List[QueueItemResponse])
async def get_queue_items(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get queue items from the last 24 hours for the current user with their status and position."""
    with logfire.span(
        "api.queue_get_items",
        user_id=str(current_user.id)
    ):
        # Calculate 24-hour cutoff time (only show recent items)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

        # Get all user's queue items ordered by creation time
        items = db.query(QueueItem).filter(
            QueueItem.user_id == current_user.id,
            QueueItem.created_at >= cutoff_time
        ).order_by(QueueItem.created_at.asc()).all()

        # Calculate positions for PENDING items in a single query using window function
        # This avoids N+1 query problem (1 query instead of N queries)

        positions_query = db.query(
            QueueItem.id,
            func.row_number().over(
                order_by=QueueItem.created_at.asc()
            ).label('position')
        ).filter(
            QueueItem.status == QueueStatus.PENDING,
            QueueItem.created_at >= cutoff_time
        ).all()

        # Create lookup map: {item_id: position}
        position_map = {str(item_id): position for item_id, position in positions_query}

        # Build response using the position map
        result = []
        for item in items:
            position = None
            if item.status == QueueStatus.PENDING:
                position = position_map.get(str(item.id))

            result.append(QueueItemResponse(
                id=str(item.id),
                recipient_name=item.recipient_name,
                status=item.status,
                position=position,
                email_id=str(item.email_id) if item.email_id else None,
                error_message=item.error_message,
                current_step=item.current_step,
                created_at=item.created_at,
            ))

        return result


@router.delete("/{queue_item_id}", response_model=CancelQueueItemResponse)
async def cancel_queue_item(
    queue_item_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a pending queue item. Cannot cancel processing/completed items."""
    # Validate UUID format
    try:
        item_uuid = ensure_uuid(queue_item_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid queue item ID format: {str(e)}"
        )

    with logfire.span(
        "api.queue_cancel_item",
        queue_item_id=queue_item_id,
        user_id=str(current_user.id)
    ):
        item = db.query(QueueItem).filter(
            QueueItem.id == item_uuid,
            QueueItem.user_id == current_user.id,
        ).first()

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Queue item not found"
            )

        if item.status != QueueStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel item with status '{item.status}'"
            )

        # Revoke the Celery task (terminate=False for graceful handling)
        if item.celery_task_id:
            celery_app.control.revoke(item.celery_task_id, terminate=False)

        # Delete from database
        db.delete(item)
        db.commit()

        logfire.info(
            "Queue item cancelled",
            queue_item_id=queue_item_id,
            user_id=str(current_user.id)
        )

        return CancelQueueItemResponse(message="Queue item cancelled")
