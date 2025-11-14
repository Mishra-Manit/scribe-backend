"""
Core pipeline infrastructure.

This package contains the core components of the pipeline:
- BasePipelineStep: Abstract base class for all pipeline steps
- PipelineRunner: Orchestrator for sequential step execution

Data models are in pipeline.models.core
Custom exceptions are in pipeline.core.exceptions
"""

from pipeline.core.runner import BasePipelineStep, PipelineRunner

__all__ = [
    "BasePipelineStep",
    "PipelineRunner",
]
