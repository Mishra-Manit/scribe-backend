"""
Celery configuration for distributed task queue.

This module configures the Celery application with:
- Redis broker and result backend
- Task routing to priority queues
- Retry policies and error handling
- Worker configuration
"""
import os
import sys
from pathlib import Path
import logfire
from celery import Celery
from celery.signals import worker_process_init
from config.redis_config import redis_settings

# Add project root to Python path for module imports
# This ensures Celery workers can resolve imports like 'from utils.llm_agent import create_agent'
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Initialize Celery application
celery_app = Celery(
    "scribe",
    broker=redis_settings.broker_url,
    backend=redis_settings.result_backend,
    include=["tasks.email_tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    # Allow both JSON and pickle for deserialization (pickle needed for exceptions)
    accept_content=["json", "pickle"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task results
    result_expires=3600,
    result_extended=True,

    # Task routing
    task_routes={
        "tasks.email_tasks.generate_email_task": {
            "queue": "email_default"
        },
    },

    # Worker configuration
    # MEMORY CONSTRAINED: Only 1 worker on 512MB Render instance
    # Each task uses ~400MB with Playwright browsers
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    worker_concurrency=1,  # Force single worker

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Retry configuration
    # Note: We handle retries at the pipeline step level, not Celery level
    # This prevents issues with exception serialization
    task_autoretry_for=(),  # Disable automatic retries
    task_retry_kwargs={
        "max_retries": 0,
    },

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)


@worker_process_init.connect
def init_worker_process(**kwargs) -> None:
    """
    Initialize each worker process with proper configuration.

    This runs once per worker process (not per task).
    Configures observability and logging for the worker.
    """
    # CRITICAL: Re-establish sys.path in forked child process
    # This fixes import issues with billiard fork on Python 3.13/macOS
    project_root = Path(__file__).parent.absolute()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Configure Logfire for observability in worker processes
    if os.getenv("LOGFIRE_TOKEN"):
        logfire.configure(
            service_name="scribe-celery-worker",
            send_to_logfire="if-token-present",
            console=False,
        )
    else:
        logfire.configure(
            send_to_logfire=False,
            console=False,
        )

    # Instrument pydantic-ai to capture agent runs and spans
    logfire.instrument_pydantic_ai()

    # Log worker initialization after logfire is configured
    logfire.info(
        "Celery worker initialized",
        project_root=str(project_root),
        logfire_enabled=bool(os.getenv("LOGFIRE_TOKEN")),
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
