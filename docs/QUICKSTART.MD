# Scribe - Quick Start Guide

> Get Scribe running on your machine in 5 minutes and generate your first personalized cold email.

---

## Overview

This guide will help you:
1. Install dependencies and configure environment variables (2 minutes)
2. Start the development server and Celery worker (1 minute)
3. Generate your first personalized email (2 minutes)

**Prerequisites:** macOS or Linux, Python 3.13+, and basic command-line familiarity.

**For detailed setup instructions, see [DEVELOPMENT.MD](DEVELOPMENT.MD)**.

---

## Step 1: Installation (2 minutes)

### Clone and Navigate
```bash
cd /path/to/pythonserver
```

### Create Virtual Environment
```bash
python3.13 -m venv venv
source venv/bin/activate
```

### Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium  # Required for web scraping (300MB download)
```

### Configure Environment Variables

Create `.env` file in the project root:

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
```

**Where to get API keys:**
- **Anthropic API Key**: [console.anthropic.com](https://console.anthropic.com/)
- **Google API Key & CSE ID**: [Google Custom Search](https://developers.google.com/custom-search/v1/introduction)
- **Supabase URL & Key**: Your Supabase project dashboard
- **Logfire Token**: [logfire.pydantic.dev](https://logfire.pydantic.dev/) (optional)

---

## Step 2: Start Services (1 minute)

### Option A: Quick Start (Recommended)

**Terminal 1: Start Redis + FastAPI + Celery Worker**
```bash
make redis-start  # Start Redis in background
make serve        # Starts FastAPI + Celery worker together
```

**Verify it's running:**
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "celery": "operational"
}
```

### Option B: Manual Start (for debugging)

**Terminal 1: Redis**
```bash
make redis-start
# Or manually: redis-server --daemonize yes
```

**Terminal 2: FastAPI Server**
```bash
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 3: Celery Worker**
```bash
source venv/bin/activate
make celery-worker
# Or manually: celery -A tasks.celery_app worker --loglevel=info
```

**Terminal 4: Flower (optional - monitoring UI)**
```bash
make flower
# Visit: http://localhost:5555
```

---

## Step 3: Generate Your First Email (2 minutes)

### Understanding Template Types

Scribe supports three template types:

| Type | Description | When to Use |
|------|-------------|-------------|
| **RESEARCH** | Mentions research papers the recipient has published | Academic outreach for research collaboration |
| **BOOK** | Mentions books the recipient has authored | Contacting published authors |
| **GENERAL** | Uses general professional information | Standard cold emails |

The pipeline automatically selects the type based on your template content.

---

### Example 1: Research Template (Recommended for First Try)

**Create a file: `test_request.json`**

```json
{
  "email_template": "Hey {{name}}, I'm fascinated by your work on {{research_area}}. I read your recent paper on machine learning and would love to discuss potential collaboration opportunities. Could we schedule a brief call?",
  "recipient_name": "Dr. Yann LeCun",
  "recipient_interest": "deep learning and computer vision"
}
```

**Send the request:**

```bash
curl -X POST http://localhost:8000/api/email/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d @test_request.json
```

**Response:**
```json
{
  "task_id": "abc-123-def-456"
}
```

---

### Check Generation Status

**Poll for completion:**

```bash
curl http://localhost:8000/api/email/status/abc-123-def-456 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Status progression:**
```json
{"status": "PENDING"}   # Task queued
{"status": "STARTED"}   # Pipeline running
{"status": "SUCCESS", "result": {"email_id": "email-789"}}  # Complete!
```

---

### Retrieve Your Generated Email

```bash
curl http://localhost:8000/api/email/email-789 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "id": "email-789",
  "recipient_name": "Dr. Yann LeCun",
  "recipient_interest": "deep learning and computer vision",
  "email_message": "Hey Dr. LeCun,\n\nI'm fascinated by your pioneering work on convolutional neural networks and their applications in computer vision. I recently read your 2015 paper \"Deep Learning\" in Nature, where you discuss...",
  "template_type": "research",
  "metadata": {
    "papers_used": ["Deep Learning (Nature, 2015)"],
    "sources": ["https://yann.lecun.com", "https://scholar.google.com/..."],
    "generation_time": 4.2
  },
  "created_at": "2025-01-24T10:30:00Z"
}
```

---

### Example 2: General Template

**Simpler template without research focus:**

```json
{
  "email_template": "Hi {{name}}, I came across your profile and was impressed by your expertise in {{topic}}. I'd love to connect and learn more about your work.",
  "recipient_name": "Jane Smith",
  "recipient_interest": "sustainable energy solutions"
}
```

This will be classified as `GENERAL` template type and skip the ArXiv paper enrichment step.

---

### Example 3: Batch Email Generation (Queue System)

**Generate multiple emails at once (1-100 recipients):**

```bash
curl -X POST http://localhost:8000/api/queue/batch \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "recipient_name": "Dr. Jane Smith",
        "recipient_interest": "machine learning for healthcare"
      },
      {
        "recipient_name": "Dr. John Doe",
        "recipient_interest": "computer vision"
      },
      {
        "recipient_name": "Dr. Alice Johnson",
        "recipient_interest": "natural language processing"
      }
    ],
    "email_template": "Hi {{name}}, I'\''m fascinated by your work on {{research_area}}. Would you be open to a brief call?"
  }'
