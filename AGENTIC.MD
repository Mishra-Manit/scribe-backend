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

    This is the expected JSON format from Claude API.
    """

    search_terms: List[str] = Field(
        ...,
        min_items=1,
        max_items=5,
        description="Search queries to use for web scraping"
    )

    placeholders: List[str] = Field(
        default_factory=list,
        description="Placeholders found in template (e.g., {{name}}, {{research}})"
    )

    tone: str = Field(
        ...,
        description="Detected tone of the template (formal, casual, enthusiastic, etc.)"
    )

    key_topics: List[str] = Field(
        default_factory=list,
        description="Main topics/themes in the template"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "search_terms": [
                    "Dr. Jane Smith machine learning",
                    "Jane Smith publications research",
                    "Jane Smith university faculty page"
                ],
                "placeholders": ["{{name}}", "{{research}}", "{{university}}"],
                "tone": "enthusiastic",
                "key_topics": ["machine learning", "research", "publications"]
            }
        }
```

#### File: `pipeline/steps/template_parser/prompts.py`

```python
"""
Prompts for TemplateParser step.

All Anthropic Claude prompts are defined here for easy modification.
"""


def get_template_analysis_prompt(
    email_template: str,
    recipient_name: str,
    recipient_interest: str,
    template_type: str
) -> str:
    """
    Generate prompt for template analysis.

    Args:
        email_template: User's email template with placeholders
        recipient_name: Full name of recipient
        recipient_interest: Research area/interest
        template_type: Type of template (research, book, general)

    Returns:
        Formatted prompt string
    """

    return f"""You are an expert at analyzing email templates and creating effective search queries.

Your task is to analyze this cold email template and generate optimal search terms to find relevant information about the recipient.

**EMAIL TEMPLATE:**
{email_template}

**RECIPIENT:**
Name: {recipient_name}
Interest/Field: {recipient_interest}
Template Type: {template_type}

**YOUR TASK:**
Generate 3-5 search queries that will help us find:
1. Professional information about {recipient_name}
2. Publications, research, or books (depending on template type)
3. Academic affiliations and positions
4. Awards, honors, or notable achievements

**REQUIREMENTS:**
- Search terms should be specific and targeted
- Include variations of the recipient's name
- Prioritize .edu domains and academic sources
- For template_type='research': focus on papers and publications
- For template_type='book': focus on authored books
- For template_type='general': focus on professional bio and achievements

**OUTPUT FORMAT (JSON):**
Return ONLY valid JSON matching this structure:
{{
  "search_terms": ["query 1", "query 2", "query 3"],
  "placeholders": ["{{name}}", "{{research}}"],
  "tone": "enthusiastic",
  "key_topics": ["machine learning", "computer vision"]
}}

Generate the JSON now:"""
```

#### File: `pipeline/steps/template_parser/main.py`

```python
"""
TemplateParser step implementation.

Extracts search terms from email template using Anthropic Claude API.
"""

import anthropic
import logfire
from typing import Optional
import os

from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
from pipeline.core.exceptions import ExternalAPIError, ValidationError
from pipeline.steps.template_parser.models import TemplateAnalysis
from pipeline.steps.template_parser.prompts import get_template_analysis_prompt


class TemplateParserStep(BasePipelineStep):
    """
    Step 1: Parse email template and extract search terms.

    Uses Anthropic Claude to analyze the template and generate
    optimal search queries for finding recipient information.
    """

    def __init__(self):
        super().__init__("template_parser")

        # Initialize Anthropic client
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = anthropic.Anthropic(api_key=api_key)

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """
        Validate that required input fields are present.

        Args:
            pipeline_data: Shared pipeline data

        Returns:
            Error message if validation fails, None if valid
        """
        if not pipeline_data.email_template:
            return "email_template is empty"

        if not pipeline_data.recipient_name:
            return "recipient_name is empty"

        if not pipeline_data.recipient_interest:
            return "recipient_interest is empty"

        # Check for at least one placeholder
        if "{{" not in pipeline_data.email_template:
            return "email_template must contain at least one placeholder {{...}}"

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute template analysis with Anthropic Claude.

        Updates pipeline_data.search_terms and pipeline_data.template_analysis

        Args:
            pipeline_data: Shared data object (modified in-place)

        Returns:
            StepResult with success/failure status
        """
        # Generate prompt
        prompt = get_template_analysis_prompt(
            email_template=pipeline_data.email_template,
            recipient_name=pipeline_data.recipient_name,
            recipient_interest=pipeline_data.recipient_interest,
            template_type=pipeline_data.template_type.value
        )

        try:
            # Call Anthropic API with Logfire span
            with logfire.span("anthropic.template_analysis"):
                response = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1024,
                    temperature=0.3,  # Lower temp for more consistent output
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )

            # Extract JSON response
            response_text = response.content[0].text

            logfire.info(
                "Anthropic response received",
                response_length=len(response_text),
                model=response.model
            )

            # Parse and validate response with Pydantic
            try:
                analysis = TemplateAnalysis.model_validate_json(response_text)
            except Exception as e:
                raise ValidationError(f"Failed to parse LLM response as JSON: {e}")

            # Update pipeline data
            pipeline_data.search_terms = analysis.search_terms
            pipeline_data.template_analysis = {
                "placeholders": analysis.placeholders,
                "tone": analysis.tone,
                "key_topics": analysis.key_topics
            }

            logfire.info(
                "Template parsing completed",
                search_terms_count=len(analysis.search_terms),
                tone=analysis.tone
            )

            # Return success
            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={
                    "search_terms_extracted": len(analysis.search_terms),
                    "placeholders_found": len(analysis.placeholders),
                    "tone": analysis.tone
                }
            )

        except anthropic.APIError as e:
            # Anthropic API error - retriable
            logfire.error("Anthropic API error", error=str(e))
            raise ExternalAPIError(f"Anthropic API failed: {e}")

        except Exception as e:
            # Unexpected error
            logfire.error("Unexpected error in template parsing", error=str(e))
            raise
