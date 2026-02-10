# Scribe

**AI-Powered Cold Email Generation with Multi-Step Agentic Pipeline**

Scribe is a production-ready cold email platform built with FastAPI that uses a sophisticated multi-step AI pipeline to generate personalized academic outreach emails. The system combines web scraping, academic paper research, and Claude AI to create contextually relevant emails based on customizable templates.

![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

---

## ✨ Features

- **Multi-Step Agentic Pipeline**: Template parsing → Web scraping → Academic enrichment → Email composition
- **Database-Backed Queue**: Submit up to 100 email recipients at once with sequential processing (Celery concurrency=1)
- **Real-Time Status Updates**: Poll queue status with position tracking and live progress indicators
- **Template Types**: Research (with ArXiv papers), Book (published works), General (professional info)
- **Smart Web Scraping**: Playwright-powered headless browser with JavaScript support
- **ArXiv Integration**: Automatic academic paper discovery and citation
- **Async Task Processing**: Celery-based job queue with persistent database state
- **Comprehensive Observability**: Logfire integration with LLM call tracking (cost, tokens, latency)
- **Anti-Hallucination Design**: Multi-source verification, uncertainty markers, chain-of-thought reasoning
- **Type-Safe**: Pydantic models throughout with structured LLM outputs via pydantic-ai

---

## 📚 Documentation

**Complete guides available in the [`docs/`](docs/) folder:**

- **[Quick Start Guide](docs/QUICKSTART.MD)** - Get Scribe running in 5 minutes
- **[Architecture Overview](docs/ARCHITECTURE.MD)** - System design and deployment
- **[Pipeline Deep Dive](docs/PIPELINE.MD)** - 4-step email generation pipeline
- **[Development Guide](docs/DEVELOPMENT.MD)** - Workflows, testing, and debugging
- **[API Reference](docs/API_REFERENCE.MD)** - Complete REST API documentation

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI 0.109+, Python 3.13, Uvicorn |
| **Database** | PostgreSQL (Supabase), SQLAlchemy 2.0, Alembic |
| **Authentication** | Supabase Auth, JWT validation |
| **AI/ML** | Anthropic Claude (Haiku 4.5, Sonnet 4.5), pydantic-ai |
| **Task Queue** | Celery 5.3+, Redis 5.0+ |
| **Web Scraping** | Playwright 1.56+, BeautifulSoup4, httpx |
| **Observability** | Logfire 4.14+ with auto-instrumentation |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- PostgreSQL (or Supabase account)
- Redis 5.0+
- Anthropic API key

### Installation

```bash
# Clone repository
git clone <repository-url>
cd pythonserver

# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Environment Configuration

Create `.env` file (see `.env.example`):

```bash
# Database (Supabase Transaction Pooler)
DB_USER=postgres.<project-ref>
DB_PASSWORD=your-password
DB_HOST=aws-1-<region>.pooler.supabase.com
DB_PORT=6543
DB_NAME=postgres

# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbG...

# APIs
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
GOOGLE_CSE_ID=012345...

# Redis (Celery)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Observability
LOGFIRE_TOKEN=your-token

# Server
ENVIRONMENT=development
DEBUG=True
ALLOWED_ORIGINS=http://localhost:3000
```

### Database Setup

```bash
# Run migrations
alembic upgrade head

# Create new migration (after model changes)
alembic revision --autogenerate -m "Description"
```

### Running the Application

```bash
# Terminal 1: Start FastAPI server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Start Celery worker
celery -A celery_config.celery_app worker --loglevel=info --queues=email_default --concurrency=1

# Terminal 3: (Optional) Start Flower monitoring
celery -A celery_config.celery_app flower
```

**Access Points:**
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- Flower Dashboard: http://localhost:5555

---

## 📡 API Endpoints

| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/api/user/init` | POST | Initialize user profile | Required |
| `/api/user/profile` | GET | Get current user | Required |
| `/api/email/generate` | POST | Generate single email (async) | Required |
| `/api/email/status/{task_id}` | GET | Check generation status | Required |
| `/api/email/{email_id}` | GET | Retrieve email by ID | Required |
| `/api/email/` | GET | List user's emails | Required |
| `/api/queue/batch` | POST | Submit batch (1-100 recipients) | Required |
| `/api/queue/` | GET | Get all user's queue items | Required |
| `/api/queue/{id}` | DELETE | Cancel pending queue item | Required |
| `/health` | GET | Health check | Public |

### Example: Generate Email

```bash
# 1. Generate email (returns task_id)
curl -X POST http://localhost:8000/api/email/generate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email_template": "Hi {{name}}, I love your work on {{research}}!",
    "recipient_name": "Dr. Jane Smith",
    "recipient_interest": "machine learning",
    "template_type": "research"
  }'

# Response: {"task_id": "abc-123"}

# 2. Poll status
curl http://localhost:8000/api/email/status/abc-123 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Response: {"status": "SUCCESS", "result": {"email_id": "550e8400-..."}}

# 3. Retrieve email
curl http://localhost:8000/api/email/550e8400-... \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Example: Batch Generate Emails

```bash
# 1. Submit batch (1-100 recipients)
curl -X POST http://localhost:8000/api/queue/batch \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"recipient_name": "Dr. Jane Smith", "recipient_interest": "machine learning"},
      {"recipient_name": "Dr. John Doe", "recipient_interest": "computer vision"},
      {"recipient_name": "Dr. Alice Johnson", "recipient_interest": "NLP"}
    ],
    "email_template": "Hi {{name}}, I love your work on {{research}}!"
  }'

