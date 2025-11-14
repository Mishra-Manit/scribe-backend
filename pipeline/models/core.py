# EmailPipelineData dataclass. Needs to have classes for JobStatus(ENUM), TemplateType(ENUM), EmailPipelineData, and many more. Draft this out later.


from attr import dataclass


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TemplateType(Enum):
    RESEARCH = "research"
    BOOK = "book"
    GENERAL = "general"


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