```

---

### 4.3 Step 2: Web Scraper

**Purpose:** Fetch and scrape web content using search terms from Step 1.

#### File: `pipeline/steps/web_scraper/utils.py`

```python
"""
Utility functions for web scraping.

Migrated from legacy api/legacy/app.py with improvements:
- Async with httpx (replacing requests)
- Better error handling
- Rate limiting
- Logfire integration
"""

import httpx
import logfire
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import re
import asyncio


async def google_custom_search(
    search_term: str,
    api_key: str,
    cse_id: str,
    num_results: int = 3
) -> List[Dict[str, str]]:
    """
    Perform Google Custom Search API query.

    Args:
        search_term: Query string
        api_key: Google API key
        cse_id: Custom Search Engine ID
        num_results: Number of results to return (max 10)

    Returns:
        List of search results with 'title', 'link', 'snippet'

    Raises:
        ExternalAPIError: If API call fails
    """
    url = "https://www.googleapis.com/customsearch/v1"

    params = {
        "key": api_key,
        "cx": cse_id,
        "q": search_term,
        "num": num_results
    }

    with logfire.span("google_custom_search", query=search_term):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()

            data = response.json()
            results = data.get("items", [])

            logfire.info(
                "Google search completed",
                query=search_term,
                results_count=len(results)
            )

            return results

        except httpx.HTTPError as e:
            logfire.error("Google API error", error=str(e))
            raise ExternalAPIError(f"Google Custom Search failed: {e}")


async def scrape_website(url: str, timeout: float = 10.0) -> Optional[str]:
    """
    Scrape text content from a URL.

    Args:
        url: URL to scrape
        timeout: Request timeout in seconds

    Returns:
        Cleaned text content, or None if scraping fails
    """
    # Skip non-HTML files
    if url.endswith(('.pdf', '.doc', '.docx', '.ppt', '.pptx')):
        logfire.warning("Skipping non-HTML URL", url=url)
        return None

    with logfire.span("scrape_website", url=url):
        try:
            # Headers to avoid being blocked
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers=headers
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, "html.parser")

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()

            # Extract text
            text = soup.get_text(separator=" ")

            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            cleaned_text = " ".join(chunk for chunk in chunks if chunk)

            # Validate text is English and meaningful
            if not is_english_text(cleaned_text) or len(cleaned_text) < 100:
                logfire.warning("Scraped content too short or non-English", url=url)
                return None

            logfire.info(
                "Website scraped successfully",
                url=url,
                content_length=len(cleaned_text)
            )

            return cleaned_text

        except httpx.TimeoutException:
            logfire.warning("Scraping timeout", url=url)
            return None

        except httpx.HTTPError as e:
            logfire.warning("HTTP error during scraping", url=url, error=str(e))
            return None

        except Exception as e:
            logfire.warning("Unexpected scraping error", url=url, error=str(e))
            return None


