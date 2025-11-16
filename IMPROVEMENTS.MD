# Scribe - Code Quality Improvements

> Comprehensive review and recommendations for the Scribe codebase

UPDATE THIS DOCUMENT WITH THE FOLLOWING:
1. Will be using pydantic agents for the backend with a pipeline with the following steps: template_parser, web_scraper, arxiv_enricher, email_composer
2. Have an ENUM for the type of email template that the user passes in. It should be either RESEARCH, BOOK, or GENERAL. RESEARCH is for when the user wants to mention research papers that the professor has written in the final email. BOOK is for when the user wants to mention books that the professor has written in the final email. GENERAL is for when the user wants to mention general information about the professor in the final email.
3. Using production level architecture, update the document with the new layout and plan to integrate logfire, pydantic agents, pipeline, and celery workers.
4. 

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Development Workflow with Makefile](#development-workflow-with-makefile)
4. [Frontend Improvements](#frontend-improvements)
5. [Backend Improvements](#backend-improvements)
6. [Security & Environment](#security-environment)
7. [Type System](#type-system)
8. [Project Structure](#project-structure)
9. [Prioritized Action Plan](#action-plan)

---

## Executive Summary

**Project:** Scribe - Cold email generation platform for research outreach

**Tech Stack:**
- **Frontend:** Next.js 15, React 19, TypeScript, Tailwind CSS, shadcn/ui
- **Backend:** Python 3.13, FastAPI, Celery, Pydantic Agents
- **Database:** Supabase/PostgreSQL (users + emails only)
- **Authentication:** Supabase Auth with JWT validation
- **Task Queue:** Celery with Redis broker
- **Observability:** Logfire (spans, events, metrics)
- **AI:** Anthropic Claude API

**Overall Assessment:** Transitioning from functional MVP to production-grade system with stateless pipeline architecture, async task processing, and comprehensive observability.

**Key Areas for Improvement:**
- Frontend: State management, error boundaries, type safety
- Backend: **Pydantic agent pipeline**, async task processing, Logfire integration
- Architecture: **Stateless design** - no intermediate DB writes, Celery for job orchestration
- Observability: Centralized logging and monitoring via Logfire
- Shared: Security (environment variables), centralized type definitions

---

## Architecture Overview

### Stateless Pipeline Architecture

**The email generation system uses a 4-step Pydantic agent pipeline with stateless execution:**

```
┌────────────────────────────────────────────────────────────────────┐
│              Stateless Pipeline (In-Memory Execution)              │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Client Request                                                    │
│       ↓                                                            │
│  POST /api/email/generate                                          │
│       ↓                                                            │
│  Celery Task Enqueued → Returns task_id                           │
│       ↓                                                            │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │          PipelineData (In-Memory State)                      │ │
│  ├──────────────────────────────────────────────────────────────┤ │
│  │                                                              │ │
│  │  Step 1: Template Parser (Pydantic Agent)                   │ │
│  │  ├─ Input: email_template, recipient_info, template_type    │ │
│  │  ├─ Process: Anthropic Claude extracts search terms         │ │
│  │  └─ Output: PipelineData.search_terms ✓                     │ │
│  │                                                              │ │
│  │  Step 2: Web Scraper (Pydantic Agent)                       │ │
│  │  ├─ Input: PipelineData.search_terms                        │ │
│  │  ├─ Process: Google Custom Search + BeautifulSoup scraping  │ │
│  │  └─ Output: PipelineData.scraped_content ✓                  │ │
│  │                                                              │ │
│  │  Step 3: ArXiv Enricher (Pydantic Agent)                    │ │
│  │  ├─ Input: recipient_name, template_type                    │ │
│  │  ├─ Process: Fetch papers if template_type == RESEARCH      │ │
│  │  └─ Output: PipelineData.arxiv_papers ✓ (conditional)       │ │
│  │                                                              │ │
│  │  Step 4: Email Composer (Pydantic Agent)                    │ │
│  │  ├─ Input: All PipelineData fields                          │ │
│  │  ├─ Process: Anthropic Claude composes personalized email   │ │
│  │  ├─ Validation: Check quality, publication mentions         │ │
│  │  └─ Output: Write to emails table in database ✓✓           │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│       ↓                                                            │
│  Returns email_id                                                  │
│       ↓                                                            │
│  Client polls: GET /api/email/status/{task_id}                    │
│       ↓                                                            │
│  Celery state: PENDING → STARTED → SUCCESS                        │
│       ↓                                                            │
│  Client fetches: GET /api/email/{email_id}                        │
│                                                                    │
│  All Progress/Errors → Logfire (NOT database)                     │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**Email Template Types (Enum):**
- `RESEARCH`: Mentions research papers the professor has written
- `BOOK`: Mentions books the professor has written
- `GENERAL`: General information about the professor

**Key Design Principles:**
- ✅ **Stateless Execution**: Pipeline state lives in `PipelineData` object (in-memory)
- ✅ **Single DB Write**: Only Step 4 (EmailComposer) writes to `emails` table
- ✅ **Celery for Orchestration**: Task queue handles job lifecycle, Redis stores task state
- ✅ **Logfire for Observability**: All progress, timing, errors → Logfire (not database)
- ✅ **Pydantic Validation**: Every step input/output validated with Pydantic models
- ✅ **Async Everything**: FastAPI endpoints, Celery tasks, pipeline steps all async

**Benefits:**
- 🚀 **Scalability**: Horizontal scaling of Celery workers, no database bottleneck
- 🧹 **Simplicity**: Only 2 database tables (users, emails) - clean schema
- 📊 **Observability**: Rich context in Logfire spans without database writes
- ⚡ **Performance**: No intermediate database I/O, all operations in-memory
- 🔄 **Reliability**: Celery handles retries, Logfire captures all execution details

---

### Backend-First Architecture

**This application follows a BACKEND-FIRST architecture:**

- ✅ **Frontend**: Only uses Supabase for authentication (OAuth, JWT)
- ✅ **Backend**: Handles ALL database operations with Supabase service role key
- ✅ **Security**: Backend validates JWT tokens and extracts user ID
- ✅ **No Direct Database Access**: Frontend NEVER queries Supabase database directly
- ✅ **API Communication**: All data flows through authenticated backend API endpoints

```
┌──────────────────────────────────────────────────────────────────┐
│                        Scribe Application                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────┐                                        │
│  │  Frontend            │                                        │
│  │  Next.js + React     │                                        │
│  └──────────┬───────────┘                                        │
│             │                                                    │
│             │ Auth Only                                          │
│             │              ┌──────────────────────┐              │
│             └─────────────▶│  Supabase Auth       │              │
│                            │  (Authentication)    │              │
│             ┌─────────────▶│                      │              │
│             │              └──────────────────────┘              │
│             │ All Data                                           │
│             │ Operations                                         │
│             │                                                    │
│             ▼                                                    │
│  ┌──────────────────────┐         ┌──────────────────────┐       │
│  │  Backend API         │────────▶│  Supabase Database   │       │
│  │  Python + FastAPI    │  Auth   │  PostgreSQL          │       │
│  │                      │  Token  │                      │       │
│  │  - Validates JWT     │         │  - Row Level         │       │
│  │  - Database ops      │         │    Security (RLS)    │       │
│  │  - Business logic    │         │  - Tables & indexes  │       │
│  └──────────────────────┘         └──────────────────────┘       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Responsibilities

**Frontend:**
- UI components and layouts
- Client-side state management
- Form validation and user interactions
- Supabase Auth integration (sign-in, sign-out, session management)
- API calls to backend for all data operations

**Backend:**
- JWT token validation
- All database operations (CRUD via Supabase client)
- Business logic and validation
- API endpoints
- Email generation service

---

## Key Architectural Improvements Implemented

### Two-Tier Summarization Architecture (Web Scraper Step)

**Problem:** Direct summarization of large web content (>30K characters) can lead to information loss and hallucinations.

**Solution:** Implemented intelligent two-tier summarization with batch processing:

```
Content ≤30K chars:
└─> Direct Summarization (Haiku) → Final Output

Content >30K chars:
├─> Step 1: Split into 30K-char chunks (sentence-aware splitting)
├─> Step 2: Batch Summarization (Haiku) for each chunk
│   └─> Extraction focus: preserve ALL facts, add [PAGE X] markers
├─> Step 3: Combine batch summaries with markers
└─> Step 4: Final Synthesis (Sonnet + Chain-of-Thought)
    └─> Multi-source verification, relevance filtering, structured output
```

**Model Selection Strategy:**
- **Haiku 4.5**: Fast extraction, batch processing, deterministic (temp 0.0)
- **Sonnet 4.5**: High-quality synthesis, Chain-of-Thought reasoning, factual (temp 0.2)

**Anti-Hallucination Safeguards:**
- Uncertainty markers: `[UNCERTAIN]`, `[SINGLE SOURCE]`
- Multi-source confirmation requirement
- Verbatim extraction from sources
- "If not found, state 'Not found in sources'" policy

**Benefits:**
- ✅ No information loss for large content
- ✅ Maintains source attribution throughout
- ✅ Cost-effective (Haiku for bulk processing)
- ✅ High quality final output (Sonnet synthesis)
- ✅ Prevents hallucinations through verification

**Implementation Location:** `pipeline/steps/web_scraper/main.py:_summarize_content()`

---

### Playwright Integration for JavaScript Support

**Migration:** httpx (static HTML) → Playwright (headless browser)

**Why:** Modern academic websites rely heavily on JavaScript rendering

**Features:**
- Headless Chromium browser with full JavaScript support
- Isolated browser contexts per URL (prevent cross-contamination)
- Network idle waiting (ensures all content loaded)
- Semaphore-based concurrency control (max 2 concurrent)
- Automatic cleanup with context managers

**Production Considerations:**
- ~300MB browser binaries (requires `playwright install chromium`)
- Container-safe with `--no-sandbox` flag
- Memory footprint monitoring required on Render

**Implementation Location:** `pipeline/steps/web_scraper/utils.py:scrape_url()`

---

### ArXiv Relevance Scoring Algorithm

**Four-Factor Scoring System:**

1. **Author Match (0.4 weight):** Is recipient an author?
2. **Topic Match (0.3 weight):** Abstract mentions research interest?
3. **Recency (0.2 weight):** Papers from last 5 years score higher
4. **Primary Author (0.1 weight):** Bonus if recipient is first author

**Formula:**
```python
score = (author_match * 0.4) + (topic_score * 0.3) + (recency * 0.2) + (primary_author * 0.1)
```

**Conditional Execution:**
- Only runs for `template_type == RESEARCH`
- Non-fatal if ArXiv search fails (continues pipeline)
- Returns top 5 most relevant papers

**Implementation Location:** `pipeline/steps/arxiv_helper/utils.py:calculate_relevance_score()`

---

### Pydantic-AI Agent Integration

**Unified LLM Interface Pattern:**

Created `utils/llm_agent.py:create_agent()` factory function for all Anthropic Claude calls:

**Benefits:**
- ✅ Automatic Logfire instrumentation (prompts, responses, tokens, cost, latency)
- ✅ Built-in retry logic with exponential backoff
- ✅ Structured output validation via Pydantic models
- ✅ Consistent error handling across all steps
- ✅ Temperature and token configuration per agent

**Usage Pattern:**
```python
# Template Parser - structured extraction
agent = create_agent(
    model="anthropic:claude-haiku-4-5",
    output_type=TemplateAnalysis,  # Pydantic model
    temperature=0.1,  # Deterministic
    max_tokens=2000,
    retries=2
)

# Email Composer - creative writing
agent = create_agent(
    model="anthropic:claude-sonnet-4-5-20250929",
    temperature=0.7,  # Creative
    max_tokens=2000,
    retries=1
)
```

**Implementation Location:** `utils/llm_agent.py`

---

### Email Validation with Retry Logic

**Three-Attempt Validation System:**

1. Generate email with Claude
2. Validate quality:
   - Length checks (50-10,000 chars)
   - Placeholder detection (`{{...}}`, `[...]`)
   - Recipient name verification
   - Publication mentions (for RESEARCH template)
   - Generic phrase detection ("your work", "your research")
3. If invalid and attempts < 3: regenerate
4. If attempts exhausted: use last attempt with warnings

**Validation Result Metadata:**
```python
class EmailValidationResult:
    is_valid: bool
    issues: List[str]  # Fatal problems
    warnings: List[str]  # Non-fatal concerns
    mentions_publications: bool
    has_placeholders: bool
    word_count: int
```

**Implementation Location:** `pipeline/steps/email_composer/utils.py:validate_email()`

---

### Smart Chunking Algorithm

**Sentence-Boundary-Aware Splitting:**

**Goal:** Split large content without breaking mid-sentence

**Algorithm:**
1. Try to split at `chunk_size` (30,000 chars)
2. Look backward up to 500 chars for sentence boundary (`.`, `!`, `?`, `\n\n`)
3. If no boundary found, split at word boundary (last space)
4. If still no boundary, hard split at `chunk_size`

**Priority of Split Points:**
```python
sentence_endings = ['\n\n', '. ', '.\n', '! ', '!\n', '? ', '?\n']
```

**Benefits:**
- ✅ Preserves semantic meaning
- ✅ Prevents incomplete sentences
- ✅ Improves batch summarization quality

**Implementation Location:** `pipeline/steps/web_scraper/main.py:_split_into_chunks()`

---

### Production-Ready Error Handling

**Three-Level Error Strategy:**

1. **Step-Level Errors:**
   - Caught by `BasePipelineStep.execute()`
   - Logged to Logfire with full context
   - Propagated to PipelineRunner

2. **Pipeline-Level Errors:**
   - Caught by `PipelineRunner.run()`
   - Logged with task_id correlation
   - Returned to Celery task

3. **External API Errors:**
   - Retry logic with exponential backoff
   - Graceful degradation (e.g., ArXiv fails → continue without papers)
   - Detailed error logging for debugging

**Non-Fatal Failures:**
- ArXiv search failure → empty papers list
- Some URLs fail to scrape → continue with successful ones
- Validation warnings → email still generated with metadata

**Implementation Locations:**
- `pipeline/core/runner.py:BasePipelineStep.execute()`
- `pipeline/core/runner.py:PipelineRunner.run()`

---

### Stateless Design Benefits Realized

**Zero Intermediate Database Writes:**
- ✅ All pipeline state in-memory (`PipelineData` object)
- ✅ Single database write at end (Step 4: EmailComposer)
- ✅ No job tracking tables needed (Celery provides this)
- ✅ Horizontally scalable Celery workers

**Performance Impact:**
- 🚀 Faster execution (no DB I/O during pipeline)
- 🚀 Lower database load (1 write per job instead of 4+)
- 🚀 Better observability (Logfire instead of DB queries)

**Simplified Schema:**
```sql
-- Only 2 tables needed:
users (id, email, display_name, generation_count)
emails (id, user_id, recipient_name, recipient_interest, email_message, template_type, metadata)
```

**Implementation Location:** `pipeline/models/core.py:PipelineData`

---

### Overview

The project now includes a comprehensive **Makefile** that streamlines all common development tasks. This replaces manual command execution and provides a consistent interface for running services, managing databases, and performing maintenance.

### Quick Start

```bash
# 1. Start Redis (required for Celery)
make redis-start

# 2. Start FastAPI server + Celery worker together
make serve
```

That's it! Your development environment is now running.

### Available Commands

#### **Server & Worker Management**

```bash
make serve              # Start FastAPI + Celery worker (most common command)
make run                # Alias for serve
make celery-worker      # Start Celery worker only
make flower             # Start Flower monitoring UI at http://localhost:5555
make stop-all           # Stop all processes (uvicorn, celery, flower)
```

---

## Frontend Improvements

### 1. State Management

**Current Issues:**
- Firebase config deleted - application broken
- Need to migrate to Supabase Auth
- Need to migrate all database operations to backend API endpoints
- Type safety problems (`any` types)
- localStorage management scattered

**Solution: Supabase Auth + API Client**

#### Setup Supabase Auth (Frontend)

**Create `config/supabase.ts`:**
```typescript
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables');
}

// Frontend client - ONLY for authentication
export const supabaseAuth = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
  },
});
```

**Frontend `.env.local`:**
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key_here
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

#### Create Auth Service

**Create `services/auth.service.ts`:**
```typescript
import { supabaseAuth } from '@/config/supabase';
import type { User } from '@supabase/supabase-js';

class AuthService {
  async signInWithGoogle() {
    const { data, error } = await supabaseAuth.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/dashboard`,
      },
    });
    if (error) throw error;
    return data;
  }

  async signOut() {
    const { error } = await supabaseAuth.auth.signOut();
    if (error) throw error;
  }

  async getSession() {
    const { data, error } = await supabaseAuth.auth.getSession();
    if (error) throw error;
    return data.session;
  }

  onAuthStateChange(callback: (user: User | null) => void) {
    return supabaseAuth.auth.onAuthStateChange((event, session) => {
      callback(session?.user ?? null);
    });
  }

  async getAuthToken(): Promise<string | null> {
    const { data: { session } } = await supabaseAuth.auth.getSession();
    return session?.access_token ?? null;
  }
}

export const authService = new AuthService();
```

#### Create API Client

**Create `services/api.ts`:**
```typescript
import { authService } from './auth.service';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export interface ApiError {
  message: string;
  status: number;
  details?: any;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async getHeaders(): Promise<HeadersInit> {
    const token = await authService.getAuthToken();
    return {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
    };
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const error: ApiError = {
        message: response.statusText,
        status: response.status,
      };
      try {
        const errorData = await response.json();
        error.details = errorData;
        error.message = errorData.message || error.message;
      } catch {}
      throw error;
    }
    return response.json();
  }

  async get<T>(endpoint: string, params?: Record<string, string>): Promise<T> {
    const url = new URL(`${this.baseUrl}${endpoint}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        url.searchParams.append(key, value);
      });
    }
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: await this.getHeaders(),
    });
    return this.handleResponse<T>(response);
  }

  async post<T>(endpoint: string, body: any): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers: await this.getHeaders(),
      body: JSON.stringify(body),
    });
    return this.handleResponse<T>(response);
  }

  async delete<T>(endpoint: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'DELETE',
      headers: await this.getHeaders(),
    });
    return this.handleResponse<T>(response);
  }
}

export const apiClient = new ApiClient(API_BASE_URL);

export const API_ENDPOINTS = {
  initUser: '/api/user/init',
  getUser: '/api/user/profile',
  getEmails: '/api/user/emails',
  generateEmail: '/api/generate-email',
  callOpenAI: '/api/call-openai',
} as const;
```

### 2. Custom Hooks

**Create `hooks/useAuth.ts`:**
```typescript
import { useState, useEffect } from 'react';
import { authService } from '@/services/auth.service';
import type { User } from '@supabase/supabase-js';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Get initial session
    authService.getSession().then(session => {
      setUser(session?.user ?? null);
      setLoading(false);
    });

    // Listen for auth changes
    const { data: { subscription } } = authService.onAuthStateChange(setUser);

    return () => subscription.unsubscribe();
  }, []);

  return {
    user,
    loading,
    isAuthenticated: !!user,
    signInWithGoogle: authService.signInWithGoogle,
    signOut: authService.signOut,
  };
}
```

**Create `hooks/useEmailHistory.ts`:**
```typescript
import { useState, useEffect } from 'react';
import { apiClient, API_ENDPOINTS } from '@/services/api';
import type { Email } from '@/types';

export function useEmailHistory() {
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEmails = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiClient.get<Email[]>(API_ENDPOINTS.getEmails);
      setEmails(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch emails');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEmails();
  }, []);

  return { emails, loading, error, refetch: fetchEmails };
}
```

### 3. Error Boundaries

**Create `components/shared/ErrorBoundary.tsx`:**
```typescript
"use client";

import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-center">
            <h2 className="text-2xl font-bold mb-4">Something went wrong</h2>
            <p className="text-gray-600 mb-4">{this.state.error?.message}</p>
            <button
              onClick={() => this.setState({ hasError: false })}
              className="px-4 py-2 bg-blue-500 text-white rounded"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
```

**Add to `app/layout.tsx`:**
```typescript
<ErrorBoundary>
  <AuthContextProvider>
    {children}
  </AuthContextProvider>
</ErrorBoundary>
```

---

## Backend Improvements

### 1. Production Pipeline Architecture

**Pydantic Agent Pattern:**

Each pipeline step follows the `BasePipelineStep` pattern:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import logfire

@dataclass
class StepResult:
    success: bool
    error: Optional[str] = None
    metadata: Optional[dict] = None

class BasePipelineStep(ABC):
    """Base class for all pipeline steps"""

    def __init__(self, step_name: str):
        self.step_name = step_name

    async def execute(self, pipeline_data: PipelineData) -> StepResult:
        """Execute with Logfire observability"""
        with logfire.span(f"pipeline.{self.step_name}", task_id=pipeline_data.task_id):
            try:
                logfire.info(f"{self.step_name} started")
                result = await self._execute_step(pipeline_data)
                logfire.info(f"{self.step_name} completed", success=result.success)
                return result
            except Exception as e:
                logfire.error(f"{self.step_name} failed", error=str(e), exc_info=True)
                raise

    @abstractmethod
    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """Step-specific logic - implemented by each agent"""
        pass
```

**PipelineData Structure (In-Memory State):**

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

class TemplateType(str, Enum):
    RESEARCH = "research"
    BOOK = "book"
    GENERAL = "general"

@dataclass
class PipelineData:
    """Shared state passed between all pipeline steps"""

    # Input data
    task_id: str
    user_id: str
    email_template: str
    recipient_name: str
    recipient_interest: str
    template_type: TemplateType

    # Step 1 outputs (TemplateParser)
    search_terms: List[str] = field(default_factory=list)

    # Step 2 outputs (WebScraper)
    scraped_content: Optional[str] = None
    scraped_urls: List[str] = field(default_factory=list)

    # Step 3 outputs (ArxivEnricher) - conditional
    arxiv_papers: List[Dict[str, Any]] = field(default_factory=list)

    # Step 4 outputs (EmailComposer)
    final_email: Optional[str] = None

    # Metadata for final DB write
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Transient data (logged to Logfire, not DB)
    step_timings: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
```

**Pipeline Runner:**

```python
class PipelineRunner:
    """Orchestrates the 4-step pipeline"""

    def __init__(self):
        self.steps = [
            TemplateParserStep(),
            WebScraperStep(),
            ArxivEnricherStep(),
            EmailComposerStep()
        ]

    async def run(self, pipeline_data: PipelineData) -> str:
        """
        Execute all steps sequentially.
        Returns email_id from final step.
        """
        with logfire.span("pipeline.full_run", task_id=pipeline_data.task_id):
            for step in self.steps:
                result = await step.execute(pipeline_data)
                if not result.success:
                    raise PipelineExecutionError(result.error)

            # Return email_id set by EmailComposer
            return pipeline_data.metadata["email_id"]
```

---

### 2. Celery Task Queue Integration

**Celery Configuration:**

```python
# celery_config.py
from celery import Celery
from kombu import Queue, Exchange

celery_app = Celery(
    "scribe",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1"
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "tasks.generate_email": {
            "queue": "email_high",
            "routing_key": "email.high"
        }
    },
    task_queues=(
        Queue("email_high", Exchange("email"), routing_key="email.high"),
        Queue("email_default", Exchange("email"), routing_key="email.default"),
    )
)
```

**Task Definition:**

```python
# celery_tasks/pipeline.py
from celery_config import celery_app
from pipeline.core.runner import PipelineRunner
import logfire

@celery_app.task(bind=True, max_retries=3)
async def generate_email_task(self, input_data: dict):
    """
    Async Celery task for email generation.
    Returns email_id when complete.
    """
    task_id = self.request.id

    with logfire.span("celery.generate_email", task_id=task_id):
        try:
            # Create in-memory pipeline data
            pipeline_data = PipelineData(
                task_id=task_id,
                user_id=input_data["user_id"],
                email_template=input_data["email_template"],
                recipient_name=input_data["recipient_name"],
                recipient_interest=input_data["recipient_interest"],
                template_type=TemplateType(input_data["template_type"])
            )

            # Run pipeline
            runner = PipelineRunner()
            email_id = await runner.run(pipeline_data)

            logfire.info("Pipeline completed", task_id=task_id, email_id=email_id)

            return {"email_id": email_id, "status": "completed"}

        except Exception as e:
            logfire.error("Pipeline failed", task_id=task_id, error=str(e))
            # Retry with exponential backoff
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
```

---

### 3. Logfire Observability

**What Goes to Logfire:**
- ✅ Pipeline execution spans (full run + each step)
- ✅ Step timings and performance metrics
- ✅ Progress events (step started/completed)
- ✅ Errors with full context and stack traces
- ✅ External API calls (Anthropic, Google, ArXiv)
- ✅ Validation failures and retries

**What Does NOT Go to Database:**
- ❌ Job status/progress (use Celery task state)
- ❌ Step outputs (in-memory only)
- ❌ Error messages (Logfire only)
- ❌ Timing data (Logfire metrics)

**Logfire Configuration:**

```python
# observability/logfire_config.py
import logfire
from logfire.integrations.fastapi import LogfireMiddleware

# Initialize Logfire
logfire.configure(
    service_name="scribe-pipeline",
    environment="production",
    send_to_logfire=True
)

# Add to FastAPI app
app.add_middleware(LogfireMiddleware)
```

---

### 4. Simplified API Endpoints

**No database job tracking - use Celery task_id:**

```python
# api/routes/email.py
from fastapi import APIRouter, Depends
from celery.result import AsyncResult
from celery_tasks.pipeline import generate_email_task

router = APIRouter(prefix="/api/email", tags=["Email Generation"])

@router.post("/generate")
async def generate_email(
    request: GenerateEmailRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Enqueue email generation job.
    Returns Celery task_id for status polling.
    """
    task = generate_email_task.apply_async(
        kwargs={
            "user_id": str(current_user.id),
            "email_template": request.email_template,
            "recipient_name": request.recipient_name,
            "recipient_interest": request.recipient_interest,
            "template_type": request.template_type
        },
        queue="email_high"
    )

    logfire.info("Task enqueued", task_id=task.id, user_id=str(current_user.id))

    return {"task_id": task.id}

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Check Celery task state (from Redis backend).
    States: PENDING, STARTED, SUCCESS, FAILURE
    """
    result = AsyncResult(task_id, app=celery_app)

    return {
        "task_id": task_id,
        "status": result.state,
        "result": result.result if result.ready() else None,
        "error": str(result.info) if result.failed() else None
    }

@router.get("/{email_id}")
async def get_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch final email from database"""
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(404, "Email not found")

    return EmailResponse.from_orm(email)
```

---

### 5. Database Schema (Simplified - Only 2 Tables)

**No pipeline_jobs table needed - Celery handles job state:**

```sql
-- Users table (existing)
CREATE TABLE users (
  id UUID REFERENCES auth.users PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  display_name TEXT,
  generation_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Emails table (only table written to by pipeline)
CREATE TABLE emails (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  recipient_name TEXT NOT NULL,
  recipient_interest TEXT NOT NULL,
  email_message TEXT NOT NULL,
  template_type VARCHAR(20) NOT NULL,  -- NEW: RESEARCH, BOOK, GENERAL
  metadata JSONB,                       -- NEW: papers used, sources, timing
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_emails_user_id ON emails(user_id);
CREATE INDEX idx_emails_created_at ON emails(created_at DESC);
CREATE INDEX idx_emails_template_type ON emails(template_type);

-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Backend can manage users" ON users
  FOR ALL USING (auth.role() = 'service_role' OR auth.uid() = id);

CREATE POLICY "Backend can manage emails" ON emails
  FOR ALL USING (auth.role() = 'service_role' OR auth.uid() = user_id);
```

**Migration to Add New Columns:**

```sql
-- Add template_type and metadata columns to existing emails table
ALTER TABLE emails
  ADD COLUMN template_type VARCHAR(20),
  ADD COLUMN metadata JSONB;

-- Create index for new template_type column
CREATE INDEX idx_emails_template_type ON emails(template_type);
```

---

## Security & Environment

### Frontend Environment (.env.local)

```env
# Supabase Auth (public - safe to expose)
# Modern Supabase API (2024+) - uses anon/publishable key for client-side auth
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key_here

# Backend API
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### Backend Environment (.env)

```env
# Supabase (Backend) - Modern API (2024+)
# Only need URL and service role key - JWT verification handled automatically via JWKS
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here

# Celery & Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Logfire Observability
LOGFIRE_TOKEN=your_logfire_token_here
LOGFIRE_ENVIRONMENT=production

# AI APIs
ANTHROPIC_API_KEY=your_anthropic_api_key  # Primary AI for email generation
GOOGLE_API_KEY=your_google_api_key        # For Custom Search
GOOGLE_CSE_ID=your_google_cse_id          # Custom Search Engine ID

# Application
ENVIRONMENT=development
DATABASE_URL=postgresql://user:pass@localhost:5432/scribe  # Auto-constructed by settings.py

# Pipeline Configuration
PIPELINE_MAX_RETRIES=3
PIPELINE_TIMEOUT=300  # seconds
```

**Security Best Practices:**
- ✅ Frontend uses publishable key (limited permissions, new system)
- ✅ Backend uses service role key (full permissions)
- ✅ Backend validates JWT tokens
- ✅ Never trust user ID from request body
- ✅ All sensitive credentials in `.env` files (gitignored)

---

## Type System

### Centralized Type Definitions

**`types/user.ts`:**
```typescript
export interface User {
  id: string;
  email: string;
  displayName: string | null;
  generationCount: number;
  createdAt: string;
}

export interface AuthContextType {
  user: User | null;
  loading: boolean;
  signOut: () => Promise<void>;
}
```

**`types/email.ts`:**
```typescript
export type EmailStatus = 'pending' | 'completed' | 'failed';

export interface Email {
  id: string;
  userId: string;
  recipientName: string;
  recipientInterest: string;
  emailMessage: string;
  createdAt: string;
}

export interface GenerationQueueItem {
  id: string;
  name: string;
  interest: string;
  status: EmailStatus;
}
```

**`types/api.ts`:**
```typescript
export interface GenerateEmailRequest {
  emailTemplate: string;
  name: string;
  interest: string;
}

export interface GenerateEmailResponse {
  email: string;
  success: boolean;
  error?: string;
}

export interface OpenAITemplateRequest {
  prompt: string;
}

export interface OpenAITemplateResponse {
  template: string;
}

export interface APIError {
  message: string;
  code?: string;
  status?: number;
  details?: any;
}
```

**`types/index.ts`:**
```typescript
export * from './user';
export * from './email';
export * from './api';
```

---

## Project Structure

```
/scribe
├── app/                        # Next.js App Router
│   ├── (auth)/                # Auth pages
│   │   └── page.tsx           # Login
│   ├── (dashboard)/           # Protected pages
│   │   ├── layout.tsx         # Dashboard layout
│   │   ├── page.tsx           # Main dashboard
│   │   ├── generate/          # Email generation
│   │   └── template/          # Template generation
│   ├── layout.tsx             # Root layout
│   ├── error.tsx              # Error handler
│   └── loading.tsx            # Loading state
│
├── components/
│   ├── ui/                    # shadcn components
│   ├── features/              # Feature components
│   │   ├── email/
│   │   └── auth/
│   ├── layout/                # Layout components
│   │   ├── Navbar.tsx
│   │   └── Header.tsx
│   └── shared/                # Shared components
│       ├── ErrorBoundary.tsx
│       └── ProtectedRoute.tsx
│
├── hooks/                     # Custom hooks
│   ├── useAuth.ts            # Auth state
│   ├── useUser.ts            # User profile
│   └── useEmailHistory.ts    # Email history
│
├── context/                   # React Context
│   ├── AuthContextProvider.tsx
│   └── EmailGenerationProvider.tsx
│
├── services/                  # API services
│   ├── api.ts                # Backend API client
│   ├── auth.service.ts       # Supabase Auth
│   └── index.ts
│
├── lib/                       # Utilities
│   ├── utils.ts              # General utilities
│   ├── validation.ts         # Form validation
│   ├── constants.ts          # App constants
│   └── errors.ts             # Error handling
│
├── types/                     # TypeScript types
│   ├── index.ts
│   ├── user.ts
│   ├── email.ts
│   └── api.ts
│
├── config/                    # Configuration
│   ├── supabase.ts           # Supabase client
│   └── constants.ts
│
├── .env.local                 # Environment variables
├── .env.example               # Example env file
└── package.json
```

---

## Prioritized Action Plan

**Migration from Legacy Flask to Production Pydantic Pipeline**

### Phase 0: Infrastructure Setup (Week 1)

**Celery + Redis + Logfire**
- [ ] Install Redis locally and configure for development
- [ ] Set up Celery with email_high and email_default queues
- [ ] Create Logfire account and configure token
- [ ] Update `.env` with all new environment variables
- [ ] Test Celery worker can start and connect to Redis
- [ ] Verify Logfire integration with FastAPI middleware

**Database Migration**
- [ ] Run migration to add `template_type` and `metadata` columns to emails table
- [ ] Create indexes for new columns
- [ ] Test backward compatibility with existing emails

---

### Phase 1: Core Pipeline Infrastructure (Week 1-2)

**Pydantic Models & Base Classes**
- [ ] Create `pipeline/models/core.py` with TemplateType enum
- [ ] Implement `PipelineData` dataclass with all step fields
- [ ] Create `StepResult` dataclass for validation
- [ ] Write unit tests for data models

**BasePipelineStep**
- [ ] Implement `pipeline/core/runner.py` with BasePipelineStep abstract class
- [ ] Add Logfire span integration in execute() method
- [ ] Implement error handling and retry logic
- [ ] Create PipelineRunner class for orchestration
- [ ] Write tests for BasePipelineStep pattern

---

### Phase 2: Pipeline Steps Implementation (Week 2-3)

**Step 1: Template Parser**
- [ ] Create `pipeline/steps/template_parser/main.py`
- [ ] Migrate to Anthropic Claude API (replace OpenAI)
- [ ] Implement prompt for extracting search terms
- [ ] Create Pydantic models for input/output validation
- [ ] Write unit tests with mocked Anthropic responses

**Step 2: Web Scraper**
- [ ] Create `pipeline/steps/web_scraper/main.py`
- [ ] Migrate `scrape_professor_publications()` from legacy code
- [ ] Refactor to async with `httpx` (replace `requests`)
- [ ] Move `google_search()` and `scrape_website_text()` to utils
- [ ] Add rate limiting and retry logic
- [ ] Write integration tests

**Step 3: ArXiv Enricher**
- [ ] Create `pipeline/steps/arxiv_enricher/main.py`
- [ ] Implement conditional execution based on template_type
- [ ] Integrate ArXiv API with httpx
- [ ] Add paper relevance scoring
- [ ] Create Pydantic models for ArxivPaper
- [ ] Write tests with mocked ArXiv responses

**Step 4: Email Composer**
- [ ] Create `pipeline/steps/email_composer/main.py`
- [ ] Migrate email composition logic from `final_together()`
- [ ] Implement Anthropic Claude for final email generation
- [ ] Add email validation (check for publications, quality)
- [ ] **Implement database write to emails table**
- [ ] Create Pydantic models for composed email
- [ ] Write integration tests with database

---

### Phase 3: Celery Integration (Week 4)

**Task Definitions**
- [ ] Create `celery_tasks/pipeline.py` with generate_email_task
- [ ] Implement task with bind=True for self-awareness
- [ ] Add retry logic with exponential backoff
- [ ] Test task execution end-to-end
- [ ] Verify email_id is returned on success

**Worker Configuration**
- [ ] Create worker startup script
- [ ] Configure concurrency and prefetch settings
- [ ] Test queue routing (email_high vs email_default)
- [ ] Set up worker monitoring

---

### Phase 4: FastAPI Endpoints (Week 4-5)

**API Routes**
- [ ] Create `api/routes/email.py` with new endpoints
- [ ] Implement `POST /api/email/generate` (returns task_id)
- [ ] Implement `GET /api/email/status/{task_id}` (Celery state)
- [ ] Implement `GET /api/email/{email_id}` (fetch from DB)
- [ ] Add Pydantic schemas for request/response validation
- [ ] Write API integration tests

**Legacy Deprecation**
- [ ] Mark legacy `/generate-email` endpoint as deprecated
- [ ] Add migration notice in API docs
- [ ] Test dual operation period (old and new endpoints)

---

### Phase 5: Observability & Monitoring (Week 5-6)

**Logfire Dashboards**
- [ ] Create dashboard for pipeline execution metrics
- [ ] Set up alerts for pipeline failures
- [ ] Add custom metrics (duration by template_type)
- [ ] Monitor Celery queue depth

**Testing & Validation**
- [ ] End-to-end tests: API → Celery → Pipeline → DB
- [ ] Load testing with multiple concurrent tasks
- [ ] Error scenario testing (API failures, timeouts)
- [ ] Verify Logfire captures all execution details

---

### Phase 6: Production Deployment (Week 6-7)

**Infrastructure**
- [ ] Deploy Redis to production
- [ ] Deploy Celery workers (separate containers)
- [ ] Configure production Logfire environment
- [ ] Set up environment variables in production
- [ ] Test production pipeline end-to-end

**Documentation**
- [ ] Update API documentation with new endpoints
- [ ] Create runbook for Celery worker operations
- [ ] Document Logfire dashboard usage
- [ ] Write troubleshooting guide

---

### Phase 7: Legacy Deprecation (Week 8)

**Cleanup**
- [ ] Remove `api/legacy/app.py` completely
- [ ] Remove Flask dependencies from requirements.txt
- [ ] Remove old `/generate-email` endpoint
- [ ] Archive legacy code for reference

**Validation**
- [ ] Verify all users migrated to new system
- [ ] Check no production traffic to old endpoints
- [ ] Run final integration tests
- [ ] Monitor for issues

---

**Total Estimated Time:** 8 weeks (part-time) or 4 weeks (full-time)

**Critical Path:**
1. Infrastructure setup (Celery + Logfire) - blocking
2. Core pipeline classes - blocking
3. Step implementations - can be parallelized
4. Integration and testing - sequential

---

## Summary

### Key Improvements

1. **Stateless Pipeline Architecture**
   - In-memory PipelineData object (no intermediate DB writes)
   - Only final email written to database
   - Celery task_id for job tracking (no pipeline_jobs table)
   - Horizontal scalability with no database bottleneck

2. **Production-Grade Observability**
   - Logfire for all logging, metrics, and tracing
   - Span-based execution tracking per pipeline step
   - Real-time monitoring without database overhead
   - Rich error context and stack traces

3. **Async Task Processing**
   - Celery workers with priority queues (email_high)
   - Redis backend for task state management
   - Retry logic with exponential backoff
   - Self-aware tasks with correlation IDs

4. **Pydantic Agent Pattern**
   - BasePipelineStep abstract class for consistency
   - Validated input/output with Pydantic models
   - Clean separation of concerns per step
   - Testable and maintainable code

5. **Simplified Database Schema**
   - Only 2 tables: users and emails
   - No job tracking tables (Celery handles it)
   - Clean data model with metadata JSON field
   - Easy to maintain and query

### Architecture Benefits

**Scalability:**
- Celery workers scale horizontally
- No database write contention during pipeline execution
- Redis handles high-throughput job queuing

**Observability:**
- Logfire provides end-to-end visibility
- No need to query database for job status
- Real-time monitoring and alerting

**Maintainability:**
- Clean code with Pydantic validation
- Each pipeline step is independently testable
- Simple database schema

**Developer Experience:**
- Type-safe throughout (Pydantic + Python typing)
- Clear error messages and debugging via Logfire
- Easy to add new pipeline steps

### Next Steps

1. **Week 1**: Set up Celery, Redis, Logfire infrastructure
2. **Week 2-3**: Implement core pipeline and all 4 steps
3. **Week 4**: Integrate Celery tasks and FastAPI endpoints
4. **Week 5-6**: Testing, monitoring, and production deployment
5. **Week 7-8**: Legacy deprecation and cleanup

**This migration transforms your email generation system from a synchronous Flask MVP into a production-ready, observable, scalable async pipeline.** 🚀