# Response: {"queue_item_ids": ["uuid-1", "uuid-2", "uuid-3"]}

# 2. Poll queue status (every 2 seconds)
curl http://localhost:8000/api/queue/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Response: [
#   {"id": "uuid-1", "status": "COMPLETED", "email_id": "email-uuid-1", "position": null},
#   {"id": "uuid-2", "status": "PROCESSING", "email_id": null, "position": 1},
#   {"id": "uuid-3", "status": "PENDING", "email_id": null, "position": 2}
# ]

# 3. Cancel pending item (only PENDING status can be canceled)
curl -X DELETE http://localhost:8000/api/queue/uuid-3 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 🔄 Pipeline Architecture

The email generation pipeline executes four sequential steps:

```
┌─────────────────────┐
│  Template Parser    │  Claude Haiku extracts search terms & classifies type
│  (~1.2s)            │  Output: search_terms, template_type
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Web Scraper       │  Google Search + Playwright scraping + summarization
│   (~5.3s)           │  Output: scraped_content, urls, metadata
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  ArXiv Helper       │  Fetch academic papers (if RESEARCH type)
│  (~0.8s)            │  Output: arxiv_papers[]
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Email Composer     │  Claude Sonnet generates final email
│  (~3.1s)            │  Output: final_email, writes to database
└─────────────────────┘

Total: ~10.4s
```

**Key Features:**
- **Stateless Design**: PipelineData lives in-memory during execution
- **Structured Outputs**: All LLM responses validated against Pydantic models
- **Real-Time Updates**: Progress callbacks update Celery task state
- **Comprehensive Metadata**: JSONB storage of search terms, URLs, papers, timings
- **Memory Optimized**: Sequential browser usage for resource-constrained environments (Raspberry Pi)

---

## 🧪 Development

### Running Tests

```bash
# Activate virtual environment first
source venv/bin/activate

# Run all tests
pytest

# Run specific test file
pytest pipeline/steps/template_parser/test_template_parser.py

# Run with coverage
pytest --cov=pipeline --cov-report=html

# Run with verbose output
pytest -v -s
```

### Project Structure

```
pythonserver/
├── main.py                      # FastAPI application entry point
├── celery_config.py             # Celery task queue configuration
├── alembic.ini                  # Database migration config
│
├── api/
│   ├── dependencies.py          # Auth (get_supabase_user, get_current_user)
│   └── routes/
│       ├── user.py              # User management endpoints
│       └── email.py             # Email generation endpoints
│
├── models/
│   ├── user.py                  # User SQLAlchemy model
│   └── email.py                 # Email SQLAlchemy model (with JSONB metadata)
│
├── pipeline/
│   ├── core/
│   │   └── runner.py            # BasePipelineStep, PipelineRunner
│   ├── models/
│   │   └── core.py              # PipelineData, StepResult, TemplateType
│   └── steps/
│       ├── template_parser/     # Step 1: Template analysis
│       ├── web_scraper/         # Step 2: Web scraping + summarization
│       ├── arxiv_helper/        # Step 3: Academic paper fetching
│       └── email_composer/      # Step 4: Email generation + DB write
│
├── tasks/
│   └── email_tasks.py           # Celery task definitions
│
├── database/
│   ├── base.py                  # SQLAlchemy engine and Base
│   └── session.py               # Session management
│
├── config/
│   └── settings.py              # Pydantic Settings (environment config)
│
└── alembic/
    └── versions/                # Database migration files
```

### Common Commands

