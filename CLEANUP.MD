# Code Quality Cleanup Plan

**Project**: Scribe - Cold Email Generation Platform
**Date**: 2025-11-19
**Audit Score**: 7.5/10 (Good foundation, needs cleanup)
**Total Cleanup Potential**: ~1,000 lines of dead code removal

---

## Executive Summary

This document outlines a comprehensive code quality improvement plan based on a systematic audit of the entire Scribe codebase. The plan is divided into 5 phases, prioritized by security impact, stability risk, and maintenance value.

**Key Metrics**:
- **Dead Code**: 867 lines
- **Security Issues**: 2 (already mitigated - API key revoked)
- **Architecture Improvements**: 4 critical patterns
- **Code Simplifications**: 8 opportunities
- **Best Practice Fixes**: 15+ instances

---

## Table of Contents

1. [Phase 1: Security & Dead Code Removal](#phase-1-security--dead-code-removal)
2. [Phase 2: Architecture Improvements](#phase-2-architecture-improvements)
3. [Phase 3: Code Simplification & DRY Principles](#phase-3-code-simplification--dry-principles)
4. [Phase 4: Best Practices & Code Quality](#phase-4-best-practices--code-quality)
5. [Phase 5: Testing & Validation](#phase-5-testing--validation)
6. [Risk Assessment](#risk-assessment)
7. [Rollback Strategy](#rollback-strategy)

---

## Phase 1: Security & Dead Code Removal

**Priority**: 🔴 CRITICAL
**Estimated Time**: 1 hour
**Risk Level**: Low (no dependencies)
**Impact**: High (security + -867 lines)

#### `pipeline/models/core.py:242-262` (20 lines)
```python
# DELETE THIS BLOCK:
# ===================================================================
# DEPRECATED CLASSES (Legacy - Will be removed in Phase 9)
# ===================================================================
#
# @dataclass
# class PipelineJob:
#     job_id: str
#     status: JobStatus
#     current_step: str = ""
#     ...
```

**Reasoning**: Commented code creates confusion and should be removed. If needed, it exists in git history.

**Risk**: ✅ **NONE** - Already deprecated and commented out

---

### 1.4 Remove Unused Imports

**File**: `models/user.py:7`
```python
# REMOVE THIS:
from typing import List  # Never used in file
```

**Verification**:
```bash
# Use flake8 or ruff to find unused imports
ruff check --select F401 .
```

**Risk**: ✅ **NONE** - No functional impact

---

## Phase 2: Architecture Improvements

**Priority**: 🟡 HIGH
**Estimated Time**: 2 hours
**Risk Level**: Medium (changes transaction behavior)
**Impact**: High (fixes anti-patterns)

### 2.1 Fix Database Context Manager Auto-Commit

**File**: `database/session.py:14-39`

**Current Code** (❌ ANTI-PATTERN):
```python
@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Database session context manager with auto-commit."""
    db = SessionLocal()
    try:
        yield db
        db.commit()  # ❌ AUTO-COMMITS - dangerous!
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

**Problems**:
1. **Violates Principle of Least Surprise**: Users expect explicit commit control
2. **Commits Read-Only Operations**: Even SELECT queries trigger commit
3. **Difficult to Debug**: Transaction boundaries unclear
4. **Can't Batch Operations**: Forces commit after every context block

**Example of Broken Behavior**:
```python
# User expects this to NOT commit anything:
with get_db_context() as db:
    user = db.query(User).first()  # Just reading
    # Oops! This commits an empty transaction

# User wants to batch multiple operations:
with get_db_context() as db:
    db.add(email1)
    # Can't validate before commit - already committed!
```

**Fixed Code** (✅ CORRECT):
```python
@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Database session context manager.

    Caller is responsible for calling db.commit() explicitly.
    Automatically rolls back on exception.

    Example:
        with get_db_context() as db:
            db.add(user)
            db.commit()  # Explicit commit
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

**Files to Update** (only 2 usages):

1. `pipeline/steps/email_composer/db_utils.py:91-100`
```python
# BEFORE:
with get_db_context() as db:
    user = db.query(User).filter(User.id == user_id).first()
    # Auto-commits here

# AFTER:
with get_db_context() as db:
    user = db.query(User).filter(User.id == user_id).first()
    # No commit needed for read-only operation
```

2. `pipeline/steps/email_composer/db_utils.py:121-133`
```python
# BEFORE:
with get_db_context() as db:
    email = Email(...)
    db.add(email)
    db.flush()
    # Auto-commits here

# AFTER:
with get_db_context() as db:
    email = Email(...)
    db.add(email)
    db.flush()
    db.commit()  # ✅ Explicit commit
```

**Risk**: ⚠️ **MEDIUM** - Changes transaction semantics
- **Mitigation**: Only 2 files use this, easy to verify
- **Testing**: Run full pipeline test to ensure writes still work

---

### 2.2 Add Timeouts to LLM Agent Calls

**Files**: All pipeline steps using `create_agent()`

**Current Code** (❌ NO TIMEOUT):
```python
agent = create_agent(
    model=self.model,
    retries=2,
    system_prompt=system_prompt
)
# If API hangs, task hangs forever!
```

**Problem**:
- External API calls can hang indefinitely
- Celery tasks can get stuck in RUNNING state
- No timeout means no guarantee of task completion
- Can exhaust worker pool

**Fixed Code** (✅ WITH TIMEOUT):
```python
agent = create_agent(
    model=self.model,
    retries=2,
    system_prompt=system_prompt,
    timeout=30.0  # 30 second timeout per API call
)
```

**Recommended Timeouts**:
- Template Parser: 30s (simple JSON extraction)
- Web Scraper: 60s (may need to wait for page load)
- Email Composer: 45s (generating email content)

**Files to Update**:
- `pipeline/steps/template_parser/main.py:85`
- `pipeline/steps/email_composer/main.py:248`
- Any other agent creation calls

**Risk**: ⚠️ **LOW** - May need to tune timeout values
- **Mitigation**: Start conservative (60s), reduce based on monitoring
- **Testing**: Test with slow network conditions

---

### 2.3 Standardize UUID Handling

**Problem**: Inconsistent UUID types across the codebase

**Current Inconsistencies**:
```python
# API layer uses strings:
@router.post("/generate/{user_id}")
async def generate_email(user_id: str, ...)  # String

# Database layer uses UUID:
def write_email_to_db(user_id: UUID, ...)  # UUID object

# Tasks layer converts:
user_id_uuid = UUID(user_id)  # Manual conversion
```

**Recommended Standard**:
1. **API Boundary**: Accept `str` in path/query parameters
2. **Internal Processing**: Convert to `UUID` immediately after validation
3. **Database Layer**: Use `UUID` type for all DB operations
4. **Serialization**: Convert back to `str` for JSON responses

**Implementation**:

**Create Utility** (`utils/uuid_helpers.py`):
```python
from uuid import UUID
from typing import Union

def ensure_uuid(value: Union[str, UUID]) -> UUID:
    """Convert string to UUID, or return UUID unchanged."""
    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except ValueError as e:
        raise ValueError(f"Invalid UUID format: {value}") from e

def ensure_str(value: Union[str, UUID]) -> str:
    """Convert UUID to string, or return string unchanged."""
    return str(value)
```

**Update API Routes**:
```python
# Before:
@router.post("/generate/{user_id}")
async def generate_email(user_id: str, ...):
    # Use string directly

# After:
from utils.uuid_helpers import ensure_uuid

@router.post("/generate/{user_id}")
async def generate_email(user_id: str, ...):
    user_uuid = ensure_uuid(user_id)  # Validate early
    # Use user_uuid for all internal operations
```

**Risk**: ⚠️ **MEDIUM** - Touches many files
- **Mitigation**: Create utility first, update incrementally
- **Testing**: Add unit tests for UUID validation

---

### 2.4 Simplify CORS Configuration

**File**: `config/settings.py`

**Problem**: Duplicate parsing logic for CORS origins

**Current Code**:
```python
# Validator parses to list:
@field_validator("allowed_origins")
@classmethod
def parse_origins(cls, v: str) -> List[str]:
    if isinstance(v, str):
        return [origin.strip() for origin in v.split(",") if origin.strip()]
    return v

# Property ALSO parses to list (redundant!):
@property
def cors_origins(self) -> List[str]:
    if isinstance(self.allowed_origins, list):
        return self.allowed_origins
    # This code is unreachable - validator already converted to list!
    return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
```

**Simplified Code**:
```python
# Keep validator only:
@field_validator("allowed_origins")
@classmethod
def parse_origins(cls, v: str) -> List[str]:
    """Parse comma-separated origins into a list."""
    if isinstance(v, str):
        return [origin.strip() for origin in v.split(",") if origin.strip()]
    return v

# DELETE the property entirely - allowed_origins is already a list!
```

**Update Usage** (`main.py:85`):
```python
# Before:
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Property
    ...
)

# After:
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,  # Direct field access
    ...
)
```

**Risk**: ✅ **NONE** - Functionally equivalent, just cleaner

---

## Phase 3: Code Simplification & DRY Principles

**Priority**: 🟡 MEDIUM
**Estimated Time**: 2 hours
**Risk Level**: Low
**Impact**: Medium (maintainability)

### 3.1 Extract Error Formatting Helper

**File**: `api/routes/email.py:158-183`

**Problem**: Celery task error formatting is duplicated and verbose

**Current Code** (❌ VERBOSE):
```python
if isinstance(result.info, dict):
    error_msg = result.info.get("exc_message", "Unknown error")
    error_type = result.info.get("exc_type", "Error")
    failed_step = result.info.get("failed_step")
    response_data["error"] = {
        "message": error_msg,
        "type": error_type,
        "failed_step": failed_step
    }
else:
    error_msg = str(result.info) if result.info else "Unknown error"
    response_data["error"] = error_msg
```

**Create Utility** (`utils/celery_helpers.py`):
```python
from typing import Any, Dict, Union

def format_celery_error(result_info: Any) -> Union[Dict[str, Any], str]:
    """
    Format Celery task error information for API responses.

    Args:
        result_info: Error info from AsyncResult.info

    Returns:
        Formatted error dict or string
    """
    if not isinstance(result_info, dict):
        return str(result_info) if result_info else "Unknown error"

    return {
        "message": result_info.get("exc_message", "Unknown error"),
        "type": result_info.get("exc_type", "Error"),
        "failed_step": result_info.get("failed_step")
    }
```

**Simplified Usage**:
```python
from utils.celery_helpers import format_celery_error

# Clean and simple:
response_data["error"] = format_celery_error(result.info)
```

**Risk**: ✅ **NONE** - Pure refactoring

---

### 3.2 Simplify Database URL Sanitization

**File**: `database/utils.py:100-111`

**Current Code** (❌ NESTED CONDITIONALS):
```python
db_url = settings.database_url
if "@" in db_url:
    protocol, rest = db_url.split("://")
    if "@" in rest:
        credentials, host = rest.split("@")
        username = credentials.split(":")[0] if ":" in credentials else credentials
        db_url_sanitized = f"{protocol}://{username}:***@{host}"
    else:
        db_url_sanitized = db_url
else:
    db_url_sanitized = db_url
```

**Simplified Code** (✅ EARLY RETURN):
```python
def sanitize_db_url(url: str) -> str:
    """
    Hide password in database URL for logging.

    Example:
        postgresql://user:password@host/db
        -> postgresql://user:***@host/db
    """
    if "@" not in url:
        return url

    try:
        protocol, rest = url.split("://", 1)
        credentials, host = rest.split("@", 1)
        username = credentials.split(":", 1)[0]
        return f"{protocol}://{username}:***@{host}"
    except ValueError:
        # Malformed URL, return as-is
        return url

# Usage:
db_url_sanitized = sanitize_db_url(settings.database_url)
```

**Benefits**:
- Early return pattern (more Pythonic)
- Explicit error handling
- Clearer intent with function name
- Single responsibility

**Risk**: ✅ **NONE** - Pure refactoring

---

### 3.3 Create Shared Validation Utilities

**Problem**: User validation logic duplicated across files

**Current Duplicates**:

1. `api/routes/email.py` - Checks user ownership
2. `pipeline/steps/email_composer/db_utils.py:91-100` - Validates user exists
3. Similar patterns elsewhere

**Create Utility** (`utils/validators.py`):
```python
from uuid import UUID
from sqlalchemy.orm import Session
from models.user import User
from fastapi import HTTPException, status

def validate_user_exists(db: Session, user_id: UUID) -> User:
    """
    Validate that a user exists in the database.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        User object if found

    Raises:
        HTTPException: 404 if user not found
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}"
        )
    return user

def validate_email_ownership(db: Session, email_id: UUID, user_id: UUID) -> Email:
    """
    Validate that an email belongs to the specified user.

    Returns:
        Email object if found and owned by user

    Raises:
        HTTPException: 404 if not found, 403 if not owned by user
    """
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email not found: {email_id}"
        )
    if email.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this email"
        )
    return email
```

**Risk**: ⚠️ **LOW** - New utility, incremental adoption

---

### 3.4 Remove Pipeline Retry Duplication

**File**: `pipeline/steps/email_composer/main.py:230-283`

**Problem**: Manual retry loop duplicates agent's built-in retry mechanism

**Current Code** (❌ DUPLICATE RETRY LOGIC):
```python
# Agent already has retries configured!
agent = create_agent(model=self.model, retries=2, ...)

# But then we ALSO do manual retry loop:
max_retries = 3
for attempt in range(max_retries):
    try:
        result = agent.run(...)
        break
    except Exception as e:
        if attempt < max_retries - 1:
            continue
        else:
            raise
```

**Simplified Code** (✅ TRUST AGENT RETRIES):
```python
# Just configure agent with appropriate retries:
agent = create_agent(
    model=self.model,
    retries=3,  # Agent handles retries internally
    ...
)

# Single call, agent handles retries:
result = agent.run(...)
```

**Risk**: ⚠️ **LOW** - Agent retry mechanism is already tested
- **Mitigation**: Verify agent retries work as expected
- **Testing**: Test with simulated API failures

---

## Phase 4: Best Practices & Code Quality

**Priority**: 🟢 MEDIUM
**Estimated Time**: 3 hours
**Risk Level**: Very Low
**Impact**: Medium (code clarity)

### 4.1 Replace print() with Structured Logging

**Problem**: 15+ instances of `print()` statements in production code

**Locations**:
- `main.py:27-62` - Startup banner (11 print statements)
- `services/supabase.py:43,45` - Client initialization (2 prints)
- `celery_config.py:94,103,110` - Worker init (3 prints)

**Why This Matters**:
1. **No Log Levels**: Can't filter by severity
2. **No Structured Data**: Can't query/analyze
3. **Goes to stdout**: Hard to capture in production
4. **No Context**: Missing timestamps, request IDs
5. **Not Production-Ready**: Logs should go through proper logging system

**Migration Strategy**:

**1. Main Application Startup** (`main.py:27-62`):
```python
# BEFORE:
print("=" * 80)
print(" SCRIBE - Email Generation API")
print(f" Database: {db_url_sanitized}")
print("=" * 80)

# AFTER:
import logfire

logger = logfire.get_logger(__name__)

logger.info(
    "Application startup",
    app_name="SCRIBE - Email Generation API",
    database_url=db_url_sanitized,
    supabase_url=settings.supabase_url,
    environment=os.getenv("ENVIRONMENT", "development")
)
```

**2. Supabase Client** (`services/supabase.py:43,45`):
```python
# BEFORE:
print(f" Supabase client initialized: {settings.supabase_url}")
print(f" Using service role key: {settings.supabase_service_role_key[:10]}...")

# AFTER:
import logfire

logfire.info(
    "Supabase client initialized",
    url=settings.supabase_url,
    service_role_key_prefix=settings.supabase_service_role_key[:10]
)
```

**3. Celery Worker** (`celery_config.py:94,103,110`):
```python
# BEFORE:
print(f"Worker {worker.hostname} is ready")

# AFTER:
import logfire

logfire.info(
    "Celery worker ready",
    hostname=worker.hostname,
    concurrency=worker.concurrency
)
```

**Benefits**:
- Structured logs can be queried in Logfire dashboard
- Automatic timestamps and context
- Log levels for filtering (INFO, WARNING, ERROR)
- Better production monitoring

**Risk**: ✅ **NONE** - Logfire already configured in project

---

### 4.2 Add Missing Type Hints

**Files**:
- `database/utils.py` - Functions missing return types

**Current Code**:
```python
def init_db():  # ❌ No return type
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)

def drop_db():  # ❌ No return type
    """Drop all database tables."""
    Base.metadata.drop_all(bind=engine)

def reset_db():  # ❌ No return type
    """Reset database (drop and recreate)."""
    drop_db()
    init_db()
```

**Fixed Code**:
```python
def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)

def drop_db() -> None:
    """Drop all database tables."""
    Base.metadata.drop_all(bind=engine)

def reset_db() -> None:
    """Reset database (drop and recreate)."""
    drop_db()
    init_db()
```

**Other Files to Check**:
- Any helper functions in `utils/`
- Pipeline step methods

**Risk**: ✅ **NONE** - Type hints are documentation, don't affect runtime

---

### 4.3 Add Comprehensive Docstrings

**File**: `database/base.py`

**Current Code** (❌ NO DOCSTRINGS):
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config.settings import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
```

**Improved Code** (✅ WITH DOCSTRINGS):
```python
"""
Database configuration and SQLAlchemy setup.

This module provides the core database infrastructure:
- SQLAlchemy engine for connection pooling
- Session factory for database transactions
- Declarative base for ORM models
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config.settings import settings

# Database engine - handles connection pooling and execution
# Connection pool size controlled by SQLAlchemy defaults
engine = create_engine(
    settings.database_url,
    echo=False,  # Set to True for SQL query logging
    pool_pre_ping=True,  # Verify connections before using
)

# Session factory - creates new database sessions
# Use with dependency injection (Depends(get_db)) in FastAPI routes
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,  # Explicit commits required
    autoflush=False,   # Explicit flush control
)

# Declarative base for ORM models
# All models should inherit from this base class
Base = declarative_base()
```

**Other Files Needing Docstrings**:
- `config/settings.py` - Document all settings
- Pipeline step classes - Document parameters and return values

**Risk**: ✅ **NONE** - Documentation only

---

### 4.4 Improve Exception Specificity

**File**: `api/dependencies.py:82-86`

**Current Code** (❌ TOO BROAD):
```python
try:
    user_data = supabase_client.auth.get_user(token)
except Exception as e:  # Catches EVERYTHING - too broad!
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Token validation failed: {str(e)}",
    )
```

**Problems**:
1. Catches all exceptions (network errors, bugs, etc.)
2. Treats all errors as auth failures (may not be true)
3. Hard to debug - no distinction between error types
4. May hide real bugs in application code

**Improved Code** (✅ SPECIFIC EXCEPTIONS):
```python
import logfire
from gotrue.errors import AuthApiError

try:
    user_data = supabase_client.auth.get_user(token)
except AuthApiError as e:
    # Specific Supabase auth error - this is expected
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Invalid or expired token: {str(e)}",
    )
except ValueError as e:
    # Malformed token
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Malformed token: {str(e)}",
    )
except Exception as e:
    # Unexpected error - log for investigation
    logfire.exception(
        "Unexpected error during token validation",
        error=str(e),
        error_type=type(e).__name__
    )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Authentication service error",
    )
```

**Benefits**:
- Proper HTTP status codes (401 vs 400 vs 500)
- Better error messages for debugging
- Logs unexpected errors for investigation
- Follows fail-fast principle

**Risk**: ⚠️ **LOW** - Need to identify correct Supabase exception types
- **Mitigation**: Test with invalid tokens to verify exception types

---

### 4.5 Add Content Quality Validation in Pipeline

**File**: `pipeline/steps/web_scraper/main.py`

**Problem**: No validation that scraped content is sufficient for email generation

**Current Code** (❌ NO VALIDATION):
```python
async def execute(self, data: PipelineData) -> StepResult:
    # Scrape content...
    data.scraped_content = scraped_text

    # Immediately return success - what if content is empty?
    return StepResult(success=True)
```

**Improved Code** (✅ WITH VALIDATION):
```python
async def execute(self, data: PipelineData) -> StepResult:
    # Scrape content...
    data.scraped_content = scraped_text

    # Validate content quality
    if not scraped_text or len(scraped_text.strip()) < 100:
        return StepResult(
            success=False,
            error="Insufficient content scraped (minimum 100 characters required)",
            metadata={
                "scraped_length": len(scraped_text) if scraped_text else 0,
                "search_terms": data.search_terms
            }
        )

    # Check for error messages in scraped content
    if "404" in scraped_text or "Page not found" in scraped_text:
        return StepResult(
            success=False,
            error="Scraped content appears to be an error page"
        )

    return StepResult(
        success=True,
        metadata={"content_length": len(scraped_text)}
    )
```

**Benefits**:
- Fail fast if scraping didn't work
- Better error messages for debugging
- Prevents wasted LLM calls on bad data
- Improves pipeline reliability

**Risk**: ⚠️ **LOW** - May need to tune validation thresholds
- **Mitigation**: Start with conservative threshold (100 chars), adjust based on testing

---

### 4.6 Standardize Import Order

**Current**: Inconsistent import ordering across files

**Standard** (PEP 8):
```python
# 1. Standard library imports
import os
import sys
from typing import List, Optional
from uuid import UUID

# 2. Third-party imports
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

# 3. Local application imports
from config.settings import settings
from database.dependencies import get_db
from models.user import User
```

**Tool**: Use `isort` to auto-format
```bash
pip install isort
isort . --profile black
```

**Risk**: ✅ **NONE** - Cosmetic change

---

## Phase 5: Testing & Validation

**Priority**: 🟢 CRITICAL
**Estimated Time**: 1 hour
**Risk Level**: N/A (validation phase)

### 5.1 Pre-Change Baseline

**Run Full Test Suite**:
```bash
source venv/bin/activate
pytest -v --cov=. --cov-report=html

# Save baseline coverage report
mv htmlcov htmlcov_baseline
```

**Test Health Endpoint**:
```bash
curl http://localhost:8000/health | jq
```

**Test Email Generation**:
```bash
# Use test_email_api.py with environment variable JWT
export TEST_JWT_TOKEN="your_test_token"
python test_email_api.py
```

---

### 5.2 Post-Phase Testing

**After Phase 1** (Dead Code Removal):
```bash
# Verify application starts
uvicorn main:app --reload

# Verify no import errors
python -c "from api.routes import user, email; print('OK')"

# Run tests
pytest -v
```

**After Phase 2** (Architecture Changes):
```bash
# Test database operations
pytest -k "test_database" -v

# Test email generation pipeline
pytest -k "test_pipeline" -v

# Manual pipeline test
python test_email_api.py
```

**After Phase 3** (Simplifications):
```bash
# Run full test suite
pytest -v

# Verify no regressions
pytest --cov=. --cov-report=html
diff -r htmlcov_baseline htmlcov  # Compare coverage
```

**After Phase 4** (Best Practices):
```bash
# Check type hints
mypy . --ignore-missing-imports

# Check import ordering
isort . --check --profile black

# Check code style
ruff check .

# Run full test suite
pytest -v
```

---

### 5.3 Integration Testing

**Manual Test Checklist**:

- [ ] User initialization (`POST /api/user/init`)
- [ ] Email generation (`POST /api/email/generate`)
- [ ] Task status check (`GET /api/email/status/{task_id}`)
- [ ] Database writes (check Supabase)
- [ ] Error handling (invalid tokens, missing users)
- [ ] Celery worker processing (check logs)

**Production Smoke Test** (if applicable):
```bash
# Test production endpoint
curl https://your-app.com/health

# Generate test email
curl -X POST https://your-app.com/api/email/generate \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"template": "...", "recipient_name": "Test"}'
```

---

## Risk Assessment

### Overall Risk Matrix

| Phase | Risk Level | Mitigation | Rollback Complexity |
|-------|-----------|-----------|---------------------|
| Phase 1 | ✅ Low | No dependencies, pure deletion | Easy (git revert) |
| Phase 2 | ⚠️ Medium | Only 2 files use context manager | Medium (targeted revert) |
| Phase 3 | ✅ Low | Pure refactoring | Easy (git revert) |
| Phase 4 | ✅ Very Low | Documentation/logging only | Easy (git revert) |
| Phase 5 | N/A | Testing phase | N/A |

### Risk Factors

**High Risk Changes** (require extra testing):
1. Database context manager modification (Phase 2.1)
2. UUID standardization (Phase 2.3)
3. Removing retry duplication (Phase 3.4)

**Low Risk Changes** (safe to batch):
1. Deleting legacy code (Phase 1)
2. Removing unused imports (Phase 1.4)
3. Adding docstrings (Phase 4.3)
4. Replacing print() with logging (Phase 4.1)

---

## Rollback Strategy

### Per-Phase Rollback

**Recommended Approach**: Implement each phase in a separate commit

```bash
# Phase 1 commit
git add api/legacy/ test_email_api.py pipeline/models/core.py
git commit -m "Phase 1: Remove dead code and security issues"

# Phase 2 commit
git add database/session.py pipeline/steps/
git commit -m "Phase 2: Architecture improvements"

# If Phase 2 breaks something:
git revert HEAD  # Rollback Phase 2 only
```

### Emergency Rollback

**If production breaks after deployment**:

```bash
# 1. Immediate rollback via deployment
git revert HEAD~4..HEAD  # Revert last 4 commits (all phases)
git push origin main

# 2. Redeploy previous version
# (Follow your deployment process)

# 3. Investigation
git log --oneline -10  # Review recent commits
git diff HEAD~4 HEAD   # See what changed
```

### Partial Rollback

**If specific change causes issues**:

```bash
# Find the specific file change
git log --oneline -- database/session.py

# Revert just that file
git checkout HEAD~1 -- database/session.py
git commit -m "Rollback: Revert database context manager changes"
```

---

## Implementation Checklist

### Pre-Implementation

- [ ] Create feature branch: `git checkout -b code-cleanup`
- [ ] Run baseline tests and save coverage report
- [ ] Back up database (if making schema changes)
- [ ] Review this document with team

### Phase 1: Security & Dead Code

- [ ] Delete `/api/legacy/` directory
- [ ] Update `test_email_api.py` to use env var for JWT
- [ ] Remove commented-out code blocks
- [ ] Remove unused imports
- [ ] Run tests: `pytest -v`
- [ ] Commit: `git commit -m "Phase 1: Remove dead code and security issues"`

### Phase 2: Architecture

- [ ] Fix database context manager
- [ ] Update context manager usages (2 files)
- [ ] Add LLM API timeouts (3+ files)
- [ ] Simplify CORS configuration
- [ ] Create UUID helpers utility
- [ ] Run tests: `pytest -k "test_database or test_pipeline" -v`
- [ ] Manual test: `python test_email_api.py`
- [ ] Commit: `git commit -m "Phase 2: Architecture improvements"`

### Phase 3: Simplification

- [ ] Create `utils/celery_helpers.py`
- [ ] Create `utils/validators.py`
- [ ] Simplify database URL sanitization
- [ ] Remove pipeline retry duplication
- [ ] Update error formatting in routes
- [ ] Run tests: `pytest -v`
- [ ] Commit: `git commit -m "Phase 3: Code simplification and DRY"`

### Phase 4: Best Practices

- [ ] Replace print() with logfire (main.py)
- [ ] Replace print() with logfire (services/supabase.py)
- [ ] Replace print() with logfire (celery_config.py)
- [ ] Add missing type hints
- [ ] Add docstrings to database/base.py
- [ ] Improve exception specificity
- [ ] Add content validation in web scraper
- [ ] Run linters: `ruff check .` and `mypy .`
- [ ] Commit: `git commit -m "Phase 4: Best practices and code quality"`

### Phase 5: Validation

- [ ] Run full test suite: `pytest -v --cov=.`
- [ ] Compare coverage with baseline
- [ ] Manual integration test (full email generation)
- [ ] Check Celery worker logs
- [ ] Verify database writes
- [ ] Test error scenarios
- [ ] Code review (if team process)

### Post-Implementation

- [ ] Merge to main: `git checkout main && git merge code-cleanup`
- [ ] Deploy to staging
- [ ] Smoke test staging environment
- [ ] Deploy to production
- [ ] Monitor logs for 24 hours
- [ ] Update team documentation

---

## Success Metrics

**Before Cleanup**:
- Total Lines of Code: ~X
- Dead Code: 867 lines
- Security Issues: 2
- Print Statements: 15+
- Missing Type Hints: 10+
- Code Health Score: 7.5/10

**After Cleanup** (Target):
- Total Lines of Code: ~X - 850 (after deletions, before additions)
- Dead Code: 0 lines
- Security Issues: 0
- Print Statements: 0 (all converted to structured logging)
- Missing Type Hints: 0
- Code Health Score: 9.0+/10

**Quality Improvements**:
- ✅ All security issues resolved
- ✅ Transaction semantics fixed
- ✅ Consistent error handling
- ✅ Structured logging throughout
- ✅ Type safety improved
- ✅ Documentation complete

---

## Questions & Decisions

### Open Questions

1. **UUID Standardization**: Should we use `UUID` or `str` in Pydantic schemas?
   - **Recommendation**: Use `str` in API schemas, convert internally

2. **Timeout Values**: What's appropriate for each pipeline step?
   - **Recommendation**: Start at 60s, tune based on monitoring

3. **Logging Level**: Should startup messages be INFO or DEBUG?
   - **Recommendation**: INFO for key events, DEBUG for details

4. **Test Coverage**: What's the minimum acceptable coverage?
   - **Current**: Needs baseline measurement
   - **Target**: Maintain or improve current coverage

### Design Decisions

**Decision 1**: Remove auto-commit from context manager
- **Rationale**: Explicit is better than implicit (Zen of Python)
- **Trade-off**: Requires manual commits, but safer

**Decision 2**: Delete entire `/api/legacy/` directory
- **Rationale**: Not referenced anywhere, contains security issues
- **Trade-off**: Loses old code, but it's in git history

**Decision 3**: Standardize on structured logging
- **Rationale**: Production-ready observability
- **Trade-off**: More verbose than print(), but much more useful

---

## Appendix

### A. Files Affected by Phase

**Phase 1** (7 files):
- DELETE: `api/legacy/app.py`
- DELETE: `api/legacy/gmailapp.py`
- DELETE: `api/legacy/scholarpage.py`
- MODIFY: `test_email_api.py`
- MODIFY: `pipeline/models/core.py`
- MODIFY: `models/user.py`
- MODIFY: `database/session.py`

**Phase 2** (10+ files):
- `database/session.py`
- `pipeline/steps/email_composer/db_utils.py`
- `pipeline/steps/template_parser/main.py`
- `pipeline/steps/email_composer/main.py`
- `config/settings.py`
- `main.py`
- CREATE: `utils/uuid_helpers.py`

**Phase 3** (8 files):
- CREATE: `utils/celery_helpers.py`
- CREATE: `utils/validators.py`
- `api/routes/email.py`
- `database/utils.py`
- `pipeline/steps/email_composer/main.py`

**Phase 4** (15+ files):
- `main.py`
- `services/supabase.py`
- `celery_config.py`
- `database/base.py`
- `database/utils.py`
- `api/dependencies.py`
- `pipeline/steps/web_scraper/main.py`
- All files (import ordering)

### B. Estimated Time Breakdown

| Phase | Task | Time |
|-------|------|------|
| Phase 1 | Delete files | 15 min |
| Phase 1 | Update test file | 15 min |
| Phase 1 | Remove comments/imports | 30 min |
| Phase 2 | Context manager fix | 30 min |
| Phase 2 | Add timeouts | 30 min |
| Phase 2 | UUID standardization | 45 min |
| Phase 2 | CORS simplification | 15 min |
| Phase 3 | Create utilities | 45 min |
| Phase 3 | Refactor usages | 45 min |
| Phase 3 | Remove retry duplication | 30 min |
| Phase 4 | Convert to logging | 60 min |
| Phase 4 | Add type hints | 30 min |
| Phase 4 | Add docstrings | 45 min |
| Phase 4 | Improve exceptions | 30 min |
| Phase 4 | Add validations | 15 min |
| Phase 5 | Testing | 60 min |
| **TOTAL** | | **8 hours** |

### C. Git Commit Template

```bash
# Phase 1
git commit -m "refactor: remove dead code and fix security issues

- Delete entire /api/legacy/ directory (867 lines)
- Remove exposed OpenAI API key
- Replace hardcoded JWT with env var in test file
- Remove commented-out deprecated code
- Remove unused imports

BREAKING CHANGE: None (dead code only)
"

# Phase 2
git commit -m "refactor: fix architecture anti-patterns

- Fix database context manager auto-commit
- Add LLM API timeouts to prevent hung tasks
- Standardize UUID handling across codebase
- Simplify CORS configuration parsing

BREAKING CHANGE: Context manager no longer auto-commits
"

# Phase 3
git commit -m "refactor: simplify code and apply DRY principles

- Extract error formatting helper
- Create shared validation utilities
- Simplify database URL sanitization
- Remove duplicate retry logic

BREAKING CHANGE: None
"

# Phase 4
git commit -m "refactor: improve code quality and best practices

- Replace print() with structured logging
- Add missing type hints
- Add comprehensive docstrings
- Improve exception specificity
- Add pipeline content validation

BREAKING CHANGE: None
"
```

---

## Conclusion

This cleanup plan addresses **security vulnerabilities**, **architectural anti-patterns**, and **technical debt** while maintaining **backward compatibility** and **stability**.

**Key Benefits**:
1. ✅ **Security**: Removes exposed API key and hardcoded secrets
2. ✅ **Maintainability**: Reduces codebase by ~850 lines
3. ✅ **Reliability**: Fixes transaction semantics and adds timeouts
4. ✅ **Observability**: Structured logging for production monitoring
5. ✅ **Quality**: Type safety, documentation, and best practices

**Recommended Execution Order**:
1. **Phase 1 FIRST** (security critical)
2. **Phase 2** (high impact on reliability)
3. **Phases 3-4** (quality improvements, can be done together)
4. **Phase 5** (comprehensive testing)

**Total Effort**: ~8 hours of focused development time + testing

**Questions?** Review each phase and mark which changes you'd like to implement. We can also execute phases incrementally based on your priorities.
