# Scribe Development Guide

> **Developer guide: setup, commands, testing, debugging, and best practices.**

---

## Development Setup

### Prerequisites
- **Python 3.13+** (required for async features)
- **Redis** (for Celery)
- **PostgreSQL** via Supabase (managed)

### Initial Setup

```bash
# 1. Clone and navigate to repo
cd /path/to/pythonserver

# 2. Create virtual environment
python3.13 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browser (~300MB)
playwright install chromium

# 5. Create .env file
cp .env.example .env
# Edit .env with your API keys
```

### Environment Variables

Create `.env` in project root:

```bash
# Database (Supabase)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# AI APIs
ANTHROPIC_API_KEY=your_key
FIREWORKS_API_KEY=your_key
EXA_API_KEY=your_key

# Celery & Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# LLM Models (hot-swappable)
TEMPLATE_PARSER_MODEL=fireworks:deepseek-v3.2
EMAIL_COMPOSER_MODEL=fireworks:deepseek-v3.2

# Optional: Logfire
LOGFIRE_TOKEN=your_token
ENVIRONMENT=development
```

**Get API Keys**:
- Anthropic: [console.anthropic.com](https://console.anthropic.com/)
- Fireworks: [fireworks.ai](https://fireworks.ai/)
- Exa: [exa.ai](https://exa.ai/)
- Supabase: Your project dashboard
- Logfire: [logfire.pydantic.dev](https://logfire.pydantic.dev/)

### Verify Installation

```bash
python --version  # Should be 3.13+
playwright --version
python -c "import anthropic, supabase, celery; print('All imports successful')"
```

---

## Running Services

### Quick Start

```bash
# Terminal 1: Redis
make redis-start

# Terminal 2: API + Worker
make serve
```

**URLs**:
- FastAPI: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Flower (monitoring): http://localhost:5555 (run `make flower`)

### Manual Start (For Debugging)

```bash
# Terminal 1: Redis
make redis-start

# Terminal 2: FastAPI (hot reload)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Celery worker
make celery-worker

# Terminal 4: Flower (monitoring)
make flower
```

### Stopping Services

```bash
make stop-all

# Or manually:
pkill -f uvicorn
pkill -f celery
redis-cli shutdown
```

---

## Common Commands

### Makefile Shortcuts

```bash
# Development
make serve          # Start API + Celery together
make celery-worker  # Start worker only
make flower         # Start Flower UI (port 5555)
make stop-all       # Stop all processes

# Redis
make redis-start    # Start Redis
make redis-stop     # Stop Redis
make redis-ping     # Check status

# Database
make migration MSG="description"  # Create migration
make migrate                       # Apply migrations
make db-current                    # Show version
make db-history                    # Show history

# Testing
make test           # All tests
make test-unit      # Unit tests only
make test-integration  # Integration tests
make test-coverage  # With coverage report

# Code Quality
make lint           # All linting (black, flake8, mypy)
make format         # Format code (black)
make type-check     # Type checking (mypy)
```

### Database Migrations

**Creating Migrations**:
```bash
# After modifying models/
make migration MSG="add new field to emails table"

# Or manually:
alembic revision --autogenerate -m "description"
```

**Applying Migrations**:
```bash
make migrate

# Or manually:
alembic upgrade head
```

**Rollback**:
```bash
alembic downgrade -1              # Rollback one
alembic downgrade <revision_id>   # Rollback to specific version
```

**Status**:
```bash
make db-current    # Current version
make db-history    # History
```

### Testing Commands

**Using Makefile**:
```bash
make test               # All tests
make test-unit          # Unit only
make test-integration   # Integration only
make test-coverage      # With HTML report (htmlcov/index.html)
```

**Using pytest directly** (recommended for dev):
```bash
# CRITICAL: Activate venv first!
source venv/bin/activate

# All tests
pytest

# Specific file
pytest pipeline/steps/template_parser/test_template_parser.py

# Specific function
pytest path/to/test.py::test_function_name

# With markers
pytest -m unit              # Unit tests only
pytest -m integration       # Integration only
pytest -m "not slow"        # Skip slow tests

# Verbose + output
pytest -v -s

# With coverage
pytest --cov=pipeline --cov=api --cov-report=html --cov-report=term
```

**Requirements**:
- ✅ Always run from project root (`/pythonserver`)
- ✅ Activate venv: `source venv/bin/activate`
- ✅ Verify pytest path: `which pytest` → should be in `venv/bin/pytest`

---

## Code Patterns

### FastAPI Route Pattern

```python
from fastapi import APIRouter, Depends, HTTPException, status
from api.dependencies import get_current_user
from models.user import User
from schemas.email import GenerateEmailRequest, GenerateEmailResponse

router = APIRouter(prefix="/api/email", tags=["Email"])

@router.post("/generate")
async def generate_email(
    request: GenerateEmailRequest,
    current_user: User = Depends(get_current_user)
) -> GenerateEmailResponse:
    """Generate email (requires auth)."""

    # Validation automatic via Pydantic
    # current_user validated from JWT

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

### Pydantic Validation

```python
from pydantic import BaseModel, Field, validator

class GenerateEmailRequest(BaseModel):
    email_template: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Template with placeholders"
    )

    recipient_name: str = Field(..., min_length=2, max_length=255)

    @validator('email_template')
    def must_have_placeholders(cls, v):
        if '{{' not in v or '}}' not in v:
            raise ValueError('Must contain placeholders like {{name}}')
        return v
```

### Pipeline Step Implementation

```python
from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
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
            result = await self._do_work(data)
            data.my_output = result

            logfire.info("Custom step completed", task_id=data.task_id)

            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={"result_length": len(result)}
            )
        except Exception as e:
            logfire.error("Custom step failed", error=str(e))
            raise

    async def _do_work(self, data: PipelineData) -> str:
        """Business logic."""
        return "result"
```

**Register in pipeline** (`pipeline/__init__.py`):
```python
def create_email_pipeline() -> PipelineRunner:
    runner = PipelineRunner()
    runner.register_step(TemplateParserStep())
    runner.register_step(WebScraperStep())
    runner.register_step(MyCustomStep())  # Add here
    runner.register_step(EmailComposerStep())
    return runner
```

---

## Testing

### Test Organization

```
pipeline/steps/template_parser/
├── main.py
├── test_template_parser.py
└── conftest.py  # Module-specific fixtures
```

### pytest Configuration

**File**: `pytest.ini`
```ini
[pytest]
python_files = test_*.py
python_functions = test_*
testpaths = pipeline api
asyncio_mode = auto

markers =
    unit: Fast unit tests
    integration: External dependencies
    slow: Slow-running tests
```

### Writing Tests

**Unit Test Example**:
```python
import pytest
from pipeline.steps.template_parser.main import TemplateParserStep
from pipeline.models.core import PipelineData

@pytest.mark.unit
@pytest.mark.asyncio
async def test_template_parser():
    """Test template parser extracts search terms."""

    step = TemplateParserStep()
    data = PipelineData(
        task_id="test-123",
        user_id="user-456",
        email_template="Hey {{name}}, love {{research}}!",
        recipient_name="Dr. Jane Smith",
        recipient_interest="machine learning"
    )

    result = await step._execute_step(data)

    assert result.success
    assert len(data.search_terms) > 0
    assert "Jane Smith" in str(data.search_terms)
```

**Integration Test Example**:
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline(db_session):
    """Test complete pipeline."""

    runner = PipelineRunner()
    runner.register_step(TemplateParserStep())
    runner.register_step(WebScraperStep())
    runner.register_step(EmailComposerStep())

    data = PipelineData(...)
    await runner.run(data)

    assert data.final_email != ""
    assert data.metadata["email_id"] is not None
```

### Common Testing Pitfalls

❌ **Running with system Python**:
```bash
pytest  # May fail if not in venv
```

✅ **Always use venv**:
```bash
source venv/bin/activate
pytest
```

❌ **Running from wrong directory**:
```bash
cd pipeline/steps/template_parser
pytest test_template_parser.py  # Import errors
```

✅ **Always from project root**:
```bash
# From /pythonserver
pytest pipeline/steps/template_parser/test_template_parser.py
```

❌ **Missing `__init__.py` files**:
```
pipeline/
├── steps/
│   └── template_parser/
│       ├── main.py
│       └── test_template_parser.py  # No __init__.py!
```

✅ **Proper package structure**:
```
pipeline/
├── __init__.py          # Required
├── steps/
│   ├── __init__.py      # Required
│   └── template_parser/
│       ├── __init__.py  # Required
│       ├── main.py
│       └── test_template_parser.py
```

---

## Debugging

### FastAPI Debugging

**Python Debugger**:
```python
# Add breakpoint
breakpoint()  # Python 3.7+

# Or use pdb
import pdb; pdb.set_trace()
```

**Logging**:
```python
import logging

logger = logging.getLogger(__name__)

@router.post("/generate")
async def generate_email(request: GenerateEmailRequest):
    logger.info(f"Received: {request.model_dump()}")

    try:
        result = await process(request)
        logger.info(f"Success: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed: {str(e)}", exc_info=True)
        raise
```

### Celery Task Debugging

**Flower UI**:
```bash
make flower
# Visit http://localhost:5555
# View: Active tasks, worker stats, history
```

**Inspect Task State**:
```python
from celery.result import AsyncResult
from celery_config import celery_app

task = AsyncResult('task-id', app=celery_app)
print(task.state)  # PENDING, STARTED, SUCCESS, FAILURE

if task.successful():
    print(task.result)

if task.failed():
    print(task.info)  # Exception details
```

**Worker Logs**:
```bash
# Debug logging
celery -A celery_config.celery_app worker --loglevel=debug --queues=email_default --concurrency=1

# Inspect queues
celery -A celery_config.celery_app inspect active_queues
```

### Pipeline Debugging

**Logfire Traces**:
1. Visit [logfire.pydantic.dev](https://logfire.pydantic.dev)
2. Find task by `task_id`
3. View nested spans for each step
4. Check timing, errors, metadata

**Custom Spans**:
```python
import logfire

with logfire.span("debug_operation", task_id=task_id):
    result = some_operation()
    logfire.info("Operation completed", result=result)
```

### Database Debugging

**Enable SQL Logging**:
```python
import logging

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
# All queries now printed
```

**Inspect Queries**:
```python
from sqlalchemy import select

result = await db.execute(
    select(Email).where(Email.user_id == user_id)
)

# Print SQL
print(str(result.statement.compile()))

# Check results
rows = result.scalars().all()
print(f"Found {len(rows)} rows")
```

### Common Errors

**`redis.exceptions.ConnectionError`**
```bash
# Check Redis
redis-cli ping  # Should respond "PONG"

# Start if not running
make redis-start
```

**`playwright._impl._api_types.Error: Executable doesn't exist`**
```bash
playwright install chromium
```

**`ModuleNotFoundError: No module named 'pipeline'`**
```bash
# Run from project root
cd /pythonserver

# Activate venv
source venv/bin/activate
```

**Task stuck in PENDING**
```bash
# Check if worker running
celery -A celery_config.celery_app inspect active

# Start worker
make celery-worker
```

---

## Best Practices

### Code Style
- **Imports**: Absolute imports (`from pipeline.models.core import PipelineData`)
- **Type Hints**: Always annotate function signatures
- **Docstrings**: For public methods and classes
- **Line Length**: Max 100 chars
- **Formatting**: Use `black`

### Async Guidelines
- **Use `async/await`** for I/O operations
- **Don't block**: Avoid `time.sleep()` (use `asyncio.sleep()`)
- **Parallel execution**: Use `asyncio.gather()` for concurrent tasks

```python
# ✅ Good: Parallel
results = await asyncio.gather(
    fetch_user(user_id),
    fetch_emails(user_id),
    fetch_stats(user_id)
)

# ❌ Bad: Sequential
user = await fetch_user(user_id)
emails = await fetch_emails(user_id)
stats = await fetch_stats(user_id)
```

### Error Handling
- Catch specific exceptions, not bare `except:`
- Log errors with Logfire
- Return structured errors via `HTTPException`

### Testing
- Write tests first (TDD)
- Mock external APIs in unit tests
- Use fixtures for shared setup
- Test edge cases

---

## Common Workflows

### Adding New Authenticated Endpoint

1. Create Pydantic schemas in `schemas/`
2. Create route in `api/routes/` with `get_current_user` dependency
3. Test with valid JWT token
4. Update docs if commonly used

### Modifying Database Schema

1. Edit model in `models/`
2. Generate migration: `make migration MSG="description"`
3. Review migration file in `alembic/versions/`
4. Apply: `make migrate`
5. Update Pydantic schemas in `schemas/`

### Writing and Running Tests

1. **Create test file** in same directory as code:
   ```bash
   # For pipeline/steps/my_step/main.py
   # Create: pipeline/steps/my_step/test_my_step.py
   ```

2. **Ensure `__init__.py` exists** in all package dirs

3. **Write test**:
   ```python
   import pytest
   from pipeline.steps.my_step.main import MyStep

   @pytest.mark.unit
   @pytest.mark.asyncio
   async def test_my_step():
       step = MyStep()
       result = await step.execute(...)
       assert result.success
   ```

4. **Run from project root**:
   ```bash
   source venv/bin/activate
   pytest pipeline/steps/my_step/test_my_step.py -v
   ```

---

## Further Reading

- **Quick Start**: [QUICKSTART.MD](QUICKSTART.MD) - Setup in 5 minutes
- **Architecture**: [ARCHITECTURE.MD](ARCHITECTURE.MD) - System design
- **Pipeline**: [PIPELINE.MD](PIPELINE.MD) - 4-step implementation
- **API Reference**: [API_REFERENCE.MD](API_REFERENCE.MD) - Complete API docs

---

*Last updated: 2025-01-24*
