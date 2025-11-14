"""
Core pipeline infrastructure - base classes for all steps.

BasePipelineStep: Abstract base class for pipeline steps
PipelineRunner: Orchestrates sequential step execution (to be implemented in Phase 4)
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

from pipeline.models.core import PipelineData, StepResult


class BasePipelineStep(ABC):
    """
    Abstract base class for all pipeline steps.

    Each step must implement _execute_step() with core business logic.
    The execute() method wraps step execution with error handling,
    logging, and timing metrics (to be completed in Phase 4).
    """

    def __init__(self, step_name: str):
        """
        Initialize pipeline step.

        Args:
            step_name: Unique identifier for this step (used in logs)
        """
        self.step_name = step_name
        self.logger = logging.getLogger(f"pipeline.{step_name}")

    async def execute(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute the pipeline step with full observability.

        This is the public interface - it wraps the step-specific
        _execute_step() method with error handling and logging.

        Args:
            pipeline_data: Shared data object (modified in-place)

        Returns:
            StepResult indicating success/failure

        Note: Full implementation will be completed in Phase 4.
        """
        # TODO: Phase 4 - Add Logfire spans, error handling, timing
        return await self._execute_step(pipeline_data)

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


# TODO: Phase 4 - Implement PipelineRunner class
# class PipelineRunner:
#     """Orchestrates sequential execution of all pipeline steps."""
#     pass
