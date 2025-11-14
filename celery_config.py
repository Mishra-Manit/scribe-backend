"""
Celery configuration for distributed task queue.

This module configures the Celery application with:
- Redis broker and result backend
- Task routing to priority queues
- Retry policies and error handling
- Worker configuration
"""
from celery import Celery
from config.redis_config import redis_settings


# Initialize Celery application
celery_app = Celery(
    "scribe",
    broker=redis_settings.broker_url,
    backend=redis_settings.result_backend,
    # include=["celery_tasks.pipeline"],  # TODO: Uncomment when pipeline.py is created
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task results
    result_expires=3600,
    result_extended=True,

    # Task routing
    # TODO: Uncomment when pipeline tasks are created
    # task_routes={
    #     "celery_tasks.pipeline.generate_email_task": {
    #         "queue": "email_default"
    #     },
    # },

    # Worker configuration
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Retry configuration
    task_autoretry_for=(Exception,),
    task_retry_kwargs={
        "max_retries": 3,
        "countdown": 60,
    },

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)


@celery_app.task(name="health_check")
def health_check() -> dict:
    """
    Health check task for monitoring worker status.

    Returns:
        dict: Health status information
    """
    return {
        "status": "healthy",
        "service": "celery-worker"
    }