def is_english_text(text: str) -> bool:
    """
    Check if text is predominantly English.

    Args:
        text: Text to check

    Returns:
        True if text appears to be English
    """
    # Check for English alphabet characters
    english_chars = sum(1 for c in text if c.isalpha() and ord(c) < 128)
    total_chars = sum(1 for c in text if c.isalpha())

    if total_chars == 0:
        return False

    # At least 80% English characters
    return (english_chars / total_chars) > 0.8


def clean_text(text: str, max_length: int = 5000) -> str:
    """
    Clean and truncate scraped text.

    Args:
        text: Raw text
        max_length: Maximum length to keep

    Returns:
        Cleaned and truncated text
    """
    # Remove non-printable characters
    text = re.sub(r'[^\x20-\x7E\n]', '', text)

    # Collapse multiple spaces
    text = re.sub(r' +', ' ', text)

    # Collapse multiple newlines
    text = re.sub(r'\n+', '\n', text)

    # Truncate
    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text.strip()
```

#### File: `pipeline/steps/web_scraper/main.py`

```python
"""
WebScraper step implementation.

Fetches web content based on search terms from TemplateParser.
"""

import os
import logfire
from typing import Optional, List, Dict, Set
import asyncio

from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
from pipeline.core.exceptions import ExternalAPIError
from pipeline.steps.web_scraper.utils import (
    google_custom_search,
    scrape_website,
    clean_text
)


class WebScraperStep(BasePipelineStep):
    """
    Step 2: Scrape web content using search terms.

    Uses Google Custom Search API to find relevant URLs,
    then scrapes and cleans the content.
    """

    def __init__(self):
        super().__init__("web_scraper")

        # Load API credentials
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.google_cse_id = os.getenv("GOOGLE_CSE_ID")

        if not self.google_api_key or not self.google_cse_id:
            raise ValueError(
                "GOOGLE_API_KEY and GOOGLE_CSE_ID environment variables must be set"
            )

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """Validate that search terms were extracted"""
        if not pipeline_data.search_terms:
            return "search_terms is empty (TemplateParser step must run first)"
        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute web scraping.

        Updates:
        - pipeline_data.scraped_content
        - pipeline_data.scraped_urls
        - pipeline_data.scraping_metadata

        Args:
            pipeline_data: Shared data object

        Returns:
            StepResult with scraping statistics
        """
        all_content = []
        scraped_urls: Set[str] = set()
        total_urls_tried = 0
        successful_scrapes = 0
        failed_urls: List[str] = []

        # Iterate through search terms
        for search_term in pipeline_data.search_terms[:3]:  # Limit to first 3 terms
            logfire.info("Processing search term", term=search_term)

            try:
                # Get search results
                results = await google_custom_search(
                    search_term=search_term,
                    api_key=self.google_api_key,
                    cse_id=self.google_cse_id,
                    num_results=3
                )

                # Scrape each URL (with concurrency limit)
                for result in results:
                    url = result.get("link")
                    if not url or url in scraped_urls:
                        continue

                    total_urls_tried += 1

                    # Scrape website
                    content = await scrape_website(url)

                    if content:
                        # Prioritize .edu and academic sites
                        priority = 1 if any(domain in url for domain in ['.edu', 'scholar.google', 'researchgate']) else 2

                        all_content.append({
                            "content": content,
                            "url": url,
                            "priority": priority
                        })

                        scraped_urls.add(url)
                        successful_scrapes += 1

                        logfire.info(
                            "URL scraped successfully",
                            url=url,
                            priority=priority,
                            content_length=len(content)
                        )
                    else:
                        failed_urls.append(url)

                    # Stop if we have enough content
                    if len(all_content) >= 5:
                        break

                # Rate limiting between search terms
                await asyncio.sleep(0.5)

            except ExternalAPIError as e:
                logfire.error("Search term failed", term=search_term, error=str(e))
                # Continue with next search term
                continue

            # Stop if we have enough content
            if len(all_content) >= 5:
                break

        # Check if we got any content
        if not all_content:
            logfire.warning("No content scraped from any source")
            return StepResult(
                success=False,
                step_name=self.step_name,
                error="Failed to scrape any content from web sources",
                warnings=["All scraping attempts failed"]
            )

        # Sort by priority (academic sources first)
        all_content.sort(key=lambda x: x["priority"])

        # Combine and clean content
        combined_text = "\n\n".join(
            f"Source: {item['url']}\n{item['content']}"
            for item in all_content[:5]  # Top 5 sources
        )

        cleaned_content = clean_text(combined_text, max_length=5000)

        # Update pipeline data
        pipeline_data.scraped_content = cleaned_content
        pipeline_data.scraped_urls = [item["url"] for item in all_content[:5]]
        pipeline_data.scraping_metadata = {
            "total_urls_tried": total_urls_tried,
            "successful_scrapes": successful_scrapes,
            "failed_urls": failed_urls[:10],  # Keep first 10 failures
            "content_length": len(cleaned_content)
        }

        logfire.info(
            "Web scraping completed",
            successful_scrapes=successful_scrapes,
            total_urls_tried=total_urls_tried,
            final_content_length=len(cleaned_content)
        )

        # Return success
        return StepResult(
            success=True,
            step_name=self.step_name,
            metadata={
                "urls_scraped": successful_scrapes,
                "content_length": len(cleaned_content)
            },
            warnings=[f"{len(failed_urls)} URLs failed to scrape"] if failed_urls else []
        )
```

---

### 4.4 Step 3: ArXiv Enricher

**Purpose:** Fetch academic papers from ArXiv (conditional on template_type).

#### File: `pipeline/steps/arxiv_enricher/models.py`

```python
"""
Pydantic models for ArXiv data.
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional


