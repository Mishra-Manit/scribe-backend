# Phase 1: Infrastructure Foundation - Setup Guide

## Overview

Phase 1 establishes the foundational infrastructure for the agentic pipeline system:
- ✅ Redis configuration for Celery broker/backend
- ✅ Celery task queue with routing
- ✅ Logfire observability integration
- ✅ Environment variable management
- ✅ FastAPI integration

## Files Created

### Configuration Files
- `config/redis_config.py` - Redis settings with Pydantic validation
- `celery_config.py` - Celery app configuration and task routing
- `observability/logfire_config.py` - Logfire initialization singleton

### Directories
- `celery_tasks/` - Celery task definitions (structure ready for Phase 6)
- `observability/` - Observability and monitoring modules
- `scripts/` - Utility scripts

### Updated Files
- `requirements.txt` - Added celery, redis, flower, logfire, httpx[http2]
- `.env.example` - Added REDIS_*, LOGFIRE_TOKEN, ANTHROPIC_API_KEY
- `main.py` - Integrated Logfire initialization on startup

## Installation Steps

### 1. Install Dependencies

```bash
# Install all new dependencies
pip install -r requirements.txt

# This includes:
# - celery>=5.3.0
# - redis>=5.0.0
# - flower>=2.0.0
# - logfire>=0.28.0
# - httpx[http2]>=0.27.0
```

### 2. Install and Start Redis

**macOS (Homebrew):**
```bash
brew install redis
brew services start redis

# Verify Redis is running
redis-cli ping
# Should return: PONG
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify
redis-cli ping
```

### 3. Configure Environment Variables

Update your `.env` file with the new variables:

```bash
# Copy from example if needed
cp .env.example .env

# Add these new variables to .env:
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Optional: Logfire token (get from https://logfire.pydantic.dev)
LOGFIRE_TOKEN=your-logfire-token-here

# Required: Anthropic API key for email generation
ANTHROPIC_API_KEY=your-anthropic-api-key-here
```

### 4. Test Infrastructure

Run the smoke test to verify everything is configured correctly:

```bash
python scripts/test_infrastructure.py
```

Expected output:
```
======================================================================
                    INFRASTRUCTURE SMOKE TEST
======================================================================

✓ PASS      Redis Config
✓ PASS      Logfire Config
✓ PASS      Celery Config
⚠️  SKIP     Redis Connection  # If Redis not running yet
```

### 5. Start Celery Worker (Optional for Phase 1)

```bash
# Start Celery worker in development mode
celery -A celery_config.celery_app worker --loglevel=info --queues=email_default

# Start Flower monitoring UI (optional)
celery -A celery_config.celery_app flower --port=5555
# Access at http://localhost:5555
```

### 6. Test Health Check Task

```bash
# In Python shell or script
from celery_config import health_check

# Synchronous execution (for testing)
result = health_check()
print(result)
# Output: {'status': 'healthy', 'service': 'celery-worker'}

# Async execution (requires worker running)
task = health_check.delay()
print(task.id)  # Task ID
print(task.get(timeout=5))  # Wait for result
```

## Configuration Details

### Redis Settings

The `RedisSettings` class automatically constructs connection URLs:

- **Broker URL**: `redis://localhost:6379/0`
- **Result Backend**: `redis://localhost:6379/1` (uses DB+1)

With password:
- `redis://:password@localhost:6379/0`

### Celery Configuration

Key settings in `celery_config.py`:

- **Serialization**: JSON only (secure)
- **Task routing**: `email_default` queue for email generation
- **Retry policy**: Max 3 retries, 60s initial countdown, exponential backoff
- **Worker prefetch**: 1 task at a time (prevents memory issues)
- **Task acks**: Late acknowledgment (ensures tasks complete before ack)

### Logfire Integration

Logfire initializes on application startup via `main.py`:

- **Service name**: `scribe-pipeline`
- **Console logging**: Enabled (logs to both Logfire and console)
- **Graceful degradation**: App works without Logfire token (logs warning)

## Verification Checklist

- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] Redis running and accessible (`redis-cli ping`)
- [ ] `.env` file updated with Redis and API keys
- [ ] Smoke test passes (`python scripts/test_infrastructure.py`)
- [ ] FastAPI starts without errors (`uvicorn main:app --reload`)
- [ ] Logfire initializes (check startup logs)
- [ ] Celery worker can start (optional for Phase 1)

## Troubleshooting

### Issue: Redis connection failed

**Solution:**
```bash
# Check if Redis is running
redis-cli ping

# If not, start Redis
brew services start redis  # macOS
sudo systemctl start redis-server  # Linux
```

### Issue: Pydantic validation errors on RedisSettings

**Cause**: Extra fields from `.env` being rejected

**Solution**: The `RedisSettings` class now has `extra = "ignore"` to handle this

### Issue: Logfire import error

**Cause**: Logfire package not installed

**Solution:**
```bash
pip install logfire>=0.28.0
```

### Issue: Celery worker won't start

**Check:**
1. Redis is running: `redis-cli ping`
2. Configuration is valid: `python -c "from celery_config import celery_app; print(celery_app.conf.broker_url)"`
3. Python path includes project root

## Next Steps

Phase 1 is complete! You can now proceed to:

**Phase 2: Database Schema Migration**
- Add `template_type` and `metadata` columns to emails table
- Create Alembic migration
- Test migration

See the implementation plan for detailed Phase 2 tasks.

## Production Deployment Notes

For production deployment, consider:

1. **Redis**: Use managed Redis service (Redis Cloud, AWS ElastiCache, etc.)
2. **Celery workers**: Run in separate containers/dynos
3. **Logfire**: Create production project with appropriate retention
4. **Environment variables**: Use secure secret management (not .env files)
5. **Monitoring**: Set up Flower or Celery events monitoring

## Resources

- [Celery Documentation](https://docs.celeryq.dev/)
- [Redis Documentation](https://redis.io/docs/)
- [Logfire Documentation](https://logfire.pydantic.dev/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
