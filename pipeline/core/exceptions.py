"""
Custom exceptions for pipeline execution.

These exceptions provide clear error messages and enable intelligent
retry logic in Celery task processing.
"""


class PipelineExecutionError(Exception):
    """
    Base exception for pipeline execution failures.

    All step-specific exceptions inherit from this.
    Celery can catch this for retry logic.
    """
    pass


class StepExecutionError(PipelineExecutionError):
    """
    Raised when a pipeline step fails.

    Attributes:
        step_name: Name of the failed step
        original_error: The underlying exception
    """

    def __init__(self, step_name: str, original_error: Exception):
        self.step_name = step_name
        self.original_error = original_error
        super().__init__(f"Step '{step_name}' failed: {str(original_error)}")


class ValidationError(PipelineExecutionError):
    """
    Raised when step input/output validation fails.

    Example: Email composer validates that email contains publication title
    """
    pass


class ExternalAPIError(PipelineExecutionError):
    """
    Raised when external API calls fail (Anthropic, Google, ArXiv).

    This is a retriable error - Celery should retry with exponential backoff.
    """
    pass