```bash
# Database migrations
alembic upgrade head                      # Apply migrations
alembic revision --autogenerate -m "msg"  # Create migration
alembic downgrade -1                      # Rollback one migration

# Development server
uvicorn main:app --reload                 # Hot reload enabled

# Celery worker
celery -A celery_config.celery_app worker --loglevel=info --queues=email_default --concurrency=1

# Celery monitoring
celery -A celery_config.celery_app flower
```

---

## 🏗️ Architecture Principles

### Backend-First Authentication
- Frontend uses Supabase ONLY for authentication (OAuth, JWT)
- Backend handles ALL database operations with service role key
- JWT validated on every request, user_id extracted from token
- No direct database access from frontend

### Stateless Pipeline Pattern
- `PipelineData` dataclass lives in-memory during execution
- Each step reads/writes specific fields
- Only final email persisted to database
- Celery manages job state in Redis (1-hour expiration)

### Observability-First Design
- Logfire integration at every layer
- Automatic pydantic-ai instrumentation (all LLM calls logged)
- Distributed tracing across pipeline steps
- Token usage, cost, and latency tracking

### Type Safety Throughout
- Pydantic models for all API requests/responses
- Structured LLM outputs via pydantic-ai
- SQLAlchemy 2.0 with type hints
- Automatic validation and serialization

---

## 🚀 Deployment

### Production Setup (Raspberry Pi + Cloudflare Tunnel)

The production backend is self-hosted on a Raspberry Pi with traffic routed through a Cloudflare Tunnel at `https://scribeapi.manitmishra.com`.

```bash
# Set production environment
ENVIRONMENT=production
DEBUG=False

# Configure CORS
ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Run with production server
uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 120
```

### Celery Worker Setup

```bash
# Production worker (recommended settings for Raspberry Pi)
celery -A celery_config.celery_app worker \
  --loglevel=info \
  --pool=solo \
  --concurrency=1 \
  --max-tasks-per-child=100
```

### Health Monitoring

The `/health` endpoint provides database connectivity status:

```json
{
  "status": "healthy",
  "service": "scribe-api",
  "version": "1.0.0",
  "database": "connected",
  "environment": "production"
}
```

---

## 📊 Database Schema

### Users Table
```sql
users (
  id UUID PRIMARY KEY,              -- Supabase auth.users UUID
  email VARCHAR(255) UNIQUE,
  display_name VARCHAR(255),
  generation_count INTEGER,
  created_at TIMESTAMP
)
```

### Emails Table
```sql
emails (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  recipient_name VARCHAR(255),
  recipient_interest VARCHAR(500),
  email_message TEXT,
  template_type ENUM('research', 'book', 'general'),
  metadata JSONB,                   -- Pipeline metadata
  created_at TIMESTAMP
)
```

### Queue Items Table
```sql
queue_items (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  recipient_name VARCHAR(255) NOT NULL,
  recipient_interest VARCHAR(500) NOT NULL,
  email_template_text TEXT NOT NULL,
  status VARCHAR(50) NOT NULL,      -- PENDING, PROCESSING, COMPLETED, FAILED
  celery_task_id VARCHAR(255),
  current_step VARCHAR(100),
  email_id UUID REFERENCES emails(id) ON DELETE SET NULL,
  error_message TEXT,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  created_at TIMESTAMP
)

-- Indexes for efficient queries
CREATE INDEX ix_queue_items_user_id ON queue_items(user_id);
CREATE INDEX ix_queue_items_status ON queue_items(status);
CREATE INDEX ix_queue_items_created_at ON queue_items(created_at);
CREATE INDEX ix_queue_items_user_status ON queue_items(user_id, status);
```

**Metadata JSONB Structure:**
```json
{
  "search_terms": ["Dr. Jane Smith machine learning"],
  "scraped_urls": ["https://example.com/profile"],
  "scraping_metadata": {"success_rate": 0.8},
  "arxiv_papers": [{"title": "...", "arxiv_url": "..."}],
  "step_timings": {"template_parser": 1.2, "web_scraper": 5.3},
  "model": "anthropic:claude-sonnet-4-5",
  "temperature": 0.7
}
```

---

## 📝 License

MIT License - See LICENSE file for details

---

## 🤝 Contributing

Contributions welcome! Please follow existing code patterns:
- Use Pydantic models for validation
- Add tests for new features (`pytest`)
- Follow existing project structure
- Update migrations for schema changes (`alembic`)

For detailed architecture documentation, see [CLAUDE.md](./CLAUDE.md).

---
