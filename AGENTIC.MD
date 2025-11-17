# Scribe - Agentic Pipeline Implementation Guide

> **Comprehensive implementation guide for building a production-grade Pydantic agent-based email generation pipeline with Celery workers and Logfire observability.**

---

## Table of Contents

0. [Development Setup with Makefile](#0-development-setup-with-makefile)
1. [Architecture Philosophy & Design](#1-architecture-philosophy--design)
2. [Core Data Models](#2-core-data-models)
3. [Pipeline Core Infrastructure](#3-pipeline-core-infrastructure)
4. [Pipeline Step Implementations](#4-pipeline-step-implementations)
5. [Celery Integration](#5-celery-integration)
6. [FastAPI Endpoints](#6-fastapi-endpoints)
7. [Logfire Observability](#7-logfire-observability)
8. [Testing Strategy](#8-testing-strategy)
9. [Migration from Legacy Flask](#9-migration-from-legacy-flask)

---

## 0. Development Setup with Makefile

### 0.3 Running the Development Server

**Quick Start (Recommended):**

```bash
# Terminal 1: Start Redis + FastAPI + Celery
make redis-start
make serve
```

That's it! Your development environment is now running:
- **FastAPI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Celery Worker**: Processing tasks in background

**Advanced Setup (Separate Processes):**

```bash
# Terminal 1: Redis
make redis-start

# Terminal 2: FastAPI server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Celery worker
make celery-worker

# Terminal 4: Flower monitoring UI
make flower  # http://localhost:5555
```

---

## 1. Architecture Philosophy & Design

### 1.1 Document Purpose

This document is a **complete implementation guide** for transforming the Scribe email generation system from a synchronous Flask MVP into a production-ready, observable, scalable async pipeline.

**Target Audience:**
- Backend engineers implementing the pipeline
- DevOps engineers deploying the infrastructure
- Future maintainers of the system

**Prerequisites:**
- Python 3.13+ knowledge
- Understanding of async/await patterns
- Familiarity with Celery task queues
- Basic knowledge of Pydantic for validation
- Experience with FastAPI

**How to Use This Guide:**
- Read sections 1-2 for architectural understanding
- Follow sections 3-6 for step-by-step implementation
- Reference sections 7-9 for operations and deployment
- Use section 10 for migration strategy

---

### 1.2 Why Stateless Pipeline Architecture?

**The Problem with State Management in Async Systems:**

Traditional job processing systems often store intermediate state in the database:

```python
# ❌ Traditional approach - database as state store
job = create_job(user_id, status="pending")
db.commit()

job.status = "processing_step_1"
db.commit()

job.step_1_output = run_step_1()
db.commit()

job.status = "processing_step_2"
db.commit()

job.step_2_output = run_step_2()
db.commit()

# Result: 5+ database writes per job, potential race conditions, complex schema
```

**Our Approach - Stateless with In-Memory State:**

```python
# ✅ Our approach - in-memory state, single DB write
pipeline_data = PipelineData(task_id=task_id, ...)  # In-memory

await step_1.execute(pipeline_data)  # Updates pipeline_data.search_terms
await step_2.execute(pipeline_data)  # Updates pipeline_data.scraped_content
await step_3.execute(pipeline_data)  # Updates pipeline_data.arxiv_papers
await step_4.execute(pipeline_data)  # Writes final email to DB

# Result: 1 database write, no race conditions, simple schema
```

**Benefits:**

1. **Performance**: No intermediate I/O, all operations in RAM
2. **Simplicity**: Only 2 database tables (users, emails)
3. **Scalability**: Workers scale horizontally with no DB bottleneck
4. **Observability**: Logfire captures all state transitions without DB writes
5. **Reliability**: Celery retries handle failures, no orphaned job records

**Trade-offs:**

- ❌ Can't query historical job execution details from database
- ✅ Use Logfire for debugging and execution history instead
- ❌ Task state lives in Redis (ephemeral)
- ✅ Only care about final result (stored in database)

---

### 1.3 Why Celery for Job Orchestration?

**Celery vs Custom Job Table:**

| Feature | Celery + Redis | Custom DB Table |
|---------|----------------|-----------------|
| Job state storage | Redis (fast) | PostgreSQL (slower) |
| Built-in retries | ✅ Yes | ❌ Must implement |
| Task routing | ✅ Priority queues | ❌ Must implement |
| Worker scaling | ✅ Horizontal | Complex |
| Monitoring | ✅ Flower UI | Must build |
| Code complexity | Low | High |

**Celery provides:**
- Task states: PENDING → STARTED → SUCCESS → FAILURE
- Automatic retry with exponential backoff
- Priority queues (email_high, email_default)
- Worker concurrency control
- Task result backend (Redis)
- Battle-tested reliability

**Our Usage:**

```python
# Enqueue task, get task_id
task = generate_email_task.apply_async(
    kwargs={"user_id": "123", ...},
    queue="email_high"
)
task_id = task.id  # Return to client

# Client polls task state
result = AsyncResult(task_id)
result.state  # PENDING, STARTED, SUCCESS, FAILURE
result.result  # {"email_id": "456"} when SUCCESS
```

---

### 1.4 Why Logfire for Observability?

**Logfire vs Database Logging:**

Traditional approach:
```python
# ❌ Database logging - slow, cluttered
job.logs.append({"step": "step_1", "started_at": now()})
db.commit()
job.logs.append({"step": "step_1", "completed": True, "duration": 1.2})
db.commit()
```

Logfire approach:
```python
# ✅ Logfire - fast, structured, queryable
with logfire.span("pipeline.step_1", task_id=task_id):
    result = await step_1.execute(data)
    logfire.info("Step 1 completed", duration=1.2, output_size=len(result))
```

**Logfire provides:**
- Distributed tracing (spans, traces)
- Structured logging with rich context
- Real-time dashboards and alerts
- No database overhead
- Correlation across services (API → Celery → Pipeline)

**What goes to Logfire:**
- ✅ Pipeline execution spans
- ✅ Step timings and performance metrics
- ✅ Errors with full stack traces
- ✅ External API calls (Anthropic, Google, ArXiv)
- ✅ Validation failures

**What does NOT go to Logfire (or DB):**
- ❌ Raw scraped content (too large)
- ❌ Full prompt/response pairs (use sampling)

---

### 1.5 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client (Frontend)                           │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                                 │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  POST /api/email/generate                                      │ │
│  │  ├─ Validate JWT (get user_id)                                 │ │
│  │  ├─ Validate request with Pydantic                             │ │
│  │  ├─ Enqueue Celery task → get task_id                          │ │
│  │  └─ Return {task_id} to client                                 │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  GET /api/email/status/{task_id}                               │ │
│  │  ├─ Query Celery: AsyncResult(task_id)                         │ │
│  │  └─ Return {status, result}                                    │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  GET /api/email/{email_id}                                     │ │
│  │  ├─ Query database: emails table                               │ │
│  │  └─ Return email record                                        │ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │    Redis    │
                    │  (Broker +  │
                    │   Backend)  │
                    └──────┬──────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Celery Worker                                  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  generate_email_task(input_data)                               │ │
│  │  ├─ task_id = self.request.id                                  │ │
│  │  ├─ Create PipelineData (in-memory)                            │ │
│  │  ├─ PipelineRunner.run(pipeline_data)                          │ │
│  │  │   ├─ Step 1: TemplateParser                                 │ │
│  │  │   │   └─ Extract search terms (Anthropic)                   │ │
│  │  │   ├─ Step 2: WebScraper                                     │ │
│  │  │   │   └─ Google Search + BeautifulSoup                      │ │
│  │  │   ├─ Step 3: ArxivEnricher (conditional)                    │ │
│  │  │   │   └─ Fetch papers if template_type=RESEARCH             │ │
│  │  │   └─ Step 4: EmailComposer                                  │ │
│  │  │       ├─ Compose email (Anthropic)                          │ │
│  │  │       └─ Write to emails table ← ONLY DB WRITE              │ │
│  │  └─ Return {email_id, status: "completed"}                     │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                           │                                          │
│                           ▼                                          │
│                    ┌─────────────┐                                  │
│                    │   Logfire   │                                  │
│                    │  (Spans +   │                                  │
│                    │   Events)   │                                  │
│                    └─────────────┘                                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ PostgreSQL  │
                    │   (users,   │
                    │   emails)   │
                    └─────────────┘
```

---

### 1.6 Data Flow Through Pipeline

**Step-by-Step Data Transformation:**

```
Input (API Request):
{
  "email_template": "Hey {{name}}, I love {{research}}...",
  "recipient_name": "Dr. Jane Smith",
  "recipient_interest": "machine learning"
}

                ↓ (Celery task created)

PipelineData (Initial State):
{
  "task_id": "abc-123",
  "user_id": "user-456",
  "email_template": "Hey {{name}}...",
  "recipient_name": "Dr. Jane Smith",
  "recipient_interest": "machine learning",
  "search_terms": [],           # Empty - to be filled by Step 1
  "scraped_content": null,      # Empty - to be filled by Step 2
  "arxiv_papers": [],           # Empty - to be filled by Step 3
  "final_email": null,          # Empty - to be filled by Step 4
  "metadata": {}
}

                ↓ (Step 1: TemplateParser)

PipelineData (After Step 1):
{
  ...,
  "template_type": "RESEARCH",  # Determined by TemplateParser
  "search_terms": [
    "Dr. Jane Smith machine learning",
    "Jane Smith publications",
    "Jane Smith research papers"
  ]
}

                ↓ (Step 2: WebScraper)

PipelineData (After Step 2):
{
  ...,
  "scraped_content": "Dr. Jane Smith is a professor...",
  "scraped_urls": [
    "https://university.edu/faculty/smith",
    "https://scholar.google.com/citations?user=..."
  ]
}

                ↓ (Step 3: ArxivEnricher - conditional on template_type)

PipelineData (After Step 3):
{
  ...,
  "arxiv_papers": [
    {
      "title": "Neural Networks for Computer Vision",
      "abstract": "We present...",
      "year": 2023,
      "url": "https://arxiv.org/abs/2301.12345"
    }
  ]
}

                ↓ (Step 4: EmailComposer)

PipelineData (After Step 4):
{
  ...,
  "final_email": "Hey Dr. Smith, I loved your paper...",
  "metadata": {
    "email_id": "email-789",
    "papers_used": ["Neural Networks for Computer Vision"],
    "sources": ["https://university.edu/faculty/smith"],
    "generation_time": 4.2
  }
}

                ↓ (Write to database)

Database (emails table):
{
  "id": "email-789",
  "user_id": "user-456",
  "recipient_name": "Dr. Jane Smith",
  "recipient_interest": "machine learning",
  "email_message": "Hey Dr. Smith, I loved your paper...",
  "template_type": "RESEARCH",
  "metadata": {
    "papers_used": [...],
    "sources": [...],
    "generation_time": 4.2
  },
  "created_at": "2025-01-13T10:30:00Z"
}
```

---

### 1.7 Technology Stack Rationale

**Python 3.13:**
- Latest stable version with improved async performance
- Better error messages and type hints
- PEP 695 type parameter syntax

**FastAPI:**
- Native async/await support
- Automatic Pydantic validation
- Built-in OpenAPI documentation
- Excellent performance (Uvicorn ASGI server)

**Celery 5.x:**
- Industry standard for Python task queues
- Proven reliability at scale
- Rich ecosystem (Flower for monitoring)
- Flexible routing and retries

**Redis:**
- Fast in-memory broker for Celery
- Low latency task dispatch
- Built-in pub/sub for task events
- Persistent task results

**Pydantic 2.x:**
- Runtime type validation
- JSON schema generation
- Fast (Rust core)
- Excellent error messages

**Anthropic Claude API:**
- State-of-the-art language model
- Better at following instructions than GPT-3.5
- Streaming support
- Competitive pricing

**Logfire:**
- Built by Pydantic team
- Native Pydantic integration
- Beautiful dashboards
- Affordable pricing

**PostgreSQL (Supabase):**
- Reliable ACID-compliant storage
- Row-level security (RLS)
- JSONB for flexible metadata
- Managed hosting via Supabase

---

### 1.8 Design Principles

**1. Single Responsibility Principle**
- Each pipeline step does ONE thing well
- TemplateParser: extract search terms
- WebScraper: fetch web content
- ArxivEnricher: fetch papers
- EmailComposer: generate final email

**2. Dependency Inversion**
- Steps depend on `PipelineData` abstraction, not concrete implementations
- Easy to mock for testing
- Can swap step implementations

**3. Fail Fast**
- Validate inputs immediately with Pydantic
- Raise exceptions on invalid data
- Celery retries handle transient failures

**4. Observability First**
- Every operation wrapped in Logfire spans
- Structured logging with correlation IDs
- Metrics tracked automatically

**5. Stateless Execution**
- No shared mutable state between tasks
- Each task creates fresh `PipelineData`
- Safe to retry or scale workers

---

This concludes Part 1. The architecture is designed for **production at scale** with simplicity, observability, and reliability as core principles.

---

## 2. Core Data Models

### 2.1 File Structure

```
pipeline/
├── __init__.py
├── models/
│   ├── __init__.py
│   └── core.py          # ← All core data models here
└── core/
    ├── __init__.py
    └── runner.py         # ← BasePipelineStep and PipelineRunner
```

---

### 2.2 Enums (pipeline/models/core.py)

**Complete Implementation:**

```python
"""
Core data models for the email generation pipeline.

This module contains all enums, dataclasses, and Pydantic models
used throughout the pipeline system.
"""

from enum import Enum


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
```

**Why `str, Enum`?**
- Inheriting from `str` makes enum values JSON-serializable
- Required for Pydantic validation and Celery task serialization
- Values can be compared directly with strings: `template_type == "research"`

---

### 2.3 PipelineData Dataclass

**Complete Implementation:**

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


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
    """Required after Step 1 – set by TemplateParser (RESEARCH, BOOK, GENERAL)"""

    template_analysis: Dict[str, Any] = field(default_factory=dict)
    """
    Required after Step 1 – parsing details (placeholders, tone, etc.). Always present after TemplateParser.
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
```

**Key Design Decisions:**

1. **Dataclass vs Pydantic Model**: We use `@dataclass` instead of Pydantic `BaseModel` because:
   - Lighter weight (no validation overhead during pipeline execution)
   - Faster to instantiate
   - Only validated at API boundary (request/response)

2. **Field Organization**: Fields are grouped by which step produces them, making it clear what data flows where

3. **Optional Fields**: Most output fields are `Optional` because they're populated during execution

4. **Helper Methods**: Convenience methods for common operations (timing, errors)

---

### 2.3 StepResult Dataclass

```python
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
```

---

### 2.4 Database Models (SQLAlchemy)

**File: `models/email.py`**

```python
"""
SQLAlchemy models for the emails table.

IMPORTANT: Only 2 tables in the entire system:
- users (defined in models/user.py)
- emails (defined here)

No pipeline_jobs table - Celery handles job state.
"""

from sqlalchemy import Column, String, Text, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import uuid

from database.base import Base


class Email(Base):
    """
    Stores final generated emails.

    This is the ONLY table written to by the pipeline.
    EmailComposer step (Step 4) creates records in this table.
    """

    __tablename__ = "emails"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Foreign key to users table
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Email content and metadata
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_interest: Mapped[str] = mapped_column(String(500), nullable=False)
    email_message: Mapped[str] = mapped_column(Text, nullable=False)

    # NEW: Template type enum
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)
    """Values: 'research', 'book', 'general'"""

    # NEW: Metadata JSONB column
    metadata: Mapped[dict] = mapped_column(JSONB, nullable=True)
    """
    Stores execution metadata:
    {
        "papers_used": ["Title 1", "Title 2"],
        "sources": ["https://url1.com", "https://url2.com"],
        "generation_time": 4.2,
        "step_timings": {...},
        "llm_tokens_used": 1500
    }
    """

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )

    # Relationship
    user = relationship("User", back_populates="emails")

    # Indexes for performance
    __table_args__ = (
        Index("idx_emails_user_id", "user_id"),
        Index("idx_emails_created_at", "created_at"),
        Index("idx_emails_template_type", "template_type"),
    )

    def __repr__(self):
        return f"<Email(id={self.id}, recipient={self.recipient_name}, type={self.template_type})>"
```

**Migration to Add New Columns:**

```bash
# Generate migration
alembic revision --autogenerate -m "Add template_type and metadata to emails"

# Review generated migration in alembic/versions/
# Should contain:
# op.add_column('emails', sa.Column('template_type', sa.String(20), nullable=True))
# op.add_column('emails', sa.Column('metadata', postgresql.JSONB(), nullable=True))

# Apply migration
alembic upgrade head
```

---

### 2.5 Pydantic Schemas (API Request/Response)

**File: `schemas/pipeline.py`**

```python
"""
Pydantic schemas for pipeline API endpoints.

These models validate API requests and responses.
Separate from PipelineData (which is internal).
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from pipeline.models.core import TemplateType


# ===================================================================
# REQUEST SCHEMAS
# ===================================================================

class GenerateEmailRequest(BaseModel):
    """
    Request body for POST /api/email/generate
    """

    email_template: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Email template with placeholders"
    )

    recipient_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Full name of recipient"
    )

    recipient_interest: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Research area or interest"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "email_template": "Hey {{name}}, I loved your work on {{research}}!",
                "recipient_name": "Dr. Jane Smith",
                "recipient_interest": "machine learning"
            }
        }


# ===================================================================
# RESPONSE SCHEMAS
# ===================================================================

class GenerateEmailResponse(BaseModel):
    """
    Response from POST /api/email/generate
    """

    task_id: str = Field(..., description="Celery task ID for status polling")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc-123-def-456"
            }
        }


class TaskStatusResponse(BaseModel):
    """
    Response from GET /api/email/status/{task_id}
    """

    task_id: str
    status: str = Field(..., description="PENDING, STARTED, SUCCESS, FAILURE")
    result: Optional[Dict[str, Any]] = Field(
        None,
        description="Result data when status=SUCCESS"
    )
    error: Optional[str] = Field(
        None,
        description="Error message when status=FAILURE"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc-123",
                "status": "SUCCESS",
                "result": {"email_id": "email-789"}
            }
        }


class EmailResponse(BaseModel):
    """
    Response from GET /api/email/{email_id}
    """

    id: str
    recipient_name: str
    recipient_interest: str
    email_message: str
    template_type: str
    metadata: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2 (was orm_mode in v1)
        json_schema_extra = {
            "example": {
                "id": "email-789",
                "recipient_name": "Dr. Jane Smith",
                "recipient_interest": "machine learning",
                "email_message": "Hey Dr. Smith, I loved your paper...",
                "template_type": "research",
                "metadata": {
                    "papers_used": ["Neural Networks for CV"],
                    "generation_time": 4.2
                },
                "created_at": "2025-01-13T10:30:00Z"
            }
        }
```

---

### 2.6 Summary - Type Safety Throughout

**Type Flow:**

```
API Request (JSON)
  ↓ [Pydantic validation]
GenerateEmailRequest
  ↓ [Celery task]
PipelineData (dataclass - in-memory)
  ↓ [Pipeline execution]
Email (SQLAlchemy model)
  ↓ [API response]
EmailResponse (Pydantic)
  ↓ [JSON]
Client
```

**Benefits:**

1. **API Boundary**: Pydantic validates all incoming requests
2. **Internal Processing**: Lightweight dataclasses for performance
3. **Database**: SQLAlchemy ensures schema compliance
4. **API Response**: Pydantic serializes responses with validation

This layered type system provides safety without sacrificing performance.

---

This concludes Part 2. All data models are now defined with complete type safety.

---

## 3. Pipeline Core Infrastructure

### 3.1 File Structure

```
pipeline/
├── __init__.py                    # Factory function: create_email_pipeline()
├── core/
│   ├── __init__.py
│   ├── runner.py                  # BasePipelineStep, PipelineRunner
│   └── exceptions.py              # Custom exceptions
└── steps/
    ├── template_parser/
    ├── web_scraper/
    ├── arxiv_enricher/
    └── email_composer/
```

---

### 3.2 Custom Exceptions (pipeline/core/exceptions.py)

```python
"""
Custom exceptions for pipeline execution.

These exceptions provide clear error messages and can be caught
by Celery for retry logic.
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

    This is a retriable error - Celery should retry.
    """
    pass
```

---

### 3.3 BasePipelineStep (pipeline/core/runner.py)

**Complete Implementation:**

```python
"""
Core pipeline infrastructure - base classes for all steps.

BasePipelineStep: Abstract base class for pipeline steps
PipelineRunner: Orchestrates sequential step execution
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable
from datetime import datetime
import time
import logfire

from pipeline.models.core import PipelineData, StepResult
from pipeline.core.exceptions import StepExecutionError


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
        start_time = time.time()

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
                duration = time.time() - start_time
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
                duration = time.time() - start_time

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
            Error message if validation fails, None if valid

        Example:
            ```python
            async def _validate_input(self, data: PipelineData) -> Optional[str]:
                if not data.search_terms:
                    return "search_terms is empty"
                return None
            ```
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

        Example:
            ```python
            async def _execute_step(self, data: PipelineData) -> StepResult:
                # Do work
                data.search_terms = ["term1", "term2"]

                # Return success
                return StepResult(
                    success=True,
                    step_name=self.step_name,
                    metadata={"terms_extracted": 2}
                )
            ```
        """
        pass
```

---

### 3.4 PipelineRunner (pipeline/core/runner.py - continued)

```python
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
            template_type=pipeline_data.template_type.value
        ):
            logfire.info(
                "Pipeline execution started",
                task_id=pipeline_data.task_id,
                total_steps=len(self.steps)
            )

            # Execute each step sequentially
            for i, step in enumerate(self.steps):
                # Log progress
                progress_pct = int((i / len(self.steps)) * 100)
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
```

---

### 3.5 Pipeline Factory (pipeline/__init__.py)

```python
"""
Pipeline factory function.

This module provides create_email_pipeline() which instantiates
all pipeline steps in the correct order.
"""

from pipeline.core.runner import PipelineRunner
from pipeline.steps.template_parser.main import TemplateParserStep
from pipeline.steps.web_scraper.main import WebScraperStep
from pipeline.steps.arxiv_enricher.main import ArxivEnricherStep
from pipeline.steps.email_composer.main import EmailComposerStep


def create_email_pipeline() -> PipelineRunner:
    """
    Factory function to create a fully configured email generation pipeline.

    Steps are registered in execution order:
    1. TemplateParser: Extract search terms
    2. WebScraper: Fetch web content
    3. ArxivEnricher: Fetch academic papers (conditional)
    4. EmailComposer: Generate final email and write to DB

    Returns:
        PipelineRunner with all steps registered

    Example:
        ```python
        runner = create_email_pipeline()
        email_id = await runner.run(pipeline_data)
        ```
    """
    runner = PipelineRunner()

    # Register steps in order
    runner.register_step(TemplateParserStep())
    runner.register_step(WebScraperStep())
    runner.register_step(ArxivEnricherStep())
    runner.register_step(EmailComposerStep())

    return runner
```

---

### 3.6 Usage Example

**How the pipeline is invoked from Celery task:**

```python
# In celery_tasks/pipeline.py

from pipeline import create_email_pipeline
from pipeline.models.core import PipelineData, TemplateType

@celery_app.task(bind=True)
async def generate_email_task(self, input_data: dict):
    """Celery task for email generation"""

    # Create pipeline data
    pipeline_data = PipelineData(
        task_id=self.request.id,
        user_id=input_data["user_id"],
        email_template=input_data["email_template"],
        recipient_name=input_data["recipient_name"],
        recipient_interest=input_data["recipient_interest"]
    )

    # Create and run pipeline
    runner = create_email_pipeline()
    email_id = await runner.run(pipeline_data)

    # Return result
    return {
        "email_id": email_id,
        "status": "completed",
        "duration": pipeline_data.total_duration()
    }
```

---

### 3.8 Key Design Patterns

**1. Template Method Pattern:**
- `execute()` provides the template (logging, timing, error handling)
- `_execute_step()` is the hook for custom behavior

**2. Dependency Injection:**
- Steps receive `PipelineData` rather than accessing global state
- Easy to mock for testing

**3. Chain of Responsibility:**
- Each step processes data and passes to next step
- Steps are independent and composable

**4. Observer Pattern:**
- `progress_callback` allows external observers (e.g., WebSocket updates)

---

This concludes Part 3. The core infrastructure is now complete with production-ready error handling, observability, and testability.

---

## 4. Pipeline Step Implementations

### 4.1 Overview

Each pipeline step follows this structure:

```
pipeline/steps/{step_name}/
├── __init__.py
├── main.py              # Step implementation (inherits BasePipelineStep)
├── models.py            # Pydantic models for validation
├── prompts.py           # LLM prompts (if applicable)
├── utils.py             # Helper functions
└── tests/
    └── test_{step_name}.py
```

---

### 4.2 Step 1: Template Parser

**Purpose:** Extract search terms from email template and recipient info using Anthropic Claude.

#### File: `pipeline/steps/template_parser/models.py`

```python
"""
Pydantic models for TemplateParser step.

These models validate LLM responses to ensure structured output.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any


class TemplateAnalysis(BaseModel):
    """
    Structured output from template analysis.

    This is the expected JSON format from Claude API via pydantic-ai.
    The agent automatically validates this schema and retries on failure.
    """

    template_type: TemplateType = Field(
        description="Type of template (RESEARCH, BOOK, or GENERAL)"
    )

    search_terms: List[str] = Field(
        description="1-3 search queries for Google Custom Search",
        min_length=1,
        max_length=3
    )

    placeholders: List[str] = Field(
        description="List of placeholder variables found in template",
        default_factory=list
    )

    @field_validator("search_terms")
    @classmethod
    def validate_search_terms(cls, v: List[str]) -> List[str]:
        """Ensure search terms are non-empty and reasonable length"""
        cleaned = [term.strip() for term in v if term.strip()]
        if not cleaned:
            raise ValueError("At least one search term is required")

        # Validate each term
        for term in cleaned:
            if len(term) < 3:
                raise ValueError(f"Search term too short: '{term}'")
            if len(term) > 200:
                raise ValueError(f"Search term too long: '{term}'")

        return cleaned

    class Config:
        json_schema_extra = {
            "example": {
                "template_type": "RESEARCH",
                "search_terms": [
                    "Dr. Jane Smith machine learning",
                    "Jane Smith publications research",
                    "Jane Smith university faculty page"
                ],
                "placeholders": ["{{name}}", "{{research}}", "{{university}}"]
            }
        }
```

#### File: `pipeline/steps/template_parser/prompts.py`

```python
"""
Prompts for Template Parser pipeline step.

All Anthropic Claude prompts are defined here for easy modification and A/B testing.
"""


SYSTEM_PROMPT = """You are an expert email template analyzer specializing in academic outreach emails.

Your task is to analyze cold email templates and extract:
1. Template type (research, book, or general)
2. Search terms for finding information about the recipient
3. Template placeholders that require personalization

TEMPLATE TYPES:
- research: Template requires academic publications, papers, or research output
- book: Template specifically mentions books authored by recipient
- general: Template focuses on general professional information (bio, position, achievements)

SEARCH TERM GUIDELINES:
- Generate 1-3 focused search queries
- Include recipient name + interest in each query
- Vary specificity (broad to narrow)
- Examples:
  - "Dr. Jane Smith machine learning publications"
  - "Jane Smith AI research papers"
  - "Dr. Jane Smith Stanford University"

STRICT OUTPUT REQUIREMENTS:
- Respond with ONLY a single JSON object. Do not include any explanations, analysis, or commentary.
- Do NOT wrap the JSON in code fences or markdown (do not use ```json or ```).
- The JSON must strictly match the following schema:
  {
    "template_type": "research" | "book" | "general",
    "search_terms": [string, ... 1 to 3 items],
    "placeholders": [string, ...]
  }
- Constraints:
  - search_terms: 1-3 items; each must include the recipient name and the research interest.
  - placeholders: list every placeholder found in the template exactly as written, preserving double braces, e.g., "{{name}}".
  - Do not include duplicate placeholders; maintain the natural order found in the template when possible.
- If uncertain, choose the most conservative, defensible answer and still return valid JSON.

Return ONLY the JSON object with no additional text before or after it."""


def create_user_prompt(
    email_template: str,
    recipient_name: str,
    recipient_interest: str
) -> str:
    """
    Generate prompt for template analysis.

    Args:
        email_template: Raw template with placeholders
        recipient_name: Professor/recipient name
        recipient_interest: Research interest/area

    Returns:
        Formatted user prompt
    """
    return f"""Analyze this email template for Professor {recipient_name}, who researches {recipient_interest}.

TEMPLATE:
{email_template}

RECIPIENT INFO:
- Name: {recipient_name}
- Research Area: {recipient_interest}

ANALYSIS REQUIRED:
1. Determine template_type: Does it need research papers (research), books (book), or general info (general)?
2. Generate search_terms: Create 1-3 Google search queries to find information about this professor
3. Extract placeholders: List all {{{{placeholder}}}} variables in the template

OUTPUT FORMAT (STRICT):
- Respond with ONLY a single JSON object. No markdown, no code fences, no commentary.
- JSON schema:
{{{{
  "template_type": "research" | "book" | "general",
  "search_terms": ["query1", "query2", "query3"],
  "placeholders": ["{{{{name}}}}", "{{{{research}}}}"]
}}}}
- Constraints:
  - 1-3 search_terms; each must include the recipient name and interest.
  - placeholders must match the template exactly, including double braces (e.g., "{{{{name}}}}").

Return ONLY the JSON, with no additional text before or after it."""
```

#### File: `pipeline/steps/template_parser/utils.py`

```python
"""
Template Parser Utilities

Helper functions for placeholder extraction and template analysis.
"""

import re
from typing import List


def extract_placeholders(template: str) -> List[str]:
    """
    Extract all {{placeholder}} patterns from template.

    Args:
        template: Email template string

    Returns:
        List of unique placeholders (including braces)

    Example:
        >>> extract_placeholders("Hi {{name}}, I loved {{research}}!")
        ['{{name}}', '{{research}}']
    """
    # Match {{variable}} pattern
    pattern = r'\{\{[^}]+\}\}'
    matches = re.findall(pattern, template)

    # Return unique placeholders in order of appearance
    seen = set()
    unique_matches = []
    for match in matches:
        if match not in seen:
            seen.add(match)
            unique_matches.append(match)

    return unique_matches
```

#### File: `pipeline/steps/template_parser/main.py`

```python
"""
Template Parser Step - Phase 5 Step 1

Analyzes email templates using Anthropic Claude to extract:
- Search terms for web scraping
- Template type classification (RESEARCH/BOOK/GENERAL)
- Template placeholders that require personalization
"""

import logfire
from typing import Optional

from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
from pipeline.core.exceptions import ExternalAPIError, ValidationError
from config.settings import settings
from utils.llm_agent import create_agent

from .models import TemplateAnalysis
from .prompts import SYSTEM_PROMPT, create_user_prompt
from .utils import extract_placeholders


class TemplateParserStep(BasePipelineStep):
    """
    Step 1: Parse email template and extract metadata.

    Responsibilities:
    - Call Anthropic Claude API for template analysis
    - Extract search terms for web scraping
    - Classify template type (RESEARCH/BOOK/GENERAL)
    - Update PipelineData with results

    Updates PipelineData fields:
    - search_terms: List[str]
    - template_type: TemplateType
    - template_analysis: Dict[str, Any]
    """

    def __init__(self):
        """Initialize template parser step."""
        super().__init__(step_name="template_parser")

        # Validate API key is configured
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        # Model configuration
        self.model = "anthropic:claude-haiku-4-5"
        self.max_tokens = 2000
        self.temperature = 0.1  # Low temperature for consistent structured output

        # Create pydantic-ai agent for structured output
        # This agent automatically:
        # - Validates output against TemplateAnalysis schema
        # - Retries on validation failures
        # - Logs all inputs/outputs to Logfire
        self.agent = create_agent(
            model=self.model,
            output_type=TemplateAnalysis,
            system_prompt=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            retries=2
        )

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """
        Validate that required input fields are present.

        Required:
        - email_template: Non-empty string
        - recipient_name: Non-empty string
        - recipient_interest: Non-empty string
        """
        if not pipeline_data.email_template or not pipeline_data.email_template.strip():
            return "email_template is empty or missing"

        if not pipeline_data.recipient_name or not pipeline_data.recipient_name.strip():
            return "recipient_name is empty or missing"

        if not pipeline_data.recipient_interest or not pipeline_data.recipient_interest.strip():
            return "recipient_interest is empty or missing"

        # Validate template has reasonable length
        if len(pipeline_data.email_template) < 20:
            return "email_template is too short (< 20 characters)"

        if len(pipeline_data.email_template) > 5000:
            return "email_template is too long (> 5000 characters)"

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute template parsing logic.

        Steps:
        1. Extract local placeholders (for validation)
        2. Call Anthropic API with structured output
        3. Validate response with Pydantic
        4. Update PipelineData
        5. Return success result
        """
        try:
            # Extract placeholders locally (for comparison)
            local_placeholders = extract_placeholders(pipeline_data.email_template)
            placeholder_count = len(local_placeholders)

            logfire.info(
                "Analyzing template",
                placeholder_count=placeholder_count,
                template_length=len(pipeline_data.email_template)
            )

            # Create prompt
            user_prompt = create_user_prompt(
                email_template=pipeline_data.email_template,
                recipient_name=pipeline_data.recipient_name,
                recipient_interest=pipeline_data.recipient_interest
            )

            # Call pydantic-ai agent for structured output
            # Agent automatically:
            # - Sends request to Anthropic API
            # - Validates response against TemplateAnalysis schema
            # - Retries on validation failures
            # - Logs everything to Logfire (inputs, outputs, tokens, cost, latency)
            logfire.info("Running pydantic-ai agent for template analysis")

            try:
                result = await self.agent.run(user_prompt)
                analysis = result.output  # Already validated TemplateAnalysis instance

                logfire.info(
                    "Template analysis completed successfully",
                    template_type=analysis.template_type.value,
                    search_term_count=len(analysis.search_terms)
                )

            except Exception as e:
                # Catch all agent errors (API errors, validation errors, etc.)
                error_msg = f"Agent failed to analyze template: {str(e)}"
                logfire.error("Template analysis failed", error=error_msg)
                raise ExternalAPIError(error_msg)

            # Update PipelineData
            pipeline_data.search_terms = analysis.search_terms
            pipeline_data.template_type = analysis.template_type
            pipeline_data.template_analysis = {
                "placeholders": analysis.placeholders,
                "local_placeholders": local_placeholders,  # For debugging
            }

            # Log final state
            logfire.info(
                "PipelineData updated",
                search_terms=pipeline_data.search_terms,
                template_type=pipeline_data.template_type.value
            )

            # Return success
            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={
                    "template_type": analysis.template_type.value,
                    "search_term_count": len(analysis.search_terms),
                    "placeholder_count": len(analysis.placeholders),
                    "model_used": self.model
                }
            )

        except ExternalAPIError:
            # Re-raise API errors (retriable)
            raise
        except ValidationError:
            # Re-raise validation errors (not retriable)
            raise
        except Exception as e:
            # Catch-all for unexpected errors
            logfire.error(
                "Unexpected error in template parser",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
```

---

### 4.3 Step 2: Web Scraper

**Purpose:** Fetch and scrape web content using search terms from Step 1, with advanced two-tier summarization for large content.

**Key Innovations:**
- **Two-Tier Summarization Architecture**: Batch processing for content > 30K chars with final synthesis
- **Playwright Integration**: Headless browser with JavaScript rendering support
- **Anti-Hallucination Engineering**: Uncertainty markers, source verification, multi-source confirmation
- **Concurrent Scraping**: Semaphore-based rate limiting (max 2 concurrent)
- **Smart Chunking**: Sentence-boundary-aware splitting for large content

**Architecture:**

```
Content Size ≤ 30K chars:
    Google Search → Playwright Scrape → Direct Summarization (Haiku) → Output

Content Size > 30K chars:
    Google Search → Playwright Scrape → Split into Batches (30K each)
                                          ↓
                                    Batch Summarization (Haiku, extraction-focused)
                                          ↓
                                    Combine Batch Summaries
                                          ↓
                                    Final Synthesis (Sonnet + COT reasoning) → Output
```

**Models Used:**
- **Claude Haiku 4.5**: Fast batch summarization and direct summarization (<30K chars)
- **Claude Sonnet 4.5**: High-quality final synthesis with chain-of-thought reasoning (>30K chars)

#### File: `pipeline/steps/web_scraper/utils.py`

```python
"""
Web Scraper Utilities

Web scraping functions with Playwright for JavaScript-heavy sites.
"""

import re
import logfire
from bs4 import BeautifulSoup, Comment
from playwright.async_api import Browser
from typing import Optional, Tuple


def clean_text(html: str) -> str:
    """Normalize HTML into readable plain text."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Drop non-content elements
    for element in soup(["script", "style", "noscript", "template", "svg"]):
        element.decompose()

    # Remove inline comments to avoid boilerplate
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    text = soup.get_text(separator="\n")

    # Split into lines, trim whitespace, and discard empties
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned_text = "\n".join(lines)

    # Remove non-ASCII characters
    cleaned_text = re.sub(r"[^\x00-\x7F]+", "", cleaned_text)

    # Collapse multiple spaces
    cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)

    # Collapse multiple newlines
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return cleaned_text.strip()


async def scrape_url(
    url: str,
    browser: Browser,
    timeout: float = 10.0,
    max_content_length: int = 500000  # 500KB limit
) -> Tuple[Optional[str], Optional[str]]:
    """
    Scrape text content from a URL using Playwright (headless browser).

    Args:
        url: URL to scrape
        browser: Playwright Browser instance (persistent across calls)
        timeout: Page load timeout in seconds
        max_content_length: Max content size (unused but kept for compatibility)

    Returns:
        Tuple of (title, content) or (None, None) if failed

    Note:
        Returns None for both on failure (no exceptions raised)
        Creates a new BrowserContext per URL for isolation
    """
    # Skip non-HTML files
    if url.endswith(('.pdf', '.doc', '.docx', '.ppt', '.pptx')):
        logfire.info("Skipping non-HTML URL", url=url)
        return None, None

    # Skip video/media platforms (not useful for text scraping)
    blocked_domains = [
        'youtube.com',
        'youtu.be',
        'vimeo.com',
    ]
    url_lower = url.lower()
    if any(domain in url_lower for domain in blocked_domains):
        logfire.info("Skipping blocked domain (video/media platform)", url=url)
        return None, None

    context = None
    page = None

    try:
        # Create new browser context for isolation (cookies, storage, etc.)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        # Create page within context
        page = await context.new_page()

        # Navigate to URL with timeout
        response = await page.goto(
            url,
            wait_until='domcontentloaded',
            timeout=int(timeout * 1000)  # Convert to milliseconds
        )

        # Check response status
        if not response or response.status >= 400:
            logfire.warning("HTTP error scraping URL", url=url, status=response.status if response else "no response")
            return None, None

        # Wait for network to be idle (all content loaded)
        await page.wait_for_load_state('networkidle', timeout=int(timeout * 1000))

        # Extract title
        title = await page.title()
        if not title:
            title = None

        # Extract HTML and clean to normalized text
        html_content = await page.content()
        cleaned = clean_text(html_content)

        if max_content_length and len(cleaned) > max_content_length:
            logfire.info(
                "Truncating content due to max_content_length",
                url=url,
                original_length=len(cleaned),
                max_content_length=max_content_length
            )
            cleaned = cleaned[:max_content_length]

        if not cleaned or len(cleaned) < 100:
            logfire.info("Insufficient content after cleaning", url=url)
            return None, None

        logfire.info(
            "Successfully scraped URL with Playwright",
            url=url,
            content_length=len(cleaned),
            word_count=len(cleaned.split())
        )

        return title, cleaned

    except Exception as e:
        # Catch all errors: TimeoutError, network errors, etc.
        logfire.warning("Error scraping URL with Playwright", url=url, error=str(e))
        return None, None

    finally:
        # Always cleanup context (includes closing page)
        if context:
            await context.close()
```

#### File: `pipeline/steps/web_scraper/google_search.py`

```python
"""
Google Custom Search API integration.

Migrated from legacy code with improvements:
- Async implementation with httpx
- Better error handling
- Result deduplication
"""

import httpx
import logfire
from typing import List, Dict, Any
from config.settings import settings


class GoogleSearchClient:
    """Client for Google Custom Search API."""

    def __init__(self):
        """Initialize search client"""
        self.api_key = settings.google_api_key
        self.cse_id = settings.google_cse_id
        self.base_url = "https://www.googleapis.com/customsearch/v1"

        # Validate credentials
        if not self.api_key or not self.cse_id:
            raise ValueError(
                "Google API credentials missing. "
                "Set GOOGLE_API_KEY and GOOGLE_CSE_ID in environment."
            )

    async def search(
        self,
        query: str,
        num_results: int = 5,
        timeout: float = 10.0
    ) -> List[Dict[str, Any]]:
        """
        Perform Google Custom Search.

        Args:
            query: Search query string
            num_results: Number of results to return (max 10)
            timeout: Request timeout in seconds

        Returns:
            List of search result dicts with 'link', 'title', 'snippet'
        """
        # Validate inputs
        if not query.strip():
            raise ValueError("Query cannot be empty")

        num_results = min(num_results, 10)  # Google API max is 10

        # Build request params
        params = {
            "key": self.api_key,
            "cx": self.cse_id,
            "q": query.strip(),
            "num": num_results
        }

        logfire.info(
            "Performing Google Custom Search",
            query=query,
            num_results=num_results
        )

        # Make async request
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()

                data = response.json()
                items = data.get("items", [])

                logfire.info(
                    "Google Search completed",
                    results_found=len(items)
                )

                return items

            except httpx.HTTPStatusError as e:
                logfire.error(
                    "Google API HTTP error",
                    status_code=e.response.status_code,
                    response=e.response.text[:500]
                )
                raise

    async def search_multiple_terms(
        self,
        queries: List[str],
        results_per_query: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Search multiple queries and combine results.

        Args:
            queries: List of search query strings
            results_per_query: Results per query

        Returns:
            Combined list of unique search results (deduplicated by URL)
        """
        all_results = []
        seen_urls = set()

        for query in queries:
            try:
                results = await self.search(query, num_results=results_per_query)

                # Deduplicate by URL
                for result in results:
                    url = result.get("link", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(result)

            except Exception as e:
                logfire.warning(
                    "Search query failed, continuing with others",
                    query=query,
                    error=str(e)
                )
                continue

        logfire.info(
            "Multi-term search completed",
            total_queries=len(queries),
            unique_results=len(all_results)
        )

        return all_results
```

#### File: `pipeline/steps/web_scraper/models.py`

```python
"""
Web Scraper Step Models

Pydantic models for scraping results and validation.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ScrapedPage(BaseModel):
    """Single scraped webpage."""

    url: str = Field(description="Source URL")

    title: Optional[str] = Field(
        description="Page title",
        default=None,
        max_length=500
    )

    content: str = Field(
        description="Cleaned text content from page",
        max_length=50000
    )

    word_count: int = Field(
        description="Word count of content",
        ge=0
    )

    scrape_time_seconds: float = Field(
        description="Time taken to scrape this page",
        default=0.0
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Ensure content is non-empty after cleaning"""
        if not v.strip():
            raise ValueError("Content cannot be empty")
        return v.strip()


class ScrapingResult(BaseModel):
    """Complete result from web scraping step."""

    pages_scraped: List[ScrapedPage] = Field(
        description="Successfully scraped pages",
        default_factory=list
    )

    failed_urls: List[str] = Field(
        description="URLs that failed to scrape",
        default_factory=list
    )

    total_attempts: int = Field(
        description="Total URLs attempted",
        ge=0
    )

    total_content_length: int = Field(
        description="Combined character count of all content",
        ge=0
    )

    @property
    def success_rate(self) -> float:
        """Calculate scraping success rate"""
        if self.total_attempts == 0:
            return 0.0
        return len(self.pages_scraped) / self.total_attempts
```

#### File: `pipeline/steps/web_scraper/prompts.py`

**Three-Level Prompting System:**

The web scraper uses three distinct prompt strategies depending on content size and processing stage:

1. **SUMMARIZATION_SYSTEM_PROMPT** (Direct summarization, ≤30K chars):
   - Anti-hallucination rules: "ONLY include information EXPLICITLY stated"
   - Source verification: "NEVER infer, speculate, or add information"
   - Uncertainty markers: Mark ambiguous info as [UNCERTAIN] or [SINGLE SOURCE]
   - Publication filtering: "ONLY include titles where professor is EXPLICITLY named as author"
   - Structured output format with sections: PUBLICATIONS, RESEARCH AREAS, CURRENT POSITION, ACHIEVEMENTS
   - Max 3000 characters output

2. **BATCH_SUMMARIZATION_SYSTEM_PROMPT** (Extraction phase, >30K chars):
   - Extraction-focused: "Extract EVERY verifiable fact" (completeness over conciseness)
   - Source attribution: Include [PAGE X] markers for each fact
   - No filtering: "DO NOT filter for relevance - extract everything"
   - Verbatim quotes with attribution
   - Max 4000 characters per batch

3. **FINAL_SUMMARY_SYSTEM_PROMPT** (Synthesis phase, >30K chars):
   - Chain-of-thought reasoning: Mental steps for fact verification, relevance filtering, synthesis
   - Multi-source confirmation: Prioritize facts appearing in multiple batches
   - Contradiction detection: Mark conflicts as [UNCERTAIN]
   - Template-specific filtering: Emphasizes publications for RESEARCH, books for BOOK
   - Max 3000 characters final output

**Key Anti-Hallucination Strategies:**
- Verification checklist: "Could I point to the specific part of the source where this appears?"
- Conservative approach: "When in doubt, leave it out"
- Explicit uncertainty: [UNCERTAIN] and [SINGLE SOURCE] markers
- No general knowledge: "DO NOT use general knowledge about the professor"
- Template-specific requirements prevent hallucination of publication titles

#### File: `pipeline/steps/web_scraper/main.py`

```python
"""
Web Scraper Step - Phase 5 Step 2

Performs web scraping using search terms from Step 1:
- Google Custom Search API to find URLs
- Async scraping with Playwright (headless browser)
- Two-tier summarization for large content
- Updates PipelineData with results
"""

import logfire
import asyncio
from typing import Optional, List

from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
from pipeline.core.exceptions import ExternalAPIError
from config.settings import settings
from utils.llm_agent import create_agent

from .models import ScrapedPage, ScrapingResult
from .google_search import GoogleSearchClient
from .utils import scrape_url
from .prompts import SUMMARIZATION_SYSTEM_PROMPT, create_summarization_prompt


class WebScraperStep(BasePipelineStep):
    """
    Step 2: Web scraping and content extraction with two-tier summarization.

    Responsibilities:
    - Use search_terms from Step 1
    - Perform Google Custom Search
    - Scrape webpage content asynchronously with Playwright
    - Batch processing for content > 30K chars
    - Clean and summarize content (max 3000 chars)
    - Update PipelineData

    Updates PipelineData fields:
    - scraped_content: str (summarized, max 3000 chars)
    - scraped_urls: List[str]
    - scraped_page_contents: Dict[str, str]
    - scraping_metadata: Dict[str, Any]
    """

    def __init__(self):
        """Initialize web scraper step."""
        super().__init__(step_name="web_scraper")

        # Initialize clients
        self.google_client = GoogleSearchClient()

        # Create pydantic-ai agent for content summarization
        # Using Haiku 4.5 for fast, cost-effective fact extraction
        # Temperature 0.0 for maximum factual accuracy (anti-hallucination)
        self.summarization_agent = create_agent(
            model="anthropic:claude-haiku-4-5",
            system_prompt=SUMMARIZATION_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=2000,
            retries=2
        )

        # Configuration
        self.results_per_query = 3
        self.max_pages_to_scrape = 5
        self.scrape_timeout = 10.0
        self.max_concurrent_scrapes = 2
        self.batch_chunk_size = 30000  # Chars per batch
        self.final_max_output_chars = 3000

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """
        Validate prerequisites from Step 1.

        Required:
        - search_terms: Non-empty list
        - template_type: Must be set
        - recipient_name and recipient_interest: Present
        """
        if not pipeline_data.search_terms:
            return "search_terms is empty (Step 1 must run first)"

        if not pipeline_data.template_type:
            return "template_type not set (Step 1 must run first)"

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute web scraping with two-tier summarization.

        Flow:
        1. Google Custom Search -> get URLs
        2. Concurrent Playwright scraping -> raw content
        3. Combine content with page markers
        4. Two-tier summarization (if >30K chars)
        5. Update PipelineData

        Updates:
        - pipeline_data.scraped_content: Final summarized content
        - pipeline_data.scraped_urls: List of successfully scraped URLs
        - pipeline_data.scraped_page_contents: {url: raw_content} mapping
        - pipeline_data.scraping_metadata: Scraping statistics

        Returns:
            StepResult with scraping and summarization statistics
        """
        try:
            # Step 1: Google Custom Search
            logfire.info(
                "Performing Google searches",
                search_terms=pipeline_data.search_terms,
                results_per_query=self.results_per_query
            )

            search_results = await self.google_client.search_multiple_terms(
                queries=pipeline_data.search_terms,
                results_per_query=self.results_per_query
            )

            if not search_results:
                logfire.warning("No search results found")
                pipeline_data.scraped_content = "No search results found."
                pipeline_data.scraped_page_contents = {}
                pipeline_data.scraped_urls = []
                pipeline_data.scraping_metadata = {
                    "total_attempts": 0,
                    "successful_scrapes": 0,
                    "failed_urls": []
                }

                return StepResult(
                    success=True,
                    step_name=self.step_name,
                    warnings=["No search results found for any query"],
                    metadata={"search_results_count": 0}
                )

            # Extract URLs from search results
            urls_to_scrape = [
                result.get('link', '')
                for result in search_results
                if result.get('link')
            ][:self.max_pages_to_scrape]

            logfire.info("URLs to scrape", total_urls=len(urls_to_scrape))

            # Step 2: Scrape URLs concurrently with Playwright
            scraped_pages = await self._scrape_urls_concurrent(urls_to_scrape)

            # Step 3: Build scraping result
            scraping_result = ScrapingResult(
                pages_scraped=scraped_pages,
                failed_urls=[
                    url for url in urls_to_scrape
                    if url not in [page.url for page in scraped_pages]
                ],
                total_attempts=len(urls_to_scrape),
                total_content_length=sum(len(page.content) for page in scraped_pages)
            )

            logfire.info(
                "Scraping completed",
                successful=len(scraped_pages),
                failed=len(scraping_result.failed_urls),
                success_rate=scraping_result.success_rate,
                total_content_length=scraping_result.total_content_length
            )

            if not scraped_pages:
                pipeline_data.scraped_content = "Failed to scrape any content."
                pipeline_data.scraped_page_contents = {}
                pipeline_data.scraped_urls = []
                pipeline_data.scraping_metadata = scraping_result.model_dump()

                return StepResult(
                    success=True,
                    step_name=self.step_name,
                    warnings=["Failed to scrape any URLs"],
                    metadata={"scraped_pages": 0}
                )

            # Step 4: Combine and summarize content
            combined_content = self._combine_scraped_content(scraped_pages)

            # ALWAYS summarize with LLM for:
            # 1. Anti-hallucination fact checking
            # 2. Content filtering (removes boilerplate, duplicates)
            # 3. Context optimization for email generation
            # 4. Structured output format
            logfire.info(
                "Summarizing content with LLM for fact verification",
                original_length=len(combined_content),
                num_pages=len(scraped_pages)
            )

            # Two-tier summarization (handles large content)
            final_content = await self._summarize_content(
                content=combined_content,
                recipient_name=pipeline_data.recipient_name,
                recipient_interest=pipeline_data.recipient_interest,
                template_type=pipeline_data.template_type
            )

            # Check for uncertainty markers in the summary
            has_uncertainty = "[UNCERTAIN]" in final_content or "[SINGLE SOURCE]" in final_content
            if has_uncertainty:
                logfire.warning(
                    "Summary contains uncertainty markers",
                    has_uncertain=("[UNCERTAIN]" in final_content),
                    has_single_source=("[SINGLE SOURCE]" in final_content)
                )

            # Step 5: Update PipelineData
            pipeline_data.scraped_content = final_content
            pipeline_data.scraped_urls = [page.url for page in scraped_pages]
            pipeline_data.scraped_page_contents = {page.url: page.content for page in scraped_pages}
            pipeline_data.scraping_metadata = {
                "total_attempts": scraping_result.total_attempts,
                "successful_scrapes": len(scraped_pages),
                "failed_urls": scraping_result.failed_urls,
                "success_rate": scraping_result.success_rate,
                "total_content_length": scraping_result.total_content_length,
                "final_content_length": len(final_content),
                "was_summarized": True,
                "has_uncertainty_markers": has_uncertainty
            }

            # Return success
            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={
                    "pages_scraped": len(scraped_pages),
                    "urls_scraped": pipeline_data.scraped_urls,
                    "content_length": len(final_content)
                },
                warnings=[
                    f"{len(scraping_result.failed_urls)} URLs failed to scrape"
                ] if scraping_result.failed_urls else []
            )

        except ExternalAPIError:
            raise
        except Exception as e:
            logfire.error(
                "Unexpected error in web scraper",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def _scrape_urls_concurrent(self, urls: List[str]) -> List[ScrapedPage]:
        """
        Scrape multiple URLs concurrently with semaphore using Playwright.

        Creates a persistent browser for all scrapes, with isolated browser
        contexts per URL to prevent cross-contamination.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of successfully scraped pages
        """
        from playwright.async_api import async_playwright
        import time

        # Launch persistent browser for all scrapes
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox']  # Required for containers/serverless
            )

            try:
                # Create semaphore for concurrency control
                semaphore = asyncio.Semaphore(self.max_concurrent_scrapes)

                async def scrape_with_semaphore(url: str) -> Optional[ScrapedPage]:
                    async with semaphore:
                        start = time.time()

                        # Pass browser to scrape_url (creates new context per URL)
                        title, content = await scrape_url(
                            url,
                            browser,
                            timeout=self.scrape_timeout
                        )

                        if content:
                            return ScrapedPage(
                                url=url,
                                title=title,
                                content=content,
                                word_count=len(content.split()),
                                scrape_time_seconds=time.time() - start
                            )
                        return None

                # Scrape all URLs concurrently
                tasks = [scrape_with_semaphore(url) for url in urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Filter successful results
                scraped_pages = [
                    result for result in results
                    if isinstance(result, ScrapedPage)
                ]

                return scraped_pages

            finally:
                # Always close browser
                await browser.close()

    def _combine_scraped_content(self, pages: List[ScrapedPage]) -> str:
        """
        Combine content from multiple pages with clear page markers.

        Each page is wrapped with delimiters for batch processing:
        - Start marker: === PAGE {index}: {url} ===
        - End marker: === END PAGE {index} ===

        This allows batch summarization to maintain source attribution.

        Args:
            pages: List of scraped pages

        Returns:
            Combined content string with page markers
        """
        combined = ""

        for idx, page in enumerate(pages, start=1):
            # Start marker
            combined += f"{'=' * 80}\n"
            combined += f"=== PAGE {idx}: {page.url} ===\n"
            combined += f"{'=' * 80}\n\n"

            # Page title (if exists)
            if page.title:
                combined += f"Title: {page.title}\n\n"

            # Page content
            combined += f"{page.content}\n\n"

            # End marker
            combined += f"{'=' * 80}\n"
            combined += f"=== END PAGE {idx} ===\n"
            combined += f"{'=' * 80}\n\n\n"

        return combined

    async def _summarize_content(
        self,
        content: str,
        recipient_name: str,
        recipient_interest: str,
        template_type: 'TemplateType'
    ) -> str:
        """
        Two-tier summarization with batch processing and final synthesis.

        Architecture:
        - If content ≤30K chars: Direct summarization with Haiku
        - If content >30K chars:
            1. Split into 30K-char chunks (sentence-aware)
            2. Summarize each batch with Haiku (extraction focus)
            3. Combine batch summaries with markers
            4. Final synthesis with Sonnet + COT reasoning

        Args:
            content: Combined scraped content (all pages)
            recipient_name: Professor name
            recipient_interest: Research area
            template_type: Template type (RESEARCH, BOOK, GENERAL)

        Returns:
            Final synthesized summary (max 3000 chars)
        """
        from .prompts import (
            FINAL_SUMMARY_SYSTEM_PROMPT,
            create_final_summary_prompt,
            create_summarization_prompt
        )

        # Direct summarization for small content (≤30K chars)
        if len(content) <= 30000:
            logfire.info(
                "Content fits in single batch, using direct summarization",
                content_length=len(content)
            )

            user_prompt = create_summarization_prompt(
                scraped_content=content,
                recipient_name=recipient_name,
                recipient_interest=recipient_interest,
                template_type=template_type
            )

            with logfire.span(
                "Direct Summarization",
                content_length=len(content),
                template_type=template_type.value
            ):
                try:
                    result = await self.summarization_agent.run(user_prompt)
                    summary = result.output

                    logfire.info(
                        "Direct summarization completed",
                        original_length=len(content),
                        summary_length=len(summary)
                    )

                    return summary[:3000]

                except Exception as e:
                    logfire.error("Direct summarization failed", error=str(e))
                    return content[:3000]

        # Batch processing for large content (>30K chars)
        chunks = self._split_into_chunks(content, chunk_size=30000)
        total_batches = len(chunks)

        logfire.info(
            "Starting batch summarization",
            total_content_length=len(content),
            num_batches=total_batches,
            avg_batch_size=len(content) // total_batches
        )

        # Step 1: Batch Summarizations with Haiku (extraction)
        batch_summaries = []

        with logfire.span(
            "Batch Summarizations",
            total_batches=total_batches,
            content_length=len(content)
        ):
            for idx, chunk in enumerate(chunks, start=1):
                batch_summary = await self._summarize_batch(
                    batch_content=chunk,
                    batch_number=idx,
                    total_batches=total_batches,
                    recipient_name=recipient_name
                )
                batch_summaries.append(batch_summary)

        # Step 2: Combine batch summaries with markers
        tiered_summarizations = ""
        for idx, summary in enumerate(batch_summaries, start=1):
            tiered_summarizations += f"{'=' * 80}\n"
            tiered_summarizations += f"=== BATCH {idx} SUMMARY ===\n"
            tiered_summarizations += f"{'=' * 80}\n\n"
            tiered_summarizations += f"{summary}\n\n"
            tiered_summarizations += f"{'=' * 80}\n"
            tiered_summarizations += f"=== END BATCH {idx} ===\n"
            tiered_summarizations += f"{'=' * 80}\n\n\n"

        logfire.info(
            "Batch summaries combined",
            num_batches=len(batch_summaries),
            combined_length=len(tiered_summarizations)
        )

        # Step 3: Final Synthesis with Sonnet + COT
        with logfire.span(
            "Final Summary Agent",
            num_batches=len(batch_summaries),
            template_type=template_type.value
        ):
            # Create final summary agent (using Sonnet for higher quality)
            final_agent = create_agent(
                model="anthropic:claude-sonnet-4-5-20250929",
                system_prompt=FINAL_SUMMARY_SYSTEM_PROMPT,
                temperature=0.2,  # Slight creativity for synthesis while staying factual
                max_tokens=2500,  # ~3000 chars
                retries=2
            )

            final_prompt = create_final_summary_prompt(
                batch_summaries=tiered_summarizations,
                recipient_name=recipient_name,
                recipient_interest=recipient_interest,
                template_type=template_type
            )

            try:
                result = await final_agent.run(final_prompt)
                final_summary = result.output

                logfire.info(
                    "Final summary completed",
                    batches_processed=len(batch_summaries),
                    final_length=len(final_summary)
                )

                return final_summary[:3000]

            except Exception as e:
                logfire.error("Final summary generation failed", error=str(e))
                # Fallback: use first batch summary (better than nothing)
                logfire.warning("Using first batch summary as fallback")
                return batch_summaries[0][:3000] if batch_summaries else content[:3000]

    def _split_into_chunks(self, content: str, chunk_size: int = 30000) -> List[str]:
        """
        Split content into chunks without breaking mid-sentence.

        Smart chunking algorithm:
        1. Try to split at chunk_size
        2. Look backward up to 500 chars for sentence boundary (., !, ?, or \n\n)
        3. If no boundary found, split at word boundary
        4. If still no boundary, hard split at chunk_size

        Args:
            content: Full combined text
            chunk_size: Target chunk size in characters (default 30000)

        Returns:
            List of content chunks, each ≤ chunk_size characters
        """
        if len(content) <= chunk_size:
            return [content]

        chunks = []
        position = 0
        content_length = len(content)

        while position < content_length:
            # Determine end of this chunk
            end_position = min(position + chunk_size, content_length)

            # If this is the last chunk, take everything
            if end_position >= content_length:
                chunks.append(content[position:])
                break

            # Look backward for sentence boundary (up to 500 chars)
            search_start = max(position, end_position - 500)
            chunk_text = content[search_start:end_position]

            # Try to find sentence boundaries (in order of preference)
            sentence_endings = ['\n\n', '. ', '.\n', '! ', '!\n', '? ', '?\n']
            best_split = -1

            for ending in sentence_endings:
                idx = chunk_text.rfind(ending)
                if idx != -1:
                    # Convert local index to global index
                    best_split = search_start + idx + len(ending)
                    break

            # If no sentence boundary, try word boundary
            if best_split == -1:
                last_space = chunk_text.rfind(' ')
                if last_space != -1:
                    best_split = search_start + last_space + 1

            # If still no boundary, hard split at chunk_size
            if best_split == -1:
                best_split = end_position

            # Extract chunk and update position
            chunks.append(content[position:best_split].strip())
            position = best_split

        return chunks

    async def _summarize_batch(
        self,
        batch_content: str,
        batch_number: int,
        total_batches: int,
        recipient_name: str
    ) -> str:
        """
        Summarize a single content batch using Haiku.

        This is an intermediate extraction step - focuses on completeness
        over conciseness. The final summary will filter and synthesize.

        Args:
            batch_content: Content chunk to summarize
            batch_number: Current batch index (1-based)
            total_batches: Total number of batches
            recipient_name: Professor name

        Returns:
            Batch summary (max 4000 chars)
        """
        from .prompts import BATCH_SUMMARIZATION_SYSTEM_PROMPT, create_batch_summarization_prompt

        # Create batch-specific agent (ephemeral)
        batch_agent = create_agent(
            model="anthropic:claude-haiku-4-5",
            system_prompt=BATCH_SUMMARIZATION_SYSTEM_PROMPT,
            temperature=0.0,  # Deterministic extraction
            max_tokens=3000,  # ~4000 chars
            retries=2
        )

        user_prompt = create_batch_summarization_prompt(
            batch_content=batch_content,
            batch_number=batch_number,
            total_batches=total_batches,
            recipient_name=recipient_name
        )

        try:
            result = await batch_agent.run(user_prompt)
            summary = result.output

            logfire.info(
                "Batch summarized",
                batch_number=batch_number,
                total_batches=total_batches,
                input_length=len(batch_content),
                output_length=len(summary)
            )

            return summary[:4000]  # Enforce limit

        except Exception as e:
            logfire.error(
                "Batch summarization failed",
                batch_number=batch_number,
                error=str(e)
            )
            # Fallback: truncate raw content
            logfire.warning(
                "Using truncated raw content for batch",
                batch_number=batch_number
            )
            return batch_content[:4000]
```

---

### 4.4 Step 3: ArXiv Enricher

**Purpose:** Fetch academic papers from ArXiv (conditional on template_type).

#### File: `pipeline/steps/arxiv_helper/models.py`

```python
"""
ArXiv Helper Step Models

Pydantic models for academic paper data.
"""

from typing import List
from pydantic import BaseModel, Field
from datetime import datetime


class ArxivPaper(BaseModel):
    """Single academic paper from ArXiv."""

    title: str = Field(description="Paper title")

    abstract: str = Field(
        description="Paper abstract",
        max_length=5000
    )

    authors: List[str] = Field(
        description="List of author names",
        min_length=1
    )

    published_date: datetime = Field(
        description="Publication date"
    )

    arxiv_id: str = Field(
        description="ArXiv paper ID (e.g., '2301.12345')"
    )

    arxiv_url: str = Field(
        description="ArXiv paper URL"
    )

    pdf_url: str = Field(
        description="Direct PDF link"
    )

    primary_category: str = Field(
        description="Primary ArXiv category (e.g., 'cs.AI')"
    )

    relevance_score: float = Field(
        description="Relevance score (0-1, higher is more relevant)",
        ge=0.0,
        le=1.0,
        default=0.0
    )

    @property
    def year(self) -> int:
        """Extract year from published_date"""
        return self.published_date.year

    @property
    def primary_author(self) -> str:
        """Get first author"""
        return self.authors[0] if self.authors else "Unknown"

    def to_dict(self) -> dict:
        """Convert to dict for PipelineData.arxiv_papers"""
        return {
            "title": self.title,
            "abstract": self.abstract[:500],  # Truncate for brevity
            "authors": self.authors,
            "year": self.year,
            "url": self.arxiv_url,
            "relevance_score": self.relevance_score
        }


class ArxivSearchResult(BaseModel):
    """Complete result from ArXiv search."""

    papers_found: List[ArxivPaper] = Field(
        description="All papers found",
        default_factory=list
    )

    papers_filtered: List[ArxivPaper] = Field(
        description="Papers after relevance filtering (top 5)",
        default_factory=list
    )

    search_query: str = Field(
        description="Query used for ArXiv search"
    )

    total_results: int = Field(
        description="Total results from ArXiv API",
        ge=0
    )
```

#### File: `pipeline/steps/arxiv_helper/utils.py`

```python
"""
ArXiv Helper Utilities

ArXiv API utilities and relevance scoring.
"""

import arxiv
import logfire
from typing import List
from datetime import datetime

from .models import ArxivPaper


def search_arxiv(
    author_name: str,
    max_results: int = 20,
    sort_by: arxiv.SortCriterion = arxiv.SortCriterion.Relevance
) -> List[ArxivPaper]:
    """
    Search ArXiv for papers by author.

    Args:
        author_name: Author name to search
        max_results: Maximum papers to fetch
        sort_by: Sort criterion

    Returns:
        List of ArxivPaper objects

    Note:
        arxiv library doesn't support async, but we wrap it
        for consistency with other steps.
    """
    # Build search query
    # Format: au:"Last Name, First Name" for better results
    query = f'au:"{author_name}"'

    logfire.info(
        "Searching ArXiv",
        query=query,
        max_results=max_results
    )

    try:
        # Create search client
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_by
        )

        papers = []

        # Fetch results (synchronous)
        for result in search.results():
            paper = ArxivPaper(
                title=result.title,
                abstract=result.summary,
                authors=[author.name for author in result.authors],
                published_date=result.published,
                arxiv_id=result.entry_id.split('/')[-1],  # Extract ID
                arxiv_url=result.entry_id,
                pdf_url=result.pdf_url,
                primary_category=result.primary_category
            )

            papers.append(paper)

        logfire.info(
            "ArXiv search completed",
            papers_found=len(papers)
        )

        return papers

    except Exception as e:
        logfire.error(
            "ArXiv search failed",
            error=str(e),
            query=query
        )
        return []


def calculate_relevance_score(
    paper: ArxivPaper,
    recipient_name: str,
    recipient_interest: str
) -> float:
    """
    Calculate relevance score for a paper.

    Scoring factors:
    - Author match (0.4): Is recipient an author?
    - Topic match (0.3): Does abstract mention interest?
    - Recency (0.2): More recent papers score higher
    - Primary author (0.1): Bonus if recipient is first author

    Args:
        paper: ArxivPaper to score
        recipient_name: Expected author name
        recipient_interest: Research interest/topic

    Returns:
        Relevance score (0-1)
    """
    score = 0.0

    # Extract last name for matching
    recipient_last_name = recipient_name.split()[-1].lower()

    # Factor 1: Author match (0.4 weight)
    author_match = any(
        recipient_last_name in author.lower()
        for author in paper.authors
    )

    if author_match:
        score += 0.4

    # Factor 2: Topic match in abstract (0.3 weight)
    interest_keywords = recipient_interest.lower().split()
    abstract_lower = paper.abstract.lower()

    keyword_matches = sum(
        1 for keyword in interest_keywords
        if keyword in abstract_lower
    )

    # Normalize by number of keywords
    topic_score = min(keyword_matches / len(interest_keywords), 1.0) * 0.3
    score += topic_score

    # Factor 3: Recency (0.2 weight)
    # Papers from last 5 years get full score, older papers decay
    current_year = datetime.now().year
    years_old = current_year - paper.year

    if years_old <= 5:
        recency_score = 0.2
    elif years_old <= 10:
        recency_score = 0.1
    else:
        recency_score = 0.0

    score += recency_score

    # Factor 4: Primary author bonus (0.1 weight)
    if paper.authors and recipient_last_name in paper.authors[0].lower():
        score += 0.1

    return min(score, 1.0)  # Cap at 1.0


def filter_top_papers(
    papers: List[ArxivPaper],
    recipient_name: str,
    recipient_interest: str,
    top_n: int = 5
) -> List[ArxivPaper]:
    """
    Score and filter papers to top N most relevant.

    Args:
        papers: List of papers to filter
        recipient_name: Recipient name
        recipient_interest: Research interest
        top_n: Number of top papers to return

    Returns:
        Sorted list of top N papers
    """
    # Score all papers
    for paper in papers:
        paper.relevance_score = calculate_relevance_score(
            paper=paper,
            recipient_name=recipient_name,
            recipient_interest=recipient_interest
        )

    # Sort by relevance (descending)
    sorted_papers = sorted(
        papers,
        key=lambda p: p.relevance_score,
        reverse=True
    )

    # Return top N
    top_papers = sorted_papers[:top_n]

    logfire.info(
        "Papers filtered",
        total_papers=len(papers),
        top_papers=len(top_papers),
        avg_relevance=sum(p.relevance_score for p in top_papers) / len(top_papers) if top_papers else 0.0
    )

    return top_papers
```

#### File: `pipeline/steps/arxiv_helper/main.py`

```python
"""
ArXiv Helper Step - Phase 5 Step 3

Conditionally fetches academic papers from ArXiv API:
- Only runs if template_type == RESEARCH
- Searches for papers by recipient
- Scores and filters to top 5 most relevant
- Updates PipelineData with results
"""

import logfire
from typing import Optional

from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult, TemplateType

from .models import ArxivSearchResult
from .utils import search_arxiv, filter_top_papers


class ArxivHelperStep(BasePipelineStep):
    """
    Step 3: Fetch academic papers from ArXiv (conditional).

    Responsibilities:
    - Check if template_type == RESEARCH
    - Search ArXiv for papers by recipient
    - Score papers by relevance
    - Filter to top 5 papers
    - Update PipelineData

    Updates PipelineData fields:
    - arxiv_papers: List[Dict[str, Any]]
    - enrichment_metadata: Dict[str, Any]
    """

    def __init__(self):
        """Initialize ArXiv helper step."""
        super().__init__(step_name="arxiv_helper")

        # Configuration
        self.max_papers_to_fetch = 20
        self.top_n_papers = 5

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """
        Validate prerequisites.

        Required:
        - template_type: Must be set (from Step 1)
        - recipient_name: Required for author search
        - recipient_interest: Required for relevance scoring
        """
        if not pipeline_data.template_type:
            return "template_type not set (Step 1 must run first)"

        if not pipeline_data.recipient_name:
            return "recipient_name is missing"

        if not pipeline_data.recipient_interest:
            return "recipient_interest is missing"

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute ArXiv paper fetching.

        Steps:
        1. Check if template_type == RESEARCH (skip if not)
        2. Search ArXiv for papers by recipient
        3. Score papers by relevance
        4. Filter to top 5
        5. Update PipelineData
        """
        try:
            # Step 1: Check template type
            if pipeline_data.template_type != TemplateType.RESEARCH:
                logfire.info(
                    "Skipping ArXiv search - not RESEARCH template",
                    template_type=pipeline_data.template_type.value
                )

                # Set empty results
                pipeline_data.arxiv_papers = []
                pipeline_data.enrichment_metadata = {
                    "skipped": True,
                    "reason": f"template_type is {pipeline_data.template_type.value}, not RESEARCH"
                }

                return StepResult(
                    success=True,
                    step_name=self.step_name,
                    metadata={
                        "skipped": True,
                        "template_type": pipeline_data.template_type.value
                    }
                )

            # Step 2: Search ArXiv
            logfire.info(
                "Searching ArXiv for papers",
                recipient_name=pipeline_data.recipient_name,
                max_results=self.max_papers_to_fetch
            )

            papers = search_arxiv(
                author_name=pipeline_data.recipient_name,
                max_results=self.max_papers_to_fetch
            )

            if not papers:
                logfire.warning(
                    "No papers found on ArXiv",
                    recipient_name=pipeline_data.recipient_name
                )

                pipeline_data.arxiv_papers = []
                pipeline_data.enrichment_metadata = {
                    "papers_found": 0,
                    "papers_filtered": 0,
                    "search_query": pipeline_data.recipient_name
                }

                return StepResult(
                    success=True,
                    step_name=self.step_name,
                    warnings=["No papers found on ArXiv"],
                    metadata={"papers_found": 0}
                )

            # Step 3: Score and filter papers
            top_papers = filter_top_papers(
                papers=papers,
                recipient_name=pipeline_data.recipient_name,
                recipient_interest=pipeline_data.recipient_interest,
                top_n=self.top_n_papers
            )

            logfire.info(
                "ArXiv papers filtered",
                total_papers=len(papers),
                top_papers=len(top_papers),
                relevance_scores=[p.relevance_score for p in top_papers]
            )

            # Step 4: Build result
            result = ArxivSearchResult(
                papers_found=papers,
                papers_filtered=top_papers,
                search_query=pipeline_data.recipient_name,
                total_results=len(papers)
            )

            # Step 5: Update PipelineData
            pipeline_data.arxiv_papers = [
                paper.to_dict() for paper in top_papers
            ]

            pipeline_data.enrichment_metadata = {
                "papers_found": len(papers),
                "papers_filtered": len(top_papers),
                "search_query": result.search_query,
                "avg_relevance_score": sum(p.relevance_score for p in top_papers) / len(top_papers) if top_papers else 0.0,
                "skipped": False
            }

            # Return success
            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={
                    "papers_found": len(papers),
                    "papers_filtered": len(top_papers),
                    "top_paper_titles": [p.title for p in top_papers[:3]]
                }
            )

        except Exception as e:
            logfire.error(
                "Error in ArXiv helper",
                error=str(e),
                error_type=type(e).__name__
            )

            # ArXiv errors are not fatal - continue pipeline with empty results
            pipeline_data.arxiv_papers = []
            pipeline_data.enrichment_metadata = {
                "error": str(e),
                "papers_found": 0
            }

            return StepResult(
                success=True,
                step_name=self.step_name,
                warnings=[f"ArXiv search failed: {str(e)}"],
                metadata={"error": str(e)}
            )
```

---

### 4.5 Step 4: Email Composer (CRITICAL STEP)

**Purpose:** Compose final email using all gathered data and write to database.

This is the ONLY step that writes to the database.

#### File: `pipeline/steps/email_composer/models.py`

```python
"""
Email Composer Step Models

Pydantic models for email generation and validation.
"""

from typing import List
from pydantic import BaseModel, Field, field_validator


class EmailValidationResult(BaseModel):
    """Result of email quality validation."""

    is_valid: bool = Field(
        description="True if email passes all validation checks"
    )

    issues: List[str] = Field(
        description="List of validation issues found",
        default_factory=list
    )

    warnings: List[str] = Field(
        description="Non-fatal warnings",
        default_factory=list
    )

    mentions_publications: bool = Field(
        description="True if email mentions specific publications",
        default=False
    )

    has_placeholders: bool = Field(
        description="True if unfilled placeholders remain",
        default=False
    )

    word_count: int = Field(
        description="Word count of email",
        ge=0
    )

    tone_matches_template: bool = Field(
        description="True if tone matches original template",
        default=True
    )


class ComposedEmail(BaseModel):
    """Final composed email ready for database storage."""

    email_content: str = Field(
        description="Final email text",
        min_length=50,
        max_length=10000
    )

    validation_result: EmailValidationResult = Field(
        description="Validation result"
    )

    generation_metadata: dict = Field(
        description="Metadata about generation process",
        default_factory=dict
    )

    @field_validator("email_content")
    @classmethod
    def validate_email_content(cls, v: str) -> str:
        """Ensure email is non-empty after stripping"""
        if not v.strip():
            raise ValueError("Email content cannot be empty")
        return v.strip()
```

#### File: `pipeline/steps/email_composer/prompts.py`

```python
"""
Email Composer Prompts

Prompts for email generation - migrated from legacy code with improvements.
"""

from typing import List


SYSTEM_PROMPT = """You are an expert cold email writer who specializes in crafting authentic, human-like academic outreach emails.

Your PRIMARY goal is to write in a natural, conversational way that perfectly matches the sender's unique writing style and tone.

WRITING PHILOSOPHY:
- Write like a real person, not an AI - avoid robotic or overly formal language
- Every email template has its own personality - study and mirror it exactly
- The recipient should feel like they're hearing from a genuine human who took time to research them
- Natural flow is more important than perfect grammar - write how people actually email

CORE RESPONSIBILITIES:
1. MATCH THE EXACT WRITING STYLE: Study the template's vocabulary, sentence structure, energy level, and personality
2. Replace ALL text within placeholders ({{variable}} or [variable]) with appropriate, specific information
3. Preserve ALL other text in the template exactly as written
4. Write replacements that sound like they came from the same person who wrote the template
5. PRESERVE THE ORIGINAL FORMATTING - maintain paragraph breaks, line spacing, and structure

STYLE MATCHING GUIDELINES:
- If the template is casual and uses contractions, your replacements should too
- If the template is energetic with exclamation points, maintain that energy
- If the template is reserved and formal, keep replacements similarly professional
- Match the sentence length patterns - short & punchy or long & flowing
- Use similar vocabulary complexity as the surrounding text
- Ensure replacements flow seamlessly with the template text

CRITICAL:
- Include specific publication titles when available in the research data
- Make all references sound natural and conversational
- NEVER leave placeholders unfilled - always replace with actual content
- NEVER add AI-sounding phrases like "cutting-edge" unless the template uses them"""


def create_composition_prompt(
    email_template: str,
    recipient_name: str,
    recipient_interest: str,
    scraped_content: str,
    arxiv_papers: List[dict],
    template_analysis: dict
) -> str:
    """
    Create prompt for email composition.

    Args:
        email_template: Original template with placeholders
        recipient_name: Professor name
        recipient_interest: Research interest
        scraped_content: Summarized web content from Step 2
        arxiv_papers: Papers from Step 3 (may be empty)
        template_analysis: Analysis from Step 1

    Returns:
        Formatted user prompt
    """
    # Format ArXiv papers
    arxiv_section = "NOT AVAILABLE - No ArXiv papers found or not a RESEARCH template."

    if arxiv_papers:
        arxiv_section = "=== ARXIV PAPERS ===\n"
        for i, paper in enumerate(arxiv_papers[:5], 1):
            arxiv_section += f"\n{i}. Title: {paper['title']}\n"
            arxiv_section += f"   Authors: {', '.join(paper['authors'][:3])}\n"
            arxiv_section += f"   Year: {paper['year']}\n"
            arxiv_section += f"   Relevance: {paper.get('relevance_score', 0):.2f}\n"

    # Build prompt
    prompt = f"""TASK: Fill in this cold email template for Professor {recipient_name}, a {recipient_interest} researcher.

STEP 1 - ANALYZE THE WRITING STYLE:
Before making any replacements, carefully study the template to understand:
- The overall tone: {template_analysis.get('tone', 'conversational')}
- Key topics: {', '.join(template_analysis.get('key_topics', []))}
- The writer's personality that comes through

TEMPLATE TO COMPLETE:
{email_template}

AVAILABLE INFORMATION:

{arxiv_section}

=== WEB RESEARCH DATA ===
{scraped_content[:10000]}

CRITICAL INSTRUCTIONS FOR NATURAL WRITING:
1. Your replacements should sound EXACTLY like the person who wrote the template
2. Prioritize natural flow over perfect accuracy - write how a real person would
3. Use conversational transitions and connectors that match the template style
4. If the template is informal, your replacements should be equally informal
5. Avoid AI-sounding phrases like "cutting-edge", "groundbreaking", "innovative" unless the template uses similar language
6. Include specific publication titles when available, but introduce them naturally as the template writer would
7. PRESERVE ALL PARAGRAPH BREAKS AND FORMATTING from the original template
8. REPLACE ALL PLACEHOLDERS - no {{{{variables}}}} or [brackets] should remain

REMEMBER:
- Write like you're the same person who wrote the template
- Keep the energy level consistent throughout
- Make it feel genuine and personal, not like a mail merge
- The professor should feel like they're getting a real, thoughtful email from someone who actually read their work

Generate the complete email now, with all placeholders filled naturally and authentically:"""

    return prompt
```

#### File: `pipeline/steps/email_composer/main.py`

```python
"""
Email Composer Step - Phase 5 Step 4

Final pipeline step - generates email and writes to database.

Responsibilities:
- Generate email using Anthropic Claude API
- Validate email quality
- Retry if validation fails
- Write to database
- Update PipelineData with final email
"""

import logfire
from typing import Optional

from config.settings import settings
from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
from utils.llm_agent import create_agent

from .models import ComposedEmail
from .prompts import SYSTEM_PROMPT, create_composition_prompt
from .utils import validate_email, clean_email_formatting
from .db_utils import write_email_to_db, increment_user_generation_count


class EmailComposerStep(BasePipelineStep):
    """
    Step 4: Generate final email and write to database.

    Responsibilities:
    - Combine data from Steps 1-3
    - Generate email via Anthropic Claude API
    - Validate email quality
    - Retry if validation fails (max 2 attempts)
    - Write to database
    - Update PipelineData

    Updates PipelineData fields:
    - final_email: str (final composed email)
    - composition_metadata: dict (generation metadata)
    - metadata["email_id"]: UUID (CRITICAL for pipeline tracking)
    """

    def __init__(self):
        """Initialize email composer step."""
        super().__init__(step_name="email_composer")

        # Configuration
        self.model = "anthropic:claude-sonnet-4-5-20250929"
        self.temperature = 0.7  # Higher for creative writing
        self.max_tokens = 2000
        self.max_retries = 2  # Total attempts = 3 (initial + 2 retries)

        # Create pydantic-ai agent for email composition
        # Using Sonnet for high-quality, creative email writing
        self.composition_agent = create_agent(
            model=self.model,
            system_prompt=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            retries=1  # Agent-level retries (validation retries handled separately)
        )

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """
        Validate prerequisites.

        Required:
        - email_template: Original template (from initialization)
        - recipient_name: Recipient name
        - recipient_interest: Research interest
        - template_analysis: Analysis from Step 1
        - scraped_content: Web data from Step 2
        - user_id: For database write

        Optional:
        - arxiv_papers: Papers from Step 3 (may be empty)
        """
        if not pipeline_data.email_template:
            return "email_template is missing"

        if not pipeline_data.recipient_name:
            return "recipient_name is missing"

        if not pipeline_data.recipient_interest:
            return "recipient_interest is missing"

        if not pipeline_data.template_analysis:
            return "template_analysis is missing (Step 1 must run first)"

        if not pipeline_data.scraped_content:
            return "scraped_content is missing (Step 2 must run first)"

        if not pipeline_data.user_id:
            return "user_id is missing (required for database write)"

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute email generation and database write.

        Steps:
        1. Prepare composition prompt
        2. Generate email via Anthropic API
        3. Validate email quality
        4. Retry if validation fails (max 2 retries)
        5. Write to database
        6. Update PipelineData
        """
        try:
            # Step 1: Prepare prompt
            user_prompt = create_composition_prompt(
                email_template=pipeline_data.email_template,
                recipient_name=pipeline_data.recipient_name,
                recipient_interest=pipeline_data.recipient_interest,
                scraped_content=pipeline_data.scraped_content,
                arxiv_papers=pipeline_data.arxiv_papers or [],
                template_analysis=pipeline_data.template_analysis
            )

            logfire.info(
                "Generating email with Anthropic",
                model=self.model,
                temperature=self.temperature,
                recipient_name=pipeline_data.recipient_name
            )

            # Step 2 & 3: Generate and validate (with retries)
            composed_email = await self._generate_with_validation(
                user_prompt=user_prompt,
                recipient_name=pipeline_data.recipient_name,
                template_type=pipeline_data.template_type
            )

            if not composed_email:
                # All retry attempts failed
                return StepResult(
                    success=False,
                    step_name=self.step_name,
                    error="Failed to generate valid email after all retry attempts"
                )

            # Step 4: Write to database
            email_id = await write_email_to_db(
                user_id=pipeline_data.user_id,
                recipient_name=pipeline_data.recipient_name,
                recipient_interest=pipeline_data.recipient_interest,
                email_content=composed_email.email_content
            )

            if not email_id:
                return StepResult(
                    success=False,
                    step_name=self.step_name,
                    error="Failed to write email to database"
                )

            logfire.info(
                "Email written to database",
                email_id=str(email_id),
                word_count=composed_email.validation_result.word_count
            )

            # Step 5: Increment user generation count (non-critical)
            await increment_user_generation_count(user_id=pipeline_data.user_id)

            # Step 6: Update PipelineData
            pipeline_data.final_email = composed_email.email_content

            pipeline_data.composition_metadata = {
                "email_id": str(email_id),
                "word_count": composed_email.validation_result.word_count,
                "mentions_publications": composed_email.validation_result.mentions_publications,
                "validation_warnings": composed_email.validation_result.warnings,
                "model": self.model,
                "temperature": self.temperature,
                **composed_email.generation_metadata
            }

            # CRITICAL: Set email_id in metadata for PipelineRunner
            pipeline_data.metadata["email_id"] = email_id

            # Return success
            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={
                    "email_id": str(email_id),
                    "word_count": composed_email.validation_result.word_count,
                    "mentions_publications": composed_email.validation_result.mentions_publications,
                    "warnings": composed_email.validation_result.warnings
                }
            )

        except Exception as e:
            logfire.error(
                "Error in email composer",
                error=str(e),
                error_type=type(e).__name__
            )

            return StepResult(
                success=False,
                step_name=self.step_name,
                error=f"Email composer error: {str(e)}"
            )

    async def _generate_with_validation(
        self,
        user_prompt: str,
        recipient_name: str,
        template_type: 'TemplateType'
    ) -> Optional[ComposedEmail]:
        """
        Generate email with validation and retry logic.

        Args:
            user_prompt: Formatted prompt for Claude
            recipient_name: Recipient name for validation
            template_type: Type of template (RESEARCH, BOOK, or GENERAL)

        Returns:
            ComposedEmail if successful, None if all retries failed
        """
        for attempt in range(self.max_retries + 1):
            try:
                logfire.info(
                    "Generating email attempt",
                    attempt=attempt + 1,
                    max_attempts=self.max_retries + 1
                )

                # Call pydantic-ai agent for email generation
                # Agent automatically logs to Logfire (prompt, response, tokens, cost, latency)
                result = await self.composition_agent.run(user_prompt)
                raw_email = result.output.strip()

                # Clean formatting
                cleaned_email = clean_email_formatting(raw_email)

                logfire.info(
                    "Email generated",
                    attempt=attempt + 1,
                    word_count=len(cleaned_email.split()),
                    length=len(cleaned_email)
                )

                # Validate email
                validation_result = validate_email(
                    email_content=cleaned_email,
                    recipient_name=recipient_name,
                    template_type=template_type
                )

                # Check if valid
                if validation_result.is_valid:
                    logfire.info(
                        "Email validation passed",
                        attempt=attempt + 1,
                        warnings_count=len(validation_result.warnings)
                    )

                    # Build ComposedEmail
                    # Note: Token counts are automatically logged to Logfire by pydantic-ai
                    composed_email = ComposedEmail(
                        email_content=cleaned_email,
                        validation_result=validation_result,
                        generation_metadata={
                            "attempts": attempt + 1,
                            "model": self.model
                        }
                    )

                    return composed_email

                else:
                    # Validation failed
                    logfire.warning(
                        "Email validation failed",
                        attempt=attempt + 1,
                        issues=validation_result.issues,
                        warnings=validation_result.warnings
                    )

                    # Retry if attempts remain
                    if attempt < self.max_retries:
                        logfire.info(
                            "Retrying email generation",
                            remaining_attempts=self.max_retries - attempt
                        )
                        continue
                    else:
                        # No more retries - return last attempt anyway
                        logfire.error(
                            "All validation attempts failed - using last attempt",
                            issues=validation_result.issues
                        )

                        return ComposedEmail(
                            email_content=cleaned_email,
                            validation_result=validation_result,
                            generation_metadata={
                                "attempts": attempt + 1,
                                "model": self.model,
                                "validation_failed": True
                            }
                        )

            except Exception as e:
                logfire.error(
                    "Error generating email",
                    attempt=attempt + 1,
                    error=str(e)
                )

                # Retry if attempts remain
                if attempt < self.max_retries:
                    continue
                else:
                    return None

        return None
```

---

### 4.6 Testing Pipeline Steps

**Example integration test:**

```python
# tests/pipeline/test_full_pipeline.py

import pytest
from pipeline import create_email_pipeline
from pipeline.models.core import PipelineData, TemplateType


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_pipeline_execution():
    """Test complete pipeline execution end-to-end"""

    # Create test data
    pipeline_data = PipelineData(
        task_id="test-integration-123",
        user_id="user-test-456",
        email_template="Hey {{name}}, I loved your work on {{research}}!",
        recipient_name="Dr. Jane Smith",
        recipient_interest="machine learning",
        template_type=TemplateType.RESEARCH
    )

    # Create and run pipeline
    runner = create_email_pipeline()
    email_id = await runner.run(pipeline_data)

    # Assertions
    assert email_id is not None
    assert pipeline_data.search_terms  # Step 1 output
    assert pipeline_data.scraped_content  # Step 2 output
    # Step 3 may or may not find papers
    assert pipeline_data.final_email  # Step 4 output
    assert len(pipeline_data.final_email) >= 100

    # Verify email quality
    assert "{{" not in pipeline_data.final_email  # No placeholders
    assert "Smith" in pipeline_data.final_email  # Recipient mentioned

    # Verify metadata
    assert "email_id" in pipeline_data.metadata
    assert pipeline_data.metadata["email_id"] == email_id

    # Verify all steps completed
    assert len(pipeline_data.step_timings) == 4
```

---

This concludes Part 4. All 4 pipeline steps are now fully implemented with production-ready code, error handling, and validation.

---

## 5. Celery Integration

### 5.1 Celery Configuration

**File: `celery_config.py`**

```python
"""
Celery configuration for Scribe email generation.

Sets up task queues, routing, and worker settings.
"""

from celery import Celery
from kombu import Queue, Exchange
import os
import logfire

# Initialize Logfire for Celery workers
logfire.configure(
    service_name="scribe-celery-worker",
    environment=os.getenv("ENVIRONMENT", "development")
)

# Create Celery app
celery_app = Celery(
    "scribe",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task tracking
    task_track_started=True,

    # Reliability settings
    task_acks_late=True,  # Acknowledge task after completion
    task_reject_on_worker_lost=True,  # Re-queue on worker crash
    worker_prefetch_multiplier=1,  # Process one task at a time

    # Task routing
    task_routes={
        "celery_tasks.pipeline.generate_email_task": {
            "queue": "email_high",
            "routing_key": "email.high"
        }
    },

    # Task queues
    task_queues=(
        Queue(
            "email_high",
            Exchange("email", type="direct"),
            routing_key="email.high"
        ),
        Queue(
            "email_default",
            Exchange("email", type="direct"),
            routing_key="email.default"
        ),
    ),

    # Result expiration
    result_expires=3600,  # 1 hour

    # Task result extended (store more metadata)
    result_extended=True
)
```

### 5.2 Celery Task

**File: `celery_tasks/pipeline.py`**

```python
"""
Celery tasks for pipeline execution.
"""

from celery_config import celery_app
from pipeline import create_email_pipeline
from pipeline.models.core import PipelineData, TemplateType
import logfire


@celery_app.task(bind=True, max_retries=3)
async def generate_email_task(self, input_data: dict):
    """
    Celery task for email generation pipeline.

    Args:
        input_data: Dict with user_id, email_template, recipient_name, etc.

    Returns:
        Dict with email_id and status

    This task is automatically retried up to 3 times on failure.
    """

    task_id = self.request.id

    with logfire.span("celery.generate_email_task", task_id=task_id):
        try:
            logfire.info("Task started", task_id=task_id, user_id=input_data.get("user_id"))

            # Create pipeline data
            pipeline_data = PipelineData(
                task_id=task_id,
                user_id=input_data["user_id"],
                email_template=input_data["email_template"],
                recipient_name=input_data["recipient_name"],
                recipient_interest=input_data["recipient_interest"],
                template_type=TemplateType(input_data["template_type"])
            )

            # Run pipeline
            runner = create_email_pipeline()
            email_id = await runner.run(pipeline_data)

            # Return result
            result = {
                "email_id": email_id,
                "status": "completed",
                "duration": pipeline_data.total_duration(),
                "step_timings": pipeline_data.step_timings
            }

            logfire.info(
                "Task completed successfully",
                task_id=task_id,
                email_id=email_id,
                duration=pipeline_data.total_duration()
            )

            return result

        except Exception as e:
            logfire.error(
                "Task failed",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )

            # Retry with exponential backoff
            retry_countdown = 2 ** self.request.retries
            raise self.retry(exc=e, countdown=retry_countdown)
```

### 5.3 Worker Startup Script

**File: `worker.py`**

```python
"""
Celery worker startup script.

Usage:
    python worker.py
"""

from celery_config import celery_app

if __name__ == "__main__":
    celery_app.worker_main([
        "worker",
        "--loglevel=info",
        "--concurrency=4",
        "--queues=email_high,email_default",
        "--max-tasks-per-child=100"  # Restart worker after 100 tasks
    ])
```

---

## 6. FastAPI Endpoints

### 6.1 Email Generation Routes

**File: `api/routes/email.py`**

```python
"""
FastAPI routes for email generation pipeline.
"""

from fastapi import APIRouter, Depends, HTTPException
from celery.result import AsyncResult
from sqlalchemy.orm import Session

from api.dependencies import get_current_user
from database.dependencies import get_db
from models.user import User
from models.email import Email
from schemas.pipeline import (
    GenerateEmailRequest,
    GenerateEmailResponse,
    TaskStatusResponse,
    EmailResponse
)
from celery_tasks.pipeline import generate_email_task
from celery_config import celery_app
import logfire


router = APIRouter(prefix="/api/email", tags=["Email Generation"])


@router.post("/generate", response_model=GenerateEmailResponse)
async def generate_email(
    request: GenerateEmailRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Enqueue an email generation job.

    Returns task_id for status polling.
    """

    with logfire.span("api.generate_email", user_id=str(current_user.id)):
        # Dispatch Celery task
        task = generate_email_task.apply_async(
            kwargs={
                "user_id": str(current_user.id),
                "email_template": request.email_template,
                "recipient_name": request.recipient_name,
                "recipient_interest": request.recipient_interest
            },
            queue="email_high"
        )

        logfire.info(
            "Email generation task enqueued",
            task_id=task.id,
            user_id=str(current_user.id)
        )

        return GenerateEmailResponse(task_id=task.id)


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Check Celery task status.

    Returns:
        - PENDING: Task waiting in queue
        - STARTED: Task is executing
        - SUCCESS: Task completed successfully
        - FAILURE: Task failed
    """

    result = AsyncResult(task_id, app=celery_app)

    return TaskStatusResponse(
        task_id=task_id,
        status=result.state,
        result=result.result if result.ready() and result.successful() else None,
        error=str(result.info) if result.failed() else None
    )


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch generated email from database"""

    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(404, "Email not found or access denied")

    return EmailResponse.from_orm(email)
```

---

## 7. Logfire Observability

### 7.1 Configuration

**File: `observability/logfire_config.py`**

```python
"""
Logfire configuration and setup.
"""

import logfire
import os
from logfire.integrations.fastapi import LogfireMiddleware


def configure_logfire():
    """Initialize Logfire with application settings"""

    logfire.configure(
        service_name="scribe-backend",
        service_version="1.0.0",
        environment=os.getenv("LOGFIRE_ENVIRONMENT", "development"),
        token=os.getenv("LOGFIRE_TOKEN")
    )

    logfire.info("Logfire configured successfully")


def add_logfire_middleware(app):
    """Add Logfire middleware to FastAPI app"""

    app.add_middleware(LogfireMiddleware)
    logfire.info("Logfire middleware added to FastAPI")
```

### 7.2 Key Metrics to Track

```python
# Custom metrics examples

# Track pipeline duration by template type
logfire.metric(
    "pipeline.duration",
    value=duration,
    unit="seconds",
    attributes={
        "template_type": template_type,
        "user_id": user_id
    }
)

# Track step success rate
logfire.metric(
    "pipeline.step.success_rate",
    value=1.0 if success else 0.0,
    attributes={
        "step_name": step_name
    }
)

# Track API latency
logfire.metric(
    "api.latency",
    value=response_time,
    unit="milliseconds",
    attributes={
        "endpoint": "/api/email/generate"
    }
)
```

---
## 9. Deployment Guide

### 9.1 Required Services

```yaml
# docker-compose.yml

version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  celery_worker:
    build: .
    command: python worker.py
    depends_on:
      - redis
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
      - DATABASE_URL=${DATABASE_URL}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LOGFIRE_TOKEN=${LOGFIRE_TOKEN}

  api:
    build: .
    command: uvicorn main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    depends_on:
      - redis
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - SUPABASE_URL=${SUPABASE_URL}
      - LOGFIRE_TOKEN=${LOGFIRE_TOKEN}
```

---

## 9. Migration from Legacy Flask

### 9.1 Code Mapping

| Legacy Function | New Component |
|----------------|---------------|
| `scrape_professor_publications()` | `WebScraperStep._execute_step()` |
| `google_search()` | `web_scraper/utils.py::google_custom_search()` |
| `scrape_website_text()` | `web_scraper/utils.py::scrape_website()` |
| `summarize_text()` | Removed - LLM does this in EmailComposer |
| `final_together()` | `EmailComposerStep._execute_step()` |
| `/generate-email` endpoint | `/api/email/generate` |

### 9.2 Migration Checklist

- [x] Set up Redis and Celery workers
- [x] Add `template_type` and `metadata` columns to emails table
- [x] Implement all 4 pipeline steps
- [ ] Create Celery tasks
- [ ] Update API endpoints
- [ ] Test with production API keys
- [ ] Run migration on staging
- [ ] Gradual rollout to production
- [ ] Monitor Logfire dashboards
- [ ] Deprecate legacy endpoints

---

## 10. What's Left - Path to Production

This section details all remaining work before the pipeline is fully operational and users can send requests through the Render server.

### 10.1 Celery Task Implementation (HIGH PRIORITY)

**Status:** Infrastructure ready, tasks NOT implemented

**What exists:**
- `celery_config.py`: Celery app configuration ✅
- `worker.py`: Celery worker entry point ✅
- Queue and routing configuration ✅

**What's missing:**
- **Actual Celery task definitions** for email generation
- Task file location should be: `tasks/email_tasks.py`
- Required task: `generate_email_task(task_id, user_id, email_template, recipient_name, recipient_interest)`

**Implementation needed:**
```python
# tasks/email_tasks.py (DOES NOT EXIST YET)

from celery_config import celery_app
from pipeline.core.runner import PipelineRunner
from pipeline.steps.template_parser.main import TemplateParserStep
from pipeline.steps.web_scraper.main import WebScraperStep
from pipeline.steps.arxiv_helper.main import ArxivHelperStep
from pipeline.steps.email_composer.main import EmailComposerStep
from pipeline.models.core import PipelineData, JobStatus
import logfire


@celery_app.task(bind=True, name="tasks.generate_email")
def generate_email_task(
    self,
    task_id: str,
    user_id: str,
    email_template: str,
    recipient_name: str,
    recipient_interest: str
):
    """
    Celery task for email generation pipeline.

    This task orchestrates the 4-step pipeline and handles all error cases.
    """
    # Implementation needed:
    # 1. Create PipelineData
    # 2. Initialize PipelineRunner with steps
    # 3. Run pipeline with error handling
    # 4. Return email_id on success
    # 5. Update task status in Redis/database
    pass
```

**Blocker:** This is the CRITICAL missing piece - without Celery tasks, the API cannot trigger email generation asynchronously.

---

### 10.2 API Routes for Email Generation (HIGH PRIORITY)

**Status:** User management complete, email generation endpoints NOT implemented

**What exists:**
- `api/routes/user.py`: User initialization and profile ✅
- `api/dependencies.py`: Authentication dependencies ✅
- FastAPI app structure ✅

**What's missing:**
- **Email generation API endpoints** in `api/routes/email.py` (FILE DOES NOT EXIST)
- Required endpoints:
  - `POST /api/email/generate`: Trigger email generation task
  - `GET /api/email/status/{task_id}`: Check task status
  - `GET /api/email/{email_id}`: Retrieve generated email
  - `GET /api/email/history`: User's email history

**Implementation template:**
```python
# api/routes/email.py (DOES NOT EXIST YET)

from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_current_user
from models.user import User
from tasks.email_tasks import generate_email_task
import uuid

router = APIRouter(prefix="/api/email", tags=["email"])


@router.post("/generate")
async def trigger_email_generation(
    request: EmailGenerationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Trigger async email generation via Celery.

    Returns task_id for status polling.
    """
    task_id = str(uuid.uuid4())

    # Trigger Celery task
    generate_email_task.delay(
        task_id=task_id,
        user_id=current_user.id,
        email_template=request.email_template,
        recipient_name=request.recipient_name,
        recipient_interest=request.recipient_interest
    )

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Email generation started"
    }


@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Poll task status from Celery."""
    # Implementation needed
    pass
```

**Blocker:** Frontend cannot trigger email generation without these endpoints.

---

### 10.3 Pydantic Schemas for API Validation (MEDIUM PRIORITY)

**Status:** Partially complete

**What exists:**
- `schemas/auth.py`: Authentication schemas ✅

**What's missing:**
- **Email generation request/response schemas** in `schemas/email.py` (FILE DOES NOT EXIST)
- Required schemas:
  - `EmailGenerationRequest`: Validate generation inputs
  - `EmailGenerationResponse`: Task initiation response
  - `EmailStatusResponse`: Task status polling response
  - `EmailHistoryResponse`: List of generated emails

**Implementation template:**
```python
# schemas/email.py (DOES NOT EXIST YET)

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from pipeline.models.core import TemplateType, JobStatus


class EmailGenerationRequest(BaseModel):
    email_template: str = Field(..., min_length=10, max_length=5000)
    recipient_name: str = Field(..., min_length=2, max_length=200)
    recipient_interest: str = Field(..., min_length=2, max_length=500)


class EmailGenerationResponse(BaseModel):
    task_id: str
    status: JobStatus
    message: str


class EmailStatusResponse(BaseModel):
    task_id: str
    status: JobStatus
    email_id: Optional[str] = None
    error: Optional[str] = None
    progress: Optional[dict] = None  # Step-by-step progress
```

### 10.7 Playwright Browser Setup for Production (HIGH PRIORITY)

**Status:** Local implementation done, production deployment needs configuration

**What exists:**
- `scrape_url()` function using Playwright ✅
- Headless browser configuration ✅
- `--no-sandbox` flag for containers ✅

**What's needed for Render:**
- **Browser binaries installation** in Docker container
- Playwright browsers are ~300MB
- Render's build process must include: `playwright install chromium`
- Update `requirements.txt` or add build script

**Render build command:**
```bash
pip install -r requirements.txt && playwright install chromium
```

---

## 10.9 Deployment Checklist - Production Readiness

### ✅ Completed
- [x] Pipeline core architecture (PipelineRunner, BasePipelineStep)
- [x] All 4 pipeline steps implemented and tested
- [x] Database models and migrations
- [x] User authentication and authorization
- [x] Pydantic-ai agent integration
- [x] Logfire instrumentation
- [x] Two-tier summarization architecture
- [x] Playwright web scraping
- [x] ArXiv integration with relevance scoring
- [x] Email validation with retry logic

### 🚧 In Progress / Blocked
- [ ] **Celery task implementation** (tasks/email_tasks.py) - **BLOCKER**
- [ ] **Email generation API endpoints** (api/routes/email.py) - **BLOCKER**
- [ ] **Pydantic schemas for email** (schemas/email.py) - **BLOCKER**
- [ ] **Redis setup on Render** - **BLOCKER**
- [ ] **Google Custom Search API credentials** - **BLOCKER**
- [ ] **Playwright browser installation in production** - **BLOCKER**

### 📋 Nice to Have (Post-MVP)
- [ ] Task status tracking database table
- [ ] WebSocket support for real-time updates
- [ ] Comprehensive integration test suite
- [ ] Load testing and performance benchmarks
- [ ] Admin dashboard for monitoring tasks
- [ ] Rate limiting and usage quotas

---

## 10.10 Estimated Timeline to Production

**Critical Path (minimum viable product):**
1. **Celery tasks implementation** - 4-6 hours
2. **API endpoints for email generation** - 3-4 hours
3. **Pydantic schemas** - 1-2 hours
4. **Redis setup on Render** - 1-2 hours
5. **Google Custom Search API setup** - 1 hour
6. **Playwright production config** - 2-3 hours
7. **Integration testing** - 3-4 hours
8. **Deployment and smoke testing** - 2-3 hours

**Biggest unknowns:**
- Redis performance on Render (may need external provider like Upstash)
- Playwright memory usage in production (may hit Render memory limits)
- Google Custom Search API quota and cost

---
