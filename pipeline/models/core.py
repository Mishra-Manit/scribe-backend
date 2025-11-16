"""
Core data models for the email generation pipeline.

This module contains all enums, dataclasses used throughout
the stateless pipeline system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, List
from datetime import datetime


# ===================================================================
# ENUMS
# ===================================================================

class JobStatus(Enum):
    """
    Internal enum for tracking pipeline job status.
    Used by Celery task state management.
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TemplateType(str, Enum):
    """
    Type of email template determining which information to include.

    RESEARCH: Include research papers and publications
    BOOK: Include books authored by the recipient
    GENERAL: Include general professional information
    """
    RESEARCH = "research"
    BOOK = "book"
    GENERAL = "general"


class StepName(str, Enum):
    """Pipeline step identifiers"""
    TEMPLATE_PARSER = "template_parser"
    WEB_SCRAPER = "web_scraper"
    ARXIV_ENRICHER = "arxiv_enricher"
    EMAIL_COMPOSER = "email_composer"


# ===================================================================
# PIPELINE DATA (IN-MEMORY STATE)
# ===================================================================

@dataclass
class PipelineData:
    """
    Shared data structure passed between all pipeline steps.

    This object lives in-memory for the duration of pipeline execution.
    Each step reads from and writes to specific fields.

    IMPORTANT: This is NEVER persisted to the database.
    Only the final email (from EmailComposer) is written to DB.
    """

    # ===================================================================
    # INPUT DATA (Set by Celery task from API request)
    # ===================================================================

    task_id: str
    """Celery task ID - used for correlation in Logfire"""

    user_id: str
    """User ID from JWT token - for database writes"""

    email_template: str
    """Template string with placeholders like {{name}}, {{research}}"""

    recipient_name: str
    """Full name of professor/recipient (e.g., 'Dr. Jane Smith')"""

    recipient_interest: str
    """Research area or interest (e.g., 'machine learning')"""

    # ===================================================================
    # STEP 1 OUTPUTS (TemplateParser)
    # ===================================================================

    search_terms: List[str] = field(default_factory=list)
    """
    Search queries extracted from template and recipient info.
    Example: ["Dr. Jane Smith machine learning", "Jane Smith publications"]
    """

    template_type: TemplateType | None = None
    """Required after Step 1 - set by TemplateParser (RESEARCH, BOOK, GENERAL)"""

    template_analysis: Dict[str, Any] = field(default_factory=dict)
    """
    Required after Step 1 - parsing details (placeholders, tone, etc.).
    Always present after TemplateParser.
    """

    # ===================================================================
    # STEP 2 OUTPUTS (WebScraper)
    # ===================================================================

    scraped_content: str = ""
    """
    Cleaned and summarized content from web scraping.
    Limited to ~5000 chars to avoid LLM context limits.
    """

    scraped_urls: List[str] = field(default_factory=list)
    """URLs that were successfully scraped"""

    scraped_page_contents: Dict[str, str] = field(default_factory=dict)
    """Mapping of URL -> raw cleaned content (per page)."""

    scraping_metadata: Dict[str, Any] = field(default_factory=dict)
    """
    Scraping stats: total_urls_tried, successful_scrapes, failed_urls
    """

    # ===================================================================
    # STEP 3 OUTPUTS (ArxivEnricher)
    # ===================================================================

    arxiv_papers: List[Dict[str, Any]] = field(default_factory=list)
    """
    Papers fetched from ArXiv API (only if template_type == RESEARCH).
    Each dict has: {title, abstract, year, url, authors}
    Limited to top 5 most relevant papers.
    """

    enrichment_metadata: Dict[str, Any] = field(default_factory=dict)
    """
    Enrichment stats: papers_found, papers_filtered, relevance_scores
    """

    # ===================================================================
    # STEP 4 OUTPUTS (EmailComposer)
    # ===================================================================

    final_email: str = ""
    """
    Final composed email (ready to send).
    Set by EmailComposer step.
    """

    composition_metadata: Dict[str, Any] = field(default_factory=dict)
    """
    Composition stats: llm_tokens_used, validation_attempts, quality_score
    """

    # ===================================================================
    # METADATA (For final DB write)
    # ===================================================================

    metadata: Dict[str, Any] = field(default_factory=dict)
    """
    Metadata that will be stored in emails.metadata JSONB column.
    EmailComposer populates this before DB write.
    """

    # ===================================================================
    # TRANSIENT DATA (Logged to Logfire, NOT persisted)
    # ===================================================================

    started_at: datetime = field(default_factory=datetime.utcnow)
    """Pipeline start time"""

    step_timings: Dict[str, float] = field(default_factory=dict)
    """
    Duration of each step in seconds.
    Example: {"template_parser": 1.2, "web_scraper": 3.5, ...}
    """

    errors: List[str] = field(default_factory=list)
    """
    Non-fatal errors encountered during execution.
    Fatal errors raise exceptions and terminate pipeline.
    """

    # ===================================================================
    # HELPER METHODS
    # ===================================================================

    def total_duration(self) -> float:
        """Calculate total pipeline execution time in seconds"""
        return (datetime.utcnow() - self.started_at).total_seconds()

    def add_timing(self, step_name: str, duration: float) -> None:
        """Record step timing"""
        self.step_timings[step_name] = duration

    def add_error(self, step_name: str, error_message: str) -> None:
        """Record non-fatal error"""
        self.errors.append(f"{step_name}: {error_message}")


# ===================================================================
# STEP RESULT
# ===================================================================

@dataclass
class StepResult:
    """
    Result of a pipeline step execution.

    Returned by BasePipelineStep.execute() to indicate success/failure.
    """

    success: bool
    """Whether the step completed successfully"""

    step_name: str
    """Name of the step that produced this result"""

    error: Optional[str] = None
    """Error message if success=False"""

    metadata: Optional[Dict[str, Any]] = None
    """
    Optional metadata about execution:
    - duration: float (seconds)
    - output_size: int (bytes/chars)
    - api_calls_made: int
    - retries_attempted: int
    """

    warnings: List[str] = field(default_factory=list)
    """Non-fatal warnings (e.g., 'some URLs failed to scrape')"""

    def __post_init__(self):
        """Validation: if success=False, error must be set"""
        if not self.success and not self.error:
            raise ValueError("StepResult with success=False must have error message")


# ===================================================================
# DEPRECATED CLASSES (Legacy - Will be removed in Phase 9)
# ===================================================================
#
# These classes were used for stateful job tracking in the database.
# The new architecture uses stateless in-memory PipelineData instead,
# with Celery managing job state in Redis.
#
# @dataclass
# class PipelineJob:
#     job_id: str
#     status: JobStatus
#     current_step: str = ""
#     error_message: Optional[str] = None
#     results: Optional[Dict[str, Any]] = None
#
# @dataclass
# class EmailAnalysis:
#     # This is a overview of the type of email that the user wants to write
#     text: str = ""
#     num_references: int = 0    # this is the number of references the user wants to include in the final email
#     user_research_field: str = ""
