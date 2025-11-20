"""
Celery utility functions.
Provides helpers for working with Celery tasks and formatting task results.
"""

from typing import Any, Dict, Union


def format_celery_error(result_info: Any) -> Union[Dict[str, Any], str]:
    """
    Format Celery task error information for API responses.

    Extracts error details from Celery's AsyncResult.info and formats them
    consistently for API responses. Handles both dict and non-dict error formats.
    """
    # Handle non-dict formats (simple errors)
    if not isinstance(result_info, dict):
        return str(result_info) if result_info else "Unknown error"

    # Extract structured error information from dict
    return {
        "message": result_info.get("exc_message", "Unknown error"),
        "type": result_info.get("exc_type", "Error"),
        "failed_step": result_info.get("failed_step")
    }