class ArxivPaper(BaseModel):
    """
    Represents a single paper from ArXiv.
    """

    title: str = Field(..., description="Paper title")

    abstract: str = Field(..., description="Paper abstract")

    authors: List[str] = Field(
        default_factory=list,
        description="List of author names"
    )

    year: int = Field(..., description="Publication year")

    url: str = Field(..., description="ArXiv URL")

    arxiv_id: str = Field(..., description="ArXiv identifier")

    relevance_score: Optional[float] = Field(
        None,
        description="Relevance score (0-1) based on recipient name match"
    )
```

#### File: `pipeline/steps/arxiv_enricher/main.py`

```python
"""
ArxivEnricher step implementation.

Fetches academic papers from ArXiv API (only for template_type=RESEARCH).
"""

import httpx
import logfire
from typing import Optional, List
import xml.etree.ElementTree as ET
from datetime import datetime

from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult, TemplateType
from pipeline.core.exceptions import ExternalAPIError
from pipeline.steps.arxiv_enricher.models import ArxivPaper


class ArxivEnricherStep(BasePipelineStep):
    """
    Step 3: Fetch academic papers from ArXiv.

    Only executes if template_type == RESEARCH.
    Otherwise, returns success with no papers.
    """

    def __init__(self):
        super().__init__("arxiv_enricher")

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute ArXiv enrichment (conditional).

        Updates pipeline_data.arxiv_papers

        Args:
            pipeline_data: Shared data object

        Returns:
            StepResult with paper count
        """
        # Check if this step should run
        if pipeline_data.template_type != TemplateType.RESEARCH:
            logfire.info(
                "Skipping ArXiv enrichment",
                template_type=pipeline_data.template_type.value,
                reason="Only runs for template_type=RESEARCH"
            )

            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={"papers_found": 0, "skipped": True}
            )

        # Extract author name for search
        author_name = self._extract_author_name(pipeline_data.recipient_name)

        logfire.info("Searching ArXiv", author=author_name)

        try:
            # Search ArXiv API
            papers = await self._search_arxiv(
                author_name=author_name,
                max_results=10
            )

            # Filter and score papers
            relevant_papers = self._filter_papers(
                papers=papers,
                recipient_name=pipeline_data.recipient_name,
                interest=pipeline_data.recipient_interest
            )

            # Keep top 5 most relevant
            top_papers = sorted(
                relevant_papers,
                key=lambda p: p.relevance_score or 0,
                reverse=True
            )[:5]

            # Update pipeline data
            pipeline_data.arxiv_papers = [
                {
                    "title": paper.title,
                    "abstract": paper.abstract,
                    "authors": paper.authors,
                    "year": paper.year,
                    "url": paper.url,
                    "arxiv_id": paper.arxiv_id,
                    "relevance_score": paper.relevance_score
                }
                for paper in top_papers
            ]

            pipeline_data.enrichment_metadata = {
                "papers_found": len(papers),
                "papers_filtered": len(relevant_papers),
                "papers_kept": len(top_papers)
            }

            logfire.info(
                "ArXiv enrichment completed",
                papers_found=len(papers),
                papers_kept=len(top_papers)
            )

            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={"papers_found": len(top_papers)},
                warnings=[
                    "No papers found on ArXiv"
                ] if len(top_papers) == 0 else []
            )

        except Exception as e:
            # Non-fatal error - continue without papers
            logfire.warning("ArXiv search failed", error=str(e))

            pipeline_data.arxiv_papers = []

            return StepResult(
                success=True,  # Don't fail pipeline
                step_name=self.step_name,
                metadata={"papers_found": 0},
                warnings=[f"ArXiv API error: {str(e)}"]
            )

    def _extract_author_name(self, full_name: str) -> str:
        """
        Extract last name for ArXiv search.

        Args:
            full_name: Full name (e.g., "Dr. Jane Smith")

        Returns:
            Last name (e.g., "Smith")
        """
        # Remove titles
        name = full_name.replace("Dr.", "").replace("Prof.", "").strip()

        # Split and get last part
        parts = name.split()
        return parts[-1] if parts else name

    async def _search_arxiv(
        self,
        author_name: str,
        max_results: int = 10
    ) -> List[ArxivPaper]:
        """
        Search ArXiv API.

        Args:
            author_name: Author last name
            max_results: Maximum number of results

        Returns:
            List of ArxivPaper objects

        Raises:
            ExternalAPIError: If API call fails
        """
        url = "http://export.arxiv.org/api/query"

        params = {
            "search_query": f"au:{author_name}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        }

        with logfire.span("arxiv_api_search", author=author_name):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()

                # Parse XML response
                root = ET.fromstring(response.content)
                namespace = {"atom": "http://www.w3.org/2005/Atom"}

                papers = []
                for entry in root.findall("atom:entry", namespace):
                    try:
                        paper = self._parse_arxiv_entry(entry, namespace)
                        papers.append(paper)
                    except Exception as e:
                        logfire.warning("Failed to parse ArXiv entry", error=str(e))
                        continue

                return papers

            except httpx.HTTPError as e:
                raise ExternalAPIError(f"ArXiv API failed: {e}")

    def _parse_arxiv_entry(
        self,
        entry: ET.Element,
        namespace: dict
    ) -> ArxivPaper:
        """Parse a single ArXiv XML entry"""

        title = entry.find("atom:title", namespace).text.strip()
        abstract = entry.find("atom:summary", namespace).text.strip()

        authors = [
            author.find("atom:name", namespace).text
            for author in entry.findall("atom:author", namespace)
        ]

        # Extract year from published date
        published = entry.find("atom:published", namespace).text
        year = int(published[:4])

        # Get ArXiv ID and URL
        arxiv_id = entry.find("atom:id", namespace).text.split("/abs/")[-1]
        url = f"https://arxiv.org/abs/{arxiv_id}"

        return ArxivPaper(
            title=title,
            abstract=abstract,
            authors=authors,
            year=year,
            url=url,
            arxiv_id=arxiv_id
        )

    def _filter_papers(
        self,
        papers: List[ArxivPaper],
        recipient_name: str,
        interest: str
    ) -> List[ArxivPaper]:
        """
        Filter and score papers by relevance.

        Args:
            papers: List of papers from ArXiv
            recipient_name: Recipient's full name
            interest: Research interest

        Returns:
            Filtered list with relevance scores
        """
        last_name = self._extract_author_name(recipient_name).lower()
        interest_lower = interest.lower()

        relevant_papers = []

        for paper in papers:
            # Check if recipient is author (case-insensitive)
            is_author = any(
                last_name in author.lower()
                for author in paper.authors
            )

            if not is_author:
                continue

            # Calculate relevance score
            score = 0.5  # Base score for being an author

            # Boost if interest mentioned in title/abstract
            if interest_lower in paper.title.lower():
                score += 0.3
            if interest_lower in paper.abstract.lower():
                score += 0.2

            # Boost for recent papers
            current_year = datetime.now().year
            if current_year - paper.year <= 2:
                score += 0.1

            paper.relevance_score = min(score, 1.0)
            relevant_papers.append(paper)

        return relevant_papers
```

---

### 4.5 Step 4: Email Composer (CRITICAL STEP)

**Purpose:** Compose final email using all gathered data and write to database.

This is the ONLY step that writes to the database.

#### File: `pipeline/steps/email_composer/models.py`

```python
"""
Pydantic models for EmailComposer step.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional


class EmailValidation(BaseModel):
    """
    Validation result for composed email.

    Used to ensure email quality before saving to database.
    """

    is_valid: bool = Field(..., description="Whether email passes validation")

    issues: List[str] = Field(
        default_factory=list,
        description="List of validation issues found"
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings"
    )

    has_publication_mention: bool = Field(
        default=False,
        description="Whether email mentions at least one publication"
    )

    has_placeholders: bool = Field(
        default=False,
        description="Whether unfilled placeholders remain ({{...}})"
    )

    length: int = Field(..., description="Email length in characters")


class ComposedEmail(BaseModel):
    """
    Final composed email from Anthropic.
    """

    email_content: str = Field(
        ...,
        min_length=100,
        max_length=5000,
        description="Final email content"
    )

    @validator("email_content")
    def validate_no_placeholders(cls, v):
        """Ensure no unfilled placeholders remain"""
        if "{{" in v or "}}" in v:
            raise ValueError("Email contains unfilled placeholders")
        return v
```

#### File: `pipeline/steps/email_composer/prompts.py`

```python
"""
Prompts for EmailComposer step.

Migrated from legacy final_together() function with improvements.
"""


def get_email_composition_prompt(
    email_template: str,
    recipient_name: str,
    recipient_interest: str,
    template_type: str,
    scraped_content: str,
    arxiv_papers: list,
    template_analysis: dict
) -> str:
    """
    Generate prompt for email composition.

    This is the main prompt that generates the final email.
    """

    # Build context from scraped content
    web_context = f"""
**WEB SEARCH CONTEXT:**
{scraped_content[:3000]}  # Limit to avoid token overflow
"""

    # Build papers context (if available)
    papers_context = ""
    if arxiv_papers:
        papers_list = "\n".join([
            f"- \"{paper['title']}\" ({paper['year']}) - {paper['abstract'][:200]}..."
            for paper in arxiv_papers[:3]
        ])
        papers_context = f"""
**RESEARCH PAPERS BY {recipient_name}:**
{papers_list}
"""

    # Get template tone and topics
    tone = template_analysis.get("tone", "professional")
    key_topics = template_analysis.get("key_topics", [])

    return f"""You are an expert cold email writer who specializes in crafting authentic, human-like academic outreach emails.

**YOUR PRIMARY GOAL:** Write in a natural, conversational way that perfectly matches the sender's unique writing style and tone.

**WRITING PHILOSOPHY:**
- Write like a real person, not an AI - avoid robotic or overly formal language
- Every email template has its own personality - study and mirror it exactly
- The recipient should feel like they're hearing from a genuine human who took time to research them
- Natural flow is more important than perfect grammar - write how people actually email

**TEMPLATE TO COMPLETE:**
{email_template}

**RECIPIENT INFORMATION:**
Name: {recipient_name}
Field/Interest: {recipient_interest}
Template Type: {template_type}

**AVAILABLE RESEARCH DATA:**
{web_context}

{papers_context if papers_context else "**Note:** No research papers found. Use web context to personalize."}

**TEMPLATE STYLE ANALYSIS:**
- Detected Tone: {tone}
- Key Topics: {', '.join(key_topics)}

**CRITICAL INSTRUCTIONS:**

1. **MATCH THE EXACT WRITING STYLE:**
   - Study the template's vocabulary, sentence structure, energy level, and personality
   - Your replacements should sound EXACTLY like the person who wrote the template
   - If the template is casual and uses contractions, your replacements should too
   - If the template is energetic with exclamation points, maintain that energy
   - Match the sentence length patterns - short & punchy or long & flowing

2. **FILL ALL PLACEHOLDERS:**
   - Replace ALL text within square brackets [ ] or curly braces {{{{ }}}} with specific information
   - Use the research data to fill placeholders naturally
   - NEVER leave placeholders unfilled
   - NEVER use phrases like "your work" or "your research" without specifics

3. **PUBLICATION MENTIONS (for template_type='research'):**
   - Include at least ONE specific publication title
   - Introduce it naturally as the template writer would
   - Don't use AI-sounding phrases like "groundbreaking" or "cutting-edge" unless the template uses them

4. **PRESERVE FORMATTING:**
   - Maintain ALL paragraph breaks from the original template
   - Keep the same line spacing and structure
   - Preserve greeting and closing if present

5. **NATURAL WRITING:**
   - Prioritize natural flow over perfect accuracy
   - Use conversational transitions that match the template style
   - Avoid generic phrases - be specific using the research data
   - Write how a real person would email, not how an AI would

**VALIDATION RULES:**
- Email must be between 100-5000 characters
- Email must NOT contain {{{{ }}}} or [ ] brackets
- Email must mention specific details about {recipient_name}
- For template_type='research': Must mention at least one publication title

**OUTPUT FORMAT:**
Return ONLY the completed email, with no preamble or explanation.
Start with the email greeting and end with the closing.

Generate the email now:"""
```

#### File: `pipeline/steps/email_composer/main.py`

```python
"""
EmailComposer step implementation.

The FINAL and MOST CRITICAL step - composes email and writes to database.
"""

