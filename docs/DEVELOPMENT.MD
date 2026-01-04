# Scribe Development Guide

> **Complete guide for developers: setup, workflows, testing, debugging, and best practices.**

---

## Overview

This guide covers everything developers need to work effectively with the Scribe codebase:

- **Development Setup**: Virtual environment, services, hot reload
- **Common Commands**: Makefile shortcuts, migrations, testing
- **Code Patterns**: FastAPI, Pydantic, async/await, pipeline steps
- **Testing**: Unit tests, integration tests, mocking strategies
- **Debugging**: Tools and techniques for troubleshooting

**Target Audience**: Backend developers contributing to Scribe

---

## Development Setup

### Prerequisites

- **Python**: 3.13+ (required for modern async features)
- **Redis**: For Celery task queue
- **PostgreSQL**: Via Supabase (managed)
- **Git**: For version control

### Initial Setup

```bash
# 1. Clone repository
cd /path/to/pythonserver

# 2. Create virtual environment
python3.13 -m venv venv

# 3. Activate virtual environment
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install Playwright browser (~300MB download)
playwright install chromium

# 6. Create .env file
cp .env.example .env
# Edit .env with your API keys and credentials
```

### Environment Variables

Create `.env` file in project root:

```bash
# Database (Supabase)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here

# AI APIs
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_CSE_ID=your_google_cse_id_here

# Celery & Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Optional: Logfire Observability
LOGFIRE_TOKEN=your_logfire_token_here
ENVIRONMENT=development
```

