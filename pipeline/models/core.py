# EmailPipelineData dataclass. Needs to have classes for JobStatus(ENUM), TemplateType(ENUM), EmailPipelineData, and many more. Draft this out later.


from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

# JobStatus is an internal enum that is used to track the status of the pipeline job
class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

# Only the template type is needed for the pipeline so it is has a str representation and a native enum representation
class TemplateType(str, Enum):
    RESEARCH = "research"
    BOOK = "book"
    GENERAL = "general"

@dataclass
class PipelineJob:
    job_id: str
    status: JobStatus
    current_step: str = ""
    error_message: Optional[str] = None
    results: Optional[Dict[str, Any]] = None

@dataclass
class EmailAnalysis:
    # This is a overview of the type of email that the user wants to write
    text: str = ""
    num_references: int = 0    # this is the number of references the user wants to include in the final email
    user_research_field: str = ""
