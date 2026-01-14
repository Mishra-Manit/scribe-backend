# Scribe API Reference

> **REST API documentation: authentication, endpoints, and error handling.**

---

## Overview

**Base URL**: `http://localhost:8000` (dev) | `https://scribe-api.onrender.com` (prod)
**Interactive Docs**: http://localhost:8000/docs

**Core Features**:
- User management and authentication
- Async email generation with 4-step AI pipeline
- Template generation from resumes
- Batch queue processing (1-100 emails)

---

## Authentication

### Flow
1. Frontend authenticates via **Supabase Auth** (OAuth: Google/GitHub)
2. Obtain JWT token from Supabase
3. Include token in `Authorization: Bearer {token}` header
4. Backend validates JWT and extracts user_id

### Example Request
```bash
curl -X POST http://localhost:8000/api/email/generate \
  -H "Authorization: Bearer {jwt_token}" \
  -H "Content-Type: application/json" \
  -d '{"email_template": "...", "recipient_name": "...", "recipient_interest": "..."}'
```

**Token Format**: `Authorization: Bearer eyJhbGc...`

---

## Endpoints

### User Management

#### POST /api/user/init
Initialize user profile (idempotent).

**Request**:
```json
{
  "display_name": "John Doe"  // Optional
}
```

**Response** (200):
```json
{
  "id": "uuid",
  "email": "john@example.com",
  "display_name": "John Doe",
  "generation_count": 0,
  "created_at": "2025-01-24T10:30:00Z"
}
```

**Errors**: `401` (invalid token), `422` (validation error)

---

#### GET /api/user/profile
Get current user profile.

**Response** (200): Same as `/init`

**Errors**: `401`, `404` (user not initialized)

---

#### PATCH /api/user/template
Update user's email template.

**Request**:
```json
{
  "email_template": "Hey {{name}}, I love your work on {{research}}!"
}
```

**Response** (200): Updated user object

---

### Email Generation

#### POST /api/email/generate
Start async email generation (returns immediately).

**Request**:
```json
{
  "email_template": "Hey {{name}}, I loved your work on {{research}}!",
  "recipient_name": "Dr. Jane Smith",
  "recipient_interest": "machine learning for healthcare"
}
```

**Validation**:
- `email_template`: 10-5000 chars, must contain `{{` and `}}`
- `recipient_name`: 2-255 chars
- `recipient_interest`: 2-500 chars

**Response** (202):
```json
{
  "task_id": "abc-123-def-456"
}
```

**Errors**: `401`, `422`

---

#### GET /api/email/status/{task_id}
Check task status (poll every 2 seconds).

**Response States**:

**PENDING** (queued):
```json
{
  "task_id": "abc-123",
  "status": "PENDING",
  "result": null
}
```

**STARTED** (running):
```json
{
  "task_id": "abc-123",
  "status": "STARTED",
  "result": {
    "current_step": "web_scraper",
    "step_timings": {"template_parser": 1.2}
  }
}
```

**SUCCESS** (completed):
```json
{
  "task_id": "abc-123",
  "status": "SUCCESS",
  "result": {
    "email_id": "uuid",
    "generation_time": 10.4,
    "step_timings": {
      "template_parser": 1.2,
      "web_scraper": 5.3,
      "arxiv_enricher": 0.8,
      "email_composer": 3.1
    }
  }
}
```

**FAILURE**:
```json
{
  "task_id": "abc-123",
  "status": "FAILURE",
  "error": "Step 'web_scraper' failed: Connection timeout"
}
```

**Errors**: `401`, `404` (task not found)

---

#### GET /api/email/{email_id}
Retrieve generated email.

**Response** (200):
```json
{
  "id": "uuid",
  "recipient_name": "Dr. Jane Smith",
  "recipient_interest": "machine learning for healthcare",
  "email_message": "Hey Dr. Smith,\n\nI'm fascinated by your work...",
  "template_type": "research",
  "metadata": {
    "papers_used": ["Neural Networks for Medical Diagnosis (2023)"],
    "sources": ["https://university.edu/faculty/smith"],
    "generation_time": 10.4
  },
  "created_at": "2025-01-24T10:30:00Z"
}
```

**Template Types**: `research` | `book` | `general`

**Errors**: `401`, `404` (not found or unauthorized)

---

#### GET /api/email/
Get paginated email history (newest first).

**Query Params**:
- `limit`: Max results (default: 20, max: 100)
- `offset`: Pagination offset (default: 0)
- `displayed`: Filter by displayed status (true/false)

**Response** (200): Array of email objects

---

#### PATCH /api/email/{email_id}
Update email properties.

**Request**:
```json
{
  "displayed": false  // Soft delete
}
```

**Response** (200): Updated email object

---

### Template Management

#### POST /api/templates/
Generate template from resume PDF (synchronous, 5-15s).

**Request**:
```json
{
  "pdf_url": "https://example.com/resume.pdf",
  "user_instructions": "Professional tone for academic outreach"
}
```

**Validation**:
- `pdf_url`: Valid HTTPS URL
- `user_instructions`: 10-2000 chars

**Response** (201):
```json
{
  "id": "uuid",
  "template_text": "Hey {{name}}, I'm [Your Name]...",
  "created_at": "2025-01-24T10:30:00Z"
}
```

**Errors**:
- `400` (PDF parsing failed)
- `429` (max 5 templates per user)
- `500` (LLM generation failed)

---

#### GET /api/templates/
List user's templates.

**Query Params**: `limit`, `offset` (same as email history)

**Response** (200): Array of template objects

