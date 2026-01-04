# Scribe API Reference

> **Complete REST API documentation: authentication, endpoints, schemas, examples, and error handling.**

---

## Overview

The Scribe API provides endpoints for:

- **User Management**: Initialize and retrieve user profiles
- **Email Generation**: Create personalized cold emails
- **Task Status**: Poll long-running generation tasks
- **Email Retrieval**: Fetch generated emails

**Base URL**: `http://localhost:8000` (development) or `https://scribe-api.onrender.com` (production)

**API Docs**: http://localhost:8000/docs (interactive Swagger UI)

---

## Authentication

### Auth Flow

Scribe uses **Supabase Auth** for user authentication with JWT tokens.

```mermaid
sequenceDiagram
    participant Client as Frontend
    participant Supabase as Supabase Auth
    participant API as Scribe API
    participant DB as PostgreSQL

    Client->>Supabase: OAuth Login (Google/GitHub)
    Supabase->>Client: JWT Token

    Client->>API: POST /api/user/init<br/>Authorization: Bearer {token}
    API->>Supabase: Validate JWT
    Supabase->>API: User ID + Email
    API->>DB: Create/update user
    DB->>API: User record
    API->>Client: User profile

    Client->>API: POST /api/email/generate<br/>Authorization: Bearer {token}
    API->>Supabase: Validate JWT
    Supabase->>API: User ID
    API->>API: Enqueue Celery task
    API->>Client: {task_id}
```

### Getting a JWT Token

**1. Frontend uses Supabase SDK**:

```javascript
// JavaScript/TypeScript (Next.js)
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
)

// Sign in with OAuth
const { data, error } = await supabase.auth.signInWithOAuth({
  provider: 'google',
  options: {
    redirectTo: `${window.location.origin}/dashboard`
  }
})

// Get current session
const { data: { session } } = await supabase.auth.getSession()
const token = session?.access_token
```

**2. Include token in API requests**:

```bash
curl -X POST http://localhost:8000/api/email/generate \
  -H "Authorization: Bearer {your_jwt_token}" \
  -H "Content-Type: application/json" \
  -d '{"email_template": "...", "recipient_name": "...", "recipient_interest": "..."}'
```

### Authorization Header Format

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Token Validation

**Backend automatically validates tokens** on protected endpoints:

```python
from api.dependencies import get_current_user
from models.user import User

@router.post("/generate")
async def generate_email(
    request: GenerateEmailRequest,
    current_user: User = Depends(get_current_user)  # ← Token validation
):
    # current_user is validated User object from database
    # If token invalid/expired, returns 401 Unauthorized
```

---

## Endpoints

### User Management

#### POST /api/user/init

**Initialize user profile** (idempotent).

**Request**:
```http
POST /api/user/init
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "display_name": "John Doe"  // Optional
}
```

**Response** (200 OK):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "john@example.com",
  "display_name": "John Doe",
  "generation_count": 0,
  "created_at": "2025-01-24T10:30:00Z"
}
```

**Errors**:
- `401 Unauthorized`: Invalid or missing JWT token
- `422 Unprocessable Entity`: Invalid request body

**Usage Notes**:
- Call this endpoint after user signs in
- Idempotent: calling multiple times returns existing user
- Required before calling `/api/email/generate`

---

#### GET /api/user/profile

**Get current user profile**.

**Request**:
```http
GET /api/user/profile
Authorization: Bearer {jwt_token}
```

**Response** (200 OK):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "john@example.com",
  "display_name": "John Doe",
  "generation_count": 15,
  "created_at": "2025-01-24T10:30:00Z"
}
```

**Errors**:
- `401 Unauthorized`: Invalid or missing JWT token
- `404 Not Found`: User not initialized (call `/api/user/init` first)

---

### Email Generation

#### POST /api/email/generate

**Start email generation** (async, returns task ID).

**Request**:
```http
POST /api/email/generate
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "email_template": "Hey {{name}}, I loved your work on {{research}}!",
  "recipient_name": "Dr. Jane Smith",
  "recipient_interest": "machine learning for healthcare"
}
```