```

**Response:**
```json
{
  "queue_item_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "660e8400-e29b-41d4-a716-446655440001",
    "770e8400-e29b-41d4-a716-446655440002"
  ]
}
```

**Monitor queue progress (poll every 2 seconds):**

```bash
curl http://localhost:8000/api/queue/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response showing processing status:**
```json
[
  {
    "id": "550e8400-...",
    "status": "COMPLETED",
    "position": null,
    "email_id": "email-uuid-1",
    "started_at": "2025-01-24T10:30:00Z",
    "completed_at": "2025-01-24T10:30:15Z"
  },
  {
    "id": "660e8400-...",
    "status": "PROCESSING",
    "position": 1,
    "email_id": null,
    "started_at": "2025-01-24T10:30:16Z",
    "completed_at": null
  },
  {
    "id": "770e8400-...",
    "status": "PENDING",
    "position": 2,
    "email_id": null,
    "started_at": null,
    "completed_at": null
  }
]
```

**Why sequential processing?**
- Celery worker runs with `concurrency=1` to prevent API rate limits
- Items processed one at a time in FIFO order
- Each email takes ~10-15 seconds to generate
- Frontend polls every 2 seconds for real-time updates

---

## What Happens Under the Hood?

When you send a generation request, Scribe executes a **4-step pipeline**:

```
1. Template Parser  � Analyzes your template and extracts search terms
2. Web Scraper      � Finds information about the recipient online
3. ArXiv Enricher   � Fetches relevant research papers (RESEARCH type only)
4. Email Composer   � Generates personalized email with all context
```

**Execution time:** 3-5 seconds (varies by template complexity and web scraping)

**For detailed pipeline explanation, see [PIPELINE.MD](PIPELINE.MD)**.

---

## Common Issues & Solutions

### Issue: `redis.exceptions.ConnectionError`
**Solution:** Redis is not running
```bash
make redis-start
# Verify: redis-cli ping  # Should respond "PONG"
```

### Issue: `playwright._impl._api_types.Error`
**Solution:** Chromium browser not installed
```bash
playwright install chromium
```

### Issue: `anthropic.APIError: Invalid API key`
**Solution:** Check your `.env` file has correct `ANTHROPIC_API_KEY`

### Issue: `Task stays in PENDING status`
**Solution:** Celery worker is not running
```bash
# Check worker is running:
celery -A tasks.celery_app inspect active
```

### Issue: `401 Unauthorized`
**Solution:** You need a valid JWT token from Supabase Auth

**For development/testing**, you can disable auth temporarily:
- Comment out `Depends(get_current_user)` in `api/routes/email.py`
- **� Remember to re-enable before deploying to production**

---

## Development Workflow Commands

### Start Everything
```bash
make serve         # FastAPI + Celery worker (one command)
```

### Stop Everything
```bash
make stop-all      # Kills all running processes
```

### View Worker Logs
```bash
# Logs are printed to terminal where `make serve` was run
# Or use Flower UI: http://localhost:5555
```

### Run Database Migrations
```bash
alembic upgrade head
```

