# Scribe Backend Architecture

> **Quick Start**: Async email generation platform using a 4-step AI pipeline. FastAPI handles requests, Celery workers run the pipeline, results stored in PostgreSQL.

## System Overview

```
Client (Next.js SPA)
     ↓  HTTPS + JWT auth
FastAPI API (request validation, task dispatch)
     ↓  Celery task enqueue
Celery + Redis (distributed queue)
     ↓  Pipeline execution (4 steps)
Pipeline → PostgreSQL (Supabase-managed)
```

**Tech Stack**:
- **Backend**: FastAPI (Python 3.13), SQLAlchemy, Alembic
- **Task Queue**: Celery 5.3+ with Redis (broker + results)
- **Database**: PostgreSQL via Supabase (direct connection, not SDK)
- **AI**: Anthropic Claude (Sonnet 4.5 for composition, Haiku 4.5 for analysis)
- **Web Scraping**: Playwright (headless Chrome), Google Custom Search API
- **Auth**: Supabase Auth (JWT validation only, all DB ops via backend)
- **Observability**: Logfire (distributed tracing, LLM call monitoring)

---

## Request Flow

### Email Generation Lifecycle

1. **Client Request**  `POST /api/email/generate` with JWT token
2. **API Validates**  JWT  extracts user_id  creates Celery task  returns `task_id`
3. **Celery Queues**  Task written to Redis (db 0)
4. **Worker Picks Up**  Executes 4-step pipeline asynchronously
5. **Pipeline Runs**  Template analysis  web scraping  paper enrichment  email composition
6. **Database Write**  Final email saved to PostgreSQL
7. **Client Polls**  `GET /api/email/status/{task_id}`  returns PENDING/RUNNING/SUCCESS/FAILURE
8. **Client Retrieves**  `GET /api/email/{email_id}`  returns generated email

**Key Point**: Tasks take 10-25 seconds, so async processing prevents HTTP timeouts.

### Authentication Flow

```
Frontend  Supabase Auth (login)  JWT token
         
Backend  Validate JWT (get_supabase_user)  Extract user_id
         Lookup in local DB (get_current_user)  Proceed
```

**Security Model**:
- Frontend uses Supabase **only** for auth (OAuth, JWT)
- Backend uses Supabase **service role key** for full DB access
- **Never trust** `user_id` from request body—always extract from the validated JWT

---

## The Pipeline (4 Sequential Steps)

Each step enriches a shared `PipelineData` object passed through the chain. Data lives **in-memory only**—the final email is the only artifact persisted to the database.

### Step 1: Template Parser (`pipeline/steps/template_parser/`)
**What**: Analyzes email template using Claude Haiku 4.5
**Input**: Template text, recipient name, research interest
**Output**: `search_terms` (list), `template_type` (RESEARCH/BOOK/GENERAL)
**Example**: `"{{name}}'s work on {{research}}"`  `["Jane Smith machine learning", "Jane Smith publications"]`

### Step 2: Web Scraper (`pipeline/steps/web_scraper/`)
**What**: Fetches and summarizes web content
**Process**: Google Search (3 results/query)  Playwright scraping  LLM summarization
**Output**: `scraped_content` (max 3000 chars), `scraped_urls`
**Memory Constraint**: Sequential scraping (1 browser at a time due to 512MB RAM limit)

### Step 3: ArXiv Helper (`pipeline/steps/arxiv_helper/`)
**What**: Conditionally fetches academic papers (only if `template_type == RESEARCH`)
**Process**: Search ArXiv by author name → fetch top 5 papers
**Output**: `arxiv_papers` (list of {title, abstract, year, url})
**Note**: Skips entirely for BOOK/GENERAL templates

### Step 4: Email Composer (`pipeline/steps/email_composer/`)
**What**: Generates final email + writes to database
**Process**: Combines all data  Claude Sonnet 4.5 (creative writing)  DB insert
**Output**: `final_email`, `email_id` (UUID from database)
**Database Ops**:
- Insert into `emails` table
- Increment `user.generation_count`
- Store metadata (papers, sources, timings) in JSONB column