**Request Schema**:

```typescript
interface GenerateEmailRequest {
  email_template: string     // Min 10, max 5000 chars
  recipient_name: string     // Min 2, max 255 chars
  recipient_interest: string // Min 2, max 500 chars
}
```

**Response** (202 Accepted):
```json
{
  "task_id": "abc-123-def-456"
}
```

**Request Flow**:

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI
    participant Celery
    participant Redis
    participant Worker

    Client->>API: POST /api/email/generate
    API->>API: Validate JWT & request
    API->>Celery: Enqueue task
    Celery->>Redis: Store task state (PENDING)
    API->>Client: 202 {task_id}

    Worker->>Redis: Poll for tasks
    Redis->>Worker: New task
    Worker->>Worker: Execute 4-step pipeline
    Worker->>Redis: Update state (STARTED → SUCCESS)

    Client->>API: GET /api/email/status/{task_id}
    API->>Redis: Query task state
    Redis->>API: SUCCESS + result
    API->>Client: 200 {email_id}
```

**Errors**:
- `401 Unauthorized`: Invalid or missing JWT token
- `422 Unprocessable Entity`: Invalid request body (see error details)
- `500 Internal Server Error`: Task enqueue failed

**Validation Rules**:
- `email_template` must contain placeholders (`{{` and `}}`)
- All fields required

**Examples**:

**curl**:
```bash
curl -X POST http://localhost:8000/api/email/generate \
  -H "Authorization: Bearer eyJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{
    "email_template": "Hey {{name}}, I loved your paper on {{research}}!",
    "recipient_name": "Dr. Yann LeCun",
    "recipient_interest": "deep learning and computer vision"
  }'
```

**Python (httpx)**:
```python
import httpx

async def generate_email(token: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/email/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email_template": "Hey {{name}}, love {{research}}!",
                "recipient_name": "Dr. Jane Smith",
                "recipient_interest": "machine learning"
            }
        )

        return response.json()  # {"task_id": "..."}
```

**JavaScript (fetch)**:
```javascript
async function generateEmail(token) {
  const response = await fetch('http://localhost:8000/api/email/generate', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      email_template: 'Hey {{name}}, love {{research}}!',
      recipient_name: 'Dr. Jane Smith',
      recipient_interest: 'machine learning'
    })
  })

  return await response.json()  // {task_id: "..."}
}
```

---

#### GET /api/email/status/{task_id}

**Check task status** (poll for completion).

**Request**:
```http
GET /api/email/status/abc-123-def-456
Authorization: Bearer {jwt_token}
```

**Response States**:

**PENDING** (task queued):
```json
{
  "task_id": "abc-123-def-456",
  "status": "PENDING",
  "result": null,
  "error": null
}
```

**STARTED** (pipeline running):
```json
{
  "task_id": "abc-123-def-456",
  "status": "STARTED",
  "result": {
    "current_step": "web_scraper",
    "step_status": "started",
    "step_timings": {
      "template_parser": 1.2
    }
  },
  "error": null
}
```

**SUCCESS** (completed):
```json
{
  "task_id": "abc-123-def-456",
  "status": "SUCCESS",
  "result": {
    "email_id": "550e8400-e29b-41d4-a716-446655440000",
    "step_timings": {
      "template_parser": 1.2,
      "web_scraper": 5.3,
      "arxiv_enricher": 0.8,
      "email_composer": 3.1
    },
    "generation_time": 10.4
  },
  "error": null
}
```

**FAILURE** (error occurred):
```json
{
  "task_id": "abc-123-def-456",
  "status": "FAILURE",
  "result": null,
  "error": "Step 'web_scraper' failed: Connection timeout"
}
```

**Task State Lifecycle**:

```
PENDING → STARTED → SUCCESS
              ↓
           FAILURE (with retries)