### Run Tests
```bash
pytest                          # Run all tests
pytest -v                       # Verbose output
pytest pipeline/steps/          # Test specific directory
```

---

## API Endpoints Quick Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/user/init` | Initialize user profile |
| GET | `/api/user/profile` | Get current user data |
| POST | `/api/email/generate` | Start email generation (returns `task_id`) |
| GET | `/api/email/status/{task_id}` | Check generation status |
| GET | `/api/email/{email_id}` | Retrieve generated email |
| GET | `/health` | System health check |

**Full API documentation:** [API_REFERENCE.MD](API_REFERENCE.MD)

---

## Template Placeholder Variables

Your email templates can use these placeholders:

| Placeholder | Description | Example |
|------------|-------------|---------|
| `{{name}}` | Recipient's name | Dr. Jane Smith |
| `{{research_area}}` | Recipient's research interest | machine learning |
| `{{research}}` | General research mention | your work on neural networks |
| `{{university}}` | Recipient's institution | Stanford University |
| `{{paper}}` | Specific paper title | "Attention Is All You Need" |
| `{{topic}}` | General topic | sustainable energy |

**Note:** Placeholders are automatically detected and filled by the pipeline.

---

## Template Best Practices

###  Good Template
```
Hey {{name}}, I read your paper on {{research_area}} and found your approach to
{{specific_topic}} fascinating. I'm working on a similar problem and would love
to discuss potential collaboration.
```

**Why it works:**
- Specific mention of research area
- References work (paper)
- Clear ask (collaboration)

### L Poor Template
```
Hi, I saw your profile and think we should connect.
```

**Why it fails:**
- Too generic
- No personalization placeholders
- No context for the recipient

---

## Next Steps

Now that you have Scribe running:

1. **Learn the Architecture**: Read [ARCHITECTURE.MD](ARCHITECTURE.MD) to understand system design
2. **Deep Dive into Pipeline**: See [PIPELINE.MD](PIPELINE.MD) for detailed step implementations
3. **Development Workflows**: Check [DEVELOPMENT.MD](DEVELOPMENT.MD) for testing, debugging, and deployment
4. **API Integration**: Read [API_REFERENCE.MD](API_REFERENCE.MD) for complete endpoint documentation

---

## Key Files to Know

```
/pythonserver
   main.py                 # FastAPI application entry point
   tasks/celery_app.py     # Celery task definitions
   .env                    # Your environment variables (gitignored)
   alembic/                # Database migrations
   api/routes/             # REST API endpoints
   pipeline/steps/         # 4 pipeline steps implementation
      template_parser/
      web_scraper/
      arxiv_helper/
      email_composer/
   docs/                   # Documentation (you are here!)
```

---

## Getting Help

**Documentation:**
- [ARCHITECTURE.MD](ARCHITECTURE.MD) - System design
- [PIPELINE.MD](PIPELINE.MD) - Pipeline implementation
- [DEVELOPMENT.MD](DEVELOPMENT.MD) - Dev workflows
- [API_REFERENCE.MD](API_REFERENCE.MD) - API docs

**Troubleshooting:**
- Check FastAPI logs: Terminal where `uvicorn` is running
- Check Celery logs: Terminal where worker is running
- Check Flower UI: http://localhost:5555 (if enabled)
- Check health endpoint: `curl http://localhost:8000/health`

**Common Commands:**
```bash
make serve          # Start everything
make stop-all       # Stop everything
make redis-start    # Start Redis
make celery-worker  # Start worker only
make flower         # Start monitoring UI
pytest              # Run tests
alembic upgrade head  # Apply migrations
```

---

## Production Deployment

**The production backend is self-hosted on a Raspberry Pi with a Cloudflare Tunnel:**
- See [ARCHITECTURE.MD - Deployment Section](ARCHITECTURE.MD#deployment-raspberry-pi--cloudflare-tunnel)
- Public URL: `https://scribeapi.manitmishra.com`
- Cloudflare Tunnel handles SSL/TLS and DDoS protection
- Redis runs locally on the Pi
- Celery worker runs with `concurrency=1` for memory efficiency

---

*Last updated: 2025-01-24*

**Ready to generate personalized emails at scale! =�**