**Pipeline Data Flow**:
```
Input  [Step 1: +search_terms]  [Step 2: +scraped_content]
       [Step 3: +papers]  [Step 4: +final_email, email_id]  Database
```

---

## Celery + Redis Architecture

### Why Celery?
- Email generation takes 10-25 seconds (too long for HTTP request)
- Allows client to poll status asynchronously
- Horizontal scaling: multiple workers can process tasks in parallel

### Redis Configuration
- **DB 0**: Celery broker (task queue)
- **DB 1**: Celery result backend (task state + results)
- **Task Expiration**: Results deleted after 1 hour

### Worker Configuration
```python
# Memory-constrained for Render 512MB deployment
worker_concurrency = 1          # Only 1 task at a time
worker_prefetch_multiplier = 1  # Don't prefetch tasks
task_acks_late = True           # Requeue on worker crash
```

### Task States
- **PENDING**: Queued in Redis, waiting for worker
- **STARTED**: Worker picked up task, includes `current_step` in metadata
- **SUCCESS**: Pipeline completed, includes `email_id`
- **FAILURE**: Error occurred, includes `error` and `failed_step`

### Monitoring
```bash
make flower  # Flower UI at localhost:5555
```

---

## Directory Structure

| Directory | Purpose |
|-----------|---------|
| `api/` | FastAPI routes (`user.py`, `email.py`) and auth dependencies |
| `models/` | SQLAlchemy ORM models (`User`, `Email`) |
| `schemas/` | Pydantic request/response validation schemas |
| `database/` | DB engine, session management, connection utilities |
| `pipeline/` | 4-step email generation pipeline |
| `pipeline/core/` | `PipelineRunner`, `BasePipelineStep` base classes |
| `pipeline/steps/` | Individual step implementations (template_parser, web_scraper, etc.) |
| `tasks/` | Celery task definitions (`generate_email_task`) |
| `config/` | Pydantic Settings (env vars, Redis config) |
| `services/` | External service clients (Supabase) |
| `alembic/` | Database migrations |
| `observability/` | Logfire configuration for distributed tracing |
| `utils/` | Shared utilities (LLM agent factory) |

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app entry point, router registration, startup checks |
| `celery_config.py` | Celery app config, worker settings, Redis connection |
| `tasks/email_tasks.py` | `generate_email_task` - orchestrates pipeline execution |
| `pipeline/__init__.py` | `create_email_pipeline()` factory - registers 4 steps |
| `pipeline/core/runner.py` | `PipelineRunner` - executes steps sequentially with observability |
| `database/base.py` | SQLAlchemy engine, session factory, connection pooling |
| `config/settings.py` | Environment variable validation (Pydantic Settings) |
| `api/dependencies.py` | `get_current_user()` - JWT validation + user lookup |

---

## Database Schema

### Users Table
```python
id              UUID (PK, from Supabase auth.users)
email           String (unique, indexed)
display_name    String (optional)
generation_count Integer (tracks usage)
created_at      DateTime
```

### Emails Table
```python
id                UUID (PK, auto-generated)
user_id           UUID (FK  users, CASCADE delete)
recipient_name    String
recipient_interest String
email_message     Text (generated content)
template_type     Enum (RESEARCH | BOOK | GENERAL)
metadata          JSONB (papers, sources, timings, model info)
created_at        DateTime (indexed)
```

**Indexes**:
- `users.email` (unique)
- `emails.user_id` + `emails.created_at` (composite for user history queries)

---

## Common Tasks

### Run Locally
```bash
# 1. Start Redis
make redis-start

# 2. Start API + Celery worker (both in one command)
make serve

# Or separately:
uvicorn main:app --reload          # API only
celery -A celery_config.celery_app worker --loglevel=info  # Worker only
```

### Add a New Pipeline Step
1. **Create step class** in `pipeline/steps/my_step/main.py`:
   ```python
   from pipeline.core.runner import BasePipelineStep

   class MyStep(BasePipelineStep):
       async def _execute_step(self, data: PipelineData) -> StepResult:
           # Your logic here
           data.my_output = "result"
           return StepResult(success=True)
   ```

