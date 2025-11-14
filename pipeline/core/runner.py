"""
Core pipeline infrastructure - base classes for all steps.

BasePipelineStep: Abstract base class for pipeline steps
PipelineRunner: Orchestrates sequential step execution
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable, List
import time
import logfire

from pipeline.models.core import PipelineData, StepResult
from pipeline.core.exceptions import StepExecutionError, ValidationError


class BasePipelineStep(ABC):
    """
    Abstract base class for all pipeline steps.

    Each step must implement:
    - _execute_step(): Core business logic
    - Optionally: _validate_input(): Input validation

    The execute() method wraps step execution with:
    - Logfire observability spans
    - Error handling and logging
    - Timing metrics
    - Result validation
    """

    def __init__(self, step_name: str):
        """
        Initialize pipeline step.

        Args:
            step_name: Unique identifier for this step (used in logs)
        """
        self.step_name = step_name

    async def execute(
        self,
        pipeline_data: PipelineData,
        progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None
    ) -> StepResult:
        """
        Execute the pipeline step with full observability.

        This is the public interface - it wraps the step-specific
        _execute_step() method with error handling and logging.

        Args:
            pipeline_data: Shared data object (modified in-place)
            progress_callback: Optional async callback for progress updates
                             Signature: callback(step_name, status)

        Returns:
            StepResult indicating success/failure

        Raises:
            StepExecutionError: If step fails and cannot continue
        """
        start_time = time.perf_counter()

        # Create Logfire span for this step
        with logfire.span(
            f"pipeline.{self.step_name}",
            task_id=pipeline_data.task_id,
            step=self.step_name
        ):
            try:
                # Log step start
                logfire.info(
                    f"{self.step_name} started",
                    task_id=pipeline_data.task_id
                )

                # Notify progress callback (if provided)
                if progress_callback:
                    await progress_callback(self.step_name, "started")

                # Validate input prerequisites
                validation_error = await self._validate_input(pipeline_data)
                if validation_error:
                    raise ValidationError(f"Input validation failed: {validation_error}")

                # Execute the step-specific logic
                result = await self._execute_step(pipeline_data)

                # Calculate duration
                duration = time.perf_counter() - start_time
                pipeline_data.add_timing(self.step_name, duration)

                # Update result metadata
                if result.metadata is None:
                    result.metadata = {}
                result.metadata["duration"] = duration

                # Log success
                logfire.info(
                    f"{self.step_name} completed",
                    task_id=pipeline_data.task_id,
                    duration=duration,
                    success=result.success
                )

                # Notify progress callback
                if progress_callback:
                    status = "completed" if result.success else "failed"
                    await progress_callback(self.step_name, status)

                return result

            except Exception as e:
                # Calculate duration even on failure
                duration = time.perf_counter() - start_time

                # Log error with full context
                logfire.error(
                    f"{self.step_name} failed",
                    task_id=pipeline_data.task_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    duration=duration,
                    exc_info=True  # Include stack trace
                )

                # Record error in pipeline data
                pipeline_data.add_error(self.step_name, str(e))

                # Notify progress callback
                if progress_callback:
                    await progress_callback(self.step_name, "failed")

                # Wrap exception for clarity
                raise StepExecutionError(self.step_name, e) from e

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """
        Validate that prerequisites for this step are met.

        Override this method to check:
        - Required fields are populated
        - Data is in expected format
        - Dependencies from previous steps exist

        Args:
            pipeline_data: Shared data object

        Returns:
            Error message if validation fails, None if valid=
        """
        # Default: no validation required
        return None

    @abstractmethod
    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute step-specific business logic.

        MUST BE IMPLEMENTED by each step.

        Args:
            pipeline_data: Shared data object (modify in-place)

        Returns:
            StepResult with success=True/False
        """
        pass


class PipelineRunner:
    """
    Orchestrates sequential execution of all pipeline steps.

    Responsibilities:
    - Register steps in execution order
    - Execute steps sequentially
    - Handle step failures
    - Track overall progress
    - Return final result (email_id)
    """

    def __init__(self, steps: Optional[List[BasePipelineStep]] = None):
        """
        Initialize pipeline runner.

        Args:
            steps: Optional list of steps (if None, use default factory)
        """
        self.steps = steps or []

    def register_step(self, step: BasePipelineStep) -> None:
        """
        Add a step to the pipeline.

        Steps execute in the order they are registered.

        Args:
            step: Pipeline step to add
        """
        self.steps.append(step)

    async def run(
        self,
        pipeline_data: PipelineData,
        progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None
    ) -> str:
        """
        Run all pipeline steps sequentially.

        Args:
            pipeline_data: Shared data object
            progress_callback: Optional callback for progress updates

        Returns:
            email_id: ID of the generated email (from metadata)

        Raises:
            StepExecutionError: If any step fails
            ValueError: If email_id not set by final step
        """
        # Create overall pipeline span
        with logfire.span(
            "pipeline.full_run",
            task_id=pipeline_data.task_id,
            user_id=pipeline_data.user_id,
            template_type=pipeline_data.template_type.value if pipeline_data.template_type else None
        ):
            logfire.info(
                "Pipeline execution started",
                task_id=pipeline_data.task_id,
                total_steps=len(self.steps)
            )

            # Execute each step sequentially
            for i, step in enumerate(self.steps):
                # Log progress
                progress_pct = int(((i + 1) / len(self.steps)) * 100)
                logfire.info(
                    f"Executing step {i+1}/{len(self.steps)}",
                    step=step.step_name,
                    progress_pct=progress_pct
                )

                # Execute step
                result = await step.execute(pipeline_data, progress_callback)

                # Check for failure
                if not result.success:
                    raise StepExecutionError(
                        step.step_name,
                        Exception(result.error or "Unknown error")
                    )

            # Verify email_id was set by final step
            email_id = pipeline_data.metadata.get("email_id")
            if not email_id:
                raise ValueError(
                    "Pipeline completed but email_id not set. "
                    "EmailComposer step must set pipeline_data.metadata['email_id']"
                )

            # Log completion
            total_duration = pipeline_data.total_duration()
            logfire.info(
                "Pipeline execution completed",
                task_id=pipeline_data.task_id,
                email_id=email_id,
                total_duration=total_duration,
                step_timings=pipeline_data.step_timings
            )

            return email_id