```

**Polling Strategy**:

```javascript
async function pollTaskStatus(taskId, token, maxAttempts = 60) {
  for (let i = 0; i < maxAttempts; i++) {
    const response = await fetch(
      `http://localhost:8000/api/email/status/${taskId}`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    )

    const data = await response.json()

    if (data.status === 'SUCCESS') {
      return data.result  // {email_id: "..."}
    }

    if (data.status === 'FAILURE') {
      throw new Error(data.error)
    }

    // Wait 2 seconds before next poll
    await new Promise(resolve => setTimeout(resolve, 2000))
  }

  throw new Error('Task timeout after 2 minutes')
}
```

**Errors**:
- `401 Unauthorized`: Invalid or missing JWT token
- `404 Not Found`: Task ID not found
- `500 Internal Server Error`: Redis connection error

---

#### GET /api/email/{email_id}

**Retrieve generated email** by ID.

**Request**:
```http
GET /api/email/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer {jwt_token}
```

**Response** (200 OK):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "recipient_name": "Dr. Jane Smith",
  "recipient_interest": "machine learning for healthcare",
  "email_message": "Hey Dr. Smith,\n\nI'm fascinated by your pioneering work on using machine learning for early disease detection in healthcare. I recently came across your 2023 paper \"Neural Networks for Medical Diagnosis\" published in Nature Medicine, where you discuss how deep learning models can analyze medical imaging data with accuracy rates exceeding traditional methods.\n\nI'm particularly interested in the novel architecture you proposed for handling imbalanced medical datasets. Would you have 15 minutes for a brief call to discuss potential collaboration opportunities in this space?\n\nBest regards,\nJohn",
  "template_type": "research",
  "metadata": {
    "papers_used": [
      "Neural Networks for Medical Diagnosis (Nature Medicine, 2023)"
    ],
    "sources": [
      "https://university.edu/faculty/smith",
      "https://scholar.google.com/citations?user=..."
    ],
    "generation_time": 10.4,
    "step_timings": {
      "template_parser": 1.2,
      "web_scraper": 5.3,
      "arxiv_enricher": 0.8,
      "email_composer": 3.1
    },
    "validation_attempts": 1
  },
  "created_at": "2025-01-24T10:30:00Z"
}
```

**Response Schema**:

```typescript
interface EmailResponse {
  id: string                      // UUID
  recipient_name: string
  recipient_interest: string
  email_message: string           // Final email content
  template_type: "research" | "book" | "general"
  metadata: {
    papers_used?: string[]        // ArXiv papers mentioned (RESEARCH type)
    sources: string[]             // URLs scraped
    generation_time: number       // Total seconds
    step_timings: Record<string, number>
    validation_attempts: number
  }
  created_at: string              // ISO 8601 timestamp
}
```

**Errors**:
- `401 Unauthorized`: Invalid or missing JWT token
- `404 Not Found`: Email not found or user doesn't own email
- `500 Internal Server Error`: Database query error

**Security Note**: Users can only access their own emails (enforced by user_id check).

---

### Template Management

#### POST /api/templates/

**Generate email template from resume** (synchronous, 5-15 seconds).

**Request**:
```http
POST /api/templates/
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "pdf_url": "https://example.com/resume.pdf",
  "user_instructions": "Professional tone for academic outreach. Emphasize research experience."
}
```

**Request Schema**:
```typescript
interface GenerateTemplateRequest {
  pdf_url: string           // Publicly accessible PDF URL (HttpUrl validated)
  user_instructions: string // Custom instructions for template generation (10-2000 chars)
}
```