import anthropic
import logfire
from typing import Optional
import os
import re
from uuid import uuid4

from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult, TemplateType
from pipeline.core.exceptions import ExternalAPIError, ValidationError
from pipeline.steps.email_composer.models import ComposedEmail, EmailValidation
from pipeline.steps.email_composer.prompts import get_email_composition_prompt
from models.email import Email
from database.session import get_db


class EmailComposerStep(BasePipelineStep):
    """
    Step 4: Compose final email and write to database.

    This is the ONLY step that performs database writes.
    All previous steps only populate PipelineData in-memory.
    """

    def __init__(self):
        super().__init__("email_composer")

        # Initialize Anthropic client
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.max_retries = 2  # Retry email composition if validation fails

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """Validate that all required data is present"""

        if not pipeline_data.scraped_content:
            return "scraped_content is empty (WebScraper step must run first)"

        # For RESEARCH templates, papers are recommended but not required
        if pipeline_data.template_type == TemplateType.RESEARCH:
            if not pipeline_data.arxiv_papers:
                logfire.warning(
                    "No ArXiv papers found for RESEARCH template",
                    recipient=pipeline_data.recipient_name
                )
                # Not a fatal error - can compose email with web data only

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Compose email and write to database.

        This is the ONLY database write in the entire pipeline.

        Updates:
        - pipeline_data.final_email
        - pipeline_data.composition_metadata
        - pipeline_data.metadata["email_id"]
        - Writes to emails table in database

        Args:
            pipeline_data: Shared data object

        Returns:
            StepResult with email_id
        """

        # Attempt email composition (with retry)
        composed_email = None
        validation_attempts = 0

        for attempt in range(self.max_retries + 1):
            validation_attempts += 1

            # Compose email with Anthropic
            email_text = await self._compose_email_with_anthropic(pipeline_data)

            # Validate email quality
            validation = self._validate_email(
                email_text=email_text,
                recipient_name=pipeline_data.recipient_name,
                template_type=pipeline_data.template_type
            )

            if validation.is_valid:
                composed_email = email_text
                break
            else:
                logfire.warning(
                    "Email validation failed",
                    attempt=attempt + 1,
                    issues=validation.issues
                )

                # If last attempt, accept email despite issues
                if attempt == self.max_retries:
                    composed_email = email_text
                    logfire.warning(
                        "Accepting email despite validation issues (max retries reached)",
                        issues=validation.issues
                    )

        if not composed_email:
            raise ValidationError("Failed to compose valid email after retries")

        # Write to database (ONLY database write in pipeline!)
        email_id = await self._write_to_database(
            pipeline_data=pipeline_data,
            email_content=composed_email
        )

        # Update pipeline data with final results
        pipeline_data.final_email = composed_email
        pipeline_data.composition_metadata = {
            "validation_attempts": validation_attempts,
            "email_length": len(composed_email),
            "has_papers": len(pipeline_data.arxiv_papers) > 0
        }
        pipeline_data.metadata["email_id"] = email_id

        logfire.info(
            "Email composition completed and saved to database",
            email_id=email_id,
            email_length=len(composed_email),
            validation_attempts=validation_attempts
        )

        # Return success
        return StepResult(
            success=True,
            step_name=self.step_name,
            metadata={
                "email_id": email_id,
                "email_length": len(composed_email)
            }
        )

    async def _compose_email_with_anthropic(
        self,
        pipeline_data: PipelineData
    ) -> str:
        """
        Call Anthropic API to compose email.

        Args:
            pipeline_data: Shared data

        Returns:
            Composed email text

        Raises:
            ExternalAPIError: If Anthropic API fails
        """

        # Build prompt
        prompt = get_email_composition_prompt(
            email_template=pipeline_data.email_template,
            recipient_name=pipeline_data.recipient_name,
            recipient_interest=pipeline_data.recipient_interest,
            template_type=pipeline_data.template_type.value,
            scraped_content=pipeline_data.scraped_content or "",
            arxiv_papers=pipeline_data.arxiv_papers,
            template_analysis=pipeline_data.template_analysis or {}
        )

        try:
            # Call Anthropic with Logfire span
            with logfire.span("anthropic.email_composition"):
                response = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=2048,
                    temperature=0.7,  # Higher for more natural/creative output
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )

            # Extract email content
            email_text = response.content[0].text.strip()

            logfire.info(
                "Anthropic response received",
                response_length=len(email_text),
                model=response.model
            )

            return email_text

        except anthropic.APIError as e:
            logfire.error("Anthropic API error", error=str(e))
            raise ExternalAPIError(f"Anthropic API failed: {e}")

    def _validate_email(
        self,
        email_text: str,
        recipient_name: str,
        template_type: TemplateType
    ) -> EmailValidation:
        """
        Validate composed email quality.

        Args:
            email_text: Composed email
            recipient_name: Recipient's name
            template_type: Type of template

        Returns:
            EmailValidation with results
        """

        issues = []
        warnings = []

        # Check length
        length = len(email_text)
        if length < 100:
            issues.append("Email too short (< 100 chars)")
        elif length > 5000:
            issues.append("Email too long (> 5000 chars)")

        # Check for unfilled placeholders
        has_placeholders = "{{" in email_text or "}}" in email_text or "[" in email_text
        if has_placeholders:
            issues.append("Email contains unfilled placeholders")

        # Check recipient name mentioned
        last_name = recipient_name.split()[-1]
        if last_name.lower() not in email_text.lower():
            warnings.append("Recipient last name not found in email")

        # For RESEARCH templates, check for publication mention
        has_publication_mention = False
        if template_type == TemplateType.RESEARCH:
            # Look for quoted titles or common publication indicators
            if '"' in email_text or "paper" in email_text.lower() or "publication" in email_text.lower():
                has_publication_mention = True
            else:
                warnings.append("No clear publication mention found")

        # Check for common placeholder text that LLM might leave
        placeholder_patterns = [
            "your work",
            "your research",
            "[insert",
            "TODO",
            "PLACEHOLDER"
        ]
        for pattern in placeholder_patterns:
            if pattern.lower() in email_text.lower():
                warnings.append(f"Generic phrase detected: '{pattern}'")

        # Determine if valid
        is_valid = len(issues) == 0

        return EmailValidation(
            is_valid=is_valid,
            issues=issues,
            warnings=warnings,
            has_publication_mention=has_publication_mention,
            has_placeholders=has_placeholders,
            length=length
        )

    async def _write_to_database(
        self,
        pipeline_data: PipelineData,
        email_content: str
    ) -> str:
        """
        Write final email to database.

        This is the ONLY database write in the entire pipeline!

        Args:
            pipeline_data: Shared data with all context
            email_content: Final composed email

        Returns:
            email_id (UUID as string)
        """

        # Generate email ID
        email_id = uuid4()

        # Prepare metadata for JSONB column
        metadata = {
            "papers_used": [
                paper["title"]
                for paper in pipeline_data.arxiv_papers[:5]
            ] if pipeline_data.arxiv_papers else [],
            "sources": pipeline_data.scraped_urls[:10],
            "generation_time": pipeline_data.total_duration(),
            "step_timings": pipeline_data.step_timings,
            "template_tone": pipeline_data.template_analysis.get("tone") if pipeline_data.template_analysis else None,
            "validation_warnings": pipeline_data.errors
        }

        # Create database record
        with logfire.span("database.insert_email", email_id=str(email_id)):
            try:
                db = next(get_db())

                email_record = Email(
                    id=email_id,
                    user_id=pipeline_data.user_id,
                    recipient_name=pipeline_data.recipient_name,
                    recipient_interest=pipeline_data.recipient_interest,
                    email_message=email_content,
                    template_type=pipeline_data.template_type.value,
                    metadata=metadata
                )

                db.add(email_record)
                db.commit()
                db.refresh(email_record)

                logfire.info(
                    "Email saved to database",
                    email_id=str(email_id),
                    user_id=pipeline_data.user_id
                )

                return str(email_id)

            except Exception as e:
                db.rollback()
                logfire.error("Database write failed", error=str(e))
                raise
            finally:
                db.close()
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

- [ ] Set up Redis and Celery workers
- [ ] Add `template_type` and `metadata` columns to emails table
- [ ] Implement all 4 pipeline steps
- [ ] Create Celery tasks
- [ ] Update API endpoints
- [ ] Test with production API keys
- [ ] Run migration on staging
- [ ] Gradual rollout to production
- [ ] Monitor Logfire dashboards
- [ ] Deprecate legacy endpoints

---