---

#### GET /api/templates/{template_id}
Get specific template.

**Response** (200): Template object

**Errors**: `400` (invalid UUID), `401`, `404`

---

### Queue Management

#### POST /api/queue/batch
Submit batch email generation (1-100 items).

**Request**:
```json
{
  "items": [
    {
      "recipient_name": "Dr. Jane Smith",
      "recipient_interest": "machine learning"
    },
    {
      "recipient_name": "Dr. John Doe",
      "recipient_interest": "computer vision"
    }
  ],
  "email_template": "Hi {{name}}, love your work on {{research}}!"
}
```

**Response** (201):
```json
{
  "queue_item_ids": ["uuid1", "uuid2"]
}
```

**Errors**: `400` (invalid count or fields), `401`, `422`

---

#### GET /api/queue/
Get all queue items with status.

**Response** (200):
```json
[
  {
    "id": "uuid",
    "recipient_name": "Dr. Jane Smith",
    "status": "COMPLETED",
    "email_id": "email-uuid",
    "position": null,
    "started_at": "2025-01-24T10:30:00Z",
    "completed_at": "2025-01-24T10:30:15Z"
  },
  {
    "id": "uuid2",
    "recipient_name": "Dr. John Doe",
    "status": "PROCESSING",
    "position": 1,
    "started_at": "2025-01-24T10:30:16Z",
    "completed_at": null
  }
]
```

**Status Values**: `PENDING` | `PROCESSING` | `COMPLETED` | `FAILED`

**Position**: Queue position (null if completed/failed)

**Polling**: Poll every 2 seconds while items are active.

---

#### DELETE /api/queue/{id}
Cancel pending queue item.

**Response** (200):
```json
{
  "message": "Queue item {id} canceled successfully"
}
```

**Constraints**: Only `PENDING` items can be canceled

**Errors**:
- `400` (cannot cancel non-pending item)
- `401`, `404`

---

### Health & System

#### GET /health
Health check (no auth required).

**Response** (200):
```json
{
  "status": "healthy",
  "database": "connected",
  "celery": "operational",
  "redis": "connected",
  "timestamp": "2025-01-24T10:30:00Z"
}
```

**Response** (503): Same format with unhealthy status

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| 200 | OK | Success |
| 201 | Created | Resource created |
| 202 | Accepted | Async task started |
| 400 | Bad Request | Invalid input |
| 401 | Unauthorized | Invalid/missing JWT |
| 404 | Not Found | Resource not found |
| 422 | Validation Error | Schema validation failed |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Unexpected error |
| 503 | Service Unavailable | Service down |

### Error Response Format

**Standard Error**:
```json
{
  "detail": "Human-readable error message"
}
```

**Validation Error** (422):
```json
{
  "detail": [
    {
      "loc": ["body", "email_template"],
      "msg": "ensure this value has at least 10 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

### Common Errors & Solutions

**401 Unauthorized** → Refresh JWT token via Supabase SDK

**404 on /api/email/status/{task_id}** → Task expired (Redis TTL = 1 hour)

**422 Validation Error** → Check field constraints in error details

**Task stuck in PENDING** → Verify Celery worker is running (`make celery-worker`)

**429 Template Limit** → User has reached max 5 templates (delete old ones)

---

## Request/Response Schemas

### GenerateEmailRequest
```typescript
{
  email_template: string      // 10-5000 chars, must contain placeholders
  recipient_name: string      // 2-255 chars
  recipient_interest: string  // 2-500 chars
}
```

### EmailResponse
```typescript
{
  id: string                  // UUID
  recipient_name: string
  recipient_interest: string
  email_message: string       // Generated email
  template_type: "research" | "book" | "general"
  metadata: {
    papers_used?: string[]    // ArXiv papers (RESEARCH type only)
    sources: string[]         // URLs scraped
    generation_time: number   // Total seconds
    step_timings: Record<string, number>
  }
  created_at: string          // ISO 8601
}
```

### QueueItemResponse
```typescript
{
  id: string
  user_id: string
  recipient_name: string
  recipient_interest: string
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED"
  email_id: string | null     // UUID (if COMPLETED)
  position: number | null     // Queue position (null if done)
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}
```

---

## Complete Example Workflow

### Python (httpx)
```python
import httpx
import asyncio

async def generate_email(token: str):
    async with httpx.AsyncClient() as client:
        # 1. Start generation
        response = await client.post(
            "http://localhost:8000/api/email/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_template": "Hey {{name}}, love {{research}}!",
                "recipient_name": "Dr. Jane Smith",
                "recipient_interest": "machine learning"
            }
        )
        task_id = response.json()["task_id"]

        # 2. Poll for completion
        while True:
            response = await client.get(
                f"http://localhost:8000/api/email/status/{task_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            data = response.json()

            if data["status"] == "SUCCESS":
                email_id = data["result"]["email_id"]
                break
            elif data["status"] == "FAILURE":
                raise Exception(data["error"])

            await asyncio.sleep(2)

        # 3. Retrieve email
        response = await client.get(
            f"http://localhost:8000/api/email/{email_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.json()
```

---

## Further Reading

- **Quick Start**: [QUICKSTART.MD](QUICKSTART.MD) - Setup in 5 minutes
- **Architecture**: [ARCHITECTURE.MD](ARCHITECTURE.MD) - System design
- **Development**: [DEVELOPMENT.MD](DEVELOPMENT.MD) - Dev workflows
- **Interactive Docs**: http://localhost:8000/docs - Test endpoints in browser

---

*Last updated: 2025-01-24*
