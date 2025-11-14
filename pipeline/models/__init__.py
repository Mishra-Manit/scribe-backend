"""
Models package for Pipeline models

NOTE: not database models
"""

from .core import (
    # Enums
    JobStatus,
    TemplateType,
    StepName,

    # Core data models
    PipelineData,
    StepResult,

    # Deprecated (will be removed in Phase 9)
    # PipelineJob,
    # EmailAnalysis,
)

__all__ = [
    # Enums
    "JobStatus",
    "TemplateType",
    "StepName",

    # Core data models
    "PipelineData",
    "StepResult",
]