2. **Register in pipeline factory** (`pipeline/__init__.py`):
   ```python
   runner.register_step(MyStep())
   ```

3. **Update PipelineData model** (`pipeline/models/core.py`):
   ```python
   @dataclass
   class PipelineData:
       my_output: Optional[str] = None  # Add your fields
   ```

### Debug a Failed Task
```bash
# 1. Check worker logs
tail -f worker.log

# 2. Inspect task in Python
from celery_config import celery_app
task = celery_app.AsyncResult('task_id')
print(task.state, task.info)

# 3. Check Logfire traces (if configured)
# Visit: https://logfire.pydantic.dev
```

### Database Migrations
```bash
# After changing models in models/
make migration MSG="add new field"  # Creates migration
make migrate                         # Applies migration
make db-current                      # Shows current version
```

---

## Key Architectural Decisions

### Stateless Pipeline (In-Memory Data)
**Why**: Simplifies debugging (all context in Logfire traces), reduces DB writes, enables idempotent retries
**Trade-off**: Can't resume mid-pipeline on failure (must re-run entire pipeline)

### Celery Over FastAPI BackgroundTasks
**Why**: Persistent task state in Redis, client can poll status, horizontal scaling with multiple workers
**Alternative**: BackgroundTasks can't be polled or resumed after server restart

### Backend-First (No Direct DB Access from Frontend)
**Why**: Security (enforce authorization), flexibility (change DB schema without frontend changes), centralized business logic
**Trade-off**: Extra API latency vs direct Supabase client queries

### Memory-Constrained Design (Sequential Scraping)
**Context**: Render free tier = 512MB RAM, Playwright browser = ~150MB
**Solution**: `max_concurrent_scrapes = 1` (sequential, not parallel)
**Future**: Increase concurrency when upgraded to 1GB+ RAM

---

## Observability

### Logfire Tracing
Every pipeline execution creates a trace with nested spans:
```
pipeline.full_run
├─ pipeline.template_parser
│  └─ pydantic_ai.agent.run (auto-instrumented)
├─ pipeline.web_scraper
│  ├─ google_search
│  ├─ playwright.scrape_url
│  └─ pydantic_ai.agent.run (summarization)
└─ pipeline.email_composer
   ├─ pydantic_ai.agent.run (composition)
   └─ db.write_email
```

**Metrics Tracked**:
- Step timings, LLM token usage, scraping success rate, total cost per email

---

## Deployment (Render)

### Services
1. **Web** (FastAPI): `uvicorn main:app --host 0.0.0.0 --port $PORT`
2. **Worker** (Celery): `celery -A celery_config.celery_app worker`
3. **Redis**: Managed service

### Build Process (`build.sh`)
- Install Python dependencies
- Install Playwright browser (Chromium ~300MB, cached in `/opt/render/project/.cache`)

### Resource Limits
- **RAM**: 512MB (shared between web + worker on free tier)
- **Concurrency**: Worker limited to 1 task at a time
- **Task Duration**: 10-25s average

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Worker not picking up tasks | Check Redis: `make redis-ping`, restart worker |
| Playwright scraping fails | Reinstall: `python -m playwright install chromium` |
| Database connection errors | Validate `.env` with `make check-env` |
| Task stuck in PENDING | Check worker logs, inspect with `AsyncResult(task_id)` |
| Out of memory errors | Reduce `max_concurrent_scrapes` or upgrade RAM |

---

## Testing

```bash
# Run all tests
pytest

# Run specific step tests
pytest pipeline/steps/template_parser/

# Run with markers
pytest -m unit              # Fast unit tests only
pytest -m "not slow"        # Skip integration tests

# Coverage report
pytest --cov=pipeline --cov-report=html
```

**Important**: Always run from project root and use virtual environment:
```bash
source venv/bin/activate
pytest
```

---

## Further Reading

- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **Development Guide**: `CLAUDE.md` (detailed commands, patterns, conventions)
- **Agentic Pipeline**: `AGENTIC.MD` (pipeline design philosophy)
- **Logfire Dashboard**: https://logfire.pydantic.dev (observability)