**Where to Get API Keys**:
- **Anthropic**: [console.anthropic.com](https://console.anthropic.com/)
- **Google Custom Search**: [developers.google.com/custom-search](https://developers.google.com/custom-search/v1/introduction)
- **Supabase**: Your project dashboard at [supabase.com](https://supabase.com)
- **Logfire** (optional): [logfire.pydantic.dev](https://logfire.pydantic.dev/)

### Verify Installation

```bash
# Check Python version
python --version  # Should be 3.13+

# Check Playwright installation
playwright --version

# Test imports
python -c "import anthropic, supabase, celery; print('All imports successful')"
```

---

## Running Services

### Quick Start (Recommended)

**Start everything with one command**:

```bash
# Terminal 1: Start Redis
make redis-start

# Terminal 2: Start FastAPI + Celery worker
make serve
```

This starts:
- **FastAPI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **Celery Worker**: Processing background tasks

### Manual Start (For Debugging)

**Run services separately for better control**:

```bash
# Terminal 1: Redis
make redis-start
# Or manually: redis-server --daemonize yes

# Terminal 2: FastAPI server (hot reload enabled)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Celery worker
make celery-worker
# Or manually: celery -A celery_config.celery_app worker --loglevel=info

# Terminal 4: Flower (monitoring UI)
make flower
# Visit: http://localhost:5555
```

### Hot Reload

**FastAPI Hot Reload** (auto-restart on file changes):
```bash
uvicorn main:app --reload
```

**Celery Hot Reload** (for development):
```bash
watchmedo auto-restart \
  --directory=./pipeline \
  --pattern='*.py' \
  --recursive \
  -- celery -A celery_config.celery_app worker --loglevel=info
```

### Stopping Services

```bash
# Stop all services
make stop-all

# Or manually:
pkill -f uvicorn
pkill -f celery
pkill -f flower
redis-cli shutdown
```

---

## Common Commands

### Makefile Shortcuts

The `Makefile` provides convenient shortcuts for common tasks:

```bash
# Development
make serve          # Start FastAPI + Celery worker together
make run            # Alias for serve
make celery-worker  # Start Celery worker only
make flower         # Start Flower monitoring UI (port 5555)
make stop-all       # Stop all running processes

# Redis
make redis-start    # Start Redis in background
make redis-stop     # Stop Redis
make redis-ping     # Check if Redis is running

# Database
make migration MSG="description"  # Create new migration
make migrate                       # Apply pending migrations
make db-current                    # Show current migration version
make db-history                    # Show migration history

# Testing
make test           # Run all tests
make test-unit      # Run only unit tests
make test-integration  # Run only integration tests
make test-coverage  # Run tests with coverage report

# Code Quality
make lint           # Run all linting checks (black, flake8, mypy)
make format         # Format code (black)
make type-check     # Run type checker (mypy)
```

### Database Migrations

**Alembic** manages database schema changes.

**Creating a Migration**:

```bash
# After modifying models in models/
make migration MSG="add new field to emails table"

# Or manually:
alembic revision --autogenerate -m "add new field to emails table"
```

**Applying Migrations**:

```bash
# Apply all pending migrations
make migrate

# Or manually:
alembic upgrade head
```

**Rolling Back**:

```bash
# Rollback one migration
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>
```

**Checking Status**:

```bash
# Current migration version
make db-current

# Migration history
make db-history

# Or manually:
alembic current
alembic history --verbose
```

### Testing Commands

**Using Makefile shortcuts** (runs pytest in venv automatically):

```bash
make test               # Run all tests
make test-unit          # Unit tests only
make test-integration   # Integration tests only
make test-coverage      # With HTML coverage report at htmlcov/index.html
```

**Using pytest directly** (recommended for development):

```bash
# IMPORTANT: Activate virtual environment first
source venv/bin/activate

# All tests
pytest

# Verbose output
pytest -v

# Specific test file
pytest pipeline/steps/template_parser/test_template_parser.py

# Specific test function
pytest pipeline/steps/template_parser/test_template_parser.py::test_extract_search_terms

# With markers
pytest -m unit              # Only unit tests
pytest -m integration       # Only integration tests
pytest -m "not slow"        # Skip slow tests

# With output capture disabled (see print statements)
pytest -s

# With coverage
pytest --cov=pipeline --cov=api --cov=models --cov=services --cov-report=html --cov-report=term
# View report: open htmlcov/index.html
```

**Critical Requirements**:
- ✅ Always run from project root (`/pythonserver`), never from subdirectories
- ✅ Activate virtual environment first: `source venv/bin/activate`
- ✅ Use venv's pytest: `which pytest` should show `/path/to/pythonserver/venv/bin/pytest`

---

## Code Patterns

### FastAPI Route Patterns

**Protected Route with Authentication**:

```python
from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_current_user
from models.user import User
from schemas.email import GenerateEmailRequest, GenerateEmailResponse

router = APIRouter(prefix="/api/email", tags=["Email Generation"])

@router.post("/generate")
async def generate_email(
    request: GenerateEmailRequest,
    current_user: User = Depends(get_current_user)
) -> GenerateEmailResponse:
    """
    Generate personalized email.

    Requires authentication - JWT token in Authorization header.
    """
    # Validate request (automatic via Pydantic)
    # current_user is validated and from database

    # Business logic here
    task = generate_email_task.apply_async(
        kwargs={
            "user_id": str(current_user.id),
            "email_template": request.email_template,
            "recipient_name": request.recipient_name,
            "recipient_interest": request.recipient_interest
        }
    )

    return GenerateEmailResponse(task_id=task.id)
```

**Error Handling**:

```python
from fastapi import HTTPException, status

@router.get("/email/{email_id}")
async def get_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch email by ID."""

    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == current_user.id  # Ensure user owns email
    ).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email {email_id} not found"
        )

    return EmailResponse.model_validate(email)
```

### Pydantic Validation Patterns

**Request Schema with Validation**:

```python
from pydantic import BaseModel, Field, validator

class GenerateEmailRequest(BaseModel):
    """Validated request body."""

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

    @validator('email_template')
    def template_must_have_placeholders(cls, v):
        """Custom validation: template must contain placeholders."""
        if '{{' not in v or '}}' not in v:
            raise ValueError('Template must contain placeholders like {{name}}')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "email_template": "Hey {{name}}, love {{research}}!",
                "recipient_name": "Dr. Jane Smith",
                "recipient_interest": "machine learning"
            }
        }
```

### Async/Await Patterns

**Async Database Query**:

```python
from sqlalchemy.ext.asyncio import AsyncSession

async def get_user_emails(
    user_id: str,
    db: AsyncSession
) -> List[Email]:
    """Fetch user's emails asynchronously."""

    result = await db.execute(
        select(Email)
        .where(Email.user_id == user_id)
        .order_by(Email.created_at.desc())
        .limit(50)
    )

    return result.scalars().all()
```

**Async External API Call**:

```python
import httpx

async def fetch_arxiv_papers(author_name: str) -> List[Dict]:
    """Fetch papers from ArXiv API."""

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": f"au:{author_name}", "max_results": 20},
            timeout=10.0
        )

        response.raise_for_status()
        return parse_arxiv_response(response.text)
```

### BasePipelineStep Implementation

**Creating a New Pipeline Step**:

```python
from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
from typing import Optional
import logfire

class MyCustomStep(BasePipelineStep):
    """Custom pipeline step."""

    def __init__(self):
        super().__init__(step_name="my_custom_step")

    async def _validate_input(self, data: PipelineData) -> Optional[str]:
        """Validate prerequisites."""
        if not data.search_terms:
            return "search_terms is empty"
        return None

    async def _execute_step(self, data: PipelineData) -> StepResult:
        """Execute step logic."""

        try:
            # Your logic here
            result = await self._do_work(data)

            # Update PipelineData
            data.my_output = result

            # Log success
            logfire.info(
                "Custom step completed",
                task_id=data.task_id,
                output_size=len(result)
            )

            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={"result_length": len(result)}
            )

        except Exception as e:
            # Log error (BasePipelineStep will handle)
            logfire.error("Custom step failed", error=str(e))
            raise

    async def _do_work(self, data: PipelineData) -> str:
        """Helper method for business logic."""
        # Implementation here
        return "result"
```

**Registering the Step**:

```python
# pipeline/__init__.py

def create_email_pipeline() -> PipelineRunner:
    """Factory function to create configured pipeline."""

    runner = PipelineRunner()

    # Register steps in order
    runner.register_step(TemplateParserStep())
    runner.register_step(WebScraperStep())
    runner.register_step(ArxivEnricherStep())
    runner.register_step(MyCustomStep())  # Your new step
    runner.register_step(EmailComposerStep())

    return runner
```

### Logfire Spans and Events

**Creating Spans**:

```python
import logfire

def process_data(data):
    with logfire.span("process_data", data_size=len(data)):
        # Operations inside span are automatically timed
        result = expensive_operation(data)

        # Log events within span
        logfire.info("Processing complete", result_count=len(result))

        return result
```

**Nested Spans**:

```python
async def full_workflow(input_data):
    with logfire.span("full_workflow"):

        with logfire.span("step_1"):
            result_1 = await step_1(input_data)

        with logfire.span("step_2"):
            result_2 = await step_2(result_1)

        return result_2
```

**Logging with Context**:

```python
logfire.info("Task started", task_id=task_id, user_id=user_id)
logfire.warning("Partial failure", failed_urls=urls, error_count=len(errors))
logfire.error("Task failed", task_id=task_id, error=str(e), exc_info=True)
```

---

## Testing

### Test Organization

```
pipeline/
├── steps/
│   ├── template_parser/
│   │   ├── main.py
│   │   ├── test_template_parser.py        # Unit tests
│   │   └── conftest.py                    # Fixtures for this module
│   ├── web_scraper/
│   │   ├── main.py
│   │   ├── utils.py
│   │   ├── test_web_scraper.py
│   │   ├── test_utils.py
│   │   └── conftest.py
│   └── ...
└── core/
    ├── runner.py
    └── test_runner.py
```

### pytest Configuration

**File**: `pytest.ini`

```ini
[pytest]
python_files = test_*.py
python_classes = Test*
python_functions = test_*
testpaths = pipeline api
asyncio_mode = auto

markers =
    unit: Fast unit tests
    integration: Tests with external dependencies
    slow: Slow-running tests
```

### Writing Unit Tests

**Testing a Pipeline Step**:

```python
import pytest
from pipeline.steps.template_parser.main import TemplateParserStep
from pipeline.models.core import PipelineData, TemplateType

@pytest.mark.unit
@pytest.mark.asyncio
async def test_template_parser_extracts_search_terms():
    """Test that template parser extracts search terms."""

    step = TemplateParserStep()
    data = PipelineData(
        task_id="test-123",
        user_id="user-456",
        email_template="Hey {{name}}, I love {{research}}!",
        recipient_name="Dr. Jane Smith",
        recipient_interest="machine learning"
    )

    result = await step._execute_step(data)

    # Assertions
    assert result.success
    assert len(data.search_terms) > 0
    assert data.template_type in [
        TemplateType.RESEARCH,
        TemplateType.BOOK,
        TemplateType.GENERAL
    ]
    assert "Jane Smith" in str(data.search_terms)
```

### Writing Integration Tests

**Testing Full Pipeline**:

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_execution(db_session):
    """Test complete pipeline from start to finish."""

    runner = PipelineRunner()
    runner.register_step(TemplateParserStep())
    runner.register_step(WebScraperStep())
    runner.register_step(ArxivEnricherStep())
    runner.register_step(EmailComposerStep())

    data = PipelineData(
        task_id="integration-test",
        user_id="user-123",
        email_template="Hey {{name}}, love your work on {{research}}",
        recipient_name="Yann LeCun",
        recipient_interest="deep learning"
    )

    await runner.run(data)

    # Verify final state
    assert data.final_email != ""
    assert data.metadata["email_id"] is not None
    assert len(data.step_timings) == 4
```

### Mocking External APIs

**Mock Anthropic API**:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_anthropic():
    """Mock Anthropic API responses."""
    with patch('anthropic.AsyncAnthropic') as mock:
        # Mock successful response
        mock.return_value.messages.create = AsyncMock(
            return_value=MockMessage(
                content=[MockContent(text="Mocked response")]
            )
        )
        yield mock

@pytest.mark.asyncio
async def test_with_mocked_anthropic(mock_anthropic):
    """Test runs without real API calls."""

    step = TemplateParserStep()
    data = PipelineData(...)

    result = await step._execute_step(data)

    # Verify mock was called
    assert mock_anthropic.return_value.messages.create.called
    assert result.success
```

**Mock HTTP Requests**:

```python
@pytest.fixture
def mock_httpx():
    """Mock httpx requests."""
    with patch('httpx.AsyncClient') as mock:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Mocked content</html>"

        mock.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        yield mock
```

### Test Fixtures

**Common Fixtures** (`conftest.py`):

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from pipeline.models.core import PipelineData

@pytest.fixture
def sample_pipeline_data():
    """Create sample PipelineData for testing."""
    return PipelineData(
        task_id="test-task-id",
        user_id="test-user-id",
        email_template="Test template {{name}}",
        recipient_name="Test Recipient",
        recipient_interest="test interest"
    )

@pytest.fixture
async def db_session():
    """Create test database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async with AsyncSession(engine) as session:
        yield session

    await engine.dispose()
```

### Common Testing Pitfalls

❌ **Running tests with system Python**:
```bash
# This will fail if pytest not installed globally
pytest
```

✅ **Always use virtual environment**:
```bash
source venv/bin/activate
pytest
```

❌ **Running from wrong directory**:
```bash
cd pipeline/steps/template_parser
pytest test_template_parser.py  # May cause import errors
```

✅ **Always run from project root**:
```bash
# From /Users/manitmishra/Desktop/pythonserver
pytest pipeline/steps/template_parser/test_template_parser.py
```

❌ **Missing `__init__.py` files**:
- Every package directory must have `__init__.py`
- Check `pipeline/`, `pipeline/steps/`, and all subdirectories

✅ **Proper package structure**:
```
pipeline/
├── __init__.py          # Required
├── steps/
│   ├── __init__.py      # Required
│   └── template_parser/
│       └── __init__.py  # Required
```

---

## Debugging

### FastAPI Debugging

**Using Python Debugger (pdb)**:

```python
# Add breakpoint in your code
import pdb; pdb.set_trace()

# Or use built-in breakpoint() (Python 3.7+)
breakpoint()
```

**VS Code Debug Configuration** (`.vscode/launch.json`):

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
      "jinja": true
    }
  ]
}
```

**Logging**:

```python
import logging

logger = logging.getLogger(__name__)

@router.post("/generate")
async def generate_email(request: GenerateEmailRequest):
    logger.info(f"Received request: {request.model_dump()}")

    try:
        # Process request
        result = await process(request)
        logger.info(f"Request processed successfully: {result}")
        return result
    except Exception as e:
        logger.error(f"Request failed: {str(e)}", exc_info=True)
        raise
```

### Celery Task Debugging

**Using Flower UI**:

```bash
# Start Flower
make flower

# Visit http://localhost:5555
# View: Active tasks, completed tasks, worker stats, task history
```

**Inspecting Task State**:

```python
from celery.result import AsyncResult
from celery_config import celery_app

# Get task by ID
task = AsyncResult('task-id-here', app=celery_app)

# Check state
print(task.state)  # PENDING, STARTED, SUCCESS, FAILURE

# Get result (if SUCCESS)
if task.successful():
    print(task.result)

# Get error (if FAILURE)
if task.failed():
    print(task.info)  # Exception info
```

**Celery Worker Logs**:

```bash
# Run worker with debug logging
celery -A celery_config.celery_app worker --loglevel=debug

# Or check specific queue
celery -A celery_config.celery_app inspect active_queues
```

### Pipeline Step Debugging

**Logfire Traces**:

1. Visit [logfire.pydantic.dev](https://logfire.pydantic.dev)
2. Find your task by `task_id`
3. View nested spans for each pipeline step
4. Check timing, errors, and custom metadata

**Local Span Inspection**:

```python
import logfire

with logfire.span("debug_span") as span:
    result = some_operation()

    # Add custom attributes
    span.set_attribute("result_size", len(result))
    span.set_attribute("custom_field", "value")

    # Log events
    logfire.info("Operation completed", result=result)
```

### Database Query Debugging

**SQLAlchemy Query Logging**:

```python
import logging

# Enable SQL query logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Now all queries will be printed
```

**Inspecting Query Results**:

```python
from sqlalchemy import select

result = await db.execute(
    select(Email).where(Email.user_id == user_id)
)

# Debug: print SQL query
print(str(result.statement.compile()))

# Debug: check row count
rows = result.scalars().all()
print(f"Found {len(rows)} rows")
```

### Common Error Messages

**Error**: `redis.exceptions.ConnectionError: Error connecting to Redis`

**Solution**:
```bash
# Check if Redis is running
redis-cli ping  # Should respond "PONG"

# If not running:
make redis-start
```

---

**Error**: `playwright._impl._api_types.Error: Executable doesn't exist`

**Solution**:
```bash
# Install Playwright browsers
playwright install chromium
```

---

**Error**: `ModuleNotFoundError: No module named 'pipeline'`

**Solution**:
```bash
# Ensure running from project root
cd /path/to/pythonserver

# Ensure virtual environment is activated
source venv/bin/activate

# Check PYTHONPATH
echo $PYTHONPATH  # Should include current directory
```

---

**Error**: `Task stays in PENDING status forever`

**Solution**:
```bash
# Check if Celery worker is running
celery -A celery_config.celery_app inspect active

# If no workers, start one:
make celery-worker
```

---

**Error**: `sqlalchemy.exc.OperationalError: connection pool exhausted`

**Solution**:
- Reduce `pool_size` in `database/base.py`
- Close database sessions properly (`await session.close()`)
- Upgrade Supabase plan for more connections

---

## Best Practices

### Code Style

- **Imports**: Use absolute imports (`from pipeline.models.core import PipelineData`)
- **Type Hints**: Always annotate function signatures
- **Docstrings**: Use for public methods and classes
- **Line Length**: Max 100 characters
- **Formatting**: Use `black` for consistent formatting

### Async Best Practices

- **Use `async/await`**: For I/O-bound operations (API calls, database queries)
- **Don't block**: Avoid `time.sleep()` in async functions (use `asyncio.sleep()`)
- **Gather parallel tasks**: Use `asyncio.gather()` for concurrent operations

```python
# ✅ Good: Parallel execution
results = await asyncio.gather(
    fetch_user(user_id),
    fetch_emails(user_id),
    fetch_stats(user_id)
)

# ❌ Bad: Sequential execution
user = await fetch_user(user_id)
emails = await fetch_emails(user_id)
stats = await fetch_stats(user_id)
```

### Error Handling

- **Be specific**: Catch specific exceptions, not bare `except:`
- **Log errors**: Use Logfire with full context
- **Return structured errors**: Use FastAPI's `HTTPException` with proper status codes

### Testing Best Practices

- **Write tests first**: TDD when possible
- **Mock external APIs**: Don't hit real APIs in unit tests
- **Use fixtures**: Share setup code with pytest fixtures
- **Test edge cases**: Empty inputs, invalid data, API failures

---

## Further Reading

- **Quick Start**: [QUICKSTART.MD](QUICKSTART.MD) - Get running in 5 minutes
- **Architecture**: [ARCHITECTURE.MD](ARCHITECTURE.MD) - System design and deployment
- **Pipeline**: [PIPELINE.MD](PIPELINE.MD) - 4-step pipeline deep dive
- **API Reference**: [API_REFERENCE.MD](API_REFERENCE.MD) - API documentation

---

*Last updated: 2025-01-24*
