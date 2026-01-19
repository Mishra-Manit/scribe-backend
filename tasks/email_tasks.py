"""
Celery tasks responsible for orchestrating the email generation pipeline.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import logfire
from celery.exceptions import Ignore

from celery_config import celery_app
from database.session import get_db_context
from models.queue_item import QueueItem, QueueStatus
from pipeline import create_email_pipeline
from pipeline.core.exceptions import PipelineExecutionError, StepExecutionError
from pipeline.models.core import JobStatus, PipelineData, TemplateType

# Mapping between internal job statuses and Celery task states.
JOB_STATUS_TO_CELERY_STATE = {
    JobStatus.PENDING: "PENDING",
    JobStatus.RUNNING: "STARTED",
    JobStatus.COMPLETED: "SUCCESS",
    JobStatus.FAILED: "FAILURE",
}


@celery_app.task(bind=True)
def generate_email_task(
    self,
    *,
    queue_item_id: Optional[str] = None,
    task_id: Optional[str] = None,
    user_id: Optional[str] = None,
    email_template: Optional[str] = None,
    recipient_name: Optional[str] = None,
    recipient_interest: Optional[str] = None,
    template_type: str | TemplateType | None = None,
) -> Dict[str, Any]:
    """
    Celery entrypoint for the 4-step email generation pipeline.
    """

    celery_request_id = getattr(self.request, "id", None)
    public_task_id = task_id or celery_request_id

    if not public_task_id:
        raise ValueError("Unable to determine task_id (missing Celery request id).")

    required_fields = {
        "user_id": user_id,
        "email_template": email_template,
        "recipient_name": recipient_name,
        "recipient_interest": recipient_interest,
    }
    missing = [field for field, value in required_fields.items() if not value]
    if missing:
        raise ValueError(f"Missing required parameters: {', '.join(missing)}")

    def update_queue_status(
        status: str,
        current_step: Optional[str] = None,
        email_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update queue item status in the database."""
        if not queue_item_id:
            return

        try:
            with get_db_context() as db:
                item = db.query(QueueItem).filter(
                    QueueItem.id == queue_item_id
                ).first()

                if not item:
                    logfire.warning(
                        "Queue item not found for status update",
                        queue_item_id=queue_item_id
                    )
                    return

                item.status = status
                if current_step:
                    item.current_step = current_step

                # Set started_at when transitioning to PROCESSING
                if status == QueueStatus.PROCESSING and not item.started_at:
                    item.started_at = datetime.now(timezone.utc)

                # Set completed_at when finishing
                if status in (QueueStatus.COMPLETED, QueueStatus.FAILED):
                    item.completed_at = datetime.now(timezone.utc)

                if email_id:
                    item.email_id = email_id

                if error_message:
                    # Truncate error message to 1000 characters to prevent database bloat
                    # Stack traces can be very large and degrade query performance
                    MAX_ERROR_LENGTH = 1000
                    if len(error_message) > MAX_ERROR_LENGTH:
                        item.error_message = error_message[:MAX_ERROR_LENGTH] + "... [truncated]"
                    else:
                        item.error_message = error_message

                db.commit()

                logfire.debug(
                    "Queue item status updated",
                    queue_item_id=queue_item_id,
                    status=status,
                    current_step=current_step
                )
        except Exception as e:
            logfire.error(
                "Failed to update queue item status",
                queue_item_id=queue_item_id,
                error=str(e)
            )

    def _update_status(status: JobStatus, extra_meta: Optional[Dict[str, Any]] = None) -> None:
        """
        Persist task status/progress in Redis via Celery's backend.
        """
        meta: Dict[str, Any] = {
            "status": status.value,
            "task_id": public_task_id,
            "celery_id": celery_request_id,
        }
        if extra_meta:
            meta.update(extra_meta)

        celery_state = JOB_STATUS_TO_CELERY_STATE[status]

        # Transform metadata for FAILURE state to match Celery's expected format
        if celery_state == "FAILURE" and extra_meta:
            meta = {
                "exc_type": extra_meta.get("error_type", "UnknownError"),
                "exc_message": extra_meta.get("error", "Unknown error occurred"),
                # Preserve custom fields for API status endpoint
                "status": status.value,
                "task_id": public_task_id,
                "celery_id": celery_request_id,
                "failed_step": extra_meta.get("failed_step"),
            }

        self.update_state(state=celery_state, meta=meta)

    _update_status(JobStatus.PENDING, {"message": "Task accepted by worker"})

    pipeline_data = PipelineData(
        task_id=public_task_id,
        user_id=user_id,
        email_template=email_template,
        recipient_name=recipient_name,
        recipient_interest=recipient_interest,
        template_type=template_type,
    )

    runner = create_email_pipeline()

    async def progress_callback(step_name: str, step_status: str) -> None:
        _update_status(
            JobStatus.RUNNING,
            {
                "current_step": step_name,
                "step_status": step_status,
                "step_timings": pipeline_data.step_timings,
            },
        )
        # Also update database queue status
        update_queue_status(QueueStatus.PROCESSING, current_step=step_name)

    async def _execute_pipeline() -> str:
        return await runner.run(pipeline_data, progress_callback=progress_callback)

    with logfire.span(
        "tasks.generate_email",
        task_id=public_task_id,
        celery_id=celery_request_id,
        user_id=user_id,
    ):
        logfire.info(
            "Email generation task started",
            task_id=public_task_id,
            celery_id=celery_request_id,
            user_id=user_id,
        )

        _update_status(
            JobStatus.RUNNING,
            {
                "current_step": "initializing_pipeline",
                "step_status": "started",
            },
        )
        # Update database queue status
        update_queue_status(QueueStatus.PROCESSING, current_step="initializing")

        try:
            email_id = asyncio.run(_execute_pipeline())
        except (StepExecutionError, PipelineExecutionError) as exc:
            failed_step = getattr(exc, "step_name", None)
            error_message = str(exc)

            logfire.error(
                "Pipeline execution failed",
                task_id=public_task_id,
                celery_id=celery_request_id,
                error=error_message,
                error_type=type(exc).__name__,
                failed_step=failed_step,
            )

            # Update status before raising to ensure it's captured
            _update_status(
                JobStatus.FAILED,
                {
                    "error": error_message,
                    "failed_step": failed_step,
                    "error_type": type(exc).__name__,
                },
            )
            # Update database queue status
            update_queue_status(QueueStatus.FAILED, error_message=error_message)

            # Raise Ignore to prevent Celery from overwriting FAILURE state with SUCCESS
            raise Ignore()

        except Exception as exc:
            error_message = str(exc)
            error_type = type(exc).__name__

            logfire.error(
                "Unhandled exception during pipeline execution",
                task_id=public_task_id,
                celery_id=celery_request_id,
                error=error_message,
                error_type=error_type,
                exc_info=True,
            )

            # Update status before raising
            _update_status(
                JobStatus.FAILED,
                {
                    "error": error_message,
                    "error_type": error_type,
                }
            )
            # Update database queue status
            update_queue_status(QueueStatus.FAILED, error_message=error_message)

            # Raise Ignore to prevent Celery from overwriting FAILURE state with SUCCESS
            raise Ignore()

        total_duration = pipeline_data.total_duration()
        template_type_value = (
            pipeline_data.template_type.value if pipeline_data.template_type else None
        )
        email_id_str = str(email_id)

        result_payload = {
            "task_id": public_task_id,
            "status": JobStatus.COMPLETED.value,
            "email_id": email_id_str,
            "metadata": {
                "step_timings": pipeline_data.step_timings,
                "errors": pipeline_data.errors,
                "total_duration": total_duration,
                "template_type": template_type_value,
                "celery_id": celery_request_id,
            },
        }

        _update_status(
            JobStatus.COMPLETED,
            {
                "email_id": email_id_str,
                "total_duration": total_duration,
                "template_type": template_type_value,
            },
        )
        # Update database queue status with email_id
        update_queue_status(QueueStatus.COMPLETED, email_id=email_id_str)

        logfire.info(
            "Email generation task completed",
            task_id=public_task_id,
            email_id=email_id_str,
            total_duration=total_duration,
        )

        return result_payload