**Response** (201 Created):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-uuid-here",
  "pdf_url": "https://example.com/resume.pdf",
  "template_text": "Hey {{name}}, I'm [Your Name], a [Your Role] with expertise in {{research_area}}. I noticed your work on {{specific_topic}} and wanted to reach out...",
  "user_instructions": "Professional tone for academic outreach. Emphasize research experience.",
  "created_at": "2025-01-24T10:30:00Z"
}
```

**How It Works**:
1. Backend fetches PDF from provided URL
2. Extracts text content from PDF
3. Sends text + user instructions to Claude Haiku 4.5
4. Returns generated template with placeholder syntax (e.g., `{{name}}`, `{{research}}`)
5. Template saved to database for reuse

**Usage Limits**:
- **Maximum 5 templates per user** (enforced server-side)
- Synchronous operation (user waits for completion, no background task)
- Template generation takes 5-15 seconds typically

**Errors**:
- `400 Bad Request`: PDF parsing failed (invalid URL, unreadable PDF, network error)
- `401 Unauthorized`: Invalid or missing JWT token
- `422 Unprocessable Entity`: Validation error (invalid URL format, instructions too long/short)
- `429 Too Many Requests`: User has reached 5 template limit
- `500 Internal Server Error`: LLM generation failed (API errors, timeouts)

**Example Usage**:

```bash
curl -X POST https://api.scribe.com/api/templates/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_url": "https://storage.example.com/resume.pdf",
    "user_instructions": "Create a friendly but professional email template for reaching out to professors about research opportunities."
  }'
```

---

#### GET /api/templates/

**List user's templates** (paginated, newest first).

**Request**:
```http
GET /api/templates/?limit=20&offset=0
Authorization: Bearer {jwt_token}
```

**Query Parameters**:
- `limit` (optional): Number of results (default: 20, max: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response** (200 OK):
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "user-uuid-here",
    "pdf_url": "https://example.com/resume.pdf",
    "template_text": "Hey {{name}}, I'm...",
    "user_instructions": "Professional tone for academic outreach",
    "created_at": "2025-01-24T10:30:00Z"
  },
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "user_id": "user-uuid-here",
    "pdf_url": "https://example.com/resume_v2.pdf",
    "template_text": "Dear {{name}}, I am...",
    "user_instructions": "Formal tone for corporate outreach",
    "created_at": "2025-01-23T15:20:00Z"
  }
]
```

**Errors**:
- `401 Unauthorized`: Invalid or missing JWT token

**Example Usage**:

```bash
curl https://api.scribe.com/api/templates/?limit=10 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

#### GET /api/templates/{template_id}

**Get specific template by ID**.

**Request**:
```http
GET /api/templates/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer {jwt_token}
```

**Response** (200 OK):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-uuid-here",
  "pdf_url": "https://example.com/resume.pdf",
  "template_text": "Hey {{name}}, I'm [Your Name]...",
  "user_instructions": "Professional tone for academic outreach",
  "created_at": "2025-01-24T10:30:00Z"
}
```

**Errors**:
- `400 Bad Request`: Invalid UUID format
- `401 Unauthorized`: Invalid or missing JWT token
- `404 Not Found`: Template doesn't exist or user doesn't own it

**Security Note**: Users can only access their own templates (enforced by user_id check).

**Example Usage**:

```bash
curl https://api.scribe.com/api/templates/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

### Health & System

#### GET /health

**System health check** (no authentication required).

**Request**:
```http
GET /health
```

**Response** (200 OK):
```json
{
  "status": "healthy",
  "database": "connected",
  "celery": "operational",
  "redis": "connected",
  "timestamp": "2025-01-24T10:30:00Z"
}
```

**Response** (503 Service Unavailable):
```json
{
  "status": "unhealthy",
  "database": "connected",
  "celery": "no workers",
  "redis": "disconnected",
  "timestamp": "2025-01-24T10:30:00Z"
}
```

**Usage**:
- Used by Render.com for health checks
- Used for monitoring and alerting
- No authentication required

---

## Request/Response Schemas

### GenerateEmailRequest

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["email_template", "recipient_name", "recipient_interest"],
  "properties": {
    "email_template": {
      "type": "string",
      "minLength": 10,
      "maxLength": 5000,
      "description": "Email template with placeholders like {{name}}, {{research}}"
    },
    "recipient_name": {
      "type": "string",
      "minLength": 2,
      "maxLength": 255,
      "description": "Full name of recipient (e.g., 'Dr. Jane Smith')"
    },
    "recipient_interest": {
      "type": "string",
      "minLength": 2,
      "maxLength": 500,
      "description": "Research area or interest (e.g., 'machine learning')"
    }
  }
}
```

### GenerateEmailResponse

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["task_id"],
  "properties": {
    "task_id": {
      "type": "string",
      "description": "Celery task ID for polling status"
    }
  }
}
```

### TaskStatusResponse

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["task_id", "status"],
  "properties": {
    "task_id": {
      "type": "string"
    },
    "status": {
      "type": "string",
      "enum": ["PENDING", "STARTED", "SUCCESS", "FAILURE"]
    },
    "result": {
      "type": "object",
      "description": "Result data (when status=SUCCESS)"
    },
    "error": {
      "type": "string",
      "description": "Error message (when status=FAILURE)"
    }
  }
}
```

### EmailResponse

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["id", "recipient_name", "recipient_interest", "email_message", "template_type", "created_at"],
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "recipient_name": {
      "type": "string"
    },
    "recipient_interest": {
      "type": "string"
    },
    "email_message": {
      "type": "string"
    },
    "template_type": {
      "type": "string",
      "enum": ["research", "book", "general"]
    },
    "metadata": {
      "type": "object",
      "properties": {
        "papers_used": {
          "type": "array",
          "items": {"type": "string"}
        },
        "sources": {
          "type": "array",
          "items": {"type": "string"}
        },
        "generation_time": {
          "type": "number"
        },
        "step_timings": {
          "type": "object"
        }
      }
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | When It Happens |
|------|---------|----------------|
| `200 OK` | Success | Request completed successfully |
| `202 Accepted` | Async task created | Email generation started |
| `400 Bad Request` | Invalid input | Malformed JSON or missing fields |
| `401 Unauthorized` | Auth failed | Invalid/missing/expired JWT token |
| `403 Forbidden` | Permission denied | User doesn't own requested resource |
| `404 Not Found` | Resource not found | Email ID or task ID doesn't exist |
| `422 Unprocessable Entity` | Validation failed | Request body doesn't match schema |
| `500 Internal Server Error` | Server error | Unexpected error (check logs) |
| `503 Service Unavailable` | Service down | Database or Redis unavailable |

### Error Response Format

All errors return JSON with this structure:

```json
{
  "detail": "Human-readable error message"
}
```

**Example** (401 Unauthorized):
```json
{
  "detail": "Invalid authentication credentials"
}
```

**Example** (422 Validation Error):
```json
{
  "detail": [
    {
      "loc": ["body", "email_template"],
      "msg": "ensure this value has at least 10 characters",
      "type": "value_error.any_str.min_length",
      "ctx": {"limit_value": 10}
    }
  ]
}
```

### Common Errors and Solutions

**Error**: `401 Unauthorized`

**Cause**: Invalid, missing, or expired JWT token

**Solution**:
```javascript
// Refresh token if expired
const { data, error } = await supabase.auth.refreshSession()
const newToken = data.session?.access_token
```

---

**Error**: `404 Not Found` on `/api/email/status/{task_id}`

**Cause**: Task ID doesn't exist or expired (Redis TTL = 1 hour)

**Solution**:
- Check task ID spelling
- Task results expire after 1 hour
- Re-run generation if needed

---

**Error**: `422 Unprocessable Entity`

**Cause**: Request body validation failed

**Solution**:
```json
// Check validation error details
{
  "detail": [
    {
      "loc": ["body", "email_template"],
      "msg": "Template must contain placeholders like {{name}}"
    }
  ]
}

// Fix: Add placeholders to template
{
  "email_template": "Hey {{name}}, love {{research}}!"
}
```

---

**Error**: Task stuck in `PENDING` status

**Cause**: Celery worker not running or queue name mismatch

**Solution**:
```bash
# Check if worker is running
celery -A celery_config.celery_app inspect active

# If no workers, start one:
make celery-worker
```

---

### Retry Strategy

**Client-Side Retries**:

For transient errors (500, 503), implement exponential backoff:

```javascript
async function fetchWithRetry(url, options, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetch(url, options)

      if (response.ok) {
        return await response.json()
      }

      if (response.status >= 500) {
        // Server error - retry
        const delay = Math.pow(2, attempt) * 1000  // 2s, 4s, 8s
        await new Promise(resolve => setTimeout(resolve, delay))
        continue
      }

      // Client error (4xx) - don't retry
      throw new Error(`HTTP ${response.status}: ${await response.text()}`)

    } catch (error) {
      if (attempt === maxRetries) {
        throw error
      }
    }
  }
}
```

**Server-Side Retries**:

Celery automatically retries failed tasks:
- Max retries: 3
- Backoff: 60s, 120s, 240s
- Only retries external API failures and network errors

---

## Rate Limiting

**Current Limits** (per user):
- **Email Generation**: 100 requests/hour
- **Status Checks**: 1000 requests/hour
- **Email Retrieval**: 500 requests/hour

**Headers**:
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1706097600
```

**Error** (429 Too Many Requests):
```json
{
  "detail": "Rate limit exceeded. Try again in 300 seconds."
}
```

---

## Complete Examples

### Full Workflow (Python)

```python
import httpx
import asyncio

async def generate_and_retrieve_email(token: str):
    """Complete workflow: generate email and retrieve result."""

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
        print(f"Task started: {task_id}")

        # 2. Poll for completion
        while True:
            response = await client.get(
                f"http://localhost:8000/api/email/status/{task_id}",
                headers={"Authorization": f"Bearer {token}"}
            )

            data = response.json()
            print(f"Status: {data['status']}")

            if data["status"] == "SUCCESS":
                email_id = data["result"]["email_id"]
                break

            if data["status"] == "FAILURE":
                raise Exception(f"Generation failed: {data['error']}")

            await asyncio.sleep(2)  # Wait 2 seconds

        # 3. Retrieve email
        response = await client.get(
            f"http://localhost:8000/api/email/{email_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        email = response.json()
        print(f"Email generated:\n{email['email_message']}")

        return email

# Usage
token = "your_jwt_token_here"
email = asyncio.run(generate_and_retrieve_email(token))
```

### Full Workflow (JavaScript/TypeScript)

```typescript
async function generateAndRetrieveEmail(token: string) {
  // 1. Start generation
  const generateResponse = await fetch('http://localhost:8000/api/email/generate', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      email_template: 'Hey {{name}}, love {{research}}!',
      recipient_name: 'Dr. Jane Smith',
      recipient_interest: 'machine learning'
    })
  })

  const { task_id } = await generateResponse.json()
  console.log(`Task started: ${task_id}`)

  // 2. Poll for completion
  let email_id: string
  while (true) {
    const statusResponse = await fetch(
      `http://localhost:8000/api/email/status/${task_id}`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    )

    const data = await statusResponse.json()
    console.log(`Status: ${data.status}`)

    if (data.status === 'SUCCESS') {
      email_id = data.result.email_id
      break
    }

    if (data.status === 'FAILURE') {
      throw new Error(`Generation failed: ${data.error}`)
    }

    await new Promise(resolve => setTimeout(resolve, 2000))
  }

  // 3. Retrieve email
  const emailResponse = await fetch(
    `http://localhost:8000/api/email/${email_id}`,
    { headers: { 'Authorization': `Bearer ${token}` } }
  )

  const email = await emailResponse.json()
  console.log(`Email generated:\n${email.email_message}`)

  return email
}
```

---

## Interactive API Docs

Visit **http://localhost:8000/docs** for:

- Interactive Swagger UI
- Try endpoints directly from browser
- View request/response schemas
- Copy curl commands
- Test authentication

---

## Further Reading

- **Quick Start**: [QUICKSTART.MD](QUICKSTART.MD) - Get running in 5 minutes
- **Architecture**: [ARCHITECTURE.MD](ARCHITECTURE.MD) - System design and deployment
- **Pipeline**: [PIPELINE.MD](PIPELINE.MD) - 4-step pipeline deep dive
- **Development**: [DEVELOPMENT.MD](DEVELOPMENT.MD) - Dev workflows and testing

---

*Last updated: 2025-01-24*
